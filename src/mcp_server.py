"""
🔌 MODEL CONTEXT PROTOCOL (MCP) SERVER MODULE
Mô phỏng kiến trúc MCP Server (Client-Server Architecture) cung cấp công cụ chuẩn hóa cho Trợ lý Thư viện.
"""

import json
import sys
from typing import Dict, Any, List
from tools import TOOLS_SCHEMA, dispatch_tool_call

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Các Tool gắn với hồ sơ cá nhân (có tham số student_id) → cần kiểm soát quyền truy cập theo MSSV đăng nhập
STUDENT_SCOPED_TOOLS = {
    tool["name"] for tool in TOOLS_SCHEMA
    if "student_id" in tool.get("parameters", {}).get("properties", {})
}

class MCPLibraryServer:
    """
    Giả lập MCP Server tuân thủ chuẩn giao thức Model Context Protocol
    """
    def __init__(self, server_name: str = "university-library-mcp-server"):
        self.server_name = server_name
        self.version = "2026.1.0"

    def list_tools(self) -> List[Dict[str, Any]]:
        """Trả về danh sách các Tools chuẩn giao thức MCP"""
        return TOOLS_SCHEMA

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], caller_id: str = None) -> Dict[str, Any]:
        """
        [TASK 2.1] Thực thi request gọi Tool theo chuẩn MCP JSON-RPC 2.0
        caller_id: MSSV của độc giả đang đăng nhập. Khi có caller_id, các Tool gắn với hồ sơ cá nhân
        (có tham số student_id) chỉ được thao tác trên hồ sơ của chính độc giả đó.
        """
        if caller_id and tool_name in STUDENT_SCOPED_TOOLS:
            requested_id = str(arguments.get("student_id") or caller_id).strip()
            if requested_id != caller_id:
                return self._response(tool_name, {
                    "status": "PERMISSION_DENIED",
                    "message": (
                        f"Bạn đang đăng nhập với MSSV {caller_id} nên chỉ được tra cứu / thao tác trên hồ sơ "
                        f"của chính mình, không được truy cập hồ sơ của MSSV {requested_id}."
                    )
                })
            arguments = {**arguments, "student_id": caller_id}

        # 1. Gọi Tool Router để lấy chuỗi JSON kết quả
        raw_result = dispatch_tool_call(tool_name, arguments)
        # 2. Chuyển chuỗi JSON thành Python Dictionary
        content = json.loads(raw_result)
        # 3. Đóng gói phản hồi theo chuẩn JSON-RPC 2.0
        return self._response(tool_name, content)

    def _response(self, tool_name: str, content: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "server": self.server_name,
            "tool": tool_name,
            "result": content
        }


if __name__ == "__main__":
    print("==========================================================")
    print("🔌 KIỂM THỬ ĐỘC LẬP MCP SERVER (university-library-mcp-server)")
    print("==========================================================")

    server = MCPLibraryServer()
    tools = server.list_tools()
    print(f"✅ Khởi tạo thành công MCP Server: {server.server_name} (Version: {server.version})")
    print(f"📦 Số lượng Tools công bố: {len(tools)}")

    # Kiểm tra TASK 1.2: mọi Tool đều có schema đầy đủ (properties + required)
    for tool in tools:
        params = tool.get("parameters", {})
        if params.get("properties") and params.get("required"):
            print(f"✅ [TASK 1.2]: Tool '{tool['name']}' đã có schema đầy đủ (required: {params['required']}).")
        else:
            print(f"⏳ [TASK 1.2]: Tool '{tool.get('name')}' chưa khai báo đủ properties / required trong 'src/tools.py'.")

    # Kiểm tra TASK 2.1: gọi thử Tool qua MCP JSON-RPC
    test_result = server.call_tool("search_book", {"keyword": "Nhập môn Học máy"})
    if test_result.get("jsonrpc") == "2.0" and test_result.get("result"):
        print(f"✅ [TASK 2.1]: Test dispatch tool 'search_book' thành công:")
        print(f"   Phản hồi JSON-RPC: {json.dumps(test_result, ensure_ascii=False)}")
    else:
        print("⏳ [TASK 2.1]: Hàm call_tool() chưa trả về đúng chuẩn JSON-RPC. Hãy kiểm tra lại 'src/mcp_server.py'!")

    # Kiểm tra kiểm soát truy cập: độc giả 21010123 không được xem hồ sơ của 21010245
    denied = server.call_tool("get_borrow_record", {"student_id": "21010245"}, caller_id="21010123")["result"]
    if denied.get("status") == "PERMISSION_DENIED":
        print(f"✅ [ACCESS CONTROL]: Chặn truy cập hồ sơ sinh viên khác: {denied['message']}")
    else:
        print("⚠️ [ACCESS CONTROL]: Chưa chặn được truy cập hồ sơ sinh viên khác!")
