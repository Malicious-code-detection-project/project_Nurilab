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
  직접 읽어 확인했습니다. 실제 실행 확인은 THE-154에서 수행했으며 결과는 6절에
  기록합니다.

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
  * MCP endpoint는 `http://127.0.0.1:8651/mcp`입니다(2026-09-30 실측, 6절).
  * **STDIO를 채택하지 않은 이유**: Local LLM(vLLM)과 같은 운영 모델(사람이 서버 실행,
    NuriLab은 접속만)을 유지하고, 앱이 외부 프로세스를 자동 실행하지 않는다는
    `AGENTS.md` 원칙에 맞추며, 실패 경계를 "접속 실패" 하나로 단순화하기 위함입니다.
* **서버 설치와 버전 고정**: `jadx-mcp-server`는 NuriLab 가상환경에 설치하지 않고, 저장소
  밖 디렉터리에 전용 가상환경을 만들어 실행합니다.
  * 업스트림 README 방식(`uv run jadx_mcp_server.py --http`)은 스크립트의 의존성
    `fastmcp>=3.0.2`를 실행 시점의 최신 버전으로 설치하므로 사용하지 않습니다.
  * 대신 업스트림이 V6.4.1 릴리즈 시점(2026-08-06)에 `uv.lock`으로 고정한 버전으로
    설치합니다: `fastmcp==3.0.2`, `mcp==1.26.0`.
  * **MCP 프로토콜 버전은 별도로 고정하지 않습니다.** 연결 시 클라이언트가 제안하고 서버가
    지원 범위 안에서 수락하므로, 위 서버 버전 고정의 결과로 정해집니다.
    * 이 조건(V6.4.1 + `mcp==1.26.0`)에서 서버가 지원하는 버전은 `2024-11-05`,
      `2025-03-26`, `2025-06-18`, `2025-11-25`이며, NuriLab 클라이언트(`mcp 2.2.0`)는
      `initialize` 방식의 최신인 `2025-11-25`로 합의합니다(6.1, 6.2 실측).
    * MCP 규격의 더 새 버전 `2026-07-28`은 요청마다 버전을 담는 stateless 방식이라 서버
      지원이 필요하며, 업스트림이 검증한 위 서버 조합에서는 사용할 수 없습니다.
    * 업스트림 README 방식처럼 더 새 `fastmcp`로 설치하면 지원 범위가 달라질 수 있으며,
      이 경우 다시 실측합니다.
  * 최초 1회 설치(릴리즈 zip SHA-256:
    `e7cf0fa756b817cde3d3a2b6c04a6a6eb8546298eaff6a957e711fb68e53b532`):
    ```bash
    gh release download V6.4.1 -R zinja-coder/jadx-ai-mcp -p 'jadx-mcp-server-6.4.1.zip' -D ~/tools/downloads
    # zip 안의 jadx-mcp-server/ 폴더를 버전이 붙은 이름으로 옮깁니다.
    python3 -c "import zipfile,os; zipfile.ZipFile(os.path.expanduser('~/tools/downloads/jadx-mcp-server-6.4.1.zip')).extractall(os.path.expanduser('~/tools'))"
    mv ~/tools/jadx-mcp-server ~/tools/jadx-mcp-server-6.4.1
    cd ~/tools/jadx-mcp-server-6.4.1
    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python "fastmcp==3.0.2" "mcp==1.26.0" "httpx>=0.28.1" "requests>=2.32.3"
    ```
  * 실행(매번, 압축을 푼 디렉터리 안에서 실행해야 `src/`를 불러옴):
    ```bash
    cd ~/tools/jadx-mcp-server-6.4.1 && .venv/bin/python jadx_mcp_server.py --http
    ```
  * FastMCP는 시작 시 새 버전 확인을 위해 외부 네트워크에 접속합니다. 기능에는 영향이
    없으나 오프라인 환경에서 참고합니다.
