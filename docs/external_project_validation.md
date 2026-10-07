# External Python Project Validation Workflow

> **상태: Phase 3 과거 기록과 Phase 4 자동 회귀 검증**
>
> `7c23d9c`의 packaging 결과는 파일 라인 수 제한 제거 이전의 과거 기록이며
> 현재 `main`의 안정성 증거가 아니다. packaging·click·requests의 최신 고정 기준선,
> 실행 조건과 재검증 결과는 아래 **Phase 4 고정 외부 회귀 검증 (THE-92)** 절을 따른다.
> 이후 코드나 도구가 바뀌면 대상 commit·NuriLab commit·환경을 기록하고 다시 검증한다.

이 문서는 외부 Python 프로젝트의 로컬 분석 절차, Phase 3 과거 기록과 Phase 4 회귀 검증을 정리한다.

외부 프로젝트 원본, dependency cache, HTML/JSON report artifact는 Project NuriLab 저장소에 커밋하지 않는다.

## 목적

Phase 3에서는 작은 fixture만이 아니라 실제 Python 프로젝트 디렉터리를 입력했을 때 다음 흐름이 끝까지 유지되는지 확인한다.

- Python 파일 재귀 수집
- `.git`, `.venv`, `__pycache__`, `build`, `dist`, `reports` 제외
- 파일 로딩과 AST 분석
- Ruff JSON 수집 또는 `--no-ruff` 비활성화 경로
- Mock review 기본 경로
- 필요 시 Local LLM review 경로
- HTML/JSON report 생성

## 저장 위치 원칙

외부 프로젝트는 저장소 밖에 둔다.

```bash
mkdir -p /tmp/nurilab-external-targets
mkdir -p /tmp/nurilab-external-reports
```

```text
/tmp/nurilab-external-targets/
├── packaging/
├── click/
└── requests/

/tmp/nurilab-external-reports/
├── packaging/
├── click/
└── requests/
```

금지 항목:

- 외부 프로젝트 원본 코드 커밋
- 외부 프로젝트의 `.git/`, `.venv/`, dependency cache 커밋
- `reports/` 또는 `/tmp/nurilab-external-reports/` 산출물 커밋
- 실제 악성 샘플 또는 민감 데이터 커밋

## 실행 workflow

외부 프로젝트 분석은 아래 순서로 진행한다. 기본 검증 경로는 Mock review이며, Local LLM review는 이미 vLLM 서버가 실행 중인 환경에서만 선택적으로 수행한다.

1. 저장소 밖에 작업 디렉터리를 만든다.

   ```bash
   mkdir -p /tmp/nurilab-external-targets
   mkdir -p /tmp/nurilab-external-reports
   ```

2. 외부 프로젝트를 `/tmp/nurilab-external-targets` 아래에 clone한다.

   ```bash
   cd /tmp/nurilab-external-targets
   git clone https://github.com/pypa/packaging.git
   ```

3. 분석 전에 대상 commit을 기록한다.

   ```bash
   git -C /tmp/nurilab-external-targets/packaging rev-parse --short HEAD
   ```

4. 먼저 Mock review + `--no-ruff`로 pipeline 생존성을 확인한다.

   ```bash
   uv run python main.py analyze /tmp/nurilab-external-targets/packaging \
     --review-client mock \
     --no-ruff \
     --out /tmp/nurilab-external-reports/packaging-mock-no-ruff
   ```

5. 그다음 Mock review + Ruff 수집 경로를 확인한다.

   ```bash
   uv run python main.py analyze /tmp/nurilab-external-targets/packaging \
     --review-client mock \
     --out /tmp/nurilab-external-reports/packaging-mock-ruff
   ```

6. Local LLM review는 vLLM OpenAI-compatible API가 이미 실행 중일 때만 별도 smoke test로 실행한다.

   ```bash
   uv run python main.py analyze /tmp/nurilab-external-targets/packaging \
     --review-client local \
     --no-ruff \
     --out /tmp/nurilab-external-reports/packaging-local-no-ruff
   ```

