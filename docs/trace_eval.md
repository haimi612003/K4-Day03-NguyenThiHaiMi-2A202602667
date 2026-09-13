# 📊 BÁO CÁO THU HOẠCH NGHIỆM THU BÀI LAB 3 (BƯỚC 3 — SUBMISSION ARTIFACT)

> **Họ và Tên Học viên:** Nguyễn Thị Hải Mi  
> **Mã Sinh Viên / Mã Học viên:** 2A202602667  
> **Chủ đề Lựa chọn:** *Trợ lý Quản lý Thư viện & Tài liệu:* Tra cứu vị trí sách, tình trạng mượn/trả và gia hạn tài liệu.

---

## 1. BẢNG CHẤM ĐIỂM AGENTIC FIT SCORING MATRIX (ĐÁNH GIÁ CHỦ ĐỀ)

| Tiêu chí Đánh giá | Mức độ (1 - 5) | Giải trình chi tiết lý do chọn điểm |
| :--- | :---: | :--- |
| **1. Multi-step Reasoning** | 4 / 5 | Gia hạn tài liệu đòi hỏi chuỗi bước nối tiếp: tra hồ sơ mượn → kiểm tra 3 điều kiện cho từng cuốn (có người đặt giữ không / user có đang quá hạn cuốn khác không / đã hết lượt gia hạn chưa) → thực hiện gia hạn → báo hạn trả mới. Với yêu cầu "gia hạn tất cả", chuỗi này lặp lại cho từng cuốn. Chấm 4 (không phải 5) vì mỗi luồng chỉ khoảng 2–4 bước và theo quy trình tương đối cố định. |
| **2. Tool Interaction** | 5 / 5 | Toàn bộ thông tin cần thiết (catalog, số bản còn rảnh, vị trí khu/tầng/kệ, hồ sơ mượn/trả, phạt) chỉ nằm trong hệ thống dữ liệu của thư viện, LLM không thể tự biết. Ngoài việc đọc dữ liệu, Agent còn phải thực hiện hành động làm thay đổi dữ liệu thật (gia hạn, đặt giữ). Không có Tool thì Agent không giải quyết được bất kỳ hành vi nào trong ba hành vi. |
| **3. Dynamic Decision** | 5 / 5 | Rẽ nhánh theo kết quả quan sát là cốt lõi của bài toán. Tra cứu sách: còn bản rảnh → báo vị trí kệ; hết bản → đề xuất đặt giữ; không có trong thư viện → báo không có và gợi ý sách tương đương. Gia hạn: đủ điều kiện → thực hiện; vướng điều kiện → từ chối kèm lý do và hướng xử lý cụ thể. Hai cuốn trong cùng một yêu cầu có thể cho hai kết quả khác nhau. |
| **4. Long Horizon Goal** | 3 / 5 | Có các luồng kéo dài qua nhiều lượt hội thoại, Agent phải nhớ user là ai và đang xử lý cuốn nào. Ví dụ: kiểm tra sách đang mượn → được cảnh báo sắp tới hạn → "gia hạn luôn giúp mình"; hoặc tra sách → hết bản → "đặt giữ đi". Tuy nhiên mục tiêu kết thúc trong một phiên hội thoại, không cần theo dõi xuyên nhiều ngày. |
| **TỔNG ĐIỂM AGENTIC FIT** | **17 / 20** | *Nếu tổng điểm > 12/20: Bài toán rất phù hợp triển khai Agentic System.* → **17/20 > 12: bài toán Trợ lý Thư viện rất phù hợp triển khai ReAct Agent.** |

---

## 2. TRÍCH XUẤT KẾT QUẢ WATERFALL TRACE LOG (SAU KHI CHẠY TEST SUITE TRÊN API THẬT)

> ⚠️ **YÊU CẦU NGHIỆM THU:** Mở tệp `.env` điền `GEMINI_API_KEY` (hoặc `OPENAI_API_KEY`) để kết nối LLM thật trước khi thực thi `python src/app.py --all`. Bài nộp chỉ dùng Mock Offline Provider sẽ không đạt điểm nghiệm thực tế.

Dán 1 đoạn trích xuất log tiêu biểu từ file `docs/trace_waterfall.json` sinh ra từ phản hồi LLM API thật:

> **LLM thật:** Google Gemini (`gemini-3.6-flash`) · chạy bằng `python src/app.py --all`.  
> **Đoạn trích:** TC04 (`multi_step_reasoning`) — độc giả 21010245 (đã đăng nhập) yêu cầu gia hạn tất cả sách đang mượn. Agent suy luận đa bước: tra hồ sơ (`get_borrow_record`) → gia hạn từng cuốn (`renew_book` × 2) → tổng hợp câu trả lời: 1 cuốn gia hạn thành công, 1 cuốn bị từ chối vì có độc giả khác đặt giữ.

