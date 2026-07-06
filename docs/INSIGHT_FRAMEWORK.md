# Khung Viết Insight

Deliverable của Milestone 8: chuyển kết quả EDA đã được validate thành insight có ý nghĩa kinh doanh cho
người học/người tìm việc và nhà tuyển dụng.

## Nguyên Tắc

Mỗi insight phải đi đủ chuỗi:

```text
Quan sát -> Bằng chứng -> Diễn giải -> Ý nghĩa kinh doanh -> Khuyến nghị -> Hạn chế
```

Không dừng ở mức "biểu đồ cho thấy X". Một insight tốt phải trả lời thêm: vì sao X quan trọng,
ai cần quan tâm, và nên hành động gì tiếp theo.

## Bảng Nguồn Chính

Phân tích chính dùng lớp Family Gold:

| Nhóm câu hỏi | Bảng chính |
|---|---|
| Thị phần tuyển dụng | `gold_market_share` |
| Nhu cầu skill theo family | `gold_family_skill` |
| Loại công ty | `gold_company` |
| Khu vực / thành phố | `gold_location` |
| Cấp bậc tuyển dụng | `gold_seniority` |
| Learning path / skill bundle | `gold_skill_cooccurrence` |
| Drill-down từng job | `gold_jobs`, `jobs_silver` |

Legacy Gold chỉ dùng làm baseline hoặc tham chiếu, không phải nguồn phân tích chính.

## Insight 1: Cấu Trúc Thị Trường

**Quan sát**  
Nhu cầu tuyển dụng tập trung vào một vài job family lớn.

**Bằng chứng**  
Top 5 family từ `gold_market_share`:

| Job family | n | pct |
|---|---:|---:|
| `BUSINESS_ANALYST` | 181 | 21.2 |
| `DATA_ENGINEER` | 149 | 17.5 |
| `DATA_ANALYST` | 125 | 14.7 |
| `AI_ENGINEER` | 118 | 13.8 |
| `RISK_FRAUD_ANALYST` | 52 | 6.1 |

**Diễn giải**  
Thị trường Data/AI Việt Nam không bị chi phối bởi các vai trò thuần mô hình hóa. Family lớn nhất là
nhóm analytics gắn với nghiệp vụ, sau đó mới đến data engineering, data analysis và applied AI engineering.

**Ý nghĩa kinh doanh**  
Với người học/người tìm việc, cửa vào ngành Data không chỉ là Data Scientist hay Machine Learning.
Các hướng Business Analyst, Data Analyst, BI, Risk/Fraud Analyst cũng là những hướng có nhu cầu rõ ràng.
Với nhà tuyển dụng, cạnh tranh nhân sự có khả năng cao nhất ở các family lớn như BA/DA/DE/AIE.

**Khuyến nghị**  
Ưu tiên xây lộ trình học và chiến lược tuyển dụng quanh các family lớn trước:
Business Analyst, Data Engineer, Data Analyst và AI Engineer.

**Hạn chế**  
Dữ liệu hiện là một snapshot, nên chỉ phản ánh cấu trúc thị trường tại thời điểm quan sát. Không được
diễn giải thành xu hướng tăng trưởng.

## Insight 2: Skill DNA Của Data Analyst

**Quan sát**  
`DATA_ANALYST` có hồ sơ kỹ năng khá rõ, xoay quanh phân tích dữ liệu và báo cáo.

**Bằng chứng**  
Report EDA hiện có ghi nhận các skill nổi bật của `DATA_ANALYST`:

| Skill | Tỷ lệ trong family |
|---|---:|
| Data Analysis | 82% |
| Reporting | 68% |
| SQL | 66% |
| Power BI | 58% |

Nguồn: `analysis/market_insights_report.md`, được tạo từ `gold_family_skill`.

**Diễn giải**  
Vai trò Data Analyst trong dataset này thiên về phân tích nghiệp vụ, báo cáo và hỗ trợ ra quyết định,
không phải vai trò machine learning tổng quát.

