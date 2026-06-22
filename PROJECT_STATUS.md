# Trạng thái & Cẩm nang dự án — VN Data Job Market Intelligence

> **Tài liệu bàn giao (authoritative).** Đọc kỹ trước khi làm tiếp. Cập nhật: 2026-06-22.
> Mục đích: bất kỳ người/AI nào nạp file này đều biết **đã làm gì, đã chốt gì (KHÔNG được
> đổi), và làm gì tiếp theo**, để KHÔNG làm lại từ đầu hay đi chệch kế hoạch.
> Phân chia người làm: [WORK_DIVISION.md](WORK_DIVISION.md).
> ✅ **Silver ĐÃ XONG** (bảng `jobs_silver` trong warehouse — xem §7). Phần "việc tiếp theo"
> (§8) bắt đầu từ **Gold**.

---

## 1. Dự án & phạm vi
Pipeline thu thập tin tuyển dụng ngành **Data** (DE/DS/DA/MLE/BI/AE) từ **job board Việt Nam**,
chuẩn hóa, và rút insight: **kỹ năng nào đang được cần, role khác nhau ra sao, yêu cầu tăng
theo seniority thế nào** → trả lời câu hỏi **"người theo nghề Data ở VN nên học kỹ năng gì".**

**RÀNG BUỘC CỨNG (không được vi phạm):**
- 🚫 **KHÔNG xử lý lương** (salary OUT OF SCOPE) — không parse/model/report/forecast lương.
- 🚫 **KHÔNG cào LinkedIn.**
- 🚫 **KHÔNG dự báo tăng trưởng/tương lai thị trường** (không có lương + chưa đủ chuỗi thời
  gian → không làm forecasting; xem §9, §11).
- Chỉ Việt Nam, chỉ ngành Data. Secret qua `.env` (gitignored). Scraping có trách nhiệm.

## 2. Đây là BÁO CÁO MÔN DATA ANALYST
Sản phẩm cuối là **báo cáo môn học Data Analyst** (+ repo tái lập được). Mọi bước phải phục vụ
một báo cáo theo mạch **descriptive → diagnostic → prescriptive**, trong đó model đóng vai
**mô tả/khám phá/kiểm chứng/khuyến nghị (KHÔNG dự đoán)** — chi tiết §9. Cấu trúc báo cáo ở §10.
**Không** biến nó thành dự án forecasting/ML nặng về lương.

## 3. Trạng thái theo Phase (đồng bộ MASTER_PLAN v1.1 — xem [MASTER_PLAN.md](MASTER_PLAN.md) là nguồn chính thức)
| Phase | Nội dung | Trạng thái |
|---|---|---|
| P0. Data Collection | 6 nguồn → warehouse (CDC) | ✅ XONG |
| P1. Silver (clean/standardize) | `jobs_silver`: skills/seniority/location/company + dedup | ✅ XONG |
| **P2. ⭐ Job Family Labeling Engine** | taxonomy phân cấp + cascade 3 tầng (rule→embedding→LLM dynamic-failover) + metadata + `job_family` | ✅ **XONG** — 1701 job gán nhãn (100% resolved), tích hợp vào jobs_silver + 7 bảng family Gold (xem §13) |
| P3. Feature/NLP | skill extraction/embedding/keyword; feature outputs | ⬜ |
| P4. Market & Statistical Analysis | EDA + **% thị trường theo job_family** + so sánh geo/company/seniority | ⬜ |
| P5. Insight-ML | association rules · clustering · topic modeling | ⬜ |
| P6. Recommendation | skill rec · similar-job (+ skill-gap) | ⬜ |
| P7. Dashboard (Streamlit) | drill-down Domain→Sub-domain→Family | ⬜ |
| P8. Report & Insight | seeker & recruiter | ⬜ |
| P9. Forecasting | job/skill demand theo thời gian | ⛔ HOÃN (mới 1 snapshot) |

