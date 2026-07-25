# Project NuriLab 문서 지도

이 디렉터리는 Project NuriLab의 현재 운영 문서, 검증 기록, 참고 자료, 과거 계획을
보관합니다.

## 정본과 역할

확인하려는 내용에 따라 다음 정본을 사용합니다.

1. Source code와 test는 현재 동작과 데이터 계약을 증명하는 실행 가능한 정본입니다.
2. `README.md`는 지원 범위와 실행 방법에 대한 사용자 계약입니다.
3. `AGENTS.md`는 저장소 협업 규칙과 품질 gate의 정본입니다.
4. `docs/CONTRIBUTING.md`는 팀원의 실제 작업 절차를 정의합니다.
5. Linear `Nurilab` 프로젝트는 현재 작업 상태의 정본입니다.
6. GitHub Pull Request는 리뷰와 병합 이력의 정본입니다.

과거 계획과 참고 자료는 현재 제품 및 협업 문서를 덮어쓰지 않습니다. 문서와 코드가
다르면 현재 동작은 source code와 test로 확인하고, 같은 이슈에서 사용자 문서를
갱신합니다.

## 문서 언어 정책

현재 운영 문서의 정본 언어는 **한국어**입니다.

- `README.md`, `AGENTS.md`, `docs/README.md`,
  `docs/CONTRIBUTING.md`, PR/Issue template은 한국어로 작성합니다.
- CLI option, command, class/function name, 환경변수, JSON field, error title,
  공식 제품명은 코드 및 외부 계약과 일치하도록 영문을 유지합니다.
- 기술 용어를 억지로 번역해 의미가 흐려지는 경우 영문 용어를 본문 안에서 그대로
  사용하고 필요한 설명만 한국어로 작성합니다.
- 영문 전체 문서는 실제 외부 독자가 있거나 별도 프로젝트 전달 과정에서 독립적인
  영문 문서가 필요한 경우에만 추가합니다.
- 한글/영문 병행본을 유지할 때는 한글 문서를 정본으로 하고 영문 파일에는
  `.en.md` suffix를 사용합니다.
- 병행본은 같은 Pull Request에서 함께 갱신합니다. 동시에 갱신하지 못하면 영문
  문서 첫머리에 번역 기준 commit과 stale 여부를 표시합니다.
- live issue 상태를 Markdown에 복사하지 않고 Linear에서 관리합니다.

현재 병행 예외:

- `FINETUNING_EXPERIMENT_PLAN.md`: 팀 공유용 한글 정본
- `FINETUNING_EXPERIMENT_PLAN.en.md`: 별도 파인튜닝 프로젝트 전달용 영문 병행본
- `AI_RULES.md`, `AI_RULES_KOR.md`: `AGENTS.md`로 대체된 과거 영문/한글 기록

## 현재 운영 문서

| 문서 | 역할 |
| --- | --- |
| [`../README.md`](../README.md) | 제품 범위, 아키텍처, CLI, Local LLM 동작, 한계 |
| [`../AGENTS.md`](../AGENTS.md) | 사람과 코딩 에이전트가 따르는 저장소 규칙 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Linear 이슈, 브랜치, 검증, PR, 완료 처리 절차 |
| [`PR_DESCRIPTION.md`](PR_DESCRIPTION.md) | 상세 PR 본문 작성 template |
| [`PLAN.md`](PLAN.md) | 현재 Phase 순서, 목표, 종료 조건을 정의하는 개발 로드맵 |
| [`../.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) | GitHub 기본 PR form |
| [`../.github/ISSUE_TEMPLATE/task.md`](../.github/ISSUE_TEMPLATE/task.md) | Owner가 요청한 경우에만 사용하는 legacy GitHub Issue form |

## 검증 및 연동 기록

| 문서 | 현재 상태 |
| --- | --- |
| [`external_project_validation.md`](external_project_validation.md) | 실행 절차와 과거 결과를 함께 보관합니다. 최신 `main`에서 재실행하기 전에는 현재 검증 근거로 사용하지 않습니다. |
| [`SGLANG_VLLM_COMPARISON.md`](SGLANG_VLLM_COMPARISON.md) | 개념 비교 참고 자료이며 현재 benchmark나 dependency 계약이 아닙니다. |
| [`FINETUNING_EXPERIMENT_PLAN.md`](FINETUNING_EXPERIMENT_PLAN.md) | 별도 파인튜닝 프로젝트로 전달할 한글 계획입니다. |
| [`FINETUNING_EXPERIMENT_PLAN.en.md`](FINETUNING_EXPERIMENT_PLAN.en.md) | 별도 프로젝트 및 외부 도구 맥락을 위한 영문 병행본입니다. |

## 과거 및 대체된 문서

| 문서 | 현재 상태 |
| --- | --- |
| [`AI_RULES.md`](AI_RULES.md) | `AGENTS.md`로 대체된 과거 영문 AI 지침입니다. |
| [`AI_RULES_KOR.md`](AI_RULES_KOR.md) | `AGENTS.md`로 대체된 과거 한글 AI 지침입니다. |

과거 문서는 의사결정 이력을 보존하기 위해 유지합니다. 출처, 상태 표시, 깨진 링크,
위험한 지침을 바로잡는 경우를 제외하고 과거 내용을 현재 기준으로 덮어쓰지 않습니다.
현재 동작은 `README.md`, `AGENTS.md`, test, source code에 기록합니다.

## 문서 변경 규칙

- 지원 동작, CLI option, 환경변수, 출력, 사용자에게 보이는 한계가 바뀌면
  `README.md`를 갱신합니다.
- 협업 정책이나 필수 검증이 바뀌면 `AGENTS.md`를 갱신합니다.
- 팀 작업 절차가 바뀌면 `CONTRIBUTING.md`를 갱신합니다.
- 실험 및 검증 결과에는 Project NuriLab commit, 대상 commit, 환경, 명령어,
  날짜를 함께 기록합니다.
- 이후 코드 변경으로 기존 결과의 가정이 무효가 되면 해당 기록을 과거 결과로
  명시합니다.
- 정본 규칙을 여러 문서에 반복하기보다 다른 문서에서 정본을 링크합니다.
- 문서를 이동하거나 이름을 바꾼 뒤에는 내부 Markdown link를 검증합니다.
