# Lộ trình biến project này thành một project Data Engineering

*Ghi lại buổi thảo luận 2026-07-28. **Chưa triển khai gì** — file này để bàn tiếp sau khi xong báo cáo môn.*

> **Quyết định đã chốt:** nhịp chạy **hàng tuần**.
> **Còn để mở:** chạy ở đâu (máy local / cloud). Người dùng muốn nhân dịp này học Cloud → xem §5.

---

## 1. Vấn đề chặn: hôm nay chạy scrape sẽ KHÔNG phát hiện được tin mới nào

Đây là việc phải sửa đầu tiên, vì mọi thứ khác vô nghĩa nếu không có nó.

Cache HTTP là **phẳng, không có ngày** (`pipeline/utils/http.py:111-116`). Tên cache của trang danh sách chỉ
mã hoá *category + số trang*:

```
data/raw/itviec/listing_data-analyst_p1.html      ← không có ngày
data/raw/vietnamworks/search_data-analyst_p1.json ← không có ngày
```

Hiện có **147 file listing** đã cache (careerviet 18 · glints 81 · itviec 28 · vietnamworks 20). Lần chạy
thứ hai sẽ cache-hit 100% và trả về đúng tập 1.701 job của 16/06/2026. Không tồn tại cờ `--fresh` /
`--no-cache` / TTL nào.

**Hệ quả:** toàn bộ tầng CDC đã xây (`first_seen_date`, `last_seen_date`, `miss_streak`, `removed_date`)
**không bao giờ kích hoạt được**. `job_observations` vĩnh viễn chỉ có 1 snapshot.

Hai comment trong code còn nói ngược nhau — cần sửa cả hai khi fix:
* `http.py` bảo *"snapshots live in the dated Bronze layer, not here"*
* `scrape.py:46` bảo *"History lives in the DuckDB warehouse, not in dated folders"*

Không cái nào đúng với tầng listing: nó chỉ đơn giản bị đóng băng.

**Cách sửa:** tách chính sách cache theo loại trang.

| Loại trang | Chính sách | Lý do |
|---|---|---|
| `detail_*` (733 file JD) | Giữ **vĩnh viễn** | JD không đổi. Đây là chỗ tốn tiền ScraperAPI và thời gian |
| `listing_*` / `search_*` | Tách **theo ngày**: `raw/<source>/<ngày>/...` | Phải tươi mới phát hiện được tin mới/tin mất |

Hiện thực: thêm tham số `volatile: bool = False` vào `HttpClient.fetch()`; khi `volatile=True` thì
`_cache_path` chèn `run_date` vào đường dẫn. Rồi 6 module trong `pipeline/ingest/` truyền `volatile=True`
cho các lời gọi listing. **Sửa 7 chỗ nhỏ.**

---

## 2. Bốn việc để thành pipeline thật

**Việc 1 — Sửa cache listing.** Như §1. *Nhỏ.* **Đây là điều kiện tiên quyết cho mọi phương án.**

**Việc 2 — Bronze ghi thêm theo ngày, không ghi đè.**
Hiện `_persist()` ghi `bronze/<source>/latest.jsonl` và **ghi đè mỗi lần** (`pipeline/scrape.py:45`). Nếu một
lần scrape lỗi giữa đường, dữ liệu thô lần trước **mất luôn**. Đổi sang `bronze/<source>/<ngày>.jsonl` cộng
một con trỏ `latest`. Việc này cho tính chất quan trọng nhất của một project DE: **warehouse dựng lại được
hoàn toàn từ dữ liệu thô**. Guard carry-forward hiện có (giữ lại `description_raw`/`skills_raw` khi
re-scrape chỉ có listing) phải giữ nguyên. *Nhỏ–trung bình.*

**Việc 3 — `pipeline all` thật + cổng chặn chất lượng.**
Hiện `all` là stub: rơi xuống nhánh cuối, in *"not implemented yet (Phase 1 ships 'inspect' only)"* và exit 1.
Header help dòng 9 thì vẫn quảng cáo nó chạy cả chuỗi — sửa cả hai.
Và `analysis/validate_gold.py` hiện **chỉ in ra, không có exit code** → nó là báo cáo, không phải cổng chặn.
Cho nó exit ≠ 0 khi số không khớp, rồi đặt làm bước cuối của `all`. *Nhỏ.*

Thứ tự đúng (đã có guard chặn sai thứ tự từ 2026-07-28):
```
scrape → load → silver → label → refine → enrich-llm → integrate → gold → validate
```

**Việc 4 — Bảng `pipeline_runs` trong DuckDB.**
Hiện **không có gì**. Không trả lời được câu *"tối qua pipeline chạy có ổn không?"*. Cần:
`run_id · bước · thời gian bắt đầu/kết thúc · số dòng vào/ra · trạng thái · thông báo lỗi`. *Nhỏ.*

---

## 3. Cái bẫy lớn nhất khi tự động hoá: parser hỏng lặng lẽ