7. 실행 후 report 산출물을 확인한다.

   ```bash
   find /tmp/nurilab-external-reports/packaging-mock-no-ruff -maxdepth 1 -type f
   ```

   확인 기준:

   - `<target>.analysis.html` 파일이 생성된다.
   - `<target>.analysis.json` 파일이 생성된다.
   - JSON report에서 `analysis.summary.total_files`, `analysis.summary.analyzed_files`, `analysis.summary.skipped_files` 값을 확인한다.
   - JSON report에서 `review.risk_level`, `review.findings`, `analysis.ruff_findings` 값을 확인한다.

8. report artifact는 커밋하지 않고, 아래 기록 양식에 결과만 남긴다.

## 후보 프로젝트

| 후보 | 저장소 | 라이선스 확인 | 선택 이유 | 예상 리스크 |
| --- | --- | --- | --- | --- |
| `pypa/packaging` | <https://github.com/pypa/packaging> | `LICENSE`에서 Apache/BSD dual license 참조 | packaging parser, metadata, marker 등 일반 Python library 구조 검증에 적합 | Python 버전별 문법과 test fixture가 많아 Ruff noise가 있을 수 있음 |
| `pallets/click` | <https://github.com/pallets/click> | BSD-style license | CLI framework라 command, option, nested module 구조 검증에 적합 | 테스트/문서용 파일이 많아 분석 대상 필터링 확인 필요 |
| `psf/requests` | <https://github.com/psf/requests> | Apache-2.0 | HTTP client library라 imports, network 관련 코드, 실사용 패키지 구조 검증에 적합 | 네트워크 관련 코드가 정상 구현임에도 pattern finding으로 표시될 수 있음 |

우선순위:

1. `pypa/packaging`
2. `pallets/click`
3. `psf/requests`

## Clone 절차

```bash
cd /tmp/nurilab-external-targets
git clone https://github.com/pypa/packaging.git
git clone https://github.com/pallets/click.git
git clone https://github.com/psf/requests.git
```

저장소 크기나 네트워크 문제가 있으면 `--depth 1`을 사용할 수 있다.

```bash
git clone --depth 1 https://github.com/pypa/packaging.git
```

## Mock / Ruff / Local LLM 사용 기준

- `--review-client mock`: 기본 검증 경로다. vLLM 서버 없이 재현 가능하므로 PR 전 안정성 확인은 이 경로를 우선한다.
- `--no-ruff`: 외부 프로젝트 규모, lint 설정, Python 버전 차이와 무관하게 입력 수집, 파일 로딩, AST 분석, report 생성을 먼저 확인할 때 사용한다.
- Ruff 수집 경로: Mock + `--no-ruff`가 통과한 뒤 tool integration과 lint 결과 집계가 깨지지 않는지 확인할 때 사용한다.
- `--review-client local`: 선택 검증 경로다. vLLM OpenAI-compatible API가 이미 실행 중일 때만 사용하며, 앱 내부에서 Local LLM 서버를 시작하지 않는다.

Local LLM smoke test는 PR 필수 gate가 아니다. 환경 의존성이 있으므로 일반 PR 검증은 Mock review 기준으로 유지한다.

## 분석 명령 예시

`<target>`에는 `packaging`, `click`, `requests` 중 하나를 넣는다.

Mock review + `--no-ruff`:

```bash
uv run python main.py analyze /tmp/nurilab-external-targets/<target> \
  --review-client mock \
  --no-ruff \
  --out /tmp/nurilab-external-reports/<target>-mock-no-ruff
```

Mock review + Ruff 수집:

```bash
uv run python main.py analyze /tmp/nurilab-external-targets/<target> \
  --review-client mock \
  --out /tmp/nurilab-external-reports/<target>-mock-ruff
```

Local LLM review + `--no-ruff`:

```bash
uv run python main.py analyze /tmp/nurilab-external-targets/<target> \
  --review-client local \
  --no-ruff \
  --out /tmp/nurilab-external-reports/<target>-local-no-ruff
```

## 기록 양식

실제 분석을 수행한 뒤에는 report artifact를 커밋하지 말고, 이 양식으로 결과만 이슈 또는 후속 문서에 기록한다. 실패한 실행도 같은 양식으로 남기고 `Crash or exception`과 `Unexpected behavior`에 원인을 적는다.