**Ý nghĩa kinh doanh**  
Với người học muốn nhắm tới Data Analyst, vấn đề không phải là học thật nhiều công cụ rời rạc.
Điểm quan trọng là học đúng cụm kỹ năng xuất hiện lặp lại trong JD: phân tích, SQL, reporting và BI tool.

**Khuyến nghị**  
Ưu tiên học SQL, Data Analysis, Reporting và Power BI trước khi đi sâu vào các chủ đề ML nâng cao.

**Hạn chế**  
Skill extraction chỉ cho biết skill có xuất hiện trong JD hay không. Nó không đo được mức độ thành thạo
mà nhà tuyển dụng yêu cầu.

## Insight 3: Rào Cản Seniority

**Quan sát**  
Thị trường tuyển dụng lệch mạnh về Mid-level.

**Bằng chứng**  
Report EDA ghi nhận:

| Seniority | Bằng chứng |
|---|---:|
| Mid | 459 job, khoảng 54% |
| Senior | 194 job, khoảng 23% |
| Manager | 106 job, khoảng 12% |
| Junior + Intern | khoảng 46 job, khoảng 5% |

Nguồn: `gold_seniority`, được tổng hợp trong `analysis/market_insights_report.md`.

**Diễn giải**  
Doanh nghiệp có xu hướng tìm ứng viên có thể đóng góp ngay. Các vị trí entry-level như Junior/Intern
tương đối ít.

**Ý nghĩa kinh doanh**  
Với người mới, rào cản không chỉ là thiếu skill. Rào cản lớn hơn là làm sao chứng minh năng lực khi
thị trường không có nhiều vị trí Junior/Intern.

**Khuyến nghị**  
Người học nên xây portfolio/project thể hiện năng lực gần mức Mid-level: SQL analysis, dashboard/reporting,
data pipeline hoặc applied AI tùy family mục tiêu.

**Hạn chế**  
Seniority là trường được suy luận từ title/source labels nên không hoàn hảo. Một số job không ghi rõ level
có thể bị gom vào Mid theo rule của pipeline.

## Insight 4: Skill Bundle / Learning Path

**Quan sát**  
Một số skill thường xuất hiện cùng nhau, gợi ý các cụm kỹ năng nên học theo bundle.

**Bằng chứng**  
Các cặp skill co-occurrence nổi bật từ report EDA:

| Cặp skill | n |
|---|---:|
| Python + SQL | 220 |
| Reporting + SQL | 188 |
| Data Analysis + SQL | 185 |
| Machine Learning + Python | 168 |
| Power BI + SQL | 156 |
| English + Python | 142 |

Nguồn: `gold_skill_cooccurrence`.

**Diễn giải**  
SQL là skill trung tâm. Nó đi cùng Reporting/Power BI trong nhóm analytics, và đi cùng Python/ML trong
nhóm kỹ thuật hoặc AI.

**Ý nghĩa kinh doanh**  
Lộ trình học nên được thiết kế theo cụm kỹ năng, không học từng skill tách rời. SQL có giá trị cao hơn
khi đi kèm một nhánh ứng dụng cụ thể.

**Khuyến nghị**  
Dùng lộ trình hai tầng:

1. Nền tảng: SQL + Python.
2. Rẽ nhánh: Power BI + Reporting cho DA/BI, hoặc Machine Learning + LLM cho AI.

**Hạn chế**  
Co-occurrence không phải quan hệ nhân quả. Nó chỉ cho thấy các skill thường được liệt kê cùng nhau,
không chứng minh skill nào phải học trước hoặc skill nào trực tiếp quyết định tuyển dụng.

## Definition Of Done

Milestone 8 hoàn thành khi:

| Yêu cầu | Đạt khi |
|---|---|
| Insight có bằng chứng | Mỗi claim có nguồn từ bảng/report/code trong repo |
| Insight có ý nghĩa kinh doanh | Người đọc hiểu vì sao kết quả đó quan trọng |
| Insight có khuyến nghị | Người đọc biết nên làm gì tiếp theo |
| Insight có hạn chế | Không diễn giải quá mức dữ liệu |
| Không vi phạm scope | Không salary, không forecasting, không supervised classifier |

