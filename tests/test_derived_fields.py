"""Regression tests for the two derived `jobs_silver` fields: seniority and employer industry.

An audit found these had almost no coverage — three seniority assertions and zero for `company_type`,
while between them they produce every number in the seniority and industry charts. Each test below pins a
defect that actually shipped, so the invariant that motivated a fix cannot silently regress.
"""

from __future__ import annotations

import pytest

from pipeline.transform.normalize import (_fold_ascii, _norm, _strip_accents, _years_from_text,
                                          clean_company, company_from_url, company_type,
                                          derive_seniority_detail, years_from_extra, years_to_band)


def _fold(t: str) -> str:
    return _fold_ascii(_norm(t))


# --- seniority: the "task is not a rank" invariant -----------------------------------------------

@pytest.mark.parametrize("title", [
    "Chuyên viên Quản lý Kho và Mô hình dữ liệu",
    "QLRR_Chuyên Viên Cao Cấp Quản Lý Rủi Ro Thanh Khoản",
    "Chuyên viên Quản lý chất lượng",
])
def test_quan_ly_as_a_task_is_not_manager(title):
    """Bare "quản lý" names a DUTY in Vietnamese titles. Treating it as a rank pushed Manager to 301 of
    1,701 postings and stole rows from Senior (Manager is matched first)."""
    band, _ = derive_seniority_detail(title, None, None, None)
    assert band != "Manager"


def test_chuyen_vien_cao_cap_is_senior():
    band, src = derive_seniority_detail("Chuyên Viên Cao Cấp Quản Lý Rủi Ro", None, None, None)
    assert (band, src) == ("Senior", "rule_title")


def test_jd_prose_never_sets_the_band_by_pattern():
    """The JD describes the work, so it is full of level-shaped words. Only title + source label may
    match patterns; the JD is read for a years REQUIREMENT and nothing else."""
    band, src = derive_seniority_detail("Data Analyst", None, "Bạn sẽ quản lý dữ liệu và báo cáo cho "
                                        "Trưởng phòng. Senior members will mentor you.", None)
    assert band != "Manager" and src != "rule_title"


# --- seniority: evidence precedence and banding --------------------------------------------------

def test_higher_years_band_wins_when_both_signals_exist():
    """The structured form field is a FLOOR, not the requirement.

    A blind two-auditor audit measured `rule_years_source` at 76% exact — the worst tier, below the JD
    regex at 91% — and 11 of 12 sampled disagreements had the form field lower than the JD ("AI Engineer
    | Junior/Middle": field says 1 year, JD asks 3). So when both signals exist the higher band wins,
    in either direction."""
    assert derive_seniority_detail("Data Analyst", None, "yêu cầu 7 năm kinh nghiệm",
                                   {"years_of_experience": 1}) == ("Senior", "rule_years_jd")
    assert derive_seniority_detail("Data Analyst", None, "yêu cầu 2 năm kinh nghiệm",
                                   {"years_of_experience": 6}) == ("Senior", "rule_years_source")


def test_solid_written_level_word_is_still_a_level():
    """Word-boundary matching cannot see "leader" inside "Teamleader", so the title was skipped and the
    years signal reported this Lead role as Junior."""
    assert derive_seniority_detail("Data Analyst Teamleader", None, None,
                                   {"years_of_experience": 1}) == ("Lead", "rule_title")


def test_title_beats_structured_years():
    band, src = derive_seniority_detail("Senior Data Engineer", None, None, {"years_of_experience": 1})
    assert (band, src) == ("Senior", "rule_title")


@pytest.mark.parametrize("extra,expected", [
    ({"years_of_experience": -1}, None),          # VietnamWorks "unspecified"
    ({"years_of_experience": 0}, 0.0),
    ({"min_years_exp": 3}, 3.0),
    ({"experience_req": {"monthsOfExperience": 24}}, 2.0),
    ({}, None),
])
def test_years_from_extra(extra, expected):
    assert years_from_extra(extra) == expected


@pytest.mark.parametrize("years,band", [
    (0, "Junior"), (1, "Junior"), (2, "Mid"), (4, "Mid"), (5, "Senior"), (9, "Senior"), (-1, None),
])
def test_year_cut_points(years, band):
    """<=1 Junior · 2-4 Mid · >=5 Senior. The old `<=5 -> Mid` put a "5-7 years" posting in Mid and
    contradicted the LLM prompt's own rule, so the two layers disagreed at the boundary."""
    assert years_to_band(years) == band


