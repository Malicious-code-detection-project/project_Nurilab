# Contributing Guide

이 문서는 Project NuriLab에 기여하는 팀원이 작업을 시작하고, 브랜치를 만들고, PR을 제출하기 위해 따라야 하는 절차를 정리합니다.

협업 규칙의 정본은 [AGENTS.md](../AGENTS.md)입니다. 이 문서는 팀원이 실제로 작업을 진행할 때 참고하는 실행 가이드입니다.

---

## 프로젝트 한 줄 요약

Project NuriLab은 로컬 환경에서 동작하는 LLM 기반 악성코드/의심 파일 분석 자동화 시스템입니다.

현재는 **Phase 3: Local LLM 리뷰 품질 개선 및 분석 대상 확장** 단계입니다. 단일 `.py` 파일과 Python 프로젝트 디렉터리를 분석하고, Mock 또는 Local LLM 리뷰를 통해 HTML + JSON 보고서를 생성합니다.

---

## 작업 재개 절차

새 PC에서 작업하거나 오랜만에 저장소를 열었다면 아래 순서로 확인합니다.

1. [README.md](../README.md) - 프로젝트 소개, 현재 Phase, 실행 방법
2. [AGENTS.md](../AGENTS.md) - 협업 운영 규칙과 PR 기준
3. [.github/PULL_REQUEST_TEMPLATE.md](../.github/PULL_REQUEST_TEMPLATE.md) - PR 작성 형식
4. [.github/ISSUE_TEMPLATE/task.md](../.github/ISSUE_TEMPLATE/task.md) - 작업 이슈 작성 형식
5. [SGLANG_VLLM_COMPARISON.md](SGLANG_VLLM_COMPARISON.md) - LLM serving 비교 자료

작업 전에는 원격 상태를 먼저 확인합니다.

```bash
git fetch origin
git status
```

로컬 브랜치가 뒤처진 상태에서 코드 구조나 구현 여부를 단정하지 않습니다.

---

## 워크스페이스 구조

```text
project_Nurilab/
├── AGENTS.md                         # 협업 운영 매뉴얼
├── README.md                         # 프로젝트 소개와 실행 방법
├── docs/                             # 기여, 비교, 실험 계획, PR 설명 템플릿
│   ├── AI_RULES.md                   # AI 코드 생성 가이드라인
│   ├── AI_RULES_KOR.md               # AI 코드 생성 가이드라인 한국어판
│   ├── CONTRIBUTING.md               # 팀원 작업 가이드
│   ├── FINETUNING_EXPERIMENT_PLAN.md # 파인튜닝 실험 계획
│   ├── PLAN.md                       # Phase 2 개발 계획 기록
│   ├── PR_DESCRIPTION.md             # PR 본문 작성 참고 템플릿
│   └── SGLANG_VLLM_COMPARISON.md     # SGLang/vLLM 비교 자료
├── main.py                           # CLI 진입점
├── pyproject.toml
├── uv.lock
├── .github/
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
│       └── task.md
├── project_nurilab/
│   ├── input/                        # 입력 수집과 파일 로딩
│   ├── analyzers/                    # Python AST, rules, secrets
│   ├── aggregation/                  # 프로젝트 단위 결과 집계
│   ├── llm/                          # Mock / Local LLM review client
│   ├── reports/                      # HTML / JSON / optional Markdown 출력
│   ├── cli.py
│   ├── config.py
│   ├── pipeline.py
│   └── schemas.py
├── tests/
│   └── fixtures/
├── data/
├── images/
└── reports/                          # 로컬 분석 결과, 커밋 금지
```

`reports/`, `.venv/`, cache 같은 로컬 작업 산출물은 커밋하지 않습니다.

---

## 개발 환경 설정

의존성은 `uv` 기준으로 관리합니다.

```bash
uv sync
```

기본 분석 실행:

```bash
uv run python main.py analyze tests
```

Local LLM 리뷰 실행 전에는 vLLM 서버를 별도 프로세스로 먼저 실행합니다.

```bash
vllm serve Qwen/Qwen2.5-Coder-3B-Instruct
uv run python main.py analyze tests --review-client local
```

앱은 vLLM 서버를 직접 실행하지 않습니다.

