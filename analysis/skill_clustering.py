"""Cluster skill profiles for VN Data/AI job postings.

Business question:
    Do Data/AI jobs in Vietnam form natural skill-profile clusters, and how do
    those clusters compare with the Job Family Engine labels?

Reads `jobs_silver.skills` from DuckDB, keeps the official analysis population,
builds a TF-IDF weighted skill matrix, chooses KMeans k by silhouette score, and
writes analysis-ready CSV artifacts.

Run:
    python analysis/skill_clustering.py
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"
OUT = Path(__file__).resolve().parent / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

SEED = 42


def _parse_skills(raw: object) -> list[str]:
    if not isinstance(raw, str):
        return []
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(values, list):
        return []
    return sorted({s.strip() for s in values if isinstance(s, str) and s.strip()})


def load_jobs() -> pd.DataFrame:
    con = duckdb.connect(str(DB), read_only=True)
    df = con.execute(
        """
        SELECT
            job_id,
            title_clean,
            company,
            job_family,
            jf_domain,
            jf_subdomain,
            seniority,
            city,
            company_type,
            skills,
            n_skills
        FROM jobs_silver
        WHERE job_family IS NOT NULL
          AND job_family != 'OTHER'
          AND is_active
          AND is_duplicate_of IS NULL
        """
    ).df()
    con.close()

    df["skill_list"] = df["skills"].apply(_parse_skills)
    return df.reset_index(drop=True)


def build_skill_matrix(df: pd.DataFrame, min_skill_n: int):
    import numpy as np

    skill_counts = Counter(skill for skills in df["skill_list"] for skill in skills)
    vocab = sorted(skill for skill, n in skill_counts.items() if n >= min_skill_n)
    if len(vocab) < 2:
        raise ValueError(f"Need at least 2 skills after min_skill_n={min_skill_n}; got {len(vocab)}.")

    idx = {skill: i for i, skill in enumerate(vocab)}
    X = np.zeros((len(df), len(vocab)), dtype="float32")
    for row_i, skills in enumerate(df["skill_list"]):
        for skill in skills:
            col_i = idx.get(skill)
            if col_i is not None:
                X[row_i, col_i] = 1.0

    # Drop jobs that only had rare skills removed by the vocabulary threshold.
    keep = X.sum(axis=1) > 0
    X = X[keep]
    kept = df.loc[keep].reset_index(drop=True)

    # Lightweight TF-IDF weighting: common skills still matter, but less dominate.
    doc_freq = X.sum(axis=0)
    idf = np.log((1 + len(kept)) / (1 + doc_freq)) + 1
    X = X * idf
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    X = X / np.where(norms == 0, 1, norms)
    return kept, vocab, X


def choose_k(X, k_min: int, k_max: int) -> tuple[int, pd.DataFrame, object]:
    from sklearn.cluster import KMeans
    from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score

    rows = []
    models = {}
    upper = min(k_max, len(X) - 1)
    for k in range(k_min, upper + 1):
        model = KMeans(n_clusters=k, random_state=SEED, n_init=20)
        labels = model.fit_predict(X)
        rows.append(
            {
                "k": k,
                "silhouette_cosine": round(float(silhouette_score(X, labels, metric="cosine")), 4),
                "calinski_harabasz": round(float(calinski_harabasz_score(X, labels)), 2),
                "davies_bouldin": round(float(davies_bouldin_score(X, labels)), 4),
            }
        )
        models[k] = model
    if not rows:
        raise ValueError(f"No valid k in range {k_min}-{k_max} for n={len(X)}.")

    scores = pd.DataFrame(rows)
    best_k = int(scores.sort_values(["silhouette_cosine", "calinski_harabasz"], ascending=False).iloc[0]["k"])
    return best_k, scores, models[best_k]


def _fmt_counter(counter: Counter[str], total: int, top_n: int) -> str:
    parts = []
    for key, n in counter.most_common(top_n):
        parts.append(f"{key} ({n}, {100 * n / total:.1f}%)")
    return "; ".join(parts)


def summarize_clusters(df: pd.DataFrame, vocab: list[str], X_binary, top_n: int) -> pd.DataFrame:
    rows = []
    overall_skill_share = X_binary.mean(axis=0)
    for cluster_id, part in df.groupby("cluster_id"):
        positions = part.index.to_list()
        cluster_skill_share = X_binary[positions].mean(axis=0)
        top_skill_ids = sorted(
            range(len(vocab)),
            key=lambda i: (cluster_skill_share[i], cluster_skill_share[i] / max(overall_skill_share[i], 1e-9)),
            reverse=True,
        )[:top_n]
        top_skills = "; ".join(
            f"{vocab[i]} ({100 * cluster_skill_share[i]:.0f}%, lift {cluster_skill_share[i] / max(overall_skill_share[i], 1e-9):.1f})"
            for i in top_skill_ids
            if cluster_skill_share[i] > 0
        )
        family_counts = Counter(part["job_family"])
        domain_counts = Counter(part["jf_domain"])
        dominant_family, dominant_n = family_counts.most_common(1)[0]
        rows.append(
            {
                "cluster_id": int(cluster_id),
                "n_jobs": int(len(part)),
                "pct_jobs": round(100 * len(part) / len(df), 1),
                "dominant_family": dominant_family,
                "dominant_family_n": int(dominant_n),
                "dominant_family_share": round(100 * dominant_n / len(part), 1),
                "top_families": _fmt_counter(family_counts, len(part), top_n=5),
                "top_domains": _fmt_counter(domain_counts, len(part), top_n=4),
                "top_skills": top_skills,
            }
        )
    return pd.DataFrame(rows).sort_values("n_jobs", ascending=False).reset_index(drop=True)


def skill_share_by_cluster(df: pd.DataFrame, vocab: list[str], X_binary) -> pd.DataFrame:
    rows = []
    overall_skill_n = X_binary.sum(axis=0)
    overall_skill_share = X_binary.mean(axis=0)

    for cluster_id, part in df.groupby("cluster_id"):
        positions = part.index.to_list()
        cluster_n = len(part)
        cluster_skill_n = X_binary[positions].sum(axis=0)
        cluster_skill_share = cluster_skill_n / cluster_n

        for i, skill in enumerate(vocab):
            if cluster_skill_n[i] == 0:
                continue
            share_overall = overall_skill_share[i]
            rows.append(
                {
                    "cluster_id": int(cluster_id),
                    "skill": skill,
                    "skill_n_in_cluster": int(cluster_skill_n[i]),
                    "cluster_n_jobs": int(cluster_n),
                    "skill_share_in_cluster": round(float(100 * cluster_skill_share[i]), 1),
                    "skill_n_overall": int(overall_skill_n[i]),
                    "total_clustered_jobs": int(len(df)),
                    "skill_share_overall": round(float(100 * share_overall), 1),
                    "lift": round(float(cluster_skill_share[i] / max(share_overall, 1e-9)), 2),
                }
            )

    return (
        pd.DataFrame(rows)
        .sort_values(["cluster_id", "skill_share_in_cluster", "lift", "skill"], ascending=[True, False, False, True])
        .reset_index(drop=True)
    )


def write_findings(
    *,
    base_n: int,
    clustered_n: int,
    min_skill_n: int,
    best_k: int,
    k_scores: pd.DataFrame,
    summary: pd.DataFrame,
) -> None:
    top_rows = "\n".join(
        "| {cluster_id} | {n_jobs} | {pct_jobs} | `{dominant_family}` | {dominant_family_share} | {top_skills} |".format(
            **row
        )
        for row in summary.to_dict("records")
    )
    k_rows = "\n".join(
        f"| {int(row.k)} | {row.silhouette_cosine:.4f} | {row.calinski_harabasz:.2f} | {row.davies_bouldin:.4f} |"
        for row in k_scores.itertuples(index=False)
    )
    doc = f"""# Skill Clustering Findings

