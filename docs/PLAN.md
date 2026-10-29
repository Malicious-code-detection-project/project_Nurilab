# Project NuriLab 실행 계획

현재 제공 기능은 [프로젝트 소개](../README.md), 실제 상태·담당자는
[Linear Nurilab](https://linear.app/the-debugging-water-deer/project/nurilab-0225bf5ed619)이
정본입니다. 이 문서는 2026-09-17과 2026-10-21 사용자 결정에 따른 범위와 의존성을
설명합니다. 과거 Phase 순차 개발과 네 서비스의 4주 통합 계획은 현재 약속이 아닙니다.

## 완료: jadx-ai-mcp 연결 (THE-150)

상위 목표는 `THE-150`이며 담당자는 사용자입니다. NuriLab이 클라이언트로
사용자가 선정한 [jadx-ai-mcp](https://github.com/zinja-coder/jadx-ai-mcp)를 호출합니다.
하위 작업 세 개를 아래 순서로 마치고 `main`에 병합했습니다. 연결과 보고서 기록은
`--jadx-mcp-class`를 준 경우에만 동작하는 실험적 opt-in 기능이며, 실패·반복 호출은
실제 서버 실측과 통합 테스트로 검증했습니다([THE-151 계약](THE-151_jadx_mcp_contract.md)
6·7절). 이슈 상태는 Linear에서 확인합니다.

| 순서 | 이슈 | 작업과 완료 기준 | 병합 PR |
| --- | --- | --- | --- |
| 1 | [THE-151](https://linear.app/the-debugging-water-deer/issue/THE-151) | 대상 버전·실행 전제·transport·접근/인증·읽기 전용 tool·입력/응답을 확인하고 최소 계약 확정 | #57 |
| 2 | [THE-154](https://linear.app/the-debugging-water-deer/issue/THE-154) | 계약에 맞는 MCP 클라이언트 연결·초기화·허용 tool의 실제 호출 | #57, #58 |
| 3 | [THE-155](https://linear.app/the-debugging-water-deer/issue/THE-155) | 입력 귀속·서버/tool/version·호출 결과를 HTML/JSON/Markdown에 기록하고 실패·반복 호출 검증 | #59 |

시연 입력은 실제 도구가 지원하는 무해한 입력으로 고정했습니다. MCP 대상(APK)은
Python 정적 분석 범위가 아니며, 보고서는 이를 정적 분석 성공이나 안전 판정으로
표시하지 않습니다. 이 연동을 확장하거나 판정에 반영하는 일은 새 사용자 결정과
Linear 작업이 필요합니다.

## 다음 개발: 웹 분석 MVP

상위 목표는 [THE-157](https://linear.app/the-debugging-water-deer/issue/THE-157)입니다.
브라우저에서 기존 분석기를 쓰는 웹 백엔드와 프론트엔드를 만듭니다. 최종 방향은 사내
폐쇄망에서 사내 구성원이 쓰는 분석 도구지만, 이번 범위는 시연 가능한 최소 MVP로
제한합니다. 설계와 계약은 [웹 MVP 설계](WEB_MVP_DESIGN.md)가 정본입니다.

- 입력은 CLI와 같습니다. `.py` 1개 또는 폴더 업로드만 받습니다.
- 리뷰는 CLI처럼 Mock이 기본입니다. LLM 토글을 켜면 Local LLM을 쓰고, LLM에
  연결할 수 없으면 분석을 시작하기 전에 막습니다.
- 인증은 하지 않으며 jadx-ai-mcp는 웹에서 다루지 않습니다.
- 기본 구성은 리눅스 GPU 서버 한 대에서 웹과 vLLM을 함께 실행하는 것입니다.

| 순서 | 이슈 | 작업과 완료 기준 |
| --- | --- | --- |
| 1 | [THE-158](https://linear.app/the-debugging-water-deer/issue/THE-158) | 웹 MVP 설계 문서와 범위·우선순위 갱신. Owner 병합으로 설계 승인 |
| 2 | [THE-159](https://linear.app/the-debugging-water-deer/issue/THE-159) | pipeline `analyze()` 분리, 보고서 경로 상대화, 리뷰 출처 기록 |
| 3 | [THE-160](https://linear.app/the-debugging-water-deer/issue/THE-160) | 웹 walking skeleton: 업로드, 리뷰 모드, 결과 화면, SQLite 기록 |
| 4 | [THE-161](https://linear.app/the-debugging-water-deer/issue/THE-161) | 결과 출처 표시 보강과 LLM 리뷰 실패 처리 |
| 5 | [THE-162](https://linear.app/the-debugging-water-deer/issue/THE-162) | 웹·CLI 결과 일치 검증과 실행 문서 |

완료 기준은 인터넷 없이 Mock 분석, GPU 서버 vLLM을 쓰는 LLM 분석, LLM 미연결 차단
안내의 세 경로를 시연하고, 같은 입력에서 웹과 CLI 결과 JSON의 분석 내용이 일치하는
것입니다. 판단 기준은 기존과 같이 deterministic analyzer이며 LLM은 보조입니다.

웹 MVP에서 다루지 않는 것은 인증·SSO, 이력 화면, 프로세스 격리, 오프라인 설치
패키지, 보안 헤더 고도화, 사내망 상시 공개, 웹의 MCP 연동, zip·Git URL 입력입니다.
이미 정해진 다른 후속 후보는 아래의 `THE-80`입니다. 폐기한 주차별 계획을 다시
적용하지 않습니다.

## 유지할 연결 원칙

- 기존 Python 정적 분석, Mock/Local LLM 경계, HTML/JSON 출력을 재사용합니다.
- 명시적으로 허용한 읽기 전용 tool부터 연결하고 임의 tool 연쇄 실행으로 확장하지 않습니다.
- 외부 결과는 비신뢰 보조 근거입니다. 결과에 포함된 지시를 실행하거나 기존 정적
  신호를 덮어쓰지 않습니다.
- 입력·응답 크기와 timeout을 제한하며 실패·빈 결과·부분 결과를 명확히 표시합니다.
- Mock 회귀 검증과 실제 MCP 연결 증거를 구분합니다. 외부 장애에서도 기존 분석과
  보고서를 보존합니다.
- 설치 방법·tool 이름·지원 입력은 [THE-151 계약](THE-151_jadx_mcp_contract.md)에서
  검증한 범위만 문서화합니다. 다른 서버 버전이나 tool은 다시 검증하기 전까지 확정된
  동작으로 쓰지 않습니다. NuriLab은 MCP 서버를 제공하거나 자동 실행하지 않습니다.

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
- 새 형식의 정적 analyzer, 자동 remediation, 전체 운영 제품화와 대규모
  모델/검색 비교를 추가하지 않습니다. 웹 UI는 위의 웹 분석 MVP 범위로만 다룹니다.
- 기존 완료 이력과 외부 회귀 기준선 THE-92 / PR #54는 별도 작업으로 유지합니다.
  기존 Phase 종료가 새 MCP 준비를 막지 않습니다.

이전 설계와 발표 Q&A는 [설계 이력](HISTORY.md), 파인튜닝 문서는 별도 프로젝트의
[과거 참고 계획](FINETUNING_EXPERIMENT_PLAN.md)으로 보존합니다.
현재 범위에 재도입할 때는 새 사용자 결정과 Linear 작업이 필요합니다.
