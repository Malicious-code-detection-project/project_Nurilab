# Local-based LLM Malware Analysis Automation

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/Package%20Manager-uv-654FF0)
![Status](https://img.shields.io/badge/Status-Prototype-orange)
![Runtime](https://img.shields.io/badge/Runtime-Local%20GPU-2E7D32)
![LLM Serving](https://img.shields.io/badge/LLM%20Serving-SGLang%20%7C%20vLLM-0A66C2)

<!--
Future badges:
- License
- Test status
- Coverage
- Documentation
- Model compatibility
- Static analysis support
-->
로컬 환경에서 동작하는 LLM 기반 악성코드/의심 파일 분석 자동화 시스템입니다. 외부 LLM API 기반 코드 리뷰와 보안 분석은 분석 단계가 고도화될수록 토큰 사용량과 호출 비용이 급격히 증가합니다. 본 프로젝트는 이러한 비용 증가를 통제하고, 반복적인 분석 워크로드를 로컬 GPU 환경에서 안정적으로 처리하는 것을 목표로 합니다.

## 1. Project Overview

이 프로젝트는 악성코드 또는 의심 파일을 로컬 환경에서 분석하고, 분석가가 읽기 쉬운 보안 보고서를 자동 생성하는 시스템을 지향합니다.

초기 단계에서는 200줄 이하의 Python 파일 1개를 대상으로 코드 리뷰 및 보안 리뷰 프로토타입을 구현합니다. 이후 입력 범위를 의심 파일과 악성코드 정적 분석 결과로 확장하고, 로컬 LLM과 RAG 기반 보안 지식 검색을 결합해 행위 해석, 위협 수준 판단, 대응 권고를 생성합니다.

## 2. Background & Motivation

현재 코드 리뷰 및 보안 분석에 외부 LLM API를 사용할 경우, 분석 대상 코드의 크기, 반복 리뷰 횟수, 다단계 분석 프롬프트, RAG 연동, 보고서 재생성 과정이 늘어날수록 API 호출량과 토큰 사용량이 빠르게 증가합니다.

이 프로젝트는 반복적이고 대량화되는 분석 워크로드를 로컬 GPU 환경에서 처리해 비용을 예측 가능하게 만들고, 모델과 서빙 프레임워크를 직접 튜닝할 수 있는 구조를 지향합니다. 로컬 환경에서 분석이 수행되므로 민감한 코드와 의심 파일을 외부 서비스로 전송하지 않아도 되는 보안상 장점도 함께 가집니다.

## 3. Key Objectives

- 200줄 이하 Python 코드 리뷰/보안 리뷰 MVP 구현
- AST 기반 import, function, class, 위험 호출 후보 추출
- 정적 분석 결과의 JSON 정규화
- Markdown/JSON 기반 코드 리뷰 보고서 생성
- 의심 파일과 소스코드의 정적 분석 자동화 확장
- 파일 메타데이터, 해시, 문자열, import/API, 함수 정보 추출 확장
- 로컬 LLM 기반 의심 행위 해석
- RAG 기반 보안 지식 검색 연동
- 위협 수준 판단 및 근거 정리
- SGLang과 vLLM 기반 로컬 LLM 서빙 비교

## 4. System Pipeline

```text
Phase 1:
.py File
-> Python File Loader
-> Python Static Analyzer
-> Feature Normalizer
-> LLM Review Client
-> Result Parser
-> Report Generator

Phase 2:
Suspicious File / Source Code
-> Input Manager
-> Static Analyzer
-> Feature Normalizer
-> RAG Retriever
-> Local LLM Client
-> Result Parser
-> Report Generator
```

## 5. Core Features

Phase 1에서는 기능을 의도적으로 작게 유지합니다.

- 200줄 이하 `.py` 파일 1개 입력
- Python AST parse 가능 여부 확인
- import, function, class 목록 추출
- 위험 호출 후보 탐지
- 정적 분석 결과 JSON 정규화
- LLM 또는 Mock LLM 기반 코드 리뷰 생성
- Markdown/JSON 보고서 생성

Phase 2에서는 악성코드/의심 파일 분석으로 확장합니다.

- 파일 메타데이터 및 해시 계산
- 문자열, URL, IP, 도메인 등 IOC 후보 추출
- PE 섹션, import/API, 함수 구조 분석
- 스크립트 및 소스코드 기반 보안 위험 분석
- MITRE ATT&CK, CVE, CWE, YARA 관련 지식 연결
- 로컬 LLM 기반 행위 요약과 위험도 판단
- 분석 근거가 포함된 보안 보고서 생성

## 6. Architecture Principles

아키텍처는 단계별로 확장 가능하게 설계하되, Phase 1에서는 작은 입력과 단순한 정적 분석에 집중합니다. 각 컴포넌트는 독립적으로 교체하거나 비교 실험할 수 있도록 분리합니다.

특히 LLM 모델, 서빙 프레임워크, 리뷰 생성 방식, 보고서 템플릿은 실험 대상이므로 코드에서 강하게 결합하지 않습니다. Phase 1에서 만든 Python 코드 리뷰 흐름은 Phase 2의 의심 파일 분석 파이프라인으로 확장될 수 있어야 합니다.

## 7. Phase 1 MVP Architecture

1차 목표는 악성코드 분석이 아니라, **Python 코드 리뷰 및 보안 리뷰 최소 프로토타입**입니다. 입력은 200줄 이하의 `.py` 파일 1개로 제한합니다.

```text
.py File
-> Python File Loader
-> Python Static Analyzer
-> Feature Normalizer
-> LLM Review Client
-> Result Parser
-> Report Generator
```

```text
                  ┌────────────────────┐
                  │ User / CLI          │
                  │ analyze sample.py   │
                  └─────────┬──────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────┐
│ Python File Loader                               │
│ - .py 파일만 허용                                │
│ - 200줄 초과 시 skip                             │
│ - UTF-8 코드 읽기                                │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Python Static Analyzer                           │
│ - AST parse                                      │
│ - import/function/class 추출                     │
│ - 위험 호출 후보 탐지                            │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Feature Normalizer                               │
│ - 정적 분석 결과 JSON 정리                       │
│ - 리뷰/보고서 입력 형태로 변환                   │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ LLM Review Client                                │
│ - 초기에는 Mock 리뷰 생성                        │
│ - 이후 로컬 LLM API로 교체                       │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Result Parser                                    │
│ - 리뷰 결과 구조화                               │
│ - risk level / findings / recommendations 정리   │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Report Generator                                 │
│ - Markdown 보고서 생성                           │
│ - JSON 결과 저장                                 │
│ - 분석 시간 / 모델 / 설정 정보 포함              │
└──────────────────────────────────────────────────┘
```

1차 MVP에서 각 컴포넌트의 역할은 다음과 같습니다.

- `Python File Loader`: `.py` 파일만 허용하고, 200줄 초과 코드는 분석 대상에서 제외
- `Python Static Analyzer`: AST 기반으로 import, function, class, 위험 호출 후보 추출
- `Feature Normalizer`: 정적 분석 결과만 JSON으로 정리
- `LLM Review Client`: 초기에는 Mock 리뷰를 생성하고, 이후 로컬 LLM API로 교체
- `Result Parser`: risk level, findings, recommendations 구조화
- `Report Generator`: Markdown 보고서와 JSON 결과 파일 생성

Phase 1에서는 `Prompt Builder`를 별도 컴포넌트로 분리하지 않습니다. 리뷰용 입력 문자열은 `LLM Review Client` 또는 pipeline 내부에서 단순하게 생성하고, 프롬프트가 복잡해지는 시점에 분리합니다.

LLM 연동 방식은 아직 확정하지 않습니다. 첫 구현은 GPU 없이 전체 흐름을 검증할 수 있도록 Mock LLM Client를 우선 사용하고, 이후 SGLang 또는 vLLM의 OpenAI-compatible API 호출로 교체합니다.

```text
project_nurilab app
-> http://localhost:8000/v1/chat/completions
-> SGLang or vLLM server
```

정적 분석 결과는 먼저 JSON으로 표준화합니다.

```json
{
  "file": {
    "path": "sample.py",
    "line_count": 87,
    "language": "python",
    "skipped": false
  },
  "imports": ["os", "subprocess"],
  "functions": ["run_command"],
  "classes": [],
  "suspicious_calls": [
    {
      "name": "subprocess.run",
      "line": 12
    }
  ]
}
```

1차에서 제외하는 항목은 다음과 같습니다.

- 디렉터리 단위 분석
- 여러 파일 동시 분석
- 200줄 초과 코드 분석
- PE/ELF/문서형 파일 분석
- RAG vector DB
- 동적 분석 sandbox
- 웹 대시보드
- 모델 파인튜닝
- SGLang/vLLM 서버 자동 설치

## 8. Phase 2 Expansion Architecture

2차 목표는 Phase 1에서 검증한 코드 리뷰 흐름을 **의심 파일/악성코드 정적 분석 자동화 시스템**으로 확장하는 것입니다. 이 단계에서 기존 큰 아키텍처를 적용합니다.

![Phase 2 확장 설계도](./images/ChatGPT%20Image%202026년%204월%2026일%20오후%2005_28_41.png)

```text
Suspicious File / Source Code
-> Input Manager
-> Static Analyzer
-> Feature Normalizer
-> Prompt Builder
-> RAG Retriever
-> Local LLM Client
-> Result Parser
-> Report Generator
```

```text
                  ┌────────────────────┐
                  │ User / CLI          │
                  │ analyze <file_path> │
                  └─────────┬──────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────┐
│ Input Manager                                    │
│ - 파일 경로 검증                                 │
│ - 파일 크기 제한 확인                            │
│ - 파일 타입 식별                                 │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Static Analyzer                                  │
│ - SHA256 / MD5 해시 계산                         │
│ - 파일 크기 / 확장자 / MIME type                 │
│ - 문자열 추출                                    │
│ - URL / IP / domain 후보 추출                    │
│ - PE 파일이면 import / section 정보 추출          │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Feature Normalizer                               │
│ - 정적 분석 결과를 공통 JSON 스키마로 변환        │
│ - 긴 문자열/결과는 요약 또는 제한                 │
│ - LLM 입력에 필요한 핵심 feature 선별             │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Prompt Builder                                   │
│ - 분석 목적에 맞는 system/user prompt 생성        │
│ - 파일 메타데이터와 정적 분석 결과 삽입           │
│ - 출력 형식 Markdown/JSON 요구                   │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ RAG Retriever                                    │
│ - 보안 지식 검색                                 │
│ - MITRE ATT&CK / CVE / YARA 관련 정보 연결        │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Local LLM Client                                 │
│ - SGLang 또는 vLLM OpenAI-compatible API 호출     │
│ - timeout / retry / error handling               │
│ - 모델별 파라미터 관리                           │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Result Parser                                    │
│ - LLM 응답 파싱                                  │
│ - 위협 수준 / 근거 / 의심 행위 / 권고사항 분리    │
│ - 실패 시 raw response 보존                      │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Report Generator                                 │
│ - Markdown 보고서 생성                           │
│ - JSON 결과 저장                                 │
│ - 분석 시간 / 모델 / 설정 정보 포함              │
└──────────────────────────────────────────────────┘
```

Phase 2에서 추가되는 주요 기능은 파일 메타데이터/해시 계산, 문자열 및 IOC 추출, PE 구조 분석, RAG 기반 보안 지식 검색, 위협 수준 판단입니다.

## 9. LLM Model Strategy

초기 모델 후보는 로컬 구동 가능한 Qwen Coder 계열을 우선 검토합니다. 이후 gpt-oss 계열과 보안 특화 오픈소스/오픈웨이트 모델을 비교 대상으로 추가합니다.

모델 평가는 다음 기준으로 수행합니다.

- 로컬 GPU 적합성
- 코드 및 파일 분석 능력
- 보안 취약점 및 의심 행위 탐지 능력
- 보고서 생성 품질
- 컨텍스트 길이
- 추론 비용과 응답 지연시간
- 라이선스 및 폐쇄망 배포 적합성

## 10. LLM Serving Strategy

LLM 서빙 프레임워크는 SGLang과 vLLM을 모두 비교 실험 대상으로 둡니다. 두 프레임워크 모두 단일 GPU와 멀티 GPU 구성을 지원하므로, 단순히 GPU 수만으로 선택하지 않고 실제 분석 워크로드를 기준으로 평가합니다.

- vLLM: PagedAttention 기반 KV cache 관리와 고처리량 serving에 강점
- SGLang: RadixAttention 기반 prefix cache reuse, structured output, 복잡한 workflow 실행에 강점

최종 선택은 처리량, 응답 지연시간, GPU 메모리 사용량, 모델 호환성, 운영 복잡도, RAG/정적 분석 파이프라인과의 통합 난이도를 기준으로 판단합니다.

자세한 비교는 [SGLANG_VLLM_COMPARISON.md](./SGLANG_VLLM_COMPARISON.md)를 참고합니다.

## 11. Repository Structure

현재 구조:

```text
.
├── project_nurilab/
│   ├── analyzers/
│   ├── input/
│   ├── llm/
│   ├── reports/
│   ├── cli.py
│   ├── config.py
│   ├── pipeline.py
│   └── schemas.py
├── tests/
│   └── fixtures/
├── main.py
├── pyproject.toml
├── uv.lock
├── AGENTS.md
├── SGLANG_VLLM_COMPARISON.md
└── README.md
```

향후 확장 구조:

```text
data/
docs/
samples/
```

## 12. Development Setup

이 프로젝트는 Python `>=3.12`와 `uv`를 사용합니다.

```bash
uv sync
```

현재 애플리케이션 실행:

```bash
uv run python main.py analyze tests/fixtures/vulnerable_sample.py --out reports
```

테스트 실행:

```bash
uv run pytest
```

린트 및 포맷:

```bash
uv run ruff check .
uv run ruff format .
```

## 13. Roadmap

- Phase 1: 200줄 이하 `.py` 파일 기반 코드 리뷰/보안 리뷰 MVP
- Phase 2: 의심 파일/악성코드 정적 분석 파이프라인 확장
- Phase 3: 로컬 LLM 연동 및 SGLang/vLLM 서빙 성능 비교
- Phase 4: RAG 기반 보안 지식 검색 연동
- Phase 5: 악성 파일 분석 워크플로우 고도화
- Phase 6: 샌드박스 및 동적 분석 결과 연계 검토

## 14. Security Notice

실제 악성 파일은 반드시 격리된 분석 환경에서만 다룹니다. 분석 대상 파일, 로그, 해시, 문자열, 내부 보안 데이터는 외부 서비스로 업로드하지 않는 것을 원칙으로 합니다.

테스트에는 가능한 무해한 fixture와 샘플 데이터를 사용합니다. API key, 내부 보고서, 실제 고객 데이터, 민감한 악성코드 샘플은 저장소에 커밋하지 않습니다.

## 15. Related Documents

- [AGENTS.md](./AGENTS.md): 이 저장소에서 에이전트가 따라야 할 작업 기준
- [SGLANG_VLLM_COMPARISON.md](./SGLANG_VLLM_COMPARISON.md): SGLang과 vLLM 비교 분석 리포트
