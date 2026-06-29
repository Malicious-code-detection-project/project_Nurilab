# AGENTS.md - Project NuriLab Collaboration Manual

이 문서는 Project NuriLab 저장소에서 코드를 작성하는 모든 주체가 따르는 협업 운영 규칙이다. 사람, Claude Code, 웹 Claude+GitHub, Cursor, 기타 코딩 에이전트는 이 문서를 기준으로 작업한다.

작업은 GitHub Issue와 Pull Request를 중심으로 진행한다. 작업자는 자유롭게 이슈를 선택할 수 있지만, Phase 3 범위, 의존성 순서, 브랜치/커밋/PR 네이밍 규칙은 반드시 지킨다.

PR 리뷰와 최종 병합 판단은 Repository Owner가 담당한다.

---

## 1. 시작 전 필독 - SSOT 지도

| 알고 싶은 것 | 정본 위치 |
| --- | --- |
| 프로젝트 소개, 현재 Phase, 실행 방법 | `README.md` |
| 팀 기여 절차, 브랜치, 커밋, 테스트 규칙 | `docs/CONTRIBUTING.md` |
| 에이전트/개발자 공통 운영 규칙 | `AGENTS.md` |
| SGLang과 vLLM 비교 | `docs/SGLANG_VLLM_COMPARISON.md` |
| PR 본문 작성 참고 템플릿 | `docs/PR_DESCRIPTION.md` |
| PR 작성 형식 | `.github/PULL_REQUEST_TEMPLATE.md` |
| 작업 이슈 작성 형식 | `.github/ISSUE_TEMPLATE/task.md` |
| 코드 구조 | `project_nurilab/` |
| 테스트 | `tests/` |

**규칙 0 - 현황을 단정하기 전에 동기화한다.**

작업 전에는 로컬 브랜치와 원격 상태를 확인한다.

```bash
git fetch origin
git status
```

로컬 상태가 뒤처진 채로 "없다", "미구현이다", "충돌 없다"라고 단정하지 않는다.

---

## 2. 프로젝트 방향

이 프로젝트는 로컬 환경에서 동작하는 LLM 기반 악성코드/의심 파일 분석 자동화 시스템이다.

현재 Phase 3의 우선순위는 다음과 같다.

- Local LLM 리뷰 품질 개선
- 외부 실제 Python 프로젝트 대상 분석 안정성 검증
- 파일 길이 제한 제거에 따른 대용량 소스 분석 흐름 정리
- 프로젝트 단위 결과 집계 및 보고서 가독성 개선
- 실제 운영 환경 기준의 Local LLM 연동 안정성 개선

현재 Phase 3 범위를 넘는 항목은 즉시 구현하지 않고 README의 `Phase Next`로 보낸다.

- 파인튜닝
- remediation snippet
- 파일 전체 patched code 생성
- Python 외 언어 지원
- 멀티모달 입력
- 실제 악성 샘플 실행 또는 동적 분석

---

## 3. 작업 선택 규칙

작업은 자유롭게 선택하되, 다음 순서를 지킨다.

```text
Issue 정리
-> 입력/스키마/인터페이스 영향 확인
-> deterministic analyzer 또는 pipeline 변경
-> Mock 경로 검증
-> Local LLM 경로 검증
-> HTML/JSON 보고서 확인
-> 테스트/문서 갱신
```

착수 전 체크리스트:

- [ ] GitHub Issue 또는 PR에서 작업 목적이 분명한가?
- [ ] 같은 작업을 다른 사람이 진행 중이지 않은가?
- [ ] Phase 3 범위에 맞는가?
- [ ] 스키마, CLI, 보고서 출력에 영향이 있는가?
- [ ] 영향이 있다면 테스트와 문서 갱신 계획이 있는가?

의존성이 있는 작업은 상위 작업을 먼저 끝낸다.

- 입력 수집 변경 전: `input/`과 `schemas.py` 영향 확인
- analyzer 변경 전: `tests/test_python_static_analyzer.py` 영향 확인
- Local LLM 변경 전: Mock 경로와 실패 처리 유지
- report 변경 전: HTML + JSON 기본 출력 유지

---

## 4. 네이밍 표준

모든 브랜치, 커밋, PR은 작업 목적을 드러내야 한다.

| 대상 | 형식 | 예시 |
| --- | --- | --- |
| 브랜치 | `<type>/phase3-<topic>` | `feat/phase3-local-llm-quality` |
| 버그 브랜치 | `fix/<topic>` | `fix/local-llm-json-parser` |
| 문서 브랜치 | `docs/<topic>` | `docs/team-collaboration-rules` |
| 실험 브랜치 | `experiment/<topic>` | `experiment/gpt-oss-review` |
| 커밋 | `<type>: <요약>` | `feat: improve local llm review prompt` |
| PR 제목 | `[Phase 3] <요약>` | `[Phase 3] Improve local LLM review quality` |

`<type>`은 다음 중 하나를 사용한다.

- `feat`
- `fix`
- `docs`
- `test`
- `refactor`
- `chore`
- `experiment`

커밋 메시지는 Conventional Commits 형식을 권장한다.

---

## 5. 개발 가드레일

**Must Do**

- 작은 단위로 변경한다.
- 핵심 로직은 `project_nurilab/` 내부 모듈에 둔다.
- CLI 진입점은 얇게 유지한다.
- public 함수와 주요 데이터 모델에는 타입 힌트를 유지한다.
- 기능 변경에는 테스트를 추가하거나 기존 테스트를 갱신한다.
- 사용자 실행 흐름이나 출력이 바뀌면 README 또는 관련 문서를 갱신한다.