---

## 브랜치 전략

`main`은 항상 동작 가능한 기준 브랜치로 유지합니다. 모든 작업은 브랜치를 만든 뒤 PR로 병합합니다.

브랜치 이름:

- `feat/phase3-<topic>`
- `fix/<topic>`
- `docs/<topic>`
- `test/<topic>`
- `refactor/<topic>`
- `experiment/<topic>`

예시:

- `feat/phase3-local-llm-quality`
- `fix/local-llm-json-parser`
- `docs/team-collaboration-rules`

---

## 커밋 메시지

Conventional Commits 형식을 권장합니다.

```text
<type>: <summary>
```

사용 가능한 type:

- `feat`
- `fix`
- `docs`
- `test`
- `refactor`
- `chore`
- `experiment`

예시:

- `feat: improve local llm review prompt`
- `fix: handle fenced local llm json`
- `docs: update phase 3 collaboration rules`
- `test: add project analysis fixture`

---

## 작업 범위 규칙

Phase 3에서 우선하는 작업:

- Local LLM 리뷰 품질 개선
- 외부 실제 Python 프로젝트 분석 안정성 검증
- 파일 길이 제한 제거에 따른 대용량 소스 분석 흐름 정리
- 프로젝트 단위 결과 집계 및 보고서 가독성 개선
- 실제 운영 환경 기준의 Local LLM 연동 안정성 개선

팀 논의 없이 바로 구현하지 않는 작업:

- 파인튜닝
- remediation snippet
- 파일 전체 patched code 생성
- Python 외 언어 지원
- 멀티모달 입력
- 실제 악성 샘플 실행 또는 동적 분석

이 항목들은 README의 `Phase Next`에 후보로 남기고, 별도 이슈에서 논의합니다.

---

## 테스트와 검증

PR 전 아래 명령을 반드시 실행합니다.

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

변경 영역별 테스트 기준:

- 입력 수집 변경: `tests/test_input_collector.py`
- Python AST 분석 변경: `tests/test_python_static_analyzer.py`
- pipeline 변경: `tests/test_pipeline.py`
- report 변경: `tests/test_review_and_report.py`
- Local LLM parsing 변경: `tests/test_tools_and_llm.py`

Local LLM 관련 변경은 실제 vLLM 서버 없이도 mock 테스트가 가능해야 합니다.

---

## PR 제출 규칙

PR은 작게 유지합니다. 하나의 PR에는 하나의 목적만 담습니다.

PR 제목:

```text
[Phase 3] <summary>
```

PR 본문에는 다음을 포함합니다.

- 변경 목적
- 주요 변경 내용
- 검증 명령과 결과
- 제한사항 또는 후속 작업
- 관련 GitHub Issue

PR 생성 전 체크리스트:

- [ ] 최신 `main` 기준 브랜치에서 작업
- [ ] 브랜치명이 규칙을 따름
- [ ] `uv run pytest` 통과
- [ ] `uv run ruff check .` 통과
- [ ] `uv run ruff format --check .` 통과
- [ ] `uv run mypy .` 통과
- [ ] 기능 변경에 테스트 포함
- [ ] 사용자 실행 흐름이나 출력 변경 시 README 갱신
- [ ] 실제 악성 샘플, secrets, 민감 데이터 미포함
- [ ] Local LLM 서버가 없어도 Mock 경로 동작

---

## 보안과 데이터 취급

다음은 커밋하지 않습니다.

- 실제 악성코드 샘플
- API key, token, password
- 민감한 내부 코드
- 개인 분석 결과
- `reports/` 출력물
- `.venv/`, cache, 로컬 설정 파일

실제 악성 파일을 다루는 단계에서는 격리된 분석 환경, 네트워크 통제, 샘플 저장 정책, 접근 권한 관리가 선행되어야 합니다.

---

## 막혔을 때

모호하거나 막히면 임의로 확장하지 말고 GitHub Issue 또는 PR 코멘트에 남깁니다.

특히 다음 변경은 Owner 확인 후 진행합니다.

- schema 변경
- CLI 옵션 변경
- 보고서 출력 구조 변경
- Local LLM prompt contract 변경
- Phase Next 항목 구현 착수
