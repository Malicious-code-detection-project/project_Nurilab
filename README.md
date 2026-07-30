# Project NuriLab

로컬 환경에서 동작하는 Python 정적 분석 및 LLM 보조 보안 리뷰 도구입니다.

Project NuriLab은 단일 Python 파일 또는 Python 프로젝트 디렉터리를 입력받아
재현 가능한 정적 분석 신호를 추출하고, 선택적으로 로컬에서 서빙되는 LLM이 해당
신호를 해석하도록 요청한 뒤 HTML과 JSON 보고서를 생성합니다.

현재 프로젝트는 **Phase 3 종료 검증 단계**입니다. 주요 기능 구현은 완료됐으며,
기본 Local LLM 전환, 실제 vLLM 검증, 외부 프로젝트 재검증, 문서와 운영 기준선
확정을 진행하고 있습니다. 실제 작업 상태는 Linear의 `Nurilab` 프로젝트에서
관리합니다.

## 동작 개요

```text
Python 파일 또는 프로젝트 디렉터리
-> 입력 수집 및 UTF-8 로딩
-> AST, 위험 호출, secret, 선택적 Ruff 분석
-> deterministic Mock 리뷰 또는 선택적 Local LLM 리뷰
-> 프로젝트 단위 집계
-> HTML 및 JSON 보고서
```

현재 지원 기능:

- 단일 `.py` 파일 또는 디렉터리 내부 `.py` 파일 재귀 분석
- `.git`, `.venv`, cache, build 결과, report 디렉터리 제외
- 파일 줄 수 제한 없는 Python 소스 분석
- import, function, class, syntax error, 위험 호출, hard-coded secret 후보 추출
- Ruff 연동이 활성화된 경우 Ruff finding 수집
- `MockReviewClient`를 이용한 재현 가능한 오프라인 리뷰
- `LocalLLMReviewClient`를 이용한 vLLM OpenAI-compatible API 호출
- Local LLM 요청 실패 시에도 정적 분석 결과와 보고서 보존
- HTML과 JSON 기본 출력 및 선택적 Markdown 출력

현재 지원하지 않는 기능:

- 코드가 악성인지 여부에 대한 확정 판단
- 입력 코드 또는 실제 악성 샘플 실행
- 동적 분석
- Python 이외 언어
- LLM 서버 시작 및 관리
- 수정된 전체 코드 또는 remediation snippet 생성
- 이 저장소 내부에서의 파인튜닝 실행

## 요구 환경

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

저장소는 `.python-version`으로 프로젝트 Python 버전을 지정합니다. 운영체제의
`python3`는 다른 버전일 수 있으므로 `uv run python`을 사용합니다.

lock 파일 기준으로 환경을 구성합니다.

```bash
uv sync --locked
```

## 빠른 시작

단일 파일 분석:

```bash
uv run python main.py analyze tests/fixtures/vulnerable_sample.py
```

프로젝트 디렉터리 분석:

```bash
uv run python main.py analyze tests
```

Ruff 수집 비활성화:

```bash
uv run python main.py analyze tests --no-ruff
```

HTML과 JSON에 Markdown까지 추가:

```bash
uv run python main.py analyze tests --format html json md
```

출력 디렉터리 지정:

```bash
uv run python main.py analyze tests --out /tmp/nurilab-reports
```

기본 출력:

```text
reports/
├── <target>.analysis.html
└── <target>.analysis.json
```

`reports/`는 로컬 산출물 디렉터리이며 저장소에 커밋하지 않습니다.

## CLI 계약

```text
project-nurilab analyze <path> [options]
```

| 옵션 | 동작 |
| --- | --- |
| `<path>` | `.py` 파일 또는 프로젝트 디렉터리 |
| `--out <dir>` | 보고서 출력 디렉터리, 기본값 `reports` |
| `--format <formats...>` | `html`, `json`, `md` 조합, 기본값 `html json` |
| `--review-client mock\|local` | 리뷰 backend, 기본값 `mock` |
| `--no-ruff` | Ruff JSON finding 수집 비활성화 |
| `--max-lines <n>` | CLI 호환성을 위해 남겨 둔 deprecated no-op |

존재하지 않는 경로는 입력 오류를 발생시킵니다. 단일 non-Python 파일은 skipped
입력으로 표현됩니다. UTF-8로 decode할 수 없거나 디스크에서 읽을 수 없는 Python
파일은 프로젝트 분석 전체를 중단하지 않고 skipped 분석 결과로 보존됩니다.

## 아키텍처

아래는 현재 모듈 구조의 요약입니다. 실행 단계, 데이터 계약, 단일 파일과 프로젝트
분기, 실패 처리와 향후 확장 지점은
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)에서 설명합니다.

```text
project_nurilab/
├── input/
│   ├── collector.py        # 파일/디렉터리 수집 및 제외 경로 처리
│   └── manager.py          # UTF-8 Python 파일 로딩
├── analyzers/
│   ├── python_static.py    # AST 신호 추출
│   ├── patterns.py         # 위험 호출 rule
│   ├── secrets.py          # hard-coded secret 후보 탐지
│   └── tools.py            # Ruff JSON 연동
├── aggregation/
│   └── result_aggregator.py
├── llm/
│   └── review.py           # Mock 및 Local LLM review client
├── reports/
│   └── generator.py        # HTML, JSON, Markdown 렌더링
├── schemas.py              # 공통 데이터 계약
├── pipeline.py             # 전체 흐름 조정
├── cli.py
└── config.py
```

