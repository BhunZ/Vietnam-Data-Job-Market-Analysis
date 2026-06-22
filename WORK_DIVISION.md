# Phân chia công việc — VN Data Job Market Intelligence

> Nhóm **2 người**. Tài liệu này chia phần việc **sau khi Silver đã xong** (giả định).
> Bối cảnh & quyết định đã khóa: [PROJECT_STATUS.md](PROJECT_STATUS.md) (ĐỌC TRƯỚC).
> Mục tiêu cuối: **báo cáo môn Data Analyst** (PROJECT_STATUS §10) — KHÔNG dự báo lương/tăng trưởng.

---

## 0. NGUYÊN TẮC (mọi người + mọi AI phải tuân theo)
- **KHÔNG làm lại** scraping/storage/Silver — đã xong (PROJECT_STATUS §4–§7). Chỉ ĐỌC Silver/Gold.
- **KHÔNG đổi** các quyết định đã khóa (PROJECT_STATUS §6): salary out, role taxonomy, OTHER bị
  loại khỏi model, lưu trữ DuckDB, dedup, v.v.
- **KHÔNG forecasting** lương/tăng trưởng. Model: association rules + clustering là chính,
  classifier chỉ để minh chứng kỹ thuật (PROJECT_STATUS §9).
- Mỗi luồng = **một sản phẩm hoàn chỉnh, một người sở hữu** — không cắt giữa một sản phẩm.
- Test + phần README/báo cáo đi kèm code của từng luồng.

## 1. Trạng thái & ai làm gì (đồng bộ MASTER_PLAN v1.1 — [MASTER_PLAN.md](MASTER_PLAN.md) là nguồn chính)
| Luồng | Nội dung (phase) | Chủ | Trạng thái |
|---|---|---|---|
| A. Data Eng | P0 Collect ✅ + P1 Silver ✅ | **Bạn** | xong (chờ tích hợp `job_family` ở P2) |
| ⭐ E. Job Family Labeling Engine | **P2** — taxonomy phân cấp + cascade 3 tầng (rule→embedding→multi-LLM voting) + metadata + KPI → tích hợp `job_family` → re-Gold theo family. Module **độc lập** (`engine.predict(job)`). | **Bạn + Teammate** | **TIẾP THEO — trọng tâm** |
| B. Analysis | P4 EDA + thống kê (**% thị trường**, geo/company/seniority) + P5 insight-ML (association rules · clustering · topic modeling) | **Teammate** | sau P2 |
| C. NLP + Recommendation | P3 skill extraction/embedding/keyword + P6 skill rec · similar-job (+ skill-gap) | **chia sau** | sau P2/P3 |
| D. Dashboard | P7 Streamlit drill-down Domain→Sub-domain→Family | **chia sau** | sau P4/P5 |
| Báo cáo | P8 báo cáo + insight cho **seeker & recruiter** (Insight Framework 7 bước) | **cả 2** | cuối |

Phụ thuộc: **A (P1) → ⭐E (P2 `job_family`) → {B, C} → D → Báo cáo.** `job_family` là interface chung;
P2 là **cổng** cho mọi phân tích. 🚫 Không salary, không supervised classifier deliverable, không forecasting (1 snapshot).

## ⭐ LUỒNG E — Job Family Labeling Engine (P2, trọng tâm — chi tiết MASTER_PLAN §⭐P2 + §10)
Module **độc lập, tái dùng** `job_family_engine/` (`engine.predict(job)`). Các bước (B1–B7):
- [ ] **B1** Taxonomy phân cấp `taxonomy_v1.yml` (Domain→Sub-domain→Family) — data-informed (tần suất
      title/skill trong corpus) + tham chiếu ESCO/O*NET/WEF/ITviec/VNW/TopCV. **Số family không hardcode**, có version.
- [ ] **B2** Tier-1 **rule/keyword** (cấu hình `rules_v1.yml` — KHÔNG hardcode trong code).
- [ ] **B3** Tier-2 **embedding similarity** vs prototype mỗi family (phần rule chưa chắc).
- [ ] **B4** Tier-3 **multi-LLM ensemble** (mỗi model trả {family, confidence, reasoning}; provider module hóa).
- [ ] **B5** **Voting** (majority/weighted) + **confidence** + **reviewer queue** (bất đồng → manual_review);
      lưu metadata: domain/subdomain/job_family/confidence/labeling_method/llm_votes/reasoning/review_status.
- [ ] **B6** **KPI** engine (coverage, agreement, unknown rate, review rate, label dist, **spot-check accuracy**).
- [ ] **B7** Tích hợp `job_family` vào `jobs_silver` → **re-Gold theo family** → bảng **% thị trường**.
- **Bàn giao:** engine chạy được + `job_family` (+metadata) phủ toàn bộ job + báo cáo KPI labeling.

