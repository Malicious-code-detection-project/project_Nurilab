# GPT-OSS-20B 파인튜닝 실험 계획

> **별도 프로젝트 전달 문서**
>
> 이 문서는 Project NuriLab의 현재 구현 계약이 아니라 파인튜닝 프로젝트로 전달할
> 계획입니다. 파인튜닝 코드, package pin, dataset, training run, adapter,
> checkpoint, 실험 결과는 별도 저장소에서 관리합니다. 실험 전에 모델 제공 상태,
> package 호환성, license, 외부 서비스 약관을 다시 확인해야 합니다.
>
> 영문 병행본은
> [`FINETUNING_EXPERIMENT_PLAN.en.md`](FINETUNING_EXPERIMENT_PLAN.en.md)입니다.
> 두 파일은 같은 Pull Request에서 함께 갱신합니다.

이 문서는 Project NuriLab 본체와 별도 파인튜닝 프로젝트 사이의 경계 및 NVIDIA
GPU 환경에서 수행할 초기 실험 방향을 정의합니다.

## 0. 프로젝트 경계

파인튜닝은 이 저장소와 분리된 프로젝트로 관리합니다.

```text
project_Nurilab/
  - 분석 제품 본체
  - Phase 3 팀 개발
  - deterministic analyzer
  - Local LLM inference 연동
  - JSON / HTML report 생성

nurilab-finetuning/
  - GPT-OSS-20B 파인튜닝 실험
  - dataset manifest 및 converter
  - training script
  - evaluation script
  - adapter / checkpoint 관리 규칙
  - tuned model의 vLLM serving 검증
```

Project NuriLab에는 팀이 전체 방향을 이해하는 데 필요한 이 계획 문서만 유지할 수
있습니다. 실제 파인튜닝 코드, dataset 전처리 job, experiment log, model adapter,
checkpoint, raw dataset, serving experiment는 별도 프로젝트로 이동합니다.

분리 이유:

- Phase 3 제품 개발과 파인튜닝은 owner, risk, release cycle이 다릅니다.
- GPU 전용 환경 관리가 일반 제품 개발 환경을 제약해서는 안 됩니다.
- Raw CTI, malware metadata, model checkpoint, 대용량 artifact를 제품 저장소에
  섞지 않습니다.
- Project NuriLab에서는 deterministic analyzer signal을 판단 근거로 유지하고,
  tuned model은 설명과 보고서 생성을 담당합니다.

## 1. 실험 목표

초기 목표는 security-domain structured explanation task에서 GPT-OSS-20B의
단일 GPU 파인튜닝 가능성을 검증하는 것입니다.

모델 입력 후보:

- 정규화된 정적 분석 결과
- 의심스러운 코드 context
- 취약점 metadata
- CTI metadata

모델 출력:

- 의심 행위 설명
- ATT&CK mapping
- 우선순위
- 구조화된 JSON report

모델은 최종 보안 판단자가 아닙니다. Deterministic analyzer signal, rule finding,
curated evidence가 판단 근거이며, fine-tuned model은 설명, TTP mapping,
우선순위화, 구조화 보고를 담당합니다.

## 2. 시작 모델

v0 baseline:

- Model: `openai/gpt-oss-20b`
- Source: Hugging Face model card
- License: Apache 2.0 및 gpt-oss usage policy 확인 필요
- Serving/training target: OpenAI API가 아닌 로컬 GPU infrastructure

`gpt-oss-20b-base`는 공식 OpenAI baseline이 아니라 community-derived
base-like LoRA model일 가능성이 있으므로 v0 baseline으로 사용하지 않습니다.
향후 provenance, formatting compatibility, safety implication을 검토한 뒤 비교
대상으로만 평가합니다.

실험 시작 시점에는 모델 제공 상태와 license를 다시 확인합니다.

## 3. 대상 태스크

v0 주요 태스크:

```text
malware-like script behavior explanation
```

모델은 정적 분석 결과, vulnerability metadata, CTI context, curated report
snippet을 입력받아 의심 행위를 설명하는 JSON을 출력합니다.

다음 내용을 생성하도록 학습하지 않습니다.