Deterministic analyzer가 판단 근거가 되는 신호를 생성합니다. Review client는 해당
신호를 사람이 읽을 수 있는 요약, 우선순위, 권고안으로 변환합니다. LLM 출력은
정적 분석 결과를 덮어쓰거나 제거하지 않습니다.

## 분석 및 리뷰 계약

단일 파일 분석은 `PythonAnalysis`로 직렬화합니다.

```text
path, line_count, language, skipped, skip_reason, syntax_error,
imports, functions, classes, suspicious_calls, secrets, ruff_findings
```

프로젝트 분석은 `ProjectAnalysis`로 직렬화합니다.

```text
root_path, file_results, ruff_findings, summary
```

프로젝트 summary:

```text
total_files, analyzed_files, skipped_files, severity_counts,
risk_level, file_summaries
```

리뷰 출력은 `ReviewResult`로 직렬화합니다.

```text
summary, risk_level, findings
```

각 review finding:

```text
title, severity, file, line, column, source, rule_id,
reason, recommendation
```

정적 분석 모델은 `info`, `low`, `medium`, `high`, `critical`, `unknown`을
표현할 수 있습니다. 현재 Local LLM prompt 계약은 모델에 `low`, `medium`,
`high` 중 하나를 반환하도록 요구합니다. 허용되지 않은 Local LLM finding
severity는 `unknown`으로 정규화됩니다.

`analysis.summary.risk_level`과 `review.risk_level`은 역할이 다릅니다. 전자는
deterministic project signal의 최고 위험도를 요약하고, 후자는 선택한 review
client의 결과를 나타냅니다. Local LLM 리뷰가 실패하면 `review.risk_level`은
`unknown`이 되지만 같은 보고서의 deterministic analysis는 그대로 유지됩니다.

JSON은 canonical machine-readable artifact입니다. HTML은 기본 human-readable
view이고 Markdown은 선택 출력입니다.

## Local LLM

Mock 리뷰는 기본 경로이며 LLM 서버가 필요하지 않습니다.

```bash
uv run python main.py analyze tests --review-client mock
```

Local LLM 리뷰를 사용하려면 vLLM을 별도 프로세스로 먼저 실행합니다. 분석
애플리케이션은 모델 서버를 시작하거나 종료하거나 다운로드하거나 감시하지 않습니다.

서버 프로세스:

```bash
vllm serve openai/gpt-oss-20b
```

분석 프로세스:

```bash
uv run python main.py analyze tests --review-client local
```

연결 설정:

| 환경변수 | 기본값 |
| --- | --- |
| `NURILAB_LLM_BASE_URL` | `http://localhost:8000/v1` |
| `NURILAB_LLM_MODEL` | `openai/gpt-oss-20b` |
| `NURILAB_LLM_TIMEOUT` | `120`초 |

예시:

```bash
export NURILAB_LLM_BASE_URL=http://127.0.0.1:8000/v1
export NURILAB_LLM_MODEL=openai/gpt-oss-20b
export NURILAB_LLM_TIMEOUT=120
uv run python main.py analyze tests --review-client local
```

Local LLM에는 정규화된 정적 분석 데이터만 전달합니다. 현재 prompt payload에는
원본 source text가 포함되지 않습니다.

Local LLM request는 `reasoning_effort="low"`를 사용합니다. vLLM 버전별
호환성을 위해 provider-specific `include_reasoning` 필드는 보내지 않으며,
응답의 raw reasoning/Chain-of-Thought는 읽거나 보고서에 저장하지 않습니다.
최종 review는 vLLM의 strict JSON Schema로 `summary`, `risk_level`,
`findings` 구조를 강제하며, 기존 parser는 서버 또는 모델이 계약을 지키지 못한
경우를 report finding으로 변환하는 방어선으로 유지합니다.

다음 실패는 pipeline을 중단하지 않고 `source="local_llm"` report finding으로
남습니다.

- 연결, URL, 예상하지 못한 API response 접근 실패
- request timeout
- HTTP error
- review JSON decode 또는 strict schema validation failure

현재 자동화 테스트는 mock으로 이 경로를 검증합니다. 특정 GPU, 모델, vLLM 버전,
네트워크 배포가 실제로 동작한다는 의미는 아닙니다. 실제 서버 검증 결과에는 모델,
서버 버전, 명령어, 환경, 결과를 함께 기록해야 합니다.

실제 vLLM server를 대상으로 하는 선택형 통합 테스트는
[docs/LOCAL_LLM_INTEGRATION_TEST.md](docs/LOCAL_LLM_INTEGRATION_TEST.md)의 절차를
사용합니다. `NURILAB_RUN_LOCAL_LLM=1`을 명시하지 않은 기본 pytest에서는 해당
테스트를 skip합니다.

