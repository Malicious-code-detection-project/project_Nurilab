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


def test_python_static_analyzer_subprocess_shell_context(tmp_path: Path) -> None:
    sample = tmp_path / "subprocess_shell.py"
    sample.write_text(
        "\n".join(
            [
                "import subprocess",
                "cmd = 'echo dynamic'",
                "subprocess.run(cmd, shell=True)",
                "subprocess.Popen('echo constant', shell=True)",
                "subprocess.run(['echo', 'normal'])",
                "subprocess.run(['echo', cmd])",
                "subprocess.run(['echo', 'explicit_false'], shell=False)",
            ]
        ),
        encoding="utf-8",
    )

    analysis = PythonStaticAnalyzer().analyze(PythonFileLoader().load(sample))

    calls = analysis.suspicious_calls
    assert len(calls) == 5
    # Call 1: subprocess.run with dynamic cmd and shell=True -> high
    assert calls[0].name == "subprocess.run"
    assert calls[0].severity == "high"
    assert "executed with shell=True" in calls[0].reason

    # Call 2: subprocess.Popen with constant string and shell=True -> high
    assert calls[1].name == "subprocess.Popen"
    assert calls[1].severity == "high"
    assert "executed with shell=True" in calls[1].reason

    # Call 3: subprocess.run with constant list and no shell -> medium
    assert calls[2].name == "subprocess.run"
    assert calls[2].severity == "medium"
    assert "executed with shell=True" not in calls[2].reason

    # Call 4: subprocess.run with dynamic list and no shell -> medium
    assert calls[3].name == "subprocess.run"
    assert calls[3].severity == "medium"
    assert "dynamic arguments" in calls[3].reason
    assert "executed with shell=True" not in calls[3].reason

    # Call 5: subprocess.run with constant list and explicit shell=False -> medium
    assert calls[4].name == "subprocess.run"
    assert calls[4].severity == "medium"
    assert "executed with shell=True" not in calls[4].reason
    assert calls[4].reason == calls[2].reason


def test_python_static_analyzer_open_mode_and_path_context(tmp_path: Path) -> None:
    sample = tmp_path / "open_modes.py"
    sample.write_text(
        "\n".join(
            [
                "target = 'user_file.txt'",
                "open('data.txt')",
                "open('data.txt', 'r')",
                "open('data.txt', 'w')",
                "open('data.txt', mode='a')",
                "open(target)",
                "open(target, 'r')",
            ]
        ),
        encoding="utf-8",
    )

    analysis = PythonStaticAnalyzer().analyze(PythonFileLoader().load(sample))
    calls = analysis.suspicious_calls
    assert len(calls) == 6

    # 1. read default
    assert calls[0].severity == "low"
    assert "read-only" in calls[0].reason

    # 2. explicit 'r'
    assert calls[1].severity == "low"
    assert "read-only" in calls[1].reason

    # 3. write 'w'
    assert calls[2].severity == "medium"
    assert "write/modify permissions" in calls[2].reason

    # 4. append keyword mode='a'
    assert calls[3].severity == "medium"
    assert "write/modify permissions" in calls[3].reason

    # 5. dynamic path default mode
    assert calls[4].severity == "medium"
    assert "dynamic file path" in calls[4].reason

    # 6. dynamic path with explicit read mode
    assert calls[5].severity == "medium"
    assert "dynamic file path" in calls[5].reason


def test_python_static_analyzer_os_system_dynamic_context(tmp_path: Path) -> None:
    sample = tmp_path / "system_context.py"
    sample.write_text(
        "\n".join(
            [
                "import os",
                "name = 'user'",
                "os.system('echo static')",
                "os.system('echo ' + name)",
                "os.system(f'echo {name}')",
            ]
        ),
        encoding="utf-8",
    )

    analysis = PythonStaticAnalyzer().analyze(PythonFileLoader().load(sample))
    calls = analysis.suspicious_calls
    assert len(calls) == 3

    assert calls[0].severity == "high"
    assert "dynamic input" not in calls[0].reason

    assert calls[1].severity == "high"
    assert "dynamic input" in calls[1].reason

    assert calls[2].severity == "high"
    assert "dynamic input" in calls[2].reason


