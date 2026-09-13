"""
🛠️ TOOL DEFINITIONS & EXECUTION BACKEND — TRỢ LÝ THƯ VIỆN ĐẠI HỌC
Mã nguồn chứa danh sách Tool Schemas (JSON Schema) và Execution Layer phục vụ cho MCP Server.
Quy định nghiệp vụ lấy từ văn bản QĐ-TV-01 (QuyDinh_ThuVien.docx).
"""

import json
import re
import unicodedata
from datetime import date, timedelta
from typing import Dict, Any, List, Optional

# ==============================================================================
# 1. KHAI BÁO TOOL SCHEMAS CHUẨN NATIVE JSON SCHEMA (TASK 1.2)
# ==============================================================================

TOOLS_SCHEMA = [
    # Tool 1: Tra cứu sách (Hành vi 1 — tra cứu vị trí sách)
    {
        "name": "search_book",
        "description": (
            "Tra cứu sách trong catalog thư viện theo mã sách (ví dụ 'B001'), tên sách, tác giả hoặc chủ đề. "
            "Trả về: thư viện có sách không, còn bao nhiêu bản rảnh, vị trí khu/tầng/kệ, "
            "sách có được mượn về không; nếu hết bản thì cho biết ngày dự kiến có bản và số người đang chờ đặt giữ. "
            "Nếu không tìm thấy, trả về danh sách sách tương đương cùng chủ đề (khi có truyền 'topic')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Mã sách, tên sách, tên tác giả hoặc chủ đề cần tìm (ví dụ: 'B001', 'Nhập môn Học máy', 'Tô Hoài')."
                },
                "topic": {
                    "type": "string",
                    "description": (
                        "Chủ đề của cuốn sách người dùng cần (ví dụ: 'Trí tuệ nhân tạo', 'Kinh tế', 'Văn học'), "
                        "dùng để gợi ý sách tương đương khi thư viện không có đúng cuốn đó."
                    )
                }
            },
            "required": ["keyword"]
        }
    },

    # Tool 2: Xem hồ sơ mượn/trả (Hành vi 2 — check tình trạng mượn/trả)
    {
        "name": "get_borrow_record",
        "description": (
            "Tra hồ sơ mượn/trả của một độc giả theo MSSV. Trả về danh sách sách đang mượn kèm hạn trả, "
            "số ngày còn lại, trạng thái (ON_TIME / DUE_SOON / OVERDUE), phí phạt tạm tính, "
            "có gia hạn được không (can_renew) và lý do nếu không; tổng phí phạt, trạng thái khóa tài khoản, "
            "danh sách sách đang đặt giữ và các cảnh báo hạn trả."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "string",
                    "description": "Mã số sinh viên (MSSV) gồm 8 ký tự, đồng thời là mã thẻ thư viện (ví dụ: '21010123')."
                }
            },
            "required": ["student_id"]
        }
    },

    # Tool 3: Gia hạn 1 cuốn sách (Hành vi 3 — gia hạn tài liệu)
    {
        "name": "renew_book",
        "description": (
            "Gia hạn MỘT cuốn sách đang mượn thêm 7 ngày (tính từ hạn trả hiện tại). "
            "Tự động kiểm tra đồng thời 3 điều kiện: không có độc giả khác đặt giữ cuốn này, "
            "độc giả không đang quá hạn bất kỳ cuốn nào, cuốn này chưa gia hạn đủ 2 lần. "
            "Trả về hạn trả mới nếu thành công, hoặc lý do từ chối kèm hướng xử lý. "
            "Muốn gia hạn nhiều cuốn thì gọi tool này lần lượt cho từng cuốn."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "string",
                    "description": "MSSV 8 ký tự của độc giả (ví dụ: '21010123')."
                },
                "book_id": {
                    "type": "string",
                    "description": "Mã sách cần gia hạn (ví dụ: 'B001'), lấy từ kết quả get_borrow_record."
                }
            },
            "required": ["student_id", "book_id"]
        }
    },

    # Tool 4: Đặt giữ sách đã hết bản
    {
        "name": "reserve_book",
        "description": (
            "Đặt giữ (reserve) một đầu sách đã được mượn hết bản để vào hàng chờ. "
            "Khi có bản được trả, độc giả được giữ chỗ 3 ngày để đến nhận. "
            "Trả về vị trí trong hàng chờ và ngày dự kiến có sách, hoặc lý do từ chối."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "string",
                    "description": "MSSV 8 ký tự của độc giả (ví dụ: '21010123')."
                },
                "book_id": {
                    "type": "string",
                    "description": "Mã sách cần đặt giữ (ví dụ: 'B002'), lấy từ kết quả search_book."
                }
            },
            "required": ["student_id", "book_id"]
        }
    }
]

