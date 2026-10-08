# Project NuriLab 사용 안내

이 문서는 현재 `main.py` 실행 경로의 CLI, report 출력과 Local LLM 연결 설정을
설명합니다. 지원 범위와 시스템 개요는 [`../README.md`](../README.md), 실행 흐름과
실패 경계는 [`ARCHITECTURE.md`](ARCHITECTURE.md)를 참조하세요.

## 설치와 실행

Python 3.12와 [uv](https://docs.astral.sh/uv/)가 필요합니다. lock 파일에 고정된
환경을 구성합니다.

```bash
uv sync --locked
```

현재 저장소는 설치형 console script를 제공하지 않습니다. 다음처럼 실행합니다.

```bash
uv run python main.py analyze <path> [options]
```

`<path>`는 한 개의 `.py` 파일 또는 Python 파일을 포함하는 디렉터리입니다.

```bash
# 단일 파일
uv run python main.py analyze tests/fixtures/vulnerable_sample.py

# 디렉터리 아래 Python 파일 재귀 분석
uv run python main.py analyze tests
```

디렉터리 수집에서는 `.git`, `.venv`, `__pycache__`, `.pytest_cache`,
`.ruff_cache`, `build`, `dist`, `reports`를 제외합니다. 존재하지 않는 경로는 입력
오류로 끝나며 report를 만들지 않습니다. 단일 non-Python 파일은 skipped 입력으로,
읽기·UTF-8 decode 오류는 skipped file result로 보존합니다.

## CLI option

| option | 기본값 | 설명 |
| --- | --- | --- |
| `--out <dir>` | `reports` | report를 쓸 디렉터리 |
| `--format <formats...>` | `html json` | `html`, `json`, `md`를 하나 이상 선택 |
| `--review-client mock\|local` | `mock` | review backend 선택 |
| `--no-ruff` | 사용 안 함 | Ruff JSON finding 수집 비활성화 |
| `--max-lines <n>` | 없음 | 하위 호환용 deprecated no-op. 파일 줄 수를 제한하지 않음 |
| `--jadx-mcp-class <class>` | 사용 안 함 | 실험적(THE-154). 주면 jadx-ai-mcp `get_class_source`를 한 번 호출 |
| `--jadx-mcp-url <url>` | `http://127.0.0.1:8651/mcp` | 실험적. jadx-mcp-server endpoint. `--jadx-mcp-class` 필요 |
| `--jadx-mcp-target <name>` | 없음 | 실험적. 기록할 대상 식별자(예: APK 파일명). 검증하지 않음. `--jadx-mcp-class` 필요 |

예시:

```bash
# 기본 Mock review, HTML과 JSON 생성
uv run python main.py analyze tests

# Ruff 없이 분석
uv run python main.py analyze tests --no-ruff

# Markdown을 포함한 세 view 생성
uv run python main.py analyze tests --format html json md

# 출력 위치 변경
uv run python main.py analyze tests --out /tmp/nurilab-reports
```

JSON은 canonical machine-readable artifact입니다. HTML과 선택적 Markdown은 같은
report payload의 view이므로 별도 분석을 다시 실행하지 않습니다. 기본 이름은
`<target>.analysis.html`, `<target>.analysis.json`이며 Markdown을 선택하면
`<target>.analysis.md`도 생성합니다. `reports/`는 로컬 산출물로 커밋하지 않습니다.

## Mock review

`MockReviewClient`가 기본 backend입니다. 네트워크와 LLM 서버가 필요하지 않으며,
정적 신호를 재현 가능한 review finding으로 바꿉니다. 일반 개발과 회귀 검증은 이
경로를 기준으로 합니다.

```bash
uv run python main.py analyze tests --review-client mock
```

## Local LLM review

`--review-client local`은 이미 실행 중인 vLLM OpenAI-compatible API에만 요청을
보냅니다. NuriLab은 vLLM을 설치하거나 시작·종료하지 않고, 모델을 다운로드하거나
GPU를 관리하지 않습니다.

별도 터미널 또는 GPU host에서 서버를 준비합니다. 아래는 코드의 기본 model name을
사용하는 예시이며, 실제 배포의 served model name에 맞춰 설정해야 합니다.

```bash
vllm serve openai/gpt-oss-20b
```

분석 환경에서 Local LLM review를 명시적으로 선택합니다.

```bash
uv run python main.py analyze tests --review-client local
```

### 연결 환경변수

| 환경변수 | 기본값 | 설명 |
| --- | --- | --- |
| `NURILAB_LLM_BASE_URL` | `http://localhost:8000/v1` | OpenAI-compatible API base URL |
| `NURILAB_LLM_MODEL` | `openai/gpt-oss-20b` | server가 제공하는 model name |
| `NURILAB_LLM_TIMEOUT` | `120` | 요청 timeout(초). 숫자여야 함 |
| `NURILAB_LLM_INPUT_BUDGET_BYTES` | `65536` | 정규화한 Local LLM payload 최대 byte 수. 최소 `1024` |

```bash
export NURILAB_LLM_BASE_URL=http://127.0.0.1:8000/v1
export NURILAB_LLM_MODEL=openai/gpt-oss-20b
export NURILAB_LLM_TIMEOUT=120
export NURILAB_LLM_INPUT_BUDGET_BYTES=65536
uv run python main.py analyze tests --review-client local
```

분석기는 원본 source text 대신 정규화된 정적 분석 결과만 Local LLM payload에 넣습니다.
payload가 budget을 넘으면 signal을 중간에서 자르지 않고 포함 수와 누락 수를 기록한
truncation metadata를 사용합니다.

Local LLM은 strict JSON schema로 `summary`, `risk_level`, `findings`를 반환해야
합니다. `risk_level`과 finding `severity`는 `low`, `medium`, `high`만 허용합니다.
요청에는 `reasoning_effort="low"`를 사용하고 provider-specific `include_reasoning`
필드는 보내지 않습니다. 응답의 별도 reasoning 필드는 사용하지 않습니다.
JSON/schema 파싱 실패 시에는 응답 content의 최대 200자 preview가 오류 설명에
포함될 수 있으며 그 설명은 보고서 finding으로 저장됩니다.

### Local LLM 문제를 해석하는 방법

연결, timeout, HTTP 응답, 응답 shape, JSON parsing 또는 schema validation 실패는
정적 분석을 지우거나 pipeline 전체를 중단하지 않습니다. `review.risk_level`은
`unknown`이며, `source="local_llm"`인 failure finding을 보고서에 남깁니다.

- 연결 오류: 서버 실행 상태, URL, host/port, model name을 확인합니다.
- timeout: 모델 로딩과 GPU 상태를 확인한 뒤 timeout을 조정합니다.
- HTTP 오류: OpenAI-compatible endpoint와 server log를 확인합니다.
- JSON/schema 오류: 모델이 JSON object만 반환하는지와 `low`/`medium`/`high`
  severity 계약을 확인합니다.

이 failure finding은 deterministic analyzer의 signal과 JSON/HTML report 생성을
계속 유지한다는 뜻입니다. report가 생성되었다고 모든 optional backend가 성공한 것은
아닙니다.

잘못된 timeout/budget 환경변수는 client 구성 단계에서 예외가 발생할 수 있습니다.
요청 후의 API 실패와 구분해야 합니다. 실제 서버 검증 방법과 환경 기록은
[Local LLM 통합 테스트](LOCAL_LLM_INTEGRATION_TEST.md)를 참조하세요.
`NURILAB_RUN_LOCAL_LLM=1`을 설정하지 않은 기본 pytest는 해당 테스트를 생략합니다.

## jadx-ai-mcp 연결 (실험적)

THE-154에서 구현한 실험적 연결입니다. 결과를 JSON/HTML 보고서에 표시하는 작업은
THE-155에서 진행하므로, 현재는 아래 터미널 출력으로만 확인할 수 있습니다. 계약과 실측
기록은 [THE-151 연결 계약](THE-151_jadx_mcp_contract.md)을 참조하세요.

`--jadx-mcp-class`는 이미 실행 중인 `jadx-mcp-server`에만 접속합니다. NuriLab은
서버나 JADX-GUI를 설치하거나 시작·종료하지 않습니다. 서버·JADX-GUI·플러그인의 설치와
버전 고정 방법은 계약 문서 2절을 따르며, 별도 터미널에서 서버를 실행합니다. 클래스
소스를 받으려면 JADX-GUI에 대상 APK가 열려 있어야 합니다.

```bash
cd ~/tools/jadx-mcp-server-6.4.1 && .venv/bin/python jadx_mcp_server.py --http
~/tools/jadx-1.5.6/bin/jadx-gui <apk 경로>
```

분석 환경에서 클래스 이름을 지정해 호출을 명시적으로 선택합니다.

```bash
uv run python main.py analyze tests \
  --jadx-mcp-class com.nurilab.mcpprobe.MainActivity \
  --jadx-mcp-target mcpprobe-debug.apk
```

호출하면 기존 출력 뒤에 상태 한 줄이 추가됩니다.

```text
JADX MCP get_class_source: success (12,345 bytes)
JADX MCP get_class_source: unavailable - Cannot connect to JADX plugin at http://127.0.0.1:8650. ...
```

- 서버 미실행, 시간 초과, 오류 응답은 상태 값으로 기록되고 분석과 보고서 생성은
  계속됩니다. MCP 결과와 관계없이 종료 코드는 `0`입니다.
- `--jadx-mcp-target`은 JADX-GUI에 실제로 열린 APK와 일치하는지 검증하지 않습니다.

상태 값과 사유 형식은 계약 문서 5.3절을 참조하세요.

### MCP 연결 환경변수

| 환경변수 | 기본값 | 설명 |
| --- | --- | --- |
| `NURILAB_JADX_MCP_URL` | `http://127.0.0.1:8651/mcp` | `--jadx-mcp-url`을 주지 않을 때 쓰는 endpoint |

### MCP 실제 서버 선택형 테스트

기본 pytest는 가짜 MCP session으로 검증하며 서버가 필요하지 않습니다. 실행 중인
서버에 실제로 접속하는 테스트는 환경변수를 설정했을 때만 실행됩니다.

```bash
NURILAB_RUN_JADX_MCP=1 uv run pytest tests/test_jadx_mcp_integration.py
```

`NURILAB_JADX_MCP_CLASS`로 조회할 클래스를 바꿀 수 있습니다. 기본값은 존재하지 않는
`com.nurilab.dummy.TestClass`이며, `get_class_source`가 실제로 호출되어 jadx가 응답했는지와
연결·호출 시간 제한이 `timeout`으로 기록되는지 확인합니다. jadx 응답으로 인정하는 상태는
`success`, `empty`, `not_found`와, 사유가 플러그인 연결 실패(`Cannot connect to JADX plugin`)인
`unavailable`뿐입니다. 서버 연결 실패나 tool 미제공처럼 호출 전에 멈춘 경우는 실패로
판정합니다. 진단 출력은 상태·사유 분류 이름·서버 버전·응답 크기·절삭 여부·소요 시간만
남기며 소스, 접속 정보, 사유 원문은 출력하지 않습니다.

## Ruff

Ruff는 보조 signal입니다. 기본적으로 `uv run ruff check <target> --output-format json`
형태로 실행하며, finding 때문에 발생하는 non-zero exit code는 pipeline 실패가
아닙니다. Ruff가 실행되지 않거나 JSON을 반환하지 못해도 diagnostic finding을
보존하고 report 생성을 계속합니다.

Ruff가 없는 환경 또는 AST 경로만 확인하려는 경우 `--no-ruff`를 사용합니다.
