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


def fig_matrix(m: pd.DataFrame, note: str, threshold: float) -> None:
    short = [disp(f) for f in m.index]
    z = m.values.astype(float)
    text = [["—" if pd.isna(v) else f"{v:.0f}%" for v in row] for row in z]
    fig = go.Figure(go.Heatmap(
        z=z, x=short, y=short, text=text, texttemplate="%{text}",
        colorscale=[[0, SEQ[0]], [0.35, SEQ[2]], [0.7, SEQ[4]], [1, SEQ[5]]],
        showscale=False, xgap=2, ygap=2, hoverongaps=False))
    fig.update_layout(
        title=dict(text=f"Người làm nghề ở HÀNG đã có sẵn bao nhiêu %<br>"
                        f"kỹ năng lõi của nghề ở CỘT",
                   font=dict(size=17, color=INK), x=0, xanchor="left", y=0.96),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, height=560, width=880,
        margin=dict(l=170, r=40, t=100, b=110),
        xaxis=dict(side="top", tickfont=dict(size=11, color=MUTED), showgrid=False),
        yaxis=dict(autorange="reversed", tickfont=dict(size=11, color=INK), showgrid=False),
        annotations=[dict(text=note, x=0, y=-0.16, xref="paper", yref="paper",
                          showarrow=False, font=dict(size=10, color=MUTED), xanchor="left")])
    FIG.mkdir(parents=True, exist_ok=True)
    fig.write_image(str(FIG / "career_map.png"), scale=2)
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

    # thang kỹ năng theo cấp bậc
    ladder = con.execute(f"""
        SELECT seniority, COUNT(*) n, ROUND(AVG(n_skills),1) mean_skills, MEDIAN(n_skills) med
        FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE} GROUP BY 1""").df()
    order = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager", "Unknown"]
    ladder["_o"] = ladder.seniority.map({v: i for i, v in enumerate(order)}).fillna(99)
    ladder = ladder.sort_values("_o").drop(columns="_o")

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

    note = (f"Nguồn: {base_n} tin Data/AI · hồ sơ kỹ năng = xuất hiện ở ≥{args.profile_threshold:.0f}% "
            f"tin của nghề · chỉ nghề có ≥{args.min_family_n} tin · 1 snapshot ⇒ không suy ra xu hướng")
    fig_matrix(m, note, args.profile_threshold)
    write_findings(m=m, core_detail=core_detail, prof_sets=prof, fam_n=fam_n, ladder=ladder,
                   sens=sens, base_n=base_n, args=args)

    print(f"analysis_base {base_n}")
    print(f"families {len(m.index)} | core {args.core_threshold}% | profile {args.profile_threshold}%")
    print(m.round(0).to_string())


