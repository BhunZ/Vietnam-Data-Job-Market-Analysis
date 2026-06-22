"""3-judge annotation orchestrator.

Selects jobs (pilot = stratified ~120; full = all), runs the BASE judge pair on each, and calls
the TIEBREAKER judge only when the base pair disagrees on primary_function (OpenRouter quota guard).
Writes one immutable vote record per (job × judge) to `judge_votes_<scope>.jsonl`. Resumable: the
per-judge disk cache means re-runs cost no new API calls for already-annotated (job, judge, prompt).

Run:  python -m pipeline annotate --scope {pilot,full}
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import _io
from .llm_clients import BASE_JUDGES, TIEBREAKER, annotate_one
from .prompt import build_prompt
from .text import run_build_text

log = logging.getLogger("pipeline.dataset.annotate")
TEXT_PATH = _io.TEXT_DIR / "jobs_text.parquet"
MAX_WORKERS = 6


def _load_text() -> pd.DataFrame:
    if TEXT_PATH.exists():
        return pd.read_parquet(TEXT_PATH)
    return run_build_text()


def _select_pilot(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Stratify by the (old rule) role_category so rare classes appear in the pilot."""
    classes = df["role_category"].fillna("OTHER").unique()
    per = max(8, round(n / max(len(classes), 1)))
    parts = [g.sample(min(len(g), per), random_state=seed)
             for _, g in df.groupby(df["role_category"].fillna("OTHER"))]
    return pd.concat(parts).reset_index(drop=True)


def _annotate_with(judge_keys: list[str], job: dict, prompt: str) -> list[dict]:
    return [r for jk in judge_keys if (r := annotate_one(jk, job, prompt)) is not None]


def run_annotate(scope: str = "pilot", n: int = 120, seed: int = 42,
                 tiebreak: bool = True) -> pd.DataFrame:
    df = _load_text()
    jobs_df = _select_pilot(df, n, seed) if scope == "pilot" else df
    jobs = jobs_df.to_dict("records")
    prompt = build_prompt()
    print(f"\n{'='*64}\nANNOTATE ({scope}) — {len(jobs)} jobs × base{BASE_JUDGES}"
          f"{' +tiebreak' if tiebreak else ''}\n{'='*64}")

    # 1) base judge pair on every job (parallel over jobs), with live progress
    votes: list[dict] = []
    total = len(jobs)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for i, recs in enumerate(ex.map(lambda j: _annotate_with(BASE_JUDGES, j, prompt), jobs), 1):
            votes.extend(recs)
            if i % 20 == 0 or i == total:
                print(f"  base progress: {i}/{total} jobs", flush=True)

    # 2) tiebreaker where the base pair DISAGREES, or where a base judge FAILED (<2 votes)
    #    so coverage reaches >=2 judges even when one base call errored.
    n_tb = 0
    if tiebreak:
        prims_by_job: dict[str, set] = {}
        nvotes_by_job: dict[str, int] = {}
        for r in votes:
            prims_by_job.setdefault(r["job_id"], set()).add(r["primary_function"])
            nvotes_by_job[r["job_id"]] = nvotes_by_job.get(r["job_id"], 0) + 1
        need_tb = {j["job_id"] for j in jobs
                   if len(prims_by_job.get(j["job_id"], set())) > 1
                   or nvotes_by_job.get(j["job_id"], 0) < 2}
        for job in jobs:
            if job["job_id"] in need_tb:
                r = annotate_one(TIEBREAKER, job, prompt)
                if r:
                    votes.append(r); n_tb += 1

    out = _io.ANNOTATION_DIR / f"judge_votes_{scope}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in votes:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    _io.manifest_append(out, rows=len(votes), schema_version="judge_votes/1",
                        produced_by=f"dataset.annotate:{scope}")

    vdf = pd.DataFrame(votes)
    print(f"votes: {len(votes)} | jobs: {jobs_df.shape[0]} | tiebreaker calls: {n_tb}")
    if not vdf.empty:
        print("per-judge counts:", vdf["judge"].value_counts().to_dict())
        cov = vdf.groupby("job_id")["judge"].nunique()
        print(f"jobs with <2 judges (failures): {(cov < 2).sum()}")
    print(f"-> {out}")
    return vdf
