# Bắt đầu phân tích — đọc file này trước

*Viết 2026-07-28. Bộ dữ liệu đã hoàn chỉnh và đã kiểm. File này nói bạn đang có gì, tin được đến đâu, và
ba câu tuyệt đối không được viết. Không có gì phải chạy lại nữa.*

---

## 1. Bạn đang có gì

**720 tin tuyển dụng Data/AI**, mỗi tin đã có: nghề (`job_family`), nhánh (`jf_domain`), cấp bậc
(`seniority`), ngành của công ty (`company_type`), thành phố, và danh sách kỹ năng đã chuẩn hoá.

720 tin này lọc ra từ 1.701 tin thu thập trên 6 job board (một lát cắt duy nhất **16/06/2026**). Phần bị
loại: tin không phải nghề data, tin trùng lặp giữa các nguồn.

Lấy số liệu ở đâu — dùng các bảng này, **đừng tự viết lại điều kiện lọc**:

| Bạn muốn biết | Bảng trong `data/warehouse.duckdb` |
|---|---|
| Thị phần theo nhánh | `gold_domain_share` |
| Thị phần theo nghề | `gold_market_share` |
| Kỹ năng theo từng nghề | `gold_family_skill` |
| Cấp bậc theo nghề | `gold_seniority` |
| Ngành công ty theo nghề | `gold_company` |
| Thành phố theo nghề | `gold_location` |
| Cặp kỹ năng đi cùng nhau | `gold_skill_cooccurrence` |

Cần lọc thủ công thì import điều kiện có sẵn, đừng gõ lại:

```python
from pipeline.utils.analysis_base import ANALYSIS_BASE_WHERE
```

Ba phân tích nâng cao đã chạy xong, kết quả ở `analysis/outputs/*.csv`, giải thích ở `docs/*_FINDINGS.md`:
luật kết hợp kỹ năng · phân cụm kỹ năng · topic modeling trên JD. Năm biểu đồ ở `analysis/figures/`.

---

## 2. Tin được đến đâu

**Tầng bảng số liệu: đúng.** Đã kiểm ngày 28/07: tính lại từng dòng từ dữ liệu gốc thì `gold_market_share`,
`gold_seniority`, `gold_company`, `gold_domain_share` lệch **0 dòng**; `gold_family_skill` 0/683 dòng sai;
không bảng nào trùng khoá. Tổng số luôn khớp 720.

**Cấp bậc: đã kiểm định mù, 86,2% đúng bậc** (hai LLM độc lập chỉ đọc tiêu đề + JD, không thấy nhãn của
mình; 96,9% lệch không quá 1 bậc).

**Nghề: chưa có nhãn người để đối chiếu.** Đây là giới hạn lớn nhất. 59% nhãn do quy tắc đọc tiêu đề, 41%
do LLM. Nên **đừng xếp hạng** bốn nghề đứng đầu — chúng nằm trong sai số của nhau.

---

## 3. Ba câu KHÔNG được viết

**❌ "Business Analyst là nghề Data lớn nhất Việt Nam."**
BA có 146 tin, nhưng **31 tin (21%)** trong đó không có một dấu hiệu công việc dữ liệu nào — chỉ có việc
viết tài liệu yêu cầu cho đội phần mềm (BRD/SRS/user story/UAT/ERP/CRM/presales). Các nghề Analytics khác
sạch hoàn toàn: Data Analyst 0%, BI 0%, Risk/Fraud 0%.
✅ **Viết thế này:** *"Analytics lõi (Data Analyst 105 + BI 43 + Risk/Fraud 38 = 186 tin) là nhóm lớn nhất.
Business Analyst có 146 tin nhưng khoảng 1/5 trong đó là BA phần mềm, nên không gộp thẳng vào nghề data."*

