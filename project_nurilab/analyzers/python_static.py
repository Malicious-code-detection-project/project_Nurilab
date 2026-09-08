"""AST-based Python static analyzer for the phase 1 MVP."""

from __future__ import annotations

import ast

from project_nurilab.analyzers.patterns import SUSPICIOUS_CALL_RULES, SuspiciousCallRule
from project_nurilab.analyzers.secrets import find_potential_secrets
from project_nurilab.input.manager import LoadedPythonFile
from project_nurilab.schemas import (
    CodeSymbol,
    ImportFinding,
    PythonAnalysis,
    SuspiciousCall,
)


class PythonStaticAnalyzer:
    """Extract review-oriented static signals from one Python file."""

    def analyze(self, loaded_file: LoadedPythonFile) -> PythonAnalysis:
        """Analyze a loaded Python file and return a normalized result."""

        analysis = PythonAnalysis(
            path=str(loaded_file.path),
            line_count=len(loaded_file.lines),
            skipped=loaded_file.skipped,
            skip_reason=loaded_file.skip_reason,
        )

        if loaded_file.skipped:
            return analysis

        analysis.secrets = find_potential_secrets(loaded_file.lines)

        try:
            tree = ast.parse(loaded_file.source, filename=str(loaded_file.path))
        except SyntaxError as exc:
            analysis.syntax_error = self._format_syntax_error(exc)
            return analysis

        visitor = _PythonSignalVisitor()
        visitor.visit(tree)

        analysis.imports = visitor.imports
        analysis.functions = visitor.functions
        analysis.classes = visitor.classes
        analysis.suspicious_calls = visitor.suspicious_calls
        return analysis

    @staticmethod
    def _format_syntax_error(exc: SyntaxError) -> str:
        """Produce a compact syntax error string suitable for reports."""

        location = f"line {exc.lineno}" if exc.lineno else "unknown line"
        return f"{location}: {exc.msg}"


