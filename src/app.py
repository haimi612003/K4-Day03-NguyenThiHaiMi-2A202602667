"""
🚀 CORE AGENT APPLICATION (DAY 03: CHATBOT VS REACT AGENT)
Thực thi so sánh giữa Chatbot Baseline (Cấp 2) và ReAct Agent kết nối MCP Server (Cấp 3).
"""

import json
import os
import sys
import time
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from mcp_server import MCPLibraryServer
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    MAX_ITERATIONS,
    build_react_system_prompt
)
from providers import get_llm_provider

load_dotenv()

def load_test_cases():
    """Tải danh sách 5 test cases từ config/test_cases.json hoặc config/test_cases.example.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    if not os.path.exists(config_path):
        example_path = os.path.join(base_dir, "config", "test_cases.example.json")
        if os.path.exists(example_path):
            print("⚠️ [CONFIG NOTICE]: Chưa thấy file 'config/test_cases.json'. Đang dùng mẫu 'config/test_cases.example.json'.")
            print("👉 Hãy chạy: copy config/test_cases.example.json config/test_cases.json và viết test cases theo đề tài của bạn!\n")
            config_path = example_path
        else:
            config_path = "test_cases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_waterfall_trace(trace_data: list):
    """Ghi vết log Waterfall Trace Log ra file docs/trace_waterfall.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    trace_path = os.path.join(docs_dir, "trace_waterfall.json")
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2)
    print(f"📊 [OBSERVABILITY]: Đã lưu {len(trace_data)} sự kiện Waterfall Trace tại '{trace_path}'!")


def login(mcp_server: MCPLibraryServer, student_id: str):
    """
    Xác định độc giả bằng MSSV trước khi vào hệ thống.
    Trả về (student, None) nếu hợp lệ, hoặc (None, thông báo lỗi).
    """
    student_id = str(student_id).strip()
    result = mcp_server.call_tool("get_borrow_record", {"student_id": student_id}, caller_id=student_id).get("result", {})
    if result.get("status") != "SUCCESS":
        return None, result.get("message", "MSSV không hợp lệ.")
    return {"student_id": student_id, "full_name": result["full_name"]}, None


def run_baseline_chatbot(user_query: str, provider):
    """Chạy Chatbot gốc (Cấp 2) không có công cụ gọi Tool"""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot phản hồi:\n{response}")