Không phải quota. Nếu một job board đổi HTML, parser có thể:
* trả về **0 tin** → dễ thấy, không nguy hiểm;
* trả về **800 ID rác trông như tin mới** → khó thấy, và sẽ đốt hết quota LLM trong một đêm rồi nhồi rác
  vào warehouse.

**Chốt bảo vệ (làm cùng Việc 3):** nếu số tin mới trong một lần chạy vượt **25% corpus hiện tại** thì
**dừng, không gán nhãn, báo lỗi**. Vừa bảo vệ quota, vừa là tín hiệu phát hiện parser hỏng. Với nhịp hàng
tuần, tin mới bình thường ước chừng **50–150**.

**Chi phí LLM cho mỗi lần chạy tăng thêm là nhỏ**, nhờ cache nhãn khoá theo `content_hash`: tin cũ được
dùng lại phiếu, **chỉ tin mới mới tốn call**. Lưu ý `content_hash` = hash của *(title + jd + skills)*, nên
đổi `ref/skills_dictionary.yml` sẽ làm cache miss — nhưng chỉ khi `jobs_text.parquet` được sinh lại.

---

## 4. Một artifact stale không ai theo dõi (phát hiện 2026-07-28)

`data/dataset/text/jobs_text.parquet` — **input của labeling engine** — có mtime **19/06**, tức mang bản
chuẩn hoá skills từ hơn một tháng trước, trong khi `jobs_silver` được xây lại 28/07. Nó **chỉ được sinh lại
bởi lệnh `discover`**, không phải bởi `silver`.

Đã kiểm: **cùng 1.701 `job_id`, lệch 0** → không tin nào bị bỏ sót nhãn, và tác động giới hạn (tầng rule đọc
*title*, tầng LLM đọc *title + JD* — cả hai không đổi theo từ điển kỹ năng). Nhưng khi tự động hoá thì phải
đưa bước sinh lại artifact này vào chuỗi, nếu không nó sẽ lệch dần một cách âm thầm.

---

## 5. Nếu muốn học Cloud trong project này

Bài học cloud giá trị nhất ở đây **không phải "chạy code ở đâu"**, mà là **"dữ liệu sống ở đâu"** — đúng chỗ
GitHub Actions bị chặn: không giữ được state giữa các lần chạy.

### Kiến trúc đề xuất (chi phí $0)

| Tầng | Dùng gì | Vì sao |
|---|---|---|
| Lưu trữ | **Cloudflare R2** (10GB free, **không phí egress**) | API tương thích S3 ⇒ học đúng API dùng ở mọi nơi. Không có bill bất ngờ |
| Compute | **GitHub Actions** + cron | Free; workflow đã tồn tại (hiện chỉ chạy test) |
| Secrets | GitHub Actions secrets | Học quản lý bí mật đúng cách |
| Kho | **DuckDB đặt trên object storage** | Pattern hiện đại thật, không phải giải pháp tạm |

**KHÔNG dùng** BigQuery / Snowflake / Redshift / Airflow / dbt / Docker. Với 1.701 dòng và 6 nguồn, chúng chỉ
thêm chỗ để hỏng, và người đọc CV có nghề sẽ thấy ngay là over-provisioning. DuckDB + object storage cho
16MB dữ liệu là lựa chọn **đúng** và bảo vệ được khi bị hỏi.

### Ba giai đoạn, theo thứ tự

**Giai đoạn 1 — làm 4 việc ở §2, vẫn hoàn toàn local.** Tự động hoá một vòng lặp phát hiện đang đóng băng
lên cloud thì chỉ là đóng băng ở chỗ đắt hơn.

**Giai đoạn 2 — chuyển bronze + warehouse lên R2, vẫn chạy ở máy mình.**
**80% bài học cloud nằm ở đây**: tách lưu trữ khỏi tính toán, object storage làm nguồn chân lý, credential
qua env. Rủi ro gần 0 vì vẫn chạy tay và thấy mọi thứ. DuckDB đọc trực tiếp parquet trên R2 qua `httpfs` —
demo rất đẹp.

**Giai đoạn 3 — đưa lần chạy hàng tuần lên GitHub Actions**, R2 làm state: tải DB về → chạy → đẩy lên.

### Rủi ro thật của giai đoạn 3 — biết trước

**Job board chặn IP datacenter mạnh hơn IP nhà rất nhiều.** Scrape từ Actions có thể bị 403 trong khi ở máy
mình vẫn chạy tốt. Project đã có `SCRAPER_API_KEY` để đi đường vòng nhưng free tier nhỏ. Các LLM free tier
cũng có thể siết hoặc chặn theo IP.

Nếu gặp chặn, phương án dự phòng **vẫn là cloud hợp lệ**: scrape ở máy mình (IP nhà, đẩy bronze lên R2),
Actions làm toàn bộ phần sau. Đó chính là kiến trúc **ingest tại biên, xử lý trên cloud** — dùng thật trong
công nghiệp, không phải chống cháy.

---

## 6. Cách chứng minh là đã xong (đừng tin lời nói)

