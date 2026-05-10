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
![1차 설계도](./images/ChatGPT%20Image%202026년%204월%2026일%20오후%2005_28_41.png)

로컬 환경에서 동작하는 LLM 기반 악성코드/의심 파일 분석 자동화 시스템입니다. 외부 LLM API 기반 코드 리뷰와 보안 분석은 분석 단계가 고도화될수록 토큰 사용량과 호출 비용이 급격히 증가합니다. 본 프로젝트는 이러한 비용 증가를 통제하고, 반복적인 분석 워크로드를 로컬 GPU 환경에서 안정적으로 처리하는 것을 목표로 합니다.

## 1. Project Overview

이 프로젝트는 악성코드 또는 의심 파일을 로컬 환경에서 분석하고, 분석가가 읽기 쉬운 보안 보고서를 자동 생성하는 시스템을 지향합니다.

초기 단계에서는 정적 분석 결과를 기반으로 파일의 주요 특징, 의심 문자열, import/API, 함수, 구조 정보를 추출하고 이를 LLM 입력에 맞게 정리합니다. 이후 로컬 LLM과 RAG 기반 보안 지식 검색을 결합해 행위 해석, 위협 수준 판단, 대응 권고를 생성합니다.

## 2. Background & Motivation

현재 코드 리뷰 및 보안 분석에 외부 LLM API를 사용할 경우, 분석 대상 코드의 크기, 반복 리뷰 횟수, 다단계 분석 프롬프트, RAG 연동, 보고서 재생성 과정이 늘어날수록 API 호출량과 토큰 사용량이 빠르게 증가합니다.

이 프로젝트는 반복적이고 대량화되는 분석 워크로드를 로컬 GPU 환경에서 처리해 비용을 예측 가능하게 만들고, 모델과 서빙 프레임워크를 직접 튜닝할 수 있는 구조를 지향합니다. 로컬 환경에서 분석이 수행되므로 민감한 코드와 의심 파일을 외부 서비스로 전송하지 않아도 되는 보안상 장점도 함께 가집니다.

## 3. Key Objectives

- 의심 파일과 소스코드의 정적 분석 자동화
- 파일 메타데이터, 해시, 문자열, import/API, 함수 정보 추출
- 로컬 LLM 기반 의심 행위 해석
- RAG 기반 보안 지식 검색 연동
- 위협 수준 판단 및 근거 정리
- Markdown/JSON 기반 분석 보고서 생성
- SGLang과 vLLM 기반 로컬 LLM 서빙 비교

## 4. System Pipeline

```text
Suspicious File / Source Code
-> Static Analysis
-> Feature Extraction
-> Preprocessing & Chunking
-> Local LLM Reasoning
-> RAG Security Knowledge Retrieval
-> Threat Assessment
-> Report Generation
```

## 5. Core Features

예정된 핵심 기능은 다음과 같습니다.

- 파일 메타데이터 및 해시 계산
- 문자열, URL, IP, 도메인 등 IOC 후보 추출
- PE 섹션, import/API, 함수 구조 분석
- 스크립트 및 소스코드 기반 보안 위험 분석
- MITRE ATT&CK, CVE, CWE, YARA 관련 지식 연결
- 로컬 LLM 기반 행위 요약과 위험도 판단
- 분석 근거가 포함된 보안 보고서 생성

## 6. Architecture

초기 아키텍처는 다음 컴포넌트를 기준으로 설계합니다.

```text
Input Manager
-> Static Analyzer
-> Feature Normalizer
-> RAG Retriever
-> Local LLM Server
-> Report Generator
```

각 컴포넌트는 독립적으로 교체하거나 비교 실험할 수 있도록 분리합니다. 특히 LLM 모델, 서빙 프레임워크, 프롬프트, 보고서 템플릿은 실험 대상이므로 코드에서 강하게 결합하지 않습니다.

## 7. Phase 1 MVP Architecture

1차 목표는 악성코드 완전 자동 분석이 아니라, **정적 분석 결과를 로컬 LLM이 해석해 보고서로 만드는 최소 자동화 파이프라인**입니다.