> **Lưu ý đồng bộ (2026-06-20):** Đây là dự án **Data Analytics**, KHÔNG phải salary/ML-prediction.
> Gold cũ (7 bảng theo `role_category` rule-based) sẽ được **dựng lại theo `job_family`** sau P2.
> Nhãn nghề chuyển từ rule (nhiễu ~27%) sang **Job Family Labeling Engine** (rule+embedding+LLM).

## 4. Kiến trúc & lưu trữ (3 tầng — ĐÃ XÂY)
```
6 nguồn → raw (cache phẳng) → bronze (latest.jsonl) → warehouse.duckdb (nguồn sự thật)
                                                          → Silver (chuẩn hóa) → Gold → báo cáo/dashboard/model
```
- **raw** `data/raw/<source>/<file>` — cache theo URL, date-less. Job cũ KHÔNG fetch lại.
- **bronze** `data/bronze/<source>/latest.jsonl` — snapshot lần chạy hiện tại (ghi đè).
- **warehouse** `data/warehouse.duckdb` (gitignored) — **nguồn sự thật, tích lũy lịch sử**:
  - `jobs` (PK `source, source_job_id`): field bronze + `posted_date`, `first_seen_date`,
    `last_seen_date`, `effective_date`, `date_source`, `is_active`, `removed_date`,
    `miss_streak`, `last_updated`.
  - `job_observations` (PK `source, source_job_id, snapshot_date`): 1 dòng/job/lần chạy → trend.
- **CDC**: ID mới→insert (`first_seen`); ID cũ còn thấy→update `last_seen`; ID biến mất→đánh
  dấu gỡ (`is_active=false`). Idempotent (chạy lại cùng ngày không nhân dòng). ĐÃ TEST.

## 5. ĐÃ LÀM (chi tiết — đừng làm lại)
### 5.1. 6 connector + dữ liệu (~1.700 job, JD 100% — số lượng thay đổi mỗi lần cào)
| Nguồn | Số job | JD | Skills tag | Cách lấy / ghi chú |
|---|--:|---|--:|---|
| VietnamWorks | 790 | 100% | ~100% | JSON API trực tiếp; ngày `createdOn` ISO |
| CareerViet | 382 | 100% | 79% | HTML trực tiếp (openresty); JD từ `JobPosting` ld+json |
| ITviec | 286 | 100% | ~100% | HTML qua ScraperAPI; JD `/content`; ngày tương đối |
| TopCV | 99 | 100% | 49% | **Cloudflare** → qua Claude-in-Chrome (Chrome đăng nhập) |
| TopDev | 82 | 100% | 94% | JSON API; **robots cấm → override cá nhân**; ngày `published.date` |
| Glints | 62 | 100% | 100% | GraphQL trực tiếp; đã lọc role Data; JD `getJobById` |

`posted_date` phủ **100% cả 6 nguồn**. Ngoài ra cột **`effective_date = COALESCE(posted_date,
first_seen_date)`** (luôn non-null) + **`date_source`** ('site' / 'first_seen') đảm bảo mọi job
luôn có ngày dùng được, minh bạch nguồn gốc.

### 5.2. CLI (`python -m pipeline ...`)
`inspect` (khảo sát) · `scrape` (cào) · `enrich --source <s>` (điền JD) · `load` (Bronze→DuckDB CDC)
· `silver` (chuẩn hóa + dedup → `jobs_silver`) · `gold` (7 bảng aggregate).
Bonus: `pipeline/topcv_browser_merge.py` (gộp JD TopCV từ Chrome). Code: `pipeline/{ingest,transform,utils,quality}/`.
Tests: `tests/` (pytest, 21 test) + CI `.github/workflows/pipeline.yml`.

### 5.3. Silver (ĐÃ XONG) — `jobs_silver`
1.701 job đã chuẩn hóa; **571 là role Data thật** (non-OTHER), còn lại OTHER là nhiễu (chủ yếu
VNW search "data" rộng: sales/tư vấn/tuyển dụng có chữ "data") → loại khỏi model/Gold.
**112 trùng chéo nguồn** (rapidfuzz). Skills chuẩn hóa qua từ điển song ngữ; token chưa map ghi
ở `data/quality/unmapped_skills.csv` để mở rộng dần. Hồ sơ skill theo role khớp trực giác
(DE: SQL/Python/ETL/DWH · DA: SQL/Data Analysis/Reporting/Power BI · DS: Python/Statistics/ML).