**❌ "Thị trường Data Việt Nam có 46,9% là Analytics."**
Con số đó là của **720 tin đã thu thập**, không phải của Việt Nam. Tỉ lệ Analytics khác nhau rất xa theo
từng job board: VietnamWorks 60,4% nhưng ITviec 28,9%, Glints 25,5%. Vì VietnamWorks đóng góp 255/720 tin,
con số 46,9% chủ yếu phản ánh VietnamWorks.
✅ **Viết thế này:** *"Trong 720 tin thu thập được, Analytics chiếm 46,9%. Tỉ lệ này phụ thuộc mạnh vào
thành phần job board (25,5%–60,4% tuỳ nguồn), nên không suy rộng ra toàn thị trường."*

**❌ "Nhu cầu kỹ năng X đang tăng."**
Chỉ có **một** lát cắt ngày 16/06/2026. Không có gì để so sánh. Mọi câu tăng/giảm/đang hot đều không có
cơ sở. Tương tự: dữ liệu **không có trường lương**, nên không viết gì về thu nhập.

---

## 4. Ba điều nên đưa vào báo cáo (điểm cộng)

1. **Cấp bậc: cùng một dữ liệu, bốn cách đo cho bốn kết quả khác nhau.** Tỉ lệ Junior+Intern đã đi
   5,6% → 11,7% → 21,9% → **20,0%** qua bốn lần sửa *cách đo*, dữ liệu không đổi một dòng. Bài học: con số
   "cửa vào nghề rất hẹp" ở bản đầu phần lớn là **hiện vật của phép đo**. Chi tiết ở
   `docs/INSIGHTS_BRAINSTORM.md` mục A3b.
2. **Kỹ năng không tạo thành cụm nghề tự nhiên.** Silhouette chỉ quanh 0,13–0,19 — theo quy ước là *không
   có cấu trúc cụm đáng kể*. Việc dám báo cáo "phân cụm không tìm ra cụm" là một kết quả thật, không phải
   thất bại.
3. **Nhãn do LLM sinh ra thì phụ thuộc vào LLM nào.** Cùng 293 tin, cùng câu lệnh: tỉ lệ một model gọi
   "không phải nghề data" là 75,4% / 70,0% / 60,1% tuỳ model. Đây là lý do báo cáo không xếp hạng cấp nghề.

**Kết luận bền nhất trong cả bộ dữ liệu** (không đổi qua mọi lần sửa cách đo): **Data Engineering là nhánh
khó vào nhất** (Junior+Intern 14,5%), **AI/ML dễ vào nhất** (26,3%) — gần gấp đôi. Dùng cái này làm luận
điểm chính thì an toàn.

---

## 5. Hai file cần điền tay (mỗi người một file, làm song song được)

### 5.1. `data/labeling/spot_check.csv` — 30 dòng, việc quan trọng nhất

**Điền cái này thì báo cáo có thêm một con số mà hiện tại KHÔNG có: độ chính xác của nhãn nghề.**

Chỉ điền **2 cột cuối**, 8 cột đầu là dữ liệu sẵn:

| Cột | Điền gì |
|---|---|
| `human_family` | Nghề bạn tự cho là đúng, viết bằng **mã in hoa** (xem danh sách dưới) |
| `verdict` | `agree` nếu trùng `job_family` · `disagree` nếu khác · `unclear` nếu tin quá mơ hồ |

**Quy tắc quan trọng nhất — làm đúng thứ tự này, nếu không con số sẽ vô giá trị:**

1. **Che 2 cột `job_family` và `reasoning` lại trước khi đọc.** Trong Excel: chọn cột C và D → chuột phải
   → Hide. Nếu bạn nhìn đáp án của máy trước rồi mới quyết, bạn sẽ bị nó dẫn dắt, và kết quả không còn là
   kiểm định độc lập nữa — nó chỉ là "tôi thấy máy nói cũng hợp lý".
2. Đọc `title`, và tra `job_id` trong DB để xem mô tả công việc đầy đủ:
   ```sql
   SELECT title_raw, description_raw FROM jobs
   WHERE source || ':' || source_job_id = 'careerviet:35C72622';
   ```
