# 실제 vLLM 선택형 통합 테스트

이 문서는 이미 실행 중인 vLLM OpenAI-compatible server와 Project NuriLab의 실제
연동을 반복 검증하는 절차와 실행 결과를 기록합니다.

기본 pytest는 GPU와 Local LLM server를 요구하지 않습니다. 실제 호출은
`NURILAB_RUN_LOCAL_LLM=1`을 명시한 경우에만 실행합니다. 애플리케이션과 테스트는
vLLM server를 시작하거나 종료하지 않습니다.

## 검증 대상

Phase 3 종료 기준 환경은 다음과 같습니다.

| 항목 | 기준 |
| --- | --- |
| OS | Ubuntu 24.04 LTS |
| CPU | Intel Xeon w5-3435X |
| RAM | 125 GiB |
| GPU | NVIDIA RTX A6000 48 GB |
| NVIDIA driver | 595.71.05 |
| Python | 3.12 |
| torch | 2.11.0+cu130 |
| vLLM | 0.21.0 |
| model | `openai/gpt-oss-20b` |

표의 값은 검증 대상 기준입니다. 실제 실행 기록에는 명령으로 확인한 값을 다시
적습니다.

## 사전 조건

1. GPU host에서 최신 Project NuriLab commit을 checkout합니다.
2. `uv sync --locked`로 프로젝트 환경을 구성합니다.
3. 별도 process에서 vLLM server를 실행합니다.
4. `/v1/chat/completions`에 접근할 수 있는지 확인합니다.

server 실행 예시:

```bash
vllm serve openai/gpt-oss-20b \
  --host 127.0.0.1 \
  --port 8000
```

환경 확인:

```bash
nvidia-smi
uv run python --version
uv run python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0))"
uv run vllm --version
git rev-parse HEAD
```

## 실행

Local LLM server가 준비된 뒤 별도 shell에서 실행합니다.

```bash
export NURILAB_RUN_LOCAL_LLM=1
export NURILAB_LLM_BASE_URL=http://127.0.0.1:8000/v1
export NURILAB_LLM_MODEL=openai/gpt-oss-20b
export NURILAB_LLM_TIMEOUT=120

uv run pytest \
  -m local_llm_integration \
  tests/test_local_llm_integration.py \
  --junitxml=/tmp/nurilab-local-llm-integration.xml \
  -vv
```

테스트는 다음 두 입력을 실제 Local LLM에 전달합니다.

- `clean_baseline_sample.py`: 정적 위험 신호가 없는 입력
- `dynamic_execution_sample.py`: `eval` high-severity 신호가 있는 입력

각 입력에 대해 다음을 검증합니다.

- `openai/gpt-oss-20b` 실제 chat completion 호출 성공
- strict review schema parsing 성공
- 정상 입력은 `low` review이며 finding이 없음
- 위험 입력은 `high` review이며 high-severity finding이 있음
- deterministic analysis와 HTML/JSON report 생성
- Local LLM failure finding이 없음

## 기본 회귀 테스트

`NURILAB_RUN_LOCAL_LLM`을 지정하지 않으면 실제 통합 테스트는 skip됩니다.

```bash
uv run pytest
```

기본 회귀 테스트가 Local LLM server 없이 통과해야 실제 통합 테스트의 opt-in
경계가 유지된 것입니다.

## 2026-07-27 예비 CLI 진단

GPU host에서 `tests/` 디렉터리를 실제 NuriLab CLI로 분석해 Local LLM 응답과
HTML/JSON report 생성을 확인했습니다. 이 기록은 호환성 원인을 찾기 위한 예비
검증이며, 아래 선택형 pytest의 최종 성공 기록을 대신하지 않습니다.

| 항목 | 결과 |
| --- | --- |
| 입력 | `tests/` 디렉터리 |
| 분석 파일 | 21개 중 21개 완료, skipped 0개 |
| 최종 risk | `high` |
| Local LLM findings | 14개 (`high` 11, `medium` 1, `low` 2) |
| Local LLM failure finding | 0개 |
| report | LLM `summary`, `reason`, `recommendation`의 JSON/HTML 반영 확인 |

호환성 진단 결과 strict `response_format=json_schema`와
`reasoning_effort="low"` 조합은 정상 동작했습니다. 여기에
`include_reasoning=false`를 함께 보내면 HTTP 200 응답의
`message.content`가 `null`이 되거나 응답이 지연됐습니다.

따라서 NuriLab은 provider-specific `include_reasoning` 요청 필드를 제거하고,
raw reasoning/Chain-of-Thought를 읽거나 보고서에 저장하지 않습니다. 서버 주소와
내부 IP, 생성된 report 원본은 저장소에 기록하거나 커밋하지 않았습니다.

## 실행 기록

실제 실행 후 아래 항목을 같은 PR과 Linear 이슈에 기록합니다. 생성된 report,
JUnit XML, server log는 로컬 검증 산출물이며 저장소에 커밋하지 않습니다.

| 항목 | 결과 |
| --- | --- |
| 실행 날짜 | 실행 후 기록 |
| Project NuriLab commit | 실행 후 기록 |
| OS | 실행 후 기록 |
| GPU / VRAM | 실행 후 기록 |
| NVIDIA driver / CUDA | 실행 후 기록 |
| Python / torch | 실행 후 기록 |
| vLLM | 실행 후 기록 |
| model | `openai/gpt-oss-20b` |
| serve command | 실행 후 기록 |
| pytest command | 실행 후 기록 |
| 정상 fixture 결과 | 실행 후 기록 |
| 위험 fixture 결과 | 실행 후 기록 |
| 최종 판정 | 실행 후 기록 |

실패한 경우에도 HTTP status, Local LLM failure title, vLLM server log의 핵심 원인,
재시도 결과를 기록합니다. 실제 성공 결과가 기록되기 전에는 THE-85를 완료로
처리하지 않습니다.
