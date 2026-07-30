"""LLM enrichment for the two `jobs_silver` fields keyword rules cannot finish: seniority and employer
industry. Runs AFTER `silver`, overlays only where the deterministic rules gave up, and records which
source decided each value.

WHY LLM, AND WHY DIFFERENTLY FOR EACH FIELD — measured on the 752-posting analysis base:

* **Seniority.** 127 of the 145 `Unknown` postings (88%) DO state an experience requirement; the regex
  just missed the phrasing ("Minimum 2 years' experience" with a curly apostrophe, "3 years plus of
  experience", or a purely qualitative "ideal for professionals with experience in..."). Reading
  comprehension is exactly the right tool, so the model gets the title + JD and must quote the sentence
  it used.

* **Employer industry.** Only 47 of 264 unclassified postings (18%) contain anything about the employer,
  and most of those matches are the word "doanh nghiệp" inside a task description. **The JD does not hold
  the answer**, so feeding it to a model would just invite invention. The only real signal is brand
  knowledge of the company NAME — which is also where hallucination lives. Two guards: the model must
  answer `unknown` unless it recognises the company (or the name itself states the industry), and
  **two independent judges must agree** or the value stays `unknown`. Disagreement is treated as
  ignorance, not averaged away.

Neither field ever overwrites a rule-derived value: `silver` stays the deterministic baseline, this stage
only fills gaps, and `seniority_source` / `company_type_source` make every value's origin auditable.

Run:  python -m pipeline enrich-llm
"""

from __future__ import annotations

import json
import logging
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import pandas as pd

from ..dataset.llm_clients import JUDGES, _client, _throttle
from ..utils.analysis_base import ANALYSIS_BASE_WHERE
from ..utils.config import DATA_DIR, get_secrets

log = logging.getLogger("pipeline.enrich_llm")

DB = DATA_DIR / "warehouse.duckdb"
CACHE = DATA_DIR / "labeling" / "enrich_cache"
PROMPT_VERSION = "1"

SEN_BANDS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager", "Unknown"]
INDUSTRIES = ["bank_finance", "tech_software", "telecom", "ecommerce", "retail_consumer",
              "manufacturing", "healthcare_pharma", "education", "consulting_audit", "logistics",
              "real_estate_construction", "media_gaming", "energy_agri", "public_sector",
              "recruitment_agency", "unknown"]

# Best-first by measured latency, widest-quota first. `groq8b` is included here even though the
# job-family engine excludes it: its bias there was an unwillingness to answer `OTHER`, which is a
# data-vs-not-data judgement and has nothing to do with reading an experience requirement or recognising
# a brand. Its 14.4k/day ceiling is the largest available, so it carries the bulk of the volume.
POOL = ["groq8b", "cerebras", "github", "sambanova", "cloudflare", "mistral", "groq"]
WORKERS = 10

_SEN_PROMPT = f"""You extract the SENIORITY LEVEL a Vietnamese/English job posting is hiring for.

Answer with exactly one: {", ".join(SEN_BANDS)}

How to decide, in priority order:
1. An explicit level word in the TITLE (intern/thực tập, junior/fresher, senior, lead/trưởng nhóm,
   manager/trưởng phòng/giám đốc).
2. Otherwise the REQUIRED YEARS OF EXPERIENCE stated anywhere in the posting:
   0-1 years or "no experience required" -> Junior · 2-5 years -> Mid · more than 5 years -> Senior.
3. Otherwise the scope described: owning a team -> Manager; owning a technical area or mentoring ->
   Senior; executing defined tasks under supervision -> Mid.
4. If the posting genuinely says nothing about level or experience, answer Unknown. Do NOT guess.

Traps: a task phrase is not a rank. "Quản lý dữ liệu"/"data management" is a duty, so it does NOT make
the job a Manager. "Chuyên viên" means specialist, not senior. "Báo cáo cho Trưởng phòng" describes who
they report TO.

Self-check before answering: if the sentence you are about to put in `evidence` does not actually contain
a level word, a number of years, or a description of scope, then you have no evidence — answer Unknown.
An empty or placeholder field ("Kinh nghiệm: null", "Experience: -") is NOT evidence.

Return ONLY JSON: {{"seniority": "<one option>", "years_min": <integer or null>,
"evidence": "<the exact sentence you used, copied from the posting>", "confidence": <0.0-1.0>}}"""

