"""Field-level normalizers driven by the versioned reference dictionaries in ref/.

Pure functions over raw strings → canonical values for the Silver layer:
skills, role_category, seniority, city/region/remote, language_req, company_type, plus
clean helpers for dedup keys. Bilingual (EN/VI) because VNW/CareerViet JDs are Vietnamese.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import yaml

from ..utils.config import REPO_ROOT

REF = REPO_ROOT / "ref"
_WS = re.compile(r"\s+")


def _norm(s) -> str:
    if not isinstance(s, str):
        return ""
    return _WS.sub(" ", s.strip().lower())


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _contains(hay: str, pattern: str) -> bool:
    """Word-boundary match (NOT substring) so 'intern' does not match 'international'.
    \\w (unicode) covers Vietnamese letters, so boundaries are correct for VI text too."""
    if not pattern:
        return False
    return re.search(r"(?<!\w)" + re.escape(pattern) + r"(?!\w)", hay) is not None


@lru_cache(maxsize=1)
def _load(name: str) -> dict:
    with (REF / name).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---- skills -----------------------------------------------------------------
@lru_cache(maxsize=1)
def _skill_index():
    skills = _load("skills_dictionary.yml")["skills"]
    alias_map, jd_terms = {}, {}  # alias(lower)->canonical ; jd term(lower,len>=3)->canonical
    for canon, meta in skills.items():
        names = [canon] + list(meta.get("aliases") or [])
        for a in names:
            al = _norm(a)
            if not al:
                continue
            alias_map[al] = canon
            if len(al) >= 3:  # only safe-length terms scanned in free-text JD
                jd_terms[al] = canon
    # one alternation regex, longest-first, non-alphanumeric boundaries (handles c++, ci/cd, .net)
    terms = sorted(jd_terms, key=len, reverse=True)
    pattern = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(t) for t in terms) + r")(?![a-z0-9])")
    return alias_map, jd_terms, pattern


def normalize_skills(skills_raw, jd_text: str | None) -> tuple[list[str], list[str]]:
    """Return (canonical skills sorted, unmapped raw tags). Combines structured tags +
    free-text JD extraction."""
    alias_map, jd_terms, pattern = _skill_index()
    found, unmapped = set(), []
    for tag in skills_raw or []:
        canon = alias_map.get(_norm(tag))
        if canon:
            found.add(canon)
        elif _norm(tag):
            unmapped.append(tag)
    for m in pattern.findall(_norm(jd_text)):
        found.add(jd_terms[m])
    return sorted(found), unmapped


# ---- role -------------------------------------------------------------------
def classify_role(title, position_label, skills_canonical) -> str:
    hay = _norm(" ".join(filter(None, [title, position_label, " ".join(skills_canonical or [])])))
    for rule in _load("role_keywords.yml")["rules"]:
        if any(_contains(hay, _norm(p)) for p in rule["patterns"]):
            return rule["role"]
    return "OTHER"


# ---- seniority --------------------------------------------------------------
# "3 năm kinh nghiệm" / "at least 5 years of experience" / "2+ years" / "3-5 nam".
_YRS = r"(?:nam|nams|years?|yrs?)"
_EXP = r"(?:kinh nghiem|experience|exp)"
# A range may use hyphen, en-dash or em-dash. Capturing BOTH bounds matters: the old pattern only
# accepted an ASCII hyphen inside an optional group, so "5-7 nam" captured 5 while "3–6 nam" captured 6 —
# identical requirements landing in opposite bands. Both bounds are captured here and the LOWER one is
# used, because a range states the minimum the employer will accept.
_RANGE = r"(?:\s*[-–—]\s*(\d{1,2}))?"
_OVER = r"(?:tren|hon|over|more than|at least|toi thieu|minimum|min\.?)"
_YEARS = re.compile(
    rf"(\d{{1,2}})\s*(\+?)\s*{_RANGE}\s*{_YRS}\b[^.]{{0,40}}?{_EXP}"
    rf"|{_EXP}[^.]{{0,40}}?(\d{{1,2}})\s*(\+?)\s*{_RANGE}\s*{_YRS}\b",
    re.I,
)
# "công ty có 20 năm kinh nghiệm trong ngành" is the EMPLOYER's tenure, not a requirement. Without this
# guard a boilerplate company blurb pushed postings to Senior.
_TENURE = re.compile(
    rf"(?:cong ty|tap doan|chung toi|we|our (?:company|team)|thanh lap|founded)"
    rf"[^.]{{0,60}}?\d{{1,2}}\s*{_YRS}", re.I)


# Ordinal rank for comparing bands. Lead and Manager share a rank: they differ in track (technical vs
# people), not in level, so neither outranks the other.
_BAND_RANK = {"Intern": 0, "Junior": 1, "Mid": 2, "Senior": 3, "Lead": 4, "Manager": 4}

# Level words that appear written solid in real titles, checked against the de-spaced title. Only
# unambiguous compounds belong here — a short stem would fire inside unrelated words.
_SOLID_LEVEL = [
    ("teamleader", "Lead"), ("teamlead", "Lead"), ("techlead", "Lead"), ("projectlead", "Lead"),
    ("groupleader", "Lead"), ("seniormanager", "Manager"), ("headof", "Manager"),
]


def years_to_band(years: float | int | None) -> str | None:
    """Years of required experience -> band. Single definition, shared by the JD regex, the structured
    source fields, and the LLM cross-check, so the three can never disagree on the cut-points.

    Cut-points: <=1 Junior · 2-4 Mid · >=5 Senior. The old code used `<=5 -> Mid`, which put a
    "5-7 years" posting in Mid and contradicted the LLM prompt's own ">5 -> Senior" rule.
    """
    if years is None:
        return None
    try:
        y = float(years)
    except (TypeError, ValueError):
        return None
    if y < 0:                    # VietnamWorks encodes "unspecified" as -1
        return None
    if y <= 1:
        return "Junior"
    if y < 5:
        return "Mid"
    return "Senior"


def _years_from_text(text: str) -> float | None:
    """Extract a required-years number from JD prose, or None.

    Used only when no title pattern matched. Handles "3 nam kinh nghiem", "5 years of experience",
    "2+ yrs exp", "3-5 nam" and en-dash ranges, takes the LOWER bound of a range (the minimum the
    employer accepts), treats "5+"/"tren 5" as 5, and refuses employer-tenure blurbs.
    """
    if _TENURE.search(text):
        text = _TENURE.sub(" ", text)
    m = _YEARS.search(text)
    if not m:
        return None
    # groups: (lo, plus, hi) for the first alternative, then the same three for the second
    g = m.groups()
    lo = g[0] if g[0] else g[3]
    if lo is None:
        return None
    try:
        return float(int(lo))
    except ValueError:
        return None


def _years_to_band(text: str) -> str | None:
    """Back-compat wrapper: read a requirement out of prose and band it."""
    return years_to_band(_years_from_text(text))


def years_from_extra(extra: dict | None) -> float | None:
    """Required years of experience from the SOURCE's own structured field, if it has one.

    Every board except ITviec and CareerViet ships this as a form field, and it is the most reliable
    signal available — the employer typed it into a numeric input, so there is no phrasing to misparse:
      * VietnamWorks `years_of_experience` (int; -1 = unspecified)
      * TopCV `experience_req.monthsOfExperience` (schema.org JobPosting)
      * Glints `min_years_exp` / `max_years_exp`
    Reading these resolves 19 of the 24 postings that were still `Unknown` after title patterns and the
    JD regex, without a single LLM call. The remaining 5 genuinely state nothing.
    """
    if not isinstance(extra, dict):
        return None
    v = extra.get("years_of_experience")
    if isinstance(v, (int, float)) and v >= 0:
        return float(v)
    v = extra.get("min_years_exp")
    if isinstance(v, (int, float)) and v >= 0:
        return float(v)
    req = extra.get("experience_req")
    if isinstance(req, dict):
        m = req.get("monthsOfExperience") or req.get("months_of_experience")
        if isinstance(m, (int, float)) and m >= 0:
            return float(m) / 12.0
    if isinstance(req, (int, float)) and req >= 0:
        return float(req)
    return None


def derive_seniority_detail(title, seniority_label, jd_head, extra=None) -> tuple[str, str]:
    """Return (band, source) where source is `rule_title` / `rule_years_source` / `rule_years_jd` / `none`.

    The source is returned separately because collapsing it into one `rule` label hid that 28% of all
    seniority values came from a regex over JD prose — the very input the redesign excluded from pattern
    matching. A reader of `gold_seniority` must be able to see which evidence produced each value.

    Evidence order: an explicit level word in the title (it names the role) > the source's own structured
    years field (a numeric form input) > a years requirement parsed out of JD prose > admit ignorance.
    """
    cfg = _load("seniority_rules.yml")
    hay = _norm(" ".join(filter(None, [title, str(seniority_label or "")])))
    for rule in cfg["rules"]:
        if any(_contains(hay, _norm(p)) for p in rule["patterns"]):
            return rule["seniority"], "rule_title"
    # Level words written solid: word-boundary matching cannot see "leader" inside "Teamleader", so
    # "Data Analyst Teamleader" fell through to the years signal and was reported Junior. Checked against
    # the de-spaced title, and kept to an unambiguous list.
    solid = _fold_ascii(hay).replace(" ", "").replace("-", "")
    for needle, band_name in _SOLID_LEVEL:
        if needle in solid:
            return band_name, "rule_title"

    # Both years signals, when present, are banded and the HIGHER one wins.
    #
    # A blind two-auditor audit put `rule_years_source` at 76% exact — the WORST tier, below even the JD
    # regex (91%) — and 11 of 12 sampled disagreements had the structured field LOWER than the JD
    # ("AI Engineer | Junior/Middle": form field 1 year, JD asks 3). The form field is a floor the
    # employer will accept, not the requirement, so reading it literally understates the level.
    src_band = years_to_band(years_from_extra(extra))
    jd_band = _years_to_band(_fold_ascii(_norm(jd_head or ""))[:6000])
    if src_band and jd_band:
        if _BAND_RANK.get(jd_band, -1) > _BAND_RANK.get(src_band, -1):
            return jd_band, "rule_years_jd"
        return src_band, "rule_years_source"
    if src_band:
        return src_band, "rule_years_source"
    if jd_band:
        return jd_band, "rule_years_jd"
    return cfg.get("default", "Unknown"), "none"


def derive_seniority(title, seniority_label, jd_head) -> str:
    """Seniority from the TITLE and the source's own level label — not from JD prose.

    The JD is excluded from pattern matching on purpose. It describes the work, so it is full of words
    that look like levels: "quản lý dữ liệu" (data management) matched `quản lý` -> Manager, and phrases
    like "senior stakeholders" or "báo cáo trưởng phòng" matched too. With the JD head included, Manager
    ballooned to 301 of 1,701 postings. The JD is still used for the years-of-experience fallback, which
    is a genuine requirement statement rather than a task description.
    """
    cfg = _load("seniority_rules.yml")
    hay = _norm(" ".join(filter(None, [title, str(seniority_label or "")])))
    for rule in cfg["rules"]:
        if any(_contains(hay, _norm(p)) for p in rule["patterns"]):
            return rule["seniority"]
    # No explicit level word in the title. Read the stated experience requirement, then admit ignorance
    # rather than defaulting everyone to Mid.
    wide = _strip_accents(_norm(jd_head or ""))[:2000]
    return _years_to_band(wide) or cfg.get("default", "Unknown")


# ---- location ---------------------------------------------------------------
# canonical city -> (region, accent-stripped patterns to detect it)
_CITY = {
    "Hồ Chí Minh": ("South", ["ho chi minh", "hcm", "sai gon", "saigon", "tphcm", "tp hcm"]),
    "Hà Nội": ("North", ["ha noi", "hanoi"]),
    "Đà Nẵng": ("Central", ["da nang", "danang"]),
    "Bình Dương": ("South", ["binh duong"]),
    "Đồng Nai": ("South", ["dong nai"]),
    "Cần Thơ": ("South", ["can tho"]),
    "Bắc Ninh": ("North", ["bac ninh"]),
    "Hưng Yên": ("North", ["hung yen"]),
    "Hải Phòng": ("North", ["hai phong"]),
    "Bắc Giang": ("North", ["bac giang"]),
    "Vĩnh Phúc": ("North", ["vinh phuc"]),
    "Quảng Nam": ("Central", ["quang nam"]),
    "Khánh Hòa": ("Central", ["khanh hoa", "nha trang"]),
    "Huế": ("Central", ["hue", "thua thien"]),
}
_REMOTE = ["remote", "tu xa", "work from home", "wfh", "hybrid"]


def normalize_location(location_raw, work_model) -> tuple[str | None, str | None, bool]:
    text = _strip_accents(_norm(location_raw))
    city = region = None
    best_pos = 10**9
    for canon, (reg, pats) in _CITY.items():
        for p in pats:
            i = text.find(p)
            if i != -1 and i < best_pos:  # first-appearing city = primary
                best_pos, city, region = i, canon, reg
    wm = _strip_accents(_norm(work_model))
    remote = any(r in wm for r in ["remote", "hybrid"]) or any(r in text for r in _REMOTE)
    return city, region, remote


# ---- language requirement ---------------------------------------------------
_LANG = {"EN": ["tieng anh", "english", "toeic", "ielts"],
         "JP": ["tieng nhat", "japanese", "jlpt", "n1", "n2", "n3"],
         "KO": ["tieng han", "korean", "topik"]}


def detect_language_req(jd_text, lang_label) -> list[str]:
    text = _strip_accents(_norm(" ".join(filter(None, [jd_text or "", str(lang_label or "")]))))
    return [code for code, kws in _LANG.items() if any(k in text for k in kws)]


# ---- company ----------------------------------------------------------------
_LEGAL = re.compile(
    r"\b(công ty|cong ty|cổ phần|co phan|tnhh|jsc|ltd|co\.?,?\s*ltd|corporation|corp|inc|"
    r"company|việt nam|viet nam|vietnam|group|tập đoàn|tap doan|mtv|một thành viên)\b",
    re.I)


# Scraper badges that end up glued to the employer name and spawn a duplicate key.
_BADGE = re.compile(r"^\s*(pro|hot|urgent|top|verified)\s+", re.I)

# Brand aliases -> one canonical key. Dedup groups by `company_key`, so an employer written several ways
# is several employers and its cross-posted vacancies never collapse: MB Bank appeared as
# "NGÂN HÀNG TMCP QUÂN ĐỘI – MBBANK" (41), "MBBANK" (23), "MB Bank" (20) and "Ngân Hàng TMCP Quân Đội" (7)
# — 91 postings under four keys, with byte-identical vacancies cross-posted to topcv/topdev/vietnamworks
# surviving dedup. Each entry is (accent-folded substring to look for, canonical key).
_BRAND_ALIASES = [
    ("mbbank", "mb bank"), ("ngan hang tmcp quan doi", "mb bank"),
    ("ngan hang quan doi", "mb bank"), ("mb ageas", "mb bank"),
    ("viettel post", "viettel post"), ("buu chinh viettel", "viettel post"),
    ("techcombank", "techcombank"), ("vpbank", "vpbank"), ("vietinbank", "vietinbank"),
    ("vietcombank", "vietcombank"), ("agribank", "agribank"), ("sacombank", "sacombank"),
    ("tpbank", "tpbank"), ("pvcombank", "pvcombank"), ("abbank", "abbank"),
    ("ngan hang tmcp ky thuong", "techcombank"), ("ngan hang tmcp viet nam thinh vuong", "vpbank"),
    ("ngan hang tmcp cong thuong", "vietinbank"), ("ngan hang tmcp ngoai thuong", "vietcombank"),
    ("ngan hang tmcp tien phong", "tpbank"), ("ngan hang tmcp an binh", "abbank"),
    ("kinh doanh f88", "f88"), ("f88", "f88"),
    ("vang bac da quy phu nhuan", "pnj"), ("pnj", "pnj"),
    ("the coffee house", "the coffee house"),
    ("fpt software", "fpt software"), ("fpt telecom", "fpt telecom"),
    ("fpt retail", "fpt retail"), ("long chau", "fpt long chau"),
    ("chung khoan dnse", "dnse"), ("dnse", "dnse"),
]


def _fold_ascii(s: str) -> str:
    """Accent-fold AND map đ/Đ to d. `_strip_accents` cannot: Vietnamese `đ` (U+0111) is its own letter
    with no canonical decomposition, so "quân đội" folds to "quan đoi" and an ASCII alias needle like
    "quan doi" never matches. This silently kept "Ngân Hàng TMCP Quân Đội" out of the MB Bank alias group.
    """
    return _strip_accents(s).replace("đ", "d").replace("Đ", "D")


def clean_company(company: str | None) -> str | None:
    """Canonical dedup key for an employer.

    Strips legal forms, scraper badges, then folds known brand aliases so one employer is one key. The
    alias table is deliberately explicit rather than fuzzy: a fuzzy company matcher would merge genuinely
    different subsidiaries (Viettel Post vs Viettel Telecom), which is worse than leaving them apart.
    """
    if not isinstance(company, str) or not company.strip():
        return None
    s = _BADGE.sub("", company)
    s = _LEGAL.sub(" ", _norm(s))
    s = _WS.sub(" ", s).strip(" .,-") or None
    if not s:
        return None
    folded = _fold_ascii(s)
    for needle, canonical in _BRAND_ALIASES:
        if needle in folded:
            return canonical
    return s


_BRAND_URL = re.compile(r"/(?:brand|cong-ty|company)/([^/?#]+)", re.I)


def company_from_url(url: str | None) -> str | None:
    """Recover the employer from a job-board URL when the page did not expose a company field.

    19 TopCV postings in the analysis base have `company IS NULL` because the scraper reads brand-page
    cards that omit it — yet the URL slug names the employer in all 19 (`/brand/vpbank/`, `/brand/fptis/`,
    `/brand/nganhangthuongmaicophanquandoi/`). Those rows were also `company_key IS NULL`, so they could
    never participate in dedup either.
    """
    m = _BRAND_URL.search(url or "")
    if not m:
        return None
    slug = m.group(1).replace("-", " ").replace("_", " ").strip()
    return _WS.sub(" ", slug).title() or None


def company_type(company, jd_text=None) -> str:
    """Employer industry, from the COMPANY NAME ONLY.

    `jd_text` is accepted and ignored, for backward compatibility with existing callers. It used to be
    matched (first 300 chars) — which let the vacancy text decide the employer's industry and produced
    49% of all classifications from JD wording alone, including `POLYTEX FAR EASTERN` (textiles) ->
    bank_fintech and `Dai-ichi Life` (insurance) -> outsourcing. An employer attribute must come from
    the employer.
    """
    hay = _strip_accents(_norm(company or ""))
    if not hay:
        return "unknown"
    for rule in _load("company_type.yml")["rules"]:
        if any(_contains(hay, _strip_accents(_norm(p))) for p in rule["patterns"]):
            return rule["type"]
        # `substrings` = tokens safe to match INSIDE a word. Vietnamese company names concatenate:
        # word-boundary matching missed `ABBANK`, `PVCombank`, `Fintechvn` because the token is glued to
        # the brand. Only unambiguous industry tokens belong here, never short ones like "vib".
        if any(_strip_accents(_norm(p)) in hay for p in rule.get("substrings", [])):
            return rule["type"]
    return _load("company_type.yml").get("default", "unknown")


def clean_title(title: str | None) -> str | None:
    if not isinstance(title, str) or not title.strip():
        return None
    # drop bracketed/parenthetical noise for a cleaner display + dedup key
    s = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", title)
    return _WS.sub(" ", s).strip() or title.strip()
