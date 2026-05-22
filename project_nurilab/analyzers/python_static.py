"""AST-based Python static analyzer for the phase 1 MVP."""

from __future__ import annotations

import ast

from project_nurilab.analyzers.patterns import SUSPICIOUS_CALL_RULES
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
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.functions.append(CodeSymbol(name=node.name, line=node.lineno))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self.functions.append(CodeSymbol(name=node.name, line=node.lineno))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.classes.append(CodeSymbol(name=node.name, line=node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        call_name = _resolve_call_name(node.func)
        rule = SUSPICIOUS_CALL_RULES.get(call_name)
        if rule:
            self.suspicious_calls.append(
                SuspiciousCall(
                    name=call_name,
                    line=node.lineno,
                    category=rule.category,
                    severity=rule.severity,
                    reason=rule.reason,
                )
            )
        self.generic_visit(node)


def _resolve_call_name(node: ast.AST) -> str:
    """Resolve common function call shapes into dotted names."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _resolve_call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""
