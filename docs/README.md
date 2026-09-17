# Project NuriLab 문서 지도

현재 운영 문서, 검증 기록, 과거 설계를 역할별로 구분합니다. 처음 방문한 독자는
[루트 README](../README.md)의 배경·현재 기능·구성도·빠른 시작부터 읽습니다.

## 정본과 역할

| 알고 싶은 것 | 정본 |
| --- | --- |
| 실제 동작과 데이터 계약의 근거 | 소스 코드와 테스트 |
| 프로젝트 소개·지원 범위·현재 구성·빠른 시작 | [README](../README.md) |
| 상세 CLI 옵션·Local LLM 설정·오류 동작 | [사용 가이드](USAGE.md) |
| 상세 실행 흐름·모듈 책임·데이터 및 실패 경계 | [아키텍처](ARCHITECTURE.md) |
| 현재 개발 범위와 의존성 | [실행 계획](PLAN.md) |
| 협업 규칙과 품질 검사 | [AGENTS](../AGENTS.md) |
| 이슈·브랜치·검증·PR 절차 | [기여 가이드](CONTRIBUTING.md) |
| 실제 진행 상태·담당자 | [Linear Nurilab](https://linear.app/the-debugging-water-deer/project/nurilab-0225bf5ed619) |
| 리뷰와 병합 이력 | [GitHub Pull Requests](https://github.com/Malicious-code-detection-project/project_Nurilab/pulls) |

## 검증·협업 문서

| 문서 | 역할 |
| --- | --- |
| [외부 프로젝트 검증](external_project_validation.md) | 실행 절차와 당시 코드·대상 버전에 대한 검증 기록 |
| [Local LLM 통합 테스트](LOCAL_LLM_INTEGRATION_TEST.md) | 실제 서버 선택형 테스트와 당시 환경·결과 |
| [PR 작성 참고](PR_DESCRIPTION.md) | PR 본문 설명 |
| [PR 양식](../.github/PULL_REQUEST_TEMPLATE.md) | GitHub 기본 PR form |
| [Legacy Issue 양식](../.github/ISSUE_TEMPLATE/task.md) | Owner가 요청할 때 쓰는 GitHub Issue 양식; 상태 정본은 Linear |

과거 검증 결과를 현재 환경에서도 실행한 증거로 사용하지 않습니다. 실제 서버 검증은
모델·버전·환경·명령·날짜와 함께 읽으며 Mock 테스트와 구분합니다.

## 참고·과거 자료

| 문서 | 현재 적용 상태 |
| --- | --- |
| [설계 이력](HISTORY.md) | 초기 설계·이미지·발표 Q&A와 출처 커밋; 현재 기능이나 개발 약속이 아님 |
| [SGLang/vLLM 비교](SGLANG_VLLM_COMPARISON.md) | 개념 참고 자료; 현재 benchmark나 지원 보장이 아님 |
| [파인튜닝 과거 계획](FINETUNING_EXPERIMENT_PLAN.md) / [English](FINETUNING_EXPERIMENT_PLAN.en.md) | 별도 프로젝트의 이전 실험 구상; 현재 방향은 재검토 중 |
| [공유 참고 지도](../references/README.md) | 공통 참고와 선택적 개인 자료 구분 |
| [하네스 보관 목록](../references/harness/README.md) | 이전 AI_RULES 및 로컬 호환 문서의 출처·상태·이동 경로 |

프로젝트의 `AGENTS.md`와 `.ai_rules/`는 현재 위치를 유지합니다. 개인
`references/이정민/`와 로컬 skill은 Git에 포함하지 않으며 공유 문서를 읽기 위한
필수 의존성이 아닙니다.

`.ai_rules/`에는 이전 Phase 문구가 남아 있을 수 있습니다. 현재 범위와 충돌하는
지시는 적용하지 않고 최신 사용자 결정·AGENTS·실행 계획을 우선합니다.

## 언어와 유지보수 정책

- 현재 운영 문서는 한국어를 정본으로 작성합니다. 코드 식별자·CLI option·환경변수·
  JSON field와 공식 제품명은 실제 계약과 같은 표기를 사용합니다.
- 영문 전체 문서는 별도 독자나 전달 목적이 있을 때만 추가합니다. 한·영 병행본은
  같은 PR에서 갱신하며 미동기화 시 기준 commit과 오래된 상태를 명시합니다.
- 파인튜닝 한·영 파일과 보관된 AI_RULES 한·영 파일은 기존 병행본으로 보존합니다.
- README의 요약을 줄일 때는 세부 정보의 이동 위치와 링크를 함께 남깁니다.
  배경·현재 구성도·모듈 역할·빠른 시작·결과물·제약·참고 출처는 유지합니다.
- 과거 기록에는 출처와 적용 당시의 조건을 남깁니다. 현재 범위와 충돌하면 역사
  문서에서 차이를 설명하고, 과거 원문을 현재 지침으로 덮어쓰지 않습니다.
- 실제 상태는 Linear에서 관리합니다. 문서 이동 시 상대 링크·anchor·이미지를 검사하고
  개인 로컬 파일이 없는 checkout에서도 공유 문서를 확인합니다.
