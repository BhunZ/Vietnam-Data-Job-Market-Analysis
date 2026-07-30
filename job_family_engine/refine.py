"""Stage-2 resolution for postings the open-ended tier-3 vote could not settle.

WHY a second stage instead of more of the same votes: the unresolved cases are not short of opinions —
they are cases where each judge picked a *different defensible* family out of ~20 options (a posting
titled just "Analyst" drew BUSINESS_ANALYST / DATA_ANALYST / RISK_FRAUD_ANALYST). Adding a 4th judge to
the same 20-way question tends to add a 4th answer. So this stage changes the QUESTION, not the number
of voters:

  * the choice set is narrowed to exactly the families the judges actually disputed (usually 2-3),
  * the judge sees the FULL job description instead of the 2,500-char window tier-3 uses,
  * the judge must quote the single most decisive JD sentence, which suppresses title-keyword guessing.

A constrained question with evidence is a genuinely easier task, so agreement rises. Because it is a
different question, re-asking a judge that already voted in tier-3 is legitimate (and it gets its own
cache namespace via REFINE_PROMPT_VERSION).

Decision rule: plurality over stage-2 votes; if stage 2 still splits, the tier-3 votes are added in as
tie-breakers (stage-2 votes count double, being better informed). Anything still tied is left
unresolved rather than settled by coin flip. Every outcome is stamped `refine:<judges>` so the label's
provenance stays auditable.

Run:  python -m pipeline refine
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from pathlib import Path

import pandas as pd

from pipeline.dataset import _io
from pipeline.dataset.llm_clients import JUDGES, _client, _throttle
from pipeline.utils.config import DATA_DIR, get_secrets

from . import llm_judge
from .taxonomy import TAXONOMY_VERSION, families, meta

log = logging.getLogger("job_family_engine.refine")

LABEL = DATA_DIR / "labeling" / "job_family.parquet"
CACHE = DATA_DIR / "labeling" / "refine_cache"
REFINE_PROMPT_VERSION = "1"
JD_CHARS = 6000            # tier-3 uses 2500; the disputed cases are exactly where the tail matters
REFINE_JUDGES = ["cloudflare", "cerebras", "mistral", "groq", "github", "gemini", "qwen"]
MIN_VOTES = 3


def _prompt(candidates: list[str]) -> str:
    fam = families()
    opts = "\n".join(f"- {c}: {fam.get(c, {}).get('name', c)}" for c in candidates if c != "OTHER")
    if "OTHER" in candidates:
        opts += "\n- OTHER: not a data/analytics/AI role at all"
    return (
        "Independent classifiers DISAGREED on this job posting. Your task is to settle it by choosing "
        "exactly one of the disputed options below — do not invent a different code.\n\n"
        f"OPTIONS:\n{opts}\n\n"
        "How to decide:\n"
        "- Judge by what this person actually spends most of their time doing, per the job description, "
        "not by keywords in the title.\n"
        "- If OTHER is an option, pick it only when the primary work is general business, sales, "
        "marketing, finance, operations, HR or teaching, with data/analytics at most a supporting tool. "
        "If the core deliverable is analysis, reporting, BI, pipelines, databases or ML, it is NOT OTHER.\n"
        "- Quote the single most decisive sentence from the description in `evidence`. If you cannot find "
        "a supporting sentence, your choice is probably wrong.\n\n"
        'Return ONLY JSON: {"job_family": "<one option exactly as written>", '
        '"confidence": <0.0-1.0>, "evidence": "<quoted sentence from the JD>", '
        '"reasoning": "<one short sentence>"}'
    )


def _user(job: dict) -> str:
    sk = job.get("skills")
    sk = list(sk) if sk is not None else []
    jd = job.get("jd") or job.get("role_view") or ""
    return (f"TITLE: {job.get('title') or ''}\nSKILLS: {', '.join(map(str, sk))}\n"
            f"FULL DESCRIPTION:\n{str(jd)[:JD_CHARS]}")


def _cache_path(judge_name: str, content_hash: str, cand_key: str) -> Path:
    return CACHE / judge_name / f"{content_hash}_{cand_key}_{REFINE_PROMPT_VERSION}.json"


def _ask(judge_key: str, job: dict, candidates: list[str]) -> dict | None:
    """One constrained vote. Cache-first (before any throttle). None on failure/out-of-set answer."""
    judge = JUDGES.get(judge_key)
    if judge is None:
        return None
    # Hash the candidate set instead of truncating it: "-".join(sorted(...))[:60] collided for real
    # 4-candidate disputes (882 of 5,985 possible sets exceed 60 chars), so one dispute could read back
    # another dispute's answer. Cached records are re-validated against the current candidate set too —
    # previously only the LIVE path checked membership, so a stale cache entry could return a family
    # that was not even on the ballot.
    cand_key = hashlib.sha1("|".join(sorted(candidates)).encode()).hexdigest()[:16]
    cpath = _cache_path(judge.name, job["content_hash"], cand_key)
    if cpath.exists():
        try:
            rec = json.loads(cpath.read_text(encoding="utf-8"))
            if rec.get("job_family") in candidates:
                return rec
            cpath.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            cpath.unlink(missing_ok=True)
    try:
        _throttle(judge_key)
        resp = _client(judge).chat.completions.create(
            model=judge.model, temperature=0, max_tokens=500,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _prompt(candidates)},
                      {"role": "user", "content": _user(job)}],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001
        log.debug("refine %s failed: %s", judge_key, str(exc)[:120])
        return None
    code = str(data.get("job_family", "")).strip().upper().replace(" ", "_")
    if code not in candidates:          # must stay inside the disputed set
        return None
    rec = {"judge": judge.name, "job_family": code,
           "confidence": round(float(data.get("confidence", 0.7) or 0.7), 3),
           "evidence": str(data.get("evidence", ""))[:400],
           "reasoning": str(data.get("reasoning", ""))[:300]}
    cpath.parent.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


def _decide(stage2: list[dict], tier3: list[dict], job: dict) -> dict | None:
    """Plurality on stage-2; tier-3 votes join as weight-1 tie-breakers (stage-2 counts double)."""
    if not stage2:
        return None
    tally = Counter()
    for v in stage2:
        tally[v["job_family"]] += 2
    for v in tier3:
        tally[v["job_family"]] += 1
    if len(stage2) < 2:
        return None                     # never settle a disputed label on a single opinion
    ranked = tally.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None                     # genuinely tied → leave unresolved, do not coin-flip
    fam = ranked[0][0]
    backers = [v for v in stage2 if v["job_family"] == fam]
    if len(backers) < 2:
        return None                     # winner carried by tier-3 weight alone → not a stage-2 verdict
    conf = sum(v["confidence"] for v in backers) / max(len(backers), 1)
    m = meta(fam)
    judges = sorted({llm_judge.provider_key_for(v["judge"]) for v in stage2})
    ev = next((v.get("evidence", "") for v in backers if v.get("evidence")), "")
    reason = next((v.get("reasoning", "") for v in backers), "")
    return {
        "job_id": job["job_id"], "job_family": fam,
        "domain": m.get("domain"), "subdomain": m.get("subdomain"),
        "confidence_score": round(min(0.95, conf), 3),
        "labeling_method": "refine:" + "+".join(judges),
        "llm_votes": json.dumps([{"judge": v["judge"], "job_family": v["job_family"],
                                  "confidence": v["confidence"]} for v in stage2], ensure_ascii=False),
        "reasoning": (f"{reason} | evidence: {ev}")[:300],
        "review_status": "resolved", "taxonomy_version": TAXONOMY_VERSION,
    }


def _pairwise(job: dict, cands: list[str], pool: list[str], tier3: list[dict] | None = None) -> dict | None:
    """Last resort for a 3-way stalemate: a knockout of TWO-option questions.

    Three judges on a two-option question always produce a majority (3 is odd), and a binary choice is
    the easiest, best-grounded question form — notably it turns "which of 20 families" into the question
    that actually divides the judges, e.g. "is this finance work or analytics work?". Candidates are
    sorted first so the bracket is deterministic and the run reproduces.
    """
    order = sorted(cands)
    champion = order[0]
    voters: set[str] = set()
    rounds: list[dict] = []
    for challenger in order[1:]:
        votes = []
        for jk in pool:
            rec = _ask(jk, job, sorted([champion, challenger]))
            if rec:
                votes.append(rec["job_family"])
                voters.add(jk)
                rounds.append(rec)
            if len(votes) >= 3:
                break
        if len(votes) < 2:
            return None            # a 1-vote "majority" is not a majority; leave it unresolved
        champion = Counter(votes).most_common(1)[0][0]
    m = meta(champion)
    return {
        "job_id": job["job_id"], "job_family": champion,
        "domain": m.get("domain"), "subdomain": m.get("subdomain"),
        "confidence_score": 0.6,     # deliberately modest: won a knockout, not a clean consensus
        # Name the judges that ACTUALLY voted (pool[:3] named the first three *configured* judges
        # regardless), and keep the tier-3 + knockout votes so the row stays auditable and a later
        # refine run can still see what was disputed. An empty llm_votes made these rows look
        # unverified to the KPI and unreachable to any future pass.
        "labeling_method": "refine-knockout:" + "+".join(sorted(voters)),
        "llm_votes": json.dumps([{"judge": v["judge"], "job_family": v["job_family"],
                                  "confidence": v["confidence"]}
                                 for v in (list(tier3 or []) + rounds)], ensure_ascii=False),
        "reasoning": f"pairwise knockout among {', '.join(order)} on the full JD",
        "review_status": "resolved", "taxonomy_version": TAXONOMY_VERSION,
    }


def refine_unresolved() -> pd.DataFrame:
    df = pd.read_parquet(LABEL)
    txt = pd.read_parquet(_io.TEXT_DIR / "jobs_text.parquet")
    jobs = {r["job_id"]: r for r in txt.to_dict("records")}
    sec = get_secrets()
    pool = [k for k in REFINE_JUDGES
            if k in JUDGES and getattr(sec, JUDGES[k].key_env, None)]
    if len(pool) < 2:
        raise RuntimeError(f"refine needs >=2 judges with keys; have {pool}")

    todo = df[df["review_status"].isin(["manual_review", "domain_only"])]
    reps, seen = [], set()
    for _, r in todo.iterrows():
        job = jobs.get(r["job_id"])
        if job is None or job["content_hash"] in seen:
            continue
        seen.add(job["content_hash"])
        reps.append((r, job))
    print(f"\n{'='*64}\nREFINE — {len(reps)} disputed jobs | judges: {pool}\n{'='*64}", flush=True)

    updates, still = {}, 0
    for i, (row, job) in enumerate(reps, 1):
        tier3 = json.loads(row["llm_votes"] or "[]")
        cands = sorted({v["job_family"] for v in tier3})
        if len(cands) < 2:
            continue
        stage2: list[dict] = []
        for jk in pool:
            rec = _ask(jk, job, cands)
            if rec:
                stage2.append(rec)
            if len(stage2) >= MIN_VOTES:
                break
        res = _decide(stage2, tier3, job)
        if res is None:                      # stage-2 still tied → knockout of binary questions
            res = _pairwise(job, cands, pool, tier3)
        if res is None:
            still += 1
        else:
            updates[job["content_hash"]] = res
        if i % 5 == 0 or i == len(reps):
            print(f"  {i}/{len(reps)} | resolved {len(updates)} | still disputed {still}", flush=True)

    h_of = {jid: j["content_hash"] for jid, j in jobs.items()}
    n = 0
    for idx, r in df.iterrows():
        h = h_of.get(r["job_id"])
        if h in updates:
            u = updates[h]
            for col in ["job_family", "domain", "subdomain", "confidence_score", "labeling_method",
                        "llm_votes", "reasoning", "review_status"]:
                df.at[idx, col] = u[col]
            n += 1

    _io.write_parquet(df, LABEL, schema_version="job_family/1", produced_by="job_family_engine.refine")
    print(f"\nupdated {n} rows | review: {dict(Counter(df['review_status']))}")
    return df