# ==============================================================================
# 2. QUY ĐỊNH NGHIỆP VỤ (QĐ-TV-01)
# ==============================================================================

TODAY = date(2026, 9, 15)       # Ngày "hôm nay" cố định để test cho kết quả ổn định
MAX_BOOKS = 5                   # Số cuốn mượn về tối đa cùng lúc
LOAN_DAYS = 14                  # Thời hạn mượn / lần
MAX_RENEWALS = 2                # Số lần gia hạn tối đa / cuốn
RENEW_DAYS = 7                  # Mỗi lần gia hạn +7 ngày (tính từ hạn trả hiện tại)
DUE_SOON_DAYS = 3               # Cảnh báo sắp tới hạn khi còn <= 3 ngày
FINE_PER_DAY = 2000             # Phí phạt 2.000đ / cuốn / ngày
LOCK_OVERDUE_DAYS = 30          # Tạm khóa khi quá hạn từ 30 ngày
LOCK_FINE = 100_000             # ... hoặc nợ phí từ 100.000đ
HOLD_DAYS = 3                   # Giữ chỗ 3 ngày khi sách đặt giữ về

CATEGORY_LABELS = {
    "giao_trinh": "Sách giáo trình, tham khảo",
    "sach_thuong": "Sách thường (văn học, phổ thông)",
    "tra_cuu": "Tài liệu tra cứu (chỉ đọc tại chỗ)"
}

# ==============================================================================
# 3. MÔ PHỎNG DỮ LIỆU THƯ VIỆN (MOCK DATABASE)
# ==============================================================================

CATALOG = {
    "B001": {"title": "Nhập môn Học máy", "author": "Nguyễn Văn Hùng", "topic": "Trí tuệ nhân tạo",
             "category": "giao_trinh", "total_copies": 3, "location": {"khu": "A", "tang": 2, "ke": "A2-05"}},
    "B002": {"title": "Deep Learning cơ bản", "author": "Trần Minh Quân", "topic": "Trí tuệ nhân tạo",
             "category": "giao_trinh", "total_copies": 2, "location": {"khu": "A", "tang": 2, "ke": "A2-06"}},
    "B003": {"title": "Xử lý ngôn ngữ tự nhiên", "author": "Lê Thu Hà", "topic": "Trí tuệ nhân tạo",
             "category": "giao_trinh", "total_copies": 2, "location": {"khu": "A", "tang": 2, "ke": "A2-07"}},
    "B004": {"title": "Kinh tế vi mô", "author": "Phạm Quốc Bảo", "topic": "Kinh tế",
             "category": "giao_trinh", "total_copies": 4, "location": {"khu": "B", "tang": 3, "ke": "B3-01"}},
    "B005": {"title": "Nguyên lý Marketing", "author": "Đỗ Thị Lan", "topic": "Kinh tế",
             "category": "giao_trinh", "total_copies": 2, "location": {"khu": "B", "tang": 3, "ke": "B3-04"}},
    "B006": {"title": "Số đỏ", "author": "Vũ Trọng Phụng", "topic": "Văn học",
             "category": "sach_thuong", "total_copies": 3, "location": {"khu": "C", "tang": 1, "ke": "C1-03"}},
    "B007": {"title": "Dế Mèn phiêu lưu ký", "author": "Tô Hoài", "topic": "Văn học",
             "category": "sach_thuong", "total_copies": 2, "location": {"khu": "C", "tang": 1, "ke": "C1-05"}},
    "B008": {"title": "Từ điển Anh - Việt", "author": "Viện Ngôn ngữ học", "topic": "Ngoại ngữ",
             "category": "tra_cuu", "total_copies": 2, "location": {"khu": "D", "tang": 1, "ke": "D1-01"}},
    "B009": {"title": "Thống kê ứng dụng", "author": "Hoàng Anh Tuấn", "topic": "Toán - Thống kê",
             "category": "giao_trinh", "total_copies": 1, "location": {"khu": "B", "tang": 3, "ke": "B3-06"}},
}

