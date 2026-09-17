# Project NuriLab 실행 계획

현재 제공 기능은 [프로젝트 소개](../README.md), 실제 상태·담당자는
[Linear Nurilab](https://linear.app/the-debugging-water-deer/project/nurilab-0225bf5ed619)이
정본입니다. 이 문서는 2026-09-17 사용자 결정에 따른 범위와 의존성을 설명합니다.
과거 Phase 순차 개발과 네 서비스의 4주 통합 계획은 현재 약속이 아닙니다.

## 다음 개발: jadx-ai-mcp 연결

상위 목표는 `THE-150`이며 담당자는 사용자입니다. NuriLab이 클라이언트로
사용자가 선정한 [jadx-ai-mcp](https://github.com/zinja-coder/jadx-ai-mcp)를 호출합니다.
현재 NuriLab에는 이 연결 기능이 없으며, 다음 순서로 진행합니다.
THE-151/154/155도 사용자 담당이며 실제 상태는 Linear에서 확인합니다.

| 순서 | 이슈 | 작업과 완료 기준 |
| --- | --- | --- |
| 1 | [THE-151](https://linear.app/the-debugging-water-deer/issue/THE-151) | 대상 버전·실행 전제·transport·접근/인증·읽기 전용 tool·입력/응답을 확인하고 최소 계약 확정 |
| 2 | [THE-154](https://linear.app/the-debugging-water-deer/issue/THE-154) | 계약에 맞는 MCP 클라이언트 연결·초기화·허용 tool의 실제 호출 |
| 3 | [THE-155](https://linear.app/the-debugging-water-deer/issue/THE-155) | 입력 귀속·서버/tool/version·호출 결과를 HTML/JSON에 기록하고 실패·반복 호출 검증 |

시연 입력은 실제 도구가 지원하는 무해한 입력으로 고정합니다. 현재 Python 정적
분석과 MCP 대상의 차이를 계약 단계에서 확인하며 새 정적 analyzer 개발로
확장하지 않습니다. 미지원 정적 형식은 성공이나 안전 판정으로 표시하지 않습니다.
구체적인 일정은 착수 시 정하며, 폐기한 주차별 계획을 다시 적용하지 않습니다.

## 유지할 연결 원칙

- 기존 Python 정적 분석, Mock/Local LLM 경계, HTML/JSON 출력을 재사용합니다.
- 명시적으로 허용한 읽기 전용 tool부터 연결하고 임의 tool 연쇄 실행으로 확장하지 않습니다.
- 외부 결과는 비신뢰 보조 근거입니다. 결과에 포함된 지시를 실행하거나 기존 정적
  신호를 덮어쓰지 않습니다.
- 입력·응답 크기와 timeout을 제한하며 실패·빈 결과·부분 결과를 명확히 표시합니다.
- Mock 회귀 검증과 실제 MCP 연결 증거를 구분합니다. 외부 장애에서도 기존 분석과
  보고서를 보존합니다.
- 실제 설치 방법·tool 이름·지원 입력은 THE-151에서 검증하기 전까지 확정된 동작으로
  문서화하지 않습니다. 이 계획은 서버 제공·자동 실행 기능을 추가하지 않습니다.

## 후속 모델 API 연결

[THE-80](https://linear.app/the-debugging-water-deer/issue/THE-80)은 별도 프로젝트에서
준비한 LLM API를 연결하는 후속 작업입니다. 파인튜닝 방향·학습·모델 산출물·서빙
준비는 그 프로젝트의 책임입니다. 모델 또는 준비 완료 시점을 가정하지 않습니다.

NuriLab의 범위는 endpoint·인증 설정 방법·모델 식별자 확인, 기존
OpenAI-compatible 경계 재사용 검토, strict JSON 응답·출처·실패 처리 검증입니다.
학습 코드나 model weight, adapter, dataset, checkpoint를 저장하지 않습니다.
THE-80은 MCP 작업의 선행 조건이나 현재 MCP 시연의 완료 조건이 아닙니다.

## 제외 범위와 이력

- RAG, VectorDB/FAISS, embedding·corpus 준비를 제외합니다.
- Sandbox 구축·VM 준비·외부 Sandbox 연동을 제외합니다.
- 새 형식의 정적 analyzer, 웹 UI, 자동 remediation, 전체 운영 제품화와 대규모
  모델/검색 비교를 추가하지 않습니다.
- 기존 완료 이력과 외부 회귀 기준선 THE-92 / PR #54는 별도 작업으로 유지합니다.
  기존 Phase 종료가 새 MCP 준비를 막지 않습니다.

이전 설계와 발표 Q&A는 [설계 이력](HISTORY.md), 파인튜닝 문서는 별도 프로젝트의
[과거 참고 계획](FINETUNING_EXPERIMENT_PLAN.md)으로 보존합니다.
현재 범위에 재도입할 때는 새 사용자 결정과 Linear 작업이 필요합니다.