class _PythonSignalVisitor(ast.NodeVisitor):
    """Collect static code review signals from a Python AST."""

    def __init__(self) -> None:
        self.imports: list[ImportFinding] = []
        self.functions: list[CodeSymbol] = []
        self.classes: list[CodeSymbol] = []
        self.suspicious_calls: list[SuspiciousCall] = []
        self._import_bindings: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self.imports.append(
                ImportFinding(
                    module=alias.name,
                    name=None,
                    alias=alias.asname,
                    line=node.lineno,
                )
            )
            binding = alias.asname or alias.name.partition(".")[0]
            canonical_name = alias.name if alias.asname else binding
            self._import_bindings[binding] = canonical_name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            self.imports.append(
                ImportFinding(
                    module=module,
                    name=alias.name,
                    alias=alias.asname,
                    line=node.lineno,
                )
            )
            if node.level == 0 and node.module and alias.name != "*":
                binding = alias.asname or alias.name
                self._import_bindings[binding] = f"{node.module}.{alias.name}"
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.functions.append(CodeSymbol(name=node.name, line=node.lineno))
        self._visit_nested_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self.functions.append(CodeSymbol(name=node.name, line=node.lineno))
        self._visit_nested_scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.classes.append(CodeSymbol(name=node.name, line=node.lineno))
        self._visit_nested_scope(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        call_name = _canonicalize_call_name(
            _resolve_call_name(node.func), self._import_bindings
        )
        rule = SUSPICIOUS_CALL_RULES.get(call_name)
        if rule:
            severity, reason = _refine_call_context(node, call_name, rule)
            self.suspicious_calls.append(
                SuspiciousCall(
                    name=call_name,
                    line=node.lineno,
                    category=rule.category,
                    severity=severity,
                    reason=reason,
                )
            )
        self.generic_visit(node)

    def _visit_nested_scope(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> None:
        """Visit a nested scope without leaking its import bindings outward."""

        outer_bindings = self._import_bindings.copy()
        self.generic_visit(node)
        self._import_bindings = outer_bindings


def _resolve_call_name(node: ast.AST) -> str:
    """Resolve common function call shapes into dotted names."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _resolve_call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _canonicalize_call_name(call_name: str, import_bindings: dict[str, str]) -> str:
    """Replace an imported root name with its canonical module path."""

    if not call_name:
        return call_name

    root, separator, remainder = call_name.partition(".")
    canonical_root = import_bindings.get(root)
    if canonical_root is None:
        return call_name
    if not separator:
        return canonical_root
    return f"{canonical_root}.{remainder}"


def _get_keyword_arg(node: ast.Call, arg_name: str) -> ast.AST | None:
    """Return the AST expression for a keyword argument, if present."""
    for kw in node.keywords:
        if kw.arg == arg_name:
            return kw.value
    return None


def _get_call_arg(node: ast.Call, position: int, arg_name: str) -> ast.AST | None:
    """Return argument at position or via keyword name."""
    if len(node.args) > position:
        return node.args[position]
    return _get_keyword_arg(node, arg_name)


def _is_dynamic_expression(node: ast.AST) -> bool:
    """Treat an expression as static only when its value is provably literal."""
    if isinstance(node, ast.Constant):
        return False
    if isinstance(node, (ast.List, ast.Tuple)):
        return any(_is_dynamic_expression(elt) for elt in node.elts)
    return True


def _extract_constant_str(node: ast.AST | None) -> str | None:
    """Return the string value if node is a string constant."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _refine_call_context(
    node: ast.Call,
    call_name: str,
    base_rule: SuspiciousCallRule,
) -> tuple[str, str]:
    """Refine severity and reason based on call arguments and execution context.

    Returns:
        A tuple of (severity, reason).
    """
    if call_name in ("subprocess.run", "subprocess.Popen"):
        shell_node = _get_keyword_arg(node, "shell")
        has_shell_true = (
            isinstance(shell_node, ast.Constant) and bool(shell_node.value) is True
        )
        if has_shell_true:
            return (
                "high",
                f"{call_name} executed with shell=True; "
                "command injection risk if input is untrusted.",
            )

        cmd_arg = _get_call_arg(node, 0, "args")
        if cmd_arg is not None and _is_dynamic_expression(cmd_arg):
            return (
                "medium",
                f"{call_name} starts external process with dynamic arguments.",
            )
        return (base_rule.severity, base_rule.reason)

    if call_name == "os.system":
        cmd_arg = _get_call_arg(node, 0, "command")
        if cmd_arg is not None and _is_dynamic_expression(cmd_arg):
            return (
                "high",
                "os.system executes shell command with dynamic input; "
                "high risk of command injection.",
            )
        return (base_rule.severity, base_rule.reason)

    if call_name in ("requests.get", "requests.post"):
        url_arg = _get_call_arg(node, 0, "url")
        if url_arg is not None and _is_dynamic_expression(url_arg):
            return (
                "medium",
                f"{call_name} called with dynamic URL; "
                "destination should be reviewed for untrusted network access.",
            )
        return (base_rule.severity, base_rule.reason)

    if call_name == "open":
        path_arg = _get_call_arg(node, 0, "file")
        path_is_dynamic = path_arg is not None and _is_dynamic_expression(path_arg)
        mode_arg = _get_call_arg(node, 1, "mode")
        mode_str = _extract_constant_str(mode_arg) if mode_arg is not None else "r"
        mode_is_dynamic = (
            mode_arg is not None
            and mode_str is None
            and _is_dynamic_expression(mode_arg)
        )
        mode_is_writable = mode_str is not None and any(
            c in mode_str for c in ("w", "a", "x", "+")
        )

        contexts: list[str] = []
        if path_is_dynamic:
            contexts.append("dynamic file path")
        if mode_is_writable:
            contexts.append(f"write/modify permissions (mode='{mode_str}')")
        elif mode_is_dynamic:
            contexts.append("dynamic mode parameter")

        if contexts:
            path_risk = (
                "; risk of path traversal or unintended file access"
                if path_is_dynamic
                else ""
            )
            return ("medium", f"open called with {' and '.join(contexts)}{path_risk}.")

        if mode_str is not None:
            return (
                "low",
                "open called for read-only access.",
            )
        return (base_rule.severity, base_rule.reason)

    return (base_rule.severity, base_rule.reason)
