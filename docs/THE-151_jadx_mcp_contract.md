# [THE-151] jadx-ai-mcp 연결 환경·입력·tool 계약 확인

## 1. 개요
본 문서는 Project NuriLab에 외부 Android 정적 분석 도구인 `jadx-ai-mcp`를 통합하기 위한 최소 연결 계약 및 사전 확인 사항을 정의합니다. (Linear Issue: THE-151)
본 설계는 향후 THE-154(클라이언트 연결) 및 THE-155(보고서 통합) 구현의 기준선이 됩니다.

## 2. 환경 및 연동 구성요소 (완료 조건 1)
* **설치/실행 전제**:
  * JADX-GUI 프로그램이 백그라운드에 실행 중이어야 하며, `jadx-ai-mcp` 플러그인이 로드되어 있어야 함.
  * Python 기반의 `jadx-mcp-server`가 NuriLab과 동일한 환경에 설치되어 실행 가능해야 함.
* **선택할 타겟 버전**: **`jadx-ai-mcp` v6.4.1** (해당 릴리즈 버전을 기준으로 호환성 보장)
* **연동 구성요소**: NuriLab (MCP Client) ↔ `jadx-mcp-server` (Python) ↔ `jadx-gui` (HTTP)
* **Transport 방식**: NuriLab 프로세스가 `jadx-mcp-server`를 Subprocess로 실행하여 **STDIO(표준 입출력)** 방식으로 통신함.
* **접근 주소 및 인증**: 로컬 통신이므로 별도의 네트워크 인증(API Key 등)은 불필요함. 현재 로컬 환경에 JADX-GUI가 켜져 있지 않으면 즉각적인 '연결 불가(Connection Refused)' 상태로 간주함.

## 3. Tool 및 테스트 입력 선정 (완료 조건 2)
사용자의 GUI 개입(화면 드래그, 클릭 등)이 필요한 Tool은 자동화 파이프라인에 부적합하므로 제외하며, 입력값만으로 결과를 반환하는 읽기 전용 Tool을 선정함.

* **선정된 Tool**: `get_class_source` (특정 클래스의 전체 Java 소스 코드를 가져오는 Tool)
* **입력 Schema (Request)**:
  ```json
  {
    "class_name": "string"
  }
  ```
* **응답 Schema (Response)**:
  ```json
  {
    "content": [
      {
        "type": "text",
        "text": "<java_source_code_string>"
      }
    ]
  }
  ```
* **무해한 테스트 입력 선정**: `"com.nurilab.dummy.TestClass"`
  * 실제 악성 앱이나 코드가 아니더라도, Tool이 파이프라인 상에서 예외 없이 빈 문자열이나 "Class not found"를 반환하는지 테스트하기 위한 더미(Dummy) 문자열.

## 4. 정적 분석 입력 차이 및 결과 귀속 정책 (완료 조건 3)
* **입력 매핑의 한계**: NuriLab은 현재 `.py` 파일의 AST 분석에 맞춰져 있으며, JADX는 안드로이드 앱(APK/Java) 클래스 분석에 맞춰져 있음.
* **결과 귀속 및 출력 방식**:
  * JADX에서 반환된 Java 코드를 NuriLab의 기존 Python AST 파이프라인에 억지로 통과시키지 않음(새 analyzer 확장 금지 규칙 준수).
  * JADX 호출 결과는 NuriLab의 전체 `ProjectAnalysis` 내에 독립적인 **`external_mcp_findings`** (또는 이와 유사한 필드) 영역을 신설하여 별도로 귀속시킴.
  * 미지원 파일(예: `.apk`)이 입력된 경우 "정적 분석 성공"으로 위장하지 않고, Python 분석은 `skipped` 처리하되 JADX 결과만 표출되도록 상태를 명확히 분리함.

## 5. 제한 사항 및 보고서 경계 정의 (완료 조건 4)
외부 프로세스 의존성으로 인한 NuriLab 파이프라인 붕괴를 방지하기 위해 다음과 같은 제약과 방어선을 설정함.

* **호출 타임아웃 (Timeout)**: **15초**
  * JADX 측에서 디컴파일이 지연되거나 무한 루프에 빠질 경우 NuriLab 분석이 멈추는 것을 방지함.
* **입력/응답 크기 제한**: 응답 Payload 최대 **1MB**.
  * 1MB 초과 시 앞부분만 남기고 절삭(Truncation) 처리하며, 보고서에 `truncated=true` 메타데이터를 명시함.
* **출처(Provenance) 식별자**:
  * `server`: "jadx-mcp-server"
  * `tool`: "get_class_source"
  * `version`: "v6.4.1" (선택된 타겟 릴리즈 버전으로 고정 명시)
* **실패 상태 경계 (Fail-safe)**:
  * 발생 가능한 오류(서버 미실행, 타임아웃, 비정상 JSON 반환 등)는 파이프라인의 `Exception`으로 던지지 않음.
  * 오류 발생 시 HTML/JSON 보고서에 `status: failed`, `reason: <오류_상세_메시지>`의 형태로 안전하게 기록된 후, 남은 파이프라인(Python 리뷰 등)이 정상적으로 마무리되도록 함.
