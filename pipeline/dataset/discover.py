"""Phase 1 — write `discovery_report.md`: understand the data BEFORE defining taxonomy.

Sections: corpus overview, title n-grams, skill frequency, per-cluster summary,
cluster × current-role_category crosstab (taxonomy-vs-natural-structure mismatch),
OTHER substructure, candidate new branches, and a Risk/Model-Analytics sanity check.

Run:  python -m pipeline discover
"""

from __future__ import annotations

import logging
import re
from collections import Counter

import pandas as pd

from . import _io

log = logging.getLogger("pipeline.dataset.discover")
SCHEMA_VERSION = "discovery_report/1"

_WORD = re.compile(r"[a-zA-Zàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]+")
_STOP = {"the", "and", "for", "of", "in", "a", "to", "with", "senior", "junior", "and/or",
         "intern", "lead", "manager", "chuyên", "viên", "nhân", "kỹ", "sư", "và", "các",
         "cao", "cấp", "cum", "mid", "staff", "principal", "remote", "hybrid"}


def _tokens(s: str) -> list[str]:
    return [w for w in _WORD.findall((s or "").lower()) if w not in _STOP and len(w) > 1]


def _top_title_terms(titles: list[str], n: int = 8) -> list[tuple[str, int]]:
    c = Counter()
    for t in titles:
        toks = _tokens(t)
        c.update(toks)
        c.update(" ".join(p) for p in zip(toks, toks[1:]))  # bigrams
    return c.most_common(n)


def _top_skills(skill_lists, n: int = 8) -> list[tuple[str, int]]:
    c = Counter(s for sk in skill_lists for s in (sk or []))
    return c.most_common(n)


def _fmt(pairs) -> str:
    return ", ".join(f"{k} ({v})" for k, v in pairs) or "—"


def _cluster_table(df: pd.DataFrame, scope_label: str) -> str:
    lines = [f"### {scope_label} — {df['cluster_id'].nunique()} clusters\n",
             "| cluster | n | top titles | top skills | dom. source | dom. lang | dom. role | sil |",
             "|--:|--:|---|---|---|---|---|--:|"]
    for cid, g in df.groupby("cluster_id"):
        titles = g["title"].dropna().tolist()
        dom_src = g["source"].mode().iloc[0] if not g["source"].mode().empty else "—"
        dom_lang = g["lang"].mode().iloc[0] if not g["lang"].mode().empty else "—"
        dom_role = g["role_category"].mode().iloc[0] if not g["role_category"].mode().empty else "—"
        sil = round(g["silhouette_sample"].mean(), 3)
        lines.append(f"| {cid} | {len(g)} | {_fmt(_top_title_terms(titles,6))} | "
                     f"{_fmt(_top_skills(g['skills'],6))} | {dom_src} | {dom_lang} | "
                     f"{dom_role} | {sil} |")
    return "\n".join(lines)


def build_report(text_df: pd.DataFrame, clusters: pd.DataFrame, meta: dict) -> str:
    n = len(text_df)
    # join cluster assignments back to text (scope='all')
    call = clusters[clusters["scope"] == "all"].merge(text_df, on="job_id", how="left")
    cother = clusters[clusters["scope"] == "other"].merge(text_df, on="job_id", how="left")

    L = [f"# Data Discovery Report\n",
         f"_Embedding model: `{meta['embed_model']}` · run_id `{meta['run_id']}` · {n} jobs_\n",
         "> Exploratory. Clusters inform the taxonomy proposal; they do NOT define labels "
         "(embeddings cluster partly by language/boilerplate, not purely by role).\n",
         "## 1. Corpus overview"]
    L.append(f"- Jobs: **{n}** | active: {int(text_df['is_active'].fillna(False).sum())}")
    L.append(f"- By source: {_fmt(Counter(text_df['source']).most_common())}")
    L.append(f"- By language: {_fmt(Counter(text_df['lang']).most_common())}")
    L.append(f"- Current rule `role_category`: {_fmt(Counter(text_df['role_category']).most_common())}")
    L.append(f"- KMeans silhouette by k (all): {meta['silhouette_all']} → best k=**{meta['best_k_all']}**")
    if meta.get("best_k_other"):
        L.append(f"- OTHER subset ({meta['n_other']} jobs) silhouette by k: "
                 f"{meta['silhouette_other']} → best k=**{meta['best_k_other']}**")

    L.append("\n## 2. Title terms (top bigrams/unigrams)")
    L.append(_fmt(_top_title_terms(text_df["title"].dropna().tolist(), 25)))

    L.append("\n## 3. Skill frequency (overall)")
    L.append(_fmt(_top_skills(text_df["skills"], 25)))

    L.append("\n## 4. Clusters over the whole corpus")
    L.append(_cluster_table(call, "ALL jobs"))

    L.append("\n## 5. Cluster × current role_category (taxonomy vs natural structure)")
    ct = pd.crosstab(call["cluster_id"], call["role_category"])
    L.append("\n```\n" + ct.to_string() + "\n```")
    L.append("_Rows that span many role_category columns = the rule label disagrees with "
             "the natural cluster (overlap / mislabeling); a cluster that is mostly OTHER "
             "but coherent = a candidate missing branch._")

    if not cother.empty:
        L.append("\n## 6. OTHER substructure (hidden-branch discovery)")
        L.append(_cluster_table(cother, "OTHER-only jobs"))

    L.append("\n## 7. Candidate new branches + sanity check")
    risk = text_df[text_df["title"].str.contains(
        r"risk|rủi ro|model validation|modeling|modelling|fraud", case=False, na=False)]
    risk_other = risk[risk["role_category"] == "OTHER"]
    L.append(f"- **Risk/Model Analytics**: {len(risk)} titles match risk/model/fraud; "
             f"**{len(risk_other)} are currently OTHER**.")
    if not cother.empty and len(risk_other):
        rc = cother[cother["job_id"].isin(risk_other["job_id"])]["cluster_id"].value_counts()
        if len(rc):
            top_c = rc.index[0]
            conc = cother[cother["cluster_id"] == top_c]
            L.append(f"  - Sanity: {rc.iloc[0]}/{len(risk_other)} land in OTHER-cluster "
                     f"#{top_c} (size {len(conc)}) → branch is detectable, not noise.")
    ai = text_df[text_df["title"].str.contains(
        r"\bai\b|genai|llm|nlp|computer vision|machine learning", case=False, na=False)]
    ai_other = ai[ai["role_category"] == "OTHER"]
    L.append(f"- **AI/GenAI**: {len(ai)} titles match AI/GenAI/LLM/NLP/CV/ML; "
             f"**{len(ai_other)} are currently OTHER** (candidate AI-Engineering branch).")
    L.append("\n_Next: Phase 2 turns these into a taxonomy proposal (ref/taxonomy/"
             "taxonomy_v1.yml) for review at the decision gate._")
    return "\n".join(L)


def run_discover(text_df: pd.DataFrame, clusters: pd.DataFrame, meta: dict) -> str:
    report = build_report(text_df, clusters, meta)
    out = _io.DISCOVERY_DIR / "discovery_report.md"
    _io.write_text(report, out, schema_version=SCHEMA_VERSION, produced_by="dataset.discover")
    log.info("discovery report -> %s", out)
    return report