READERS = {
    "21010123": {"full_name": "Lê Minh Anh"},      # A: có cuốn sắp tới hạn, gia hạn được
    "21010245": {"full_name": "Trần Quốc Bảo"},    # B: có cuốn bị người khác đặt giữ
    "21010367": {"full_name": "Phạm Thu Trang"},   # C: có cuốn đã gia hạn đủ 2 lần
    "21010489": {"full_name": "Vũ Đức Huy"},       # D: đang có sách quá hạn, bị phạt
    "21010501": {"full_name": "Đỗ Hoàng Nam"},
    "21010623": {"full_name": "Ngô Thị Mai"},
}

# Phiếu mượn đang hiệu lực (sách chưa trả)
LOANS = [
    {"student_id": "21010123", "book_id": "B001", "borrow_date": date(2026, 9, 3), "due_date": date(2026, 9, 17), "renewals_used": 0},
    {"student_id": "21010123", "book_id": "B006", "borrow_date": date(2026, 9, 10), "due_date": date(2026, 9, 24), "renewals_used": 0},
    {"student_id": "21010245", "book_id": "B002", "borrow_date": date(2026, 9, 5), "due_date": date(2026, 9, 19), "renewals_used": 0},
    {"student_id": "21010245", "book_id": "B004", "borrow_date": date(2026, 9, 1), "due_date": date(2026, 9, 22), "renewals_used": 1},
    {"student_id": "21010367", "book_id": "B003", "borrow_date": date(2026, 8, 20), "due_date": date(2026, 9, 17), "renewals_used": 2},
    {"student_id": "21010489", "book_id": "B005", "borrow_date": date(2026, 8, 18), "due_date": date(2026, 9, 1), "renewals_used": 0},
    {"student_id": "21010489", "book_id": "B007", "borrow_date": date(2026, 9, 9), "due_date": date(2026, 9, 23), "renewals_used": 0},
    {"student_id": "21010501", "book_id": "B002", "borrow_date": date(2026, 9, 2), "due_date": date(2026, 9, 16), "renewals_used": 0},
    {"student_id": "21010623", "book_id": "B009", "borrow_date": date(2026, 9, 6), "due_date": date(2026, 9, 20), "renewals_used": 0},
]

# Hàng chờ đặt giữ (theo thứ tự thời gian đặt)
RESERVATIONS = [
    {"student_id": "21010623", "book_id": "B002", "reserved_at": date(2026, 9, 10)},
]

# ==============================================================================
# 4. HÀM TIỆN ÍCH NỘI BỘ
# ==============================================================================

def _normalize(text: str) -> str:
    """Chuẩn hóa chuỗi để tìm kiếm không phân biệt hoa/thường và dấu tiếng Việt"""
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").strip()


# Các từ thừa hay xuất hiện trong câu hỏi (đã bỏ dấu), bỏ qua khi so khớp theo từng từ
SEARCH_STOPWORDS = {
    "sach", "cuon", "quyen", "dau", "ma", "cua", "tac", "gia", "thu", "vien", "con", "hang", "khong",
    "co", "o", "nam", "ke", "nao", "tim", "tra", "cuu", "giup", "minh", "toi", "em", "cho", "hoi",
    "ban", "va", "la", "voi", "nhe", "a", "the", "chu", "de"
}
BOOK_ID_PATTERN = re.compile(r"\bb\d{3}\b")


