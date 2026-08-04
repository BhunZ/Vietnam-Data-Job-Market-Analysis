# Trạng thái & Cẩm nang dự án — VN Data Job Market Intelligence

> **Tài liệu bàn giao (authoritative).** Đọc kỹ trước khi làm tiếp. Cập nhật: 2026-07-07.
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
| **P2. ⭐ Job Family Labeling Engine** | taxonomy phân cấp + cascade 3 tầng (rule→embedding→LLM dynamic-failover) + metadata + `job_family` | ✅ **XONG** — 1701 job gán nhãn (100% resolved), tích hợp vào jobs_silver + 8 bảng family Gold (xem §13) |
| P3. Feature/NLP | skill extraction/embedding/keyword; feature outputs | ◐ **NỀN ĐÃ CÓ** — `jobs_silver.skills`, `job_family`, text/embedding artifacts; chưa mở rộng NER/keyphrase mới |
| P4. Market & Statistical Analysis | EDA + **% thị trường theo job_family** + so sánh geo/company/seniority | ◐ **ĐÃ CÓ MẪU + VALIDATION** — `analysis/market_insights.py`, `analysis/robustness_figures.py`, `analysis/career_map.py` |
| P5. Insight-ML | association rules · clustering · topic modeling | ✅ **XONG** — Association Rules ✅; Clustering ✅; Topic Modeling ✅ |
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
**Thứ tự chuẩn (nguồn duy nhất):**
`scrape` → `enrich --source <s>` → `load` → `silver` → `discover` → `label` → **`refine`** →
**`enrich-llm`** → (tùy chọn **`apply-manual`**) → `label-kpi` → `integrate` → `gold`.
· `enrich-llm` điền `seniority` + ngành công ty ở những chỗ rule bỏ trống (LLM, có cache); ngành công ty
  cần **2 judge đồng thuận** mới nhận, bất đồng thì giữ `unknown`.
· `apply-manual` áp danh sách công ty bạn tự gán trong `data/labeling/company_industry_todo.csv`.
⚠️ `gold` giờ **phụ thuộc `integrate`** (nó lọc theo `job_family`, sẽ thoát sớm nếu chưa có cột đó).
Ngoài ra: `inspect` (khảo sát).
Bonus: `pipeline/topcv_browser_merge.py` (gộp JD TopCV từ Chrome). Code: `pipeline/{ingest,transform,utils,quality}/`.
Tests: `tests/` (pytest, 61 test) + CI `.github/workflows/pipeline.yml`.

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
(song ngữ EN/VI). **Bước sau (Gold/Analyze/Dashboard) CHỈ đọc `jobs_silver`/Gold, không sửa lại.**
⚠️ **Phân tích lọc theo `job_family`, KHÔNG theo `role_category`** (cột rule cũ, nhiễu ~27%, chỉ giữ để
so sánh baseline). Định nghĩa chuẩn duy nhất: `pipeline/utils/analysis_base.py::ANALYSIS_BASE_WHERE`.

## 8. VIỆC TIẾP THEO — roadmap chi tiết
> **Roadmap từng bước chính thức = [MASTER_PLAN.md](MASTER_PLAN.md) §10 (B1–B11).** P2 Job Family
> Labeling Engine đã hoàn thành và đã tích hợp vào `jobs_silver` + Family Gold. Việc tiếp theo hiện
> nằm ở **P5 Insight-ML**: đã xong Association Rules + **Clustering** + **Topic Modeling**.
> Phân vai: [WORK_DIVISION.md](WORK_DIVISION.md).
### 8.1. Gold (bảng tổng hợp) — ✅ ĐÃ XONG (`python -m pipeline gold`)
7 bảng trong DuckDB từ `jobs_silver`, lọc theo `ANALYSIS_BASE_WHERE` (job_family, **720 job Data**). Đã verify
2026-07-28 bằng cách tính lại từ `jobs_silver`: `gold_market_share`/`gold_seniority`/`gold_company`/`gold_domain_share`
lệch **0 dòng**, `gold_family_skill` 0/683 sai `share_in_family`, không bảng nào trùng khoá grain.
Top skill: SQL 47,8% · Python 43,5% · Data Analysis 39,6% · Reporting 38,3% · English 33,8% ·
Machine Learning 30,4% · **Database 28,1%** · **Data Management 27,9%** · Power BI 24,4% ·
**Data Science 21,0%** · **Cloud 20,8%**.

