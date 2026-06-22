"""Tier-2: embedding similarity to family prototypes (multilingual e5).

Family prototype = embedding of (name + aliases + typical skills). Job vector = e5 of the
role-relevant view (reused from the precomputed discovery embeddings parquet; encoded on the fly
for unseen jobs). Accept a family only when the top match is confident AND clearly ahead of the
runner-up; otherwise defer to Tier-3 (LLM).
"""

from __future__ import annotations

import glob
from functools import lru_cache

import numpy as np
import pandas as pd

from .taxonomy import families

ACCEPT_THRESHOLD = 0.82   # calibrated vs tier-1: T≥0.82 + margin≥0.02 → ~92% agreement
ACCEPT_MARGIN = 0.02      # top1 must beat top2 by this much (margin = precision lever)
_EMB_GLOB = "data/dataset/discovery/embeddings_*.parquet"
_E5_PREFIX = "passage: "


@lru_cache(maxsize=1)
def _job_vectors() -> dict:
    path = sorted(glob.glob(_EMB_GLOB))[-1]
    df = pd.read_parquet(path)
    return {r["job_id"]: np.asarray(r["vector"], dtype="float32") for _, r in df.iterrows()}


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("intfloat/multilingual-e5-base")


@lru_cache(maxsize=1)
def _prototypes() -> tuple:
    fam = {c: m for c, m in families().items() if c != "OTHER"}
    texts = [_E5_PREFIX + f"{m['name']}. " + ", ".join(m["aliases"] + m["typical_skills"])
             for m in fam.values()]
    vecs = _model().encode(texts, normalize_embeddings=True)
    return list(fam.keys()), np.asarray(vecs, dtype="float32")


def _encode_view(text: str) -> np.ndarray:
    v = _model().encode([_E5_PREFIX + (text or "")], normalize_embeddings=True)[0]
    return np.asarray(v, dtype="float32")


def tier2(job_id: str | None, role_view: str | None = None) -> tuple[str | None, float, float]:
    """Return (family_code | None, top_score, margin). None if not confident enough."""
    vecs = _job_vectors()
    jv = vecs.get(job_id) if job_id else None
    if jv is None:
        if not role_view:
            return None, 0.0, 0.0
        jv = _encode_view(role_view)
    codes, proto = _prototypes()
    sims = proto @ jv  # both normalized → cosine
    order = np.argsort(-sims)
    top, second = float(sims[order[0]]), float(sims[order[1]])
    margin = top - second
    if top >= ACCEPT_THRESHOLD and margin >= ACCEPT_MARGIN:
        return codes[order[0]], top, margin
    return None, top, margin
