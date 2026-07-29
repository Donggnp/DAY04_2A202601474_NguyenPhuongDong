# Day 04 Lab v2 Report — Research Agent

> File này gồm 2 phần, deadline khác nhau:
> - **PHẦN A — Giới thiệu agent**: ngắn gọn 1 trang để team khác hiểu nhanh agent có tool gì, làm được gì, thử bằng câu hỏi nào. Xong trước 16:30 để làm tài liệu phụ trợ khi demo.
> - **PHẦN B — Chi tiết / Bằng chứng**: bảng đầy đủ (v0–v3, failure, eval, chat) dựa trên log thật. Có thể hoàn thiện sau buổi debate để nộp bài.

## Team

- Team: DAY04_2A202601474_NguyenPhuongDong
- Members: Nguyễn Phương Đông - 2A202601474 - role UI/QA/Deployment
            Trần Thị Kiều Trang - 2A202601498 - role Prompt & Eval Lead
            Nguyễn Quý Dùng - 2A202601200 - role Backend/Agent Engineer
            Nguyễn Nhật Minh - 2A202601950 - role Tool & Data Engineer
            
- Provider/model: openai / gpt-4o-mini (local proxy)

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

> Điều kiện metric hợp lệ: `provider_error_cases` = `0`; `measured_cases` = `total_cases`. Tool_results có ConnectionError hoặc missing API key được review thủ công — routing PASS không chứng minh tool execution đúng.

## B1. Version evidence

| Version | Prompt/tool change | Hypothesis | Metric name | Before | After | Run File |
|---|---|---|---|---:|---:|---|
| v0 | Baseline: prompt chỉ định scope tool, hỏi lại khi thiếu info, không có routing table | Model tự suy ra tool từ mô tả ngắn → bỏ sót compound call (G03) | case_accuracy | — | 0.90 | v0_B_group_openai_20260729T160659089290.json |
| v1 | Thêm Tool-routing decision table (papers/paper_text/lookup/fetch/format/clarify); thêm Compound requests rule | Routing table giúp model emit đủ call song song cho G03; nhưng phát sinh regression G09 (clarify thay format) | case_accuracy | 0.90 | 0.80 | v1_B_group_openai_20260729T161303839760.json |
| v2 | Thêm Hard URL rule (bắt buộc fetch khi có http URL); thêm format rule (gọi format khi prior results tồn tại) | Rule cứng cho URL fix G03 (fetch không bị bỏ sót); format rule fix G09 (không gọi clarify thay format) | case_accuracy | 0.80 | 0.90 | v2_B_group_openai_20260729T161618727045.json |
| v3 | Thêm Multi-turn state rules + Final call audit; download_figure routing rule; làm rõ scope boundary | Internal checklist audit đảm bảo mọi sub-request đều có call; multi-turn carryover rules tránh miss G03 fetch | case_accuracy | 0.90 | 1.00 | v3_B_group_openai_20260729T162628181403.json |

## B2. Failure analysis

| Case ID | Failure Type | Actual Tool Calls (observed) | What Failed | Fix áp dụng |
|---|---|---|---|---|
| G03 (v0) | wrong_tool | `fetch(url=...)` only | Bỏ sót `lookup` — model chọn một tool khi user cung cấp URL, không emit song song | v2: Thêm Hard URL rule: "whenever user includes URL and asks to read, emit fetch AND lookup if also searching" |
| G03 (v1) | wrong_tool | `fetch(url=...)` only | Routing table v1 mô tả fetch nhưng chưa có rule bắt buộc compound | v2: Hard URL rule cứng hóa hành vi |
| G03 (v2) | wrong_tool | `lookup(query=...)` only | Lần này model emit lookup nhưng bỏ fetch — flip lỗi | v3: Final call audit: "before returning, verify every explicit sub-request has a call" |
| G09 (v1) | wrong_arg_value | `clarify(question=..., response_type=text)` | Model hỏi lại user vì "không thấy danh sách bài báo" thay vì gọi format với empty items | v2: format rule: "A reference such as 'các bài vừa tìm' means previous results exist; call format instead of clarify" |

## B3. Team eval cases

| Case ID | Type | What It Tests | Expected Tool | v3 Result |
|---|---|---|---|---|
| G01_arxiv_papers_search | Single-turn | Tìm paper arXiv với max_results=3 | `papers(query="Retrieval Augmented Generation", max_results=3)` | ✅ PASS |
| G02_arxiv_paper_text_read | Single-turn | Đọc paper theo arXiv ID + max_pages=2 | `paper_text(arxiv_url="1706.03762", max_pages=2)` | ✅ PASS |
| G03_parallel_lookup_and_fetch | Single-turn | Compound: tìm web + đọc URL cụ thể song song | `lookup(query="Claude 3.5", topic="news")` + `fetch(url=...)` | ✅ PASS |
| G04_clarify_missing_paper_url | Single-turn | Thiếu URL/ID → clarify hỏi lại | `clarify(response_type="text")` | ✅ PASS |
| G05_out_of_scope_math | Single-turn | Câu hỏi toán ngoài scope → từ chối không gọi tool | `no_tool` + refuse | ✅ PASS |
| G06_multiturn_clarify_then_papers | Multi-turn (3 turns) | Carry topic từ turn 2 + max_results từ turn 3 → papers | `papers(query="Graph Neural Networks", max_results=5)` | ✅ PASS |
| G07_multiturn_clarify_url_then_paper_text | Multi-turn (3 turns) | Carry arXiv ID từ turn 2 + max_pages từ turn 3 → paper_text | `paper_text(arxiv_url="2303.08774", max_pages=3)` | ✅ PASS |
| G08_multiturn_switch_web_to_arxiv | Multi-turn (3 turns) | Đổi tool từ lookup sang papers, giữ nguyên query | `papers(query="AI Agent")` | ✅ PASS |
| G09_multiturn_format_digest | Multi-turn (3 turns) | Format prior results thành digest với template=brief | `format(template="brief")` | ✅ PASS |
| G10_multiturn_no_tool_meta | Multi-turn (3 turns) | Turn cuối hỏi meta → không gọi tool, trả lời trực tiếp | `no_tool` | ✅ PASS |

