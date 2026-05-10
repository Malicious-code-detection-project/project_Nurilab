# SGLang과 vLLM 비교 분석 리포트

## 목적

본 리포트는 local-based LLM 기반 악성코드/의심 파일 분석 자동화 시스템에서 사용할 LLM 서빙 프레임워크 후보로 SGLang과 vLLM을 비교하기 위한 문서다. 비교 기준은 로컬 GPU 활용성, 멀티 GPU 확장성, 처리량, 지연시간, 모델 호환성, 운영 복잡도, 보안 분석 워크로드 적합성이다.

## 요약

SGLang과 vLLM은 모두 고성능 LLM 추론 및 서빙을 목표로 하는 오픈소스 프레임워크다. 두 프레임워크 모두 단일 GPU와 멀티 GPU 구성을 지원하며, OpenAI 호환 API 형태로 로컬 추론 서버를 구성할 수 있다.

차이는 설계 초점에 있다. vLLM은 PagedAttention 기반 KV cache 메모리 관리와 높은 처리량의 범용 LLM serving에 강점이 있다. SGLang은 구조화된 LLM 프로그램, 복수 generation 호출, JSON/도구 호출, RAG 및 agentic workflow처럼 복잡한 호출 패턴을 효율적으로 실행하는 데 초점이 있다.

## 공통점

| 항목 | 공통 특징 |
| --- | --- |
| 목적 | LLM inference 및 serving 성능 최적화 |
| 배포 방식 | 로컬 서버, API 서버, OpenAI 호환 인터페이스 구성 가능 |
| GPU 지원 | 단일 GPU 및 멀티 GPU 지원 |
| 병렬화 | tensor parallelism 지원 |
| 처리량 최적화 | batching, KV cache 관리, GPU 메모리 활용 최적화 |
| 모델 생태계 | Hugging Face 계열 오픈소스/오픈웨이트 모델 활용 가능 |
| 프로젝트 적합성 | 폐쇄망 또는 로컬 환경에서 LLM 분석 서버로 활용 가능 |

## vLLM 특징

vLLM의 핵심 기술은 PagedAttention이다. PagedAttention 논문은 LLM serving에서 KV cache가 동적으로 증가하고 줄어들며, 비효율적으로 관리될 경우 fragmentation과 중복 저장으로 batch size가 제한된다고 설명한다. vLLM은 OS의 virtual memory와 paging 개념을 차용해 KV cache waste를 줄이고, 같은 latency 수준에서 기존 시스템 대비 높은 throughput을 목표로 한다.

공식 문서 기준 vLLM은 단일 GPU, 단일 노드 멀티 GPU, 멀티 노드 멀티 GPU 구성을 지원한다. 단일 노드 멀티 GPU에서는 `tensor_parallel_size`를 GPU 수에 맞게 설정한다. 멀티 노드에서는 tensor parallelism과 pipeline parallelism을 조합할 수 있으며, Ray 기반 분산 실행을 사용한다.

예시:

```bash
vllm serve <MODEL_PATH> \
  --tensor-parallel-size 4
```

vLLM은 다음 경우에 특히 적합하다.

- 긴 context와 많은 동시 요청을 처리해야 하는 경우
- 단순하고 안정적인 OpenAI compatible serving이 중요한 경우
- GPU 메모리 효율과 throughput을 우선 평가해야 하는 경우
- 멀티 노드 확장과 운영 구성을 명확히 분리해야 하는 경우

## SGLang 특징

SGLang은 논문에서 structured language model program의 효율적 실행을 목표로 제안됐다. 단일 prompt-response serving뿐 아니라 여러 generation 호출, control flow, structured output, tool use, RAG pipeline, multi-turn workflow처럼 복잡한 LLM 애플리케이션을 효율적으로 실행하는 데 초점을 둔다.

SGLang의 핵심 최적화 중 하나는 RadixAttention이다. 이는 prefix/KV cache reuse를 통해 반복되는 prompt prefix나 분기형 generation workflow에서 중복 계산을 줄이는 방향의 최적화다. 공식 문서도 SGLang이 tensor, pipeline, expert, data parallelism 등을 지원한다고 설명한다.

공식 server arguments 기준 SGLang은 `--tp-size` 또는 `--tp`, `--pipeline-parallel-size`, `--data-parallel-size`, `--expert-parallel-size` 등 다양한 병렬화 옵션을 제공한다.

예시:

```bash
python -m sglang.launch_server \
  --model-path <MODEL_PATH> \
  --tp 4
```

SGLang은 다음 경우에 특히 적합하다.

- 분석 파이프라인이 여러 LLM 호출로 구성되는 경우
- JSON 보고서, 구조화 출력, tool call, reasoning parser가 중요한 경우
- RAG, rule 기반 판단, 단계적 분석 prompt를 하나의 workflow로 묶어야 하는 경우
- 동일한 시스템 prompt나 분석 template을 반복 재사용하는 경우

## 주요 차이점