Sau khi làm Việc 1–4, chạy **scrape hai lần cách nhau** và kiểm bằng SQL:

```sql
-- phải có >= 2 dòng
SELECT snapshot_date, COUNT(*) FROM job_observations GROUP BY 1 ORDER BY 1;

-- phải có tin mới và/hoặc tin biến mất
SELECT COUNT(*) FROM jobs WHERE first_seen_date > DATE '2026-06-16';
SELECT COUNT(*) FROM jobs WHERE miss_streak > 0;
SELECT COUNT(*) FROM jobs WHERE removed_date IS NOT NULL;
```

Nếu cả bốn con số vẫn y như hôm nay (1 snapshot, 0, 0, 0) thì cache listing **chưa** được sửa thật.

---

## 7. Việc nhỏ còn treo (không chặn gì)

* `trend` (76 dòng, 1 snapshot) có số **trùng y hệt `skill_demand`** (SQL = 344 ở cả hai) → không mang thêm
  thông tin, mà cái tên thì mời gọi kết luận xu hướng. Xoá hoặc đổi tên `skill_demand_snapshot`.
  *Sau khi CDC chạy thật thì `trend` mới có ý nghĩa — lúc đó giữ lại.*
* 15 bảng cho 8 aggregate, hai writer (`gold.py` ghi 7 tên trần, `integrate.py` ghi 8 `gold_*`; 4 cặp trùng
  khít). **Bẫy:** `skill_demand`, `seniority_progression`, `trend` **chỉ tồn tại ở bộ tên trần** — xoá cả bộ
  legacy là mất 3 aggregate.
* `gold_jobs` là bảng gold **duy nhất không lọc**: 1.554 dòng, 834 = `OTHER`. Chưa ai dùng, nhưng ai viết
  `GROUP BY job_family FROM gold_jobs` sẽ chia cho 1.554.
* `jf_review` = `resolved` cho cả 1.701 dòng ⇒ `ANALYSIS_BASE_DOMAIN_WHERE` giờ **giống hệt**
  `ANALYSIS_BASE_WHERE`; docstring còn mô tả một phân biệt `domain_only` không còn tồn tại.
* Định nghĩa 20 job family: `job_family_engine/taxonomy/taxonomy_v1.yml` liệt kê 20 mã **không mã nào có mô
  tả**, và prompt chỉ bung `code=name`. Đây là cơ chế sinh ra việc nhãn phụ thuộc judge. Viết định nghĩa thì
  rẻ, nhưng **áp dụng** thì phải bump `FAMILY_PROMPT_VERSION` → 4, làm mất 3.694 phiếu cache v3 và phải chấm
  lại toàn bộ. Cái bẫy: cache key là `content_hash + version`, **không** hash nội dung prompt — sửa prompt mà
  quên bump version thì cache lặng lẽ trả phiếu chấm dưới prompt cũ.

---

## 8. Ý tưởng sản phẩm cho sau này: hệ thống GỢI Ý nghề theo kỹ năng

*Ghi nhận 2026-08-03. Là sản phẩm, không thuộc phạm vi báo cáo môn học.*

**Ý tưởng.** Người dùng tick các kỹ năng mình đang có → hệ thống **xếp hạng các nghề phù hợp**, kèm giải
thích: *"bạn hợp Data Analyst (đã có 4/4 kỹ năng lõi) và BI (3/4, còn thiếu Business Intelligence)"*.

**Vì sao là GỢI Ý chứ không phải ĐOÁN.** Ban đầu ý tưởng là huấn luyện bộ phân loại đoán nghề từ kỹ năng.
Nhưng dữ liệu cho thấy Data Analyst / BI / Business Analyst / Risk-Fraud **chồng lấn nhau rất mạnh** — máy
nhầm chúng qua lại 16–23%. Với bài toán *đoán*, đó là **lỗi**. Với bài toán *gợi ý*, đó lại là **thông tin
đúng**: người dùng thật sự đủ điều kiện cho cả bốn, và nên chọn theo ngành mình thích chứ không theo kỹ năng.

| | "Đoán nghề" | "Gợi ý nghề" |
|---|---|---|
| Đầu ra | một nhãn | xếp hạng vài nghề + lý do |
| Khi model lưỡng lự | là lỗi | là thông tin đúng |
| Ai dùng được | không ai | người đang chọn hướng học |

**Nền tảng đã có sẵn, không cần model mới.** Chỉ cần hai thứ đã tính được từ `gold_family_skill`:
bộ **kỹ năng lõi** của mỗi nghề (kỹ năng xuất hiện ở ≥50% tin), và phép so khớp tập hợp giữa kỹ năng người
dùng với từng bộ đó. Phần "giải thích" chính là danh sách kỹ năng còn thiếu — thứ mà một mô hình học máy
hộp đen **không** đưa ra được.

**Việc cần làm khi triển khai:** kiểm độ nhạy của ngưỡng 50% (bộ kỹ năng lõi đổi bao nhiêu ở 40% và 60%),
và xử lý trường hợp người dùng chưa có kỹ năng nào.
