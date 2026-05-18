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


def test_python_file_loader_skips_files_over_line_limit(tmp_path: Path) -> None:
    sample = tmp_path / "large.py"
    sample.write_text("\n".join("print('x')" for _ in range(3)), encoding="utf-8")

    loaded = PythonFileLoader(max_lines=2).load(sample)
    analysis = PythonStaticAnalyzer().analyze(loaded)

    assert analysis.skipped is True
    assert analysis.skip_reason is not None
    assert "exceeds" in analysis.skip_reason
