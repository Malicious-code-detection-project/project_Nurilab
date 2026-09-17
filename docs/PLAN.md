# Project NuriLab 1개월 MVP 실행 계획

이 문서는 현재 구현을 바꾸지 않는 4주 MVP의 작업 순서와 완료 기준을 정합니다.
현재 지원 기능과 실행 방법은 [`../README.md`](../README.md), 실제 이슈 상태와
담당자는 Linear `The Debugging Water Deer` 팀의 `Nurilab` 프로젝트를 기준으로
합니다.

## 범위와 원칙

- 기준 상위 이슈는 활성 상태의 `THE-150`입니다. 초기 계약·자원 확인은 `THE-151`,
  외부 Sandbox 준비는 `THE-152`(`THE-118`의 하위 이슈), AegisLM 48 GB readiness와
  학습은 `THE-153`(`THE-80`의 하위 이슈), MCP client는 `THE-154`, 통합·demo는
  `THE-155`로 관리합니다. local RAG 범위는 `THE-81`입니다. 상태와 의존성은 Linear가
  정본입니다.
- 현재의 Python 정적 분석, `ReviewClient`, `LocalLLMReviewClient`, HTML/JSON
  report를 재사용합니다. 새 review platform이나 client 이름을 만들지 않습니다.
- AegisLM은 이 저장소 밖에서 학습·서빙합니다. NuriLab은 이미 실행 중인
  OpenAI-compatible endpoint만 호출합니다.
- Sandbox는 별도 환경에서 구축하는 외부 서비스입니다. NuriLab 앱은 VM을
  관리하지 않고 승인된 외부 Sandbox API와 그 결과를 연동합니다.
