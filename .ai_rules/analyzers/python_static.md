# AI & Developer Guide: python_static.py
이 파일은 로드된 파이썬 소스 코드의 문자열 및 라인 정보를 바탕으로 AST(Abstract Syntax Tree)를 파싱하고 순회(Traversal)하여 임포트 구조, 함수/클래스 정의, 위험한 호출 및 하드코딩된 시크릿 패턴을 탐색하여 결정론적 신호(deterministic signal)를 추출하는 정적 분석的核心 역할을 담당합니다.

## 🤖 AI Agent Guidelines
- **관심사 분리 (Separation of Concerns) 엄격 준수**: 분석 제어 흐름 및 예외 처리를 전담하는 외부 인터페이스인 `PythonStaticAnalyzer` 클래스와 실제 AST 노드를 순회하며 탐지 로직을 수행하는 내부 `_PythonSignalVisitor` (또는 개별 전용 Visitor) 클래스의 물리적 및 논리적 분리 구조를 철저히 유지해야 합니다.
- **클래스 및 메서드 제약 사항**:
  - `PythonStaticAnalyzer.analyze(self, loaded_file: LoadedPythonFile) -> PythonAnalysis`의 명시적 시그니처와 반환 타입을 절대 어겨서는 안 됩니다.
  - AST 노드를 순회할 때 `ast.NodeVisitor` 클래스를 상속받아 `visit_Call`, `visit_Import` 등 표준 명명 규칙(`visit_NodeName`)을 오버라이딩하십시오.
- **예외 복구성**: AST 파싱(`ast.parse`) 중 Python `SyntaxError`가 발생하더라도 애플리케이션이 크래시되지 않아야 합니다. 예외 발생 시 `PythonAnalysis` 객체의 `syntax_error` 필드에 포맷팅된 오류 정보(`_format_syntax_error`)를 담아 정상 반환하도록 예외 제어를 설계하십시오.
- **안티 패턴**: 노드 방문 로직 내부에서 복잡한 파일 I/O 작업을 직접 수행하거나 외부 네트워크 API를 호출하여 상태를 확인해서는 안 됩니다. 순수 정적 AST 분석에만 집중하십시오.

## 👨💻 Developer Context
- **오탐(FP) 관리 및 문맥 제공**: 이 모듈에서 추출된 위협 신호(예: `SuspiciousCall`)는 최종적인 "악성 판정"을 내리는 것이 아닙니다. 이 신호들은 후속 단계인 LLM 리뷰어가 안전성을 문맥적으로 파악하고 정밀 분석할 수 있도록 돕는 "설명 가능한 결정론적 데이터(deterministic signal)"를 빌딩하는 것을 우선 과제로 삼습니다.
- **Visitor 확장성**: 분석 대상을 확장하거나 신규 AST 노드 패턴 탐지가 필요한 경우, `_PythonSignalVisitor`에 새 `visit_*` 핸들러를 추가하거나, 상속 계층을 준수하여 구현해 주십시오.
- **테스트 커버리지**: AST 분석 로직을 변경한 경우, `tests/test_python_static_analyzer.py`에 다양한 신규 및 엣지 케이스 소스 코드 예시를 추가하여 기존 기능이 깨지지 않는지 보장해 주십시오.
