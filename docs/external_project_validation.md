# External Python Project Validation Targets

이 문서는 Phase 3 안정성 검증에 사용할 외부 Python 프로젝트 후보와 로컬 분석 절차를 정리한다.

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

## 분석 명령

기본 Mock review + Ruff 수집:

```bash
uv run python main.py analyze /tmp/nurilab-external-targets/packaging \
  --out /tmp/nurilab-external-reports/packaging
```

Ruff 없이 pipeline 생존성 우선 확인:

```bash
uv run python main.py analyze /tmp/nurilab-external-targets/packaging \
  --no-ruff \
  --out /tmp/nurilab-external-reports/packaging-no-ruff
```

Local LLM review는 vLLM 서버가 이미 실행 중일 때만 별도 smoke test로 실행한다.

```bash
uv run python main.py analyze /tmp/nurilab-external-targets/packaging \
  --review-client local \
  --no-ruff \
  --out /tmp/nurilab-external-reports/packaging-local
```

Local LLM smoke test는 PR 필수 gate가 아니다. 환경 의존성이 있으므로 일반 PR 검증은 Mock review 기준으로 유지한다.

## 기록 양식

실제 분석을 수행한 뒤에는 report artifact를 커밋하지 말고, 이 양식으로 결과만 이슈 또는 후속 문서에 기록한다.

```markdown
## Target

- Repository:
- Commit:
- License:
- Local path:
- Command:

## Result

- Exit status:
- HTML report generated: yes/no
- JSON report generated: yes/no
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

## 다음 작업 연결

- THE-16: 외부 프로젝트 분석 실행 절차 문서화
- THE-18: 프로젝트 디렉터리 대상 Ruff 수집 안정성 검증
- THE-19: report artifact 없이 외부 프로젝트 분석 결과 기록
- THE-20: 실제 프로젝트 파일 로딩 오류 처리 안정화
