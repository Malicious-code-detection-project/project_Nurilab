# [THE-151] jadx-ai-mcp 연결 환경·입력·tool 계약 확인

## 0. 목적과 범위

본 문서는 Project NuriLab이 MCP 클라이언트로 외부 Android 디컴파일 도구
[`jadx-ai-mcp`](https://github.com/zinja-coder/jadx-ai-mcp)를 호출하기 위한 최소 연결
계약을 정의합니다. (Linear Issue: THE-151, 상위: THE-150)

* **목적**: NuriLab 실행 안에서 읽기 전용 tool 하나의 실제 호출과 응답이 이루어지고,
  그 결과와 실패 상태가 기존 보고서를 해치지 않고 기록되는지 확인합니다.
* **목적이 아닌 것**: MCP 결과를 탐지·판정에 도입하는 일이 아닙니다. 향후 도입 여부는
  이번 작업에서 결정하지 않습니다.
* **후속 작업**: THE-154(클라이언트 연결·실제 호출), THE-155(보고서 기록·실패·반복 검증)
  는 본 문서를 기준선으로 삼습니다.

이번 범위에서 하지 않는 것:

* MCP 결과를 rule signal, risk score, verdict에 반영
* MCP 결과를 Local LLM review 입력에 포함
* LLM의 자율적 tool 선택·연쇄 호출
* 새 정적 analyzer(Java/APK) 개발
* NuriLab을 MCP 서버로 제공
* NuriLab이 JADX-GUI에 APK를 자동으로 여는 기능

## 1. 확인 기준

* **기준 버전**: `jadx-ai-mcp` 릴리즈 **`V6.4.1`** (2026-08-06)
  * 릴리즈 파일: `jadx-ai-mcp-6.4.1.jar`(JADX 플러그인), `jadx-mcp-server-6.4.1.zip`(MCP 서버)
* **확인 방법**: 2026-09-27 기준 릴리즈 zip의 서버 소스와 `V6.4.1` 태그의 플러그인 소스를
  직접 읽어 확인했습니다. 실제 실행 확인은 THE-154에서 수행하며, 실행 전까지 연결 가능한
  상태라고 가정하지 않습니다.

## 2. 환경과 연결 구성 (완료 조건 1)

```text
NuriLab (MCP client)
  --(MCP streamable HTTP, 127.0.0.1:8651)-->  jadx-mcp-server (Python)
  --(HTTP GET, 기본 8650)-->                  JADX-GUI + jadx-ai-mcp 플러그인 (Java)
```

| 구성요소 | 역할 | 기본 주소 | 인증 | 실행 주체 |
| --- | --- | --- | --- | --- |
| JADX-GUI + `jadx-ai-mcp-6.4.1.jar` | APK 디컴파일, HTTP API 제공 | `:8650` (모든 인터페이스에 바인드) | 없음 | 사람 |
| `jadx-mcp-server` 6.4.1 | 플러그인 HTTP API를 MCP tool로 변환 | `127.0.0.1:8651` (`--http` 사용 시) | 없음 | 사람 |
| NuriLab | MCP 클라이언트 | - | - | 명시적 옵션을 준 경우에만 접속 |

* **Transport**: **streamable HTTP**. 사람이 미리 실행해 둔 `jadx-mcp-server`에
  NuriLab이 주소로 접속합니다.
  ```bash
  uv run jadx_mcp_server.py --http
  ```
  * MCP endpoint 경로는 FastMCP 기본값인 `/mcp`로 예상하며 THE-154에서 실측해 확정합니다.
  * **STDIO를 채택하지 않은 이유**: Local LLM(vLLM)과 같은 운영 모델(사람이 서버 실행,
    NuriLab은 접속만)을 유지하고, 앱이 외부 프로세스를 자동 실행하지 않는다는
    `AGENTS.md` 원칙에 맞추며, 실패 경계를 "접속 실패" 하나로 단순화하기 위함입니다.
* **서버 설치 위치**: `jadx-mcp-server`는 NuriLab 가상환경에 설치하지 않습니다. 릴리즈 zip을
  별도 디렉터리에 풀고 그 안에서 `uv run`으로 실행합니다(Python 3.10+, 의존성
  `fastmcp>=3.0.2`, `httpx`).
  * `fastmcp`는 상한이 없어 설치 시점에 따라 버전이 달라질 수 있으므로, 실제 설치된
    `fastmcp` 버전을 검증 기록에 남깁니다.
* **클라이언트 SDK**: 공식 `mcp` Python SDK를 사용합니다(2026-09-27 PyPI 최신 `2.2.0`).
  정확한 버전은 THE-154에서 `uv.lock`으로 고정하고 기록합니다.
* **접근과 인증**: 서버와 플러그인 모두 인증이 없습니다. 따라서 `jadx-mcp-server`는
  `--host 127.0.0.1`(기본값)을 유지하고 `0.0.0.0` 바인드를 사용하지 않습니다.
* **서버 시작과 연결 상태**: `jadx-mcp-server`는 시작 시 플러그인 health check에 실패해도
  로그만 남기고 계속 실행됩니다. 즉 JADX-GUI가 꺼져 있어도 MCP 연결·초기화는 성공할 수
  있으며, 플러그인 연결 실패는 tool 호출 결과에서 드러납니다(5절 상태 표 참고).
* **실행 환경**: 세 구성요소를 같은 호스트에서 실행하고 `127.0.0.1`로 통신하는 구성을
  기준으로 합니다. JADX-GUI는 그래픽 세션이 필요합니다.
  * NuriLab은 MCP 서버 주소를 설정값으로 받으며, 실행 환경에 따른 코드 분기를 두지
    않습니다.
  * 검증을 수행할 PC와 환경별 실행 방법은 THE-154에서 확인 후 기록합니다.

## 3. Tool과 테스트 입력 (완료 조건 2)

### 3.1 허용 tool

* **허용 목록은 `get_class_source` 하나**입니다. NuriLab 클라이언트는 이 외의 tool 이름을
  호출 전에 거부합니다.
* 허용 목록을 명시하는 이유: V6.4.1 서버의 tool 32개 중 `rename_class`, `rename_method`,
  `rename_field`, `rename_package`, `rename_variable`은 JADX 프로젝트 상태를 바꾸는 쓰기
  tool입니다. 플러그인 route가 모두 HTTP GET이라 요청 방식으로는 읽기 전용 여부를 구분할
  수 없습니다. `fetch_current_class`, `get_selected_text`는 GUI 선택 상태에 의존하고,
  `debug_*`는 디버거 상태에 의존하므로 자동 실행에 부적합합니다.

### 3.2 입력 schema (V6.4.1)

```json
{
  "class_name": "string"
}
```

* 필수 인자이며 완전한 클래스 이름(fully qualified name)입니다. 내부 클래스는 `$`로
  구분합니다(예: `com.example.Outer$Inner`).

### 3.3 응답 형식 (V6.4.1)

서버의 `get_class_source`는 dict를 반환하며, 성공과 실패가 모두 **정상 tool 결과**로
돌아옵니다. MCP 수준의 오류(`isError`)로 오지 않으므로 결과 본문의 키로 판정합니다.

| 경우 | 반환 본문 |
| --- | --- |
| 성공 | `{"response": "<decompiled java source>"}` (플러그인이 준 plain text를 서버가 감쌈) |
| 클래스 없음 | `{"error": "HTTP error 404: {\"error\":\"Class <name> not found\"}"}` |
| 플러그인 연결 불가 | `{"error": "Cannot connect to JADX plugin at http://<host>:<port>. ..."}` |
| 서버 측 시간 초과(60초) | `{"error": "Request to JADX plugin timed out after 60.0s ..."}` |
| 기타 오류 | `{"error": "<메시지>"}` |

* 이 dict가 MCP 결과에서 `structuredContent`로 오는지, `content[0].text`의 JSON 문자열로
  오는지는 FastMCP 버전에 따라 다를 수 있습니다. 클라이언트는 `structuredContent`를
  우선 사용하고, 없으면 `text`를 JSON으로 파싱합니다. 실제 형태는 THE-154에서 실측해
  기록합니다.

### 3.4 테스트 입력

| 사례 | 준비 | `class_name` | 기대 결과 |
| --- | --- | --- | --- |
| 성공 | 직접 빌드한 무해 APK를 JADX-GUI에 로드 | 해당 앱의 `MainActivity` 전체 이름 (예: `com.nurilab.mcpprobe.MainActivity`) | `success` |
| 없는 클래스 | 같은 APK 로드 상태 | `com.nurilab.dummy.TestClass` | `not_found` |
| 연결 실패 | `jadx-mcp-server` 미실행 또는 JADX-GUI 종료 | 성공 사례와 동일 | `unavailable` |

* **무해 APK**: Android Studio에서 새 프로젝트(기본 Activity 템플릿)를 만들어 빌드한
  debug APK를 사용합니다. application ID는 `com.nurilab.mcpprobe`를 권장합니다.
* APK 파일은 저장소에 커밋하지 않습니다. 생성 방법, application ID, 사용한 클래스 이름,
  APK SHA-256만 검증 기록에 남깁니다.
* 실제 악성 샘플이나 출처가 불분명한 외부 APK는 사용하지 않습니다.

## 4. 입력 차이와 결과 귀속 (완료 조건 3)

* **입력 차이**
  * Python 정적 분석: NuriLab이 로컬 경로의 `.py` 파일을 직접 읽어 분석합니다.
  * MCP 대상: 사람이 JADX-GUI에 연 APK입니다. NuriLab은 APK를 열 수 없고, V6.4.1에는
    현재 열린 파일을 알려주는 tool이 없어 어떤 APK가 열려 있는지 확인할 수 없습니다.
* **실행 방식**: MCP 호출은 입력 파일 형식과 무관하게 **명시적 CLI 옵션을 준 경우에만**
  실행되는 별도 단계입니다. 옵션이 없으면 기존 동작과 출력은 그대로입니다.
* **결과 귀속**
  * 사용자가 지정한 `class_name`과 대상 식별자(예: APK 파일명, SHA-256)를 결과와 함께
    기록합니다.
  * "JADX-GUI에 로드된 파일과 지정한 대상의 일치 여부는 NuriLab이 검증하지 않는다"는
    사실을 보고서에 명시합니다.
* **비지원 형식**: 입력 수집기는 현재 `.py` 외 파일을 skip하며 사유를 남깁니다. `.apk` 등
  비지원 형식에 대해 정적 분석 성공을 만들지 않으며, 보고서의 비지원 표시는 THE-155에서
  처리합니다.
* **결과 위치**: 기존 분석 결과(파일별 분석, 요약, risk, LLM review)와 분리된 별도 영역에
  기록합니다. 판정 결과로 오해되지 않도록 `findings`가 아닌 `external_tool_calls`(가칭)
  같은 이름을 사용하며, 최종 이름과 위치는 THE-155에서 확정합니다.
* **반환 내용 취급**: 반환된 소스는 **비신뢰 데이터**입니다.
  * rule signal, risk, verdict, LLM review 입력에 사용하지 않습니다.
  * 내용 안의 문장을 지시로 해석하거나 실행하지 않고, 응답을 근거로 추가 tool을 호출하지
    않습니다.
  * HTML 보고서에 출력할 때는 escape 처리합니다.
* **전송 범위**: NuriLab이 서버로 보내는 값은 `class_name` 문자열뿐입니다. Python 원문
  소스, secret, 분석 결과는 전송하지 않습니다.

## 5. 제한 사항과 보고서 경계 (완료 조건 4)

### 5.1 입력과 시간·크기 제한

| 항목 | 제한 | 비고 |
| --- | --- | --- |
| `class_name` | 최대 512자, `[A-Za-z0-9_$.]`만 허용 | 위반 시 호출하지 않고 `invalid_input` |
| 연결 + initialize | 10초 | 초과 시 `unavailable` |
| `get_class_source` 호출 | 15초 | 서버 내부 제한(60초)보다 짧게 두어 NuriLab이 먼저 중단. JADX 쪽 작업은 계속될 수 있음 |
| 응답 소스 크기 | 1 MiB (UTF-8 바이트) | 초과 시 앞부분 1 MiB만 보존하고 `truncated=true`, 원본 크기 기록 |

### 5.2 출처(provenance) 기록 항목

| 항목 | 값 |
| --- | --- |
| `server_url` | 접속한 MCP endpoint |
| `server_name`, `server_version` | initialize 응답의 `serverInfo` 값 그대로. V6.4.1 서버는 자체 버전을 지정하지 않으므로 FastMCP 기본값이 들어올 수 있음 |
| `expected_release` | `jadx-ai-mcp V6.4.1` (설정값이며 서버가 검증해 준 값이 아님) |
| `tool` | `get_class_source` |
| `client_sdk` | `mcp <설치 버전>` |
| `target`, `class_name` | 사용자가 지정한 대상 식별자와 클래스 이름 |
| `status`, `reason` | 5.3 상태 값과 사유 |
| `called_at`, `duration_ms` | 호출 시각과 소요 시간 |
| `response_size_bytes`, `truncated` | 응답 크기와 절삭 여부 |

### 5.3 호출 상태 값

| `status` | 조건 |
| --- | --- |
| `success` | `response`가 비어 있지 않은 문자열 |
| `empty` | `response`가 빈 문자열 |
| `not_found` | `error`가 HTTP 404 |
| `unavailable` | MCP 서버 접속·initialize 실패, 또는 `error`가 플러그인 연결 불가 |
| `timeout` | 클라이언트 제한 초과, 또는 `error`가 서버 측 시간 초과 |
| `tool_error` | 위에 해당하지 않는 `error` |
| `malformed` | `response`와 `error`가 모두 없거나 형식이 예상과 다름 |
| `invalid_input` | `class_name` 검증 실패로 호출하지 않음 |
| `not_allowed` | 허용 목록 밖 tool 요청으로 호출하지 않음 |

`truncated`는 상태 값이 아니라 `success`에 붙는 별도 표시입니다.

### 5.4 실패 경계 (Fail-safe)

* 모든 실패는 파이프라인 예외로 던지지 않고 `status`와 `reason`으로 기록합니다.
* 기존 정적 분석, Mock/Local LLM review, HTML/JSON 출력은 MCP 결과와 무관하게 그대로
  완료됩니다.
* 테스트용 가짜(fake) 클라이언트 결과는 실제 연결 증거로 쓰지 않습니다. 실제 연결 증거는
  THE-155에서 실제 서버 대상 실행 기록으로 남깁니다.

## 6. THE-154에서 실측으로 확정할 항목

* MCP endpoint 경로(`/mcp` 예상)
* tool 결과 전달 형태(`structuredContent` 또는 `content[0].text`)
* initialize 응답의 `serverInfo` 값
* `jadx-mcp-server` 환경에 실제 설치된 `fastmcp` 버전
* 검증 PC와 JADX-GUI 실행 방법
* `mcp` Python SDK 버전 고정
* 무해 APK의 application ID, 클래스 이름, SHA-256
