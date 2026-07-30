"""BLIND audit of the assigned seniority band.

Why blind: an auditor that can see the current label mostly ratifies it. Here two independent judges are
shown only the title + job description and asked to assign a band themselves; the stored value is
compared afterwards. Only postings where the two auditors AGREE with each other are used as a reference —
if they cannot agree, the posting is genuinely ambiguous and says nothing about our label.

Why stratified by `seniority_source`: that is the hypothesis worth testing. A level word in the title
should be near-perfect; a years-of-experience number the employer typed into a form field should be close
behind; a number scraped out of JD prose is the weakest link and produces 20% of all values. A single
overall accuracy figure would hide exactly the difference that matters.

Auditors are `cerebras` + `mistral`, neither of which decided any of the `llm`-sourced values (those came
from cloudflare/github/groq), so the audit is independent even on that stratum.

Run:  python analysis/audit_seniority.py [--per-stratum 30]
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.dataset.llm_clients import JUDGES, _client, _throttle          # noqa: E402
from pipeline.utils.analysis_base import ANALYSIS_BASE_WHERE, qualified      # noqa: E402
from pipeline.utils.config import DATA_DIR                                   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"
OUT = ROOT / "analysis" / "outputs"
CACHE = DATA_DIR / "labeling" / "audit_cache"
AUDITORS = ["cerebras", "mistral"]
BANDS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager", "Unknown"]
# Ordinal distance for "within one band". Lead and Manager share a rank; they differ in track
# (technical vs people), not in level, so a Lead/Manager swap is not a seniority error.
RANK = {"Intern": 0, "Junior": 1, "Mid": 2, "Senior": 3, "Lead": 4, "Manager": 4}

PROMPT = f"""You read a Vietnamese/English job posting and state the SENIORITY LEVEL it hires for.

Answer with exactly one: {", ".join(BANDS)}

Decide in this order:
1. An explicit level word in the TITLE (intern/thực tập, junior/fresher, senior, lead/trưởng nhóm,
   manager/trưởng phòng/giám đốc).
2. Otherwise the REQUIRED YEARS OF EXPERIENCE: 0-1 years or "no experience needed" -> Junior ·
   2-4 years -> Mid · 5 or more -> Senior.
3. Otherwise the scope: owns a team -> Manager · owns a technical area or mentors -> Senior ·
   executes defined tasks -> Mid.
4. If the posting says nothing about level or experience, answer Unknown. Do not guess.

A task phrase is not a rank: "quản lý dữ liệu"/"data management" is a duty, "Chuyên viên" means
specialist, and "báo cáo cho Trưởng phòng" names who they report TO.

