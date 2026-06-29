# Phase 2 Development Plan

## 1. 방향 전환

Phase 2에서는 악성코드 분석을 직접 목표로 두지 않는다. 현재는 악성코드 데이터가 충분하지 않아 학습, 파인튜닝, 평가 데이터셋 구축이 어렵다. 따라서 Phase 1의 Python 코드 리뷰 컨셉을 유지하면서, **코드 전체를 대상으로 하는 정적 분석 자동화 시스템**으로 확장한다.

장기적으로 악성코드 샘플, 분석 리포트, IOC, 행위 태그, 보안 룰 데이터가 충분히 확보되면 모델 학습 또는 파인튜닝을 통해 악성코드/의심 파일 분석 시스템으로 업그레이드한다.

## 2. Phase 2 목표

Phase 2의 목표는 단일 `.py` 파일 분석을 넘어, Python 프로젝트 전체를 입력받아 코드 품질과 보안 위험을 자동으로 분석하고 보고서로 정리하는 것이다.

핵심 목표:

- Python 프로젝트 또는 디렉터리 입력 지원
- 여러 `.py` 파일 자동 수집
- 파일별 AST 기반 정적 분석
- 위험 호출, hard-coded secret, import, function, class 정보 수집
- Ruff, Bandit, Semgrep 등 외부 정적 분석 도구 연동 검토
- 분석 결과를 공통 JSON 스키마로 정규화
- Mock Review Client를 Local LLM Review Client로 교체할 수 있는 구조 설계
- Markdown/JSON 기반 프로젝트 단위 리뷰 보고서 생성

## 3. 제외 범위

Phase 2에서는 다음 기능을 아직 구현하지 않는다.

- 악성코드 샘플 분석
- PE/ELF/문서형 파일 분석
- 동적 분석 sandbox
- 모델 파인튜닝
- 자체 LLM 학습
- MCP/gRPC agent server
- 웹 대시보드
- 자동 코드 수정

이 기능들은 데이터, 평가 기준, 운영 환경이 정리된 뒤 후속 Phase에서 검토한다.

## 4. 참고 아키텍처 반영 방식

참고 프로젝트 `A2A-MCP / Code_Vulnerability`는 여러 agent server를 통해 취약점 분석을 수행한다. 우리 프로젝트는 같은 역할 분리는 유지하되, Phase 2에서도 agent server를 띄우지 않고 단일 프로세스 내부 모듈로 구현한다.

| 참고 프로젝트 역할 | Phase 2 구현 방향 |
| --- | --- |
| Quick Agent | 빠른 패턴 기반 위험 코드 탐지 |
| Secrets Agent | hard-coded secret 탐지 |
| Static Agent | AST 및 정적 분석 도구 결과 통합 |
| Criteria Agent | 향후 보안 기준 문서/RAG 연동 후보 |
| Summary Agent | 프로젝트 단위 Markdown/JSON 보고서 생성 |
| Remediation Agent | 전체 pipeline orchestration |
| MCP/gRPC | Phase 2 제외 |

## 5. Phase 2 아키텍처

```text
Project Directory / Python File
-> Input Collector
-> File Filter
-> Python Static Analyzer
-> Tool Result Collector
-> Feature Normalizer
-> Review Client
-> Result Aggregator
-> Report Generator
```

상세 흐름:

```text
                  ┌─────────────────────────────┐
                  │ User / CLI                   │
                  │ analyze ./target_project     │
                  └──────────────┬──────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────┐
│ Input Collector                                        │
│ - 파일 또는 디렉터리 입력 허용                         │
│ - Python 파일 재귀 탐색                                │
│ - 제외 경로 필터링                                     │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ File Filter                                            │
│ - .py 파일만 분석 대상                                 │
│ - venv, __pycache__, build, dist 제외                  │
│ - 파일 크기/라인 수 제한 적용                          │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Python Static Analyzer                                 │
│ - AST parse                                            │
│ - import/function/class 추출                           │
│ - 위험 호출 후보 탐지                                  │
│ - hard-coded secret 후보 탐지                          │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Tool Result Collector                                  │
│ - Ruff 결과 수집                                       │
│ - Bandit 결과 수집 후보                                │
│ - Semgrep 결과 수집 후보                               │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Feature Normalizer                                     │
│ - 파일별 분석 결과를 공통 JSON 스키마로 정리            │
│ - 프로젝트 단위 summary 생성                           │
│ - LLM 입력 또는 보고서 입력으로 변환                   │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Review Client                                          │
│ - 초기에는 Mock Review 유지                            │
│ - 이후 Local LLM Review Client로 교체                   │
│ - finding별 reason/recommendation 생성                  │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Result Aggregator                                      │
│ - 파일별 finding 통합                                  │
│ - severity별 정렬                                      │
│ - 프로젝트 risk level 산정                             │
└────────────────────────┬───────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Report Generator                                       │
│ - 프로젝트 단위 Markdown 보고서 생성                   │
│ - JSON 결과 저장                                       │
│ - 분석 설정/도구 버전/실행 시간 기록                   │
└────────────────────────────────────────────────────────┘
```

