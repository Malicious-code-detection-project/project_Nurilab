# Project NuriLab 기여 가이드

이 문서는 팀원이 작업을 재개하고, Linear 이슈를 선택하고, 범위가 명확한 변경을
구현하고, 검증한 뒤 GitHub Pull Request를 제출하는 절차를 설명합니다.

저장소 정책은 [`../AGENTS.md`](../AGENTS.md), 제품 동작과 실행 명령은
[`../README.md`](../README.md), 전체 문서 지도는
[`README.md`](README.md)를 기준으로 합니다.

## 작업 추적 체계

Project NuriLab은 Linear와 GitHub의 책임을 구분합니다.

| 시스템 | 책임 |
| --- | --- |
| Linear 팀 `The Debugging Water Deer`, 프로젝트 `Nurilab` | 작업 범위, 우선순위, 담당자, 의존성, 상태 |
| GitHub Pull Request | 코드/문서 리뷰, 검증 근거, 병합 이력 |

브랜치 이름, commit, 로컬 메모만으로 작업을 시작하지 않습니다. 먼저 Linear 이슈를
생성하거나 선택합니다.

팀 workflow 상태:

```text
Backlog
-> Todo
-> In Progress
-> In Review
-> Done
```

의도적으로 중단한 작업은 `Canceled`, 다른 이슈와 같은 작업은 `Duplicate`로
처리합니다.

`Done`은 Owner가 Pull Request를 병합했거나, 저장소 변경이 필요 없다는 근거가
이슈에 명시된 상태를 의미합니다. 브랜치를 push하거나 PR을 열었다는 사실만으로
완료 처리하지 않습니다.

## 오랜만에 작업을 재개할 때

새 PC에서 작업하거나 오랜만에 저장소를 열었다면 다음 순서를 따릅니다.

1. [`../README.md`](../README.md)를 읽습니다.
2. [`../AGENTS.md`](../AGENTS.md)를 읽습니다.
3. Linear `Nurilab` 프로젝트에서 현재 이슈 상태를 확인합니다.
4. 로컬 checkout을 최신 상태로 동기화합니다.
5. lock 파일 기준으로 Python 환경을 복구합니다.
6. 파일을 수정하기 전에 기본 품질 gate를 실행합니다.

```bash
git fetch origin --prune
git switch main
git pull --ff-only origin main
git status
uv sync --locked
```

프로젝트 interpreter를 확인합니다.

```bash
uv run python --version
```

운영체제의 `python3`는 Python 3.12가 아닐 수 있으므로 프로젝트 명령에 사용하지
않습니다.

기본 검증:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

작업 시작 전부터 검증이 실패하면 관련 없는 수정에 섞지 말고 Linear 이슈에
baseline failure를 기록합니다.

## 이슈 착수

구현 전:

1. 이슈가 팀 `The Debugging Water Deer`, 프로젝트 `Nurilab`에 속하는지
   확인합니다.
2. 목표, 완료 조건, 대상 파일, 의존성, 제외 범위를 읽습니다.
3. 겹치는 `In Progress` 이슈나 branch를 다른 팀원이 소유하고 있지 않은지
   확인합니다.
4. 자신을 담당자로 지정합니다.
5. 이슈를 `In Progress`로 변경합니다.
6. 최신 `main`에서 작업 branch를 생성합니다.

권장 이슈 본문:

```markdown
## 목표

## 배경

## 범위

## 제외 범위

## 대상 파일

## 완료 조건

## 검증
```

브랜치 이름:

| 변경 종류 | 형식 | 예시 |
| --- | --- | --- |
| 기능 | `feat/phase3-<topic>` | `feat/phase3-project-summary` |
| 버그 수정 | `fix/phase3-<topic>` | `fix/phase3-local-llm-timeout` |
| 테스트 | `test/phase3-<topic>` | `test/phase3-large-input` |
| 리팩터링 | `refactor/phase3-<topic>` | `refactor/phase3-report-ordering` |
| 문서 | `docs/phase3-<topic>` | `docs/phase3-documentation-alignment` |
| 실험 | `experiment/<topic>` | `experiment/gpt-oss-review` |