_CO_PROMPT = f"""You identify what INDUSTRY a Vietnamese employer operates in, from its company name.

Answer with exactly one: {", ".join(INDUSTRIES)}

Rules — read them carefully, they matter more than giving an answer:
- Answer only if you actually RECOGNISE this company, or the name itself states the industry
  (e.g. "... Ngân hàng ...", "... Technology ...", "... Logistics ...").
- If you do not recognise it and the name is generic ("NEYU", "Công ty TNHH ABC"), answer `unknown`.
  `unknown` is a correct, useful answer. A guess is worse than an admission.
- Never infer the industry from what the JOB does. A data-analyst vacancy at a cement maker is
  manufacturing, not tech.
- `recruitment_agency` is for staffing firms and postings that hide the real employer
  (e.g. "Navigos Search's Client").
- Classify the employer's own business, not its customers'.

Return ONLY JSON: {{"industry": "<one option>", "what_they_do": "<max 12 words, or empty if unknown>",
"recognised": <true|false>, "confidence": <0.0-1.0>}}"""


def _cache_path(kind: str, judge_name: str, key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:120]
    return CACHE / kind / judge_name / f"{safe}_{PROMPT_VERSION}.json"


# Judges that failed with a long/daily rate limit during THIS run. Without this, a re-run re-probes a
# dead provider for every remaining item: each attempt costs a ~15s client timeout, which is why a
# supposedly cache-warm replay was slower than the original live run.
_DEAD: set[str] = set()


