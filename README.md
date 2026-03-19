# MinerU MCP Server

基于 [FastMCP 3.x](https://gofastmcp.com) 的 MCP 服务器，将 [MinerU](https://mineru.net) 的文档转 Markdown API 暴露为 MCP 工具。

支持 PDF、Word、PPT 及图片格式（JPG、PNG）的解析。

## 工具

| 工具 | 说明 |
|------|------|
| `parse_documents` | 将文件转换为 Markdown（支持本地路径和 URL，可批量处理） |
| `get_ocr_languages` | 获取 OCR 支持的语言列表 |

## 安装

```bash
pip install mineru-mcp
```

从源码安装：

```bash
git clone https://github.com/Tongzhao9417/mineru_mcp.git
cd mineru_mcp
pip install -e .
```

核心依赖仅 3 个：`fastmcp>=3.0.0`、`python-dotenv>=1.0.0`、`httpx>=0.24.0`

## 环境变量

在项目根目录创建 `.env` 文件（参考 `.env.example`），或直接设置环境变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MINERU_API_KEY` | MinerU API 密钥（[官网申请](https://mineru.net)） | 必填 |
| `MINERU_API_BASE` | 远程 API 基础 URL | `https://mineru.net` |
| `OUTPUT_DIR` | 转换结果保存路径 | `./downloads` |
| `USE_LOCAL_API` | 是否使用本地 API | `false` |
| `LOCAL_MINERU_API_BASE` | 本地 API 地址（`USE_LOCAL_API=true` 时生效） | `http://localhost:8080` |

## MCP 客户端配置

### Claude Code / Claude Desktop

```json
{
  "mcpServers": {
    "mineru-mcp": {
      "command": "mineru-mcp",
      "env": {
        "MINERU_API_KEY": "your-api-key"
      }
    }
  }
}
```

### 从源码运行

```json
{
  "mcpServers": {
    "mineru-mcp": {
      "command": "uv",
      "args": ["--directory", "/path/to/mineru_mcp", "run", "mineru-mcp"],
      "env": {
        "MINERU_API_KEY": "your-api-key"
      }
    }
  }
}
```

## 直接运行

```bash
# stdio 模式（默认，MCP 客户端自动管理）
mineru-mcp

# HTTP 模式（独立服务，多客户端可连接）
mineru-mcp --transport streamable-http --port 8001
```

> 推荐使用 `streamable-http` 传输模式（MCP 规范推荐），SSE 已被标记为 deprecated。

## parse_documents 参数

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `file_sources` | string | 文件路径或 URL，多个用逗号分隔 | 必填 |
| `enable_ocr` | bool | 启用 OCR | `false` |
| `language` | string | 文档语言（`ch`/`en` 等） | `ch` |
| `page_ranges` | string | 页码范围，如 `"2,4-6"`（仅远程 API） | `None` |

## 常见问题

**API 返回 401**：检查 `MINERU_API_KEY` 是否正确设置。

**找不到文件**：请使用绝对路径。

**调用超时**：大文档处理耗时较长，建议分批处理或使用本地 API 模式。

## License

MIT
