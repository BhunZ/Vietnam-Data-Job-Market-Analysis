"""Phase 1 — unsupervised clustering to discover the dataset's natural structure.

Runs KMeans at several k (picks best by silhouette) over the whole corpus, and SEPARATELY
over the current OTHER bucket to surface hidden coherent branches (e.g. bank Risk/Model
Analytics). Clustering is EXPLORATORY — it informs the taxonomy, it does NOT define labels
(embeddings cluster partly by language/boilerplate, not purely by role).

Output: one parquet of per-job cluster assignments (scope 'all' and 'other') + a meta dict
(silhouette per k, chosen k) consumed by the discovery report.

Run:  python -m pipeline discover   (clustering is step 3)
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from . import _io

log = logging.getLogger("pipeline.dataset.cluster")

SCHEMA_VERSION = "clusters/1"
SEED = 42
K_ALL = [8, 12, 16, 20]
K_OTHER = [4, 6, 8, 10]


def _matrix(emb: pd.DataFrame) -> np.ndarray:
    return np.asarray(emb["vector"].tolist(), dtype="float32")


def _kmeans_best(X: np.ndarray, ks: list[int]) -> tuple[int, dict, object]:
    """Return (best_k, {k: silhouette}, fitted_model_at_best_k)."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    sils, models = {}, {}
    for k in ks:
        if k >= len(X):
            continue
        km = KMeans(n_clusters=k, random_state=SEED, n_init=10).fit(X)
        sils[k] = round(float(silhouette_score(X, km.labels_)), 4)
        models[k] = km
    best_k = max(sils, key=sils.get)
    return best_k, sils, models[best_k]


def _assignments(emb: pd.DataFrame, X: np.ndarray, km, k: int, scope: str,
                 run_id: str) -> pd.DataFrame:
    from sklearn.metrics import silhouette_samples

    dist = km.transform(X).min(axis=1)
    sil = silhouette_samples(X, km.labels_) if k > 1 else np.zeros(len(X))
    return pd.DataFrame({
        "job_id": emb["job_id"].values,
        "run_id": run_id,
        "algo": "kmeans",
        "k": k,
        "scope": scope,
        "cluster_id": km.labels_.astype(int),
        "dist_to_centroid": dist.round(4),
        "silhouette_sample": sil.round(4),
    })


def cluster_corpus(emb: pd.DataFrame, text_df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    run_id = _io.content_hash("kmeans", str(K_ALL), str(K_OTHER), str(SEED),
                              emb["embed_model"].iloc[0])

    X = _matrix(emb)
    best_k, sils_all, km = _kmeans_best(X, K_ALL)
    log.info("ALL: silhouette by k=%s -> best k=%d", sils_all, best_k)
    parts = [_assignments(emb, X, km, best_k, "all", run_id)]

    # OTHER subset (hidden-branch discovery)
    other_ids = set(text_df.loc[text_df["role_category"] == "OTHER", "job_id"])
    emb_o = emb[emb["job_id"].isin(other_ids)].reset_index(drop=True)
    sils_other, best_k_o = {}, None
    if len(emb_o) >= min(K_OTHER):
        Xo = _matrix(emb_o)
        best_k_o, sils_other, km_o = _kmeans_best(Xo, K_OTHER)
        log.info("OTHER: silhouette by k=%s -> best k=%d", sils_other, best_k_o)
        parts.append(_assignments(emb_o, Xo, km_o, best_k_o, "other", run_id))

    clusters = pd.concat(parts, ignore_index=True)
    meta = {
        "run_id": run_id, "embed_model": emb["embed_model"].iloc[0],
        "silhouette_all": sils_all, "best_k_all": best_k,
        "silhouette_other": sils_other, "best_k_other": best_k_o,
        "n_all": int(len(emb)), "n_other": int(len(emb_o)),
    }
    return clusters, meta


def run_cluster(emb: pd.DataFrame, text_df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    clusters, meta = cluster_corpus(emb, text_df)
    out = _io.DISCOVERY_DIR / f"clusters_kmeans_{meta['run_id']}.parquet"
    _io.write_parquet(clusters, out, schema_version=SCHEMA_VERSION,
                      produced_by="dataset.cluster", config_run_id=meta["run_id"])
    (_io.DISCOVERY_DIR / "cluster_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("clusters -> %s", out)
    return clusters, meta