## 6. QUYẾT ĐỊNH ĐÃ KHÓA (⚠️ KHÔNG ĐƯỢC ĐỔI)
1. Salary, LinkedIn, forecasting tăng trưởng → loại bỏ (như §1).
2. `role_category` ∈ {DE, DS, DA, MLE, BI, AE, OTHER}, suy ra từ **title + position-label + skills**.
   Tin mơ hồ/không-Data → **OTHER**, GIỮ để đếm nhưng **LOẠI khỏi training model**.
3. Lưu trữ: raw phẳng + bronze `latest.jsonl` + DuckDB warehouse (KHÔNG quay lại folder theo ngày).
4. Dedup chéo nguồn: rapidfuzz trên `company + title + city`, giữ bản `first_seen` sớm nhất.
5. Nguồn free-text (CareerViet, Glints, TopCV) khớp NHIỄU (vd `data-warehouse`→"Thủ Kho") →
   Silver phải lọc về role Data thật (qua `role_category`→OTHER).
6. Snapshot/trend = từ `job_observations` + `first_seen/last_seen`, KHÔNG copy full theo ngày.

## 7. HỢP ĐỒNG OUTPUT CỦA SILVER (ĐÃ XONG — bảng `jobs_silver` trong `warehouse.duckdb`)
Cột: `job_id (= source:source_job_id), source, source_job_id, title_clean, company,
company_key (bỏ hậu tố pháp lý, dùng cho dedup), role_category, seniority, city, region,
remote_flag, skills (JSON mảng chuẩn hóa), n_skills, language_req (JSON, EN/JP/KO), company_type,
posted_date, effective_date, date_source, first_seen_date, last_seen_date, is_active,
is_duplicate_of (job_id bản gốc nếu là trùng)`. Lịch sử snapshot qua `job_observations`.
Reference dicts: `ref/{skills_dictionary,role_keywords,seniority_rules,company_type}.yml`
(song ngữ EN/VI). **Bước sau (Gold/Model/Analyze/Dashboard) CHỈ đọc `jobs_silver`/Gold, không
sửa lại. Phân tích lọc `role_category != 'OTHER' AND is_active AND is_duplicate_of IS NULL`.**

## 8. VIỆC TIẾP THEO — roadmap chi tiết
> **Roadmap từng bước chính thức = [MASTER_PLAN.md](MASTER_PLAN.md) §10 (B1–B11).** Bước ngay sau Silver
> KHÔNG phải Gold-cũ mà là **P2 — Job Family Labeling Engine** (B1 chốt `taxonomy_v1.yml` data-informed →
> B2 rule → B3 embedding → B4 LLM ensemble → B5 voting/confidence/reviewer → B6 KPI/spot-check →
> B7 tích hợp `job_family` + re-Gold + % thị trường). Phân vai: [WORK_DIVISION.md](WORK_DIVISION.md).
### 8.1. Gold (bảng tổng hợp) — ✅ ĐÃ XONG (`python -m pipeline gold`)
7 bảng trong DuckDB từ `jobs_silver`, lọc `role_category!='OTHER' AND is_active AND
is_duplicate_of IS NULL` (**597 job Data**). Đã verify (pct hợp lệ, top-skill theo role đúng
trực giác). Top skill: SQL 54% · Python 48% · Reporting 42% · Data Analysis 41% · ML 34%.
Learning-path mạnh nhất: Python+SQL, Data Analysis+SQL, ML+Python. Các bảng:
- `skill_demand` (skill, role_category, count, pct_of_role)
- `skill_cooccurrence` (skill_a, skill_b, count) — cạnh learning-path
- `role_skill_matrix` (role × skill share)
- `seniority_progression` (seniority, skill, share)
- `role_by_location` (role, city, count)
- `company_type_demand` (company_type, role/skill counts)
- `trend` (snapshot_date, skill, count) — từ `job_observations`; **chỉ mô tả, KHÔNG dự báo**