* **클라이언트 SDK**: 공식 `mcp` Python SDK `2.2.0`을 사용하며 `uv.lock`으로 고정합니다
  (`pyproject.toml`에는 `mcp>=2.2.0`). 2.x는 1.x와 API가 다르므로(예: `server_info`,
  `is_error`처럼 snake_case 속성) 버전을 올릴 때는 클라이언트 테스트로 확인합니다.
* **접근과 인증**: 서버와 플러그인 모두 인증이 없습니다. 따라서 `jadx-mcp-server`는
  `--host 127.0.0.1`(기본값)을 유지하고 `0.0.0.0` 바인드를 사용하지 않습니다.
  * 플러그인은 바인드 주소를 바꿀 수 없어 `8650` 포트가 모든 인터페이스에 열리며(6.3),
    `rename_*` 같은 쓰기 기능도 HTTP GET으로 노출됩니다. 일반 Linux에서는 방화벽으로 외부
    접근을 막고(예: `sudo ufw deny 8650`) 신뢰할 수 있는 네트워크에서만 JADX-GUI를
    실행합니다.
* **서버 시작과 연결 상태**: `jadx-mcp-server`는 시작 시 플러그인 health check에 실패해도
  로그만 남기고 계속 실행됩니다. 즉 JADX-GUI가 꺼져 있어도 MCP 연결·초기화는 성공할 수
  있으며, 플러그인 연결 실패는 tool 호출 결과에서 드러납니다(5절 상태 표 참고).
* **실행 환경**: 세 구성요소를 같은 호스트에서 실행하고 `127.0.0.1`로 통신하는 구성을
  기준으로 합니다. JADX-GUI는 그래픽 세션이 필요합니다.
  * NuriLab은 MCP 서버 주소를 설정값으로 받으며, 실행 환경에 따른 코드 분기를 두지
    않습니다.
  * THE-154 검증은 개인 PC의 WSL2(Ubuntu 24.04) 안에서 세 구성요소를 모두 실행하고,
    JADX-GUI 창은 WSLg로 띄웠습니다(6.3).
* **JADX-GUI와 플러그인 설치(버전 고정)**: Java 11 이상(64비트)이 필요합니다.
  * JADX는 릴리즈 `v1.5.6`의 `jadx-1.5.6.zip`을 저장소 밖 `~/tools/jadx-1.5.6/`에 풀어
    사용합니다. `unzip`이 없는 환경을 고려해 Python `zipfile`로 풀며, `zipfile`은 실행
    권한을 보존하지 않으므로 `bin/` 스크립트에 실행 권한을 다시 줍니다.
  * 플러그인 설치에 README의 `jadx plugins --install "github:zinja-coder:jadx-ai-mcp"`는
    항상 최신 버전을 받으므로 사용하지 않고, `V6.4.1` 릴리즈 jar를 파일로 지정합니다.
    ```bash
    sudo apt install -y openjdk-17-jre
    gh release download v1.5.6 -R skylot/jadx -p 'jadx-1.5.6.zip' -D ~/tools/downloads
    python3 -c "import zipfile,os; zipfile.ZipFile(os.path.expanduser('~/tools/downloads/jadx-1.5.6.zip')).extractall(os.path.expanduser('~/tools/jadx-1.5.6'))"
    chmod +x ~/tools/jadx-1.5.6/bin/*
    gh release download V6.4.1 -R zinja-coder/jadx-ai-mcp -p 'jadx-ai-mcp-6.4.1.jar' -D ~/tools/downloads
    ~/tools/jadx-1.5.6/bin/jadx plugins --install-jar ~/tools/downloads/jadx-ai-mcp-6.4.1.jar
    ~/tools/jadx-1.5.6/bin/jadx plugins --list
    ```
  * 실행: `~/tools/jadx-1.5.6/bin/jadx-gui <apk 경로>`. 플러그인은 `8650` 포트에서
    대기합니다.

## 3. Tool과 테스트 입력 (완료 조건 2)

### 3.1 허용 tool

* **허용 목록은 `get_class_source` 하나**입니다. NuriLab 클라이언트는 이 외의 tool 이름을
  호출 전에 거부합니다.
