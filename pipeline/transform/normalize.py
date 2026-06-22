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
def derive_seniority(title, seniority_label, jd_head) -> str:
    cfg = _load("seniority_rules.yml")
    hay = _norm(" ".join(filter(None, [title, str(seniority_label or ""), (jd_head or "")[:200]])))
    for rule in cfg["rules"]:
        if any(_contains(hay, _norm(p)) for p in rule["patterns"]):
            return rule["seniority"]
    return cfg.get("default", "Mid")


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


def clean_company(company: str | None) -> str | None:
    if not isinstance(company, str) or not company.strip():
        return None
    s = _LEGAL.sub(" ", _norm(company))
    return _WS.sub(" ", s).strip(" .,-") or None


def company_type(company, jd_text) -> str:
    hay = _strip_accents(_norm(" ".join(filter(None, [company or "", (jd_text or "")[:300]]))))
    for rule in _load("company_type.yml")["rules"]:
        if any(_contains(hay, _strip_accents(_norm(p))) for p in rule["patterns"]):
            return rule["type"]
    return _load("company_type.yml").get("default", "other")


def clean_title(title: str | None) -> str | None:
    if not isinstance(title, str) or not title.strip():
        return None
    # drop bracketed/parenthetical noise for a cleaner display + dedup key
    s = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", title)
    return _WS.sub(" ", s).strip() or title.strip()
