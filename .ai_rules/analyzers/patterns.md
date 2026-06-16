# AI & Developer Guide: patterns.py
이 파일은 정적 분석 중 AST 파서가 의심해야 할 위험한 파이썬 기본 함수 호출(예: eval, exec, subprocess.run 등)의 정의, 탐지 사유 및 심각도 등 결정론적 탐지 룰 상수를 통합 정의하고 관리하는 사전(Dictionary) 역할을 담당합니다.

## 🤖 AI Agent Guidelines
- **데이터 구조 유지**: 
  - 각 룰은 반드시 `@dataclass(frozen=True, slots=True)` 데코레이터를 적용한 `SuspiciousCallRule` 클래스의 규격을 따라야 합니다.
  - 전체 의심 호출 데이터는 `SUSPICIOUS_CALL_RULES: dict[str, SuspiciousCallRule]` 형식으로 관리되어야 하며 키는 탐지 대상 함수명(예: `eval`, `os.system`)이어야 합니다.
- **기본 위험 규칙 보호**: `eval`, `exec`, `compile`, `os.system`, `subprocess.run`, `subprocess.Popen`, `pickle.load`, `pickle.loads`, `yaml.load` 등 런타임 공격 및 원격 코드 실행(RCE) 위험을 동반하는 파이썬 코어 API 호출에 대한 기본 룰을 사전에서 임의로 삭제해서는 안 됩니다.
- **안티 패턴**: 룰 딕셔너리 내에 비즈니스 분석 로직이나 복잡한 동적 판별 함수를 매핑하지 마십시오. 이 모듈은 오직 정적 상수를 관리하는 데이터 스토어 역할에 집중해야 합니다.

## 👨💻 Developer Context
- **룰 추가 기준 및 정밀도(Precision)**: 새로운 함수나 메소드 호출을 의심 호출 패턴으로 등록하기 전에는, 실제 탐지 범위를 넓히면서 발생할 오탐률의 증가 추이를 충분히 검토해야 합니다. 무분별한 룰 추가는 개발자가 보고서 결과를 불신하게 만들 수 있습니다.
- **안전 완화 요소의 배제**: 이 모듈에 작성되는 룰 상수는 단순 호출을 감지하기 위한 고정 데이터입니다. 해당 호출이 내부적으로 안전하게 샌드박싱되어 실행되는지 혹은 외부 입력값이 주입되는지에 대한 '문맥적인 판단'은 정적 분석이나 LLM 단계에서 유추하도록 설계해야 합니다.
