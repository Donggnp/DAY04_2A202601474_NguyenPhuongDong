# Day 04 Lab v2 Report — Research Agent

> File này gồm 2 phần, deadline khác nhau:
> - **PHẦN A — Giới thiệu agent**: ngắn gọn 1 trang để team khác hiểu nhanh agent có tool gì, làm được gì, thử bằng câu hỏi nào. Xong trước 16:30 để làm tài liệu phụ trợ khi demo.
> - **PHẦN B — Chi tiết / Bằng chứng**: bảng đầy đủ (v0–v3, failure, eval, chat) dựa trên log thật. Có thể hoàn thiện sau buổi debate để nộp bài.

## Team

- Team: DAY04_2A202601474_NguyenPhuongDong
- Members: Nguyễn Phương Đông
- Provider/model: openai / gpt-5.4-mini (local proxy)

---

# PHẦN A — Giới thiệu agent

## A1. Agent này làm được gì

Research Paper Agent: tìm kiếm bài báo arXiv theo chủ đề, đọc nội dung PDF paper theo arXiv ID, tìm tin tức web, đọc URL bất kỳ, trích xuất hình ảnh/biểu đồ từ paper arXiv, và trình bày kết quả thành digest markdown. Agent hỏi lại khi thiếu thông tin và từ chối các yêu cầu ngoài phạm vi research.

**Link dùng thử (truy cập được trong showdown):**

> URL: http://localhost:8501 (Streamlit, chạy `streamlit run app.py` trên máy demo)

## A2. Tool agent có

| Tên tool | Làm được gì | Tool mới nhóm thêm? |
|---|---|---|
| clarify | Hỏi lại người dùng khi thiếu arXiv ID, URL hoặc topic; xác nhận trước hành động nhạy cảm | không |
| papers | Tìm kiếm bài báo trên arXiv theo từ khóa, sắp xếp theo relevance hoặc ngày đăng | không |
| paper_text | Tải PDF arXiv và trích text theo số trang hoặc số ký tự | không |
| lookup | Tìm kiếm tin tức / thông tin chung trên web với bộ lọc topic và timeframe | không |
| fetch | Đọc và tóm tắt nội dung một URL cụ thể (không phải arXiv) | không |
| format | Trình bày danh sách kết quả thành digest markdown theo template (brief/sections/bullets/thread/daily_ai_vn) | không |
| download_figure | Trích xuất hình ảnh, biểu đồ, bảng kết quả từ PDF bài báo arXiv thành file PNG | **CÓ — tool mới của nhóm** |

## A3. Câu hỏi mẫu để thử

1. `Tìm giúp mình 5 bài báo arXiv mới nhất về Retrieval Augmented Generation.`
2. `Đọc nội dung bài báo arXiv 1706.03762, lấy 3 trang đầu.`
3. `Tìm tin tức web hôm nay về model Gemini 2.0 và tóm tắt link này: https://deepmind.google/technologies/gemini/`
4. `Tổng hợp các bài báo vừa tìm thành digest, dùng template brief.`
5. `Trích xuất hình ảnh kết quả từ paper arXiv 2303.08774.`

## A4. Kịch bản demo đã rehearse

| Scenario | Tool trace cần thấy | Câu chuyện cải thiện version | Fallback run/transcript |
|---|---|---|---|
| Tìm paper RAG + đọc paper cụ thể | `papers(query="RAG", max_results=3)` → `paper_text(arxiv_url="...", max_pages=2)` | v0 thiếu routing table → v1 thêm decision table → v3 pass 100% | v3_B_group_openai_20260729T162628181403.json |
| Compound request: web + URL | `lookup(query="Claude 3.5", topic="news")` + `fetch(url="...")` song song | v1 chỉ gọi fetch bỏ lookup → v2 thêm Hard URL rule → v3 pass G03 | v3_B_group_openai_20260729T162628181403.json |
| Format digest sau khi tìm paper | `format(template="brief")` từ prior results | v1 gọi `clarify` thay vì `format` → v2 thêm rule format → v3 pass G09 | v3_B_group_openai_20260729T162628181403.json |
| Trích hình ảnh từ paper arXiv | `download_figure(arxiv_url="2303.08774", max_images=4)` | Tool mới của nhóm; demo live extraction từ PDF | runs/v3_B_group_openai_20260729T162628181403.json |

---

# PHẦN B — Chi tiết / Bằng chứng

> Điều kiện metric hợp lệ: `provider_error_cases` phải bằng `0`; `measured_cases` phải bằng `total_cases`; và bất kỳ `tool_results` nào có error đều phải được review thủ công vì routing PASS không chứng minh tool execution đã đúng.

## B1. Version evidence

Fill from `artifacts/version_log.csv` and `runs/*.json`.

| Version | Prompt/tool change | Hypothesis | Metric name | Before | After | Run File |
|---|---|---|---|---:|---:|---|
| v0 | baseline |  |  |  |  |  |
| v1 |  |  |  |  |  |  |
| v2 |  |  |  |  |  |  |
| v3 |  |  |  |  |  |  |

## B2. Failure analysis

Use actual failures from `results[*].result.failures`.

| Case ID | Failure Type | Actual Tool Calls | What Failed | Fix |
|---|---|---|---|---|
|  |  |  |  |  |

## B3. Team eval cases

List the 10 cases added to `data/eval_group.json`:

- 5 single-turn
- 5 multi-turn

This section is for the mandatory team-authored eval set. Optional built-ins do
not belong here.

File template để trống có chủ đích; nhóm phải tự thiết kế đủ 10 case.

| Case ID | What It Tests | Expected Tool/Behavior | Result |
|---|---|---|---|
|  |  |  |  |

## B4. Live chat evidence

Use `transcripts/*.transcript.json`.

| Scenario/Turn | Version | Tool Calls + Args | Transcript/Run | Outcome |
|---|---|---|---|---|
|  |  |  |  |  |

## B5. Tool capability evidence

Phân loại rõ tool mới bắt buộc, optional built-in và tool đủ điều kiện bonus. Chỉ ghi Telegram/PDF nếu nhóm thực sự dùng; base report không cần chúng.

UI is core deliverable, not bonus. Do not list it here.

| Category | Evidence File | What Worked | Risk / Guardrail |
|---|---|---|---|
| Must-have: tool mới đầu tiên |  |  |  |
| Optional built-in |  |  |  |
| Bonus: tool mới thứ 4 trở đi |  |  |  |

## B6. Reflection

- Which fixes belonged in `system_prompt.md`?
- Which fixes belonged in `tools.yaml`?
- Which failure needed manual review instead of automatic grading?
- What would you improve next?
