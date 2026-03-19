"""server 模块的单元测试。"""

import asyncio

import pytest

from mineru_mcp.server import mcp


class TestMCPServerSetup:
    """验证 FastMCP 实例配置正确。"""

    def test_mcp_instance_name(self):
        assert mcp.name == "MinerU File to Markdown Conversion"

    def test_mcp_has_tools(self):
        """验证 MCP 实例注册了正确的工具。"""
        tools = asyncio.run(mcp.list_tools())
        tool_names = [tool.name for tool in tools]
        assert "parse_documents" in tool_names
        assert "get_ocr_languages" in tool_names

    def test_mcp_tool_count(self):
        """验证工具数量正确。"""
        tools = asyncio.run(mcp.list_tools())
        assert len(tools) == 2
