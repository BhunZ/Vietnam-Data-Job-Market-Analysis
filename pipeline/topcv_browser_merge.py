"""Merge TopCV JD/skills collected via the Chrome browser into the TopCV Bronze file.

The browser step (Claude-in-Chrome) downloads a JSON map {job_id: {desc, skills,
datePosted, exp, cat}} to the user's Downloads folder. This reads the newest such file
and fills `description_raw` / `skills_raw` / `posted_date_raw` on the existing
`data/bronze/topcv/<snapshot>/all.jsonl`. Re-runnable (idempotent).

Run:  python -m pipeline.topcv_browser_merge [downloads_glob]
"""

from __future__ import annotations

import glob
import json
import os
import sys

from .utils.config import DATA_DIR

def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    pattern = argv[0] if argv else os.path.expanduser("~/Downloads/topcv_jd*.json")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not files:
        print(f"No JD download found matching {pattern}")
        return 1
    jd = json.load(open(files[0], encoding="utf-8"))
    print(f"Loaded {len(jd)} JD entries from {files[0]}")

    path = DATA_DIR / "bronze" / "topcv" / "latest.jsonl"
    rows = [json.loads(l) for l in path.open(encoding="utf-8")]

    filled = 0
    for r in rows:
        info = jd.get(r["source_job_id"])
        if not info:
            continue
        if info.get("desc") and not r.get("description_raw"):
            r["description_raw"] = info["desc"]
            filled += 1
        if info.get("skills") and not r.get("skills_raw"):
            r["skills_raw"] = [s.strip() for s in str(info["skills"]).split(",") if s.strip()]
        if info.get("datePosted") and not r.get("posted_date_raw"):
            r["posted_date_raw"] = info["datePosted"]
        r.setdefault("extra", {})
        r["extra"]["experience_req"] = info.get("exp")
        r["extra"]["occupational_category"] = info.get("cat")

    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    have = sum(1 for r in rows if r.get("description_raw"))
    print(f"Merged: +{filled} JD this run. Coverage {have}/{len(rows)}. Bronze: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
