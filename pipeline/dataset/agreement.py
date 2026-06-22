"""Consensus + routing from per-judge votes.

For each job: majority primary_function (≥2/3 of judges that voted), agreement stats, and a
routing_tier. set-overlap on secondary_functions ONLY orders the human queue (priority) — it
never resolves or auto-accepts a primary disagreement. No research IAA here (% agreement only).

Run:  python -m pipeline consensus --scope {pilot,full}
"""

from __future__ import annotations

import json
import logging
from collections import Counter

import pandas as pd

from . import _io

log = logging.getLogger("pipeline.dataset.agreement")
_CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def _load_votes(scope: str) -> pd.DataFrame:
    path = _io.ANNOTATION_DIR / f"judge_votes_{scope}.jsonl"
    rows = [json.loads(l) for l in path.open(encoding="utf-8")]
    return pd.DataFrame(rows)


def build_consensus(votes: pd.DataFrame, whitelist: set | None = None) -> pd.DataFrame:
    """One row per job. whitelist = classes whose ≥2/3 consensus may auto-accept (from pilot
    label-QA). whitelist=None ⇒ only unanimous auto-accepts (conservative; used in pilot)."""
    out = []
    for jid, g in votes.groupby("job_id"):
        prims = list(g["primary_function"])
        n = len(prims)
        cnt = Counter(prims)
        top, top_n = cnt.most_common(1)[0]
        unanimous = top_n == n and n >= 2
        majority = top_n * 2 >= n and n >= 2 and top_n > n / 2  # strictly > half
        min_conf = min((_CONF_RANK.get(c, 0) for c in g["confidence"]), default=0)
        any_hybrid = bool((g["annotation_status"] == "genuinely_hybrid").any())
        # secondary union (for human-queue ordering only)
        sec_union = sorted({s for lst in g["secondary_functions"] for s in (lst or [])})

        if unanimous and min_conf >= 1 and not any_hybrid:
            tier = "auto_accept"
        elif (majority and not any_hybrid and min_conf >= 1
              and whitelist is not None and top in whitelist):
            tier = "auto_accept"
        else:
            tier = "human_review"

        out.append({
            "job_id": jid, "n_judges": n,
            "consensus_primary": top if majority else None,
            "unanimous": unanimous, "majority": bool(majority),
            "vote_distribution": json.dumps(dict(cnt), ensure_ascii=False),
            "n_agree": top_n, "min_confidence": min_conf,
            "any_hybrid": any_hybrid, "secondary_union": json.dumps(sec_union, ensure_ascii=False),
            "routing_tier": tier,
        })
    return pd.DataFrame(out)


def write_qa_summary(scope: str, votes: pd.DataFrame, agr: pd.DataFrame) -> None:
    """Markdown QA summary for guideline review (Stage 4.2 input): stats + disagreement cases."""
    text = pd.read_parquet(_io.TEXT_DIR / "jobs_text.parquet").set_index("job_id")
    n = len(agr)
    L = [f"# Pilot QA summary ({scope})\n",
         f"- jobs: {n} | unanimous: {int(agr['unanimous'].sum())} "
         f"({100*int(agr['unanimous'].sum())//max(n,1)}%) | majority: {int(agr['majority'].sum())} | "
         f"no-majority: {int((~agr['majority']).sum())}",
         f"- tiers: {agr['routing_tier'].value_counts().to_dict()}",
         f"- consensus label distribution: {Counter(agr['consensus_primary'].dropna()).most_common()}\n",
         "## Disagreement cases (guideline-review candidates)\n",
         "| job_id | title | judge primaries | snippet |", "|---|---|---|---|"]
    dis = agr[~agr["unanimous"]]
    for jid in dis["job_id"]:
        g = votes[votes["job_id"] == jid]
        prims = " / ".join(f"{r['judge'].split('-')[0]}={r['primary_function']}" for _, r in g.iterrows())
        title = str(text.loc[jid, "title"]) if jid in text.index else ""
        snip = (str(text.loc[jid, "jd"])[:90].replace("\n", " ") if jid in text.index else "")
        L.append(f"| {jid} | {title[:46]} | {prims} | {snip}… |")
    out = _io.ANNOTATION_DIR / f"qa_summary_{scope}.md"
    _io.write_text("\n".join(L), out, schema_version="qa_summary/1", produced_by=f"dataset.agreement:{scope}")
    print(f"-> {out} ({len(dis)} disagreement cases)")


def run_consensus(scope: str = "pilot", whitelist: set | None = None) -> pd.DataFrame:
    votes = _load_votes(scope)
    agr = build_consensus(votes, whitelist)
    out = _io.ANNOTATION_DIR / f"agreement_{scope}.parquet"
    _io.write_parquet(agr, out, schema_version="agreement/1",
                      produced_by=f"dataset.agreement:{scope}")

    n = len(agr)
    print(f"\n{'='*64}\nCONSENSUS ({scope}) — {n} jobs\n{'='*64}")
    print(f"  unanimous : {agr['unanimous'].sum()} ({100*agr['unanimous'].sum()//max(n,1)}%)")
    print(f"  majority  : {agr['majority'].sum()} ({100*agr['majority'].sum()//max(n,1)}%)")
    print(f"  no-majority: {(~agr['majority']).sum()}")
    print(f"  tiers: {agr['routing_tier'].value_counts().to_dict()}")
    # pairwise % agreement among base judges (simple reliability, not research IAA)
    print(f"  consensus label dist: {Counter(agr['consensus_primary'].dropna()).most_common()}")
    print(f"-> {out}")
    write_qa_summary(scope, votes, agr)
    return agr
