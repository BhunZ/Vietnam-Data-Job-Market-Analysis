"""Silver layer: normalize + deduplicate the warehouse `jobs` into `jobs_silver`.

Reads the DuckDB `jobs` master (raw fields + state + `extra` JSON), applies the
ref-dictionary normalizers (skills/role/seniority/location/language/company_type), runs
cross-source fuzzy dedup, and writes the `jobs_silver` table. Unmapped skill tags are
logged to data/quality/unmapped_skills.csv for dictionary growth.

Run:  python -m pipeline silver
"""

from __future__ import annotations

import json
import logging
from collections import Counter

import duckdb
import pandas as pd
from rapidfuzz import fuzz

from ..utils.config import DATA_DIR
from . import normalize as N

log = logging.getLogger("pipeline.silver")
DB_PATH = DATA_DIR / "warehouse.duckdb"
DEDUP_THRESHOLD = 90  # rapidfuzz token_set_ratio on accent-stripped clean title


def _normalize_rows(jobs: list[dict]) -> tuple[list[dict], Counter]:
    unmapped = Counter()
    out = []
    for j in jobs:
        extra = json.loads(j.get("extra") or "{}")
        skills_raw = json.loads(j["skills_raw"]) if j.get("skills_raw") else []
        skills, miss = N.normalize_skills(skills_raw, j.get("description_raw"))
        unmapped.update(miss)
        position_label = extra.get("position_label") or extra.get("role_category_hint")
        work_model = extra.get("work_model") or extra.get("work_model_raw")
        city, region, remote = N.normalize_location(j.get("location_raw"), work_model)
        out.append({
            "job_id": f"{j['source']}:{j['source_job_id']}",
            "source": j["source"], "source_job_id": j["source_job_id"],
            "title_clean": N.clean_title(j.get("title_raw")),
            "company": j.get("company_raw"),
            "company_key": N.clean_company(j.get("company_raw")),
            "role_category": N.classify_role(j.get("title_raw"), position_label, skills),
            # seniority from title + source level only (JD scan inflates Manager/Senior)
            "seniority": N.derive_seniority(j.get("title_raw"), extra.get("seniority_label"), None),
            "city": city, "region": region, "remote_flag": remote,
            "skills": skills, "n_skills": len(skills),
            "language_req": N.detect_language_req(j.get("description_raw"),
                                                  extra.get("language_req_raw")),
            "company_type": N.company_type(j.get("company_raw"), j.get("description_raw")),
            "posted_date": j.get("posted_date"), "effective_date": j.get("effective_date"),
            "date_source": j.get("date_source"), "first_seen_date": j.get("first_seen_date"),
            "last_seen_date": j.get("last_seen_date"), "is_active": j.get("is_active"),
            "is_duplicate_of": None,
        })
    return out, unmapped


def _dedup(rows: list[dict]) -> int:
    """Mark cross-source duplicates: same company_key + city + fuzzy-similar title. Survivor
    = earliest effective_date; others get is_duplicate_of = survivor.job_id."""
    by_company: dict[str, list[dict]] = {}
    for r in rows:
        if r["company_key"]:
            by_company.setdefault(r["company_key"], []).append(r)
    n_dups = 0
    for group in by_company.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (str(r["effective_date"] or "9999"), r["job_id"]))
        survivors: list[dict] = []
        for r in group:
            dup_of = None
            title = N._strip_accents(N._norm(r["title_clean"]))
            for s in survivors:
                if s["city"] == r["city"] and fuzz.token_set_ratio(
                        title, N._strip_accents(N._norm(s["title_clean"]))) >= DEDUP_THRESHOLD:
                    dup_of = s["job_id"]
                    break
            if dup_of:
                r["is_duplicate_of"] = dup_of
                n_dups += 1
            else:
                survivors.append(r)
    return n_dups


def run_silver() -> None:
    con = duckdb.connect(str(DB_PATH))
    dfj = con.execute("SELECT * FROM jobs").df()
    jobs = dfj.astype(object).where(pd.notnull(dfj), None).to_dict("records")  # NaN -> None
    rows, unmapped = _normalize_rows(jobs)
    n_dups = _dedup(rows)

    df = pd.DataFrame(rows)
    df["skills"] = df["skills"].map(lambda x: json.dumps(x, ensure_ascii=False))
    df["language_req"] = df["language_req"].map(lambda x: json.dumps(x, ensure_ascii=False))
    con.register("silver_df", df)
    con.execute("DROP TABLE IF EXISTS jobs_silver")
    con.execute("CREATE TABLE jobs_silver AS SELECT * FROM silver_df")
    con.unregister("silver_df")

    # log unmapped skill tags for dictionary growth
    qdir = DATA_DIR / "quality"
    qdir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(unmapped.most_common(), columns=["token", "count"]).to_csv(
        qdir / "unmapped_skills.csv", index=False, encoding="utf-8")

    # ---- report ----
    total = len(rows)
    uniq = total - n_dups
    print(f"\n{'='*64}\nSILVER → jobs_silver  ({total} rows, {uniq} unique sau dedup)\n{'='*64}")
    print("role_category:", dict(Counter(r["role_category"] for r in rows).most_common()))
    non_other = [r for r in rows if r["role_category"] != "OTHER"]
    print(f"  (non-OTHER: {len(non_other)}/{total})")
    print("seniority:", dict(Counter(r["seniority"] for r in rows).most_common()))
    print("region:", dict(Counter(r["region"] for r in rows).most_common()))
    print("company_type:", dict(Counter(r["company_type"] for r in rows).most_common()))
    sk = Counter(s for r in rows for s in r["skills"])
    print(f"distinct skills: {len(sk)} | top 15: {[s for s,_ in sk.most_common(15)]}")
    miss_n = sum(unmapped.values())
    print(f"cross-source duplicates: {n_dups} | unmapped skill tokens: {len(unmapped)} distinct "
          f"({miss_n} total) → {qdir/'unmapped_skills.csv'}")
    nnull = sum(1 for r in rows if not r["skills"])
    print(f"jobs with 0 skills: {nnull}/{total} ({100*nnull//total}%) | "
          f"city resolved: {sum(1 for r in rows if r['city'])}/{total}")
    con.close()
    print(f"\nDone. Table: jobs_silver trong {DB_PATH}")