**Kết quả v3: 10/10 PASS — case_accuracy=1.0, tool_routing_accuracy=1.0, multiturn_accuracy=1.0**

## B4. Live chat evidence

Transcript: `transcripts/v3_openai_20260729T163955122047.transcript.json`

| Turn | Scenario | Tool Calls + Args | Outcome |
|---|---|---|---|
| 1 | Research request: "Tìm 3 paper arXiv về LLM Agents" | `papers(query="LLM Agents", max_results=3, sort_by="relevance")` → 3 paper thật từ arXiv (15565 tổng kết quả) | ✅ Tìm được 3 paper có tiêu đề, tóm tắt, URL đầy đủ |
| 2 | Thiếu thông tin: "Tóm tắt bài báo này giúp mình" (không có URL/ID) | `clarify(question="Bạn muốn mình tóm tắt paper nào trong 3 paper vừa liệt kê? Gửi arXiv link hoặc title nhé.", response_type="text")` | ✅ Hỏi lại đúng, không đoán bừa |
| 3 | Out-of-scope: "Viết giúp mình một bài báo hoàn chỉnh về LLM" | Không gọi tool; agent từ chối và gợi ý hỗ trợ nghiên cứu (tìm paper, dàn ý, related work) | ✅ Từ chối đúng boundary |

## B5. Tool capability evidence

| Category | Evidence File | What Worked | Risk / Guardrail |
|---|---|---|---|
| Must-have: tool mới — `download_figure` | `tools/download_figure/TOOL.md`, `tools/download_figure/tool.py` | Trích hình ảnh/biểu đồ từ PDF arXiv thành PNG; khai báo trong `tools.yaml` + `tools/__init__.py` | Tool routing chỉ khi user cung cấp arXiv ID/URL và yêu cầu hình ảnh; nếu thiếu ID thì gọi `clarify` |
| Optional built-in — `papers` | `runs/v3_B_group_openai_...T162628.json`, transcript turn 1 | Tìm kiếm arXiv thật (15565 kết quả cho "LLM Agents"); trả về arxiv_id, title, summary, PDF URL | ConnectionError khi không có mạng ra ngoài (WinError 10013); routing PASS nhưng tool_results cần review |
| Optional built-in — `paper_text` | `runs/v3_B_group_openai_...T162628.json` | Routing đúng arxiv_url + max_pages từ multi-turn context | ConnectionError khi không kết nối arxiv.org; cần HTTPS outbound |
| Optional built-in — `fetch` | Routing pass v3 G03 | Routing đúng URL; tool execution phụ thuộc FIRECRAWL_API_KEY | Cần set `FIRECRAWL_API_KEY` để execute thật |
| Optional built-in — `lookup` | Routing pass v3 G03 | Routing đúng query + topic="news" | Cần `TAVILY_API_KEY` để execute thật |
| Optional built-in — `format` | Runs v2/v3 G09 PASS | Gọi `format(template="brief")` đúng từ prior results context | Eval context không có items thật → item_count=0 (acceptable) |

## B6. Reflection

**Fixes thuộc về `system_prompt.md`:**
- Routing decision table cho từng tool (khi nào dùng, khi nào không).
- Hard URL rule: "khi user cung cấp URL và muốn đọc, bắt buộc emit fetch".
- Format rule: "prior results reference → gọi format không gọi clarify".
- Multi-turn state rules: carry forward topic/URL/count; chỉ answer latest turn.
- Final call audit: trước khi trả về, verify mọi sub-request có call tương ứng.

**Fixes thuộc về `tools.yaml`:**
- Thêm `download_figure` với declaration rõ ràng (khi nào dùng, cần arxiv_url, optional max_images/dpi).
- Mô tả `papers` bổ sung convention `sort_by` cho "mới nhất".
- Mô tả `format` bổ sung note về empty items khi eval context không có payload.

**Failures cần manual review thay vì chấm tự động:**
- `G03 v0/v1/v2`: routing score là FAIL vì bỏ sót một call, nhưng tool_results đều có error (TAVILY/FIRECRAWL key missing) — cần review xem lỗi từ routing hay từ môi trường.
- `G01/G02 v1/v2`: routing PASS nhưng `tool_results` có ConnectionError (WinError 10013 — blocked outbound HTTPS) — cần manual note là tool execution failed vì network, không phải sai routing.

**Cải thiện tiếp theo:**
- Bổ sung `TAVILY_API_KEY` và `FIRECRAWL_API_KEY` để test tool execution thật cho `lookup` và `fetch`.
- Mở firewall outbound HTTPS để `papers` và `paper_text` kết nối được arxiv.org.
- Viết thêm case eval cho `download_figure` (tool mới của nhóm) để có evidence execution thật.
- Thêm case test negative: user cung cấp URL nhưng yêu cầu chỉ lookup (không fetch) để kiểm tra hard rule không over-trigger.