* 허용 목록을 명시하는 이유: V6.4.1 서버의 tool 32개 중 `rename_class`, `rename_method`,
  `rename_field`, `rename_package`, `rename_variable`은 JADX 프로젝트 상태를 바꾸는 쓰기
  tool입니다. 플러그인 route가 모두 HTTP GET이라 요청 방식으로는 읽기 전용 여부를 구분할
  수 없습니다. `fetch_current_class`, `get_selected_text`는 GUI 선택 상태에 의존하고,
  `debug_get_stack_frames`, `debug_get_threads`, `debug_get_variables`는 디버거 상태에
  의존하므로 자동 실행에 부적합합니다. `clear_cache`는 서버
  캐시를 바꾸고, `get_cache_stats`는 분석 대상이 아닌 서버 상태를 돌려주므로 제외합니다.

**선정 기준**: THE-154·THE-155가 요구하는 검증을 하나의 tool로 모두 재현할 수 있어야
합니다.

1. 입력 하나로 조회 대상을 지정하고 기록·검증할 수 있다(입력 식별자, `invalid_input`).
2. 입력만 바꿔 성공과 실패(`not_found`)를 재현할 수 있다.
3. 응답이 15초 안에 끝나고, 응답 크기 제한(5.1)을 실제로 검증할 수 있을 만큼 클 수 있다.
4. 응답이 텍스트 하나로 와서 현재 판정 규칙(`{"response"}` / `{"error"}`)을 그대로 쓴다.

**사용 가능한 읽기 전용 후보와 판단** (V6.4.1 서버·플러그인 소스 기준)

| 분류 | tool | 입력 | 응답 | 판단 |
| --- | --- | --- | --- | --- |
| 클래스 단위 조회 | `get_class_source` | `class_name` | 디컴파일된 Java 소스 텍스트 | **선정**. 기준 1~4를 모두 충족 |
| | `get_smali_of_class` | `class_name` | smali 텍스트 | 기준은 충족하나 같은 클래스의 저수준 바이트코드 표현이라 Java 소스보다 사람이 확인하기 어려움 |
| | `get_methods_of_class`, `get_fields_of_class` | `class_name` | 메서드·필드 목록 텍스트 | 응답이 작아 크기 제한을 검증할 수 없음(기준 3) |
| 입력 없는 조회 | `get_main_activity_class`, `get_android_manifest` | 없음 | `{"name", "type", "content"}` JSON | 입력이 없어 `invalid_input`·`not_found`를 입력으로 재현할 수 없고(기준 1·2), 응답 형식이 달라 판정 규칙을 추가해야 함(기준 4) |
| | `get_package_tree`, `get_main_application_classes_names` | 없음 | 패키지·클래스 목록 JSON | 입력이 없고(기준 1·2) 구조화된 목록이라 판정 규칙이 다름(기준 4) |
| 목록·페이지 조회 | `get_all_classes`, `get_strings`, `get_all_resource_file_names`, `get_main_application_classes_code` | `offset`, `count` | 페이지 단위 목록(`count=0`이면 전체) | 응답 크기가 APK 크기에 비례하고 페이지 처리가 필요함(기준 3·4) |
| 여러 인자 조회 | `get_method_by_name`, `get_manifest_component`, `get_xrefs_to_class`, `get_xrefs_to_method`, `get_xrefs_to_field` | 2개 이상 또는 열거값·페이지 인자 | 텍스트 또는 페이지 목록 | 인자 조합별 검증과 귀속이 복잡해짐(기준 1) |
| | `get_resource_file` | `resource_name` | 리소스 내용 | 리소스 이름을 알려면 목록 조회가 먼저 필요하고, 바이너리 리소스는 텍스트로 오지 않음(기준 2·4) |
| 검색 | `search_classes_by_keyword`, `search_method_by_name` | 검색어 등 | 페이지 결과, 진행률 보고 | 서버 내부 제한이 최대 3600초라 15초 제한과 맞지 않음(기준 3) |