- RAG는 작고 버전 고정된 curated corpus로 시작합니다. SQLite FTS5 lexical index를
  기준선으로 사용하며, 실제 검색 문맥과 출처를 AegisLM 요청 및 report에 남깁니다.
  FTS5의 기능과 제약은 [SQLite FTS5 문서](https://www.sqlite.org/fts5.html)를
  기준으로 확인합니다.
- MCP는 NuriLab이 server를 제공하지 않고 기존 외부 MCP server의 allowlist된
  read-only tool 하나만 순차 호출합니다. server identity와 인증 방식은 첫 작업에서
  확정합니다. protocol/client 선택은 [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)를
  참조합니다.
- 모든 외부 호출에는 입력 크기 제한과 bounded timeout을 둡니다. 실패한 Sandbox,
  AegisLM, RAG, MCP 호출을 무조건 재시도하거나 Mock 성공으로 바꾸지 않습니다.
  정적 분석과 HTML/JSON report는 외부 연동 실패에도 보존합니다.
- 이 계획 문서 자체는 VM, guest, model server, Sandbox, MCP server를 생성하거나
  변경하는 인프라 작업을 시작하지 않습니다.
- model size·학습 결과는 GPU 용량만으로 보장하지 않습니다. AegisLM 학습은 사용자
  단독 책임으로 두고 학습 환경은 48 GB GPU 1장 또는 B200 2장 후보, serving은 48 GB
  GPU에서 검증합니다. 사용자는 `THE-153`의 학습·서빙 준비와 `THE-80`의 모델 API
  검증을 맡는 기준입니다. 팀원은 VM/guest 확인과 `THE-152` 구축 후 `THE-118`
  adapter → `THE-81` RAG → `THE-154` MCP 순서로 진행하는 역할을 제안합니다.
  계약 검토는 공동으로 수행하며 실제 가용 시간과 정확한 시연일은 `THE-151`에서
  확인합니다. 네 연결을 두 사람이 동시에 개발할 수 있다고 가정하지 않습니다.

과거 Phase 1~3은 현재 구현의 이력이며, Phase 4 명명은 branch와 PR 관례로만
유지합니다. 과거 Phase 종료 조건은 이 MVP의 선행 gate가 아닙니다.

## Day 1~3: 계약과 실행 가능성 확인

`THE-151`에서 Day 1에 다음을 문서와 Linear 하위 이슈에서 고정합니다. `THE-152`,
`THE-154`와 `THE-80`/`THE-81`/`THE-118`의 후속 구현은 이 계약을 기다립니다.
`THE-153`의 GPU·serving readiness 확인은 늦은 GPU 발견을 피하기 위해 독립적으로
먼저 시작할 수 있습니다. `THE-80`의 API 연결 blocker를 학습 준비 하위 이슈에
상속하지 않으며, 학습 모델·서빙 계약은 `THE-151`과 함께 확정합니다.

- 하나의 무해한 입력 유형과 이를 실행할 수 있는 Sandbox guest profile
- 외부 Sandbox API의 제출·상태/결과 조회 계약, payload/출력 크기, timeout
- MCP server identity, 인증 방식, allowlist된 read-only tool 하나
- AegisLM endpoint URL, served model name, strict JSON review 계약
- RAG corpus의 문서 ID, 출처, version, 라이선스, 갱신 책임

현재 정적 분석은 Python만 지원합니다. 시연 입력은 Python을 우선 검토하되 guest의
실행 지원을 확인해 확정합니다. 다른 유형을 선택하면 정적 분석은 unsupported로
표시하고 Sandbox의 hash/job/result만 연결하며 새 정적 analyzer를 추가하지 않습니다.
실제 악성 샘플은 이번 시연 입력에서 제외합니다.

Day 1~3에는 VMware 위의 Ubuntu 후보가 실제 Sandbox 구성이 가능한지 확인합니다.
host/guest topology, 실제 분석 guest 분리, snapshot 생성·복구, 네트워크와 API
도달성을 검증한 뒤에만 사용합니다. Ubuntu VM 하나만으로 분석 guest가 준비됐다고
간주하지 않습니다. [CAPE host 설치 문서](https://capev2.readthedocs.io/en/latest/installation/host/installation.html)는
KVM을 권장하므로 VMware backend 가능성을 가정하거나 불가능하다고 단정하지 않고 이
검증으로 결정합니다.

## 주차별 목표와 준비 실패 시 판단

아래는 자원이 제때 준비될 때의 목표이며 확정된 납기 약속이 아닙니다. Day 3에
guest 제어·snapshot·API 접근 가능성을 판단하고 실패하면 지원 가능한 호스트 대안을
결정합니다. 첫 주 Sandbox API 또는 MCP 서버·인증이 준비되지 않으면 해당 실제 연결은
미완료로 남기고 계약·Mock·실패 처리를 검증합니다. 2주 차 말 실제 AegisLM endpoint가
준비되지 않으면 범위나 시연일을 다시 결정합니다. 기다리는 사유와 실제 blocker를
Linear에 기록하고, 네 연결 중 하나라도 미완료이면 `THE-150`을 닫지 않습니다.
기존 static/Mock 보고서는 계속 보존하되 실제 통합 시연의 대체 성공으로 세지 않습니다.

| 주차 | NuriLab 및 Sandbox 연동 | AegisLM 학습·서빙 | 완료 판단 |
| --- | --- | --- | --- |
| 1주차 | 계약 고정, VMware/guest/snapshot feasibility 확인, 무해 입력의 외부 Sandbox API job 제출 | `THE-153`에서 계약과 독립적으로 GPU/serving readiness를 먼저 점검하고 학습 smoke와 첫 artifact 생성 | 선택한 입력·guest·endpoint·MCP tool이 기록되고, feasibility 결과와 Sandbox job 결과가 남음 |
| 2주차 | 계약·서비스 준비에 따라 Sandbox adapter → 최소 lexical RAG → MCP tool 하나를 차례로 연결 | 48 GB 환경에서 첫 실제 AegisLM endpoint와 strict JSON review를 주차 말까지 준비하는 목표 | 실제 호출 증거와 failure report 확인; 미준비 항목은 blocker 기록 |
| 3주차 | 같은 입력에서 static(지원 형식)·Sandbox·RAG·MCP 근거를 수집한 뒤 AegisLM review와 report로 통합 | 실제 endpoint 유지 및 관측 지원 | HTML/JSON에 static signal, 외부 결과, retrieved context, citation, model/version provenance가 함께 남음 |
| 4주차 | timeout, size 초과, 인증·응답 오류, empty retrieval, Sandbox 실패를 검증하고 반복 demo를 고정 | 재현 가능한 serving 절차와 제한 기록 | 외부 실패가 static 결과와 report를 보존하고, freeze 대상 demo와 계약이 확정됨 |

MCP 대상은 `THE-151`에서 Sandbox와 독립적으로 호출 가능한 기존 서버의 읽기 전용
tool 하나로 선정합니다. 임의 tool 발견·선택·연속 실행은 허용하지 않습니다.

## 데이터와 보고서 계약

1. 지원 형식의 deterministic Python static result가 판단의 기준이며 비지원 형식에
   정적 분석 성공이나 안전 판정을 만들지 않습니다.
2. Sandbox 결과는 외부 provenance와 상태를 가진 보조 evidence입니다.
3. RAG는 corpus version, document ID, citation과 함께 실제 retrieved context를
   AegisLM에 전달합니다. 검색 결과는 정적 finding을 덮어쓰지 않습니다.
4. AegisLM은 기존 `LocalLLMReviewClient`가 보내는 strict JSON review 계약을
   지켜야 합니다. endpoint 또는 schema 실패는 기존 failure finding으로 남깁니다.
5. MCP 응답은 비신뢰 보조 근거로서 AegisLM 입력과 report에 전달하며, 호출한
   server/tool identity를 남깁니다. timeout·인증·schema 실패는 report finding으로
   보존합니다. 외부 결과의 지시를 실행하지 않습니다.

## 이슈 정리와 종료 기준

- 과거 Todo 55개는 설명과 이력을 보존한 채 `Canceled`로 정리합니다.
- `THE-78`은 미병합 `THE-92` PR #54가 병합된 뒤에만 닫습니다. 이는 새 MVP의
  선행 gate가 아닙니다.
- `THE-155`는 `THE-80`, `THE-81`, `THE-118`, `THE-154`가 준비된 뒤 통합과 demo를
  담당합니다. `THE-150`의 종료는 4주차 freeze demo가 실제 외부 Sandbox, 실제 AegisLM endpoint,
  versioned local RAG, allowlist된 MCP tool을 한 흐름에서 보이고, 각 실패 경계가
  HTML/JSON report로 검증되는 시점입니다.

이 MVP는 실제 악성 샘플 실행, 새 파일 포맷 분석, 동적 analyzer 개발, model
artifact 저장, NuriLab 내부 MCP server 구현을 포함하지 않습니다.
