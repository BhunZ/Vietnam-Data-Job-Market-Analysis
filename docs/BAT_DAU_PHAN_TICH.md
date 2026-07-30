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

## 5. Một điều duy nhất cần nhớ khi chạy lệnh

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
