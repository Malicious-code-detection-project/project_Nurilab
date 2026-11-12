# Project NuriLab 사용 안내

이 문서는 현재 `main.py` 실행 경로의 CLI, report 출력, Local LLM 연결 설정과
시연용 [웹 분석](#웹-분석-mvp) 실행 방법을 설명합니다. 지원 범위와 시스템 개요는
[`../README.md`](../README.md), 실행 흐름과 실패 경계는
[`ARCHITECTURE.md`](ARCHITECTURE.md)를 참조하세요.

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
| `--jadx-mcp-class <class>` | 사용 안 함 | 실험적(THE-154, THE-155). 주면 jadx-ai-mcp `get_class_source`를 한 번 호출하고 결과를 JSON/HTML에 기록 |
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
UTF-8로 쓸 수 없는 문자(UTF-8이 아닌 파일 이름, LLM 응답의 짝 없는 서로게이트 등)는
어디서 왔든 보고서에 `?`로 기록합니다.

## Mock review

`MockReviewClient`가 기본 backend입니다. 네트워크와 LLM 서버가 필요하지 않으며,
정적 신호를 재현 가능한 review finding으로 바꿉니다. 일반 개발과 회귀 검증은 이
경로를 기준으로 합니다. Mock으로 만든 HTML 보고서의 제목 옆에는 `Mock 모드(LLM 미사용)`
배지가 붙습니다. JSON과 Markdown 보고서에는 붙지 않습니다.

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

JSON 보고서의 `review.reviewer`는 리뷰를 만든 client와 결과를 기록합니다.
LLM 실패 여부는 `review.reviewer.status`가 `failed`인지로 판단합니다.
Mock도 읽지 못한 단일 파일(skipped)과 신호 없이 읽지 못한 파일이 있는 폴더는
`risk_level`이 `unknown`이므로 `risk_level`만으로는 LLM 실패와 구별되지 않습니다.

```json
"reviewer": {"client": "local", "model": "openai/gpt-oss-20b", "status": "failed", "failure_code": "timeout"}
```

- `client`: `mock` 또는 `local`. `model`은 Mock이면 `null`입니다.
- `status`: `ok` 또는 `failed`. `failure_code`는 성공이면 `null`입니다.

`failure_code`별 확인할 곳은 다음과 같습니다.

- `connection_failed` (연결 오류): 서버 실행 상태, URL, host/port, model name을
  확인합니다.
- `timeout`: 모델 로딩과 GPU 상태를 확인한 뒤 timeout을 조정합니다. 응답 본문을
  받다가 멈춘 경우도 포함합니다.
- `http_error` (HTTP 오류): OpenAI-compatible endpoint와 server log를 확인합니다.
- `invalid_response` (응답 shape 오류): 응답이 OpenAI-compatible
  `choices[0].message.content` 구조인지 server log와 함께 확인합니다. 응답 본문을
  받는 도중 연결이 끊긴 경우도 여기에 해당하므로 서버 재시작이나 네트워크 상태도
  확인합니다.
- `json_parse_failed` (JSON/schema 오류): 모델이 JSON object만 반환하는지와
  `low`/`medium`/`high` severity 계약을 확인합니다. `message.content`가 `null`인
  응답(예: gpt-oss가 추론에 토큰을 다 쓴 경우)도 여기에 해당합니다.

이 failure finding은 deterministic analyzer의 signal과 JSON/HTML report 생성을
계속 유지한다는 뜻입니다. report가 생성되었다고 모든 optional backend가 성공한 것은
아닙니다.

잘못된 timeout/budget 환경변수는 client 구성 단계에서 예외가 발생할 수 있습니다.
요청 후의 API 실패와 구분해야 합니다. 실제 서버 검증 방법과 환경 기록은
[Local LLM 통합 테스트](LOCAL_LLM_INTEGRATION_TEST.md)를 참조하세요.
`NURILAB_RUN_LOCAL_LLM=1`을 설정하지 않은 기본 pytest는 해당 테스트를 생략합니다.

## 웹 분석 (MVP)

브라우저에서 CLI와 같은 분석기를 쓰는 시연용 최소 웹입니다(THE-157). 입력은 CLI와
같은 `.py` 1개 또는 폴더 1개이고, 리뷰도 CLI처럼 Mock이 기본입니다. 인증이 없으므로
시연과 개인 테스트에만 씁니다. 설계와 API 계약은 [웹 MVP 설계](WEB_MVP_DESIGN.md)가
정본입니다.

### 실행

```bash
uv run python -m project_nurilab.web
```

브라우저에서 `http://127.0.0.1:8080`을 열고, 끝나면 터미널에서 `Ctrl+C`로 내립니다.
공식 실행 명령은 이것 하나입니다. `uvicorn …:app`을 직접 실행하면 아래 bind 설정을
읽지 않으므로 쓰지 않습니다. 웹은 vLLM을 시작하지 않습니다.

| 환경변수 | 기본값 | 설명 |
| --- | --- | --- |
| `NURILAB_WEB_HOST` | `127.0.0.1` | bind 주소. 다른 PC에서 접속하는 서버 시연 때만 `0.0.0.0` |
| `NURILAB_WEB_PORT` | `8080` | bind 포트 |
| `NURILAB_WEB_DATA_DIR` | `~/.local/share/nurilab-web` | job별 업로드 원본·보고서와 `jobs.sqlite3`. 사내 소스가 커밋되지 않도록 저장소 밖에 둡니다. `\`가 든 경로는 쓸 수 없습니다 |
| `NURILAB_WEB_MAX_UPLOAD_BYTES` | `52428800` (50 MiB) | 요청 본문 전체 크기 상한 |
| `NURILAB_WEB_MAX_PYTHON_FILES` | `500` | 걸러낸 뒤 분석할 `.py` 수 상한 |
| `NURILAB_WEB_MAX_FORM_FILES` | `1000` | 요청 하나에 받을 파일 수 상한. `NURILAB_WEB_MAX_PYTHON_FILES`보다 크고 1000 이하 |

LLM endpoint와 모델은 CLI와 같은 [연결 환경변수](#연결-환경변수)
(`NURILAB_LLM_BASE_URL`, `NURILAB_LLM_MODEL`, `NURILAB_LLM_TIMEOUT`)를 씁니다.

위 표의 `NURILAB_WEB_*` 값이 잘못되면 웹은 시작하지 않고 원인을 출력한 뒤 종료 코드
`2`로 끝납니다. `NURILAB_LLM_*` 값은 시작할 때 검사하지 않습니다.
`NURILAB_LLM_TIMEOUT`이나 `NURILAB_LLM_INPUT_BUDGET_BYTES`가 잘못되어도 웹은 뜨고
Mock 분석도 되지만, LLM 연결 확인과 LLM 분석 요청은 `500 internal_error`로
실패합니다. 원인은 웹 서버 로그에 남습니다.

### 사용 방법

1. "파일 선택"이나 "폴더 선택"을 누르거나, 파일 1개 또는 폴더 1개를 끌어 놓습니다.
   새로 고르면 이전 선택은 지워집니다.
2. 리뷰 모드를 고릅니다. "LLM 리뷰 사용" 토글이 꺼져 있으면 Mock(CLI의
   `--review-client mock`), 켜면 Local LLM(`--review-client local`)입니다. 토글을
   켜면 LLM 연결 상태와 모델 이름이 표시되고, 연결할 수 없으면 실행 버튼이 막힙니다.
3. "분석 실행"을 누르면 결과가 나옵니다. `정적 분석 위험도`가 판단 기준이고 그 아래의
   `리뷰 위험도`는 Mock 또는 LLM의 해석입니다. 출처, 해석 안내, 정적 분석 신호, 리뷰
   요약과 finding, 읽지 못한 파일을 표시하고 JSON/HTML 보고서를 내려받을 수 있습니다.

LLM이 분석 도중 실패하면 job은 완료로 끝나고 "LLM 리뷰 실패, 정적 분석 결과만 유효"
경고와 `failure_code`별 고정 문구가 뜹니다. endpoint 주소와 예외 원문은 화면에
나오지 않으며, 원인은 내려받은 보고서의 finding과 웹 서버 로그에서 확인합니다.

### 업로드 규칙

- `.py`만 분석합니다. 다른 파일과 제외 폴더(CLI와 같은 `.git`, `.venv`,
  `__pycache__`, `.pytest_cache`, `.ruff_cache`, `build`, `dist`, `reports`) 아래
  파일은 조용히 버립니다. 제외 폴더는 업로드한 폴더 아래에서만 판정하므로 `build`라는
  폴더 자체를 올리면 분석됩니다.
- 브라우저도 업로드 전에 같은 규칙으로 거릅니다(`GET /api/upload-rules`).
- 경로 조작(`..`, 절대 경로, `\`, `<`·`>`), 대소문자나 유니코드 정규화만 다른 같은
  경로, 최상위 폴더 2개 이상, 64단계를 넘는 깊이, 보고서 파일 이름이 너무 긴 업로드는
  `400 invalid_path`로 거부합니다. 전체 목록은 설계 문서 6절에 있습니다.
- 요청 크기(`NURILAB_WEB_MAX_UPLOAD_BYTES`)를 넘으면 `413 too_large`, 걸러낸 뒤
  `.py` 수(`NURILAB_WEB_MAX_PYTHON_FILES`)를 넘으면 `413 too_many_files`, 걸러낸 뒤
  `.py`가 0개면 `422 no_python_files`입니다. 요청 하나의 파일 수
  (`NURILAB_WEB_MAX_FORM_FILES`)를 넘으면 걸러내기 전에 `400 invalid_upload`로
  거부합니다.

### CLI와 다른 점

같은 입력에서 웹의 JSON 보고서는 CLI `--no-ruff` Mock 보고서와 `generated_at`을
빼고 같습니다(`tests/test_web_cli_parity.py`). 경로만 업로드 기준 상대 경로
(`myproj/a.py`)로 바뀝니다. 그 밖에 의도적으로 다른 동작은 다음과 같습니다.

- 웹은 Ruff를 실행하지 않습니다(CLI `--no-ruff`와 같음).
- LLM 토글을 켰는데 연결할 수 없으면 job을 만들지 않고 `503 llm_unavailable`로
  막습니다. CLI는 실행한 뒤 실패를 finding으로 남깁니다.
- `.py`가 0개인 업로드와 위 업로드 규칙에 걸린 경로는 거부합니다. CLI는 보고서를
  만듭니다.
- 화면은 LLM 실패 원문을 고정 문구로 바꿉니다. 내려받은 보고서에는 원문이 남습니다.
- 웹 화면은 정적 분석 위험도와 리뷰 위험도를 나눠 보여주지만, 보고서 헤더 배지와 CLI
  터미널의 `Risk Level`은 리뷰 값입니다.
- jadx-ai-mcp는 웹에서 다루지 않습니다.

### 실행 구성

- **기본:** 리눅스 GPU 서버 한 대에서 vLLM과 웹을 함께 실행하고 웹은
  `localhost:8000`의 vLLM을 호출합니다. vLLM은 [Local LLM 통합
  테스트](LOCAL_LLM_INTEGRATION_TEST.md)의 사전 조건대로 `--host 127.0.0.1`로 띄웁니다.
- **서버 시연:** 다른 PC의 브라우저로 보여줄 때만 bind를 바꿉니다.

  ```bash
  NURILAB_WEB_HOST=0.0.0.0 uv run python -m project_nurilab.web
  ```

  다른 PC에서 `http://<서버주소>:8080`을 엽니다. 인증과 `Origin`·`Host` 확인이
  없어 같은 망의 누구나 분석을 요청할 수 있으므로, 시연이 끝나면 바로 내리고 가능하면
  방화벽으로 접근 IP를 제한합니다.
- **개인 PC 임시 테스트:** 웹은 개인 PC에서 기본값(`127.0.0.1`)으로 띄우고, LLM은
  서버 주소로 호출합니다. 서버 주소와 내부 IP가 커밋되지 않도록 `config.py`를 고치지
  않고 환경변수로 지정합니다.

  ```bash
  NURILAB_LLM_BASE_URL=http://<서버주소>:8000/v1 uv run python -m project_nurilab.web
  ```

  테스트 동안만 서버의 vLLM을 `--host 0.0.0.0`으로 띄웁니다. vLLM도 인증 없이
  열리므로 끝나면 바로 내리고, 가능하면 접근 IP를 제한합니다.

### 시연 절차

새 환경에서는 `uv sync --locked` 뒤 웹을 띄우고 아래 세 경로를 차례로 확인합니다.
입력은 저장소의 무해한 fixture 폴더 `tests/fixtures/review_quality_project`입니다.

1. **Mock 분석 (인터넷 없이):** 토글을 끈 채 폴더를 올려 분석합니다. 결과에
   `정적 분석 위험도` `high`, `리뷰` `Mock (LLM 미사용)`, `리뷰 상태` `성공`과
   "Mock 모드(LLM 미사용)" 배지가 나와야 합니다.
2. **LLM 미연결 차단:** vLLM을 띄우지 않은 상태에서(또는 닫힌 포트를
   `NURILAB_LLM_BASE_URL`로 지정하고) 토글을 켭니다. "LLM 서버에 연결할 수 없거나
   응답이 올바르지 않습니다." 안내가 뜨고 실행 버튼이 막혀야 합니다. 토글을 끄면
   Mock으로 실행할 수 있습니다.
3. **LLM 분석:** vLLM을 띄운 뒤 토글을 켜면 "LLM 서버에 연결되었습니다. (모델: …)"가
   표시됩니다. 분석하면 `리뷰`가 `LLM (<모델>)`, `리뷰 상태`가 `성공`이고 LLM 실패
   경고가 없어야 합니다.
   LLM이 응답하는 데 수십 초가 걸릴 수 있습니다.

실제 vLLM으로 웹 LLM 경로를 확인하는 선택형 테스트와 기록 항목은
[Local LLM 통합 테스트](LOCAL_LLM_INTEGRATION_TEST.md)에 있습니다.

### 데이터 정리

업로드 원본은 분석이 끝나면(실패해도) 바로 지웁니다. 보고서와 job 기록은
`NURILAB_WEB_DATA_DIR`에 남고 자동으로 지우지 않으므로, 필요하면 웹을 내린 뒤 그
폴더를 직접 정리합니다. 웹을 다시 시작하면 끝나지 못한 job은 `failed`
(`interrupted`)로 바뀝니다.

### 확인한 환경과 알려진 한계

- 검증 기준 브라우저는 Chrome입니다. 다른 브라우저는 확인하지 않았습니다.
- 인증이 없습니다. job id(UUID)를 아는 사람은 결과를 볼 수 있습니다.
- 분석은 한 번에 하나씩 실행하며 프로세스 격리와 전체 시간 상한이 없습니다.
- LLM prompt에는 서버 절대 경로가 들어갑니다. LLM이 그 경로를 잘라 문장에 쓰면 경로
  치환에서 빠져 화면과 보고서에 남을 수 있습니다.
- 전체 목록과 이유는 설계 문서 9절을 참조하세요.

## jadx-ai-mcp 연결 (실험적)

THE-154·THE-155에서 구현한 실험적 연결입니다. 호출 기록은 아래 터미널 출력, JSON 보고서의
최상위 `external_tool_calls`, HTML 보고서 끝의 `External Tool Calls (jadx-ai-mcp)`
섹션에서 확인할 수 있습니다. 선택 출력인 Markdown 보고서에도 끝에 같은 이름의 섹션으로
상태·사유·출처 항목을 남기며, 받은 소스는 HTML·JSON 보고서에만 담습니다. 보고서의
`server_url`에는 `--jadx-mcp-url`의 사용자 정보(`user:token@`)·query·fragment를 빼고
기록하며, 사용자 정보를 확실히 가려낼 수 없는 URL은 `(unparsable URL omitted)`로
대신합니다. 계약과 실측 기록은
[THE-151 연결 계약](THE-151_jadx_mcp_contract.md)을 참조하세요.

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
`com.nurilab.dummy.TestClass`이며, `get_class_source`가 실제로 호출되어 jadx가 응답했는지,
연결·호출 시간 제한이 `timeout`으로 기록되는지, 같은 호출을 3번 반복해도 상태·크기·소스
SHA-256이 같은지, 실제 호출 결과가 JSON/HTML 보고서에 기록되고 정적 분석과 review는
바뀌지 않는지 확인합니다. jadx 응답으로 인정하는 상태는
`success`, `empty`, `not_found`와, 사유가 플러그인 연결 실패(`Cannot connect to JADX plugin`)인
`unavailable`뿐입니다. 서버 연결 실패나 tool 미제공처럼 호출 전에 멈춘 경우는 실패로
판정합니다. 진단 출력은 상태·사유 분류 이름·서버 버전·응답 크기·절삭 여부·소요 시간만
남기며 소스, 접속 정보, 사유 원문은 출력하지 않습니다. 반복 호출 테스트는 비교를 위해
소스 대신 소스의 SHA-256만 함께 출력합니다.

## Ruff

Ruff는 보조 signal입니다. 기본적으로 `uv run ruff check <target> --output-format json`
형태로 실행하며, finding 때문에 발생하는 non-zero exit code는 pipeline 실패가
아닙니다. Ruff가 실행되지 않거나 JSON을 반환하지 못해도 diagnostic finding을
보존하고 report 생성을 계속합니다.

Ruff가 없는 환경 또는 AST 경로만 확인하려는 경우 `--no-ruff`를 사용합니다.