@pytest.mark.parametrize("text,years", [
    ("5-7 nam kinh nghiem", 5.0),          # hyphen range -> lower bound
    ("kinh nghiem 3–6 nam", 3.0),     # en-dash range -> ALSO lower bound (used to take the upper)
    ("tren 5 nam kinh nghiem", 5.0),
    ("5+ years of experience", 5.0),
    ("toi thieu 2 nam kinh nghiem", 2.0),
    ("cong ty co 20 nam kinh nghiem trong nganh", None),   # employer tenure, not a requirement
])
def test_years_from_prose(text, years):
    assert _years_from_text(_fold(text)) == years


def test_silence_stays_unknown():
    """`Unknown` must remain reachable. The original rules file had `default: Mid` with no Mid pattern,
    so 45% of the corpus was silently reported as mid-level."""
    band, src = derive_seniority_detail("Data Analyst", None, "Mô tả công việc: phân tích dữ liệu.", {})
    assert (band, src) == ("Unknown", "none")


# --- employer identity: dedup keys ---------------------------------------------------------------

def test_brand_aliases_collapse_to_one_key():
    """Dedup groups by `company_key`, so one employer written several ways is several employers and its
    cross-posted vacancies survive dedup. MB Bank was four keys over 91 postings."""
    keys = {clean_company(n) for n in [
        "NGÂN HÀNG TMCP QUÂN ĐỘI – MBBANK", "MBBANK", "MB Bank", "Ngân Hàng TMCP Quân Đội"]}
    assert len(keys) == 1


def test_vietnamese_d_folds_to_ascii_d():
    """`đ` (U+0111) is its own letter with no canonical decomposition, so `_strip_accents` leaves it and
    an ASCII alias needle never matches. This kept "Quân Đội" out of the MB Bank group."""
    assert _fold_ascii("quân đội") == "quan doi"
    assert _strip_accents("quân đội") != "quan doi"      # documents WHY _fold_ascii exists


def test_scraper_badge_does_not_spawn_a_second_key():
    assert clean_company("Pro Công ty CP Kinh doanh F88") == clean_company(
        "CÔNG TY CỔ PHẦN KINH DOANH F88")


def test_company_recovered_from_url():
    """19 base postings had `company IS NULL` (brand-page cards) yet the URL slug names the employer;
    they were also ineligible for dedup because `company_key` was NULL."""
    assert company_from_url("https://www.topcv.vn/brand/vpbank/tuyen-dung") == "Vpbank"
    assert company_from_url("https://example.com/jobs/123") is None


# --- employer industry: priority and matching ----------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Techcombank", "bank_finance"),
    ("ABBANK", "bank_finance"),                                  # substring: "bank" inside the brand
    ("CÔNG TY TNHH Công Nghệ Tài Chính New Asia", "bank_finance"),  # fintech in Vietnamese
    ("Viettel Cyber Security", "tech_software"),                 # not the telecom arm
    ("Tổng Công Ty CP Bưu Chính Viettel", "logistics"),
    ("Trung Tâm Bán Dẫn Viettel", "manufacturing"),
    ("MindX Technology School", "education"),                    # edtech is education, not software
    ("ITviec Recruitment Consulting", "recruitment_agency"),
    ("OUTSOURCE SOLUTIONS CO.,LTD", "tech_software"),            # stem match needs `substrings`
    ("GoTymeX", "bank_finance"),
    ("Navigos Search's Client", "recruitment_agency"),
    ("NEYU", "tech_software"),
])
def test_industry_assignment(name, expected):
    assert company_type(name) == expected


def test_industry_never_reads_the_job_description():
    """An employer attribute must come from the employer. Matching the JD classified 49% of employers
    from vacancy wording — a textile maker became a bank because its posting said "tài chính"."""
    assert company_type("CÔNG TY TNHH POLYTEX FAR EASTERN (VIỆT NAM)",
                        "Mô tả: phân tích tài chính, ngân hàng, thanh toán") == "manufacturing"


def test_unnamed_employer_is_unknown_not_a_bucket():
    assert company_type(None) == "unknown"
    assert company_type("") == "unknown"