def test_python_static_analyzer_requests_url_context(tmp_path: Path) -> None:
    sample = tmp_path / "requests_context.py"
    sample.write_text(
        "\n".join(
            [
                "import requests",
                "target = 'https://example.com/api'",
                "requests.get('https://example.com')",
                "requests.post('https://example.com')",
                "requests.get(target)",
                "requests.post(f'https://example.com/{target}')",
            ]
        ),
        encoding="utf-8",
    )

    analysis = PythonStaticAnalyzer().analyze(PythonFileLoader().load(sample))
    calls = analysis.suspicious_calls
    assert len(calls) == 4

    # 1. Normal get
    assert calls[0].name == "requests.get"
    assert calls[0].severity == "low"
    assert "dynamic URL" not in calls[0].reason

    # 2. Normal post
    assert calls[1].name == "requests.post"
    assert calls[1].severity == "low"
    assert "dynamic URL" not in calls[1].reason

    # 3. get with dynamic URL
    assert calls[2].name == "requests.get"
    assert calls[2].severity == "medium"
    assert "dynamic URL" in calls[2].reason

    # 4. post with dynamic URL
    assert calls[3].name == "requests.post"
    assert calls[3].severity == "medium"
    assert "dynamic URL" in calls[3].reason


def test_python_static_analyzer_context_with_import_aliases(tmp_path: Path) -> None:
    sample = tmp_path / "alias_context.py"
    sample.write_text(
        "\n".join(
            [
                "import subprocess as sp",
                "from requests import get as http_get",
                "from os import system as sys_exec",
                "cmd = 'dynamic'",
                "url = 'https://dynamic.com'",
                "sp.run(cmd, shell=True)",
                "sp.run(['echo', cmd], shell=False)",
                "http_get(url)",
                "sys_exec(cmd)",
            ]
        ),
        encoding="utf-8",
    )

    analysis = PythonStaticAnalyzer().analyze(PythonFileLoader().load(sample))
    calls = analysis.suspicious_calls
    assert len(calls) == 4

    # 1. sp.run with shell=True -> subprocess.run, high
    assert calls[0].name == "subprocess.run"
    assert calls[0].severity == "high"
    assert "executed with shell=True" in calls[0].reason

    # 2. sp.run with dynamic command, shell=False -> subprocess.run, medium
    assert calls[1].name == "subprocess.run"
    assert calls[1].severity == "medium"
    assert "dynamic arguments" in calls[1].reason
    assert "executed with shell=True" not in calls[1].reason

    # 3. http_get with dynamic url -> requests.get, medium
    assert calls[2].name == "requests.get"
    assert calls[2].severity == "medium"
    assert "dynamic URL" in calls[2].reason

    # 4. sys_exec with dynamic command -> os.system, high
    assert calls[3].name == "os.system"
    assert calls[3].severity == "high"
    assert "dynamic input" in calls[3].reason


def test_python_static_analyzer_treats_unproven_expressions_as_dynamic(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "dynamic_expressions.py"
    sample.write_text(
        "\n".join(
            [
                "import requests",
                "import subprocess",
                "flag = True",
                "primary = 'https://primary.example'",
                "fallback = 'https://fallback.example'",
                "args = ['echo', 'dynamic']",
                "requests.get(primary if flag else fallback)",
                "requests.post(primary or fallback)",
                "open('data.txt', 'w' if flag else 'r')",
                "open(primary if flag else fallback)",
                "subprocess.run([*args])",
            ]
        ),
        encoding="utf-8",
    )

    analysis = PythonStaticAnalyzer().analyze(PythonFileLoader().load(sample))
    calls = analysis.suspicious_calls
    assert len(calls) == 5

    assert calls[0].name == "requests.get"
    assert calls[0].severity == "medium"
    assert "dynamic URL" in calls[0].reason

    assert calls[1].name == "requests.post"
    assert calls[1].severity == "medium"
    assert "dynamic URL" in calls[1].reason

    assert calls[2].name == "open"
    assert calls[2].severity == "medium"
    assert "dynamic mode parameter" in calls[2].reason

    assert calls[3].name == "open"
    assert calls[3].severity == "medium"
    assert "dynamic file path" in calls[3].reason

    assert calls[4].name == "subprocess.run"
    assert calls[4].severity == "medium"
    assert "dynamic arguments" in calls[4].reason


def test_python_static_analyzer_combines_open_path_and_mode_context(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "combined_open_context.py"
    sample.write_text(
        "\n".join(
            [
                "target = 'user_file.txt'",
                "mode = 'w'",
                "open(target, 'w')",
                "open(target, mode)",
            ]
        ),
        encoding="utf-8",
    )

    analysis = PythonStaticAnalyzer().analyze(PythonFileLoader().load(sample))
    calls = analysis.suspicious_calls
    assert len(calls) == 2

    assert calls[0].severity == "medium"
    assert "dynamic file path" in calls[0].reason
    assert "write/modify permissions" in calls[0].reason

    assert calls[1].severity == "medium"
    assert "dynamic file path" in calls[1].reason
    assert "dynamic mode parameter" in calls[1].reason