| 비교 항목 | SGLang | vLLM |
| --- | --- | --- |
| 설계 초점 | 구조화된 LLM 프로그램과 복잡한 workflow 실행 | 범용 고처리량 LLM serving |
| 대표 최적화 | RadixAttention, structured output, tool/reasoning workflow 최적화 | PagedAttention, paged KV cache 기반 메모리 효율 |
| 멀티 GPU | tensor/data/pipeline/expert parallelism 지원 | tensor/pipeline parallelism 및 Ray 기반 multi-node 지원 |
| API 사용성 | OpenAI 호환 API와 SGLang native workflow 모두 고려 가능 | OpenAI 호환 API 중심의 serving 구성이 단순 |
| 악성 파일 분석 적합성 | 다단계 분석, RAG, 보고서 생성 workflow에 강점 | 대량 요청 처리, 긴 context, 안정적인 serving에 강점 |
| 운영 복잡도 | 기능이 많은 만큼 실험 설계가 중요 | serving 중심 구성은 상대적으로 명확 |

## 본 프로젝트 관점의 판단

이 프로젝트는 단순 chatbot serving이 아니라 의심 파일 분석 결과를 단계적으로 해석하는 시스템이다. 따라서 최종 시스템은 다음 흐름을 가진다.

```text
파일 입력
-> 정적 분석
-> 문자열/API/섹션/행위 후보 추출
-> RAG 기반 보안 지식 검색
-> LLM 기반 행위 해석
-> 위협 수준 판단
-> 보고서 생성
```

이 흐름에서는 두 프레임워크를 모두 실험 대상으로 유지하는 것이 타당하다.

vLLM은 baseline serving 프레임워크로 적합하다. 모델별 처리량, latency, GPU memory usage를 측정하기 쉽고, OpenAI compatible API 기반으로 애플리케이션과 분리하기 좋다.

SGLang은 분석 workflow가 복잡해질수록 비교 가치가 커진다. 특히 동일한 분석 template을 반복 사용하거나, RAG 결과와 정적 분석 결과를 조합해 structured report를 생성하는 단계에서는 SGLang의 structured generation 및 workflow 최적화 장점을 검증할 필요가 있다.

## 권장 실험 계획

1. 동일 모델을 SGLang과 vLLM에 각각 배포한다.
2. 동일 입력으로 단일 파일 분석 latency를 측정한다.
3. 여러 파일 동시 분석 시 throughput과 GPU memory usage를 측정한다.
4. 긴 정적 분석 결과 입력에서 context 처리 안정성을 비교한다.
5. JSON 보고서 생성, tool call, RAG 결합 workflow에서 출력 품질과 구현 난이도를 비교한다.
6. 단일 GPU, 단일 노드 멀티 GPU, 필요 시 다중 노드 구성을 분리해 측정한다.

## 결론

현재 단계에서는 SGLang과 vLLM 중 하나를 사전에 고정하지 않는다. vLLM은 안정적인 고처리량 serving baseline으로 두고, SGLang은 복잡한 보안 분석 workflow와 구조화 보고서 생성에 대한 비교 후보로 둔다.

최종 선택은 실제 로컬 환경에서의 실험 결과로 결정한다. 판단 기준은 처리량, 응답 지연시간, GPU 메모리 사용량, 모델 호환성, 폐쇄망 배포 편의성, RAG/정적 분석 파이프라인과의 통합 난이도다.

## 핵심 기술 간략 설명

### PagedAttention

PagedAttention은 vLLM의 대표적인 KV cache 관리 기법이다. LLM 추론에서는 생성 토큰이 늘어날수록 request별 KV cache가 계속 커지는데, 이를 연속 메모리로 단순 관리하면 fragmentation과 메모리 낭비가 커진다.

PagedAttention은 운영체제의 virtual memory와 paging 개념처럼 KV cache를 작은 block 단위로 나누어 관리한다. 이를 통해 필요한 만큼 동적으로 할당하고, 요청 간 cache sharing과 copy-on-write를 활용해 GPU 메모리 낭비를 줄인다. 결과적으로 더 큰 batch size와 높은 throughput을 가능하게 하는 것이 핵심 목적이다.

### RadixAttention

RadixAttention은 SGLang의 대표적인 prefix/KV cache reuse 최적화 기법이다. 복잡한 LLM 애플리케이션에서는 동일한 system prompt, few-shot example, RAG context, 분석 template이 여러 요청이나 여러 generation 단계에서 반복되는 경우가 많다.

RadixAttention은 이러한 공통 prefix를 radix tree 형태로 관리해 중복된 prefix 계산을 재사용한다. 즉, 같은 앞부분을 가진 여러 prompt가 있을 때 이미 계산된 KV cache를 재활용하여 latency와 연산량을 줄인다. 이 특성은 다단계 분석, structured output, RAG, agent workflow처럼 반복 prompt 구조가 많은 작업에서 유리하다.

## 참고 자료

- vLLM 공식 문서, Parallelism and Scaling: https://docs.vllm.ai/en/latest/serving/parallelism_scaling.html
- vLLM 공식 문서, Paged Attention: https://docs.vllm.ai/en/v0.18.0/design/paged_attention/
- Kwon et al., "Efficient Memory Management for Large Language Model Serving with PagedAttention", arXiv:2309.06180: https://huggingface.co/papers/2309.06180
- SGLang 공식 문서: https://docs.sglang.ai/
- SGLang 공식 문서, Server Arguments: https://docs.sglang.io/advanced_features/server_arguments.html
- Zheng et al., "SGLang: Efficient Execution of Structured Language Model Programs", NeurIPS 2024 / arXiv:2312.07104: https://mast.stanford.edu/pubs/sglang_efficient_execution_of_structured_language_model_programs/
