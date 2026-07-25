# Project NuriLab 아키텍처

이 문서는 현재 `main` 구현을 기준으로 Project NuriLab의 실행 구조, 모듈 책임,
데이터 계약과 실패 경계를 설명합니다. 현재 지원 기능과 CLI 사용법은
[`../README.md`](../README.md), 향후 Phase 계획은 [`PLAN.md`](PLAN.md)를
기준으로 합니다.

## 시스템 경계

Project NuriLab은 입력 코드를 실행하지 않는 단일 프로세스 Python 정적 분석
애플리케이션입니다.

애플리케이션이 직접 수행하는 작업:

- 파일 또는 디렉터리에서 Python 입력 수집
- UTF-8 source 로딩
- AST, 위험 호출 rule, secret pattern 분석
- 선택적 Ruff subprocess 실행
- deterministic Mock review 또는 외부 Local LLM API 호출
- 프로젝트 결과 집계
- HTML, JSON, 선택적 Markdown 보고서 생성

애플리케이션 경계 밖의 작업:

- vLLM 시작, 종료, 모델 다운로드와 GPU 관리
- 입력 코드와 실제 악성 샘플 실행
- 파인튜닝과 model artifact 생성
- 외부 프로젝트 clone과 dependency 설치

## 전체 데이터 흐름

```text
CLI
 |
 v
Phase1Pipeline
 |
 +--> InputCollector
 |    CollectedInput
 +--> PythonFileLoader
 |    LoadedPythonFile[]
 +--> PythonStaticAnalyzer -> PythonAnalysis[]
 +--> optional RuffToolCollector -> RuffFinding[]
 |
 +---- single file: PythonAnalysis + RuffFinding[]
 |
 +---- project: ResultAggregator
                  | ProjectAnalysis
                  v
              ReviewClient
                  | ReviewResult
                  v
       AnalysisReport or ProjectReport
                  |
                  v
            ReportGenerator
                  |
                  +--> HTML
                  +--> JSON
                  +--> optional Markdown
```

`Phase1Pipeline`이 현재 전체 흐름을 조정합니다. 이름은 초기 Phase의 흔적이지만
현재는 단일 파일과 프로젝트 입력을 모두 처리합니다. Phase 5의 `THE-99`에서
`AnalysisPipeline` 명칭과 이전 import 호환성을 정리할 예정입니다.

## 실행 경로

### CLI와 pipeline 구성

`project_nurilab.cli.main()`은 CLI option을 해석하고 review backend와 Ruff 사용
여부를 선택합니다.

- 기본 review backend: `MockReviewClient`
- `--review-client local`: `LocalLLMReviewClient`
- 기본 Ruff: 활성화
- `--no-ruff`: Ruff 비활성화

CLI는 분석 로직을 직접 수행하지 않고 `Phase1Pipeline.run()`에 입력 경로,
출력 디렉터리와 출력 형식을 전달합니다.

### 입력 수집과 로딩

`InputCollector`는 입력 경로를 절대 경로로 정규화합니다.

- `.py` 파일은 단일 분석 대상으로 수집합니다.
- 디렉터리는 하위 `.py` 파일을 정렬된 순서로 재귀 수집합니다.
- `.git`, `.venv`, cache, build, report 디렉터리는 제외합니다.
- non-Python 파일은 프로젝트 분석 대상에서 제외합니다.
- 존재하지 않는 경로는 즉시 `FileNotFoundError`를 발생시킵니다.

`PythonFileLoader`는 수집된 각 Python 파일을 UTF-8로 읽어
`LoadedPythonFile`을 만듭니다. decode, 권한, 파일 읽기 오류는 예외로 전체
pipeline을 중단하지 않고 `skipped=True`와 `skip_reason`으로 변환합니다.

### deterministic 분석

`PythonStaticAnalyzer`는 `LoadedPythonFile`을 `PythonAnalysis`로 변환합니다.

1. 줄 수와 skip 상태를 기록합니다.
2. line-oriented secret pattern을 검사합니다.
3. `ast.parse()`로 Python AST를 생성합니다.
4. import, function, class와 위험 호출 rule을 수집합니다.

문법 오류는 `syntax_error`로 저장되며 다른 파일 분석을 중단하지 않습니다.
현재 위험 호출은 AST에서 계산한 정확한 dotted call name으로 rule을 조회합니다.
import alias와 호출 인자 문맥은 아직 해석하지 않습니다.

### Ruff 보조 신호

`RuffToolCollector`는 `uv run ruff check <target> --output-format json`을 별도
subprocess로 실행합니다. Ruff의 non-zero exit code는 finding이 존재할 때도
사용되므로 pipeline 실패로 취급하지 않습니다.

- JSON stdout은 `RuffFinding`으로 정규화합니다.
- stdout이 JSON이 아니면 `RUFF_PARSE_ERROR` finding을 만듭니다.
- stdout이 비어 있으면 현재는 빈 finding 목록으로 처리합니다.

Ruff finding과 Ruff 실행 실패를 더 정확히 구분하는 작업은 Phase 4의 `THE-91`
범위입니다.

### 단일 파일과 프로젝트 분기

단일 파일:

```text
PythonAnalysis
-> ReviewClient
-> AnalysisReport
-> ReportGenerator
```

프로젝트:

