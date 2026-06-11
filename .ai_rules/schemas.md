# AI & Developer Guide: schemas.py
이 파일은 정적 분석 결과, 리뷰 발견 사항, 보고서 데이터 포맷 등 파이프라인 전반에서 통용되는 모든 공통 데이터 구조와 계약(Contract)을 정의하여 데이터 정합성을 유지하는 역할을 담당합니다.

## 🤖 AI Agent Guidelines
- **외부 유효성 검사 라이브러리 도입 금지 (Pydantic 금지)**: 가벼운 성능과 로컬 단일 실행 효율성을 위해 Pydantic 등 무거운 외부 유효성 검사 라이브러리를 임의로 추가하여 데이터 모델을 재선언하지 마십시오.
- **표준 라이브러리 데코레이터 강제**: 모든 데이터 모델은 표준 라이브러리인 `dataclasses`를 기반으로 정의해야 하며, 객체 생성 성능 최적화와 멤버 필드 고정을 위해 `@dataclass(slots=True)` 데코레이터를 엄격히 적용해야 합니다.
- **직렬화 기능 제공**: 모델을 JSON이나 HTML 템플릿에 편리하게 바인딩할 수 있도록, 주요 최상위 데이터 클래스(`PythonAnalysis`, `ReviewResult`, `AnalysisReport`, `ProjectAnalysis`, `ProjectReport`)에는 명시적인 `to_dict() -> dict[str, Any]` 메서드가 필수적으로 구현되어야 합니다.
- **안티 패턴**: 클래스 멤버 필드를 타입 힌트 없이 선언하거나 `Any`를 남용하여 구조적 명확성을 해치지 마십시오. 리스트 타입 필드는 반드시 기본 팩토리(`field(default_factory=list)`)를 사용하여 안전하게 초기화해야 합니다.

## 👨💻 Developer Context
- **데이터 모델 변경 영향도 분석**: 이 모듈은 데이터의 직렬화(JSON)와 렌더링(HTML/MD Reports)은 물론, 테스트 코드의 Mock 데이터와도 강력히 결합되어 있습니다. 따라서 신규 필드 추가나 필드 타입 수정 등의 구조 변경 시에는 연동되어 있는 리포트 생성기(`reports/generator.py`)와 전체 테스트 파일에 영향이 가는지 사전에 철저히 검사해야 합니다.
- **일관성 있는 카테고리 구성**: `SuspiciousCall` 및 `SecretFinding` 등의 하위 필드 데이터 모델들이 static analyzer에 의해 일관되게 주입되는지 구조적 타입을 항상 정렬해 두십시오.