```text
Suspicious File / Source Code
-> Input Manager
-> Static Analyzer
-> Feature Normalizer
-> Prompt Builder
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

1차 MVP에서 각 컴포넌트의 역할은 다음과 같습니다.

- `Input Manager`: 파일 경로 검증, 파일 크기 제한 확인, 파일 타입 식별
- `Static Analyzer`: 해시, 파일 크기, 문자열, URL/IP/domain 후보, PE import/section 정보 추출
- `Feature Normalizer`: 정적 분석 결과를 공통 JSON 스키마로 변환하고 LLM 입력에 맞게 요약
- `Prompt Builder`: 분석 목적, 정적 분석 결과, 출력 형식을 포함한 프롬프트 생성
- `Local LLM Client`: SGLang 또는 vLLM의 OpenAI-compatible API 호출
- `Result Parser`: 위협 수준, 의심 행위, 근거, 권고사항을 구조화
- `Report Generator`: Markdown 보고서와 JSON 결과 파일 생성

LLM 서버는 애플리케이션 내부에 포함하지 않습니다. SGLang 또는 vLLM은 별도 로컬 서버로 실행하고, 애플리케이션은 API로 연결합니다.

```text
project_nurilab app
-> http://localhost:8000/v1/chat/completions
-> SGLang or vLLM server
```

정적 분석 결과는 먼저 JSON으로 표준화합니다.

```json
{
  "file": {
    "name": "sample.exe",
    "size": 102400,
    "sha256": "..."
  },
  "strings": ["http://example.com", "powershell"],
  "network_indicators": {
    "urls": [],
    "ips": [],
    "domains": []
  },
  "pe": {
    "imports": [],
    "sections": []
  }
}
```

1차에서는 RAG를 완전히 구현하지 않고, 이후 확장 가능한 위치만 남깁니다.

```text
Phase 1:
Static Analysis Result
-> Prompt Builder
-> Local LLM

Phase 2:
Static Analysis Result
-> RAG Retriever
-> Prompt Builder
-> Local LLM
```

1차 MVP의 목표 출력은 사람이 읽는 Markdown 보고서와 후속 처리용 JSON 결과입니다.

1차에서 제외하는 항목은 다음과 같습니다.

- 동적 분석 sandbox
- 자동 샘플 실행
- 대규모 RAG vector DB
- 웹 대시보드
- 사용자 인증
- 모델 파인튜닝
- SGLang/vLLM 서버 자동 설치

## 8. LLM Model Strategy

초기 모델 후보는 로컬 구동 가능한 Qwen Coder 계열을 우선 검토합니다. 이후 gpt-oss 계열과 보안 특화 오픈소스/오픈웨이트 모델을 비교 대상으로 추가합니다.

모델 평가는 다음 기준으로 수행합니다.

- 로컬 GPU 적합성
- 코드 및 파일 분석 능력
- 보안 취약점 및 의심 행위 탐지 능력
- 보고서 생성 품질
- 컨텍스트 길이
- 추론 비용과 응답 지연시간
- 라이선스 및 폐쇄망 배포 적합성

## 9. LLM Serving Strategy

LLM 서빙 프레임워크는 SGLang과 vLLM을 모두 비교 실험 대상으로 둡니다. 두 프레임워크 모두 단일 GPU와 멀티 GPU 구성을 지원하므로, 단순히 GPU 수만으로 선택하지 않고 실제 분석 워크로드를 기준으로 평가합니다.

- vLLM: PagedAttention 기반 KV cache 관리와 고처리량 serving에 강점
- SGLang: RadixAttention 기반 prefix cache reuse, structured output, 복잡한 workflow 실행에 강점

최종 선택은 처리량, 응답 지연시간, GPU 메모리 사용량, 모델 호환성, 운영 복잡도, RAG/정적 분석 파이프라인과의 통합 난이도를 기준으로 판단합니다.

자세한 비교는 [SGLANG_VLLM_COMPARISON.md](./SGLANG_VLLM_COMPARISON.md)를 참고합니다.

## 10. Repository Structure

현재 구조:

```text
.
├── main.py
├── pyproject.toml
├── uv.lock
├── AGENTS.md
├── SGLANG_VLLM_COMPARISON.md
└── README.md
```

향후 구조:

```text
project_nurilab/
project_nurilab/analyzers/
project_nurilab/llm/
project_nurilab/reports/
tests/
tests/fixtures/
data/
docs/
```

## 11. Development Setup

이 프로젝트는 Python `>=3.12`와 `uv`를 사용합니다.

```bash
uv sync
```

현재 애플리케이션 실행:

```bash
uv run python main.py
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

## 12. Roadmap

- Phase 1: 정적 분석 결과 기반 보고서 생성 최소 프로토타입
- Phase 2: 로컬 LLM 연동 및 코드/파일 분석 프롬프트 설계
- Phase 3: RAG 기반 보안 지식 검색 연동
- Phase 4: SGLang/vLLM 서빙 성능 비교
- Phase 5: 악성 파일 분석 워크플로우 고도화
- Phase 6: 샌드박스 및 동적 분석 결과 연계 검토

## 13. Security Notice

실제 악성 파일은 반드시 격리된 분석 환경에서만 다룹니다. 분석 대상 파일, 로그, 해시, 문자열, 내부 보안 데이터는 외부 서비스로 업로드하지 않는 것을 원칙으로 합니다.

테스트에는 가능한 무해한 fixture와 샘플 데이터를 사용합니다. API key, 내부 보고서, 실제 고객 데이터, 민감한 악성코드 샘플은 저장소에 커밋하지 않습니다.

## 14. Related Documents

- [AGENTS.md](./AGENTS.md): 이 저장소에서 에이전트가 따라야 할 작업 기준
- [SGLANG_VLLM_COMPARISON.md](./SGLANG_VLLM_COMPARISON.md): SGLang과 vLLM 비교 분석 리포트
