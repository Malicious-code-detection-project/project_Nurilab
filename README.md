# Local LLM Malware and Suspicious File Analysis Automation

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/Package%20Manager-uv-654FF0)
![Status](https://img.shields.io/badge/Status-Phase%203%20Prototype-orange)
![Runtime](https://img.shields.io/badge/Runtime-Local%20First-2E7D32)
![LLM Serving](https://img.shields.io/badge/Serving-vLLM%20%7C%20SGLang-0A66C2)

이 프로젝트는 로컬 환경에서 동작하는 LLM 기반 악성코드/의심 파일 분석 자동화 시스템입니다.

현재 **Phase 3: Local LLM 리뷰 품질 개선 및 분석 대상 확장** 단계입니다.

현재 프로토타입은 단일 `.py` 파일 또는 Python 프로젝트 디렉터리를 입력받아 AST 분석, secret 탐지, Mock/Local LLM 리뷰, HTML/JSON 보고서를 생성합니다.

## 1. Current Scope

현재 지원 범위는 다음과 같습니다.

- 단일 `.py` 파일 분석
- Python 프로젝트 디렉터리 분석
- Mock / Local LLM 리뷰 지원
- HTML + JSON 보고서 출력

## 2. Current Development Goals

현재 Phase 3에서 집중하는 개발 목표는 다음과 같습니다.

- Local LLM 리뷰 품질 개선
- 외부 실제 Python 프로젝트 대상 분석 안정성 검증
- 파일 길이 제한 제거에 따른 대용량 소스 분석 흐름 정리
- 프로젝트 단위 결과 집계 및 보고서 가독성 개선
- 실제 운영 환경 기준의 로컬 LLM 연동 안정성 개선

외부 프로젝트 검증 후보와 로컬 clone/분석 절차는 [External Python Project Validation Targets](./docs/external_project_validation.md)에 정리합니다.

## 3. Pipeline

```text
Input
-> Loader
-> Static Analyzer
-> Review Client
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
│ Input                                                  │
│ - 단일 파일 또는 디렉터리 입력                         │
│ - Python 파일 재귀 탐색                                │
│ - .git/.venv/__pycache__/reports 제외                  │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Loader                                                 │
│ - 분석 대상 파일 수집 및 로드                          │
│ - UTF-8 기준 코드 읽기                                 │
│ - 외부 실제 프로젝트 폴더 입력 지원                    │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Static Analyzer                                        │
│ - AST parse                                            │
│ - import/function/class 추출                           │
│ - 위험 호출 후보 탐지                                  │
│ - hard-coded secret 후보 탐지                          │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Review Client                                          │
│ - MockReviewClient: 오프라인/테스트용                  │
│ - LocalLLMReviewClient: vLLM OpenAI-compatible API     │
│ - 프로젝트 단위 요약 및 리뷰 품질 개선 대상            │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Report Generator                                       │
│ - HTML 작업자용 보고서                                 │
│ - JSON 에이전트/자동화용 결과                          │
│ - 프로젝트 요약 가독성 개선 대상                       │
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

## 6. Local Environment Note

이 프로젝트는 로컬 환경에서 실행되는 분석 흐름을 기준으로 설계합니다.

- 핵심 분석 경로는 단일 파일과 프로젝트 디렉터리 입력을 모두 처리해야 합니다.
- Python AST 기반 정적 분석과 Local LLM 리뷰 경로를 함께 유지합니다.
- `ruff`는 현재 구현에 남아 있지만, 핵심 파이프라인 설명에서는 선택 도구로 취급합니다.

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

리뷰 경로는 다음 기준으로 선택합니다.

- `MockReviewClient`: 기본 경로입니다. 외부 서버 없이 deterministic analyzer 결과를 report finding으로 변환하므로 테스트와 PR 검증의 기준으로 사용합니다.
- `LocalLLMReviewClient`: `--review-client local`을 명시했을 때만 사용합니다. 이미 실행 중인 vLLM OpenAI-compatible API에 HTTP 요청을 보내 요약, 해석, 우선순위화, 권고안을 생성합니다.
- Local LLM 서버 오류, timeout, JSON 파싱 실패는 pipeline 실패가 아닙니다. 분석 결과와 HTML/JSON report는 유지하고, 실패 원인은 `source="local_llm"` report finding으로 남깁니다.

Local LLM 관련 변경을 검증할 때는 실제 vLLM 서버가 없어도 통과하는 mock 기반 테스트를 먼저 유지합니다.

```bash
uv run pytest tests/test_tools_and_llm.py tests/test_pipeline.py tests/test_review_and_report.py
```

SGLang도 비교 대상이지만, 현재 코드 경로는 vLLM 호환 API를 우선 기준으로 두고 있습니다. 두 프레임워크 모두 멀티 GPU 구성을 지원하므로, 이후 처리량과 운영 복잡도를 비교해 선택 범위를 좁힙니다.

테스트와 린트:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

## 8. Recommended Models

- `Qwen/Qwen2.5-Coder-3B-Instruct`: 기본 코드 리뷰 및 Python 정적 분석용
- `gpt-oss-20b`: reasoning 중심 대안 모델
- `Gemma 4 26B MoE`: 향후 멀티모달 분석 확장을 위한 후보 모델

## 9. Output

기본 보고서는 `HTML + JSON`입니다. JSON은 기계/에이전트용 canonical output이고, HTML은 작업자용 보고서입니다.

Phase 3에서는 출력 포맷 자체를 바꾸기보다, 실제 프로젝트 단위 분석에 맞춰 리뷰 품질과 프로젝트 요약 가독성을 개선하는 데 집중합니다.

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

## 10. Why the LLM Server Runs Separately

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

## 11. Prompt Contract (LLM의 역할 및 입출력 명세)
 
시스템과 LLM 간의 역할과 입출력 규격을 명확히 하기 위해 프롬프트 계약(Prompt Contract)을 정의하여 코드와 문서에 반영하고 있습니다.

### LLM의 역할 제한
- **최종 판단자가 아님**: LLM은 코드가 악성인지 아닌지를 최종적으로 판결하는 판사가 아닙니다. 악성 여부의 판단 기준은 Rule Engine과 정적 분석 결과에 있습니다.
- **정적 신호 해석자**: LLM은 정적 분석 파이프라인에서 추출된 객관적인 분석 결과를 입력받아 요약, 해석, 우선순위화, 권고안을 생성하는 보조적인 역할만 수행합니다.
- **CoT(Chain of Thought) 적용**: LLM은 발견된 정적 신호와 코드 컨텍스트를 분석하여, 단순히 정적 룰 설명을 출력하는 것이 아니라 맥락과 신호를 결합한 객관적인 해석을 생성합니다.

### 입출력 명세 (I/O Specification)
- **Input**: AST 파서, 패턴 탐지 등을 거친 정규화된 정적 분석 결과.
- **Output**: 반드시 다음 JSON 스키마 구조를 준수하여 응답해야 합니다.
  ```json
  {
    "summary": "전체 분석 결과 요약",
    "risk_level": "low|medium|high",
    "findings": [
      {
        "title": "발견 항목 제목",
        "severity": "low|medium|high",
        "file": "대상 파일 경로",
        "line": 42,
        "reason": "정적 신호와 컨텍스트를 종합한 객관적인 설명",
        "recommendation": "수정 및 완화 조치 권고안"
      }
    ]
  }
  ```

## 12. Roadmap

- Phase 1: 단일 `.py` 파일 기반 코드 리뷰 MVP
- Phase 2: Python 프로젝트 단위 정적 분석 자동화
- Phase 3: Local LLM 리뷰 품질 개선 및 분석 대상 확장
- Phase 4: RAG 기반 보안 기준 문서/룰 검색 연동
- Phase 5: 악성코드 데이터 확보 후 보안 특화 학습/파인튜닝 검토

## 13. Security Notice

이 저장소에는 실제 악성코드 샘플이나 민감한 내부 데이터를 커밋하지 않습니다. `data/samples/`에는 교육과 테스트를 위한 무해한 샘플만 둡니다.

향후 실제 악성 파일을 다루는 단계에서는 격리된 분석 환경, 네트워크 통제, 샘플 저장 정책, 접근 권한 관리가 선행되어야 합니다.

## 14. Reference

이 프로젝트는 `<A2A × MCP 멀티에이전트 오케스트레이션 실전>` 도서의 예제 프로젝트 중 하나인 `Code_Vulnerability` 구성을 참고했습니다.

다만 현재 구현은 MCP/gRPC 기반 멀티에이전트 구조를 직접 사용하지 않고, 단일 프로세스 기반 파이프라인으로 단순화해 확장하고 있습니다.

- [A2A-MCP / Code_Vulnerability](https://github.com/gilbutITbook/080493/tree/main/Code_Vulnerability)

## 15. Phase Next

- [SGLANG_VLLM_COMPARISON.md](./docs/SGLANG_VLLM_COMPARISON.md): SGLang과 vLLM 비교 분석 리포트
- 코드 수정 제안 및 remediation snippet 출력 방식 설계
- 파일 전체 patched code 생성 여부 검토
- 파인튜닝 전략 및 학습 데이터셋 구성 검토
- 멀티모달 입력 확장 방식 검토
- Python 외 언어 지원 여부 및 구조 일반화 검토
- 선택적 정적 분석 도구 확장 여부 검토

## 16. 중간 발표 때 들어온 질문들

### Q1. 새로운 악성코드가 생성되어 공격이 들어오면, 바로 파인튜닝할 것인가?

현재 방향은 **즉시 파인튜닝보다는 우선 축적, 이후 주기적 업데이트**입니다.

- 새 악성코드 샘플, IOC, 문자열, 행위 패턴, 분석 리포트 등은 먼저 벡터 DB 또는 지식 저장소에 축적
- 빠른 대응은 RAG, 룰, 검색 기반 참조로 처리
- 파인튜닝이나 모델 업데이트는 정제된 데이터셋을 기준으로 반기 또는 연 단위, 혹은 의미 있는 변화 시점에 수행

정리하면 다음과 같습니다.

- 실시간 반영: 벡터 DB, 룰, 지식베이스
- 주기 반영: 파인튜닝, 모델 업데이트, 재배포

### Q2. 현재는 Python AST 기반 정적 분석 중심인데, 프로젝트 이름처럼 악성코드 탐지 시스템으로 발전시키려면 PE/ELF/APK나 난독화 스크립트 분석 중 어느 방향을 우선 확장할 계획인가?

현재 방향은 **난독화 스크립트와 스크립트형 의심 코드 분석을 먼저 확장**하는 것입니다.

- 현재 구조가 Python 정적 분석 기반이기 때문에 확장 비용이 가장 낮음
- 문자열, 실행 흐름, 위험 호출, 난독화 패턴 분석이 기존 파이프라인과 자연스럽게 연결됨
- PE/ELF/APK는 포맷별 파서, 메타데이터, import/API, 섹션 구조 등 별도 분석 체계가 필요해 난이도가 더 높음

우선순위는 다음과 같습니다.

- 1차: Python 및 스크립트형 난독화/의심 코드 분석 확장
- 2차: PE/ELF 같은 실행 파일 정적 분석
- 3차: APK 등 플랫폼 특화 포맷 확장

### Q3. 현재 룰은 `eval`, `exec`, `os.system`, `pickle`, `yaml.load` 등 보수적인 위험 호출 중심인데, 오탐을 줄이면서 탐지 범위를 넓히기 위한 기준은 무엇인가?

핵심은 **룰 개수 확대보다 문맥 정보 강화**입니다.

- 단일 위험 호출 존재 여부만 보지 않음
- 외부 입력과 직접 연결되는지 확인
- 검증, 예외 처리, 격리 여부 같은 완화 요소를 함께 확인
- 여러 위험 신호를 조합해 우선순위와 위험도를 판단
- 새 룰 추가 전에는 검증 데이터셋으로 precision / recall을 확인

정리하면 다음과 같습니다.

- 탐지 범위 확장: 룰 추가
- 오탐 억제: 문맥 정보, 조합 규칙, 점수화

### Q4. 현재 구조에서는 정적 분석기가 deterministic signal을 만들고 LLM이 reviewer-facing summary를 생성하는 방식인데, 최종 판단 권한은 rule engine과 LLM 중 어디에 두는 것이 맞다고 보는가?

현재 방향은 **최종 판단 기준은 rule engine과 deterministic analyzer에 두고, LLM은 해석과 요약을 담당하도록 두는 것**입니다.

- rule 기반 결과는 재현 가능하고 검증 가능함
- 보안 영역에서는 판단 근거와 버전 관리가 중요함
- LLM은 설명, 우선순위화, 권고안 정리에는 강하지만 최종 판단 기준으로 두기에는 변동성이 있음

역할 분리는 다음과 같습니다.

- Rule Engine / Static Analyzer: 탐지 근거 생성, 위험 신호 식별, 기준점 제공
- LLM: 결과 요약, 사람 친화적 설명, 위험 해석, 권고안 정리