def _match_books(keyword: str) -> List[str]:
    """
    Tìm mã sách khớp với từ khóa:
    1. Từ khóa có chứa mã sách (B001...) → trả đúng mã đó.
    2. Cả cụm từ khóa nằm trong tên sách / tác giả / chủ đề.
    3. Mọi từ có nghĩa của từ khóa (đã bỏ từ thừa) đều xuất hiện trong tên sách + tác giả + chủ đề.
    """
    kw = _normalize(keyword)
    ids = [code.upper() for code in BOOK_ID_PATTERN.findall(kw) if code.upper() in CATALOG]
    if ids:
        return ids
    if not kw:
        return []
    phrase = [book_id for book_id, book in CATALOG.items()
              if any(kw in _normalize(book[field]) for field in ("title", "author", "topic"))]
    if phrase:
        return phrase
    tokens = [t for t in re.findall(r"\w+", kw) if t not in SEARCH_STOPWORDS]
    if not tokens:
        return []
    return [book_id for book_id, book in CATALOG.items()
            if all(t in re.findall(r"\w+", _normalize(f"{book['title']} {book['author']} {book['topic']}")) for t in tokens)]


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _money(amount: int) -> str:
    """Định dạng tiền kiểu Việt Nam: 28000 -> '28.000đ'"""
    return f"{amount:,}đ".replace(",", ".")


def _error(status: str, message: str) -> str:
    return json.dumps({"status": status, "message": message}, ensure_ascii=False)


def _validate_student(student_id: str) -> Optional[str]:
    """Trả về chuỗi JSON lỗi nếu MSSV không hợp lệ / không tồn tại, ngược lại trả về None"""
    if len(student_id) != 8:
        return _error("INVALID_STUDENT_ID", f"MSSV '{student_id}' không hợp lệ. MSSV phải gồm đúng 8 ký tự (ví dụ: 21010123).")
    if student_id not in READERS:
        return _error("NOT_FOUND", f"Không tìm thấy độc giả có MSSV '{student_id}' trong hệ thống thư viện.")
    return None


def _loans_of_student(student_id: str) -> List[Dict[str, Any]]:
    return [loan for loan in LOANS if loan["student_id"] == student_id]


def _loans_of_book(book_id: str) -> List[Dict[str, Any]]:
    return [loan for loan in LOANS if loan["book_id"] == book_id]


def _reservation_queue(book_id: str) -> List[Dict[str, Any]]:
    return [r for r in RESERVATIONS if r["book_id"] == book_id]


def _available_copies(book_id: str) -> int:
    book = CATALOG[book_id]
    if book["category"] == "tra_cuu":
        return book["total_copies"]
    return book["total_copies"] - len(_loans_of_book(book_id))


def _overdue_days(loan: Dict[str, Any]) -> int:
    return max(0, (TODAY - loan["due_date"]).days)


def _account_lock_reason(student_id: str) -> Optional[str]:
    """Kiểm tra ngưỡng tạm khóa: quá hạn từ 30 ngày hoặc nợ phí từ 100.000đ"""
    loans = _loans_of_student(student_id)
    total_fine = sum(_overdue_days(loan) * FINE_PER_DAY for loan in loans)
    max_overdue = max((_overdue_days(loan) for loan in loans), default=0)
    if max_overdue >= LOCK_OVERDUE_DAYS:
        return f"Có tài liệu quá hạn {max_overdue} ngày (ngưỡng khóa: từ {LOCK_OVERDUE_DAYS} ngày)."
    if total_fine >= LOCK_FINE:
        return f"Đang nợ phí phạt {_money(total_fine)} (ngưỡng khóa: từ {_money(LOCK_FINE)})."
    return None


