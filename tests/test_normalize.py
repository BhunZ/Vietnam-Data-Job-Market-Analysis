"""Field normalizers (pipeline/transform/normalize.py) — incl. the bugs found in review."""

from pipeline.transform import normalize as N


def test_skills_from_tags_and_unmapped():
    sk, un = N.normalize_skills(["Power BI", "python", "Totally Unknown Skill"], None)
    assert "Power BI" in sk and "Python" in sk
    assert "Totally Unknown Skill" in un


def test_skills_extracted_from_jd_text():
    sk, _ = N.normalize_skills([], "Strong SQL and Apache Spark, plus AWS experience.")
    assert {"SQL", "Spark", "AWS"} <= set(sk)


def test_short_alias_not_matched_in_freetext():
    # 'R' (len<3) must come only from tags, never from random JD text.
    sk, _ = N.normalize_skills([], "our work supports everyone in our role")
    assert "R" not in sk


def test_role_data_engineer():
    assert N.classify_role("Senior Data Engineer", None, []) == "DE"


def test_role_data_governance_is_de():
    assert N.classify_role("Data Quality Management Specialist", None, []) == "DE"


def test_role_word_boundary_other():
    # 'analyst' patterns must not fire on unrelated titles
    assert N.classify_role("International Sales Officer", None, []) == "OTHER"


def test_seniority_real_intern():
    assert N.derive_seniority("Data Analyst Intern", None, None) == "Intern"


def test_seniority_international_not_intern():
    assert N.derive_seniority("International Business Officer", None, None) != "Intern"


def test_seniority_sr_is_senior():
    assert N.derive_seniority("Sr. Data Engineer", None, None) == "Senior"


def test_location_city_region_remote():
    city, region, remote = N.normalize_location("Ho Chi Minh", "Remote")
    assert city == "Hồ Chí Minh" and region == "South" and remote is True


def test_clean_company_strips_legal():
    key = N.clean_company("Công Ty TNHH FPT Software Việt Nam")
    assert key and "tnhh" not in key and "fpt software" in key


def test_language_detect_en():
    assert "EN" in N.detect_language_req("Yêu cầu tiếng Anh giao tiếp tốt", None)