결론적으로 기준 1~4를 모두 충족하는 후보는 클래스 단위 조회 tool이며, 그중 응답 크기
검증이 가능하고 jadx의 핵심 결과물인 디컴파일 소스를 돌려주는 `get_class_source`를
선정했습니다.

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

* 이 dict는 `structuredContent`와 `content[0].text`(JSON 문자열)에 **모두** 담겨 옵니다
  (fastmcp 3.0.2 실측). FastMCP 버전에 따라 `structuredContent`가 빠질 수 있으므로
  클라이언트는 `structuredContent`를 우선 사용하고, 없으면 `text`를 JSON으로 파싱합니다.
  * 단, 서버가 tool의 outputSchema를 선언했는데 `structuredContent`가 없으면 MCP SDK
    검증이 먼저 실패해 `tool_error`(`call failed: RuntimeError: ...`)로 기록되며 `text`
    대체는 쓰이지 않습니다. V6.4.1 서버는 항상 `structuredContent`를 보내므로 해당하지
    않습니다.
* 위 표의 오류는 모두 `isError: false`로 옵니다. 반면 서버 측 인자 검증 실패(예: 필수
  인자 누락)는 `isError: true`와 JSON이 아닌 오류 문장만 `text`로 옵니다. 클라이언트는
  `isError: true`를 `tool_error`로 기록하고, jadx가 반환한 `tool_error`와 구분되도록
  `reason`을 `MCP tool error: <오류 문장>` 형식으로 담습니다.

### 3.4 테스트 입력

| 사례 | 준비 | `class_name` | 기대 결과 |
| --- | --- | --- | --- |
| 성공 | 직접 빌드한 무해 APK를 JADX-GUI에 로드 | 해당 앱의 `MainActivity` 전체 이름 (예: `com.nurilab.mcpprobe.MainActivity`) | `success` |
| 없는 클래스 | 같은 APK 로드 상태 | `com.nurilab.dummy.TestClass` | `not_found` |
| 연결 실패 | `jadx-mcp-server` 미실행 또는 JADX-GUI 종료 | 성공 사례와 동일 | `unavailable` |

* **무해 APK**: Android Studio에서 새 프로젝트(Empty Views Activity, Java)를 만들어
  수정 없이 빌드한 debug APK를 사용합니다. application ID는 `com.nurilab.mcpprobe`,
  성공 사례의 클래스는 `com.nurilab.mcpprobe.MainActivity`입니다. 사용한 APK의
  SHA-256은 6.3절에 기록합니다.
* APK 파일은 저장소에 커밋하지 않습니다. 생성 방법, application ID, 사용한 클래스 이름,
  APK SHA-256만 검증 기록에 남깁니다.
* 실제 악성 샘플이나 출처가 불분명한 외부 APK는 사용하지 않습니다.

## 4. 입력 차이와 결과 귀속 (완료 조건 3)

* **입력 차이**
  * Python 정적 분석: NuriLab이 로컬 경로의 `.py` 파일을 직접 읽어 분석합니다.
  * MCP 대상: 사람이 JADX-GUI에 연 APK입니다. NuriLab은 APK를 열 수 없고, V6.4.1에는
    현재 열린 파일을 알려주는 tool이 없어 어떤 APK가 열려 있는지 확인할 수 없습니다.
* **실행 방식**: MCP 호출은 입력 파일 형식과 무관하게 **명시적 CLI 옵션
  `--jadx-mcp-class`를 준 경우에만** 실행되는 별도 단계입니다. 옵션이 없으면 기존 동작과
  출력은 그대로입니다.
* **결과 귀속**
  * 사용자가 지정한 `class_name`과 대상 식별자(예: APK 파일명, SHA-256)를 결과와 함께
    기록합니다. 대상 식별자는 `--jadx-mcp-target`으로만 받으며, 주지 않으면 추측하지 않고
    비워 둡니다.
  * "JADX-GUI에 로드된 파일과 지정한 대상의 일치 여부는 NuriLab이 검증하지 않는다"는
    사실을 보고서에 명시합니다.