## 정적 분석의 한계

현재 analyzer는 의도적으로 보수적인 초기 구현입니다.

- 위험 호출은 정확한 AST call name으로 매칭합니다. import alias와 data flow는
  해석하지 않습니다.
- Secret 탐지는 semantic analysis가 아닌 line-oriented pattern matching입니다.
- 위험 호출 발견은 검토 신호이며 악성 의도의 증거가 아닙니다.
- Ruff는 선택적인 보조 신호이며 보안 판단 engine이 아닙니다.
- 파일 줄 수 제한은 없지만 source chunking과 RAG는 구현하지 않았습니다.
- Local LLM 입력에는 정규화된 신호만 포함되며 전체 코드 문맥은 포함되지 않습니다.

Risk level과 finding을 해석할 때 이 한계를 함께 고려해야 합니다.

## 검증

모든 Pull Request는 다음 명령을 통과해야 합니다.

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

테스트 suite는 Local LLM 서버 없이 실행할 수 있어야 합니다.

## 작업 및 Pull Request 흐름

작업은 Linear에서 관리합니다.

1. Linear 팀 `The Debugging Water Deer`, 프로젝트 `Nurilab`에서 이슈를
   생성하거나 선택합니다.
2. 작업 범위, 완료 조건, 의존성, 대상 파일을 확인합니다.
3. 이슈를 `In Progress`로 변경합니다.
4. 최신 `main`에서 작업 브랜치를 생성합니다.
5. 구현 후 네 가지 필수 검증 명령을 실행합니다.
6. GitHub Pull Request를 열고 Linear 이슈를 `In Review`로 변경합니다.
7. Repository Owner가 PR을 검토하고 병합합니다.
8. 병합을 확인한 뒤 Linear 이슈를 `Done`으로 변경합니다.

브랜치를 push하거나 PR을 열었다는 이유만으로 이슈를 `Done`으로 변경하지 않습니다.

저장소 규칙은 [AGENTS.md](AGENTS.md), 전체 기여 절차는
[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)를 확인합니다.

## 문서

문서 지도, 정본 우선순위, 언어 정책은
[docs/README.md](docs/README.md)에서 관리합니다.

주요 문서:

- [AGENTS.md](AGENTS.md): 협업 및 코딩 에이전트 행동 규칙
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md): 팀원 작업 절차
- [docs/external_project_validation.md](docs/external_project_validation.md):
  외부 프로젝트 검증 절차 및 과거 실행 결과
- [docs/FINETUNING_EXPERIMENT_PLAN.md](docs/FINETUNING_EXPERIMENT_PLAN.md):
  별도 파인튜닝 프로젝트로 전달할 범위와 계획

## Roadmap

작업 순서와 상세 범위는 [docs/PLAN.md](docs/PLAN.md), 실제 상태는 Linear
`Nurilab` 프로젝트를 기준으로 합니다.

| Phase | 목표 | 현재 상태 |
| --- | --- | --- |
| Phase 1 | 단일 Python 파일 분석 MVP | 완료 |
| Phase 2 | Python 프로젝트 단위 정적 분석 | 완료 |
| Phase 3 | Local LLM과 보고서 파이프라인 종료 검증 | 진행 중 |
| Phase 4 | Python 정적 분석 정확도와 대규모 입력 안정성 | 예정 |
| Phase 5 | 설치·배포·재현·운영 가능한 제품화 | 예정 |
| Phase 6 | AegisLM 모델 연동과 기준 모델 비교 | 예정 |
| Phase 7 | 오프라인 우선 보안 지식 RAG와 근거 추적 | 예정 |

Phase 3은 다음 조건을 모두 충족한 뒤 종료합니다.

- 기본 Local LLM을 `openai/gpt-oss-20b` 기준으로 전환
- strict JSON review 계약과 비정상 응답 처리 검증
- 선택형 실제 vLLM 통합 테스트 기록
- `packaging`, `click`, `requests` 외부 프로젝트 재검증
- 문서, Linear, 테스트 결과의 정합성 확인

파인튜닝 코드, 데이터셋, adapter, checkpoint, 실험 로그는 별도 AegisLM
프로젝트에서 관리합니다. Project NuriLab은 Phase 6에서 이미 서빙 중인 모델을
OpenAI-compatible API로 호출하고 비교·추적하는 제품 연동만 담당합니다.

다음 항목은 번호가 지정된 Phase에 포함하지 않고 연구 백로그로 유지합니다.

- remediation snippet 또는 전체 patched code
- Python 이외 언어
- 멀티모달 및 실행 파일 입력
- 실제 악성코드 실행 또는 동적 분석

## 보안

다음 항목은 커밋하지 않습니다.

- 실제 악성코드 샘플 또는 실행 가능한 payload
- API key, credential, private CTI
- 승인받지 않은 고객 또는 내부 source code
- 내려받은 외부 프로젝트
- 생성된 report
- raw dataset, model weight, adapter, checkpoint

실제 악성코드를 다루려면 별도로 승인된 격리 환경, 저장 정책, 네트워크 정책,
접근 권한 관리 절차가 선행되어야 합니다.