def _expected_available_date(book_id: str, queue_position: int) -> Optional[str]:
    """Ước tính ngày có sách cho người ở vị trí queue_position trong hàng chờ, dựa trên các hạn trả"""
    due_dates = sorted(loan["due_date"] for loan in _loans_of_book(book_id))
    if not due_dates:
        return None
    return _fmt(due_dates[min(queue_position, len(due_dates)) - 1])


def _renewal_block_reasons(student_id: str, loan: Dict[str, Any]) -> List[Dict[str, str]]:
    """Kiểm tra đồng thời 3 điều kiện gia hạn, trả về danh sách lý do bị chặn (rỗng = được gia hạn)"""
    reasons = []

    overdue_loans = [l for l in _loans_of_student(student_id) if _overdue_days(l) > 0]
    if overdue_loans:
        titles = ", ".join(f"'{CATALOG[l['book_id']]['title']}'" for l in overdue_loans)
        fine = sum(_overdue_days(l) * FINE_PER_DAY for l in overdue_loans)
        reasons.append({
            "code": "HAS_OVERDUE",
            "message": f"Độc giả đang có tài liệu quá hạn: {titles}.",
            "suggestion": f"Trả tài liệu quá hạn và nộp phí phạt ({_money(fine)}) tại quầy trước, sau đó mới gia hạn được."
        })

    reserved_by_others = [r for r in _reservation_queue(loan["book_id"]) if r["student_id"] != student_id]
    if reserved_by_others:
        reasons.append({
            "code": "RESERVED_BY_OTHERS",
            "message": "Cuốn sách này đang có độc giả khác đặt giữ.",
            "suggestion": f"Vui lòng trả sách đúng hạn ({_fmt(loan['due_date'])}) để nhường lượt cho người đặt giữ."
        })

    if loan["renewals_used"] >= MAX_RENEWALS:
        reasons.append({
            "code": "MAX_RENEWALS_REACHED",
            "message": f"Cuốn sách này đã gia hạn đủ {MAX_RENEWALS} lần (tối đa).",
            "suggestion": "Vui lòng trả sách; sau đó có thể mượn lại nếu còn bản rảnh."
        })

    return reasons

# ==============================================================================
# 5. HÀM THỰC THI TOOL (EXECUTION LAYER)
# ==============================================================================

def execute_search_book(keyword: str, topic: str = "") -> str:
    """Tra cứu sách theo tên / tác giả / chủ đề; gợi ý sách cùng chủ đề nếu không tìm thấy"""
    matches = _match_books(str(keyword))

    if not matches:
        suggestions = []
        if topic:
            tp = _normalize(topic)
            suggestions = [
                {"book_id": book_id, "title": book["title"], "author": book["author"],
                 "topic": book["topic"], "available_copies": _available_copies(book_id)}
                for book_id, book in CATALOG.items()
                if tp in _normalize(book["topic"]) or _normalize(book["topic"]) in tp
            ]
        return json.dumps({
            "status": "NOT_FOUND",
            "message": f"Thư viện hiện không có sách khớp với '{keyword}'.",
            "similar_books": suggestions,
            "available_topics": sorted({book["topic"] for book in CATALOG.values()})
        }, ensure_ascii=False)

    results = []
    for book_id in matches:
        book = CATALOG[book_id]
        loanable = book["category"] != "tra_cuu"
        available = _available_copies(book_id)
        item = {
            "book_id": book_id,
            "title": book["title"],
            "author": book["author"],
            "topic": book["topic"],
            "category": CATEGORY_LABELS[book["category"]],
            "loanable": loanable,
            "total_copies": book["total_copies"],
            "available_copies": available,
            "location": book["location"]
        }
        if not loanable:
            item["note"] = "Tài liệu tra cứu: chỉ đọc tại chỗ, không cho mượn về."
        elif available == 0:
            queue = _reservation_queue(book_id)
            item["reservation_queue_length"] = len(queue)
            item["expected_available_date"] = _expected_available_date(book_id, len(queue) + 1)
            item["note"] = "Đã hết bản rảnh. Có thể đặt giữ (reserve_book) để vào hàng chờ."
        results.append(item)

    return json.dumps({"status": "SUCCESS", "today": _fmt(TODAY), "results": results}, ensure_ascii=False)