* **비지원 형식**: 입력 수집기는 현재 `.py` 외 파일을 skip하며 사유를 남깁니다. `.apk` 등
  비지원 형식에 대해 정적 분석 성공을 만들지 않으며, 보고서의 비지원 표시는 THE-155에서
  처리합니다.
* **결과 위치**: 기존 분석 결과(파일별 분석, 요약, risk, LLM review)와 분리된 별도 영역에
  기록합니다. 판정 결과로 오해되지 않도록 `findings`가 아닌 `external_tool_calls`라는
  이름을 사용합니다.
  * THE-154 구현: `AnalysisReport`와 `ProjectReport`의 `external_tool_calls` 필드에 호출
    기록을 담아 THE-155로 전달합니다. `to_dict()`에는 아직 포함하지 않으므로 JSON/HTML
    출력은 바뀌지 않습니다.
  * JSON/HTML에 표시하는 방식은 THE-155에서 정합니다.
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
| 연결 + initialize + tool 목록 확인 | 10초 | 초과 시 `timeout` |
| `get_class_source` 호출 | 15초 | 서버 내부 제한(60초)보다 짧게 두어 NuriLab이 먼저 중단. JADX 쪽 작업은 계속될 수 있음 |
| 응답 소스 크기 | 256 KiB (UTF-8 바이트) | 초과 시 앞부분 256 KiB만 보존하고 `truncated=true`, 원본 크기 기록 |
| 전송 한계 | 약 381 KiB (Java 형태 소스, 6.2 실측) | MCP SDK가 응답 이벤트를 1 MiB까지만 받고 서버가 소스를 이스케이프해 두 번 보내므로, 이를 넘는 소스는 받지 못해 `tool_error`(`call failed: MCPError: SSE stream ended without a response`)로 기록되고 원본 크기도 남지 않음. NuriLab에서 바꿀 수 없는 한계 |

### 5.2 출처(provenance) 기록 항목

| 항목 | 값 |
| --- | --- |
| `server_url` | 접속한 MCP endpoint |
| `server_name`, `server_version` | initialize 응답의 `serverInfo` 값 그대로. 실측 결과 `server_version`은 jadx 릴리즈가 아니라 FastMCP 버전(`3.0.2`)임 |
| `expected_release` | `jadx-ai-mcp V6.4.1` (설정값이며 서버가 검증해 준 값이 아님) |
| `tool` | `get_class_source` |
| `client_sdk` | `mcp <설치 버전>` |
| `target` | 사용자가 지정한 대상 식별자(`--jadx-mcp-target`), 없으면 비어 있음 |
| `arguments` | 서버에 보낸(또는 거부되어 보내지 않은) 인자. `{"class_name": "<클래스 이름>"}` |
| `content` | `success`일 때 받은 소스(비신뢰 데이터, 256 KiB 초과 시 절삭) |
| `status`, `reason` | 5.3 상태 값과 사유 |
| `called_at`, `duration_ms` | 호출 시각과 소요 시간 |
| `response_size_bytes`, `truncated` | 응답 크기와 절삭 여부 |

### 5.3 호출 상태 값

| `status` | 조건 |
| --- | --- |
| `success` | `response`가 비어 있지 않은 문자열 |
| `empty` | `response`가 빈 문자열 |
| `not_found` | `error`가 HTTP 404 |
| `unavailable` | MCP 서버 접속·initialize 실패, 서버가 허용 tool을 제공하지 않음(capability 확인 실패), 또는 `error`가 플러그인 연결 불가 |
| `timeout` | 클라이언트 제한 초과, 또는 `error`가 서버 측 시간 초과 |
| `tool_error` | 위에 해당하지 않는 `error`, 또는 MCP 결과가 `isError: true` |
| `malformed` | `response`와 `error`가 모두 없거나 형식이 예상과 다름 |
| `invalid_input` | `class_name` 검증 실패로 호출하지 않음 |
| `not_allowed` | 허용 목록 밖 tool 요청으로 호출하지 않음 |

