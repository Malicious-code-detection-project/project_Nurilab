# Documentation Map

This directory contains current operating documentation, validation records,
reference material, and historical plans for Project NuriLab.

## Authority

Use the authority that matches the question:

1. Source code and tests are the executable truth for current behavior and data
   contracts.
2. `README.md` is the public contract for supported scope and execution.
3. `AGENTS.md` defines repository collaboration rules and quality gates.
4. `docs/CONTRIBUTING.md` defines the contributor workflow.
5. Linear project `Nurilab` is the authority for live work status.
6. GitHub pull requests are the authority for review and merge history.

Historical plans and reference reports do not override current product or
collaboration documents.

## Current Operating Documents

| Document | Purpose |
| --- | --- |
| [`../README.md`](../README.md) | Product scope, architecture, CLI, Local LLM behavior, limits |
| [`../AGENTS.md`](../AGENTS.md) | Repository-wide rules for people and coding agents |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Linear issue, branch, validation, PR, and completion workflow |
| [`PR_DESCRIPTION.md`](PR_DESCRIPTION.md) | Detailed PR body template |
| [`../.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) | GitHub's default PR form |
| [`../.github/ISSUE_TEMPLATE/task.md`](../.github/ISSUE_TEMPLATE/task.md) | Legacy GitHub issue form; Linear is the current work tracker |

## Validation And Integration Records

| Document | Status |
| --- | --- |
| [`external_project_validation.md`](external_project_validation.md) | Procedure plus historical results; rerun against current `main` before treating results as current evidence |
| [`SGLANG_VLLM_COMPARISON.md`](SGLANG_VLLM_COMPARISON.md) | Reference comparison, not a current benchmark or dependency contract |
| [`FINETUNING_EXPERIMENT_PLAN.md`](FINETUNING_EXPERIMENT_PLAN.md) | Handoff plan for a separate fine-tuning project; no fine-tuning implementation belongs here |

## Historical And Superseded Documents

| Document | Status |
| --- | --- |
| [`PLAN.md`](PLAN.md) | Historical Phase 2 plan; some assumptions intentionally differ from current behavior |
| [`AI_RULES.md`](AI_RULES.md) | Legacy English AI guidance, superseded by `AGENTS.md` |
| [`AI_RULES_KOR.md`](AI_RULES_KOR.md) | Legacy Korean AI guidance, superseded by `AGENTS.md` |

Historical documents are retained to preserve project decisions. Update them
only to correct provenance, status labels, broken links, or dangerous
instructions. Current behavior belongs in `README.md`, `AGENTS.md`, tests, and
source code.

## Documentation Change Rules

- Update `README.md` when supported behavior, CLI options, environment
  variables, output, or user-visible limitations change.
- Update `AGENTS.md` when collaboration policy or required validation changes.
- Update `CONTRIBUTING.md` when the team workflow changes.
- Record live progress in Linear rather than copying issue status into Markdown.
- Include the implementation commit, environment, and date for empirical
  validation results.
- Mark old results as historical when later code changes invalidate the
  assumptions under which they were collected.
- Do not duplicate the same normative rule across multiple documents unless
  one document clearly links to the authority.
