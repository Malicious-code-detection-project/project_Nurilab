# Contributing Guide

This guide explains how team members resume work, claim a Linear issue, make a
focused change, validate it, and submit a GitHub pull request.

Repository policy is defined in [`../AGENTS.md`](../AGENTS.md). Product
behavior and commands are defined in [`../README.md`](../README.md). The full
documentation map is in [`README.md`](README.md).

## Work Tracking

Project NuriLab uses two systems with different responsibilities:

| System | Responsibility |
| --- | --- |
| Linear team `The Debugging Water Deer`, project `Nurilab` | Work scope, priority, assignee, dependencies, and status |
| GitHub Pull Request | Code/document review, validation evidence, and merge history |

Do not use a branch name, commit, or local note as the only record of active
work. Create or select the Linear issue first.

The team workflow states are:

```text
Backlog
-> Todo
-> In Progress
-> In Review
-> Done
```

Use `Canceled` when work is intentionally stopped. Use `Duplicate` only when
another issue already represents the same work.

`Done` means the Owner has merged the pull request, or the issue contains
explicit evidence that no repository change was required. A pushed branch or
open pull request is not complete.

## Resume Work

When opening the repository on a new machine or after a long break:

1. Read [`../README.md`](../README.md).
2. Read [`../AGENTS.md`](../AGENTS.md).
3. Check the Linear `Nurilab` project for live issue status.
4. Synchronize the local checkout.
5. Restore the locked Python environment.
6. Run the baseline quality gates before changing files.

```bash
git fetch origin --prune
git switch main
git pull --ff-only origin main
git status
uv sync --locked
```

Use the project interpreter:

```bash
uv run python --version
```

Do not rely on the operating system's `python3`; it may not be Python 3.12.

Baseline validation:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

If the baseline is already failing, record that fact in the Linear issue before
making unrelated changes.

## Start An Issue

Before implementation:

1. Confirm the issue belongs to team `The Debugging Water Deer` and project
   `Nurilab`.
2. Read its goal, acceptance criteria, target files, dependencies, and excluded
   scope.
3. Check that no one else owns an overlapping `In Progress` issue or branch.
4. Assign the issue to yourself.
5. Move it to `In Progress`.
6. Create a branch from the latest `main`.

Recommended issue content:

```markdown
## Goal

## Background

## Scope

## Out of Scope

## Target Files

## Acceptance Criteria

## Validation
```

Branch names:

| Change | Pattern | Example |
| --- | --- | --- |
| Feature | `feat/phase3-<topic>` | `feat/phase3-project-summary` |
| Bug fix | `fix/phase3-<topic>` | `fix/phase3-local-llm-timeout` |
| Test | `test/phase3-<topic>` | `test/phase3-large-input` |
| Refactor | `refactor/phase3-<topic>` | `refactor/phase3-report-ordering` |
| Documentation | `docs/phase3-<topic>` | `docs/phase3-documentation-alignment` |
| Experiment | `experiment/<topic>` | `experiment/gpt-oss-review` |

Include the Linear identifier when it helps ownership:

```text
docs/phase3-the-76-documentation-alignment
```

Never commit directly to `main`.

## Implement The Change

Keep one issue and one pull request focused on one objective.

Before editing:

- identify schema, CLI, report, prompt, and documentation impact;
- inspect the existing ownership boundary in `project_nurilab/`;
- identify the smallest relevant tests;
- confirm that the requested behavior remains in Phase 3.

Repository responsibilities:

| Path | Responsibility |
| --- | --- |
| `project_nurilab/input/` | Input collection, filtering, and loading |
| `project_nurilab/analyzers/` | Deterministic AST, pattern, secret, and tool signals |
| `project_nurilab/aggregation/` | Project-level counts and risk summaries |
| `project_nurilab/llm/` | Mock and Local LLM review clients |
| `project_nurilab/reports/` | HTML, JSON, and optional Markdown reports |
| `project_nurilab/schemas.py` | Shared analysis, review, and report contracts |
| `tests/` | Regression tests and benign fixtures |

Do not introduce a new module when the responsibility already belongs to an
existing module. Do not combine unrelated cleanup with the selected issue.

## Local LLM Changes

Mock review is the mandatory offline regression path. It must work without a
running model server.