`truncated`는 상태 값이 아니라 `success`에 붙는 별도 표시입니다.

`reason` 형식은 다음과 같습니다.

| 경우 | `reason` 예 |
| --- | --- |
| jadx가 돌려준 `error` | 서버 메시지 원문 (예: `Cannot connect to JADX plugin at ...`) |
| `isError: true` 결과 | `MCP tool error: <text>` (text가 없으면 `(no message)`) |
| 연결·호출 중 예외 | `connect failed: ConnectError: ...`, `call failed: <예외 종류>: <메시지>` |
| 클라이언트 제한 초과 | `connect exceeded 10s limit.`, `call exceeded 15s limit.` |
| capability 확인 실패 | `Server does not provide tool 'get_class_source'.` |

### 5.4 실패 경계 (Fail-safe)

* 모든 실패는 파이프라인 예외로 던지지 않고 `status`와 `reason`으로 기록합니다.
* 기존 정적 분석, Mock/Local LLM review, HTML/JSON 출력은 MCP 결과와 무관하게 그대로
  완료됩니다.
* 테스트용 가짜(fake) 클라이언트 결과는 실제 연결 증거로 쓰지 않습니다. 실제 연결 증거는
  6절의 실제 서버 실측 기록이며, 보고서 기반 반복 검증 기록은 THE-155에서 남깁니다.

## 6. THE-154 실측 기록

### 6.1 MCP 서버 단독 실측 (2026-09-30)

JADX-GUI 없이 `jadx-mcp-server`만 실행한 상태에서 curl로 MCP 요청을 보내 확인했습니다.
curl `initialize` 요청의 `protocolVersion`은 NuriLab 클라이언트와 같은 `2025-11-25`로
보냈습니다.

* 환경: 개인 PC의 WSL2(Ubuntu), 서버 전용 Python 3.12 가상환경
* 설치 버전: `fastmcp==3.0.2`, `mcp==1.26.0`, `httpx==0.28.1`, `requests==2.34.2`

| 항목 | 결과 |
| --- | --- |
| MCP endpoint | `http://127.0.0.1:8651/mcp` |
| 응답 방식 | SSE(`text/event-stream`), `mcp-session-id` 헤더로 세션 유지 |
| 합의된 프로토콜 버전 | `2025-11-25` (2절 버전 고정 조건에서 서버가 지원하는 최신) |
| `serverInfo` | name `JADX-AI-MCP Plugin Reverse Engineering Server`, version `3.0.2`(FastMCP 버전) |
| tool 목록 | 32개. `get_class_source` 입력 스키마 `{"class_name": string}`(필수), outputSchema는 object |
| 결과 전달 형태 | `structuredContent`와 `content[0].text` 모두 포함 |
| JADX-GUI 미실행 시 호출 | `{"error": "Cannot connect to JADX plugin at http://127.0.0.1:8650. ..."}`, `isError: false`, 약 0.06초 → `unavailable` |
| 필수 인자 누락 호출 | `isError: true`, `text`에 pydantic 검증 오류 문장, `structuredContent` 없음 → `tool_error` |

### 6.2 NuriLab 클라이언트 실측 (2026-09-30 ~ 2026-10-02)

6.1과 같은 서버에 NuriLab 클라이언트(`mcp 2.2.0`)로 접속해 확인했습니다. JADX-GUI는
실행하지 않았습니다.

