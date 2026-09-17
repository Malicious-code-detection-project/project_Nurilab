# Project NuriLab 역사 기록

이 문서는 초기 README의 설계 가정과 발표 Q&A를 보존합니다. 과거 문서는 의사결정의
맥락을 보여 주는 기록이며 현재 지원 기능, 데이터 계약, 로드맵을 정의하지 않습니다.
현재 동작은 [`../README.md`](../README.md), [`ARCHITECTURE.md`](ARCHITECTURE.md),
source code와 test를 기준으로 확인합니다.

## 출처

- 초기 프로젝트 소개와 확장 설계: [commit `7d25cac`](https://github.com/Malicious-code-detection-project/project_Nurilab/blob/7d25cac86248b3a040273deea8982b42f102a419/README.md)
- 프로젝트 단위 정적 분석 README: [branch `feature/phase2-project-static-review`](https://github.com/Malicious-code-detection-project/project_Nurilab/blob/483c55a553b070d24021e6affff7b836657249e1/README.md)
- 발표 Q&A가 들어 있던 README: [commit `4456c66`](https://github.com/Malicious-code-detection-project/project_Nurilab/blob/4456c6680c0286951a550ee07830bf34db095cfa/README.md)
- 문서 통합 직전의 같은 Q&A 기록: [commit `7dc3ea4`](https://github.com/Malicious-code-detection-project/project_Nurilab/blob/7dc3ea4b86f01b74b25e85cdc838b7c51df7695f/README.md)

## 초기 목표와 현재 결정

초기 문서는 로컬 GPU에서 반복 분석 비용을 통제하고, 장기적으로 의심 파일과
악성코드 분석을 돕는 시스템을 지향했습니다. 현재도 로컬 우선, 정적 신호 우선,
분리된 LLM serving이라는 원칙은 유지합니다.

다음은 더 이상 현재 계약이 아닌 초기 가정입니다.

| 초기 기록의 가정 | 현재 결정 |
| --- | --- |
| 200줄 이하 Python 파일 한 개로 제한 | 줄 수 제한 없이 단일 파일과 디렉터리의 Python 파일을 분석 |
| RAG, Sandbox, UI/DB, PE/ELF, 자동 remediation을 확장 설계에 함께 제시 | 현재 구현 범위에서 제외. 번호가 지정된 현재 Phase의 기능도 아님 |
| SGLang과 vLLM을 동등한 현재 serving 후보로 제시 | 현재 Local review는 vLLM OpenAI-compatible API를 대상으로 함 |
| raw response를 실패 시 보존하는 확장 설계 | 별도 reasoning 필드는 사용하지 않음. JSON/schema 오류 진단에는 content의 최대 200자 preview가 남을 수 있음 |
| 모델·파인튜닝 전략을 저장소 로드맵에 포함 | 파인튜닝과 artifact는 별도 AegisLM 프로젝트의 책임. NuriLab은 endpoint 연동만 백로그에서 검토 |

현재 deterministic analyzer가 판단 근거이며 LLM은 해석·요약·우선순위·권고를
담당합니다. Local LLM 오류도 정적 분석을 지우지 않고 finding으로 보존합니다.

## 초기 확장 설계도

아래 이미지는 초기 README에 있던 개념 설계도입니다. 저장소의 원본 asset은 바꾸지
않았습니다.

![초기 개념 설계도 — 현재 구현이 아님](../images/ChatGPT%20Image%202026년%204월%2026일%20오후%2005_28_41.png)

당시 그림과 주변 설명에는 UI/DB, chunking, RAG, 넓은 파일 형식과 분석 단계가
포함되었습니다. 이는 현재 NuriLab의 module map이나 실행 흐름이 아닙니다. 현재
구현은 Python 정적 분석, 선택적 Ruff, Mock 또는 Local LLM review, HTML/JSON
report로 한정됩니다.

## 중간 발표 Q&A — 당시 원문

다음 네 문답은 [commit `4456c66`](https://github.com/Malicious-code-detection-project/project_Nurilab/blob/4456c6680c0286951a550ee07830bf34db095cfa/README.md)의 표현을 보존한 역사 기록입니다.
RAG, 벡터 DB, 파일 형식 확장, 파인튜닝 주기 등의 언급은 현재 구현 또는 확정된
로드맵을 뜻하지 않습니다.

### Q1. 새로운 악성코드가 생성되어 공격이 들어오면, 바로 파인튜닝할 것인가?

현재 방향은 **즉시 파인튜닝보다는 우선 축적, 이후 주기적 업데이트**입니다.

- 새 악성코드 샘플, IOC, 문자열, 행위 패턴, 분석 리포트 등은 먼저 벡터 DB 또는 지식 저장소에 축적
- 빠른 대응은 RAG, 룰, 검색 기반 참조로 처리
- 파인튜닝이나 모델 업데이트는 정제된 데이터셋을 기준으로 반기 또는 연 단위, 혹은 의미 있는 변화 시점에 수행

정리하면 다음과 같습니다.

- 실시간 반영: 벡터 DB, 룰, 지식베이스
- 주기 반영: 파인튜닝, 모델 업데이트, 재배포

### Q2. 현재는 Python AST 기반 정적 분석 중심인데, 프로젝트 이름처럼 악성코드 탐지 시스템으로 발전시키려면 PE/ELF/APK나 난독화 스크립트 분석 중 어느 방향을 우선 확장할 계획인가?

현재 방향은 **난독화 스크립트와 스크립트형 의심 코드 분석을 먼저 확장**하는 것입니다.

- 현재 구조가 Python 정적 분석 기반이기 때문에 확장 비용이 가장 낮음
- 문자열, 실행 흐름, 위험 호출, 난독화 패턴 분석이 기존 파이프라인과 자연스럽게 연결됨
- PE/ELF/APK는 포맷별 파서, 메타데이터, import/API, 섹션 구조 등 별도 분석 체계가 필요해 난이도가 더 높음

우선순위는 다음과 같습니다.

- 1차: Python 및 스크립트형 난독화/의심 코드 분석 확장
- 2차: PE/ELF 같은 실행 파일 정적 분석
- 3차: APK 등 플랫폼 특화 포맷 확장

### Q3. 현재 룰은 `eval`, `exec`, `os.system`, `pickle`, `yaml.load` 등 보수적인 위험 호출 중심인데, 오탐을 줄이면서 탐지 범위를 넓히기 위한 기준은 무엇인가?

핵심은 **룰 개수 확대보다 문맥 정보 강화**입니다.

- 단일 위험 호출 존재 여부만 보지 않음
- 외부 입력과 직접 연결되는지 확인
- 검증, 예외 처리, 격리 여부 같은 완화 요소를 함께 확인
- 여러 위험 신호를 조합해 우선순위와 위험도를 판단
- 새 룰 추가 전에는 검증 데이터셋으로 precision / recall을 확인

정리하면 다음과 같습니다.

- 탐지 범위 확장: 룰 추가
- 오탐 억제: 문맥 정보, 조합 규칙, 점수화

### Q4. 현재 구조에서는 정적 분석기가 deterministic signal을 만들고 LLM이 reviewer-facing summary를 생성하는 방식인데, 최종 판단 권한은 rule engine과 LLM 중 어디에 두는 것이 맞다고 보는가?

현재 방향은 **최종 판단 기준은 rule engine과 deterministic analyzer에 두고, LLM은 해석과 요약을 담당하도록 두는 것**입니다.

- rule 기반 결과는 재현 가능하고 검증 가능함
- 보안 영역에서는 판단 근거와 버전 관리가 중요함
- LLM은 설명, 우선순위화, 권고안 정리에는 강하지만 최종 판단 기준으로 두기에는 변동성이 있음

역할 분리는 다음과 같습니다.

- Rule Engine / Static Analyzer: 탐지 근거 생성, 위험 신호 식별, 기준점 제공
- LLM: 결과 요약, 사람 친화적 설명, 위험 해석, 권고안 정리

## 참고 프로젝트

초기 설계는 Gilbut의
[A2A × MCP 멀티에이전트 오케스트레이션 실전 / Code_Vulnerability](https://github.com/gilbutITbook/080493/tree/main/Code_Vulnerability)를
참고했습니다. 참고 프로젝트의 agent/MCP 구조는 NuriLab의 현재 구현이 아닙니다.
NuriLab의 MCP 계획은 별도 제한 도구를 위한 `THE-151 → THE-154 → THE-155` 작업으로
관리합니다.
