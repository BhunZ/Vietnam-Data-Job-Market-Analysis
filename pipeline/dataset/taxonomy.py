"""Phase 2 — generate a DATA-INFORMED taxonomy proposal at ref/taxonomy/taxonomy_v1.yml.

The proposal is a faceted scheme — FUNCTION × DOMAIN × DATA_INTENSITY — seeded by a
domain-knowledge skeleton and refined with evidence from Phase 1 clustering (candidate
branches that the current flat taxonomy has no home for, e.g. bank Risk/Model Analytics
and AI/GenAI engineering). It is a PROPOSAL for the decision gate, not a frozen schema:
nothing downstream (codebook, annotation) runs until the user approves it.

Run: invoked by `python -m pipeline discover --propose-taxonomy` (or directly after review).
"""

from __future__ import annotations

import logging

import pandas as pd
import yaml

from ..utils.config import REPO_ROOT
from . import _io

log = logging.getLogger("pipeline.dataset.taxonomy")
SCHEMA_VERSION = "taxonomy/1"

# FUNCTION level — frozen by the decision-gate rulings (2026-06-18):
#  - classify by PRIMARY RESPONSIBILITIES, not title;
#  - Risk/Decision Analytics is NOT a function → it is a DOMAIN facet (validated: the 34
#    data-heavy risk roles disperse across DS/DA/BI, they do not form a separate function);
#  - AI/GenAI stays in scope but split by function: pure ML/NLP/LLM/CV engineering = data
#    (MLE/AIE); AI application/backend/fullstack = software → OTHER;
#  - bare Business Analyst = ANALYTICS_ADJ unless analytics/reporting is the dominant duty.
_FUNCTIONS = [
    {"code": "DE", "name": "Data Engineering",
     "definition": "Builds/operates data platforms, pipelines, warehouses, ETL/ELT.",
     "inclusion": "data pipelines, ETL/ELT, warehouse/lakehouse, data platform/infra, streaming",
     "exclusion": "generic backend/software dev that merely touches a database (→ OTHER)",
     "typical_skills": ["SQL", "Python", "ETL", "Spark", "Airflow", "Data Warehouse", "dbt"]},
    {"code": "DS", "name": "Data Science",
     "definition": "Statistical modeling, experimentation, predictive/quant modeling.",
     "inclusion": "ML/statistical model building, experimentation, quant risk/credit/fraud models",
     "exclusion": "pure reporting with no modeling (→ DA)",
     "typical_skills": ["Python", "Statistics", "Machine Learning", "SQL"]},
    {"code": "MLE", "name": "ML Engineering",
     "definition": "Productionizes ML models; MLOps, serving, training infra.",
     "inclusion": "model serving/deployment, MLOps, training pipelines, classic ML eng",
     "exclusion": "AI app/backend dev where ML is consumed not built (→ OTHER)",
     "typical_skills": ["Python", "Machine Learning", "Deep Learning", "MLOps"]},
    {"code": "AIE", "name": "AI / GenAI / NLP / CV Engineering",
     "definition": "Pure LLM/GenAI/NLP/Computer-Vision engineering & research (emerging). "
                   "IN SCOPE only when the PRIMARY function is building AI/ML, not shipping an "
                   "app that calls AI. (Discovery: 95 pure vs 14 software-with-AI of 157.)",
     "inclusion": "LLM/GenAI modeling, NLP, computer vision, AI research, agent/model building",
     "exclusion": "AI Software/Backend/Fullstack/App engineer (AI as a feature) → OTHER",
     "typical_skills": ["LLM", "NLP", "Deep Learning", "Python", "Computer Vision"]},
    {"code": "DA", "name": "Data Analysis",
     "definition": "Analyzes data, builds reports/dashboards, answers business questions.",
     "inclusion": "data analysis, reporting/dashboarding, ad-hoc insight, risk/fraud DATA analysis",
     "exclusion": "requirements/process analysis with little data work (→ ANALYTICS_ADJ)",
     "typical_skills": ["SQL", "Data Analysis", "Reporting", "Power BI", "Excel"]},
    {"code": "BI", "name": "Business Intelligence",
     "definition": "BI development/reporting: semantic models, dashboards, BI tooling.",
     "inclusion": "BI semantic models, dashboard development, BI platform work",
     "exclusion": "one-off Excel reporting by a non-BI role (→ DA/ANALYTICS_ADJ)",
     "typical_skills": ["Power BI", "Tableau", "SQL", "Data Modeling", "Reporting"]},
    {"code": "AE", "name": "Analytics Engineering",
     "definition": "Transforms/models data for analytics (dbt-style); bridges DE↔DA. "
                   "(Discovery: tiny + does not separate cleanly — confirm or fold into DE/DA.)",
     "inclusion": "analytics data modeling, dbt, transformation layer for BI/DA",
     "exclusion": "full data-platform engineering (→ DE)",
     "typical_skills": ["dbt", "SQL", "Data Modeling"]},
    {"code": "ANALYTICS_ADJ", "name": "Analytics-adjacent (Business/Product/Risk/Marketing Analyst)",
     "definition": "Analyst/BA roles where requirements/process/stakeholder work dominates. "
                   "Classify here by PRIMARY responsibility; if analytics/reporting dominates, "
                   "reclassify to DA/BI instead. data_intensity is recorded independently.",
     "inclusion": "business/requirements analyst, process analyst, product/marketing analyst "
                  "whose core duty is NOT data analysis",
     "exclusion": "analyst whose dominant duty IS data analysis/reporting (→ DA/BI)",
     "typical_skills": ["SQL", "Excel", "Reporting", "Agile"]},
    {"code": "OTHER", "name": "Not a data role",
     "definition": "No substantive data work (sales/accounting/ops/software-with-AI/etc). "
                   "Kept for counts, excluded from model training.",
     "inclusion": "sales, accounting, ops, generic software/AI-app engineering, etc.",
     "exclusion": "any role whose primary function is a data function above",
     "typical_skills": []},
]