def _cached(kind: str, judge_key: str, key: str) -> dict | None:
    """Cache probe only — never a live call, never a throttle wait."""
    judge = JUDGES.get(judge_key)
    if judge is None:
        return None
    cp = _cache_path(kind, judge.name, key)
    if not cp.exists():
        return None
    try:
        return json.loads(cp.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        cp.unlink(missing_ok=True)
        return None


def _ask(kind: str, judge_key: str, key: str, system: str, user: str) -> dict | None:
    """One cached call. Cache first; a judge already known dead this run is skipped outright."""
    judge = JUDGES.get(judge_key)
    if judge is None:
        return None
    hit = _cached(kind, judge_key, key)
    if hit is not None:
        return hit
    if judge_key in _DEAD:
        return None
    cp = _cache_path(kind, judge.name, key)
    try:
        _throttle(judge_key)
        resp = _client(judge).chat.completions.create(
            model=judge.model, temperature=0, max_tokens=400,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        rec = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        # Only a DAILY/plan exhaustion retires a judge. A plain per-minute 429 must NOT — with 10 workers
        # those happen constantly and retiring a provider on one would starve the pool within seconds.
        # Per-minute limits are handled by failing over to the next judge and by `_throttle` spacing.
        if any(t in msg for t in ("per day", "requests per day", "daily", "quota", "used up",
                                  "insufficient", "exceeded your current")):
            _DEAD.add(judge_key)
            log.warning("judge %s retired for this run (%s)", judge_key, str(exc)[:80])
        log.debug("%s %s failed: %s", kind, judge_key, str(exc)[:120])
        return None
    rec["_judge"] = judge_key
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


def _pool() -> list[str]:
    sec = get_secrets()
    return [k for k in POOL if k in JUDGES and getattr(sec, JUDGES[k].key_env, None)]


# ---------------------------------------------------------------- seniority ----
def enrich_seniority(con, pool: list[str], only_base: bool) -> pd.DataFrame:
    where = "seniority = 'Unknown'" + (f" AND {ANALYSIS_BASE_WHERE}" if only_base else "")
    rows = con.execute(f"""
        SELECT s.job_id, s.title_clean, j.description_raw
        FROM jobs_silver s JOIN jobs j USING (source, source_job_id)
        WHERE {where.replace('seniority', 's.seniority').replace('job_family', 's.job_family')
                    .replace('is_active', 's.is_active').replace('is_duplicate_of', 's.is_duplicate_of')
                    .replace('jf_review', 's.jf_review')}
    """).fetchall()
    print(f"  seniority: {len(rows)} tin can suy luan", flush=True)
    out = []
    for i, (job_id, title, jd) in enumerate(rows, 1):
        user = f"TITLE: {title or ''}\n\nPOSTING:\n{(jd or '')[:5000]}"
        # Pass 1: any judge's CACHED answer (free). Pass 2 only then goes live.
        rec = next((r for jk in pool
                    if (r := _cached("seniority", jk, job_id)) and r.get("seniority") in SEN_BANDS), None)
        if rec is None:
            for jk in pool:
                rec = _ask("seniority", jk, job_id, _SEN_PROMPT, user)
                if rec and rec.get("seniority") in SEN_BANDS:
                    break
                rec = None
        if rec:
            out.append({"job_id": job_id, "seniority": rec["seniority"],
                        "years_min": rec.get("years_min"),
                        "evidence": str(rec.get("evidence", ""))[:300],
                        "confidence": rec.get("confidence"), "judge": rec.get("_judge")})
        if i % 25 == 0:
            print(f"    {i}/{len(rows)}", flush=True)
    df = pd.DataFrame(out)
    if not df.empty:
        # Models are inconsistent about JSON number types — some return "0.7" as a string, which makes
        # the column dtype `object` and breaks the parquet write at the very end of a long run.
        for col in ("confidence", "years_min"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        print(f"  -> {dict(Counter(df.seniority))}", flush=True)
    return df


# ------------------------------------------------------------------ company ----
def enrich_company(con, pool: list[str], only_base: bool) -> pd.DataFrame:
    where = "company_type = 'unknown' AND company IS NOT NULL" + (
        f" AND {ANALYSIS_BASE_WHERE}" if only_base else "")
    rows = con.execute(f"""
        SELECT DISTINCT company_key, ANY_VALUE(company) AS company
        FROM jobs_silver WHERE {where} GROUP BY company_key
    """).fetchall()
    print(f"  company: {len(rows)} cong ty unique (moi cong ty can 2 judge dong thuan)", flush=True)
    out: list[dict] = []
    lock, done = threading.Lock(), [0]

    def work(row):
        ckey, name = row
        key = ckey or name
        votes = [r for jk in pool
                 if (r := _cached("company", jk, key)) and r.get("industry") in INDUSTRIES][:2]
        if len(votes) < 2:                       # top up with live calls only where cache is short
            seen = {v.get("_judge") for v in votes}
            for jk in pool:
                if jk in seen:
                    continue
                rec = _ask("company", jk, key, _CO_PROMPT, f"COMPANY NAME: {name}")
                if rec and rec.get("industry") in INDUSTRIES:
                    votes.append(rec)
                if len(votes) == 2:
                    break
        if len(votes) < 2:
            with lock:
                done[0] += 1
            return
        # Consensus required: two independent models agreeing on a brand is real evidence, one model's
        # recall is not. On disagreement ask a THIRD judge and take the majority — the same escalation the
        # job-family engine uses. Only a genuine 3-way split stays `unknown`; we never average two
        # different answers into one.
        if votes[0]["industry"] != votes[1]["industry"]:
            seen = {v.get("_judge") for v in votes}
            for jk in pool:
                if jk in seen:
                    continue
                rec = _ask("company", jk, key, _CO_PROMPT, f"COMPANY NAME: {name}")
                if rec and rec.get("industry") in INDUSTRIES:
                    votes.append(rec)
                    break
        tally = Counter(v["industry"] for v in votes)
        top, top_n = tally.most_common(1)[0]
        industry = top if top_n >= 2 else "unknown"
        with lock:
            out.append({"company_key": ckey, "company": name, "company_type": industry,
                        "agreed": top_n >= 2, "n_votes": len(votes),
                        "what_they_do": next((str(v.get("what_they_do", "")) for v in votes
                                              if v["industry"] == industry), "")[:120],
                        "judges": "+".join(str(v.get("_judge")) for v in votes)})
            done[0] += 1
            if done[0] % 25 == 0:
                print(f"    {done[0]}/{len(rows)}", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(work, rows))
    df = pd.DataFrame(out)
    if not df.empty:
        agreed = int(df.agreed.sum())
        print(f"  -> {agreed}/{len(df)} cong ty duoc 2 judge dong thuan "
              f"({len(df)-agreed} bat dong -> giu unknown)", flush=True)
    return df


def export_residual(con) -> Path:
    """Write the still-unclassified employers, ranked by how many postings they account for.

    The residual is long-tailed: a handful of employers carry many postings each, so labelling the top
    rows by hand buys far more coverage per minute than any further automation, and it is real ground
    truth rather than a model's recall. Fill the `industry` column and run `apply_manual()`.
    """
    df = con.execute(f"""
        SELECT company_key, ANY_VALUE(company) AS company, COUNT(*) AS n_postings
        FROM jobs_silver
        WHERE company_type = 'unknown' AND company IS NOT NULL AND {ANALYSIS_BASE_WHERE}
        GROUP BY company_key ORDER BY n_postings DESC, company
    """).df()
    df["industry"] = ""                      # <- fill this in; leave blank to keep unknown
    out = DATA_DIR / "labeling" / "company_industry_todo.csv"

    # NEVER discard hand-filled rows. Two ways this file destroys human work if written naively:
    #   1. a re-run blanks the `industry` column someone spent an hour on;
    #   2. once `apply_manual()` has run, those employers are no longer `unknown`, so the query above
    #      does not return them at all and they silently vanish from the file — taking with them the
    #      only record of WHICH employer was hand-classified as WHAT. That record is load-bearing:
    #      `apply_manual()` reads this file, so after a `silver --force` (which resets company_type)
    #      it is the only way to put the manual values back.
    # So: carry every previously-filled row forward, and keep it even if it is no longer in the residual.
    if out.exists():
        try:
            prev = pd.read_csv(out, encoding="utf-8-sig")
        except Exception:                                        # noqa: BLE001
            prev = None
        if prev is not None and {"company_key", "industry"} <= set(prev.columns):
            filled = prev[prev["industry"].astype(str).str.strip() != ""].copy()
            if not filled.empty:
                done = set(filled["company_key"])
                df = pd.concat([filled, df[~df["company_key"].isin(done)]], ignore_index=True)
                print(f"  carried forward {len(filled)} hand-filled employer(s)")

    df = df.sort_values(["industry", "n_postings"], ascending=[True, False], kind="stable")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    covered = int(df.head(30)["n_postings"].sum())
    print(f"\n  residual: {len(df)} employers -> {out.name}")
    print(f"  labelling just the TOP 30 by hand would cover {covered} postings "
          f"({100*covered/max(int(df.n_postings.sum()),1):.0f}% of the residual)")
    print(f"  valid values: {', '.join(INDUSTRIES)}")
    return out


def apply_manual() -> None:
    """Apply hand-filled industries from `company_industry_todo.csv` (source = 'manual')."""
    src = DATA_DIR / "labeling" / "company_industry_todo.csv"
    if not src.exists():
        print(f"{src.name} not found — run `enrich-llm` first.")
        return
    df = pd.read_csv(src)
    df = df[df["industry"].astype(str).str.strip().isin(INDUSTRIES)]
    df = df[df["industry"] != "unknown"]
    if df.empty:
        print("no hand-filled rows yet (column `industry` is empty).")
        return
    con = duckdb.connect(str(DB))
    con.register("man", df[["company_key", "industry"]])
    con.execute("""UPDATE jobs_silver SET company_type = man.industry,
                   company_type_source = 'manual'
                   FROM man WHERE jobs_silver.company_key = man.company_key""")
    con.unregister("man")
    n = con.execute("SELECT COUNT(*) FROM jobs_silver WHERE company_type_source='manual'").fetchone()[0]
    con.close()
    print(f"applied {len(df)} hand-labelled employers -> {n} postings now source='manual'")


def enrich(only_base: bool = True) -> None:
    pool = _pool()
    if len(pool) < 2:
        raise RuntimeError(f"need >=2 judges with keys in .env; have {pool}")
    con = duckdb.connect(str(DB))
    print(f"\n{'='*64}\nLLM ENRICH — judges: {pool}\n{'='*64}", flush=True)

    sen = enrich_seniority(con, pool, only_base)
    co = enrich_company(con, pool, only_base)

    for col, typ in [("seniority_source", "VARCHAR"), ("company_type_source", "VARCHAR")]:
        con.execute(f"ALTER TABLE jobs_silver ADD COLUMN IF NOT EXISTS {col} {typ}")
    con.execute("UPDATE jobs_silver SET seniority_source = COALESCE(seniority_source, "
                "CASE WHEN seniority = 'Unknown' THEN 'none' ELSE 'rule' END)")
    con.execute("UPDATE jobs_silver SET company_type_source = COALESCE(company_type_source, "
                "CASE WHEN company_type = 'unknown' THEN 'none' ELSE 'rule' END)")

    if not sen.empty:
        keep = sen[sen.seniority != "Unknown"]
        con.register("sen", keep)
        con.execute("""UPDATE jobs_silver SET seniority = sen.seniority, seniority_source = 'llm'
                       FROM sen WHERE jobs_silver.job_id = sen.job_id""")
        con.unregister("sen")
        (DATA_DIR / "labeling").mkdir(parents=True, exist_ok=True)
        sen.to_parquet(DATA_DIR / "labeling" / "seniority_llm.parquet", index=False)
        print(f"  applied seniority to {len(keep)} rows")

    if not co.empty:
        keep = co[co.company_type != "unknown"]
        con.register("co", keep)
        con.execute("""UPDATE jobs_silver SET company_type = co.company_type,
                       company_type_source = 'llm'
                       FROM co WHERE jobs_silver.company_key = co.company_key""")
        con.unregister("co")
        co.to_parquet(DATA_DIR / "labeling" / "company_industry_llm.parquet", index=False)
        print(f"  applied industry to {len(keep)} companies")

    export_residual(con)

    print("\n=== sau enrich ===")
    for q, lab in [("SELECT seniority, COUNT(*) n FROM jobs_silver GROUP BY 1 ORDER BY n DESC", "seniority"),
                   ("SELECT company_type, COUNT(*) n FROM jobs_silver GROUP BY 1 ORDER BY n DESC LIMIT 8",
                    "company_type")]:
        print(f"  {lab}: {dict(con.execute(q).fetchall())}")
    con.close()