---

## 2. LUỒNG A — Data Engineering (Silver + Gold) → Bạn — ✅ HOÀN TẤT
Silver (`jobs_silver`) + Gold (7 bảng) đã build, test (21 pytest) và verify. Việc còn lại của A
chỉ là **vận hành**: cron hằng tuần `scrape → enrich → load → silver → gold` (gồm bước TopCV qua
Chrome) để tích lũy `trend`. **⚠️ Thứ tự BẮT BUỘC: enrich PHẢI chạy sau scrape** (nếu không JD
của CareerViet/Glints sẽ rỗng — đã có guard carry-forward nhưng vẫn nên chạy enrich).
- **Bàn giao:** 7 bảng Gold + `jobs_silver` ổn định (PROJECT_STATUS §7/§8.1) → B/C/D dùng chung.

## 3. LUỒNG B — Phân tích nâng cao (insight ML) → Teammate (đọc kỹ PROJECT_STATUS §9)
Đầu vào: Silver (`jobs_silver`) + Gold (`skill_cooccurrence`, `role_skill_matrix`).
**CHỈ ML unsupervised TẠO INSIGHT** (đây là dự án Data Analyst — KHÔNG prediction, KHÔNG classifier):
- [ ] ⭐ **Association rules** (Apriori/FP-growth) trên `skills` → combo "biết X nên học Y"
      (ngôi sao prescriptive, không leakage).
- [ ] **Clustering** (KMeans/HDBSCAN trên vector skill) → nhóm nghề tự nhiên + kiểm chứng role có
      tách theo skill không; (UMAP/PCA tùy chọn để VẼ).
- [ ] **Topic modeling** (LDA/NMF trên JD free-text) → chủ đề công nghệ/kỹ năng ẩn → "công nghệ nào đang nổi".
- ✅ **Nhãn role = LLM consensus labeling** (engine `pipeline/dataset/annotate.py`+`agreement.py`:
      đọc title+JD+skills, 2–3 model bỏ phiếu → nhánh Data) → nền cho **% thị trường** + skill theo nhánh.
- 🚫 KHÔNG: salary prediction, forecasting, **train supervised classifier**, golden/IAA benchmark
      (đã LOẠI 2026-06-20 — xem PROJECT_STATUS §9). Chỉ GÁN NHÃN tập này, không train mô hình dự đoán.
- **Bàn giao:** nhãn role (LLM) + association rules + clustering + topic modeling + phần "Phân tích" của báo cáo.

## 4. LUỒNG C — Analyze (chia sau) → đọc từ Gold
- [ ] Notebook: top skill tổng & theo role; khác biệt role; theo thành phố & loại công ty;
      seniority progression.
- [ ] **Diễn giải** kết quả association rules + clustering (do Luồng B tạo ra) thành narrative
      learning-path — KHÔNG tự tính lại (tránh trùng sở hữu với Luồng B).
- [ ] Kết luận: **"kỹ năng nên học để theo nghề Data ở VN"** (mục tiêu cuối).
- **Bàn giao:** notebook + mục EDA/Diagnostic/Kết luận của báo cáo.

## 5. LUỒNG D — Dashboard (chia sau) → đọc từ Gold
- [ ] Streamlit (`dashboard/`) + plotly/altair: skill demand, role differentiation,
      seniority progression, role theo location, trend (mô tả).
- **Bàn giao:** dashboard chạy được + ảnh cho báo cáo.

## 6. BÁO CÁO MÔN DATA ANALYST (cả 2) — cấu trúc ở PROJECT_STATUS §10
Mỗi người viết phần thuộc luồng của mình; ghép lại theo cấu trúc §10. Bắt buộc có mục
**Hạn chế** (PROJECT_STATUS §11): nêu rõ "không có lương → không dự đoán thu nhập/tăng trưởng",
"mới 1 snapshot → trend là hướng phát triển", coi đó là sự trung thực khoa học, không phải thiếu sót.

## 7. Thứ tự gợi ý
```
[Bạn] Gold (từ Silver)  ──►  ┌── [Teammate] Model
                              ├── [chia sau] Analyze
                              └── [chia sau] Dashboard   ──►  [cả 2] Báo cáo
```
Trong lúc chờ Gold đầy đủ: Teammate dựng khung train trên `jobs_silver`; Analyze/Dashboard dựng
khung trên bảng Gold mẫu. **Ai sửa data thì sửa trong Luồng A** (một nguồn sự thật duy nhất).