# DOMAIN facet (independent of function). risk/credit/fraud/aml captures the dispersed
# Risk/Decision Analytics work as a SPECIALIZATION of DS/DA/BI rather than its own function.
_DOMAINS = ["banking_finance", "risk_credit_fraud_aml", "product", "marketing_growth",
            "ecommerce_retail", "manufacturing", "consulting_outsourcing",
            "healthcare", "public_sector", "general"]


def _branch_evidence(text_df: pd.DataFrame, clusters: pd.DataFrame, meta: dict) -> dict:
    """Quantify the gate-validation findings from Phase 1 so the proposal cites real numbers."""
    def slist(s):
        return list(s) if s is not None else []

    # AIE split: pure ML/NLP/LLM/CV vs software-with-AI (validates "classify by function")
    ai = text_df[text_df["title"].str.contains(
        r"\bai\b|genai|\bllm\b|\bnlp\b|computer vision|machine learning|deep learning",
        case=False, na=False)]
    soft = r"backend|back-end|front\s?end|fullstack|full[ -]stack|software engineer|developer|\.net|java\b|nodejs|node\.js|react|web\b|mobile|devops|embedded|game"
    pure = r"machine learning engineer|\bml engineer\b|nlp|computer vision|deep learning|data scientist|research scientist|applied scientist|\bai engineer\b|mlops|ai research"
    is_soft = ai["title"].str.contains(soft, case=False, na=False)
    is_pure = ai["title"].str.contains(pure, case=False, na=False)

    # RA: data-heavy risk/credit/fraud roles + how they disperse across functions
    ra = text_df[text_df["title"].str.contains(
        r"risk|rủi ro|credit|fraud|\baml\b|model validation|modeling|modelling|scoring|quản trị rủi ro",
        case=False, na=False)].copy()
    core = ["Machine Learning", "Statistics", "Python", "SQL", "Data Analysis", "Deep Learning"]
    ra_dh = ra[ra["skills"].apply(lambda s: sum(1 for x in core if x in slist(s)) >= 2)]
    return {
        "n_jobs": int(len(text_df)),
        "n_other": int((text_df["role_category"] == "OTHER").sum()),
        "embed_model": meta.get("embed_model"),
        "cluster_run_id": meta.get("run_id"),
        "cluster_note": "clusters split mainly by LANGUAGE+SOURCE (silhouette ~0.07), not role "
                        "→ clustering informs but cannot define labels; content-based labeling needed.",
        "aie_split": {"ai_titles": int(len(ai)), "pure_ml_nlp_cv": int(is_pure.sum()),
                      "software_with_ai": int(is_soft.sum()),
                      "generic_needs_jd": int((~is_pure & ~is_soft).sum())},
        "risk_domain": {"risk_titles": int(len(ra)), "data_heavy": int(len(ra_dh)),
                        "data_heavy_current_roles": ra_dh["role_category"].value_counts().to_dict(),
                        "verdict": "disperses across DS/DA/BI → DOMAIN facet, not a function"},
    }