```markdown
## Target

- Repository:
- Commit:
- License:
- Local path:
- Review client: mock/local
- Ruff mode: enabled/disabled
- Output dir:
- Command:

## Result

- Exit status:
- HTML report generated: yes/no
- JSON report generated: yes/no
- HTML report path:
- JSON report path:
- Total Python files:
- Analyzed files:
- Skipped files:
- Findings count:
- Ruff findings count:
- Crash or exception:

## Notes

- Unexpected behavior:
- Follow-up issue:
```

## 실행 결과 기록

아래 기록은 외부 프로젝트 원본과 report artifact를 저장소에 커밋하지 않고 요약만 남긴 것이다.

### 2026-06-29 - `pypa/packaging`

환경:

- Project NuriLab commit: `7c23d9c`
- Python: `3.12.13`
- Ruff: `0.15.11`
- External source path: `/tmp/nurilab-external-targets/packaging`
- Report artifact path: `/tmp/nurilab-external-reports/`
- External source and generated HTML/JSON reports: not committed

대상:

- Repository: <https://github.com/pypa/packaging>
- Commit: `fb82782`
- License: Apache/BSD dual license
- Local path: `/tmp/nurilab-external-targets/packaging`

Mock review + `--no-ruff`:

```bash
uv run python main.py analyze /tmp/nurilab-external-targets/packaging \
  --review-client mock \
  --no-ruff \
  --out /tmp/nurilab-external-reports/packaging-mock-no-ruff
```

- Exit status: 0
- HTML report generated: yes
- JSON report generated: yes
- Total Python files: 74
- Analyzed files: 35
- Skipped files: 39
- Review risk level: `high`
- Review findings count: 19
- Ruff findings count: 0
- Crash or exception: none

Mock review + Ruff collection:

```bash
uv run python main.py analyze /tmp/nurilab-external-targets/packaging \
  --review-client mock \
  --out /tmp/nurilab-external-reports/packaging-mock-ruff
```

- Exit status: 0
- HTML report generated: yes
- JSON report generated: yes
- Total Python files: 74
- Analyzed files: 35
- Skipped files: 39
- Review risk level: `high`
- Review findings count: 19
- Ruff findings count: 0
- Crash or exception: none

Notes:

- 두 경로 모두 project-level HTML/JSON report 생성까지 완료했다.
- `--no-ruff`와 Ruff collection 경로의 요약 수치는 동일했다.
- 39개 파일은 현재 파일 로딩 정책에 따라 skipped result로 report에 남았다.
- 후속 외부 프로젝트 실행은 `click`, `requests` 순서로 확장한다.

## Phase 4 고정 외부 회귀 검증 (THE-92)

이 절은 PR #54의 자동 회귀 절차와 2026-09-17 재검증 결과다. 위 Phase 3 기록과
분리해서 해석한다. 제품 코드 기준은 `main`의
`694d2ee2c2a560befb959e249b3511f7e0eb5be7`이며, 이 PR은 제품 코드를 변경하지 않는다.

### 고정 대상과 환경

`tests/fixtures/external_regression/targets.json`이 아래 커밋을 고정한다.
외부 소스는 별도로 준비한 깨끗한 Git checkout이어야 한다. 외부 프로젝트의 패키지를
설치하거나 테스트·소스를 실행하지 않는다.

| 대상 | Repository | 고정 commit | License |
| --- | --- | --- | --- |
| packaging | <https://github.com/pypa/packaging> | `053c884615f2e83d80705251b447769ec2599653` | Apache-2.0 / BSD 이중 라이선스 (`LICENSE`) |
| click | <https://github.com/pallets/click> | `2c8cd3ac958a7eb316d67f2d316c27086c4c0369` | BSD-3-Clause (`LICENSE.txt`) |
| requests | <https://github.com/psf/requests> | `6af0b94158bbe10c45e754e85f9701f401e6aa9c` | Apache-2.0 (`LICENSE`) |

