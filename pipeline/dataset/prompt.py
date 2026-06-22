"""Build the versioned judge system prompt from the frozen taxonomy + decision tree + codebook.

Assembled from `taxonomy_v2.yml` (functions + handling rules + facet vocab) so the prompt stays
in sync with the label space, plus a compact decision-tree summary and a few borderline rules.
Persisted to `prompts/prompt_v<ver>.txt` + hashed (provenance). The judge returns a JSON object
matching `schema.JudgeAnnotation`.
"""

from __future__ import annotations

import yaml

from ..utils.config import REPO_ROOT
from . import _io
from .schema import TAXONOMY_PATH, vocab

PROMPT_VERSION = "1"
PROMPTS_DIR = REPO_ROOT / "prompts"

# Compact decision tree (mirrors decision_tree_v1.md S0–S8; priority resolves overlap).
_TREE = """\
Decide primary_function by PRIMARY RESPONSIBILITIES (title is only a prior), in this order:
S1 no substantive data/analytics/ML as the main duty (sales/accounting/ops/OLTP-DBA/IT-infra/
   generic software or AI-app dev) -> OTHER. Can't tell from JD -> best guess + annotation_status=unsure_insufficient_info.
S2 primary artifact = data pipeline/platform/warehouse/lake/DataOps/data-governance -> DE  (OLTP DBA admin -> OTHER)
S3 primary artifact = production ML system (serving/MLOps/deploy/monitoring-eng/maintenance) -> MLE
S4 trains/fine-tunes/researches models: NLP/CV/LLM/GenAI modeling -> AIE ; statistical/quant
   (incl risk/credit/fraud model BUILDING, quant model VALIDATION) -> DS
S5 analysis/insight/reporting: BI semantic-model/dashboard DEVELOPMENT -> BI ; data analysis/reporting/ad-hoc -> DA
S6 analyst/BA where requirements/process/stakeholder work dominates over data work -> ANALYTICS_ADJ
S7 dbt/analytics-transformation bridging DE<->DA -> AE
S8 conflicting/balanced signals -> best-supported guess + annotation_status=genuinely_hybrid; fill secondary_functions."""

_RULES = """\
Key rules:
- "mô hình dữ liệu" = data model/schema -> DA/DE; "mô hình" (rủi ro/ML) = ML model -> DS. Do not conflate.
- Model lifecycle: build->DS; serve/deploy/ops/monitor-eng->MLE; quant validation->DS; DATA governance->DE.
- AIE only if the primary artifact is an AI/ML model or model-centric system (train/fine-tune/eval
  NLP/CV/LLM). An app/backend that merely CALLS pre-built AI -> OTHER.
- Bare Business/IT/Process Analyst -> ANALYTICS_ADJ unless data analysis/reporting is the dominant duty
  (then DA/BI). DBA/OLTP admin -> OTHER; DataOps/platform -> DE.
- secondary_functions = other functions with a clear task signal (optional, aids triage)."""


def build_prompt() -> str:
    tax = yaml.safe_load(TAXONOMY_PATH.open(encoding="utf-8"))
    v = vocab()
    funcs = "\n".join(
        f"  {f['code']}: {f['name']} — {f['definition']} "
        f"[include: {f.get('inclusion','')}] [exclude: {f.get('exclusion','')}]"
        for f in tax["functions"]
    )
    return f"""You are an expert annotator classifying Vietnamese/English job postings (Data/AI domain) \
into ONE primary job function. Read the job description and decide by what the role ACTUALLY DOES.

FUNCTIONS (choose exactly one for primary_function):
{funcs}

{_TREE}

{_RULES}

Return ONLY a JSON object with these fields:
  primary_function: one of {sorted(v['functions'])}
  secondary_functions: list (subset of the functions, may be empty; exclude the primary)
  task_tags: list from {sorted(v['task_tags'])}
  artifact: one of {sorted(v['artifacts'])} or null
  data_intensity: one of {sorted(v['data_intensity'])}
  domain: one of {sorted(v['domains'])} or null
  specialization: list (free short tags, may be empty)
  evidence: {{"span": "<verbatim quote from the JD>", "decision_tree_node_id": "<S1..S8>"}}
  confidence: one of {sorted(v['confidence'])}
  annotation_status: one of {sorted(v['statuses'])}
No prose, no markdown — JSON object only."""


def persist_prompt() -> tuple[str, str]:
    text = build_prompt()
    out = PROMPTS_DIR / f"prompt_v{PROMPT_VERSION}.txt"
    _io.write_text(text, out, schema_version=f"prompt/{PROMPT_VERSION}", produced_by="dataset.prompt")
    return text, _io.content_hash(text)


def prompt_hash() -> str:
    return _io.content_hash(build_prompt())
