"""
🧪 KIỂM THỬ TOOL & KIỂM SOÁT TRUY CẬP (chạy offline, không tốn quota LLM)
Chạy: python -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from tools import dispatch_tool_call
from mcp_server import MCPLibraryServer
from providers import is_daily_quota_error


def search(keyword: str) -> dict:
    return json.loads(dispatch_tool_call("search_book", {"keyword": keyword}))


class TestSearchBook(unittest.TestCase):
    def assertFinds(self, keyword: str, book_id: str):
        result = search(keyword)
        self.assertEqual(result["status"], "SUCCESS", keyword)
        self.assertIn(book_id, [b["book_id"] for b in result["results"]], keyword)

    def test_by_book_id(self):
        self.assertFinds("B001", "B001")
        self.assertFinds("b001", "B001")
        self.assertFinds("sách có mã B001 còn không", "B001")

    def test_by_title_and_author(self):
        self.assertFinds("Nhập môn Học máy", "B001")
        self.assertFinds("hoc may", "B001")
        self.assertFinds("Tô Hoài", "B007")

    def test_extra_words_in_query(self):
        self.assertFinds("sách Nhập môn Học máy", "B001")
        self.assertFinds("sách Nhập môn Học máy còn hàng không", "B001")
        self.assertFinds("Học máy Nguyễn Văn Hùng", "B001")

    def test_not_found(self):
        self.assertEqual(search("B999")["status"], "NOT_FOUND")
        self.assertEqual(search("xyz")["status"], "NOT_FOUND")
        self.assertEqual(search("sách")["status"], "NOT_FOUND")


class TestAccessControl(unittest.TestCase):
    def test_cannot_read_other_student_record(self):
        result = MCPLibraryServer().call_tool("get_borrow_record", {"student_id": "21010245"}, caller_id="21010123")
        self.assertEqual(result["result"]["status"], "PERMISSION_DENIED")

    def test_own_record_allowed(self):
        result = MCPLibraryServer().call_tool("get_borrow_record", {}, caller_id="21010123")
        self.assertEqual(result["result"]["status"], "SUCCESS")


class TestQuotaError(unittest.TestCase):
    def test_daily_vs_minute_quota(self):
        self.assertTrue(is_daily_quota_error("429 ... 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'"))
        self.assertFalse(is_daily_quota_error("429 ... 'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'"))


if __name__ == "__main__":
    unittest.main()
