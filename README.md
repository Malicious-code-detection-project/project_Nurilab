# Local-based LLM Static Code Review and Future Malware Analysis

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/Package%20Manager-uv-654FF0)
![Status](https://img.shields.io/badge/Status-Phase%202%20Prototype-orange)
![Runtime](https://img.shields.io/badge/Runtime-Local%20First-2E7D32)
![LLM Serving](https://img.shields.io/badge/Serving-vLLM%20%7C%20SGLang-0A66C2)

외부 LLM API 기반 코드 리뷰와 보안 분석은 분석 단계가 고도화될수록 토큰 사용량과 호출 비용이 빠르게 증가합니다. 이 프로젝트는 반복적인 코드 리뷰/보안 분석 워크로드를 로컬 환경에서 처리하기 위한 프로토타입입니다.

이 프로젝트의 **최종 목표**는 폐쇄망 로컬 환경에서 동작하는 **LLM 기반 악성코드/의심 파일 분석 자동화 시스템**입니다. 다만 현재는 악성코드 학습 데이터와 검증 데이터가 충분하지 않기 때문에, **Phase 2: Python 프로젝트 단위 정적 분석 자동화**를 먼저 개발하고 있습니다.

현재 프로토타입은 단일 `.py` 파일 또는 Python 프로젝트 디렉터리를 입력받아 AST 분석, secret 탐지, 선택적 Ruff 결과 수집, Mock/Local LLM 리뷰, HTML/JSON 보고서를 생성합니다.

## 1. Reference Architecture

이 프로젝트는 [A2A-MCP / Code_Vulnerability](https://github.com/jeongminllee/A2A-MCP-/tree/main/Code_Vulnerability)의 역할 분리를 벤치마크합니다.

참고 프로젝트는 MCP/gRPC 기반 agent server를 사용하지만, 이 프로젝트는 초기 개발 속도를 위해 단일 프로세스 내부 모듈로 단순화합니다.

| Reference Project | This Project |
| --- | --- |
| Quick Agent | `analyzers/patterns.py` |
| Secrets Agent | `analyzers/secrets.py` |
| Static Agent | `analyzers/python_static.py`, `analyzers/tools.py` |
| Summary Agent | `reports/generator.py` |
| Remediation Agent | `pipeline.py` |
| MCP/gRPC | 현재 제외 |

## 2. Current Scope

현재 단계와 장기 방향을 다음처럼 구분합니다.

- 현재 개발 목표: Python 코드 리뷰 및 프로젝트 단위 정적 분석 자동화
- 최종 목표: 악성코드/의심 파일 분석 자동화

지원 범위:

- 단일 `.py` 파일 분석
- Python 프로젝트 디렉터리 재귀 분석
- `.py` 파일 수집 및 제외 경로 필터링
- 200줄 초과 파일 skip
- AST 기반 import/function/class 추출
- 위험 호출 후보 탐지
- hard-coded secret 후보 탐지
- 선택적 Ruff JSON 결과 수집
- Mock Review Client 또는 vLLM 기반 Local LLM Review Client
- HTML/JSON 기본 보고서 생성
- Markdown 선택 출력

제외 범위:

- 악성코드 샘플 분석
- PE/ELF/문서형 파일 분석
- 동적 분석 sandbox
- 모델 파인튜닝
- MCP/gRPC agent server
- 웹 대시보드
- 자동 코드 수정

## 3. Pipeline

```text
Python File / Project Directory
-> Input Collector
-> Python File Loader
-> Python Static Analyzer
-> Ruff Tool Collector
-> Result Aggregator
-> Mock or Local LLM Review Client
-> Report Generator
-> HTML / JSON Report
```

```text
                  ┌─────────────────────────────┐
                  │ User / CLI                   │
                  │ analyze <file_or_directory>  │
                  └──────────────┬──────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────┐
│ Input Collector                                        │
│ - 단일 파일 또는 디렉터리 입력                         │
│ - Python 파일 재귀 탐색                                │
│ - .git/.venv/__pycache__/reports 제외                  │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Python Static Analyzer                                 │
│ - AST parse                                            │
│ - import/function/class 추출                           │
│ - 위험 호출 후보 탐지                                  │
│ - hard-coded secret 후보 탐지                          │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Ruff Tool Collector                                    │
│ - uv run ruff check <target> --output-format json      │
│ - Ruff finding을 분석 결과로 정규화                    │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Review Client                                          │
│ - MockReviewClient: 오프라인/테스트용                  │
│ - LocalLLMReviewClient: vLLM OpenAI-compatible API     │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Report Generator                                       │
│ - HTML 작업자용 보고서                                 │
│ - JSON 에이전트/자동화용 결과                          │
│ - Markdown 선택 출력                                   │
└────────────────────────────────────────────────────────┘
```

## 4. Implementation Structure

```text
project_nurilab/
├── aggregation/
│   └── result_aggregator.py
├── analyzers/
│   ├── patterns.py
│   ├── python_static.py
│   ├── secrets.py
│   └── tools.py
├── input/
│   ├── collector.py
│   └── manager.py
├── llm/
│   └── review.py
├── reports/
│   └── generator.py
├── cli.py
├── config.py
├── pipeline.py
└── schemas.py
```

## 5. Quick Start

의존성 설치:

```bash
uv sync
```

단일 파일 분석:

```bash
uv run python main.py analyze tests/fixtures/vulnerable_sample.py
```

프로젝트/디렉터리 분석:

```bash
uv run python main.py analyze tests
```

기본 생성 결과:

```text
reports/
├── <target>.analysis.html
└── <target>.analysis.json
```

Markdown까지 출력:

```bash
uv run python main.py analyze tests --format md html json
```

Ruff 수집 비활성화:

```bash
uv run python main.py analyze tests --no-ruff
```

## 6. Air-Gapped Deployment Note

이 프로젝트는 폐쇄망 또는 컨테이너 기반 배포를 염두에 두고 설계합니다.

- 핵심 분석 경로는 외부 네트워크 없이 동작해야 합니다.
- `ruff`는 선택적 외부 도구입니다.
- 컨테이너 이미지나 내부 패키지 저장소에 `ruff`가 포함된 경우에만 활성화하는 구성이 현실적입니다.
- `ruff`를 포함하지 않는 환경에서는 `--no-ruff`로 내부 AST 분석 경로만 사용하면 됩니다.

## 7. Local LLM Serving

기본값은 서버 없이 동작하는 `MockReviewClient`입니다. 실제 LLM 리뷰가 필요할 때만 로컬 서빙 LLM을 붙입니다.

현재 구현은 vLLM의 OpenAI-compatible API를 기준으로 연결되어 있습니다.

vLLM 기반 Local LLM 리뷰:

```bash
vllm serve Qwen/Qwen2.5-Coder-3B-Instruct
uv run python main.py analyze tests --review-client local
```

환경변수로 LLM 연결 설정을 바꿀 수 있습니다.

```bash
export NURILAB_LLM_BASE_URL=http://localhost:8000/v1
export NURILAB_LLM_MODEL=Qwen/Qwen2.5-Coder-3B-Instruct
export NURILAB_LLM_TIMEOUT=120
```

SGLang도 비교 대상이지만, 현재 코드 경로는 vLLM 호환 API를 우선 기준으로 두고 있습니다. 두 프레임워크 모두 멀티 GPU 구성을 지원하므로, 이후 처리량과 운영 복잡도를 비교해 선택 범위를 좁힙니다.

테스트와 린트:

```bash
uv run pytest
uv run ruff check .
```

## 8. Output Model

기본 보고서는 `HTML + JSON`입니다. JSON은 기계/에이전트용 canonical output이고, HTML은 작업자용 보고서입니다.

파일 단위 결과:

```text
PythonAnalysis
- path
- line_count
- skipped / skip_reason
- syntax_error
- imports
- functions
- classes
- suspicious_calls
- secrets
- ruff_findings
```

프로젝트 단위 결과:

```text
ProjectAnalysis
- root_path
- file_results[]
- ruff_findings[]
- summary
  - total_files
  - analyzed_files
  - skipped_files
  - severity_counts
  - risk_level
```

리뷰 결과:

```text
ReviewResult
- summary
- risk_level
- findings[]
  - title
  - severity
  - file
  - line
  - column
  - source
  - rule_id
  - reason
  - recommendation
```

## 9. Why the LLM Server Runs Separately

이 프로젝트는 vLLM 서버를 애플리케이션 내부에서 자동 실행하지 않습니다. vLLM은 별도 터미널 또는 별도 GPU 서버에서 먼저 실행하고, 분석 애플리케이션은 이미 떠 있는 vLLM API에 HTTP 요청만 보냅니다.

```text
Terminal or GPU Server
-> vllm serve Qwen/Qwen2.5-Coder-3B-Instruct
-> http://localhost:8000/v1

Analysis App
-> uv run python main.py analyze <target> --review-client local
-> POST /v1/chat/completions
-> HTML/JSON report
```

이 구조를 선택한 이유는 다음과 같습니다.

- **역할 분리**: vLLM은 모델 로딩, GPU 메모리, batching, 병렬 추론을 담당하고, 분석 앱은 코드 수집, 정적 분석, 보고서 생성을 담당합니다.
- **반복 분석 효율**: 모델은 한 번 로딩해 서버에 올려두고, 여러 코드 분석 작업이 같은 vLLM 서버를 재사용할 수 있습니다.
- **디버깅 용이성**: vLLM 로그와 분석 앱 로그를 분리해서 볼 수 있어 모델 로딩 문제, GPU 문제, API 문제, 분석 로직 문제를 구분하기 쉽습니다.
- **운영 확장성**: MacBook에서 분석 앱을 실행하고, 8 GPU 서버에서 vLLM을 실행하는 구조로 자연스럽게 확장할 수 있습니다.
- **프로세스 안정성**: 앱이 vLLM 서버 시작/종료까지 책임지면 포트 충돌, 모델 다운로드, GPU 메모리 부족, 장시간 실행 프로세스 관리가 복잡해집니다.

따라서 현재 구조는 다음 원칙을 따릅니다.

```text
분석 앱은 vLLM 서버를 실행하지 않는다.
분석 앱은 실행 중인 vLLM 서버에 요청만 보낸다.
LLM 서버가 없어도 기본 MockReviewClient로 분석은 가능해야 한다.
```

LLM 응답은 JSON으로 파싱하며, 파싱 실패나 서버 오류는 pipeline 실패가 아니라 보고서 finding으로 남깁니다.

## 10. Roadmap

- Phase 1: 단일 `.py` 파일 기반 코드 리뷰 MVP
- Phase 2: Python 프로젝트 단위 정적 분석 자동화
- Phase 3: Local LLM 리뷰 품질 개선 및 vLLM/SGLang 병렬 처리 실험
- Phase 4: RAG 기반 보안 기준 문서/룰 검색 연동
- Phase 5: 악성코드 데이터 확보 후 보안 특화 학습/파인튜닝 검토

## 11. Security Notice

이 저장소에는 실제 악성코드 샘플이나 민감한 내부 데이터를 커밋하지 않습니다. `data/samples/`에는 교육과 테스트를 위한 무해한 샘플만 둡니다.

향후 실제 악성 파일을 다루는 단계에서는 격리된 분석 환경, 네트워크 통제, 샘플 저장 정책, 접근 권한 관리가 선행되어야 합니다.

## 12. Related Documents

- [SGLANG_VLLM_COMPARISON.md](./SGLANG_VLLM_COMPARISON.md): SGLang과 vLLM 비교 분석 리포트