def run_react_agent(user_query: str, provider, mcp_server: MCPLibraryServer, history: list = None, student: dict = None) -> list:
    """
    [REACT AGENT LOOP] Thực thi vòng lặp Thought -> Action -> Observation với MCP Server.
    Kết quả Observation được nạp lại vào hội thoại để LLM suy luận bước tiếp theo,
    cho tới khi LLM đưa ra câu trả lời cuối (Final Answer) hoặc hết MAX_ITERATIONS.
    history: lịch sử hội thoại dùng chung giữa các lượt (chế độ interactive). None = phiên mới.
    student: độc giả đang đăng nhập {"student_id", "full_name"}; MCP Server chỉ cho thao tác trên hồ sơ của người này.
    Trả về danh sách trace log của phiên thực thi.
    """
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")

    system_prompt = build_react_system_prompt(student)
    caller_id = student["student_id"] if student else None
    messages = history if history is not None else []
    messages.append({"role": "user", "content": user_query})
    step = 0
    trace_logs = []
    tools_list = mcp_server.list_tools()

    while step < MAX_ITERATIONS:
        step += 1
        step_start_time = time.time()
        print(f"\n--- 🔄 Vòng lặp ReAct Loop (Step {step}/{MAX_ITERATIONS}) ---")

        # Gọi LLM với Native Tool Calling Specs + toàn bộ hội thoại (kèm các Observation trước đó)
        llm_response = provider.generate_with_tools(messages, tools_list, system_prompt=system_prompt)
        # Không tính thời gian chờ do giới hạn tốc độ API (rate limit) vào độ trễ suy luận
        latency_ms = round((time.time() - step_start_time) * 1000 - llm_response.get("wait_ms", 0), 2)

        thought = llm_response.get("thought", "Đang suy luận...")
        print(f"🧠 [Thought]: {thought}")

        # Trường hợp 1: LLM quyết định trả lời bằng văn bản → kết thúc vòng lặp
        if llm_response.get("type") == "text":
            final_content = llm_response.get("content", "")
            messages.append({"role": "assistant", "content": final_content})
            print(f"🏁 [Final Answer]: {final_content}")
            trace_logs.append({
                "step": step,
                "query": user_query,
                "action_type": "FINAL_ANSWER",
                "thought": thought,
                "output": final_content,
                "latency_ms": latency_ms
            })
            return trace_logs

        # Trường hợp 2: LLM đề xuất gọi một hoặc nhiều Tool (Action)
        tool_calls = llm_response.get("tool_calls", [])
        messages.append({"role": "assistant", "tool_calls": tool_calls, "raw": llm_response.get("raw")})

        for call in tool_calls:
            print(f"🛠️ [Action Proposed]: {call['name']}({json.dumps(call['arguments'], ensure_ascii=False)})")

            # Thực thi Tool qua MCP Server
            tool_start_time = time.time()
            mcp_result = mcp_server.call_tool(call["name"], call["arguments"], caller_id=caller_id)
            tool_latency_ms = round((time.time() - tool_start_time) * 1000, 2)
            obs_data = mcp_result.get("result", {})
            print(f"👁️ [Observation từ MCP Server]: {json.dumps(obs_data, ensure_ascii=False)}")

            # Nạp Observation lại vào hội thoại cho lượt suy luận kế tiếp
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"], "content": obs_data})
            trace_logs.append({
                "step": step,
                "query": user_query,
                "action_type": "TOOL_EXECUTION",
                "thought": thought,
                "tool_name": call["name"],
                "arguments": call["arguments"],
                "observation": obs_data,
                "latency_ms": latency_ms,
                "tool_latency_ms": tool_latency_ms
            })

    # Hết số vòng lặp cho phép mà LLM chưa đưa ra câu trả lời cuối
    final_content = f"Xin lỗi, mình chưa hoàn tất được yêu cầu trong giới hạn {MAX_ITERATIONS} bước xử lý. Bạn vui lòng thử lại."
    messages.append({"role": "assistant", "content": final_content})
    print(f"⚠️ [MAX_ITERATIONS]: {final_content}")
    trace_logs.append({
        "step": step,
        "query": user_query,
        "action_type": "MAX_ITERATIONS_REACHED",
        "thought": f"Đã chạy đủ {MAX_ITERATIONS} vòng lặp ReAct mà chưa có câu trả lời cuối.",
        "output": final_content,
        "latency_ms": 0.0
    })
    return trace_logs