**Bổ sung từ điển kỹ năng 2026-07-28:** 7 kỹ năng trước đây xuất hiện nhiều nhưng **không được đếm ở đâu cả**
đã được thêm vào `ref/skills_dictionary.yml`: Business Analysis · Data Management · Data Science · Database ·
Cloud · API · ERP. Quy tắc: chỉ thêm token rõ ràng là kỹ năng và ≥20 lần. **Cố ý không thêm** kỹ năng mềm
(Communication sẽ phủ 37,4%, Analytical Skills 28,1%, Leadership 16,4%) vì từ điển được quét trên **toàn văn
JD**, nên chúng bắn từ câu sáo rỗng và ghép cặp vô nghĩa với mọi thứ trong association rules.
Learning-path mạnh nhất: Python+SQL, Data Analysis+SQL, ML+Python. Các bảng:
- `skill_demand` (skill, role_category, count, pct_of_role)
- `skill_cooccurrence` (skill_a, skill_b, count) — cạnh learning-path
- `role_skill_matrix` (role × skill share)
- `seniority_progression` (seniority, skill, share)
- `role_by_location` (role, city, count)
- `company_type_demand` (company_type, role/skill counts)
- `trend` (snapshot_date, skill, count) — từ `job_observations`; **chỉ mô tả, KHÔNG dự báo**.
  ⚠️ Chỉ có **1 snapshot** (2026-06-16) nên số của nó **trùng y hệt `skill_demand`** (SQL = 344 ở cả hai).
  Bảng không mang thêm thông tin nào; tên `trend` là bẫy — đừng dùng nó để nói tăng/giảm.

⚠️ **8 bảng `gold_*` do `job_family_engine/integrate.py` sinh ra chứa cùng nội dung với 4 trong 7 bảng trên**
(`skill_cooccurrence`≡`gold_skill_cooccurrence`, `role_skill_matrix`≡`gold_family_skill`,
`role_by_location`≡`gold_location`, `company_type_demand`≡`gold_company` — kiểm 2026-07-28, lệch 0 dòng).
Nhưng `skill_demand`, `seniority_progression`, `trend` **chỉ tồn tại ở bộ tên trần** — xoá cả bộ này là mất
3 aggregate. `gold_jobs` là bảng gold **duy nhất không lọc**: 1554 dòng, 834 = `OTHER`; đừng dùng nó làm mẫu số.

### 8.2. Phân tích nâng cao (insight ML) — Teammate (xem §9): association rules + clustering + topic modeling (unsupervised). KHÔNG supervised classifier, KHÔNG LLM-benchmark.
**Cập nhật 2026-07-11:** P5 Insight-ML đã được triển khai:
- **Association rules · KMeans clustering · NMF topic modeling: ĐÃ CHẠY, ĐÃ BỎ khỏi báo cáo (2026-08-03).**
  Cả ba đều không cho ra phát hiện đáng đưa vào một báo cáo phân tích:
  * **KMeans** — silhouette chỉ 0,125–0,174 qua k=2..20 ⇒ *không có cấu trúc cụm*. Nguyên nhân chính là
    một phát hiện thật: các nghề chia sẻ lõi kỹ năng chung quá mạnh nên mọi tin đều na ná nhau.
  * **NMF topic modeling** — 6/9 chủ đề tách theo **ngôn ngữ** của tin hoặc theo job board, không theo nội dung.
  * **Association rules** — hơn 1.200 luật vượt kiểm định nhưng các luật mạnh nhất đều hiển nhiên
    (SQL đi với Python), lift chỉ ~1,2. Kết luận rút ra ("thị trường có lõi chung mạnh") đã được đưa vào
    phần mô tả; phần luật chi tiết không cần.

  Ba kỹ thuật này được gói lại thành **ba câu** trong phụ lục `docs/INSIGHTS_BRAINSTORM.md`. Script và
  file findings đã xoá để repo khỏi phình.

