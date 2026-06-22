"""Phase 1 — embed the role-relevant view of every job.

Uses a LOCAL multilingual sentence-transformer (offline, free, reproducible) so the same
input always yields the same vector — important for a reproducible dataset. Default model
`intfloat/multilingual-e5-base` handles the bilingual VN/EN corpus well; e5 expects a
"passage: " prefix for documents. Output is a parquet of (job_id, vector, provenance).

Run:  python -m pipeline discover   (embedding is step 2)
"""

from __future__ import annotations

import logging

import pandas as pd

from . import _io
from .text import run_build_text

log = logging.getLogger("pipeline.dataset.embed")

DEFAULT_MODEL = "intfloat/multilingual-e5-base"
EMBED_VERSION = "1"
SCHEMA_VERSION = "embeddings/1"


def embed_jobs(model_name: str = DEFAULT_MODEL, text_df: pd.DataFrame | None = None) -> pd.DataFrame:
    from sentence_transformers import SentenceTransformer  # heavy import, lazy

    df = text_df if text_df is not None else run_build_text()
    model = SentenceTransformer(model_name)
    # e5 family expects an instruction prefix on documents.
    prefix = "passage: " if "e5" in model_name.lower() else ""
    inputs = [prefix + v for v in df["role_view"].fillna("").tolist()]
    log.info("embedding %d jobs with %s", len(inputs), model_name)
    vecs = model.encode(inputs, batch_size=32, show_progress_bar=False,
                        normalize_embeddings=True)
    out = pd.DataFrame({
        "job_id": df["job_id"].values,
        "content_hash": df["content_hash"].values,
        "input_view_hash": [_io.content_hash(v) for v in df["role_view"].fillna("")],
        "embed_model": model_name,
        "embed_version": EMBED_VERSION,
        "dim": int(vecs.shape[1]),
        "vector": [v.astype("float32").tolist() for v in vecs],
    })
    return out


def run_embed(model_name: str = DEFAULT_MODEL, text_df: pd.DataFrame | None = None) -> pd.DataFrame:
    emb = embed_jobs(model_name, text_df)
    tag = model_name.split("/")[-1]
    out = _io.DISCOVERY_DIR / f"embeddings_{tag}_v{EMBED_VERSION}.parquet"
    _io.write_parquet(emb, out, schema_version=SCHEMA_VERSION, produced_by="dataset.embed")
    log.info("embeddings: %d x %d -> %s", len(emb), emb["dim"].iloc[0], out)
    return emb