### 8.2. Phân tích nâng cao (insight ML) — Teammate (xem §9): association rules + clustering + topic modeling (unsupervised). KHÔNG supervised classifier, KHÔNG LLM-benchmark.
### 8.3. Analyze (notebook) + Dashboard (Streamlit) — chia sau (xem WORK_DIVISION.md)
### 8.4. Report (báo cáo môn học) — xem §10
### 8.5. Tests (pytest) + CI (`.github/workflows/pipeline.yml`)

## 9. ĐỀ XUẤT CHỌN MODEL ⭐ (phần quan trọng — đọc kỹ)
**Bối cảnh quyết định loại model:** KHÔNG có lương; mới 1 snapshot (chuỗi thời gian gần như
chưa có). ⇒ Không có target liên tục hay tương lai để đoán. **KHÔNG làm** regression/forecasting
(lương, tăng trưởng, cầu tương lai) — ngoài phạm vi + thiếu dữ liệu. Ở đây model KHÔNG dùng để
**dự đoán**, mà để **mô tả cấu trúc, khám phá pattern, kiểm chứng, và khuyến nghị**.

**⚠️ Cảnh báo circularity (phải đọc trước khi train classifier):** `role_category` được suy ra
bằng LUẬT từ title + position-label + skills (§6 mục 2). Nếu train classifier để đoán
`role_category` mà lại dùng title/skills làm feature → **vòng tròn**: model học lại chính luật gán
nhãn → accuracy cao GIẢ TẠO, "insight skill X đặc trưng role Y" chỉ phản chiếu luật của mình,
không phải khám phá độc lập. Bắt buộc xử lý (mục 4 dưới) và ghi vào Hạn chế (§11).

**Thứ tự ưu tiên cho mục tiêu thật ("nên học gì") — đặt đúng ngôi sao:**
1. **(XƯƠNG SỐNG — KHÔNG cần ML) bảng Gold descriptive**: `role_skill_matrix`,
   `seniority_progression`, `skill_demand` → trả lời TRỰC TIẾP "role/seniority nào cần skill nào".
   Đơn giản nhưng trung thực và đúng trọng tâm nhất.
2. ⭐ **(NGÔI SAO — prescriptive, unsupervised) Association rules** (Apriori/FP-growth) trên mảng
   `skills` → "biết X thường đi kèm Y" = combo nên học. Không nhãn → không leakage; trả lời thẳng
   câu hỏi cốt lõi.
3. **(KIỂM CHỨNG — unsupervised) Clustering** (KMeans/HDBSCAN trên vector skill) → các role Data
   ở VN có thật sự tách theo skill không, hay DE/DS/DA nhập nhằng? Đối chiếu cụm tự nhiên với
   taxonomy role → **kiểm chứng độc lập** hệ thống gán nhãn. Không dùng nhãn → không circular.
4. **(KHÁM PHÁ — unsupervised) Topic modeling** (LDA/NMF trên JD free-text) → các "chủ đề"
   kỹ năng/công nghệ ẩn vượt ngoài skill-tag (vd cụm cloud-data, BI-báo cáo, ML/AI). Trả lời
   "công nghệ nào đang nổi" — insight mà thống kê thuần khó lộ.
5. *(tùy chọn, CHỈ để VẼ)* **Giảm chiều** (UMAP/PCA) để trực quan hóa cụm / không gian skill.