| 확인 | 결과 |
| --- | --- |
| 합의된 프로토콜 버전 | `2025-11-25` |
| 실제 서버 통합 테스트 `NURILAB_RUN_JADX_MCP=1 uv run pytest tests/test_jadx_mcp_integration.py` | 3 passed (2026-10-02). 기본 호출은 `status=unavailable`, `server_version=3.0.2`, `client_sdk=mcp 2.2.0`. 연결·호출 제한을 극단적으로 줄인 두 테스트는 실제 SDK 연결에서도 각각 `timeout`으로 기록됨 |
| CLI `analyze ... --jadx-mcp-class com.nurilab.dummy.TestClass` | `JADX MCP get_class_source: unavailable - Cannot connect to JADX plugin at ...`, 종료 코드 0, JSON 최상위 키는 기존과 동일 |
| 서버가 없는 주소(`127.0.0.1:8659`) | `unavailable`, `connect failed: ConnectError: All connection attempts failed` |
| 응답 크기 한계 (2026-10-07, 같은 `fastmcp 3.0.2`로 띄운 임시 가짜 서버가 지정 크기의 소스를 반환) | 받을 수 있는 최대 소스: 순수 문자 약 512 KiB, Java 형태 텍스트 약 381 KiB. 그 이상은 `tool_error`. 상한 256 KiB 적용 후 300·380 KiB 소스는 `success`, `truncated=true`, 원본 크기 기록, 400 KiB는 `tool_error` |

### 6.3 JADX-GUI 연동 실측 (2026-10-06)

무해 APK를 JADX-GUI에 열고 3.4절의 테스트 입력을 실행했습니다.

* 환경: 개인 PC의 WSL2(Ubuntu 24.04.4), JADX-GUI는 WSLg 창으로 실행
* 버전: OpenJDK `17.0.20.1`, JADX `1.5.6`, 플러그인 `jadx-ai-mcp-6.4.1.jar`
  (SHA-256 `df7040ee4bc724c132635e8ad906b0961829db09a35da3365cbc46a761bed983`, 공식
  `V6.4.1` 릴리즈 파일과 동일), 서버·클라이언트는 6.1·6.2와 동일
* APK: `mcpprobe-debug.apk`(Empty Views Activity, Java, debug 빌드), application ID
  `com.nurilab.mcpprobe`, SHA-256
  `8d7c6b56f9f32dce4cfdf216e1c2b06bcfa52c036678d3be05f7d335634d4260`
* 플러그인 HTTP 서버는 `*:8650`(모든 인터페이스)에 바인드되었고 `/health`는 HTTP 200을
  반환했습니다.

| 사례 | 실행 | 결과 |
| --- | --- | --- |
| 성공 | CLI `--jadx-mcp-class com.nurilab.mcpprobe.MainActivity --jadx-mcp-target mcpprobe-debug.apk` | `success (1,573 bytes)`, 종료 코드 0. 받은 소스는 `package com.nurilab.mcpprobe;`로 시작하는 32줄, `truncated=false`, 약 0.2초 |
| 없는 클래스 | 같은 명령, `--jadx-mcp-class com.nurilab.dummy.TestClass` | `not_found - HTTP error 404: {"error":"Class com.nurilab.dummy.TestClass not found"}` |
| 연결 실패 | JADX-GUI 종료 후 성공 명령 | `unavailable - Cannot connect to JADX plugin at http://127.0.0.1:8650. ...`, 종료 코드 0 |
| 통합 테스트 | `NURILAB_RUN_JADX_MCP=1 NURILAB_JADX_MCP_CLASS=com.nurilab.mcpprobe.MainActivity uv run pytest tests/test_jadx_mcp_integration.py` | 3 passed. 기본 호출 `status=success`, `response_size_bytes=1573` |
| 기존 출력 보존 | 성공 실행의 JSON 보고서 | 최상위 키 `generated_at`, `analyzer_version`, `analysis`, `review`로 기존과 동일 |

### 6.4 남은 항목과 제한

* 절삭은 무해 APK의 클래스가 작아 jadx 실제 서버로는 재현하지 않았고, 실제 SDK 연결
  경로는 임시 가짜 서버로 확인했습니다(6.2). 단위 테스트는 가짜 session을 써서 전송
  단계를 거치지 않으므로 판정 규칙만 검증합니다.
* 약 381 KiB를 넘는 클래스 소스는 받을 수 없고 원인이 드러나지 않는 `tool_error`로
  남습니다(5.1). 보고서에서 이를 어떻게 안내할지는 THE-155에서 판단합니다.