- **Phân tích thay thế, ĐANG DÙNG:** `analysis/career_map.py` (bản đồ chuyển nghề + bộ kỹ năng tối thiểu +
  kiểm độ nhạy ngưỡng → `docs/CAREER_MAP_FINDINGS.md` tự sinh) và `analysis/robustness_figures.py`
  (forest plot khoảng tin cậy, độ nhạy phép đo, cơ cấu theo job board).

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
- **1701/1701 job gán nhãn, 100% resolved, 0 manual_review.** Method mix (25/07/2026): rule **489** ·
  embedding **0** (tier-2 đã siết ngưỡng → không nhận job nào) · LLM **1212** (`vote:*` 1182 + `refine:*` 27
  + `refine-knockout:*` 3). Judge tham gia: cerebras · mistral · qwen · github · groq · cloudflare.
- OTHER **51,9%** (nhiễu do scrape-query rộng, như dự kiến). `confidence_score` KHÔNG dùng làm thước đo
  chất lượng: nó trộn 3 thang khác nhau (hằng số 0.9 cho rule, cosine cho embedding, LLM tự khai).
- **720 job Data/AI** (active, non-dup, non-OTHER, resolved) → `jobs_silver.job_family` + **8 bảng Gold**.
- Artifacts: `data/labeling/job_family.parquet`, `docs/labeling_kpi.md`, `data/labeling/spot_check.csv`,
  Gold tables trong `warehouse.duckdb`.

> ⚠️ **SỐ HIỆN TẠI (28/07/2026) — mọi con số ở trên đã bị thay thế.** Analysis base = **720**;
> `jf_review` = `resolved` cho cả 1701 dòng (0 `manual_review`, 0 `domain_only`).
>
> **Tầng nào quyết định nhãn, trên base 720:** rule (regex tiêu đề) **426 = 59,2%** · vote LLM **272 =
> 37,8%** · refine **22 = 3,1%**. Nói cách khác **phần lớn base KHÔNG do LLM gán** — 317/426 tin tầng rule
> chưa từng có judge nào đọc. Chú thích trên figure đã sửa lại cho đúng tỉ lệ này.
>
> **Cấp DOMAIN — `gold_domain_share`, 720 job:** Analytics 46,9% (338) · AI/ML 24,9% (179) ·
> Data Engineering 20,1% (145) · Governance 5,6% (40) · Leadership 2,5% (18).
>
> **Cấp FAMILY chỉ để bóc chi tiết, KHÔNG xếp hạng:** BA 20,3% (146) · DE 17,4% (125) · AIE 15,3% (110) ·
> DA 14,6% (105) · BI 6,0% (43) · RISK 5,3% (38).
>
> ⚠️ **Cấp domain cũng KHÔNG bền — đo 28/07/2026.** Tỉ lệ Analytics khác nhau rất xa theo từng job board:
> vietnamworks **60,4%** · topcv 53,8% · careerviet 50,9% · itviec 28,9% · glints 25,5%. Và tỉ lệ tin
> "vào được base" cũng theo board: topcv 91,9% · glints 82,3% · itviec 66,4% · vnw 32,3% · careerviet
> 28,8% · topdev 28,0%. Vì vnw chiếm 255/720 base, **"Analytics 46,9%" phần lớn là profile của
> VietnamWorks pha loãng**, không phải cấu trúc thị trường VN. Báo cáo phải nói rõ điều này.
>
> ⚠️ **`BUSINESS_ANALYST` (top-1, 146 tin) là family HỖN HỢP — và nó được gán ĐÚNG.**
> **Đính chính 2026-08-03:** bản trước của mục này viết "không nên gọi là nghề data". Sai. Taxonomy đặt
> BUSINESS_ANALYST trong domain **Analytics**, và prompt gán nhãn nói rõ *"IT/systems/**requirements**/
> data/reporting work → BUSINESS_ANALYST; general market/sales/strategy → OTHER"*. Một BA phần mềm viết
> BRD/SRS **là BA, gán đúng**. Phép đo cũ dùng tiêu chí riêng (phải có SQL/Python mới tính là data) —
> tiêu chí mà project đã chủ động bác bỏ. Hệ quả "loại 31 tin thì DE thành #1" **không có cơ sở**.
>
> Điều đo được vẫn thật, chỉ khác cách hiểu: **family này không đồng nhất bên trong** — ~55% tin có công
> cụ phân tích, ~21% chỉ có đặc tả/ERP/UAT, còn lại ở giữa. Đây là chuyện **phạm vi trình bày**, không
> phải chất lượng nhãn: người đọc nghe "family data lớn nhất" sẽ tưởng người làm phân tích, nên phải chú
> thích rằng rổ đó gồm cả người viết đặc tả cho lập trình viên.
>
> **Nhãn phụ thuộc judge nào còn quota.** Đo ghép cặp trên cache v3 (cùng tin, cùng prompt,
> `temperature=0`), 293 tin có phiếu của cả 3 judge lớn: tỉ lệ gọi `OTHER` là cerebras **75,4%** ·
> mistral **70,0%** · groq-8b **60,1%**; `DATA_ENGINEER` 1,7% vs 10,6%. Đồng thuận từng cặp dao động
> **44,8%–92,5%**; cặp thực dùng nhiều nhất (cerebras+mistral, n=820) là **82,7%**. Vote 2-judge không
> phát hiện được lỗi này vì mọi judge lệch cùng chiều.