```json
[
  {
    "step": 1,
    "query": "Mình là 21010245, gia hạn giúp mình tất cả sách đang mượn nhé.",
    "action_type": "TOOL_EXECUTION",
    "thought": "Gemini quyết định gọi công cụ: get_borrow_record({\"student_id\": \"21010245\"})",
    "tool_name": "get_borrow_record",
    "arguments": {
      "student_id": "21010245"
    },
    "observation": {
      "status": "SUCCESS",
      "today": "15/09/2026",
      "student_id": "21010245",
      "full_name": "Trần Quốc Bảo",
      "account_locked": false,
      "lock_reason": null,
      "borrowed_count": 2,
      "max_books": 5,
      "loans": [
        {
          "book_id": "B002",
          "title": "Deep Learning cơ bản",
          "borrow_date": "05/09/2026",
          "due_date": "19/09/2026",
          "days_left": 4,
          "status": "ON_TIME",
          "overdue_days": 0,
          "fine_estimate": 0,
          "renewals_used": 0,
          "max_renewals": 2,
          "can_renew": false,
          "renew_block_reasons": [
            {
              "code": "RESERVED_BY_OTHERS",
              "message": "Cuốn sách này đang có độc giả khác đặt giữ.",
              "suggestion": "Vui lòng trả sách đúng hạn (19/09/2026) để nhường lượt cho người đặt giữ."
            }
          ]
        },
        {
          "book_id": "B004",
          "title": "Kinh tế vi mô",
          "borrow_date": "01/09/2026",
          "due_date": "22/09/2026",
          "days_left": 7,
          "status": "ON_TIME",
          "overdue_days": 0,
          "fine_estimate": 0,
          "renewals_used": 1,
          "max_renewals": 2,
          "can_renew": true,
          "renew_block_reasons": []
        }
      ],
      "total_fine": 0,
      "reservations": [],
      "warnings": []
    },
    "latency_ms": 3650.74,
    "tool_latency_ms": 0.22
  },
  {
    "step": 2,
    "query": "Mình là 21010245, gia hạn giúp mình tất cả sách đang mượn nhé.",
    "action_type": "TOOL_EXECUTION",
    "thought": "Gemini quyết định gọi công cụ: renew_book({\"book_id\": \"B004\", \"student_id\": \"21010245\"})",
    "tool_name": "renew_book",
    "arguments": {
      "book_id": "B004",
      "student_id": "21010245"
    },
    "observation": {
      "status": "SUCCESS",
      "book_id": "B004",
      "title": "Kinh tế vi mô",
      "old_due_date": "22/09/2026",
      "new_due_date": "29/09/2026",
      "renewals_used": 2,
      "renewals_left": 0,
      "message": "Gia hạn thành công 'Kinh tế vi mô'. Hạn trả mới: 29/09/2026."
    },
    "latency_ms": 3562.43,
    "tool_latency_ms": 0.17
  },
  {
    "step": 3,
    "query": "Mình là 21010245, gia hạn giúp mình tất cả sách đang mượn nhé.",
    "action_type": "TOOL_EXECUTION",
    "thought": "Gemini quyết định gọi công cụ: renew_book({\"book_id\": \"B002\", \"student_id\": \"21010245\"})",
    "tool_name": "renew_book",
    "arguments": {
      "book_id": "B002",
      "student_id": "21010245"
    },
    "observation": {
      "status": "REJECTED",
      "book_id": "B002",
      "title": "Deep Learning cơ bản",
      "due_date": "19/09/2026",
      "reasons": [
        {
          "code": "RESERVED_BY_OTHERS",
          "message": "Cuốn sách này đang có độc giả khác đặt giữ.",
          "suggestion": "Vui lòng trả sách đúng hạn (19/09/2026) để nhường lượt cho người đặt giữ."
        }
      ]
    },
    "latency_ms": 2475.71,
    "tool_latency_ms": 0.14
  },
  {
    "step": 4,
    "query": "Mình là 21010245, gia hạn giúp mình tất cả sách đang mượn nhé.",
    "action_type": "FINAL_ANSWER",
    "thought": "Gemini tổng hợp câu trả lời bằng văn bản (không cần gọi thêm công cụ).",
    "output": "Chào bạn **Trần Quốc Bảo** (MSSV: 21010245),\n\nDưới đây là kết quả xử lý gia hạn cho **tất cả 02 cuốn sách** bạn đang mượn:\n\n---\n\n### 1. Gia hạn THÀNH CÔNG (01 cuốn)\n* **Tên sách:** *Kinh tế vi mô* (Mã sách: `B004`)\n* **Hạn trả cũ:** 22/09/2026\n* **Hạn trả mới:** **29/09/2026** *(thêm 7 ngày)*\n* **Số lần gia hạn còn lại:** 0/2 lần.\n\n---\n\n### 2. Gia hạn KHÔNG THÀNH CÔNG (01 cuốn)\n* **Tên sách:** *Deep Learning cơ bản* (Mã sách: `B002`)\n* **Lý do từ chối:** Cuốn sách này đang có độc giả khác đặt giữ.\n* **Hướng xử lý:** Vui lòng mang sách đến trả đúng hạn hiện tại là **19/09/2026** để nhường lượt cho người đặt giữ.\n\n---\nNếu cần hỗ trợ thêm thông tin gì khác, bạn cứ báo cho mình nhé!",
    "latency_ms": 4915.6
  }
]
```

---

## 3. TỔNG KẾT KẾT QUẢ NGHIỆM THU & NỘP BÀI

- [x] Đã điền API Key thật trong `.env` và xác nhận Agent chạy mượt mà trên LLM API thật (Gemini/OpenAI). *(Google Gemini — `gemini-3.6-flash`)*
- **Tổng số Test Cases đã chạy thành công:** 5 / 5 test cases.
- **Số lượt gọi Tool qua MCP Server chính xác:** 7 lượt *(TC02: `search_book` ×1 · TC03: `get_borrow_record` ×1 · TC04: `get_borrow_record` ×1 + `renew_book` ×2 · TC05: `get_borrow_record` ×1 + `renew_book` ×1; TC01 trả lời trực tiếp, không gọi Tool)*.
- **Kết quả đẩy Repo nộp bài:** [x] Đã Commit và Push mã nguồn thành công lên GitHub cá nhân.

---

> ✅ **HOÀN TẤT NỘP BÀI:** Sao chép đường link GitHub Repository cá nhân của bạn và dán vào ô nộp bài trên hệ thống LMS VLearn để hoàn tất Bài Lab 3!
