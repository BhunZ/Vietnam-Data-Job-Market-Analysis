"""Report-grade market-insight figures for the VN Data job market (Plotly).

Reads the shipped DuckDB warehouse (`gold_*`, built by the Job Family Engine) and renders each figure as
PNG + interactive HTML into `analysis/figures/`. Only the PNGs are committed; the HTML is a local
convenience (hover tooltips) and is gitignored.

Design rules applied:
  * ONE message per figure, and every figure shares the same 900x560 canvas so a single `width=` in
    LaTeX renders them all at the same size.
  * Horizontal bars whenever category names are long — vertical bars force rotated, overlapping ticks.
  * Every bar carries a DIRECT value label; three palette slots sit below 3:1 contrast on the light
    surface, and a visible label is the required relief.
  * Colours come from a validated categorical palette (adjacent-pair CVD ΔE >= 8, normal-vision >= 15).
    Colour follows the ENTITY (a domain keeps its hue in every figure), never rank.
  * `unknown` buckets are drawn in muted grey and never highlighted: they are missing data, not a finding.
  * No dual axes anywhere; counts and percentages never share a scale.

Run:  python analysis/market_insights.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))                     # so `analysis/x.py` runs standalone, not just -m

from pipeline.utils.analysis_base import ANALYSIS_BASE_WHERE   # noqa: E402

DB = ROOT / "data" / "warehouse.duckdb"
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# --- validated palette (light surface #fcfcfb) --------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
S1, S2, S3, S4, S5 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
NEUTRAL = "#c3c2b7"          # for "unknown"/unclassified — never a highlight colour
FONT = "Segoe UI, system-ui, sans-serif"

# MOI hinh dung CHUNG mot chieu rong. Trong LaTeX ta luon dat cung mot `width=` cho tat ca, nen chieu
# rong bang nhau => co chu sau khi thu nho la bang nhau. Chieu cao thi de thay doi theo so dong du lieu.
FIG_W = 900
# ...va CUNG mot chieu cao. Truoc day moi hinh cao mot kieu theo so dong du lieu, nen khi dat cung
# `width=` trong LaTeX thi hinh nay cao gap ruoi hinh kia — nhin rat lech. Gio khung la co dinh; hinh
# it dong thi bar day hon (chinh bang `bargap`), chu khung khong doi.
FIG_H = 560
# Co chu tinh theo ti le voi FIG_W: 17/900 ~ 1.9% chieu rong, thu nho ve ~14cm trong LaTeX van ~8.5pt,
# tuc xap xi co chu than bai (10pt). Ban cu de 11-13 nen khi dua vao Overleaf bi nho kho doc.
FS_BASE, FS_TICK, FS_LABEL, FS_CAT = 17, 15, 16, 16

# Domain keeps ONE hue across every figure (colour follows the entity).
DOMAIN_COLORS = {
    "Analytics": S1,
    "AI / Machine Learning": S2,
    "Data Engineering": S3,
    "Governance & Architecture": S4,
    "Data Leadership": S5,
}
PRETTY = {
    "BUSINESS_ANALYST": "Business Analyst", "DATA_ENGINEER": "Data Engineer",
    "DATA_ANALYST": "Data Analyst", "AI_ENGINEER": "AI Engineer",
    "RISK_FRAUD_ANALYST": "Risk / Fraud Analyst", "BI": "BI Analyst",
    "DATA_SCIENTIST": "Data Scientist", "DATA_GOVERNANCE": "Data Governance",
    "PRODUCT_ANALYST": "Product Analyst", "DATA_LEADERSHIP": "Data Leadership",
    "DBA_DATABASE": "DBA / Database", "CV_NLP": "Computer Vision / NLP",
    "DATA_ARCHITECT": "Data Architect", "ML_ENGINEER": "ML Engineer",
    "GENAI_LLM": "GenAI / LLM", "ANALYTICS_ENGINEER": "Analytics Engineer",
    "RESEARCH_SCIENTIST": "Research Scientist", "DATAOPS": "DataOps",
    "MLOPS": "MLOps", "BIG_DATA_ENGINEER": "Big Data Engineer",
}
INDUSTRY_VI = {
    "bank_finance": "Ngân hàng / Tài chính", "tech_software": "Công nghệ / Phần mềm",
    "telecom": "Viễn thông", "manufacturing": "Sản xuất", "retail_consumer": "Bán lẻ / Tiêu dùng",
    "consulting_audit": "Tư vấn / Kiểm toán", "logistics": "Logistics", "ecommerce": "Thương mại điện tử",
    "media_gaming": "Truyền thông / Game", "education": "Giáo dục",
    "healthcare_pharma": "Y tế / Dược", "real_estate_construction": "BĐS / Xây dựng",
    "energy_agri": "Năng lượng / Nông nghiệp", "public_sector": "Khu vực công",
    "recruitment_agency": "Công ty tuyển dụng", "unknown": "Chưa phân loại được",
}
SEN_VI = {"Intern": "Intern", "Junior": "Junior", "Mid": "Mid", "Senior": "Senior",
          "Lead": "Lead", "Manager": "Manager", "Unknown": "Không xác định"}


def _shell(fig, h=FIG_H):
    r"""Khung chung cho mọi hình.

    KHÔNG vẽ tiêu đề và KHÔNG vẽ dòng "Nguồn: ..." lên hình. Lý do: hình được đưa vào LaTeX, nơi
    `\caption{}` đã làm đúng việc của tiêu đề, còn phần nguồn/ghi chú thuộc về phần chữ của báo cáo.
    Nhúng chúng vào ảnh chỉ tạo ra hai tiêu đề chồng nhau và một dòng chữ nhỏ không ai đọc.

    Cỡ chữ đặt lớn hơn mặc định của Plotly, vì ảnh sẽ bị thu nhỏ khi chèn vào trang A4.
    """
    fig.update_layout(
        template="plotly_white", font=dict(family=FONT, size=FS_BASE, color=INK),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        height=h, showlegend=False,
        title=None,
        margin=dict(l=10, r=30, t=20, b=40),
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS,
                     tickfont=dict(size=FS_TICK, color=INK2))
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS,
                     tickfont=dict(size=FS_TICK, color=INK2))
    return fig


def _save(fig, name, h=FIG_H):
    fig.write_image(str(OUT / f"{name}.png"), width=FIG_W, height=h, scale=2)
    fig.write_html(str(OUT / f"{name}.html"), include_plotlyjs="cdn", full_html=True)
    print(f"  -> figures/{name}.png + .html")


# --- 1. Domain share — the headline, and the only level a ranking survives at --
def fig_domain(con):
    d = con.execute("SELECT jf_domain, n, pct FROM gold_domain_share ORDER BY n").df()
    labels = list(d["jf_domain"])
    fig = go.Figure(go.Bar(
        y=labels, x=d["pct"], orientation="h",
        marker=dict(color=[DOMAIN_COLORS.get(x, NEUTRAL) for x in labels],
                    line=dict(color=SURFACE, width=2)),   # 2px surface gap between adjacent fills
        text=[f"<b>{p:.1f}%</b>  ({int(n)} tin)" for p, n in zip(d["pct"], d["n"])],
        textposition="outside", textfont=dict(size=FS_LABEL, color=INK), cliponaxis=False,
        hovertemplate="%{y}<br>%{x:.1f}% · %{customdata} tin<extra></extra>", customdata=d["n"],
    ))
    fig.update_xaxes(range=[0, 60], ticksuffix="%")
    fig.update_layout(margin=dict(l=200, r=110, t=25, b=55), bargap=0.42)
    _shell(fig)
    _save(fig, "domain_share")


# --- 2. Family detail — explicitly NOT a ranking ------------------------------
TOP_FAMILIES = 10   # 10 nhanh dau da chiem 91.1% so tin; 10 nhanh con lai deu duoi 2%.


def fig_family(con):
    """Thi phan theo nhanh nghe — CHI ve TOP_FAMILIES nhanh dau.

    Ve du 20 nhanh thi hinh cao gap doi va nua duoi la nhung thanh gan nhu vo hinh (2-13 tin),
    khong doc duoc gi ma lai an het cho trong bao cao. Nhung cat bot ma im lang thi doc gia
    tuong 10 nhanh nay la toan bo thi truong, nen phan duoi duoc GOP thanh mot thanh xam co ghi
    ro so nhanh va so tin — hinh van cong du 100%, khong giau gi.
    """
    d = con.execute("SELECT job_family, jf_domain, n, pct FROM gold_market_share "
                    "ORDER BY n DESC").df()
    top, tail = d.head(TOP_FAMILIES), d.tail(len(d) - TOP_FAMILIES)

    labels = [PRETTY.get(c, c) for c in top["job_family"]]
    pcts = list(top["pct"])
    ns = [int(v) for v in top["n"]]
    colors = [DOMAIN_COLORS.get(x, NEUTRAL) for x in top["jf_domain"]]
    if len(tail):
        labels.append(f"<i>{len(tail)} nhánh còn lại</i>")
        pcts.append(float(tail["pct"].sum()))
        ns.append(int(tail["n"].sum()))
        colors.append(NEUTRAL)
    # Plotly ve tu duoi len, nen dao nguoc de nhanh lon nhat nam tren cung.
    labels, pcts, ns, colors = labels[::-1], pcts[::-1], ns[::-1], colors[::-1]

    fig = go.Figure(go.Bar(
        y=labels, x=pcts, orientation="h",
        marker=dict(color=colors, line=dict(color=SURFACE, width=1.5)),
        text=[f"{p:.1f}%  ({n})" for p, n in zip(pcts, ns)], textposition="outside",
        textfont=dict(size=FS_LABEL, color=INK2), cliponaxis=False,
        hovertemplate="%{y}<br>%{x:.1f}% · %{customdata} tin<extra></extra>", customdata=ns,
    ))
    fig.update_xaxes(range=[0, 26], ticksuffix="%")
    fig.update_layout(margin=dict(l=205, r=80, t=20, b=55), bargap=0.22)
    # Legend: colour = domain, so identity is never carried by colour alone in the caption either.
    # Dat BEN TRONG khung ve, o goc duoi-phai: cac nhanh nho nen vung do trong hoan toan. Truoc day
    # de duoi truc x thi Plotly cat mat dong chu vi no nam ngoai vung giay.
    chips = "<br>".join(f"<span style='color:{c}'>■</span> {n}" for n, c in DOMAIN_COLORS.items())
    fig.add_annotation(text=chips, xref="paper", yref="paper", x=0.47, y=0.34,
                       showarrow=False, xanchor="left", yanchor="top",
                       align="left", font=dict(size=FS_TICK, color=INK2))
    _shell(fig)
    _save(fig, "family_share")


# --- 3. Who hires — industry --------------------------------------------------
TINT = "#9ec5f4"     # nen: moi nganh khong-top-3 deu dung dung mau nay


def fig_industry(con):
    """Nganh cua nha tuyen dung.

    Mau CHI dung de tach top 3 khoi phan con lai. Truoc day moi nganh mot kieu (xanh cho ngan hang,
    luc cho cong nghe, xam cho "cong ty tuyen dung") khien nguoi doc di tim y nghia trong tung mau
    trong khi khong co y nghia nao ca. Top 3 dam, 11 nganh con lai cung mot mau nhat: mat doc thang
    vao dieu duy nhat hinh muon noi.
    """
    d = con.execute("SELECT company_type, SUM(n) n FROM gold_company GROUP BY 1 "
                    "ORDER BY n").df()
    d = d[d["n"] >= 3]
    labels = [INDUSTRY_VI.get(t, t) for t in d["company_type"]]
    total = con.execute("SELECT SUM(n) FROM gold_market_share").fetchone()[0]
    top3 = set(d.nlargest(3, "n")["company_type"])
    colors = [S1 if t in top3 else TINT for t in d["company_type"]]
    fig = go.Figure(go.Bar(
        y=labels, x=d["n"], orientation="h",
        marker=dict(color=colors, line=dict(color=SURFACE, width=2)),
        text=[f"<b>{int(n)}</b>  ({100*n/total:.1f}%)" for n in d["n"]],
        textposition="outside", textfont=dict(size=FS_LABEL, color=INK), cliponaxis=False,
        hovertemplate="%{y}: %{x} tin<extra></extra>",
    ))
    fig.update_xaxes(range=[0, max(d["n"]) * 1.28])
    fig.update_layout(margin=dict(l=250, r=95, t=20, b=55), bargap=0.22)
    _shell(fig)
    _save(fig, "industry_share")


# --- 4. Seniority — with the honest Unknown bucket ---------------------------
def fig_seniority(con):
    d = con.execute("SELECT seniority, SUM(n) n FROM gold_seniority GROUP BY 1").df()
    order = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager", "Unknown"]
    d = d.set_index("seniority").reindex(order).dropna().reset_index()
    total = d["n"].sum()
    colors = [NEUTRAL if s == "Unknown" else S1 for s in d["seniority"]]
    fig = go.Figure(go.Bar(
        x=[SEN_VI.get(s, s) for s in d["seniority"]], y=d["n"],
        marker=dict(color=colors, line=dict(color=SURFACE, width=2)),
        text=[f"<b>{int(n)}</b><br>{100*n/total:.1f}%" for n in d["n"]],
        textposition="outside", textfont=dict(size=FS_LABEL, color=INK), cliponaxis=False,
        hovertemplate="%{x}: %{y} tin<extra></extra>",
    ))
    fig.update_yaxes(range=[0, max(d["n"]) * 1.30])
    fig.update_layout(margin=dict(l=85, r=55, t=25, b=70), bargap=0.38)
    _shell(fig)
    _save(fig, "seniority_share")


# --- 5. Dia diem tuyen dung --------------------------------------------------
def fig_location(con):
    """Tin tuyen theo tinh/thanh.

    Ve tung tinh RIENG chu khong gop thanh "cac tinh khac": ca cai duoi cong lai chi 25 tin, va
    chinh viec nhin thay Da Nang = 1 tin moi noi len dieu can noi. Gop lai thanh mot thanh 25 tin
    se lam no trong nhu mot phan thi truong that su.

    Nhom tin KHONG ghi thanh pho duoc ve rieng bang mau xam, khong bo di va khong nhap vao dau:
    day la du lieu thieu, khong phai mot dia phuong.
    """
    d = con.execute(f"""
        SELECT COALESCE(NULLIF(TRIM(city), ''), '(không ghi thành phố)') AS city, COUNT(*) AS n
        FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE}
        GROUP BY 1 ORDER BY n
    """).df()
    total = int(d["n"].sum())
    hubs = {"Hà Nội", "Hồ Chí Minh"}
    colors = [NEUTRAL if c.startswith("(") else S1 if c in hubs else "#9ec5f4" for c in d["city"]]
    fig = go.Figure(go.Bar(
        y=list(d["city"]), x=d["n"], orientation="h",
        marker=dict(color=colors, line=dict(color=SURFACE, width=2)),
        text=[f"<b>{int(n)}</b>  ({100*n/total:.1f}%)" for n in d["n"]],
        textposition="outside", textfont=dict(size=FS_LABEL, color=INK), cliponaxis=False,
        hovertemplate="%{y}: %{x} tin<extra></extra>",
    ))
    fig.update_xaxes(range=[0, max(d["n"]) * 1.25])
    fig.update_layout(margin=dict(l=225, r=95, t=20, b=60), bargap=0.22)
    _shell(fig)
    _save(fig, "location_share")


def main():
    con = duckdb.connect(str(DB), read_only=True)
    print("Rendering figures → analysis/figures/")
    fig_domain(con)
    fig_family(con)
    fig_industry(con)
    fig_seniority(con)
    fig_location(con)
    con.close()
    print("Done.")


if __name__ == "__main__":
    main()
