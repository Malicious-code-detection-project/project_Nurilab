from __future__ import annotations

from pathlib import Path

from project_nurilab.analyzers.python_static import PythonStaticAnalyzer
from project_nurilab.input.manager import PythonFileLoader


FIXTURES = Path(__file__).parent / "fixtures"


def test_python_static_analyzer_extracts_ast_signals() -> None:
    loaded = PythonFileLoader().load(FIXTURES / "vulnerable_sample.py")
    analysis = PythonStaticAnalyzer().analyze(loaded)

    assert analysis.skipped is False
    assert analysis.syntax_error is None
    assert [item.module for item in analysis.imports] == ["os", "subprocess"]
    assert [item.name for item in analysis.functions] == ["run_command"]
    assert [item.name for item in analysis.suspicious_calls] == [
        "os.system",
        "subprocess.run",
    ]
    assert len(analysis.secrets) == 1
    assert analysis.secrets[0].kind == "api_key"


def test_python_file_loader_analyzes_files_over_previous_line_limit(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "large.py"
    source_lines = [
        "import os",
        *("print('x')" for _ in range(205)),
        "def run(command):",
        "    return os.system(command)",
    ]
    sample.write_text("\n".join(source_lines), encoding="utf-8")

    loaded = PythonFileLoader().load(sample)
    analysis = PythonStaticAnalyzer().analyze(loaded)

    assert analysis.skipped is False
    assert analysis.skip_reason is None
    assert analysis.line_count > 200
    assert [item.name for item in analysis.suspicious_calls] == ["os.system"]


def test_python_static_analyzer_resolves_imported_call_paths(tmp_path: Path) -> None:
    sample = tmp_path / "import_aliases.py"
    sample.write_text(
        "\n".join(
            [
                "import os as operating_system",
                "import subprocess as process",
                "from os import system as shell",
                "from subprocess import run",
                "from yaml import load as yaml_load",
                "from requests import get",
                "operating_system.system('echo alias')",
                "process.Popen(['echo', 'module alias'])",
                "shell('echo from import')",
                "run(['echo', 'direct from import'])",
                "yaml_load('payload')",
                "get('https://example.com')",
            ]
        ),
        encoding="utf-8",
    )

    analysis = PythonStaticAnalyzer().analyze(PythonFileLoader().load(sample))

    assert [item.name for item in analysis.suspicious_calls] == [
        "os.system",
        "subprocess.Popen",
        "os.system",
        "subprocess.run",
        "yaml.load",
        "requests.get",
    ]
    assert [item.severity for item in analysis.suspicious_calls] == [
        "high",
        "medium",
        "high",
        "medium",
        "high",
        "low",
    ]


def test_python_static_analyzer_does_not_resolve_relative_imports(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "relative_import.py"
    sample.write_text(
        "from .os import system as local_system\nlocal_system('echo local')\n",
        encoding="utf-8",
    )

    analysis = PythonStaticAnalyzer().analyze(PythonFileLoader().load(sample))

    assert analysis.suspicious_calls == []


def test_python_static_analyzer_keeps_import_bindings_in_their_scope(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "scoped_imports.py"
    sample.write_text(
        "\n".join(
            [
                "import subprocess as process",
                "def use_module_alias():",
                "    process.run(['echo', 'outer binding'])",
                "def use_local_alias():",
                "    from os import system as run",
                "    run('echo local binding')",
                "run('not imported in module scope')",
            ]
        ),
        encoding="utf-8",
    )

    analysis = PythonStaticAnalyzer().analyze(PythonFileLoader().load(sample))

    assert [item.name for item in analysis.suspicious_calls] == [
        "subprocess.run",
        "os.system",
    ]
    assert [item.line for item in analysis.suspicious_calls] == [3, 6]