3. Tự quyết `human_family` → ghi vào.
4. **Chỉ khi đã điền xong cả 30 dòng** mới bỏ ẩn cột `job_family` và điền `verdict`.

**20 mã nghề hợp lệ** (`job_family_engine/taxonomy/taxonomy_v1.yml`):

| Nhánh | Mã |
|---|---|
| Analytics | `DATA_ANALYST` · `BI` · `BUSINESS_ANALYST` · `PRODUCT_ANALYST` · `RISK_FRAUD_ANALYST` |
| Data Engineering | `DATA_ENGINEER` · `ANALYTICS_ENGINEER` · `BIG_DATA_ENGINEER` · `DATAOPS` · `DBA_DATABASE` |
| AI / Machine Learning | `DATA_SCIENTIST` · `RESEARCH_SCIENTIST` · `ML_ENGINEER` · `MLOPS` · `AI_ENGINEER` · `GENAI_LLM` · `CV_NLP` |
| Governance & Architecture | `DATA_ARCHITECT` · `DATA_GOVERNANCE` |
| Data Leadership | `DATA_LEADERSHIP` |
| Không phải nghề data | `OTHER` |

⚠️ **Ranh giới hay gây phân vân nhất — quyết theo *sản phẩm chính* của công việc:**
* `DATA_ANALYST` vs `BUSINESS_ANALYST`: **ai đọc kết quả?** DA giao **con số/dashboard** cho người ra
  quyết định. BA giao **tài liệu yêu cầu** (BRD/SRS/user story) cho đội lập trình. JD chỉ nói
  "biết SQL là một lợi thế" → vẫn là BA.
* `BUSINESS_ANALYST` vs `OTHER`: nếu JD toàn ERP/CRM/UAT/backlog/presales mà **không có việc dữ liệu nào**
  → `OTHER`. Đây đúng là chỗ máy đang sai nhiều nhất (21% tin BA), nên đừng ngại chọn `OTHER`.
* `AI_ENGINEER` vs `ML_ENGINEER` vs `DATA_SCIENTIST`: **ứng dụng model có sẵn** (LLM/API/GenAI) →
  `AI_ENGINEER`. **Đưa model lên production, MLOps** → `ML_ENGINEER`. **Tự xây model, thống kê, thí
  nghiệm** → `DATA_SCIENTIST`.
* `DATA_ENGINEER` vs `DBA_DATABASE`: xây **pipeline/ETL/warehouse** → DE. Vận hành/tối ưu **một hệ CSDL**
  (Oracle/SQL Server) → DBA.

**Sau khi điền xong**, đếm: `agree / 30` = độ chính xác ước lượng. Ghi thẳng con số đó vào báo cáo kèm câu
"mẫu 30 tin, phân tầng theo `stratum`, người gán nhãn không nhìn đáp án của engine".

### 5.2. `data/labeling/company_industry_todo.csv` — 98 công ty

Chỉ điền **1 cột `industry`**. Đây là 98 nhà tuyển dụng mà 2 LLM **không đồng thuận** được ngành, nên bị
để `unknown`. Chúng chiếm **104/720 tin (14,4%)**.

**16 giá trị hợp lệ — chỉ dùng đúng các chuỗi này, viết thường, có gạch dưới:**

| Giá trị | Nghĩa | Đang có (base 720) |
|---|---|--:|
| `bank_finance` | Ngân hàng, chứng khoán, bảo hiểm, fintech | 199 |
| `tech_software` | Công ty công nghệ, phần mềm, outsourcing IT | 176 |
| `manufacturing` | Sản xuất, nhà máy, điện tử, dệt may | 58 |
| `retail_consumer` | Bán lẻ, hàng tiêu dùng, F&B | 29 |
| `logistics` | Vận tải, kho vận, giao nhận, bưu chính | 26 |
| `recruitment_agency` | Công ty tuyển dụng, headhunt | 21 |
| `real_estate_construction` | Bất động sản, xây dựng | 19 |
| `consulting_audit` | Tư vấn, kiểm toán | 18 |
| `education` | Giáo dục, đào tạo, edtech | 17 |
| `telecom` | Viễn thông | 14 |
| `ecommerce` | Thương mại điện tử, sàn TMĐT | 14 |
| `media_gaming` | Truyền thông, quảng cáo, game | 10 |
| `energy_agri` | Năng lượng, nông nghiệp | 9 |
| `healthcare_pharma` | Y tế, dược, bệnh viện | 5 |
| `public_sector` | Nhà nước, cơ quan công | 1 |
| `unknown` | **Thật sự không tra được** — để nguyên | 104 |

