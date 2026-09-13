"""
🔌 MULTI-PROVIDER LLM ADAPTER (Google Gemini, OpenAI, Groq & Offline Mock)
Hỗ trợ Native Tool Calling và chuyển đổi linh hoạt qua biến môi trường LLM_PROVIDER.

Định dạng lịch sử hội thoại dùng chung (provider-agnostic) truyền vào generate_with_tools():
  {"role": "user", "content": "<câu hỏi>"}
  {"role": "assistant", "content": "<câu trả lời>"}
  {"role": "assistant", "tool_calls": [{"id", "name", "arguments"}], "raw": <content gốc của provider>}
  {"role": "tool", "tool_call_id": "<id>", "name": "<tool>", "content": <dict kết quả Observation>}

Kết quả trả về của generate_with_tools():
  {"type": "text", "content": "...", "thought": "..."}
  {"type": "tool_call", "tool_calls": [{"id", "name", "arguments"}], "thought": "...", "raw": ...}
"""

import os
import re
import sys
import json
import time
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

class BaseLLMProvider:
    """Interface cơ sở cho các LLM Provider hỗ trợ Native Tool Calling"""
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def generate_with_tools(self, messages: List[Dict[str, Any]], tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        raise NotImplementedError


def _vnd(amount: int) -> str:
    return f"{amount:,}đ".replace(",", ".")


def is_daily_quota_error(message: str) -> bool:
    """Lỗi 429 do hết quota THEO NGÀY (chờ vài giây cũng không gọi lại được), khác với giới hạn theo phút"""
    return "PerDay" in message or "per day" in message.lower()


class MockOfflineProvider(BaseLLMProvider):
    """Offline Mock Provider dùng để chạy thử mà không tốn API Key (mô phỏng quyết định của LLM bằng từ khóa)"""
    def __init__(self):
        self.model_name = "Offline-Mock-Model-2026"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return f"[Mock Chatbot Response]: Xin chào! Tôi đã nhận được câu hỏi '{prompt}'. (Chế độ Chatbot không có Tool tra cứu dữ liệu thời gian thực)."

    # ---------------- Mô phỏng quyết định gọi Tool ----------------

    def generate_with_tools(self, messages: List[Dict[str, Any]], tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        last_user_idx = max(i for i, m in enumerate(messages) if m["role"] == "user")
        text = messages[last_user_idx]["content"]
        t = text.lower()
        # Kết quả Tool đã nhận trong lượt hiện tại (sau câu hỏi mới nhất của user)
        results = {}
        for m in messages[last_user_idx + 1:]:
            if m["role"] == "tool":
                results.setdefault(m["name"], []).append(m["content"])

        student_id = self._find_student_id(messages, system_prompt)
        book_code = re.search(r"\b[Bb]\d{3}\b", text)
        keyword = self._find_quoted(text) or (book_code.group().upper() if book_code else None)

        # Câu hỏi về quy định gia hạn → trả lời trực tiếp, không cần Tool
        if "gia hạn" in t and ("điều kiện" in t or "quy định" in t) and not re.search(r"\d{8}", text):
            return self._text(
                "Để được gia hạn, cuốn sách phải thỏa đồng thời 3 điều kiện: (1) không có độc giả khác đặt giữ; "
                "(2) bạn không đang quá hạn cuốn nào; (3) cuốn đó chưa gia hạn đủ 2 lần. Mỗi lần gia hạn thêm 7 ngày "
                "tính từ hạn trả hiện tại.",
                "Câu hỏi về quy định gia hạn, trả lời trực tiếp từ quy định thư viện, không cần gọi Tool."
            )

        if "gia hạn" in t:
            return self._renew_flow(student_id, keyword, t, results)
        if "đặt giữ" in t:
            return self._reserve_flow(messages, student_id, keyword, results)
        if any(k in t for k in ["đang mượn", "tình trạng", "hạn trả", "phạt", "nợ sách", "mượn gì"]):
            if not student_id:
                return self._ask_student_id()
            if "get_borrow_record" not in results:
                return self._call("get_borrow_record", {"student_id": student_id},
                                  f"Người dùng muốn kiểm tra tình trạng mượn/trả. Tôi sẽ gọi get_borrow_record với MSSV {student_id}.")
            return self._text(self._summarize_record(results["get_borrow_record"][-1]),
                              "Đã có hồ sơ mượn/trả. Tổng hợp danh sách sách đang mượn và cảnh báo hạn trả.")
        if book_code or any(k in t for k in ["sách", "cuốn", "kệ", "ở đâu", "tìm", "còn"]):
            if "search_book" not in results:
                kw = keyword or text
                return self._call("search_book", {"keyword": kw},
                                  f"Người dùng muốn tra cứu sách '{kw}'. Tôi sẽ gọi search_book.")
            return self._text(self._summarize_search(results["search_book"][-1]),
                              "Đã có kết quả tra cứu catalog. Tổng hợp tình trạng và vị trí sách.")
        return self._text(
            "Mình hỗ trợ 3 việc: tra cứu vị trí sách, kiểm tra tình trạng mượn/trả và gia hạn tài liệu. "
            "Yêu cầu này nằm ngoài phạm vi hỗ trợ.",
            "Yêu cầu nằm ngoài 3 việc được hỗ trợ."
        )

    def _renew_flow(self, student_id, keyword, t, results) -> Dict[str, Any]:
        if not student_id:
            return self._ask_student_id()
        if "get_borrow_record" not in results:
            return self._call("get_borrow_record", {"student_id": student_id},
                              f"Người dùng muốn gia hạn. Tôi cần tra hồ sơ mượn của MSSV {student_id} để lấy mã sách.")
        record = results["get_borrow_record"][-1]
        if record.get("status") != "SUCCESS":
            return self._text(record.get("message", "Không tra được hồ sơ mượn."), "Không tra được hồ sơ, báo lại cho user.")
        if "renew_book" not in results:
            loans = record["loans"]
            if keyword and "tất cả" not in t:
                loans = [l for l in loans if keyword.lower() in l["title"].lower() or keyword.upper() == l["book_id"]]
            if not loans:
                return self._text("Mình không thấy cuốn sách này trong danh sách bạn đang mượn.",
                                  "Không có cuốn phù hợp trong hồ sơ mượn.")
            calls = [{"name": "renew_book", "arguments": {"student_id": student_id, "book_id": l["book_id"]}} for l in loans]
            titles = ", ".join(f"'{l['title']}'" for l in loans)
            return self._calls(calls, f"Đã có hồ sơ. Tôi sẽ gọi renew_book cho từng cuốn: {titles}.")
        lines = []
        for r in results["renew_book"]:
            if r.get("status") == "SUCCESS":
                lines.append(f"✅ '{r['title']}': gia hạn thành công, hạn trả mới {r['new_due_date']}.")
            else:
                reason = r["reasons"][0]
                lines.append(f"❌ '{r.get('title', r.get('book_id'))}': không gia hạn được. {reason['message']} {reason['suggestion']}")
        return self._text("\n".join(lines), "Đã có kết quả gia hạn từng cuốn. Tổng hợp cuốn nào thành công, cuốn nào bị từ chối.")

    def _reserve_flow(self, messages, student_id, keyword, results) -> Dict[str, Any]:
        if not student_id:
            return self._ask_student_id()
        if "reserve_book" in results:
            r = results["reserve_book"][-1]
            msg = r.get("message") or r.get("reason", {}).get("message", "Không đặt giữ được.")
            return self._text(msg, "Đã có kết quả đặt giữ. Báo lại cho user.")
        # Lấy mã sách từ kết quả tra cứu gần nhất trong hội thoại (có thể ở lượt trước)
        search = next((m["content"] for m in reversed(messages)
                       if m["role"] == "tool" and m["name"] == "search_book" and m["content"].get("results")), None)
        if search is None:
            if not keyword:
                return self._text("Bạn muốn đặt giữ cuốn sách nào?", "Chưa biết cuốn sách cần đặt giữ.")
            return self._call("search_book", {"keyword": keyword}, f"Cần tìm mã sách '{keyword}' trước khi đặt giữ.")
        book = search["results"][0]
        return self._call("reserve_book", {"student_id": student_id, "book_id": book["book_id"]},
                          f"User đồng ý đặt giữ '{book['title']}'. Tôi sẽ gọi reserve_book.")

    # ---------------- Tổng hợp câu trả lời từ Observation ----------------

    def _summarize_search(self, obs: Dict[str, Any]) -> str:
        if obs.get("status") != "SUCCESS":
            msg = obs.get("message", "Không tìm thấy sách.")
            similar = obs.get("similar_books") or []
            if similar:
                msg += " Sách tương đương: " + ", ".join(f"'{b['title']}'" for b in similar) + "."
            return msg
        lines = []
        for b in obs["results"]:
            loc = b["location"]
            where = f"Khu {loc['khu']}, Tầng {loc['tang']}, Kệ {loc['ke']}"
            if not b["loanable"]:
                lines.append(f"'{b['title']}' ở {where}. {b['note']}")
            elif b["available_copies"] > 0:
                lines.append(f"'{b['title']}' còn {b['available_copies']}/{b['total_copies']} bản rảnh tại {where}.")
            else:
                lines.append(f"'{b['title']}' đã hết bản, dự kiến có lại từ {b['expected_available_date']}. "
                             f"Bạn có muốn đặt giữ không?")
        return "\n".join(lines)

    def _summarize_record(self, obs: Dict[str, Any]) -> str:
        if obs.get("status") != "SUCCESS":
            return obs.get("message", "Không tra được hồ sơ mượn.")
        lines = [f"{obs['full_name']} đang mượn {obs['borrowed_count']}/{obs['max_books']} cuốn:"]
        for l in obs["loans"]:
            lines.append(f"- '{l['title']}': hạn trả {l['due_date']} ({l['status']}).")
        lines.append(f"Tổng phí phạt: {_vnd(obs['total_fine'])}.")
        lines += [f"⚠️ {w}" for w in obs["warnings"]]
        return "\n".join(lines)

    # ---------------- Tiện ích ----------------

    @staticmethod
    def _find_student_id(messages, system_prompt: str = "") -> Optional[str]:
        """
        Xác định MSSV cần thao tác: MSSV user nhắc trong câu hỏi mới nhất → MSSV phiên đăng nhập (System Prompt)
        → MSSV user nhắc ở các lượt trước (mô phỏng trí nhớ hội thoại)
        """
        user_texts = [m["content"] for m in reversed(messages) if m["role"] == "user"]
        found = re.search(r"\b\d{8}\b", user_texts[0]) if user_texts else None
        if found:
            return found.group()
        session = re.search(r"đang đăng nhập: .*?MSSV (\d{8})", system_prompt)
        if session:
            return session.group(1)
        for text in user_texts[1:]:
            found = re.search(r"\b\d{8}\b", text)
            if found:
                return found.group()
        return None

    @staticmethod
    def _find_quoted(text: str) -> Optional[str]:
        found = re.search(r"['\"“‘]([^'\"”’]+)['\"”’]", text)
        return found.group(1).strip() if found else None

    @staticmethod
    def _text(content: str, thought: str) -> Dict[str, Any]:
        return {"type": "text", "content": f"[Mock Agent Response]: {content}", "thought": thought}

    def _ask_student_id(self) -> Dict[str, Any]:
        return self._text("Bạn cho mình xin MSSV (8 ký tự) để tra hồ sơ nhé.", "Cần MSSV để xác định user nhưng user chưa cung cấp.")

    def _call(self, name: str, arguments: Dict[str, Any], thought: str) -> Dict[str, Any]:
        return self._calls([{"name": name, "arguments": arguments}], thought)

    @staticmethod
    def _calls(calls: List[Dict[str, Any]], thought: str) -> Dict[str, Any]:
        tool_calls = [{"id": f"mock_call_{i}", **c} for i, c in enumerate(calls)]
        return {"type": "tool_call", "tool_calls": tool_calls, "thought": thought, "raw": None}


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider (Native Tool Calling với Google GenAI SDK)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-3.6-flash"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(model=self.model_name, contents=contents)
            return response.text
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"

    @staticmethod
    def _to_contents(messages: List[Dict[str, Any]]) -> list:
        """Chuyển lịch sử hội thoại chung sang định dạng contents của Gemini"""
        from google.genai import types

        contents = []
        prev_role = None
        for m in messages:
            if m["role"] == "user":
                contents.append(types.Content(role="user", parts=[types.Part(text=m["content"])]))
            elif m["role"] == "assistant" and m.get("tool_calls"):
                if m.get("raw") is not None:
                    # Giữ nguyên content gốc của Gemini (kèm thought signature nếu có)
                    contents.append(m["raw"])
                else:
                    contents.append(types.Content(role="model", parts=[
                        types.Part(function_call=types.FunctionCall(name=c["name"], args=c["arguments"]))
                        for c in m["tool_calls"]
                    ]))
            elif m["role"] == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part(text=m["content"])]))
            elif m["role"] == "tool":
                part = types.Part.from_function_response(name=m["name"], response=m["content"])
                # Gom các kết quả Tool liên tiếp vào cùng một lượt phản hồi
                if prev_role == "tool":
                    contents[-1].parts.append(part)
                else:
                    contents.append(types.Content(role="user", parts=[part]))
            prev_role = m["role"]
        return contents

    def _generate_with_retry(self, client, contents, config, max_retries: int = 5):
        """
        Gọi Gemini; nếu vượt giới hạn tốc độ (429 RESOURCE_EXHAUSTED, gói miễn phí ~5 lượt/phút)
        thì chờ đúng thời gian Google yêu cầu rồi thử lại. Trả về (response, tổng thời gian chờ ms).
        """
        from google.genai import errors

        waited_ms = 0.0
        for attempt in range(max_retries + 1):
            try:
                return client.models.generate_content(model=self.model_name, contents=contents, config=config), waited_ms
            except errors.ClientError as e:
                if e.code == 429 and is_daily_quota_error(str(e)):
                    found = re.search(r"quotaValue': '(\d+)'", str(e))
                    limit = f" ({found.group(1)} lượt/ngày)" if found else ""
                    raise RuntimeError(
                        f"[Gemini API Error]: Đã hết quota Gemini miễn phí trong ngày{limit} cho model {self.model_name}. "
                        "Quota được đặt lại lúc 0h giờ Thái Bình Dương (khoảng 14h–15h giờ Việt Nam). "
                        "Hãy thử lại sau, dùng API key khác, hoặc bật thanh toán cho project Gemini."
                    ) from e
                if e.code != 429 or attempt == max_retries:
                    raise
                found = re.search(r"retry in ([\d.]+)s", str(e))
                delay = float(found.group(1)) + 1 if found else 60.0
                print(f"⏳ [Gemini Rate Limit]: Vượt giới hạn tốc độ của gói miễn phí, chờ {delay:.0f}s rồi thử lại ({attempt + 1}/{max_retries})...")
                time.sleep(delay)
                waited_ms += delay * 1000

    def generate_with_tools(self, messages: List[Dict[str, Any]], tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            print("ℹ️ [Gemini Provider]: Chưa tìm thấy GEMINI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline.")
            return MockOfflineProvider().generate_with_tools(messages, tools_schema, system_prompt)

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)

            # Chuẩn hóa function declarations cho Gemini SDK
            function_declarations = []
            for tool in tools_schema:
                # Bỏ qua các tool schema chưa được định nghĩa hoàn chỉnh
                if not tool.get("name") or not tool.get("parameters"):
                    continue
                function_declarations.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {})
                })

            config = types.GenerateContentConfig(
                system_instruction=system_prompt if system_prompt else None,
                tools=[{"function_declarations": function_declarations}] if function_declarations else None,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                temperature=0.2
            )

            response, wait_ms = self._generate_with_retry(client, self._to_contents(messages), config)

            # Kiểm tra xem Gemini có trả về Tool Call không
            if response.function_calls:
                tool_calls = [
                    {"id": call.id or f"gemini_call_{i}", "name": call.name, "arguments": dict(call.args) if call.args else {}}
                    for i, call in enumerate(response.function_calls)
                ]
                parts = response.candidates[0].content.parts or []
                model_text = " ".join(p.text for p in parts if p.text).strip()
                summary = "; ".join(f"{c['name']}({json.dumps(c['arguments'], ensure_ascii=False)})" for c in tool_calls)
                return {
                    "type": "tool_call",
                    "tool_calls": tool_calls,
                    "thought": model_text or f"Gemini quyết định gọi công cụ: {summary}",
                    "raw": response.candidates[0].content,
                    "wait_ms": wait_ms
                }
            else:
                return {
                    "type": "text",
                    "content": response.text or "",
                    "thought": "Gemini tổng hợp câu trả lời bằng văn bản (không cần gọi thêm công cụ).",
                    "wait_ms": wait_ms
                }

        except RuntimeError:
            raise
        except Exception as e:
            # Đã cấu hình API Key thật → dừng và báo lỗi, không lặng lẽ fallback về Mock (tránh sinh trace log giả)
            raise RuntimeError(f"[Gemini API Error]: Gọi live API thất bại ({str(e)}). Kiểm tra lại GEMINI_API_KEY / LLM_MODEL trong .env.") from e


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (Native Tool Calling với OpenAI SDK)"""
    label = "OpenAI"
    env_key = "OPENAI_API_KEY"
    placeholder = "your_openai_api_key_here"
    base_url = None
    default_model = "gpt-4o-mini"

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv(self.env_key)
        self.model_name = model or os.getenv("LLM_MODEL") or self.default_model

    def _client(self):
        from openai import OpenAI
        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == self.placeholder:
            return f"[{self.label} Error]: Chưa cấu hình {self.env_key} trong file .env! Đang sử dụng chế độ Mock."
        try:
            client = self._client()
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(model=self.model_name, messages=messages)
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"[{self.label} Exception]: {str(e)}"

    @staticmethod
    def _to_messages(messages: List[Dict[str, Any]], system_prompt: str) -> list:
        """Chuyển lịch sử hội thoại chung sang định dạng messages của OpenAI"""
        out = [{"role": "system", "content": system_prompt}] if system_prompt else []
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                out.append({"role": "assistant", "content": None, "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                    for c in m["tool_calls"]
                ]})
            elif m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"],
                            "content": json.dumps(m["content"], ensure_ascii=False)})
            else:
                out.append({"role": m["role"], "content": m["content"]})
        return out

    def generate_with_tools(self, messages: List[Dict[str, Any]], tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        if not self.api_key or self.api_key == self.placeholder:
            print(f"ℹ️ [{self.label} Provider]: Chưa tìm thấy {self.env_key} hợp lệ. Tự động chuyển sang Mock Offline.")
            return MockOfflineProvider().generate_with_tools(messages, tools_schema, system_prompt)

        try:
            client = self._client()

            tools = []
            for tool in tools_schema:
                if not tool.get("name"):
                    continue
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {})
                    }
                })

            kwargs = {"model": self.model_name, "messages": self._to_messages(messages, system_prompt)}
            if tools:
                kwargs.update(tools=tools, tool_choice="auto")
            response = client.chat.completions.create(**kwargs)

            msg = response.choices[0].message
            # Phần suy luận của model (reasoning models trên Groq trả về trường 'reasoning')
            reasoning = (getattr(msg, "reasoning", None) or "").strip()
            if msg.tool_calls:
                tool_calls = [
                    {"id": call.id, "name": call.function.name,
                     "arguments": json.loads(call.function.arguments) if call.function.arguments else {}}
                    for call in msg.tool_calls
                ]
                summary = "; ".join(f"{c['name']}({json.dumps(c['arguments'], ensure_ascii=False)})" for c in tool_calls)
                return {
                    "type": "tool_call",
                    "tool_calls": tool_calls,
                    "thought": reasoning or (msg.content or "").strip() or f"{self.label} quyết định gọi công cụ: {summary}",
                    "raw": None
                }
            else:
                return {
                    "type": "text",
                    "content": msg.content or "",
                    "thought": reasoning or f"{self.label} tổng hợp câu trả lời bằng văn bản (không cần gọi thêm công cụ)."
                }
        except Exception as e:
            # Đã cấu hình API Key thật → dừng và báo lỗi, không lặng lẽ fallback về Mock (tránh sinh trace log giả)
            raise RuntimeError(f"[{self.label} API Error]: Gọi live API thất bại ({str(e)}). Kiểm tra lại {self.env_key} / LLM_MODEL trong .env.") from e


class GroqProvider(OpenAIProvider):
    """Groq Provider (API tương thích OpenAI → dùng lại OpenAI SDK với base_url của Groq)"""
    label = "Groq"
    env_key = "GROQ_API_KEY"
    placeholder = "your_groq_api_key_here"
    base_url = "https://api.groq.com/openai/v1"
    default_model = "openai/gpt-oss-120b"


def get_llm_provider() -> BaseLLMProvider:
    """Factory function khởi tạo Provider theo LLM_PROVIDER env variable"""
    provider_type = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider_type == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if key and key != "your_gemini_api_key_here":
            return GeminiProvider()
        else:
            return MockOfflineProvider()
    elif provider_type == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if key and key != "your_openai_api_key_here":
            return OpenAIProvider()
        else:
            return MockOfflineProvider()
    elif provider_type == "groq":
        key = os.getenv("GROQ_API_KEY")
        if key and key != "your_groq_api_key_here":
            return GroqProvider()
        else:
            return MockOfflineProvider()
    elif provider_type == "mock":
        return MockOfflineProvider()
    else:
        return MockOfflineProvider()
