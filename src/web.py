"""
🌐 WEB UI SERVER — TRỢ LÝ THƯ VIỆN (ReAct Agent + MCP Server)
Phục vụ giao diện web (src/web/index.html) và các API gọi ReAct Agent thật.
Chạy: python src/web.py  → mở http://localhost:8000
"""

import os
import sys
import threading
import uuid
import webbrowser

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from app import run_react_agent, login
from mcp_server import MCPLibraryServer
from providers import get_llm_provider, MockOfflineProvider
from tools import TODAY, READERS, MAX_BOOKS

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)   # In log ReAct ra terminal ngay lập tức
except Exception:
    pass

HOST = "127.0.0.1"   # Chỉ cho phép truy cập từ chính máy này
PORT = int(os.getenv("WEB_PORT", "8000"))
INDEX_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "index.html")

# Tình huống kiểm thử của từng độc giả mẫu (hiển thị ở trang đăng nhập)
DEMO_NOTES = {
    "21010123": "Có cuốn sắp tới hạn, gia hạn được",
    "21010245": "1 cuốn bị người khác đặt giữ",
    "21010367": "Có cuốn đã gia hạn đủ 2 lần",
    "21010489": "Đang quá hạn 1 cuốn, phạt 28.000đ",
    "21010501": "Có cuốn còn 1 ngày tới hạn",
    "21010623": "Đang mượn 1 cuốn, đặt giữ 1 cuốn",
}

provider = get_llm_provider()
mcp_server = MCPLibraryServer()
sessions = {}                    # token -> {"student": {...}, "history": [...]}
agent_lock = threading.Lock()    # Dữ liệu mô phỏng dùng chung → xử lý tuần tự từng câu hỏi


def provider_label() -> str:
    if isinstance(provider, MockOfflineProvider):
        return "mock offline"
    return f"{provider.__class__.__name__.replace('Provider', '').lower()} · {provider.model_name}"


def reader_stats(student_id: str) -> dict:
    """Số liệu hồ sơ hiển thị ở cột bên trái, lấy qua MCP Server (get_borrow_record)"""
    record = mcp_server.call_tool("get_borrow_record", {"student_id": student_id}, caller_id=student_id)["result"]
    loans = record.get("loans", [])
    return {
        "borrowed": f"{record.get('borrowed_count', 0)} / {record.get('max_books', MAX_BOOKS)}",
        "due_soon": sum(loan["status"] == "DUE_SOON" for loan in loans),
        "overdue": sum(loan["status"] == "OVERDUE" for loan in loans),
        "fine": f"{record.get('total_fine', 0):,}đ".replace(",", "."),
    }


async def read_session(request: Request):
    body = await request.json()
    return body, sessions.get(body.get("token"))


async def index(request: Request):
    return FileResponse(INDEX_HTML)


async def api_info(request: Request):
    return JSONResponse({
        "today": f"{TODAY:%d/%m/%Y}",
        "provider": provider_label(),
        "is_mock": isinstance(provider, MockOfflineProvider),
        "readers": [{"id": sid, "name": r["full_name"], "note": DEMO_NOTES.get(sid, "")} for sid, r in READERS.items()],
    })


async def api_login(request: Request):
    body = await request.json()
    student, error = login(mcp_server, body.get("student_id", ""))
    if not student:
        return JSONResponse({"error": error}, status_code=400)
    token = uuid.uuid4().hex
    sessions[token] = {"student": student, "history": []}
    return JSONResponse({"token": token, "student": student, "stats": reader_stats(student["student_id"])})


async def api_chat(request: Request):
    body, session = await read_session(request)
    if not session:
        return JSONResponse({"error": "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại."}, status_code=401)
    message = str(body.get("message", "")).strip()
    if not message:
        return JSONResponse({"error": "Câu hỏi đang trống."}, status_code=400)

    history = session["history"]
    history_len = len(history)

    def work():
        with agent_lock:
            return run_react_agent(message, provider, mcp_server, history, session["student"])

    try:
        trace = await run_in_threadpool(work)
    except RuntimeError as e:
        del history[history_len:]   # Hoàn tác lượt lỗi để lịch sử hội thoại không bị dở dang
        return JSONResponse({"error": str(e)}, status_code=502)

    final = next((e for e in reversed(trace) if e["action_type"] != "TOOL_EXECUTION"), {})
    return JSONResponse({
        "answer": final.get("output", ""),
        "trace": trace,
        "stats": reader_stats(session["student"]["student_id"]),
    })


async def api_clear(request: Request):
    _, session = await read_session(request)
    if session:
        session["history"].clear()
    return JSONResponse({"ok": True})


async def api_logout(request: Request):
    body = await request.json()
    sessions.pop(body.get("token"), None)
    return JSONResponse({"ok": True})


app = Starlette(routes=[
    Route("/", index),
    Route("/api/info", api_info),
    Route("/api/login", api_login, methods=["POST"]),
    Route("/api/chat", api_chat, methods=["POST"]),
    Route("/api/clear", api_clear, methods=["POST"]),
    Route("/api/logout", api_logout, methods=["POST"]),
])


if __name__ == "__main__":
    url = f"http://localhost:{PORT}"
    print("==========================================================")
    print("🌐 TRỢ LÝ THƯ VIỆN — WEB UI")
    print(f"🔌 LLM Provider: {provider_label()} | 🌐 MCP Server: {mcp_server.server_name}")
    print(f"👉 Mở trình duyệt tại: {url}   (Ctrl + C để dừng)")
    print("==========================================================")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
