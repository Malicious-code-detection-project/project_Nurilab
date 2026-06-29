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