**Must Not**

- 실제 악성 샘플, secrets, 민감 데이터를 커밋하지 않는다.
- `main`에 직접 push하지 않는다.
- Local LLM 서버를 앱 내부에서 자동 실행하지 않는다.
- Ruff를 핵심 파이프라인의 필수 조건으로 만들지 않는다.
- LLM 응답을 최종 판단 기준으로 삼지 않는다.
- Phase Next 항목을 논의 없이 Phase 3 구현에 섞지 않는다.
- 지정된 타겟 파일 외의 다른 파일을 임의로 변경하지 않는다. (예: `ruff format .`이나 `ruff check --fix .` 처럼 프로젝트 전체에 걸쳐 자동 정렬/수정 명령을 실행하여 무관한 파일들의 스타일을 일괄 변경하는 행위를 금지하며, 일괄 적용된 경우 반드시 타겟 외 파일들은 되돌려서(Revert) 배제해야 한다.)

**판단 기준**

- deterministic analyzer와 rule signal이 판단 기준이다.
- LLM은 요약, 해석, 우선순위화, 권고안 생성을 담당한다.
- LLM 서버 오류나 JSON 파싱 실패는 pipeline 실패가 아니라 report finding으로 남긴다.

**Local LLM 작업 기준**

- Mock review는 기본 회귀 검증 경로이며 Local LLM 서버 없이 동작해야 한다.
- Local LLM review는 `--review-client local`을 명시한 경우에만 이미 실행 중인 vLLM OpenAI-compatible API를 호출한다.
- Local LLM 관련 변경은 `tests/test_tools_and_llm.py`, `tests/test_pipeline.py`, `tests/test_review_and_report.py` 중 영향 범위에 맞는 테스트로 검증한다.

---

## 6. 코드 구조와 책임

| 영역 | 책임 |
| --- | --- |
| `project_nurilab/input/` | 입력 경로 수집, 파일 필터링, 파일 로딩 |
| `project_nurilab/analyzers/` | Python AST, rule, secret 등 deterministic signal 생성 |
| `project_nurilab/aggregation/` | 프로젝트 단위 결과 집계 |
| `project_nurilab/llm/` | Mock / Local LLM review client |
| `project_nurilab/reports/` | HTML / JSON / optional Markdown 보고서 생성 |
| `project_nurilab/schemas.py` | 분석, 리뷰, 보고서 데이터 계약 |
| `tests/` | 회귀 테스트와 fixture |

새 모듈을 만들기 전에 기존 책임 경계에 들어갈 수 있는지 먼저 확인한다. 단일 사용처를 위한 추상화는 만들지 않는다.

---

## 7. 테스트 규칙

PR 전 반드시 실행한다.

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

테스트 기준:

- 입력 수집 변경: `tests/test_input_collector.py`
- Python AST 분석 변경: `tests/test_python_static_analyzer.py`
- pipeline 변경: `tests/test_pipeline.py`
- report 변경: `tests/test_review_and_report.py`
- Local LLM parsing 변경: `tests/test_tools_and_llm.py`

Local LLM 관련 기능은 실제 vLLM 서버 없이도 mock 테스트가 가능해야 한다.

---

## 8. PR 제출 체크리스트

PR 생성 전:

- [ ] 최신 `main` 기준 브랜치에서 작업했는가?
- [ ] 브랜치명이 네이밍 표준을 따르는가?
- [ ] PR 제목이 `[Phase 3] <요약>` 형식을 따르는가?
- [ ] `uv run pytest` 통과
- [ ] `uv run ruff check .` 통과
- [ ] `uv run ruff format --check .` 통과
- [ ] `uv run mypy .` 통과
- [ ] 기능 변경에 테스트가 포함됐는가?
- [ ] 문서 변경이 필요한 경우 README 또는 `docs/CONTRIBUTING.md`를 갱신했는가?
- [ ] 실제 악성 샘플, secrets, 민감 데이터가 포함되지 않았는가?
- [ ] Local LLM 서버가 없어도 Mock 경로가 동작하는가?

PR 본문에는 다음을 포함한다.

- 변경 목적
- 주요 변경 내용
- 검증 명령과 결과
- 제한사항 또는 후속 작업
- 관련 GitHub Issue

---

## 9. 거버넌스

- `README.md`는 프로젝트 소개, 현재 Phase, 실행 방법의 정본이다.
- `AGENTS.md`는 작업 규칙과 에이전트 행동 기준의 정본이다.
- `docs/CONTRIBUTING.md`는 팀원이 PR을 올리기 위한 절차 문서다.
- `docs/PR_DESCRIPTION.md`는 PR 본문 작성 참고 템플릿이다.
- GitHub Issue는 작업 단위와 상태 추적의 정본이다.
- PR은 코드 리뷰와 변경 이력의 정본이다.

설계 변경, 데이터 계약 변경, 출력 포맷 변경은 반드시 문서와 테스트를 함께 갱신한다.

모호하거나 막히면 임의로 확장하지 말고 GitHub Issue 또는 PR 코멘트에 남긴 뒤 Owner 확인을 받는다.

---

## 10. 유지보수 TODO

- GitHub Actions 기반 CI 추가 검토
- CODEOWNERS 도입 여부 검토
- branch protection 설정 검토
- Phase 3 이슈 목록 정리
- 외부 실제 Python 프로젝트 테스트셋 선정
- README의 `Phase Next` 항목 주기적 정리