담당 작업을 명확히 할 필요가 있으면 Linear identifier를 포함합니다.

```text
docs/phase3-the-76-documentation-alignment
```

`main`에 직접 commit하거나 push하지 않습니다.

## 구현

하나의 이슈와 Pull Request에는 하나의 목적만 담습니다.

수정 전:

- schema, CLI, report, prompt, 문서 영향 확인
- `project_nurilab/`의 기존 책임 경계 확인
- 필요한 최소 test 범위 확인
- 현재 Phase 범위에 포함되는지 확인

모듈별 책임:

| 경로 | 책임 |
| --- | --- |
| `project_nurilab/input/` | 입력 수집, 필터링, 로딩 |
| `project_nurilab/analyzers/` | deterministic AST, pattern, secret, tool signal |
| `project_nurilab/aggregation/` | 프로젝트 단위 count 및 risk summary |
| `project_nurilab/llm/` | Mock 및 Local LLM review client |
| `project_nurilab/reports/` | HTML, JSON, 선택적 Markdown report |
| `project_nurilab/schemas.py` | 분석, 리뷰, 보고서 공통 계약 |
| `tests/` | 회귀 test 및 무해한 fixture |

기존 모듈이 이미 해당 책임을 가진다면 새 모듈을 만들지 않습니다. 선택한 이슈와
무관한 정리는 함께 수행하지 않습니다.

## Local LLM 변경

Mock review는 필수 offline regression 경로이며 실행 중인 모델 서버 없이 동작해야
합니다.

Local LLM review 원칙:

- `--review-client local`을 지정한 경우에만 실행합니다.
- 이미 실행 중인 vLLM OpenAI-compatible API를 호출합니다.
- 원본 source text가 아니라 정규화된 정적 분석 결과를 전달합니다.
- 애플리케이션에서 vLLM을 시작하거나 관리하지 않습니다.
- 요청 실패 시에도 정적 분석 결과와 report를 보존합니다.

현재 구분하는 실패 finding:

- `Local LLM connection failed`
- `Local LLM request timed out`
- `Local LLM HTTP error`
- `Local LLM JSON parsing failed`

Local LLM 작업은 일반적으로 다음 test 중 하나 이상에 영향을 줍니다.

```text
tests/test_tools_and_llm.py
tests/test_pipeline.py
tests/test_review_and_report.py
```

실제 vLLM smoke test는 유용한 운영 근거지만 mock 기반 regression test를 대체하지
않습니다. 실제 서버 결과를 기록할 때는 모델, vLLM 버전, GPU, 명령어, 환경변수,
결과를 함께 남깁니다.

## 외부 프로젝트 검증

[`external_project_validation.md`](external_project_validation.md)의 절차를
따릅니다. 외부 프로젝트와 생성 report는 이 저장소 밖에 둡니다.

기존 `pypa/packaging` 결과는 Python line-count limit 제거 전의 과거 기록입니다.
재실행하기 전에는 최신 `main`의 검증 근거로 제시하지 않습니다.

커밋 금지:

- 외부 프로젝트 source tree
- 외부 프로젝트의 `.git`, virtual environment, dependency cache
- 생성된 HTML 또는 JSON report
- private source code 또는 실제 악성코드

## 문서 변경

문서별 정본과 언어 정책은 [`README.md`](README.md)를 따릅니다.

- 현재 동작, command, 환경변수, 출력, 사용자에게 보이는 한계는
  `../README.md`에 기록합니다.
- 저장소 정책은 `../AGENTS.md`에 기록합니다.
- 팀 workflow는 이 문서에 기록합니다.
- 현재 운영 문서의 본문은 한국어로 작성하되 code identifier, CLI option,
  환경변수, JSON field, 공식 제품명은 영문을 유지합니다.