def execute_get_borrow_record(student_id: str) -> str:
    """Tra hồ sơ mượn/trả của độc giả, kèm cảnh báo sắp tới hạn / quá hạn"""
    student_id = str(student_id).strip()
    error = _validate_student(student_id)
    if error:
        return error

    loans_out = []
    warnings = []
    for loan in _loans_of_student(student_id):
        book = CATALOG[loan["book_id"]]
        days_left = (loan["due_date"] - TODAY).days
        overdue = _overdue_days(loan)
        if overdue > 0:
            status = "OVERDUE"
            warnings.append(f"'{book['title']}' đã quá hạn {overdue} ngày, phí phạt tạm tính {_money(overdue * FINE_PER_DAY)}. Cần trả và nộp phạt ngay.")
        elif days_left <= DUE_SOON_DAYS:
            status = "DUE_SOON"
            warnings.append(f"'{book['title']}' sắp tới hạn (còn {days_left} ngày, hạn {_fmt(loan['due_date'])}). Cân nhắc trả hoặc gia hạn.")
        else:
            status = "ON_TIME"

        block_reasons = _renewal_block_reasons(student_id, loan)
        loans_out.append({
            "book_id": loan["book_id"],
            "title": book["title"],
            "borrow_date": _fmt(loan["borrow_date"]),
            "due_date": _fmt(loan["due_date"]),
            "days_left": days_left,
            "status": status,
            "overdue_days": overdue,
            "fine_estimate": overdue * FINE_PER_DAY,
            "renewals_used": loan["renewals_used"],
            "max_renewals": MAX_RENEWALS,
            "can_renew": not block_reasons,
            "renew_block_reasons": block_reasons
        })

    reservations_out = []
    for r in RESERVATIONS:
        if r["student_id"] == student_id:
            queue = _reservation_queue(r["book_id"])
            reservations_out.append({
                "book_id": r["book_id"],
                "title": CATALOG[r["book_id"]]["title"],
                "reserved_at": _fmt(r["reserved_at"]),
                "queue_position": queue.index(r) + 1
            })

    lock_reason = _account_lock_reason(student_id)
    return json.dumps({
        "status": "SUCCESS",
        "today": _fmt(TODAY),
        "student_id": student_id,
        "full_name": READERS[student_id]["full_name"],
        "account_locked": lock_reason is not None,
        "lock_reason": lock_reason,
        "borrowed_count": len(loans_out),
        "max_books": MAX_BOOKS,
        "loans": loans_out,
        "total_fine": sum(l["fine_estimate"] for l in loans_out),
        "reservations": reservations_out,
        "warnings": warnings
    }, ensure_ascii=False)


def execute_renew_book(student_id: str, book_id: str) -> str:
    """Kiểm tra điều kiện và gia hạn một cuốn sách thêm 7 ngày"""
    student_id = str(student_id).strip()
    book_id = str(book_id).strip().upper()
    error = _validate_student(student_id)
    if error:
        return error

    loan = next((l for l in _loans_of_student(student_id) if l["book_id"] == book_id), None)
    if loan is None:
        return json.dumps({
            "status": "REJECTED",
            "book_id": book_id,
            "reasons": [{
                "code": "NOT_BORROWED",
                "message": f"Độc giả {student_id} hiện không mượn sách có mã '{book_id}'.",
                "suggestion": "Kiểm tra lại mã sách bằng get_borrow_record."
            }]
        }, ensure_ascii=False)

    title = CATALOG[book_id]["title"]
    block_reasons = _renewal_block_reasons(student_id, loan)
    if block_reasons:
        return json.dumps({
            "status": "REJECTED",
            "book_id": book_id,
            "title": title,
            "due_date": _fmt(loan["due_date"]),
            "reasons": block_reasons
        }, ensure_ascii=False)

    old_due = loan["due_date"]
    loan["due_date"] = old_due + timedelta(days=RENEW_DAYS)
    loan["renewals_used"] += 1
    return json.dumps({
        "status": "SUCCESS",
        "book_id": book_id,
        "title": title,
        "old_due_date": _fmt(old_due),
        "new_due_date": _fmt(loan["due_date"]),
        "renewals_used": loan["renewals_used"],
        "renewals_left": MAX_RENEWALS - loan["renewals_used"],
        "message": f"Gia hạn thành công '{title}'. Hạn trả mới: {_fmt(loan['due_date'])}."
    }, ensure_ascii=False)