**✅ GIỮ — LLM LABELING = bước LÀM SẠCH NHÃN role (KHÔNG phải train model):**
Câu hỏi cốt lõi cần **% thị trường mỗi nhánh** (DA/BI/DE/DS/AI-MLE/BA…). Nhiều job KHÔNG có chữ
"data" ở title nhưng JD/skills cho thấy là role data → **rule theo title không đủ** (rule cũ nhiễu
~27%). Dùng **LLM đọc title+JD+skills → gán nhánh** (consensus 2–3 model; engine `pipeline/dataset/
annotate.py` + `agreement.py` ĐÃ BUILD). Đây là bước **gán nhãn/làm sạch** phục vụ thống kê mô tả —
đúng việc của Data Analyst. (Spot-check tay ~30–50 job để báo cáo độ tin cậy, KHÔNG cần golden/test.)

**❌ LOẠI — phần ML thừa (không tạo insight):**
- **Supervised classifier** (train LogReg/LightGBM/XGB để *dự đoán* role job mới; macro-F1; train/
  test split): ta chỉ cần GÁN NHÃN tập này, không cần MÔ HÌNH dự đoán → bỏ. (`train_eval.py`/`splits.py` park.)
- **Bộ máy benchmark** (golden test, IAA Krippendorff/MASI, bias-audit, multi-setting): research overhead → bỏ.
- **Salary prediction**: vẫn loại (không lương).

**Bảng biện minh ML (mọi ML phải tạo insight, nếu không → bỏ):**

| Thành phần | Vai trò / câu hỏi | Tạo insight? | Giữ? |
|---|---|---|---|
| **LLM labeling** (consensus, đọc title+JD) | gán nhánh Data mỗi job → **% thị trường** + skill theo nhánh | ✅ làm sạch nhãn (rule không đủ) | ✅ **Giữ** |
| Supervised classifier (train/predict) | dự đoán role job mới | ❌ không cần | ❌ Bỏ |
| Benchmark formalism (golden/IAA/MASI) | đo chất lượng học thuật | ❌ | ❌ Bỏ |
| Association rules (skills) | "skill nào học cùng nhau?" | ✅ combo learning-path | ✅ Giữ (⭐) |
| Clustering (skill/JD vector) | "nhóm nghề tự nhiên? role tách?" | ✅ cấu trúc + kiểm chứng | ✅ Giữ |
| Topic modeling (JD) | "chủ đề công nghệ ẩn?" | ✅ theme tiềm ẩn | ✅ Giữ |
| Salary prediction | — | ❌ | ❌ Bỏ |

**Tóm tắt:** **LLM labeling** lo phần *gán nhãn nhánh Data* (→ % thị trường, nền cho mọi thống kê);
ML insight = **association rules + clustering + topic modeling** (unsupervised). **KHÔNG train
classifier, KHÔNG benchmark.** Xương sống = bảng descriptive + thống kê so sánh trên nhãn LLM.

## 10. CẤU TRÚC BÁO CÁO MÔN DATA ANALYST (mục tiêu cuối)
1. Đặt vấn đề & mục tiêu (thị trường Data VN; "nên học gì").
2. Thu thập dữ liệu (6 nguồn, phương pháp, đạo đức/robots, ~1.700 job, JD).
3. Tiền xử lý (Silver: chuẩn hóa skill/role/seniority/location, dedup, từ điển).
4. EDA / descriptive (phân bố role/thành phố/loại công ty; top skill).
5. Diagnostic (khác biệt role DE/DS/DA/MLE/BI; HN vs HCM vs ĐN; product vs outsourcing vs bank).
6. Phân tích nâng cao (§9): **association rules (learning path) + clustering (kiểm chứng/khám phá
   nhóm) + topic modeling (chủ đề công nghệ ẩn)** — tất cả unsupervised, tạo insight. KHÔNG classifier.
7. Kết luận & khuyến nghị ("kỹ năng nên học" theo role/seniority).
8. **Hạn chế** (§11) + hướng phát triển.
9. Khả năng tái lập (pipeline, lệnh chạy).

## 11. HẠN CHẾ (ghi rõ trong báo cáo — biến điểm yếu thành sự trung thực)
- **Không có lương** → không phân tích/dự đoán thu nhập hay mức tăng trưởng.
- **Mới 1 snapshot** → `trend` hiện chỉ minh họa; cần tích lũy nhiều tuần để mô tả xu hướng
  (vẫn **không** forecasting). Cron `scrape→enrich→load` hằng tuần sẽ tích dữ liệu này.