```text
PythonAnalysis[]
+ RuffFinding[]
+ CollectedInput
-> ResultAggregator
-> ProjectAnalysis
-> ReviewClient
-> ProjectReport
-> ReportGenerator
```

`ResultAggregator`는 severity count, 프로젝트 risk level, analyzed/skipped count와
파일별 요약을 계산합니다. 프로젝트 risk는 deterministic signal의 최고 severity를
기준으로 합니다.

### review backend

`ReviewClient` protocol은 `PythonAnalysis | ProjectAnalysis`를 받아
`ReviewResult`를 반환합니다.

`MockReviewClient`:

- 네트워크 없이 동작합니다.
- 정적 신호를 deterministic finding으로 변환합니다.
- 기본 테스트와 회귀 검증 경로입니다.

`LocalLLMReviewClient`:

- 정규화된 정적 분석 payload만 vLLM OpenAI-compatible
  `/chat/completions` endpoint로 전송합니다.
- 원본 source text는 전송하지 않습니다.
- 응답 JSON을 `ReviewResult`와 `ReviewFinding`으로 정규화합니다.
- 상대 finding 경로를 분석 대상 기준의 절대 경로로 복원합니다.

Local LLM 결과는 정적 분석 결과를 덮어쓰지 않습니다. 연결, timeout, HTTP,
response shape와 JSON parsing 실패는 `risk_level="unknown"`인
`source="local_llm"` finding으로 변환됩니다.

## 주요 데이터 계약

| 단계 | 데이터 모델 | 책임 |
| --- | --- | --- |
| 입력 수집 | `CollectedInput` | root, Python 파일, 사전 제외 경로 |
| 파일 로딩 | `LoadedPythonFile` | source, lines, 읽기 skip 상태 |
| 파일 분석 | `PythonAnalysis` | AST, 위험 호출, secret, syntax, Ruff 신호 |
| 프로젝트 집계 | `ProjectAnalysis` | 파일 결과, Ruff 결과, 프로젝트 summary |
| 리뷰 | `ReviewResult` | summary, review risk, review findings |
| 단일 보고서 | `AnalysisReport` | metadata, `PythonAnalysis`, review |
| 프로젝트 보고서 | `ProjectReport` | metadata, `ProjectAnalysis`, review |

`analysis.summary.risk_level`은 deterministic project signal의 집계입니다.
`review.risk_level`은 선택한 review backend의 결과입니다. Local LLM 실패로 review
risk가 `unknown`이어도 deterministic analysis는 같은 보고서에 유지됩니다.

## 실패 경계

| 실패 | 현재 처리 |
| --- | --- |
| 입력 경로 없음 또는 잘못된 경로 종류 | 예외 발생, 보고서 생성 안 함 |
| UTF-8 decode, 권한, 파일 읽기 실패 | skipped file result로 보존 |
| Python syntax error | `syntax_error` signal로 보존 |
| Ruff invalid JSON | `RUFF_PARSE_ERROR` finding으로 보존 |
| Local LLM 연결·timeout·HTTP 오류 | Local LLM failure finding으로 보존 |
| Local LLM JSON parsing 오류 | Local LLM parsing finding으로 보존 |
| 출력 디렉터리 또는 파일 쓰기 실패 | 예외 발생 |

pipeline이 실패 finding으로 변환하는 장애와 호출자에게 예외를 반환하는 장애를
구분해야 합니다. 보고서가 생성됐다는 사실이 모든 analyzer와 외부 backend가
성공했다는 의미는 아닙니다.

## 보고서 경계

`ReportGenerator`는 하나의 report payload를 여러 view로 직렬화합니다.

- JSON: canonical machine-readable artifact
- HTML: 기본 human-readable view
- Markdown: 선택 출력

HTML과 Markdown은 별도 분석을 수행하지 않습니다. 세 출력은 동일한
`AnalysisReport` 또는 `ProjectReport`에서 생성됩니다.

## 현재 모듈 책임

```text
project_nurilab/
├── input/          # 입력 수집과 UTF-8 로딩
├── analyzers/      # AST, rule, secret, Ruff signal
├── aggregation/    # 프로젝트 summary와 risk 집계
├── llm/            # Mock/Local review backend
├── reports/        # JSON/HTML/Markdown view 생성
├── schemas.py      # 단계 간 데이터 계약
├── pipeline.py     # 전체 orchestration
├── cli.py          # 사용자 입력과 dependency 선택
└── config.py       # 기본값과 제외 경로
```

새 모듈은 이 책임 경계에 들어갈 수 없는 경우에만 추가합니다.

## 향후 확장 지점

다음은 현재 구현이 아니라 [`PLAN.md`](PLAN.md)에 정의된 예정 구조입니다.

- Phase 4: `analyzers/`의 alias·문맥 분석과 Local LLM payload budget
- Phase 5: 설치형 CLI, report provenance, pipeline 명칭 정리
- Phase 6: `llm/`의 serving contract를 유지한 AegisLM 모델 비교
- Phase 7: versioned local knowledge index와 finding evidence 결합

예정 기능을 현재 모듈처럼 문서화하지 않습니다. 각 Phase의 schema와 책임 경계는
해당 Linear 이슈에서 구현과 테스트가 병합된 뒤 이 문서에 반영합니다.
