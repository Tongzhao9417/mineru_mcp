"""file_utils 模块的单元测试。"""

import pytest
from mineru_mcp.file_utils import parse_list_input


class TestParseListInput:
    """parse_list_input 函数的测试。"""

    def test_empty_string(self):
        assert parse_list_input("") == []

    def test_single_item(self):
        assert parse_list_input("/path/to/file.pdf") == ["/path/to/file.pdf"]

    def test_comma_separated(self):
        result = parse_list_input("/path/a.pdf, /path/b.pdf")
        assert result == ["/path/a.pdf", "/path/b.pdf"]

    def test_newline_separated(self):
        result = parse_list_input("/path/a.pdf\n/path/b.pdf")
        assert result == ["/path/a.pdf", "/path/b.pdf"]

    def test_space_separated(self):
        result = parse_list_input("/path/a.pdf /path/b.pdf")
        assert result == ["/path/a.pdf", "/path/b.pdf"]

    def test_quoted_items(self):
        result = parse_list_input('"file1.pdf","file2.pdf"')
        assert result == ["file1.pdf", "file2.pdf"]

    def test_single_quoted_items(self):
        result = parse_list_input("'file1.pdf','file2.pdf'")
        assert result == ["file1.pdf", "file2.pdf"]

    def test_mixed_separators(self):
        result = parse_list_input("a.pdf, b.pdf\nc.pdf")
        assert result == ["a.pdf", "b.pdf", "c.pdf"]

    def test_strips_whitespace(self):
        result = parse_list_input("  file.pdf  ")
        assert result == ["file.pdf"]

    def test_removes_empty_items(self):
        result = parse_list_input("a.pdf,,b.pdf")
        assert result == ["a.pdf", "b.pdf"]