- **Nhãn role = LLM consensus labeling** (đọc title+JD+skills, 2–3 model bỏ phiếu) thay cho rule
  theo title (rule nhiễu ~27%). Hạn chế: LLM có thể lệch ở ca biên (AIE↔MLE, BA↔DA) → spot-check
  tay một mẫu + nêu độ đồng thuận judge trong báo cáo. **Không** train classifier (chỉ gán nhãn tập này).
- Volume vài trăm–nghìn job; lớp role thưa (DS/DA) → metric model cần đọc thận trọng.
- Nguồn free-text có nhiễu (đã lọc ở Silver nhưng không hoàn hảo).
- **Ngày đăng**: `posted_date` đã phủ 100% (TopDev lấy từ `published.date`). Lưu ý *backfill*:
  job tồn tại TRƯỚC lần cào đầu có `first_seen_date` = ngày cào đầu (không phải ngày đăng thật);
  với nguồn có `posted_date` thì đã là ngày thật. Phân tích "job cũ/mới" nên ưu tiên
  `effective_date` (= posted_date khi có).
- **`posted_date` khác NGỮ NGHĨA giữa các nguồn** (đừng coi là cùng loại khi phân tích):
  VNW/Glints/TopCV = ngày đăng tuyệt đối; TopDev = ngày `published`; CareerViet = ngày
  *cập nhật/làm mới* (không phải đăng gốc); ITviec = *xấp xỉ* từ "N ngày trước". Nhiều site còn
  "bump" ngày cho tin trông mới → `posted_date` có thể bị làm tươi; `first_seen_date` trung thực
  hơn với cửa sổ quan sát của mình. Khi phân tích recency/time-on-market: dùng `effective_date`
  nhưng ý thức rõ sự khác biệt này.
- TopCV cần Chrome đăng nhập để cào (cookie/session hết hạn phải lấy lại).

## 12. Cách chạy lại / automate
```bash
python -m pip install -e .            # gồm duckdb, rapidfuzz, pandas...
cp .env.example .env                  # điền SCRAPER_API_KEY (chỉ ITviec cần)
python -m pipeline scrape             # cào → bronze/<src>/latest.jsonl
python -m pipeline enrich --source careerviet   # điền JD nếu thiếu
python -m pipeline load               # bronze → warehouse.duckdb (CDC)
# TopCV: cần Chrome + extension Claude-in-Chrome (xem §5.1)
```
Automate: cron chạy `scrape → enrich → load` hằng tuần → warehouse tự cập nhật job mới/gỡ,
không cào lại từ đầu, không phình lưu trữ.

## 13. ⭐ JOB FAMILY ENGINE — ✅ ĐÃ CHẠY XONG (2026-06-23, dynamic failover)
**KẾT QUẢ THỰC TẾ (label → label-kpi → integrate đều chạy thành công):**
- **1701/1701 job gán nhãn, 100% resolved, 0 manual_review.** Method mix: rule 527 · embedding 58 ·
  LLM 1116 (groq8b 476 · cerebras 358 · mistral 154 · groq 102 · qwen 26 — gemini tự reroute do hết quota).
- Confidence: 1483 ở [0.85-1.0], 213 ở [0.66-0.85], 5 ở [0.5-0.66]. OTHER 45.8% (nhiễu VNW như dự kiến).
- **852 job Data/AI** (active, non-dup, non-OTHER) → `jobs_silver.job_family` + 7 bảng Gold + market share
  (tổng 99.9%): **BA 21.2% · DE 17.5% · DA 14.7% · AIE 13.8%** · RISK 6.1% · BI 5.0% · DS 3.9% · …
- Artifacts: `data/labeling/job_family.parquet`, `docs/labeling_kpi.md`, `data/labeling/spot_check.csv`,
  Gold tables trong `warehouse.duckdb`.