if __name__ == "__main__":
    print("==========================================================")
    print("🏫 VINUNI AI COURSE - DAY 03 LAB: CHATBOT VS REACT AGENT")
    print("==========================================================")
    
    provider = get_llm_provider()
    mcp_server = MCPLibraryServer()
    
    print(f"🔌 LLM Provider: {provider.__class__.__name__}")
    print(f"🌐 MCP Server: {mcp_server.server_name}\n")
    
    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases thử nghiệm.\n")
    
    if "--interactive" in sys.argv:
        print("🎮 [INTERACTIVE MODE] Trò chuyện trực tiếp với ReAct Agent:")
        print("💡 Gợi ý câu hỏi thử nghiệm:")
        print("   - Tra cứu vị trí sách: 'Thư viện còn cuốn \"Deep Learning cơ bản\" không, ở kệ nào?'")
        print("   - Kiểm tra mượn/trả: 'Mình đang mượn những sách nào, có bị phạt không?'")
        print("   - Gia hạn tài liệu: 'Gia hạn giúp mình tất cả sách đang mượn'")
        print("   - Gõ 'exit' hoặc 'quit' để kết thúc phiên trò chuyện.\n")
        student = None
        try:
            # Đăng nhập bằng MSSV trước khi trò chuyện
            while student is None:
                entered = input("🔑 Nhập MSSV để đăng nhập: ").strip()
                if not entered or entered.lower() in ["exit", "quit"]:
                    break
                student, error = login(mcp_server, entered)
                print(f"✅ Xin chào {student['full_name']} (MSSV {student['student_id']})!\n" if student else f"❌ {error}")
        except (KeyboardInterrupt, EOFError):
            pass
        history = []       # Lịch sử hội thoại dùng chung giữa các lượt để Agent nhớ ngữ cảnh
        session_logs = []
        while student:
            try:
                user_input = input("👤 Sinh viên hỏi: ").strip()
                if not user_input or user_input.lower() in ["exit", "quit"]:
                    print("👋 Tạm biệt! Kết thúc phiên trò chuyện.")
                    break
                logs = run_react_agent(user_input, provider, mcp_server, history, student)
                session_logs.extend(logs)
                save_waterfall_trace(session_logs)
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Đã thoát phiên tương tác.")
                break
    elif "--all" in sys.argv:
        print("🚀 [TEST SUITE MODE] Kiểm tra 5 Test Cases:")
        completed_count = 0
        todo_count = 0
        all_traces = []
        
        for tc in tests:
            print(f"\n==================================================")
            print(f"🧪 [{tc['id']}] Loại test: {tc['type']} (Độ phức tạp: {tc['complexity']})")
            print(f"📌 Kỳ vọng: {tc['expected_behavior']}")
            
            if tc["question"].strip().startswith("TODO"):
                print(f"⏸️ [CHƯA KÍCH HOẠT - ĐANG LÀ TODO]:")
                print(f"   {tc['question']}")
                print(f"   👉 Hãy mở file 'config/test_cases.json' để viết câu hỏi thực tế cho Test Case này!")
                todo_count += 1
            else:
                # Mỗi test case chạy với phiên đăng nhập của độc giả trong trường 'student_id'
                student = login(mcp_server, tc["student_id"])[0] if tc.get("student_id") else None
                print(f"🔑 Đăng nhập: {student['full_name']} (MSSV {student['student_id']})" if student else "🔑 Không đăng nhập")
                logs = run_react_agent(tc["question"], provider, mcp_server, student=student)
                all_traces.extend(logs)
                completed_count += 1
                
        print(f"\n==================================================")
        print(f"📊 [KẾT QUẢ TEST SUITE]: Đã thực thi {completed_count}/{len(tests)} Test Cases | {todo_count} Test Cases đang chờ điền câu hỏi (TODO)")
        if all_traces:
            save_waterfall_trace(all_traces)
        print(f"💡 Để trò chuyện trực tiếp từng câu: Chạy 'python src/app.py --interactive'")
    else:
        # Chế độ mặc định khi chỉ gõ 'python src/app.py'
        print("ℹ️ HƯỚNG DẪN SỬ DỤNG CHƯƠNG TRÌNH:")
        print("  1. Chat trực tiếp liên tục:   python src/app.py --interactive")
        print("  2. Chạy toàn bộ Test Cases:    python src/app.py --all\n")
        
        sample = tests[1]
        print(f"--- 🏁 DEMO CHẠY THỬ 1 TEST CASE MẪU ({sample['id']}) ---")
        student = login(mcp_server, sample["student_id"])[0] if sample.get("student_id") else None
        logs = run_react_agent(sample["question"], provider, mcp_server, student=student)
        save_waterfall_trace(logs)
        print("\n💡 Hãy thử ngay lệnh: python src/app.py --interactive để chat trực tiếp!")