- live issue 상태는 Markdown이 아니라 Linear에 기록합니다.
- 실험 결과에는 Project NuriLab commit, 대상 commit, 환경, 명령어, 날짜를
  포함합니다.
- 과거 계획과 오래된 결과는 이력을 지우지 않고 현재 적용 여부를 표시합니다.
- 문서를 이동하거나 이름을 바꾸면 relative Markdown link를 검증합니다.
- 한글/영문 병행본은 같은 PR에서 함께 갱신합니다.

## 검증

문서 전용 PR을 포함한 모든 Pull Request에서 다음 네 명령을 실행합니다.

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

변경 영역별 기본 test:

| 변경 | 기본 test |
| --- | --- |
| 입력 수집 및 로딩 | `tests/test_input_collector.py` |
| Python AST 분석 | `tests/test_python_static_analyzer.py` |
| Pipeline orchestration | `tests/test_pipeline.py` |
| Report 및 JSON 계약 | `tests/test_review_and_report.py` |
| Local LLM 및 Ruff 연동 | `tests/test_tools_and_llm.py` |

추가 검사:

```bash
git diff --check
```

관련 없는 이슈를 처리하면서 `ruff format .` 또는 `ruff check --fix .`를 실행해
저장소 전체를 수정하지 않습니다. 자동 수정은 이슈의 대상 파일 범위 안에
한정합니다.

## Commit 및 Pull Request

Conventional Commit 형식:

```text
<type>: <summary>
```

예시:

```text
docs: 프로젝트 문서를 현재 동작에 맞게 정비
fix: local llm timeout에서도 보고서 보존
test: 프로젝트 json 보고서 계약 검증
```

이슈 branch를 push한 뒤 GitHub Pull Request를 생성합니다.

PR 제목:

```text
[Phase 3] <요약>
```

PR 본문은 [`PR_DESCRIPTION.md`](PR_DESCRIPTION.md)를 사용하며 다음 내용을
포함합니다.

- Linear 이슈 (`Closes THE-XX`)
- 목적과 구현 범위
- 의도적으로 제외한 작업
- API/schema/CLI/report/prompt 계약 영향
- 완료 조건 충족 근거
- 모든 검증 명령과 결과
- 실행하지 않은 환경 의존 검증
- 후속 작업

PR 생성 후:

1. Linear 이슈를 `In Review`로 변경합니다.
2. PR link 또는 branch/commit 근거를 이슈에 추가합니다.
3. Repository Owner의 리뷰와 병합을 기다립니다.
4. 병합 후 `main`을 동기화하고 merge commit을 확인합니다.
5. Linear 이슈를 `Done`으로 변경합니다.

병합을 확인하고 후속 commit이 필요 없을 때만 작업 branch를 삭제할 수 있습니다.

## 보안 및 산출물

커밋 금지:

- 실제 악성코드 sample 또는 실행 가능한 payload
- secret, API key, credential, private CTI
- 생성된 `reports/`
- 외부 프로젝트 source tree
- raw dataset
- model weight, adapter, checkpoint
- machine-specific `.env`

파인튜닝은 별도 프로젝트에서 수행합니다. 이 저장소에는 제품의 Local LLM 연동
경계와 전달 계획만 유지합니다.

## 작업이 막힌 경우

불명확한 요구사항을 우회하기 위해 범위를 임의로 확장하지 않습니다.

Linear 이슈 또는 PR에 다음을 기록합니다.

- 정확한 blocker
- 근거와 재현 절차
- 영향받는 계약 또는 파일
- 시도한 대안
- Owner에게 필요한 결정

이슈는 `In Progress`로 유지하거나 팀에서 합의한 blocked 표현을 사용합니다.
병합되지 않았거나 막힌 작업을 `Done`으로 변경하지 않습니다.
