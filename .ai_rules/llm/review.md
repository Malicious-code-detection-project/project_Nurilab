# AI & Developer Guide: review.py
이 파일은 정적 분석에서 수집된 결정론적 신호(static signals)를 바탕으로 오프라인으로 모의 결과를 리턴하는 MockReviewClient와, 로컬 서빙 vLLM API를 호출하여 보다 정밀한 사람 친화적 요약, 위험도 산출 및 취약점 개선 패치 가이드를 제공하는 LocalLLMReviewClient 등 리뷰 비즈니스 로직을 담당합니다.

## 🤖 AI Agent Guidelines
- **인터페이스 제약**: 모든 리뷰 클라이언트는 `ReviewClient(Protocol)` 인터페이스 규약을 엄격히 만족해야 하며, `def review(self, analysis: PythonAnalysis | ProjectAnalysis) -> ReviewResult`의 매개변수 및 리턴 데이터 형태를 보존해야 합니다.
- **vLLM 서버 라이프사이클 관리 절대 금지**: 애플리케이션 프로세스 내부에서 `vllm serve`나 GPU 할당 프로세스를 시작, 제어, 종료하는 행위를 절대 수행하지 마십시오. vLLM 서버는 독립된 외부 백엔드로 완전히 분리하여 수동 실행되며, 본 모듈은 지정된 REST API 엔드포인트(`base_url`)로의 HTTP 요청 송수신에만 한정되어야 합니다.
- **오류 감내 제어 (Fault Tolerance)**: 외부 LLM API 요청 시 타임아웃, 네트워크 실패, API 오류 혹은 반환된 결과의 JSON 파싱 실패가 발생하더라도 파이프라인 전체가 즉시 비정상 중단(Crash)되지 않아야 합니다. 이 예외를 안전하게 포착하고 `ReviewResult`의 findings 내에 해당 실패 원인과 권장 조치사항(예: "Check if vLLM is running...")을 `ReviewFinding` 형태로 담아 정상 반환하십시오.
- **안티 패턴**:
  - LLM 모델에 프롬프트를 전송할 때 반환 결과로 마크다운 설명과 JSON이 복잡하게 섞여 나올 수 있으므로, `_extract_json_payload` 함수를 통한 정제 없이 바로 `json.loads`를 호출하는 코드를 작성하지 마십시오.

## 👨💻 Developer Context
- **오프라인 및 Mock의 중요성**: 로컬 LLM 서버가 오프라인이거나 사용 불가능한 상황에서도 테스트가 매끄럽게 통과할 수 있도록 `MockReviewClient`가 항상 최신 static signal 스키마를 완벽히 소화하여 완결성 있는 요약을 제공할 수 있도록 관리하십시오.
- **역할 및 판단 기준**: LLM은 보안 판단의 "해설자 및 보조 도구"이지 최종 절대 기준이 아닙니다. 엄격한 규칙 탐지와 결과 수치는 static analyzer의 결과와 schemas 계약을 근거로 삼아야 합니다. LLM은 탐지된 사항을 사람이 읽기 편하게 정리하고 개선책을 유추하는 용도로 프롬프트와 컨텍스트가 집중되도록 제어해 주십시오.