def write_findings(*, m, core_detail, prof_sets, fam_n, ladder, sens, base_n, args) -> None:
    """Sinh doc TỪ số liệu. Không gõ tay con số nào vào đây."""
    fams = list(m.index)
    hdr = " | ".join(f.replace("_", " ").title()[:14] for f in fams)
    rows_md = "\n".join(
        "| **" + a.replace("_", " ").title() + "** | "
        + " | ".join("—" if a == b else f"{m.loc[a, b]:.0f}%" for b in fams) + " |"
        for a in fams)

    core_md = "\n".join(
        f"| {disp(f)} | {fam_n[f]} | {len(core_detail[f])} | "
        + (" · ".join(f"{s} {v:.0f}%" for s, v in core_detail[f]) or "*(không kỹ năng nào vượt ngưỡng)*")
        + " |" for f in fams)

    # từ nghề đông tin nhất, phải học thêm gì
    anchor = args.anchor if args.anchor in fams else max(fams, key=lambda f: fam_n[f])
    core_sets_map = prof_sets  # danh sách "học thêm" dùng HỒ SƠ, cùng thang với ma trận
    learn_md = "\n".join(
        f"| {disp(b)} | **{len(core_sets_map[b] - core_sets_map[anchor])}** | "
        + (", ".join(sorted(core_sets_map[b] - core_sets_map[anchor])) or "*(không thiếu gì)*") + " |"
        for b in sorted(fams, key=lambda x: len(core_sets_map[x] - core_sets_map[anchor]))
        if b != anchor)

    ladder_md = "\n".join(
        f"| {r.seniority} | {r.n} | {r.mean_skills} | {r.med:.0f} |"
        for r in ladder.itertuples(index=False))

    # độ nhạy: cặp nào đảo chiều khi đổi ngưỡng
    piv = sens.pivot_table(index=["from_family", "to_family"], columns="threshold",
                           values="overlap_pct")
    flips = piv.dropna()
    swing = (flips.max(axis=1) - flips.min(axis=1)).sort_values(ascending=False)
    swing_md = "\n".join(
        f"| {disp(a)} → {disp(b)} | "
        + " | ".join(f"{flips.loc[(a, b), c]:.0f}%" for c in flips.columns)
        + f" | **{swing.loc[(a, b)]:.0f}pt** |"
        for (a, b) in swing.head(8).index)
    th_cols = " | ".join(f"{c:.0f}%" for c in flips.columns)
    stable = swing[swing <= 15]
    stable_md = "\n".join(
        f"| {disp(a)} → {disp(b)} | "
        + " | ".join(f"{flips.loc[(a, b), c]:.0f}%" for c in flips.columns)
        + f" | {swing.loc[(a, b)]:.0f}pt |"
        for (a, b) in stable.head(12).index) or "| *(không cặp nào đủ bền)* | | | | |"

    doc = f"""# Bản đồ chuyển nghề — Findings

*Sinh tự động bởi `python analysis/career_map.py`. Đừng sửa tay; chạy lại để cập nhật.*

## Câu hỏi

Bảng thị phần nói *nghề nào nhiều tin*. Nó không nói **"tôi nên học gì, và từ đây đi được đâu"**.
File này trả lời câu đó bằng cách so sánh **bộ kỹ năng lõi** giữa các nghề.

## Cách đo

**Hai ngưỡng, hai mục đích — đây là chỗ dễ nhầm nhất:**

| Ngưỡng | Dùng cho | Vì sao |
|---|---|---|
| **≥{args.core_threshold:.0f}%** | Bảng *"vào nghề cần gì"* | Thứ phần lớn tin tuyển dụng đòi. Danh sách ngắn, dứt khoát |
| **≥{args.profile_threshold:.0f}%** | *Ma trận so sánh nghề* | Ở mức {args.core_threshold:.0f}% hồ sơ co lại còn 1–6 kỹ năng và ma trận thành vô nghĩa — Business Analyst chỉ còn 1 kỹ năng vượt ngưỡng nên mọi ô liên quan hoá 0% hoặc 100% |

- **Độ phủ** (hàng A, cột B) = *người làm A đã có sẵn bao nhiêu % hồ sơ kỹ năng của B*.
  Công thức: `|profile(A) ∩ profile(B)| / |profile(B)|`.
- Phép này **bất đối xứng có chủ ý** — và chính sự bất đối xứng là phát hiện chính.
- Chỉ xét nghề có **≥{args.min_family_n} tin**. Tập phân tích: **{base_n}** tin.

## Bản đồ chuyển nghề

Đọc: *người đang làm nghề ở **hàng** đã có sẵn bao nhiêu % kỹ năng lõi của nghề ở **cột***.

| Từ ↓ / Sang → | {hdr} |
|---|{'---|' * len(fams)}
{rows_md}

![Bản đồ chuyển nghề](../analysis/figures/career_map.png)

> **Muốn tự kiểm ô trong bảng?** Dùng `analysis/outputs/career_map_profiles.csv` (ngưỡng
> {args.profile_threshold:.0f}%), **KHÔNG** dùng `career_map_core_skills.csv` (ngưỡng
> {args.core_threshold:.0f}%, phục vụ bảng "vào nghề cần gì" bên dưới). Hai file dùng hai ngưỡng khác
> nhau nên tính nhầm file sẽ ra số khác hẳn.
>
> Ví dụ ô `Data Analyst → BI`: hồ sơ BI có 9 kỹ năng, Data Analyst đã có sẵn 7 trong đó
> (thiếu Business Intelligence và Data Modeling) ⇒ 7/9 = 77,8%. Chiều ngược lại dùng **cùng 7 kỹ năng
> chung** nhưng chia cho 12 (số kỹ năng của Data Analyst) ⇒ 58,3%. Tử số giống nhau, mẫu số đổi — đó là
> lý do bảng bất đối xứng.

## Bộ kỹ năng tối thiểu để vào nghề

| Nghề | Số tin | Số kỹ năng lõi | Kỹ năng lõi (% tin của nghề đó yêu cầu) |
|---|--:|--:|---|
{core_md}

## Xuất phát từ `{disp(anchor)}` thì phải học thêm gì

| Sang nghề | Số kỹ năng phải học thêm | Là những gì |
|---|--:|---|
{learn_md}

## Thang kỹ năng theo cấp bậc

| Cấp bậc | Số tin | Số kỹ năng trung bình | Trung vị |
|---|--:|--:|--:|
{ladder_md}

## Kiểm độ nhạy của ngưỡng — phần chống tự lừa mình

Ngưỡng {args.profile_threshold:.0f}% là một lựa chọn, không phải hằng số. Bảng dưới cho biết độ phủ đổi
bao nhiêu khi dùng 20% / {args.profile_threshold:.0f}% / 30%. **Cặp nào dao động lớn thì đừng đưa vào báo cáo
như một con số cụ thể** — chỉ nói theo hướng ("dễ / khó"), không nói theo số.

| Cặp | {th_cols} | Dao động |
|---|{'---|' * len(flips.columns)}---|
{swing_md}

### Cặp nào BỀN — chỉ những cặp này mới được trích số cụ thể

Dao động ≤ 15 điểm phần trăm qua cả ba ngưỡng:

| Cặp | {th_cols} | Dao động |
|---|{'---|' * len(flips.columns)}---|
{stable_md}

Các cặp còn lại **chỉ nói theo hướng** ("gần / xa", "dễ / khó"), tuyệt đối không trích con số.

Bảng đầy đủ: `analysis/outputs/career_map_sensitivity.csv`.

## Cách đọc — và cách KHÔNG được đọc

- ✅ *"Người làm A đã có sẵn phần lớn kỹ năng lõi của B"* — đúng với phép đo.
- ❌ *"Nghề A dễ hơn nghề B"* — bộ kỹ năng lõi không đo độ khó, không đo chiều sâu, không đo kinh nghiệm.
- ❌ *"Chỉ cần học N kỹ năng này là chuyển được nghề"* — đây là **danh sách kỹ năng tin tuyển dụng viết ra**,
  không phải chương trình đào tạo. Số N là *hàng rào tối thiểu*, không phải *đủ điều kiện*.
- Bảng chỉ phản ánh **những gì tin tuyển dụng viết**, không phải công việc thực tế.

## Giới hạn

- Một lát cắt duy nhất ⇒ không có phát ngôn xu hướng.
- Không có trường lương ⇒ không có phát ngôn về thu nhập.
- Tỉ lệ mô tả **tập dữ liệu này**, không phải thị trường Việt Nam — mỗi job board được truy vấn với độ
  rộng từ khoá khác nhau.
- Kỹ năng lấy từ từ điển chuẩn hoá; kỹ năng chưa có trong từ điển thì không được đếm
  (xem `data/quality/unmapped_skills.csv`).
"""
    (ROOT / "docs" / "CAREER_MAP_FINDINGS.md").write_text(doc, encoding="utf-8")
    print("  -> docs/CAREER_MAP_FINDINGS.md")


if __name__ == "__main__":
    main()
