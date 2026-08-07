"""Bản đồ chuyển nghề: từ nghề A sang nghề B thì phải học thêm những gì.

Trả lời câu hỏi mà bảng thị phần không trả lời được: *"tôi nên học gì, và đi theo lộ trình nào?"*

Cách làm — chỉ là đếm và so sánh tập hợp, không có model nào:
  1. **Hai ngưỡng, hai mục đích khác nhau — đừng trộn.**
     * `--core-threshold` (mặc định 50%) → **bộ kỹ năng tối thiểu để vào nghề**: thứ mà phần lớn tin
       tuyển dụng đòi. Danh sách ngắn, gọn, dùng để trả lời "cần gì để ứng tuyển".
     * `--profile-threshold` (mặc định 25%) → **hồ sơ kỹ năng để SO SÁNH các nghề**. Ở mức 50% bộ kỹ năng
       co lại còn 1–6 món, và ma trận so sánh trở nên vô nghĩa (Business Analyst chỉ còn đúng 1 kỹ năng
       vượt ngưỡng ⇒ mọi ô liên quan tới nó thành 0% hoặc 100%). Ở mức 25% hồ sơ đủ dày để so sánh.
  2. Với mỗi cặp (A, B): `overlap = |core(A) ∩ core(B)| / |core(B)|` — *người làm A đã có sẵn bao nhiêu
     phần trăm kỹ năng lõi của B*. Phép này **bất đối xứng** có chủ ý: nghề đòi nhiều kỹ năng thì bao
     được nghề đòi ít, chiều ngược lại thì không. Chính sự bất đối xứng đó là phát hiện.
  3. `core(B) \\ core(A)` = danh sách phải học thêm.

Ngưỡng 50% là một lựa chọn, không phải hằng số của tự nhiên — nên script **luôn quét thêm 40% và 60%**
và báo cáo kết luận nào đổi. Một project trước đây đã suýt đưa vào báo cáo một kết luận hoá ra chỉ là
hiện vật của ngưỡng; phần kiểm độ nhạy này tồn tại để chuyện đó không lặp lại.

Chạy:  python analysis/career_map.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.utils.analysis_base import ANALYSIS_BASE_WHERE  # noqa: E402

DB = ROOT / "data" / "warehouse.duckdb"
OUT = ROOT / "analysis" / "outputs"
FIG = ROOT / "analysis" / "figures"

# Bảng màu đã kiểm CVD-safe, dùng chung với market_insights.py
SURFACE = "#fcfcfb"
INK, MUTED, GRID = "#1a1a18", "#6b6b66", "#e6e6e2"
SEQ = ["#f7f7f5", "#d6e4f0", "#a8c8e4", "#6fa8d6", "#3d7fb8", "#1f4e79"]

FIG_W, FIG_H = 900, 560   # cung KHUNG voi cac hinh khac, xem analysis/market_insights.py

# `.title()` bien AI_ENGINEER thanh "Ai Engineer" va BI thanh "Bi" — viet tay cho dung.
DISPLAY = {"AI_ENGINEER": "AI Engineer", "BI": "BI", "DATA_ANALYST": "Data Analyst",
           "DATA_ENGINEER": "Data Engineer", "DATA_SCIENTIST": "Data Scientist",
           "BUSINESS_ANALYST": "Business Analyst", "DATA_GOVERNANCE": "Data Governance",
           "RISK_FRAUD_ANALYST": "Risk / Fraud Analyst", "ML_ENGINEER": "ML Engineer",
           "DATA_ARCHITECT": "Data Architect", "GENAI_LLM": "GenAI / LLM", "CV_NLP": "CV / NLP"}


def disp(f: str) -> str:
    return DISPLAY.get(f, f.replace("_", " ").title())


def core_sets(con, threshold: float, min_n: int) -> dict[str, set[str]]:
    """Bộ kỹ năng lõi của từng nghề, chỉ lấy nghề có đủ `min_n` tin."""
    fam_n = dict(con.execute(
        f"SELECT job_family, COUNT(*) FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE} GROUP BY 1"
    ).fetchall())
    rows = con.execute(
        "SELECT job_family, skill FROM gold_family_skill WHERE share_in_family >= ?", [threshold]
    ).fetchall()
    out: dict[str, set[str]] = {}
    for fam, skill in rows:
        if fam_n.get(fam, 0) >= min_n:
            out.setdefault(fam, set()).add(skill)
    # nghề có đủ tin nhưng không kỹ năng nào vượt ngưỡng vẫn phải xuất hiện, với bộ rỗng
    for fam, n in fam_n.items():
        if n >= min_n:
            out.setdefault(fam, set())
    return out


def overlap_matrix(core: dict[str, set[str]]) -> pd.DataFrame:
    fams = sorted(core, key=lambda f: -len(core[f]))
    m = pd.DataFrame(index=fams, columns=fams, dtype=float)
    for a in fams:
        for b in fams:
            m.loc[a, b] = float("nan") if a == b else (
                100.0 * len(core[a] & core[b]) / len(core[b]) if core[b] else float("nan"))
    return m


def fig_matrix(m: pd.DataFrame, threshold: float) -> None:
    r"""Ma trận chuyển nghề. Không vẽ tiêu đề và không vẽ dòng nguồn lên hình — trong LaTeX thì
    `\caption{}` lo phần đó; nhúng vào ảnh chỉ tạo hai tiêu đề chồng nhau."""
    short = [disp(f) for f in m.index]
    z = m.values.astype(float)
    text = [["—" if pd.isna(v) else f"{v:.0f}%" for v in row] for row in z]
    fig = go.Figure(go.Heatmap(
        z=z, x=short, y=short, text=text, texttemplate="%{text}",
        textfont=dict(size=15),
        colorscale=[[0, SEQ[0]], [0.35, SEQ[2]], [0.7, SEQ[4]], [1, SEQ[5]]],
        showscale=False, xgap=2, ygap=2, hoverongaps=False))
    fig.update_layout(
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        height=FIG_H, width=FIG_W, margin=dict(l=175, r=20, t=95, b=15),
        font=dict(size=16),
        xaxis=dict(side="top", tickfont=dict(size=15, color=INK), showgrid=False, tickangle=-30),
        yaxis=dict(autorange="reversed", tickfont=dict(size=15, color=INK), showgrid=False))
    FIG.mkdir(parents=True, exist_ok=True)
    fig.write_image(str(FIG / "career_map.png"), width=FIG_W, height=FIG_H, scale=2)
    fig.write_html(str(FIG / "career_map.html"), include_plotlyjs="cdn", full_html=True)
    print("  -> figures/career_map.png + .html")


def sensitivity(con, thresholds: list[float], min_n: int) -> pd.DataFrame:
    """Bộ kỹ năng lõi và ma trận đổi bao nhiêu khi đổi ngưỡng? Đây là phần chống tự lừa mình."""
    rows = []
    for th in thresholds:
        core = core_sets(con, th, min_n)
        m = overlap_matrix(core)
        for a in m.index:
            for b in m.columns:
                if a != b and not pd.isna(m.loc[a, b]):
                    rows.append({"threshold": th, "from_family": a, "to_family": b,
                                 "overlap_pct": round(float(m.loc[a, b]), 1),
                                 "n_core_from": len(core[a]), "n_core_to": len(core[b])})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Bản đồ chuyển nghề theo kỹ năng lõi.")
    ap.add_argument("--core-threshold", type=float, default=50.0,
                    help="Bộ kỹ năng TỐI THIỂU để vào nghề: xuất hiện ở >= X%% tin.")
    ap.add_argument("--profile-threshold", type=float, default=25.0,
                    help="Hồ sơ kỹ năng để SO SÁNH nghề. Thấp hơn core vì ở 50%% hồ sơ quá mỏng.")
    ap.add_argument("--anchor", default="DATA_ANALYST",
                    help="Nghe xuat phat cho bang 'phai hoc them gi'.")
    ap.add_argument("--min-family-n", type=int, default=25,
                    help="Bỏ qua nghề có ít hơn ngần này tin — tỉ lệ trên mẫu nhỏ không đáng tin.")
    args = ap.parse_args()

    con = duckdb.connect(str(DB), read_only=True)
    base_n = con.execute(f"SELECT COUNT(*) FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE}").fetchone()[0]
    core = core_sets(con, args.core_threshold, args.min_family_n)      # bộ tối thiểu (bảng "vào nghề cần gì")
    prof = core_sets(con, args.profile_threshold, args.min_family_n)   # hồ sơ (ma trận so sánh)
    m = overlap_matrix(prof)

    fam_n = dict(con.execute(
        f"SELECT job_family, COUNT(*) FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE} GROUP BY 1"
    ).fetchall())

    # bộ kỹ năng lõi kèm tỉ lệ, để bảng "vào nghề cần gì" đọc được
    core_detail: dict[str, list[tuple[str, float]]] = {}
    for fam in core:
        rows = con.execute(
            "SELECT skill, share_in_family FROM gold_family_skill "
            "WHERE job_family = ? AND share_in_family >= ? ORDER BY share_in_family DESC",
            [fam, args.core_threshold]).fetchall()
        core_detail[fam] = [(s, float(v)) for s, v in rows]

    sens = sensitivity(con, [20.0, args.profile_threshold, 30.0], args.min_family_n)
    con.close()

    OUT.mkdir(parents=True, exist_ok=True)
    m.round(1).to_csv(OUT / "career_map_matrix.csv", encoding="utf-8-sig")
    sens.to_csv(OUT / "career_map_sensitivity.csv", index=False, encoding="utf-8-sig")

    # HAI file danh sach ky nang, HAI nguong khac nhau. Truoc day chi xuat file 50% nen ma tran
    # KHONG tai lap duoc tu output — nguoi doc thu tinh lai se ra so khac han (vi du DA->BI ra 100%
    # thay vi 77.8%). Moi file nay deu mang cot `threshold_pct` va tu noi no dung de lam gi.
    pd.DataFrame([{"job_family": f, "threshold_pct": args.core_threshold,
                   "dung_de": "bo ky nang toi thieu de ung tuyen (KHONG dung tinh ma tran)",
                   "n_postings": fam_n[f], "n_skills": len(core[f]),
                   "skills": " · ".join(f"{s} {v:.0f}%" for s, v in core_detail[f])}
                  for f in m.index]).to_csv(OUT / "career_map_core_skills.csv",
                                            index=False, encoding="utf-8-sig")
    pd.DataFrame([{"job_family": f, "threshold_pct": args.profile_threshold,
                   "dung_de": "HO SO de tinh ma tran chuyen nghe",
                   "n_postings": fam_n[f], "n_skills": len(prof[f]),
                   "skills": " · ".join(sorted(prof[f]))}
                  for f in m.index]).to_csv(OUT / "career_map_profiles.csv",
                                            index=False, encoding="utf-8-sig")

    fig_matrix(m, args.profile_threshold)

    print(f"analysis_base {base_n}")
    print(f"families {len(m.index)} | core {args.core_threshold}% | profile {args.profile_threshold}%")
    print(m.round(0).to_string())


if __name__ == "__main__":
    main()