- **Spot-check (2026-06-23):** đã review tay mẫu stratified 21 job (1/family) → **đúng hết** → engine
  đáng tin để dùng cho phân tích. (Có thể nâng `spot_n` nếu muốn mẫu lớn hơn cho báo cáo.)
- → **Bàn giao Teammate: phân tích chỉ đọc `jobs_silver.job_family` + bảng `gold_*`.** 45 test pass.

**(Lịch sử) Engine module `job_family_engine/`:**
- `taxonomy/taxonomy_v1.yml` — phân cấp Domain→Sub-domain→Family (6 domain, 21 family), versioned.
- `rules.py` (Tier-1, title-only, ~30% = 527 job conf≥0.9) · `embed_match.py` (Tier-2, e5 cosine,
  T≥0.82/margin≥0.02 → 58 job) · `llm_judge.py` (Tier-3: `classify_once` 1-call + `cached_any`
  resume + `RateLimited`/`_reset_seconds` parse 429 header+body+daily-quota).
- `engine.py` cascade — **DYNAMIC DISPATCHER + FAILOVER** (thay cho partition tĩnh từng-stall-2h):
  1 hàng đợi chung, worker pool chọn provider rảnh nhất; **429 ngắn→cooldown+requeue, 429 dài/hết-quota
  →đánh dấu exhausted+reroute, hết sạch provider→manual_review**. Một provider dính limit KHÔNG còn
  ghì được các provider khác. `integrate.py` (B7) + `evaluate.py` (B6, đã sửa lọc `llm:` method) viết xong.

**6 provider (key, req/phút, daily cap):** groq8b 15/14000 · gemini 15/1400 · groq-70b 24/950 ·
cerebras 5/2300 · mistral 3/300 · qwen 2/45. **Smoke-test 2026-06-22:** groq8b/groq-70b/cerebras/
mistral/qwen ✅; **gemini key hiện trả 429 hết-quota → engine tự reroute** (groq8b 14.4k/ngày một
mình thừa sức gánh). Combined daily cap ≫ corpus → chắc chắn xong.

**Dry-run local (0 quota) + smoke xác nhận:** tier1+tier2 giải **585**; LLM remainder **1116** (dedup
theo content_hash → 1111 unique), trong đó **760 đã cached** → **chỉ còn ~351 job cần gọi LLM** →
~6-10 phút.

**Đã qua 2 vòng review đối nghịch (multi-agent) + sửa toàn bộ finding xác nhận:** vòng 1 → fix
concurrency (mỗi job luôn finalize/requeue đúng 1 lần) + backstop chống treo; vòng 2 → fix **blocker
double-finalize** (guard progress-print), **parse reset giờ** (Groq daily-cap "1h23m" trước bị đọc
thành ~1s → giờ exhaust+reroute đúng), method nhất quán live/cache, dedup content_hash, cache tự-lành
khi file hỏng + ghi parquet atomic, tighten nhận diện 429. **45 test pass.**

**CHẠY SÁNG MAI (3 lệnh, ~25-30 phút, dùng Python314):**
```bash
PY="C:/Users/znigh/AppData/Local/Programs/Python/Python314/python.exe"
"$PY" -m pipeline label        # gán job_family → data/labeling/job_family.parquet (~24 phút)
"$PY" -m pipeline label-kpi    # KPI + spot_check.csv → docs/labeling_kpi.md
"$PY" -m pipeline integrate    # job_family → jobs_silver + family Gold + % thị trường
```
Sau đó verify: `gold_market_share` % cộng = 100, spot-check hợp lý → bàn giao Teammate.
Nếu provider đổi policy/key: chỉ sửa `engine.PROVIDERS` + `llm_clients._MIN_INTERVAL`.
> Lưu ý: §8.1 "Gold ✅ XONG" là **Gold cũ theo `role_category`** (legacy/baseline). Gold mới theo
> `job_family` sẽ do `integrate` dựng (gold_jobs, gold_market_share, gold_family_skill,
> gold_company, gold_location, gold_seniority, gold_skill_cooccurrence).