Return ONLY JSON: {{"seniority": "<one option>", "years_min": <integer or null>,
"evidence": "<the exact sentence you used>"}}"""


def _ask(judge_key: str, job_id: str, user: str, cached_only: bool = False) -> dict | None:
    judge = JUDGES.get(judge_key)
    if judge is None:
        return None
    safe = "".join(c if c.isalnum() else "_" for c in job_id)[:100]
    cp = CACHE / judge.name / f"{safe}.json"
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cp.unlink(missing_ok=True)
    if cached_only:
        # A free-tier auditor that has hit its daily cap does not fail fast — it backs off for minutes,
        # so a handful of missing votes can stall the whole report. Reporting from cache keeps the audit
        # reproducible without spending quota; postings missing a vote simply drop out of the reference
        # set, which is the same thing that happens when the two auditors disagree.
        return None
    try:
        _throttle(judge_key)
        resp = _client(judge).chat.completions.create(
            model=judge.model, temperature=0, max_tokens=300,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": PROMPT}, {"role": "user", "content": user}],
        )
        rec = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        return None
    if rec.get("seniority") not in BANDS:
        return None
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-stratum", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cached-only", action="store_true",
                    help="report from cached auditor votes only; never call a provider")
    args = ap.parse_args()

    con = duckdb.connect(str(DB), read_only=True)
    df = con.execute(f"""
        SELECT s.job_id, s.title_clean, s.seniority, s.seniority_source, j.description_raw
        FROM jobs_silver s JOIN jobs j USING (source, source_job_id)
        WHERE {qualified()}
    """).df()
    con.close()

    parts = []
    for src, g in df.groupby("seniority_source"):
        parts.append(g.sample(min(len(g), args.per_stratum), random_state=args.seed))
    sample = pd.concat(parts).reset_index(drop=True)
    print(f"blind audit: {len(sample)} postings | auditors {AUDITORS}")
    print(f"strata: {dict(Counter(sample.seniority_source))}\n", flush=True)

    rows: list[dict] = []
    lock, done = threading.Lock(), [0]

    def work(r):
        # The auditor sees ONLY the posting. The stored band is never in the prompt.
        user = f"TITLE: {r.title_clean or ''}\n\nPOSTING:\n{(r.description_raw or '')[:4000]}"
        votes = [v for v in (_ask(a, r.job_id, user, args.cached_only) for a in AUDITORS) if v]
        with lock:
            rows.append({"job_id": r.job_id, "title": r.title_clean, "stored": r.seniority,
                         "source": r.seniority_source,
                         "a1": votes[0]["seniority"] if len(votes) > 0 else None,
                         "a2": votes[1]["seniority"] if len(votes) > 1 else None,
                         "evidence": (votes[0].get("evidence") or "")[:200] if votes else ""})
            done[0] += 1
            if done[0] % 20 == 0:
                print(f"  {done[0]}/{len(sample)}", flush=True)

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(work, list(sample.itertuples(index=False))))

    res = pd.DataFrame(rows)
    res["reference"] = [a1 if (a1 and a1 == a2) else None for a1, a2 in zip(res.a1, res.a2)]
    usable = res[res.reference.notna()].copy()
    usable["exact"] = usable.stored == usable.reference
    usable["within1"] = [
        s == r or (RANK.get(s) is not None and RANK.get(r) is not None and abs(RANK[s] - RANK[r]) <= 1)
        for s, r in zip(usable.stored, usable.reference)]

    incomplete = int((res.a1.isna() | res.a2.isna()).sum())
    print(f"\n{'='*70}")
    if incomplete:
        print(f"{incomplete}/{len(res)} postings are missing at least one auditor vote "
              f"(provider unavailable) and cannot be scored.")
    print(f"Auditors agreed with each other on {len(usable)}/{len(res)} postings "
          f"({100*len(usable)/max(len(res),1):.0f}%) — only those are used as a reference.")
    print(f"{'='*70}")
    print(f"\nOVERALL: exact {usable.exact.mean()*100:.1f}%  |  within one band "
          f"{usable.within1.mean()*100:.1f}%   (n={len(usable)})")

    print(f"\n{'source':22s} {'n':>4s} {'exact':>7s} {'within1':>8s}")
    for src, g in usable.groupby("source"):
        print(f"{src:22s} {len(g):4d} {g.exact.mean()*100:6.1f}% {g.within1.mean()*100:7.1f}%")

    print("\nDisagreements (stored -> reference):")
    for (s, r), n in Counter(zip(usable[~usable.exact].stored,
                                usable[~usable.exact].reference)).most_common(12):
        print(f"  {n:3d}  {s:8s} -> {r}")

    print("\nExamples of gross errors (more than one band apart):")
    gross = usable[~usable.within1]
    for x in gross.head(10).itertuples():
        print(f"  [{x.source}] stored={x.stored:8s} ref={x.reference:8s} | {str(x.title)[:44]}")
        print(f"      auditor evidence: {str(x.evidence)[:110]}")
    if gross.empty:
        print("  (none)")

    OUT.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT / "seniority_audit.csv", index=False, encoding="utf-8-sig")
    print(f"\n-> {OUT / 'seniority_audit.csv'}")


if __name__ == "__main__":
    main()