def build_taxonomy(text_df: pd.DataFrame, clusters: pd.DataFrame, meta: dict) -> dict:
    ev = _branch_evidence(text_df, clusters, meta)
    return {
        "version": 1,
        "status": "PROPOSAL v1 — gate decisions applied (2026-06-18); pending final approval",
        "scheme": "faceted: function × domain × data_intensity",
        "classification_principle": (
            "Classify by PRIMARY RESPONSIBILITIES / function, NOT job title. Title is a prior "
            "only. `domain` and `data_intensity` are INDEPENDENT facets, never the primary "
            "decision rule. Multi-label allowed; record exactly one primary `function`."
        ),
        "gate_decisions": [
            "AI/GenAI/NLP/CV: in scope as AIE ONLY when the primary function is building AI/ML; "
            "AI application/backend/fullstack → OTHER (software).",
            "Risk/Decision Analytics: NOT a function — it is a DOMAIN facet "
            "(risk_credit_fraud_aml). Keep primary function (DS/DA/BI). Promote to a function "
            "later only if volume + separation justify it.",
            "Business Analyst: ANALYTICS_ADJ by default; reclassify to DA/BI only when "
            "analytics/reporting is the dominant duty. data_intensity recorded independently.",
            "AE kept provisionally; fold into DE/DA if it never separates (tiny + low silhouette).",
        ],
        "notes": [
            "Clusters split mainly by language+source, not role → labels must be content-based "
            "(LLM/human reading responsibilities), not assigned from clusters.",
            "`data_intensity` (0..1) lets borderline roles enter WITH a score instead of a hard cut.",
        ],
        "validation_from_discovery": ev,
        "functions": _FUNCTIONS,
        "domains": _DOMAINS,
        "data_intensity": {
            "type": "float 0..1 (independent facet)",
            "guide": {"0.0-0.3": "minimal data work", "0.3-0.6": "mixed/analytics-adjacent",
                      "0.6-1.0": "core data role"},
        },
        "deferred_next": "Phase 3 codebook (inclusion/exclusion already seeded per function) → "
                         "3-judge LLM-first annotation → human Golden. Frozen only after approval.",
    }


def run_taxonomy(text_df: pd.DataFrame, clusters: pd.DataFrame, meta: dict) -> dict:
    tax = build_taxonomy(text_df, clusters, meta)
    out = REPO_ROOT / "ref" / "taxonomy" / "taxonomy_v1.yml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(tax, allow_unicode=True, sort_keys=False), encoding="utf-8")
    _io.manifest_append(out, rows=len(_FUNCTIONS), schema_version=SCHEMA_VERSION,
                        produced_by="dataset.taxonomy")
    log.info("taxonomy proposal -> %s", out)
    return tax
