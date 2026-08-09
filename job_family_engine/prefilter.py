"""Tier 0: settle the obviously-not-Data postings before any of the paid tiers run.

Keyword search on Vietnamese job boards drags in a specific kind of false positive. In a
Vietnamese ad, *data* usually means the lead list handed to a salesperson — "Data Nóng Từ
MKT", "Data Sẵn" — so a search for `data` returns sales roles. Measured on TopCV, the
generic `data` category came back 74% sales. Those postings reach the labeling engine,
skip tier 1 (no title alias matches) and tier 2 (which currently accepts nothing), and are
read by an LLM purely to be told they are OTHER.

Note the trap that makes a naive filter useless: these titles *contain* the word data.
"Has a sales word and no data word" catches almost none of them. What separates them is
the **role head** — the job is "Nhân Viên Kinh Doanh", and data is a perk mentioned in
parentheses. So the rule keys on the role head and only fires when no Data role name
appears anywhere in the title.

Only patterns that were 100% precise against the 1,701 already-labeled postings are here.
Two more were measured and deliberately left out:

    ketoan       63 killed, 96.8% precise — misses e.g. an IT auditor labeled RISK_FRAUD
    devnondata   24 killed, 95.8% precise — misses e.g. a Full-stack role labeled AI_ENGINEER

They would have saved ~84 more calls at the cost of three real Data postings. That is the
wrong trade: an LLM call costs quota, while a Data posting dropped here is gone from the
analysis silently and forever. Tier 0 exists to be cheap, not to be clever — anything it
is unsure about belongs downstream where something actually reads the description.

Re-measure after editing any pattern::

    python -m pytest tests/test_prefilter.py -q
"""

from __future__ import annotations

import re

TIER0_METHOD = "rule:tier0"
TIER0_CONFIDENCE = 0.95

#: Any Data *role*, in either language. Its presence vetoes every rule below — a title that
#: names a Data role goes downstream no matter what else it says.
#:
#: The word `data` alone is deliberately NOT here. A first version vetoed on it and was
#: blind to the very postings this tier exists for: "Chuyên Viên Tư Vấn ... (Data Sẵn)"
#: contains `data`, so the veto fired and the sales ad sailed through to a paid judge. What
#: has to appear is a role — `data engineer`, `kỹ sư dữ liệu` — not the bare noun.
DATA_ROLE = re.compile(
    r"(data (engineer|analyst|scientist|architect|analytics|platform|warehouse|steward"
    r"|specialist|consultant|lead|manager|officer)"
    r"|dữ liệu|analytics engineer|business analyst|business intelligence|\bbi\b"
    r"|machine learning|\bml engineer\b|\bai engineer\b|mlops|\betl\b|big data"
    r"|data mining|khoa học dữ liệu|phân tích|thống kê|insight"
    r"|\bsql\b|python|power bi|tableau|rủi ro|\brisk\b|fraud"
    r"|công nghệ thông tin|\bit audit\b|kiểm toán công nghệ)"
)

#: Role heads that are unambiguously not Data work. Each was measured separately; see the
#: module docstring for the two groups that did not make the cut.
NON_DATA_ROLES: dict[str, re.Pattern] = {
    "sales": re.compile(
        r"(nhân viên kinh doanh|chuyên viên kinh doanh|trưởng phòng kinh doanh"
        r"|giám đốc kinh doanh|giám sát kinh doanh|telesale|tele sale|nhân viên tư vấn"
        r"|chuyên viên tư vấn|tư vấn viên|tư vấn tuyển sinh|chăm sóc khách hàng|cskh"
        r"|sales executive|sales staff|sales admin|sales supervisor|sales manager"
        r"|nhân viên bán hàng)"),
    "marketing": re.compile(
        r"(marketing executive|nhân viên marketing|content writer|content creator"
        r"|\bseo\b|social media|thiết kế đồ hoạ|graphic designer)"),
    "hr": re.compile(
        r"(nhân viên nhân sự|chuyên viên nhân sự|trưởng phòng nhân sự"
        r"|talent acquisition|\brecruiter\b|hr executive|hr manager|hr business partner)"),
    "operations": re.compile(
        r"(công nhân|vận hành máy|kỹ sư cơ khí|kỹ sư điện|kỹ sư xây dựng"
        r"|giám sát công trình|thiết kế nội thất|\blái xe\b|\bbảo vệ\b|nhân viên kho)"),
}


def classify(title: str | None) -> tuple[bool, str | None]:
    """Return (is_obviously_not_data, which_rule_fired).

    ``(False, None)`` means "no opinion" — the posting goes on to the paid tiers. Tier 0
    never assigns a Data family; it only ever rules one out.
    """
    if not title:
        return False, None
    t = title.lower()
    if DATA_ROLE.search(t):
        return False, None
    for name, pattern in NON_DATA_ROLES.items():
        if pattern.search(t):
            return True, name
    return False, None


def reason(rule_name: str) -> str:
    return f"tier0: title is a {rule_name} role and names no Data role"
