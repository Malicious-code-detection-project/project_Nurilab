# Repository Guidelines

## Agent Role

이 저장소에서 에이전트의 역할은 **local-based LLM 기반 코드 리뷰 및 악성코드/의심 파일 분석 자동화 시스템**을 단계적으로 설계하고 구현하는 것이다. 모든 설계는 외부 LLM API 비용 증가를 줄이고, 로컬 GPU/서버 환경에서 모델 추론, 분석, 보고서 생성이 가능하도록 구성한다.

작업할 때는 처음부터 악성코드 분석 전체를 완전 자동화하려 하지 않는다. Phase 1에서는 200줄 이하의 `.py` 파일 1개를 대상으로 Python 코드 리뷰/보안 리뷰 MVP를 만든다. Phase 2에서 의심 파일 입력, 파일 정적 분석, RAG, 샌드박스 연계, 모델 비교 기능을 점진적으로 붙인다.

## Implementation Priorities

우선순위는 다음 순서로 둔다.

1. 200줄 이하 `.py` 파일 1개를 입력받는 Python File Loader를 만든다.
2. Python AST 기반으로 import, function, class, 위험 호출 후보를 추출한다.
3. 정적 분석 결과를 공통 JSON 구조로 정규화한다.
4. 초기에는 Mock LLM Review Client로 코드 리뷰 결과를 생성한다.
5. 리뷰 결과를 risk level, findings, recommendations로 구조화한다.
6. Markdown 보고서와 JSON 결과 파일을 생성한다.
7. 이후 로컬 LLM API, 의심 파일 정적 분석, RAG, 모델/서빙 비교 기능을 순차적으로 확장한다.

새 기능을 만들 때는 Phase 1 범위를 넘기지 않는지 먼저 확인한다. 디렉터리 분석, 여러 파일 동시 분석, 200줄 초과 코드 분석, PE/ELF 분석, RAG, 동적 분석, 웹 대시보드는 Phase 1에 넣지 않는다.

## Model and Serving Decisions

초기 모델 실험은 로컬 구동 가능한 Qwen Coder 계열을 우선 고려한다. 이후 gpt-oss 계열을 포함한 오픈소스/오픈웨이트 모델을 비교 대상으로 추가한다.

모델 선택 기준은 로컬 GPU 적합성, 코드/파일 분석 능력, 취약점 탐지 능력, 보고서 생성 품질, 컨텍스트 길이, 추론 비용, 라이선스 적합성이다. 모델명이나 성능 수치를 문서에 쓸 때는 최신 공식 자료를 확인하고 단정적으로 과장하지 않는다.

LLM 서빙은 로컬 환경에서 SGLang과 vLLM을 모두 비교 실험 대상으로 둔다. 두 프레임워크 모두 멀티 GPU 구성을 지원하므로, 단일 GPU/다중 GPU 여부만으로 선택하지 않는다.

SGLang은 `--tp` 기반 tensor parallel, `--dp` 기반 data parallel 등 멀티 GPU 병렬 구성을 검토한다. vLLM은 `tensor_parallel_size`, `pipeline_parallel_size`, `distributed_executor_backend` 구성을 검토한다. 단일 노드에서는 두 프레임워크 모두 로컬 GPU 자원 활용성을 비교하고, 다중 노드가 필요할 경우 SGLang의 multi-node deployment와 vLLM의 Ray 기반 구성을 함께 검토한다.

최종 선택은 처리량, 지연시간, 모델 호환성, GPU 메모리 사용량, 운영 복잡도, 폐쇄망 배포 편의성, 분석 워크로드와의 통합 난이도를 기준으로 판단한다.

## Repository Structure

현재 프로젝트는 Python `uv` 기반이며 진입점은 `main.py`다. 의존성과 Python 버전은 `pyproject.toml`, 잠금 파일은 `uv.lock`에서 관리한다.

규모가 커지면 재사용 가능한 코드는 `project_nurilab/`, 테스트는 `tests/`, 샘플 입력과 fixture는 `tests/fixtures/` 또는 `data/`에 둔다. 실험 산출물, 로컬 가상환경, 민감 데이터는 커밋하지 않는다.

## Development Commands

- `uv sync`: 의존성 설치 및 동기화
- `uv run python main.py`: 현재 애플리케이션 실행
- `uv run pytest`: 테스트 실행
- `uv run ruff check .`: 린트 검사
- `uv run ruff format .`: 코드 포맷팅

모든 명령은 저장소 루트에서 실행한다.

## Coding and Testing Rules

Python `>=3.12`를 기준으로 작성한다. 4칸 들여쓰기, `snake_case` 함수/변수명, `PascalCase` 클래스명, `UPPER_SNAKE_CASE` 상수명을 사용한다. 공용 함수에는 타입 힌트를 붙이고, `main.py`에는 실행 흐름만 두며 핵심 로직은 모듈로 분리한다.

테스트는 `pytest`를 사용한다. 테스트 파일은 `tests/test_<module>.py`, 테스트 함수는 `test_<behavior>()` 형식으로 작성한다. 외부 API, 모델 호출, 네트워크 요청은 mock 또는 fixture로 대체해 재현 가능하게 만든다.

## Proposal and Documentation Behavior

제안서나 문서를 작성할 때는 다음 메시지를 유지한다.

> 본 프로젝트는 외부 클라우드 LLM에 의존하지 않고 로컬 환경에서 동작하는 LLM 기반 악성코드/의심 파일 분석 자동화 시스템을 목표로 한다. 초기에는 정적 분석 결과와 로컬 LLM을 결합해 의심 파일의 행위와 위험 요소를 해석하고, 이후 RAG 기반 보안 지식 검색과 분석 자동화 기능을 확장한다.

Phase 1 문서에서는 다음 메시지를 유지한다.

> 초기 프로토타입은 악성코드 분석 전체 자동화가 아니라, 200줄 이하 Python 파일을 대상으로 한 코드 리뷰 및 보안 리뷰 MVP이다. AST 기반 정적 분석 결과를 JSON으로 정리하고, Mock LLM 또는 로컬 LLM을 통해 Markdown/JSON 보고서를 생성한다.

제안서 제목은 `Local-based LLM 기반 악성코드 및 의심 파일 분석 자동화 시스템` 또는 `로컬 LLM 기반 악성 파일 정적 분석 및 보안 보고서 자동화 시스템 개발`을 우선 사용한다.

문서에는 검증되지 않은 성능 주장이나 과도한 자동화 표현을 넣지 않는다. 비교 실험, 단계적 확장, 평가 기준을 명확히 적는다.

## Commit and PR Rules

아직 커밋 이력이 없으므로 커밋 메시지는 `Add review pipeline`처럼 짧은 명령형 영어 문장으로 작성한다. PR에는 변경 요약, 검증 명령, 관련 이슈, 모델/의존성/설정 변경 여부를 포함한다.