재검증 환경은 Linux x86_64 / WSL2 (`6.6.87.2-microsoft-standard-WSL2`),
Python `3.12.13`, pytest `9.0.3`, Ruff `0.15.11`, mypy `2.1.0`이다.
NuriLab의 `uv.lock` 기준 환경에서 저장소 루트를 작업 디렉터리로 사용한다.
Ruff 버전·외부 설정·Python 버전이 다르면 결과도 달라질 수 있다.

### 실행과 실패 조건

기본 `uv run pytest`에서는 외부 회귀 6개가 skip되고 작은 검증 로직 테스트는 실행된다.
외부 소스 경로를 지정하면 세 대상의 Mock no-Ruff / Mock Ruff 조합을 모두 검증한다.

```bash
NURILAB_EXTERNAL_REGRESSION_ROOT=/tmp/nurilab-external-targets \
  uv run pytest tests/test_external_regression.py
```

지정한 디렉터리 아래에는 `packaging`, `click`, `requests` checkout이 있어야 한다.
`~` 경로도 확장한다. 명시한 경로가 비었거나 유효하지 않으면 skip 대신 실패한다.
대상 누락, 부모 저장소를 잘못 가리키는 경로, 다른 SHA, 수정·추가된 파일 또는 ignored
파일이 있는 checkout도 실패한다. 환경·캐시·분석 산출물은 대상 checkout 밖에 둔다.
테스트는 네트워크, 자동 clone/download, Local LLM을 사용하지 않는다.

Ruff 조합은 테스트 전용 collector에서 설치된 Ruff를 현재 Python interpreter로
실행하고, 기존 collector의 finding 변환과 실제 pipeline을 사용한다.
`--no-fix --no-fix-only --no-cache`를 명시하므로 외부 프로젝트의 `fix = true` 설정이
있어도 소스를 수정하지 않는다. 실행·JSON 오류는 기준선 비교 전 실패한다.
이는 이번 회귀 테스트의 실행 조건이며 제품 CLI의 기본 Ruff 실행 방식을 변경하지 않는다.
기본 collector의 오류 변환은 기존 `tests/test_tools_and_llm.py`에서 별도로 검증한다.

HTML·JSON 생성, 반환 report와 저장 JSON의 일치, 최종 정규화 JSON을 검증한다.
정규화는 top-level `generated_at`을 제거하고 외부 root 경로만 `<ROOT>`로 치환한다.
그 외 분석·리뷰 필드와 신호는 유지하며 원래 report 객체를 변경하지 않는다.

### 재검증 결과와 기준선 유지

| 대상 | 분석 Python 파일 | skipped | Mock findings | Ruff findings | 두 조합 기준선 |
| --- | ---: | ---: | ---: | ---: | --- |
| packaging | 74 | 0 | 64 | 0 | 일치 |
| click | 79 | 0 | 27 | 0 | 일치 |
| requests | 37 | 0 | 137 | 0 | 일치 |

세 대상 모두 실제 Ruff 결과가 0건이므로 현재 Ruff/no-Ruff JSON 쌍은 동일하다.
Ruff 실행 누락과 이를 혼동하지 않도록 작은 양성 사례에서 finding 생성과 소스 보존을
별도로 검사한다. 6개 조합에서 HTML·JSON이 생성됐고 외부 checkout은 깨끗하게 유지됐다.
실제 vLLM 및 다른 OS에서의 재현 검증은 이 결과에 포함하지 않는다.

`*_expected.json`은 검토된 정규화 fixture다. 누락·손상 시 테스트는 실패하며 파일을
자동 생성하거나 덮어쓰지 않는다. 기준선 갱신은 별도 변경으로 생성 결과의 차이와
고정 커밋·도구 버전·실행 근거를 검토한 뒤 반영한다. 외부 원본과 생성된 HTML/JSON
보고서는 계속 저장소 밖에 둔다.

## 다음 작업 연결

- THE-16: 외부 프로젝트 분석 실행 절차 문서화
- THE-18: 프로젝트 디렉터리 대상 Ruff 수집 안정성 검증
- THE-19: report artifact 없이 외부 프로젝트 분석 결과 기록
- THE-20: 실제 프로젝트 파일 로딩 오류 처리 안정화