Local LLM review:

- runs only with `--review-client local`;
- calls an already running vLLM OpenAI-compatible API;
- receives normalized static analysis rather than original source text;
- never starts or manages vLLM from the application;
- preserves static analysis and reports when the request fails.

Failure findings currently distinguish:

- `Local LLM connection failed`;
- `Local LLM request timed out`;
- `Local LLM HTTP error`;
- `Local LLM JSON parsing failed`.

Local LLM work normally affects one or more of:

```text
tests/test_tools_and_llm.py
tests/test_pipeline.py
tests/test_review_and_report.py
```

An actual vLLM smoke test is useful operational evidence, but it is not a
replacement for mock-based regression tests. Record the model, vLLM version,
GPU, command, environment variables, and result when reporting a real-server
test.

## External Project Validation

Follow
[`external_project_validation.md`](external_project_validation.md). Clone
external projects outside this repository and write reports outside the
repository.

The existing `pypa/packaging` result is historical and predates removal of the
Python line-count limit. Do not present it as current-main evidence without a
rerun.

Never commit:

- an external project's source tree;
- its `.git`, virtual environment, or dependency cache;
- generated HTML or JSON reports;
- private source code or real malware.

## Documentation Changes

Use [`README.md`](README.md) to determine the authority and status of each
document.

- Update `../README.md` for current behavior, commands, environment variables,
  outputs, and limitations.
- Update `../AGENTS.md` for repository policy.
- Update this guide for team workflow.
- Store live issue status in Linear, not in Markdown.
- Mark empirical results with the Project NuriLab commit, target commit,
  environment, command, and date.
- Mark historical plans and stale results explicitly instead of silently
  rewriting project history.
- Verify relative Markdown links after moving or renaming documents.

## Validation

Run all four commands before every pull request, including documentation-only
pull requests:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

Area-specific tests:

| Change | Primary test |
| --- | --- |
| Input collection/loading | `tests/test_input_collector.py` |
| Python AST analysis | `tests/test_python_static_analyzer.py` |
| Pipeline orchestration | `tests/test_pipeline.py` |
| Reports and JSON contract | `tests/test_review_and_report.py` |
| Local LLM and Ruff integration | `tests/test_tools_and_llm.py` |

Also run:

```bash
git diff --check
```

Do not run `ruff format .` or `ruff check --fix .` across the repository merely
to satisfy an unrelated issue. Automatic modifications must remain within the
issue's target files.

## Commit And Pull Request

Use a Conventional Commit message:

```text
<type>: <summary>
```

Examples:

```text
docs: align project documentation with current behavior
fix: preserve reports on local llm timeout
test: cover project json report contract
```

Push the issue branch and open a GitHub pull request.

PR title:

```text
[Phase 3] <summary>
```

Write the body from [`PR_DESCRIPTION.md`](PR_DESCRIPTION.md). It must include:

- the Linear issue (`Closes THE-XX`);
- purpose and implementation scope;
- intentionally excluded work;
- API/schema/CLI/report/prompt contract impact;
- acceptance-criteria evidence;
- all validation commands and results;
- unexecuted environment-dependent checks;
- follow-up work.

After opening the PR:

1. Move the Linear issue to `In Review`.
2. Add the PR link or branch/commit evidence to the issue.
3. Wait for the Repository Owner to review and merge.
4. After merge, synchronize `main` and verify the merge commit.
5. Move the Linear issue to `Done`.

The working branch may be deleted only after the merge is confirmed and no
follow-up commit is needed.

## Security And Artifacts

Do not commit:

- real malware samples or executable payloads;
- secrets, API keys, credentials, or private CTI;
- generated `reports/`;
- external project source trees;
- raw datasets;
- model weights, adapters, or checkpoints;
- machine-specific `.env` files.

Fine-tuning is a separate project. This repository keeps only the product-side
Local LLM integration boundary and the handoff plan.

## When Work Is Blocked

Do not expand scope to work around an unclear requirement.

Record the following in the Linear issue or PR:

- the exact blocker;
- evidence and reproduction steps;
- contracts or files affected;
- attempted alternatives;
- the decision required from the Owner.

Keep the issue `In Progress` or use the team's agreed blocked representation.
Do not mark blocked or unmerged work `Done`.