- 실행 가능한 malware
- 우회 logic
- credential theft workflow
- persistence instruction
- exploit 실행 절차

## 4. 데이터셋 계획

Dataset은 이 Git 저장소가 아니라 NVIDIA GPU 장비 또는 승인된 GPU server storage에
설치합니다.

별도 `nurilab-finetuning` 프로젝트에 포함할 수 있는 항목:

- 전처리 script
- schema
- prompt
- dataset manifest
- evaluation logic

어느 저장소에도 다음 항목을 커밋하지 않습니다.

- 대용량 downloaded dataset
- 실제 malware payload
- API key
- private CTI
- 민감 데이터

### v0: 메타데이터 및 보고서 데이터

허용 후보:

- NVD / NIST CVE data
- CISA KEV catalog
- MITRE ATT&CK STIX / TAXII data
- VirusTotal metadata 및 report(API 약관 준수)
- MalwareBazaar metadata 및 report(API 약관 준수)
- 공개 CTI report와 defensive malware analysis write-up
- 무해한 정적 분석을 위해 만든 synthetic suspicious Python snippet
- Project NuriLab의 정규화된 static analysis output

v0에서는 실행 가능한 malware payload를 저장하지 않습니다.

### v1: 실제 샘플 취급

실제 malware sample download, unpacking, storage는 별도 v1 track입니다.

v1 시작 전 필수 조건:

- 격리된 분석 환경
- 개발 장비에서 실행 금지
- Git에 sample 저장 금지
- 통제된 network policy
- 문서화된 sample handling policy
- Owner 승인

## 5. JSON 출력 계약

v0 파인튜닝 출력은 JSON만 사용합니다.

```json
{
  "summary": "string",
  "behavior_explanation": "string",
  "risk_level": "low|medium|high|critical|unknown",
  "malware_like_behaviors": [
    {
      "behavior": "string",
      "evidence": "string",
      "confidence": "low|medium|high"
    }
  ],
  "attack_mapping": [
    {
      "tactic": "string",
      "technique_id": "string",
      "technique_name": "string",
      "evidence": "string"
    }
  ],
  "recommendations": ["string"],
  "limitations": ["string"]
}
```

HTML은 파인튜닝 track의 범위 밖입니다. 향후 HTML report는 JSON output에서
생성합니다.

## 6. 실험 환경

초기 파인튜닝 실험 대상은 single-GPU Linux workstation입니다.

Hardware:

- CPU: Intel(R) Xeon(R) w5-3435X
- RAM: 125 GiB
- SSD: 1 TB
- GPU: NVIDIA RTX A6000
- VRAM: 48 GB

System:

- OS: Ubuntu 24.04 LTS
- NVIDIA-SMI: 595.71.05
- NVIDIA Driver: 595.71.05
- NVIDIA-SMI reported CUDA: 13.2
- Python: 3.12
- Python package manager: uv

기록된 serving/inference stack snapshot:

- vLLM: 0.21.0
- torch: 2.11.0+cu130
- torch CUDA runtime: 13.0
- torch CUDA device: NVIDIA RTX A6000
- torch-c-dlpack-ext: 0.1.5
- torchaudio: 2.11.0+cu130
- torchvision: 0.26.0+cu130

이 값은 계획 작성 당시의 snapshot이며 최신 호환성 보장이 아닙니다. Unsloth, TRL,
CUDA, gpt-oss 호환성을 맞추기 위해 uv 환경의 PyTorch 및 training package 버전을
조정할 수 있습니다. 변경 사항은 결과 비교 전에 experiment log에 기록합니다.

## 7. 학습 스택

장시간 training path를 선택하기 전에 작은 PoC를 비교합니다.

후보:

- Unsloth QLoRA
- Hugging Face TRL LoRA

v0 하드웨어 전제:

- single CUDA GPU server
- `openai/gpt-oss-20b` QLoRA 실험에 충분한 VRAM
- GPU 장비 또는 승인된 mounted storage에 저장된 dataset

각 PoC 기록 항목:

