# Project NuriLab

Local-first Python static analysis and LLM-assisted security review.

Project NuriLab accepts one Python file or a Python project directory, extracts
deterministic static signals, optionally asks a locally served LLM to interpret
those signals, and writes HTML and JSON reports.

The project is currently in **Phase 3 stabilization**. Phase 3 implementation
work covers Local LLM review quality, real-project input stability, large source
files, project-level aggregation, report readability, and Local LLM failure
handling. Live work status is tracked in the Linear project `Nurilab`.

## What It Does

```text
Python file or project directory
-> input collection and UTF-8 loading
-> AST, suspicious-call, secret, and optional Ruff analysis
-> deterministic Mock review or optional Local LLM review
-> project aggregation
-> HTML and JSON reports
```

Current capabilities:

- Analyze one `.py` file or recursively collect `.py` files from a directory.
- Exclude `.git`, `.venv`, caches, build output, and report directories.
- Analyze Python files without a line-count limit.
- Extract imports, functions, classes, syntax errors, suspicious calls, and
  potential hard-coded secrets.
- Collect Ruff findings when Ruff integration is enabled.
- Produce deterministic offline reviews with `MockReviewClient`.
- Call a running vLLM OpenAI-compatible API with `LocalLLMReviewClient`.
- Preserve static analysis and report generation when Local LLM requests fail.
- Write HTML and JSON by default, with optional Markdown output.

Project NuriLab does not currently:

- determine conclusively whether code is malware;
- execute submitted code or real malware samples;
- perform dynamic analysis;
- support languages other than Python;
- start or manage an LLM server;
- generate patched source files or remediation snippets;
- run fine-tuning jobs in this repository.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

The repository pins the project interpreter through `.python-version`. Use
`uv run python`, not the operating system's unqualified `python3`, because the
system interpreter may be a different version.

Set up the environment from the lock file:

```bash
uv sync --locked
```

## Quick Start

Analyze one file:

```bash
uv run python main.py analyze tests/fixtures/vulnerable_sample.py
```

Analyze a project directory:

```bash
uv run python main.py analyze tests
```

Disable Ruff collection:

```bash
uv run python main.py analyze tests --no-ruff
```

Request Markdown in addition to HTML and JSON:

```bash
uv run python main.py analyze tests --format html json md
```

Choose an output directory:

```bash
uv run python main.py analyze tests --out /tmp/nurilab-reports
```

Default output:

```text
reports/
├── <target>.analysis.html
└── <target>.analysis.json
```

The `reports/` directory is a local artifact directory and must not be
committed.

## CLI Contract

```text
project-nurilab analyze <path> [options]
```

| Option | Behavior |
| --- | --- |
| `<path>` | A `.py` file or project directory |
| `--out <dir>` | Report output directory; default `reports` |
| `--format <formats...>` | Any of `html`, `json`, `md`; default `html json` |
| `--review-client mock\|local` | Review backend; default `mock` |
| `--no-ruff` | Disable Ruff JSON collection |
| `--max-lines <n>` | Deprecated no-op retained for CLI compatibility |

An invalid path raises an input error. A non-Python file is represented as a
skipped input. Python files that cannot be decoded as UTF-8 or read from disk
are preserved as skipped analysis results instead of terminating project
analysis.

## Architecture

```text
project_nurilab/
├── input/
│   ├── collector.py        # file/directory collection and exclusions
│   └── manager.py          # UTF-8 Python file loading
├── analyzers/
│   ├── python_static.py    # AST signal extraction
│   ├── patterns.py         # suspicious call rules
│   ├── secrets.py          # potential hard-coded secret checks
│   └── tools.py            # Ruff JSON integration
├── aggregation/
│   └── result_aggregator.py
├── llm/
│   └── review.py           # Mock and Local LLM review clients
├── reports/
│   └── generator.py        # HTML, JSON, and Markdown rendering
├── schemas.py              # shared data contracts
├── pipeline.py             # orchestration
├── cli.py
└── config.py
```

The deterministic analyzers are the evidence source. Review clients convert
that evidence into summaries, priorities, and recommendations. LLM output does
not override or remove deterministic analysis results.

## Analysis And Review Contracts

Single-file analysis is serialized as `PythonAnalysis`:

```text
path, line_count, language, skipped, skip_reason, syntax_error,
imports, functions, classes, suspicious_calls, secrets, ruff_findings
```

Project analysis is serialized as `ProjectAnalysis`:

```text
root_path, file_results, ruff_findings, summary
```

The project summary contains:

```text
total_files, analyzed_files, skipped_files, severity_counts,
risk_level, file_summaries
```

Review output is serialized as `ReviewResult`:

```text
summary, risk_level, findings
```

Each review finding contains:

```text
title, severity, file, line, column, source, rule_id,
reason, recommendation
```

