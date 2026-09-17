# NuriLab 개인 하네스 호환 안내

> 보존용 호환 문서이며 현재 적용하지 않습니다. 이전 로컬 경로: `AGENTS_CODEX.md`. 개인 V3는 Git에 포함하지 않으며 아래 선택 경로가 없어도 공통 문서를 사용할 수 있습니다.

이 파일은 기존 개인 하네스 진입 경로를 위한 **로컬 호환 어댑터**다. 팀 규칙과
사용자 요청은 항상 [AGENTS.md](../../../AGENTS.md), [README.md](../../../README.md),
[docs/CONTRIBUTING.md](../../../docs/CONTRIBUTING.md), Linear `The Debugging Water Deer` /
`Nurilab`을 우선한다.

개인 V3 문서가 이번 작업에 명시된 경우에만
V3 진입점 (선택적 로컬 경로: `references/이정민/index.md`)을 읽는다. 설치·전역 설정·스크립트 생성이나
자동 모델 전환은 하지 않는다. 이 파일과 `docs/agents/`, `.agents/skills/`의 호환
문서는 사용자 `.gitignore`에 의해 로컬 상태일 수 있으며, 팀 정본을 대체하지 않는다.

현재 소스 진입점은 [main.py](../../../main.py), 핵심 모듈은
[project_nurilab/](../../../project_nurilab), 회귀 테스트는 [tests/](../../../tests)다. 작업 상태와
Phase는 문서의 고정 문구로 판단하지 말고 Linear 및 팀 정본에서 확인한다.

필요한 세부 절차는 V3의 작업 배분 (선택적 로컬 경로: `references/이정민/harness/routing.md`),
인수인계 (선택적 로컬 경로: `references/이정민/harness/handoff.md`),
검토 (선택적 로컬 경로: `references/이정민/harness/review.md`)를 따른다.