- package version
- PyTorch/CUDA compatibility note
- GPU type 및 VRAM
- GPU 장비의 dataset path
- dataset size
- training command
- peak VRAM
- training time
- output JSON validity
- inference latency

## 8. 평가

v0 주요 평가 지표:

- JSON parse success rate
- required field completeness
- behavior explanation usefulness
- ATT&CK tactic/technique mapping quality
- severity consistency
- hallucinated TTP rate
- unsafe 또는 과도하게 actionable한 malware guidance rate

평가 후보:

- held-out NVD/KEV example
- held-out ATT&CK technique example
- CyberSecEval-style security benchmark
- CyberSOCEval-style malware analysis 및 CTI reasoning benchmark
- Project NuriLab synthetic suspicious Python fixture

LLM output을 ground truth로 사용하지 않습니다. Curated label, deterministic
analyzer signal, human review와 비교합니다.

## 9. 안전 및 저장 규칙

- 실제 malware sample을 커밋하지 않습니다.
- downloaded dataset을 커밋하지 않습니다.
- secret, API key, private CTI, private customer data를 커밋하지 않습니다.
- Owner의 명시적 승인 없이 private code를 학습하지 않습니다.
- 단계별 공격 실행 지침을 포함한 output을 학습하지 않습니다.
- deterministic signal이 판단 근거라는 Project NuriLab 원칙을 약화하지 않습니다.
- 대용량 artifact, model checkpoint, raw dataset은 Git 저장소 밖에 둡니다.

## 10. 별도 프로젝트 골격

```text
nurilab-finetuning/
  pyproject.toml
  uv.lock
  README.md
  AGENTS.md
  configs/
    train/
    eval/
    serving/
  schemas/
    malware_behavior_report.schema.json
  datasets/
    README.md
    manifests/
  scripts/
    prepare_datasets.py
    train_unsloth_qlora.py
    train_trl_lora.py
    evaluate_json_outputs.py
    serve_vllm_adapter.py
  evals/
    fixtures/
    expected/
  experiments/
    README.md
  outputs/
    .gitkeep
```

별도 프로젝트 Git 규칙:

- Code, config, schema, small fixture, dataset manifest는 커밋할 수 있습니다.
- Raw dataset, malware sample, API key, model weight, adapter, checkpoint,
  대용량 generated output은 커밋하지 않습니다.
- Machine-specific path는 ignored `.env` 또는 local config overlay로 관리합니다.
- 재현 가능한 experiment summary는 Markdown 또는 JSON log로 기록합니다.

## 11. 초기 실험 순서

1. 별도 `nurilab-finetuning` 프로젝트 skeleton을 생성합니다.
2. NVIDIA GPU 장비에서 `openai/gpt-oss-20b` load를 확인합니다.
3. Base model의 vLLM inference를 확인합니다.
4. 선택한 PoC stack과 호환되는 uv training environment를 구성합니다.
5. Metadata/report-only source로 작은 JSONL dataset을 준비합니다.
6. Unsloth QLoRA PoC를 실행합니다.
7. 같은 dataset으로 Hugging Face TRL LoRA PoC를 실행합니다.
8. JSON validity, output quality, VRAM, training time을 비교합니다.
9. v0 training stack을 선택합니다.
10. PoC path가 안정화된 뒤 dataset 구성을 확장합니다.
11. 선택한 tuned model은 기존 Local LLM inference boundary를 통해서만 Project
    NuriLab에 연결합니다.

## 12. 참고 링크

- OpenAI gpt-oss help:
  <https://help.openai.com/en/articles/11870455-openai-open-weight-models-gpt-oss>
- Hugging Face model card:
  <https://huggingface.co/openai/gpt-oss-20b>
- MITRE ATT&CK data and tools:
  <https://attack.mitre.org/resources/attack-data-and-tools/>
- NIST NVD:
  <https://www.nist.gov/itl/nvd>
- CISA KEV catalog:
  <https://www.cisa.gov/known-exploited-vulnerabilities-catalog>
- MalwareBazaar API:
  <https://bazaar.abuse.ch/api/>
- VirusTotal API docs:
  <https://docs.virustotal.com/docs/api-overview>