## 6. 구현 단계

### Step 1. 입력 범위 확장

- 단일 파일 입력 유지
- 디렉터리 입력 추가
- `.py` 파일 재귀 탐색
- 제외 경로 정의

예외 경로:

```text
.venv/
__pycache__/
.git/
build/
dist/
reports/
```

### Step 2. 파일별 분석 결과 구조화

현재 `PythonAnalysis`는 단일 파일 기준이다. Phase 2에서는 프로젝트 단위 결과를 추가한다.

예상 스키마:

```text
ProjectAnalysis
- root_path
- total_files
- analyzed_files
- skipped_files
- file_results[]
- summary
```

### Step 3. 외부 정적 분석 도구 연동 검토

우선순위:

1. Ruff: 코드 품질, 스타일, 기본 오류 탐지
2. Bandit: Python 보안 취약점 탐지
3. Semgrep: 보안 패턴 룰 기반 탐지

초기에는 Ruff 결과부터 JSON으로 수집한다. Bandit/Semgrep은 도입 전 의존성, 실행 시간, 출력 포맷, 룰 관리 부담을 검토한다.

### Step 4. 리뷰 클라이언트 개선

현재 `MockLLMReviewClient`는 정적 분석 결과를 deterministic review로 변환한다. Phase 2에서는 인터페이스를 명확히 나누고, 이후 Local LLM Client를 추가한다.

```text
ReviewClient protocol
├── MockReviewClient
└── LocalLLMReviewClient
```

Local LLM Client는 SGLang/vLLM의 OpenAI-compatible API를 호출할 수 있도록 설계하되, Phase 2 초반에는 필수 구현으로 보지 않는다.

### Step 5. 프로젝트 단위 보고서 생성

보고서는 파일별 상세 결과와 프로젝트 전체 요약을 모두 포함한다.

보고서 항목:

- 분석 대상 경로
- 분석 파일 수
- skip 파일 수와 이유
- 전체 risk level
- severity별 finding 개수
- 파일별 finding 목록
- 주요 위험 호출
- hard-coded secret 후보
- 도구별 결과 요약
- 개선 권고

## 7. 권장 디렉터리 구조

```text
project_nurilab/
├── analyzers/
│   ├── patterns.py
│   ├── python_static.py
│   ├── secrets.py
│   └── tools.py              # Ruff/Bandit/Semgrep 결과 수집 후보
├── input/
│   ├── manager.py            # 단일 파일 로더
│   └── collector.py          # 디렉터리 입력 및 파일 수집
├── llm/
│   ├── review.py             # ReviewClient interface / Mock client
│   └── local_client.py       # 향후 Local LLM API client
├── reports/
│   └── generator.py
├── aggregation/
│   ├── __init__.py
│   └── result_aggregator.py
├── cli.py
├── config.py
├── pipeline.py
└── schemas.py
```

## 8. 평가 기준

Phase 2는 모델 성능보다 시스템 구조와 분석 자동화 품질을 먼저 평가한다.

평가 항목:

- 디렉터리 입력 처리 안정성
- 분석 대상/제외 대상 구분 정확성
- 파일별 finding 재현성
- 보고서 가독성
- false positive 설명 가능성
- 분석 실행 시간
- 외부 도구 결과 통합 난이도
- Local LLM Client로 교체 가능한 구조인지 여부

## 9. Roadmap

```text
Phase 1:
단일 .py 파일 기반 코드 리뷰/보안 리뷰 MVP

Phase 2:
Python 프로젝트 단위 정적 분석 자동화 시스템

Phase 3:
Local LLM Review Client 연동 및 SGLang/vLLM 비교

Phase 4:
RAG 기반 보안 기준 문서/룰 검색 연동

Phase 5:
악성코드 데이터 확보 후 보안 특화 학습/파인튜닝 검토

Phase 6:
악성코드/의심 파일 분석 자동화 시스템으로 컨셉 확장
```

## 10. 다음 작업 후보

가장 먼저 할 작업:

1. `Input Collector` 추가
2. `ProjectAnalysis` 스키마 추가
3. 디렉터리 입력 CLI 지원
4. 파일별 분석 결과 aggregation 구현
5. 프로젝트 단위 Markdown/JSON 보고서 생성

그 다음 작업:

1. Ruff JSON 결과 수집 실험
2. Bandit 도입 여부 검토
3. ReviewClient 인터페이스 분리
4. Local LLM Client 설계
5. README를 Phase 2 계획에 맞게 업데이트