def execute_reserve_book(student_id: str, book_id: str) -> str:
    """Đặt giữ một đầu sách đã hết bản"""
    student_id = str(student_id).strip()
    book_id = str(book_id).strip().upper()
    error = _validate_student(student_id)
    if error:
        return error
    if book_id not in CATALOG:
        return _error("NOT_FOUND", f"Không tìm thấy sách có mã '{book_id}' trong catalog.")

    book = CATALOG[book_id]

    def rejected(code: str, message: str) -> str:
        return json.dumps({"status": "REJECTED", "book_id": book_id, "title": book["title"],
                           "reason": {"code": code, "message": message}}, ensure_ascii=False)

    if book["category"] == "tra_cuu":
        return rejected("REFERENCE_ONLY", "Tài liệu tra cứu chỉ đọc tại chỗ, không cho mượn về nên không thể đặt giữ.")
    lock_reason = _account_lock_reason(student_id)
    if lock_reason:
        return rejected("ACCOUNT_LOCKED", f"Tài khoản đang bị tạm khóa: {lock_reason} Cần trả tài liệu và nộp đủ phí phạt để gỡ khóa.")
    if any(l["book_id"] == book_id for l in _loans_of_student(student_id)):
        return rejected("ALREADY_BORROWING", "Độc giả đang mượn chính cuốn sách này.")
    if any(r["student_id"] == student_id for r in _reservation_queue(book_id)):
        return rejected("ALREADY_RESERVED", "Độc giả đã đặt giữ cuốn sách này rồi.")
    available = _available_copies(book_id)
    if available > 0:
        loc = book["location"]
        return rejected("BOOK_AVAILABLE",
                        f"Sách vẫn còn {available} bản rảnh, không cần đặt giữ. "
                        f"Vị trí: Khu {loc['khu']}, Tầng {loc['tang']}, Kệ {loc['ke']}.")

    RESERVATIONS.append({"student_id": student_id, "book_id": book_id, "reserved_at": TODAY})
    queue_position = len(_reservation_queue(book_id))
    return json.dumps({
        "status": "SUCCESS",
        "book_id": book_id,
        "title": book["title"],
        "queue_position": queue_position,
        "expected_available_date": _expected_available_date(book_id, queue_position),
        "hold_days": HOLD_DAYS,
        "message": (
            f"Đặt giữ thành công '{book['title']}', vị trí thứ {queue_position} trong hàng chờ. "
            f"Khi có sách, bạn được giữ chỗ {HOLD_DAYS} ngày để đến nhận."
        )
    }, ensure_ascii=False)


# Router gọi tool thực tế
TOOL_ROUTER = {
    "search_book": execute_search_book,
    "get_borrow_record": execute_get_borrow_record,
    "renew_book": execute_renew_book,
    "reserve_book": execute_reserve_book
}

def dispatch_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Hàm trung chuyển thực thi tool"""
    if tool_name in TOOL_ROUTER:
        try:
            return TOOL_ROUTER[tool_name](**arguments)
        except Exception as e:
            return json.dumps({"status": "EXECUTION_ERROR", "error": str(e)}, ensure_ascii=False)
    return json.dumps({"status": "UNKNOWN_TOOL", "error": f"Tool '{tool_name}' không tồn tại!"}, ensure_ascii=False)