Milestone P5 deliverable: clustering skill profiles to test whether Data/AI jobs form natural skill groups, then compare those groups with `job_family`.

## Business Question

Do Vietnamese Data/AI job postings naturally separate into skill-profile clusters, and where do those clusters align or blur across labeled job families?

## Metric

| Metric | Meaning |
|---|---|
| `silhouette_cosine` | Cluster separation on normalized skill vectors; higher is better |
| `dominant_family_share` | Share of the largest `job_family` inside a cluster |
| `top_skills` | Skills with high within-cluster share, with lift versus the overall clustered population |

## Table

Input table: `jobs_silver`

Official analysis filter:

```sql
job_family IS NOT NULL
AND job_family != 'OTHER'
AND is_active
AND is_duplicate_of IS NULL
```

Feature input: `skills` only. `job_family` is used after clustering for interpretation, not as a feature.

## Pipeline

Script: `analysis/skill_clustering.py`

Outputs:

| Artifact | Purpose |
|---|---|
| `analysis/outputs/skill_clusters.csv` | One row per clustered job |
| `analysis/outputs/skill_cluster_summary.csv` | Cluster size, dominant family, top skills |
| `analysis/outputs/skill_cluster_k_selection.csv` | Evidence for selected k |

## Run Evidence

- Official analysis base: {base_n} jobs
- Clustered jobs with usable skills after `min_skill_n={min_skill_n}`: {clustered_n}
- Selected k: {best_k}