- ⭐ **Spot-check: ĐÃ XONG, và đây LÀ con số accuracy (2026-07-31).** `data/labeling/spot_check.csv` đã điền
  đủ **30/30**, không giá trị nào sai định dạng. Người review gán `human_family` **khi đã ẩn cột
  `job_family` và `reasoning`** rồi mới so — tức gán nhãn **mù**, nên khác hẳn kiểu "đọc lý do thấy hợp lý"
  và nó **cho ra được accuracy**.

  | | Khớp với nhãn người |
  |---|---|
  | **Toàn mẫu** | **29/30 = 96,7%** (Wilson 95% CI **83,3%–99,4%**) |
  | Có trọng số theo `stratum_size` | 96,8% |
  | Tầng `vote` (≥2 judge) | 18/18 = **100%** |
  | Tầng `refine` | 3/3 = **100%** |
  | **Tầng `rule` (regex tiêu đề)** | **8/9 = 88,9%** |

  **Ca lệch duy nhất đúng bằng thứ audit đã dự đoán:** một tin `BUSINESS_ANALYST` do **tầng rule** gán
  ("Chuyên Viên Phân Tích Nghiệp Vụ"), người đọc ra `OTHER`. Mọi nhãn do LLM quyết trong mẫu **đều đúng**;
  lỗi duy nhất đến từ tầng chỉ đọc tiêu đề.

  ⚠️ Giới hạn phải nói kèm: **n=30 nhỏ**, khoảng tin cậy rộng (83,3%–99,4%), và 11/30 dòng thuộc stratum
  `OTHER` vốn là nhóm dễ. Đây là ước lượng, không phải phép đo chính xác.
- (lịch sử) Trước đó: Mẫu 21 job đã được review tay ở một session/máy khác
  (kết quả báo: đúng hết), nhưng **bản ghi không được lưu** — cột `human_family` trong
  `data/labeling/spot_check.csv` trống 21/21, và `data/labeling/` bị gitignore nên không có history.
  Lưu ý: mẫu đó thuộc thời **tier-2 còn bật**, mà tier-2 sau này bị xác định sinh nhãn sai
  (`Software Engineer → BIG_DATA_ENGINEER`) → kết luận "đúng hết" có thể có trước khi phát hiện lỗi này.
- **Vì vậy bằng chứng chất lượng dùng được hiện tại = độ đồng thuận giữa các LLM độc lập
  (reliability), KHÔNG phải accuracy.** Muốn có accuracy trích dẫn được: điền `verdict`/`human_family`
  trên mẫu phân tầng mới (`evaluate.py` đã sinh, có `stratum`/`stratum_size` để tính trọng số, kèm
  `reasoning` để review nhanh — chỉ cần phán "lý do có vô lý không", không cần đọc lại JD).
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