Static analysis models can represent `info`, `low`, `medium`, `high`,
`critical`, and `unknown`. The current Local LLM prompt contract asks the model
to return `low`, `medium`, or `high`; unsupported Local LLM finding severities
are normalized to `unknown`.

`analysis.summary.risk_level` and `review.risk_level` have different
responsibilities. The former summarizes deterministic project signals. The
latter is the selected review client's result. If Local LLM review fails,
`review.risk_level` becomes `unknown`, while the deterministic analysis remains
available in the same report.

JSON is the canonical machine-readable artifact. HTML is the default
human-readable view. Markdown is optional.

## Local LLM

Mock review is the default and requires no LLM server:

```bash
uv run python main.py analyze tests --review-client mock
```

For Local LLM review, start vLLM separately. The application never starts,
stops, downloads, or supervises the model server.

Server process:

```bash
vllm serve Qwen/Qwen2.5-Coder-3B-Instruct
```

Analysis process:

```bash
uv run python main.py analyze tests --review-client local
```

Configuration:

| Environment variable | Default |
| --- | --- |
| `NURILAB_LLM_BASE_URL` | `http://localhost:8000/v1` |
| `NURILAB_LLM_MODEL` | `Qwen/Qwen2.5-Coder-3B-Instruct` |
| `NURILAB_LLM_TIMEOUT` | `120` seconds |

Example:

```bash
export NURILAB_LLM_BASE_URL=http://127.0.0.1:8000/v1
export NURILAB_LLM_MODEL=Qwen/Qwen2.5-Coder-3B-Instruct
export NURILAB_LLM_TIMEOUT=120
uv run python main.py analyze tests --review-client local
```

Only normalized static analysis data is sent to the Local LLM. Original source
text is not included in the current prompt payload.

These Local LLM failures become `source="local_llm"` report findings instead
of terminating the pipeline:

- connection, URL, and unexpected API response access failures;
- request timeouts;
- HTTP errors;
- review JSON parsing failures.

The current automated suite verifies these paths with mocks. It does not prove
that a specific GPU, model, vLLM version, or network deployment works. Record
real-server validation separately with the exact model, server version,
command, and result.

## Static Analysis Limits

The current analyzer is intentionally conservative:

- Suspicious calls are exact AST call-name matches. Import aliases and
  data-flow relationships are not resolved.
- Secret detection is line-oriented pattern matching, not semantic analysis.
- A suspicious call is a review signal, not proof of malicious intent.
- Ruff is an optional supporting signal and is not the security decision
  engine.
- Large files are analyzed without a line limit, but no source chunking or RAG
  path is implemented.
- Local LLM input contains normalized signals, not full code context.
- A syntactically valid non-object Local LLM JSON value currently normalizes to
  an empty low-risk review instead of a schema-error finding.

These limitations must be considered when interpreting risk levels and
findings.

## Validation

Every pull request must pass:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

The test suite must remain runnable without a Local LLM server.

## Work And Pull Request Workflow

Work is tracked in Linear:

1. Create or select an issue in team `The Debugging Water Deer`, project
   `Nurilab`.
2. Confirm scope, acceptance criteria, dependencies, and target files.
3. Move the issue to `In Progress`.
4. Create a branch from the latest `main`.
5. Implement and run the four required validation commands.
6. Open a GitHub pull request and move the Linear issue to `In Review`.
7. The Repository Owner reviews and merges the pull request.
8. After merge confirmation, move the Linear issue to `Done`.

Do not mark an issue `Done` merely because a branch was pushed or a pull
request was opened.

See [AGENTS.md](AGENTS.md) for repository rules and
[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for the complete contributor
workflow.

## Documentation

The documentation map and authority rules are maintained in
[docs/README.md](docs/README.md).

Primary documents:

- [AGENTS.md](AGENTS.md): collaboration and agent behavior rules.
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md): contributor workflow.
- [docs/external_project_validation.md](docs/external_project_validation.md):
  external-project validation procedure and historical results.
- [docs/FINETUNING_EXPERIMENT_PLAN.md](docs/FINETUNING_EXPERIMENT_PLAN.md):
  boundary and handoff notes for the separate fine-tuning project.

## Phase Boundary

The following work is outside the current Phase 3 product scope and requires a
separate Linear issue and explicit Owner approval:

- fine-tuning;
- RAG-based security knowledge retrieval;
- remediation snippets or full patched code;
- non-Python languages;
- multimodal input;
- executable malware formats;
- real malware execution or dynamic analysis.

Fine-tuning code, datasets, adapters, checkpoints, and experiment logs belong
in a separate project. This repository only keeps the integration boundary and
high-level handoff plan.

## Security

Never commit:

- real malware samples or executable payloads;
- API keys, credentials, or private CTI;
- private customer or internal source code without approval;
- downloaded external projects;
- generated reports;
- raw datasets, model weights, adapters, or checkpoints.

Real malware handling requires a separately approved isolated environment,
storage policy, network policy, and access-control procedure.