### K Selection

| k | silhouette_cosine | calinski_harabasz | davies_bouldin |
|---:|---:|---:|---:|
{k_rows}

### Cluster Summary

| Cluster | Jobs | % | Dominant family | Dominant family share | Top skills |
|---:|---:|---:|---|---:|---|
{top_rows}

## Interpretation

Clustering is used as an unsupervised check, not a replacement for the Job Family Engine. A high dominant-family share means a cluster's skill profile is close to one family. A mixed cluster means the market asks for overlapping skills across families.

## Recommendation

Use the cluster summary together with association rules:

1. Treat repeated top skills inside large clusters as learning bundles.
2. Use mixed clusters to explain why some roles are hard to separate by title alone.
3. Keep `job_family` as the reporting unit, and use clusters as supporting evidence for skill pathways.

## Limitations

- Skill tags record whether a JD mentions a skill, not required proficiency.
- Jobs without usable skill tags after vocabulary filtering are excluded from clustering.
- KMeans forces every job into a cluster, so small or hybrid clusters should be interpreted cautiously.
- This is one snapshot only; do not interpret clusters as a market trend or forecast.
- Salary is not present in the repo, so clusters cannot imply compensation differences.
"""
    (ROOT / "docs" / "SKILL_CLUSTERING_FINDINGS.md").write_text(doc, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster Data/AI job skill profiles.")
    parser.add_argument("--min-skill-n", type=int, default=10, help="Minimum jobs for a skill to enter the vocabulary.")
    parser.add_argument("--k-min", type=int, default=3)
    parser.add_argument("--k-max", type=int, default=8)
    parser.add_argument("--top-n", type=int, default=6)
    args = parser.parse_args()

    jobs = load_jobs()
    base_n = len(jobs)
    skill_jobs = jobs[jobs["skill_list"].map(bool)].reset_index(drop=True)
    clustered, vocab, X = build_skill_matrix(skill_jobs, min_skill_n=args.min_skill_n)

    best_k, k_scores, model = choose_k(X, args.k_min, args.k_max)
    labels = model.predict(X)

    # Binary matrix after vocabulary filtering is easier to explain in cluster summaries.
    import numpy as np

    vocab_idx = {skill: i for i, skill in enumerate(vocab)}
    X_binary = np.zeros((len(clustered), len(vocab)), dtype="float32")
    for row_i, skills in enumerate(clustered["skill_list"]):
        for skill in skills:
            col_i = vocab_idx.get(skill)
            if col_i is not None:
                X_binary[row_i, col_i] = 1.0

    clustered = clustered.copy()
    clustered["cluster_id"] = labels.astype(int)
    cluster_out = clustered[
        [
            "job_id",
            "title_clean",
            "company",
            "job_family",
            "jf_domain",
            "jf_subdomain",
            "seniority",
            "city",
            "company_type",
            "n_skills",
            "cluster_id",
        ]
    ].sort_values(["cluster_id", "job_family", "job_id"])

    summary = summarize_clusters(clustered, vocab, X_binary, top_n=args.top_n)
    skill_share = skill_share_by_cluster(clustered, vocab, X_binary)

    cluster_out.to_csv(OUT / "skill_clusters.csv", index=False, encoding="utf-8")
    summary.to_csv(OUT / "skill_cluster_summary.csv", index=False, encoding="utf-8")
    skill_share.to_csv(OUT / "skill_cluster_skill_share.csv", index=False, encoding="utf-8")
    k_scores.to_csv(OUT / "skill_cluster_k_selection.csv", index=False, encoding="utf-8")
    write_findings(
        base_n=base_n,
        clustered_n=len(clustered),
        min_skill_n=args.min_skill_n,
        best_k=best_k,
        k_scores=k_scores,
        summary=summary,
    )

    print(f"analysis_base {base_n}")
    print(f"analysis_base_with_skills {len(skill_jobs)}")
    print(f"clustered_jobs {len(clustered)}")
    print(f"vocab_skills {len(vocab)}")
    print(f"selected_k {best_k}")
    print(f"outputs {OUT / 'skill_clusters.csv'}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