**Cách làm nhanh:** file đã sắp theo `n_postings` giảm dần. **Chỉ cần điền 30 dòng đầu là phủ ~35% phần
còn thiếu** — hiệu quả nhất trên mỗi phút bỏ ra. Tra tên công ty ở cột `company` bằng Google; nếu 30 giây
không ra thì để `unknown`, đừng đoán.

⚠️ Phân loại theo **ngành của công ty**, KHÔNG theo nội dung tin tuyển dụng. Một công ty dệt may đăng tin
"phân tích tài chính" vẫn là `manufacturing`. Đây đúng là lỗi bản đầu mắc phải.

**Áp vào dữ liệu sau khi điền:**
```bash
python -m pipeline apply-manual
python -m pipeline integrate
python -m pipeline gold
```

### 5.3. `data/quality/unmapped_skills.csv` — KHÔNG phải file để điền

File này là **báo cáo tự sinh**, mỗi lần chạy `silver` nó ghi đè. Nội dung: những chuỗi kỹ năng xuất hiện
trong tin tuyển dụng mà `ref/skills_dictionary.yml` **chưa biết**, nên **không được đếm ở bất kỳ bảng nào**.

Công dụng: nó cho biết **bảng kỹ năng đang thiếu gì**. Ngày 28/07 đọc file này đã phát hiện 7 kỹ năng bị bỏ
sót hoàn toàn (Business Analysis, Database, Cloud, API, ERP, Data Management, Data Science) — thêm vào từ
điển xong thì `Database` 28,1% và `Data Management` 27,9% lọt thẳng vào top 8.

Muốn thêm kỹ năng: sửa `ref/skills_dictionary.yml` (không sửa file CSV), rồi chạy lại chuỗi ở §6.

⚠️ **Không phải token nào cũng nên thêm.** 2.825 token còn lại phần lớn là:
* **tên chức danh** lọt vào ô kỹ năng — `Data Engineer` (54), `Consultant` (33), `Data Analyst` (22);
* **ngành nghề khác** — `Sales` (37), `Customer Service` (29), `Market Research` (24);
* **kỹ năng mềm** — `Communication` (39+37), `Leadership` (30), `Project Management` (49). Nhóm này đã
  được **cân nhắc và cố ý loại**: từ điển quét trên **toàn văn JD**, nên `Communication` sẽ phủ 37,4% chỉ
  vì câu sáo rỗng "good communication skills", rồi ghép cặp vô nghĩa với mọi kỹ năng khác trong phân tích
  lộ trình học. Lý do đã ghi ngay trong `ref/skills_dictionary.yml`.

---

## 6. Một điều duy nhất cần nhớ khi chạy lệnh

Thứ tự đúng, và **đừng chạy `silver` một mình** — nó xoá nhãn nghề:

```
silver → integrate → enrich-llm → integrate → gold
```

Từ 28/07 đã có chốt an toàn: chạy `python -m pipeline silver` sẽ **bị từ chối** kèm hướng dẫn, thay vì âm
thầm xoá nhãn. Muốn xây lại thật thì thêm `--force` rồi chạy hết chuỗi trên.

Muốn kiểm nhanh mọi thứ còn khớp:

```bash
python analysis/validate_gold.py
```

Phải in `analysis_base 720` và `gold_market_total_n 720`. Nếu hai số này khác nhau là có gì đó sai.
