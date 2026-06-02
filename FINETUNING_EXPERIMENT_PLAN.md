# GPT-OSS-20B Fine-Tuning Experiment Plan

This document defines the Project NuriLab fine-tuning experiment track.

The Phase 3 Linear issues remain assigned to the team. This experiment track is
focused on preparing and running a local fine-tuning experiment on a machine
with NVIDIA GPU resources.

## 1. Goal

Fine-tune a local LLM to explain malware-like script behavior and produce
structured JSON reports for suspicious code, vulnerability context, and CTI
metadata.

The model is not the final security decision maker. Deterministic analyzer
signals, rule findings, and curated evidence remain the basis for judgement.
The fine-tuned model is used for explanation, TTP mapping, prioritization, and
structured reporting.

## 2. Starting Model

Use the official OpenAI open-weight model as the v0 baseline:

- Model: `openai/gpt-oss-20b`
- Source: Hugging Face model card
- License: Apache 2.0, subject to the gpt-oss usage policy
- Serving / training target: local GPU infrastructure, not OpenAI API

Do not use `gpt-oss-20b-base` as the v0 baseline. Current evidence suggests it
is a community-derived base-like LoRA model, not the official OpenAI baseline.
It may be evaluated later as a comparison target only after provenance,
formatting compatibility, and safety implications are reviewed.

## 3. Target Task

Primary v0 task:

```text
malware-like script behavior explanation
```

The model should receive static analysis results, vulnerability metadata, CTI
context, or curated report snippets and produce structured JSON that explains
suspicious behavior.

The model must not be trained to generate deployable malware, bypass logic,
credential theft workflows, persistence instructions, or exploit execution
steps.

## 4. Dataset Plan

Datasets will be installed and stored on the NVIDIA GPU machine or approved GPU
server storage, not in this Git repository.

The repository may contain scripts, schema definitions, prompts, and evaluation
logic later. It must not contain large downloaded datasets, real malware
payloads, API keys, private CTI, or sensitive data.

### v0: Metadata and Report Data

Allowed v0 sources:

- NVD / NIST CVE data
- CISA KEV catalog
- MITRE ATT&CK STIX / TAXII data
- VirusTotal metadata and reports, subject to API terms
- MalwareBazaar metadata and reports, subject to API terms
- Public CTI reports and defensive malware analysis writeups
- Synthetic suspicious Python snippets created for benign static analysis
- Existing Project NuriLab normalized static analysis outputs

v0 must not store executable malware payloads in this repository.

### v1: Real Sample Handling

Actual malware sample download, unpacking, or storage is a separate v1 track.

Before v1 starts, require:

- isolated analysis environment
- no execution on the development machine
- no sample storage in Git
- controlled network policy
- documented sample handling policy
- owner approval

## 5. JSON Output Contract

v0 fine-tuning output is JSON only.

Use this schema as the first training and evaluation contract:

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

HTML is out of scope for this fine-tuning track. Future HTML reports should be
generated from JSON output.

## 6. Experiment Environment

The first fine-tuning experiments target a single-GPU Linux workstation.

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
- CUDA reported by NVIDIA-SMI: 13.2
- Python: 3.12
- Python package manager: uv

Current serving / inference stack snapshot:

- vLLM: 0.21.0
- torch: 2.11.0+cu130
- torch CUDA runtime: 13.0
- torch CUDA device: NVIDIA RTX A6000
- torch-c-dlpack-ext: 0.1.5
- torchaudio: 2.11.0+cu130
- torchvision: 0.26.0+cu130

PyTorch and training package versions may be adjusted inside the uv environment
to satisfy Unsloth, TRL, CUDA, and gpt-oss compatibility. Any adjustment must be
recorded in the experiment log before training results are compared.

## 7. Training Stack

Run a small PoC comparison before choosing the long-running training path.

Candidate stacks:

- Unsloth QLoRA
- Hugging Face TRL LoRA

v0 hardware assumption:

- single CUDA GPU server
- enough VRAM for `openai/gpt-oss-20b` QLoRA experiments
- datasets stored on the GPU machine or approved mounted storage

Record for each PoC:

- package versions
- PyTorch / CUDA compatibility note
- GPU type and VRAM
- dataset path on the GPU machine
- dataset size
- training command
- peak VRAM
- training time
- output JSON validity
- inference latency

## 8. Evaluation

Primary v0 evaluation metrics:

- JSON parse success rate
- required field completeness
- behavior explanation usefulness
- ATT&CK tactic / technique mapping quality
- severity consistency
- hallucinated TTP rate
- unsafe or overly actionable malware guidance rate

Evaluation candidates:

- held-out NVD / KEV examples
- held-out ATT&CK technique examples
- CyberSecEval-style security benchmarks
- CyberSOCEval-style malware analysis and CTI reasoning benchmarks
- Project NuriLab synthetic suspicious Python fixtures

Do not treat LLM output as final ground truth. Evaluation should compare model
output against curated labels, deterministic analyzer signals, and human review.

## 9. Safety and Storage Rules

- Do not commit real malware samples.
- Do not commit downloaded datasets.
- Do not commit secrets, API keys, private CTI, or private customer data.
- Do not train on private code unless the owner explicitly approves it.
- Do not train outputs that include step-by-step attack execution guidance.
- Do not weaken Project NuriLab's principle that deterministic signals remain
  the decision basis.
- Keep large artifacts, model checkpoints, and raw datasets outside the Git
  repository.

## 10. Initial Experiment Steps

1. Confirm the NVIDIA GPU machine can load `openai/gpt-oss-20b`.
2. Verify vLLM inference on the base model.
3. Create a uv training environment compatible with the selected PoC stack.
4. Prepare a small JSONL dataset from metadata/report-only sources.
5. Run Unsloth QLoRA PoC.
6. Run Hugging Face TRL LoRA PoC on the same small dataset.
7. Compare JSON validity, output quality, VRAM usage, and training time.
8. Choose the v0 training stack.
9. Scale dataset construction only after the PoC path is stable.

## 11. Current Reference Links

- OpenAI gpt-oss help:
  https://help.openai.com/en/articles/11870455-openai-open-weight-models-gpt-oss
- Hugging Face model card:
  https://huggingface.co/openai/gpt-oss-20b
- MITRE ATT&CK data and tools:
  https://attack.mitre.org/resources/attack-data-and-tools/
- NIST NVD:
  https://www.nist.gov/itl/nvd
- CISA KEV catalog:
  https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- MalwareBazaar API:
  https://bazaar.abuse.ch/api/
- VirusTotal API docs:
  https://docs.virustotal.com/docs/api-overview
