# Project NuriLab 개발 로드맵

이 문서는 Project NuriLab의 Phase 순서, 목표, 종료 조건을 정의합니다. 사용자에게
제공되는 현재 기능과 실행 방법은 [`../README.md`](../README.md), 실제 이슈
상태와 담당자는 Linear `The Debugging Water Deer` 팀의 `Nurilab` 프로젝트를
기준으로 합니다.

## 운영 원칙

- Phase는 `3 종료 검증 -> 4 분석 신뢰성 -> 5 운영 제품화 -> 6 AegisLM 연동
  -> 7 RAG` 순서로 진행합니다.
- 이전 Phase의 종료 조건을 충족하기 전에는 다음 Phase 구현을 시작하지 않습니다.
- 각 Phase는 Linear 상위 이슈와 한 PR 단위의 하위 이슈로 관리합니다.
- deterministic analyzer가 판단 기준이며 LLM과 RAG는 해석과 근거 보강을
  담당합니다.
- 실제 악성 샘플, model weight, adapter, dataset, checkpoint는 이 저장소에
  커밋하지 않습니다.

## 완료된 기반 Phase

### Phase 1 - 단일 Python 파일 분석 MVP

- 단일 `.py` 파일 입력
- AST 기반 구조와 위험 신호 추출
- Mock review
- JSON과 사람이 읽을 수 있는 보고서

### Phase 2 - Python 프로젝트 단위 정적 분석

- 디렉터리 재귀 수집과 제외 경로
- 여러 Python 파일 분석
- Ruff 보조 신호
- 프로젝트 단위 집계
- HTML과 JSON 기본 출력

Phase 1과 Phase 2의 현재 동작은 README와 테스트를 기준으로 하며, 과거 설계의
파일 길이 제한은 더 이상 적용하지 않습니다.

## Phase 3 종료 - 기준선 확정

Linear 상위 이슈: `THE-77`

목표는 이미 구현된 분석·리뷰·보고서 파이프라인을 최신 코드와 실제 운영 환경에서
재검증하고 다음 Phase가 의존할 기준선을 고정하는 것입니다.

주요 작업:

- 프로젝트 로드맵과 Phase 경계 최신화
- 기본 Local LLM을 `openai/gpt-oss-20b`로 전환
- strict JSON Schema와 비정상 JSON 실패 처리
- 실제 vLLM 선택형 통합 테스트
- `packaging`, `click`, `requests` 외부 프로젝트 재검증

종료 조건:

- 모든 Phase 3 종료 하위 이슈의 PR이 병합됩니다.
- `pytest`, Ruff check, Ruff format check, mypy가 통과합니다.
- 실제 GPU/vLLM 검증 환경과 결과가 기록됩니다.
- 외부 프로젝트 세 개의 고정 commit과 분석 결과가 기록됩니다.
- README, AGENTS, 이 문서와 Linear 상태가 일치합니다.

## Phase 4 - 분석 신뢰성

Linear 상위 이슈: `THE-78`

Python 정적 분석 신호의 정확성과 대규모 입력 처리의 예측 가능성을 개선합니다.

주요 작업:

- import alias와 `from ... import ...` 호출 경로 해석
- 위험 호출 인자와 실행 문맥 분석
- hard-coded secret 오탐 감소
- Local LLM 입력 budget, 정렬, truncation 정책
- Ruff 실행 실패 진단
- 외부 프로젝트 회귀 기준선 자동화
- 내장 analyzer 완료 후 Bandit/Semgrep 비교 spike

종료 조건:

- alias, 호출 문맥, secret 회귀 fixture가 통과합니다.
- 같은 입력은 같은 정적 신호와 LLM payload를 생성합니다.
- 대규모 입력이 잘린 경우 그 사실을 추적할 수 있습니다.
- Ruff 실패와 finding 0건을 구분합니다.

## Phase 5 - 운영 제품화

Linear 상위 이슈: `THE-79`

새 환경에서 설치하고, 반복 실행하고, 결과의 생성 환경을 추적할 수 있는 제품
형태로 정리합니다.

주요 작업:

- Python package metadata와 runtime dependency 정리
- `project-nurilab` 설치형 CLI
- GitHub Actions 품질 gate
- JSON/HTML report provenance
- 외부 프로젝트 검증 manifest
- `AnalysisPipeline` 명칭과 이전 import 호환
- CODEOWNERS와 branch protection 운영 기준

종료 조건:

- lock 파일 기준 설치와 CLI 실행이 재현됩니다.
- 모든 PR에서 품질 gate 4종이 자동 실행됩니다.
- 보고서에서 analyzer, 모델, runtime, 분석 시간을 추적할 수 있습니다.

## Phase 6 - AegisLM 연동

Linear 상위 이슈: `THE-80`

별도 AegisLM 프로젝트에서 생성한 모델 또는 adapter를 기존 vLLM
OpenAI-compatible 경계로 연결하고 기본 GPT-OSS 모델과 비교합니다.

Project NuriLab의 책임:

- serving endpoint와 served model name을 통한 호출
- 모델·adapter manifest와 report provenance
- 고정 평가셋 비교
- JSON 유효성, 품질, 지연 시간, 실패율 측정
- 모델 실패 시 deterministic 분석 결과 보존

AegisLM 프로젝트의 책임:

- dataset과 학습 코드
- fine-tuning과 평가 실행
- model weight, adapter, checkpoint와 실험 로그

종료 조건:

- 기본 모델과 AegisLM을 같은 입력·스키마로 비교할 수 있습니다.
- 실제 사용한 모델과 adapter를 보고서에서 추적할 수 있습니다.
- AegisLM 장애가 전체 분석 pipeline을 중단하지 않습니다.

## Phase 7 - 오프라인 우선 RAG

Linear 상위 이슈: `THE-81`

버전 고정 로컬 보안 지식 인덱스를 finding에 연결하고 사용자가 근거와 출처를
추적할 수 있게 합니다.

초기 corpus:

- NVD CVE와 CVSS/CWE 정보
- CISA Known Exploited Vulnerabilities
- MITRE ATT&CK Enterprise

주요 작업:

- corpus 필드, 라이선스, 버전, 갱신 정책
- 분석과 분리된 명시적 인덱스 갱신 명령
- lexical baseline과 local embedding retrieval 비교
- finding과 검색 근거 결합
- JSON/HTML 출처 ID, corpus version, retrieval 정보
- 인덱스 누락과 검색 실패 시 기존 결과 보존

분석 실행 중 외부 네트워크는 필수가 아닙니다. 네트워크는 사용자가 명시적으로
인덱스를 갱신할 때만 사용합니다.

종료 조건:

- 네트워크 없이 버전 고정 인덱스로 검색할 수 있습니다.
- 검색 결과가 deterministic finding을 덮어쓰지 않습니다.
- finding별 출처와 corpus version을 JSON과 HTML에서 확인할 수 있습니다.

## 연구 백로그

다음 항목은 실험 필요성이 인정되지만 현재 번호가 지정된 Phase의 완료 약속에는
포함하지 않습니다.

- Python 이외 언어 정적 분석
- PE/ELF와 문서형 파일, 멀티모달 입력
- 승인된 격리 환경에서의 동적 분석
- remediation snippet과 전체 patched code 생성
- 인증·라이선스 정책 확정 전 VirusTotal/MalwareBazaar 연동

연구 백로그 항목을 제품 Phase로 이동하려면 별도 Linear 상위 이슈와 Owner 승인이
필요합니다.
