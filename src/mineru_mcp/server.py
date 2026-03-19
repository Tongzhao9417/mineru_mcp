"""MinerU File转Markdown转换的FastMCP服务器实现。"""

import traceback
from pathlib import Path
from typing import Annotated, Any, Dict, Optional

from fastmcp import FastMCP
from pydantic import Field

from . import config
from .api import MinerUClient
from .converters import convert_file_path, convert_file_url, local_parse_file
from .file_utils import parse_list_input
from .language import get_language_list
from .result_processor import process_conversion_result


# 初始化 FastMCP 服务器
mcp = FastMCP(
    name="MinerU File to Markdown Conversion",
    instructions="""
    一个将文档转化工具，可以将文档转化成Markdown、Json等格式，支持多种文件格式，包括
    PDF、Word、PPT以及图片格式（JPG、PNG、JPEG）。

    系统工具:
    parse_documents: 解析文档（支持本地文件和URL，自动读取内容）
    get_ocr_languages: 获取OCR支持的语言列表
    """,
)


class ServerState:
    """服务器状态管理，替代模块级全局变量。"""

    def __init__(self):
        self.output_dir: str = config.DEFAULT_OUTPUT_DIR
        self._client: Optional[MinerUClient] = None

    def get_client(self) -> MinerUClient:
        """获取 MinerUClient 的单例实例。"""
        if self._client is None:
            self._client = MinerUClient()
        return self._client

    def set_output_dir(self, dir_path: str) -> str:
        """设置转换后文件的输出目录。"""
        self.output_dir = dir_path
        config.ensure_output_dir(self.output_dir)
        return self.output_dir

    async def cleanup(self):
        """清理资源。"""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as e:
                config.logger.error(f"清理客户端资源时出错: {str(e)}")
            finally:
                self._client = None
        config.logger.info("资源清理完成")


state = ServerState()


# 为 cli.py 保留的兼容接口
def set_output_dir(dir_path: str) -> str:
    return state.set_output_dir(dir_path)


@mcp.tool()
async def parse_documents(
    file_sources: Annotated[
        str,
        Field(
            description="""文件路径或URL，支持以下格式:
            - 单个路径或URL: "/path/to/file.pdf" 或 "https://example.com/document.pdf"
            - 多个路径或URL(逗号分隔): "/path/to/file1.pdf, /path/to/file2.pdf" 或
              "https://example.com/doc1.pdf, https://example.com/doc2.pdf"
            - 混合路径和URL: "/path/to/file.pdf, https://example.com/document.pdf"
            (支持pdf、ppt、pptx、doc、docx以及图片格式jpg、jpeg、png)"""
        ),
    ],
    enable_ocr: Annotated[bool, Field(description="启用OCR识别,默认False")] = False,
    language: Annotated[
        str, Field(description='文档语言，默认"ch"中文，可选"en"英文等')
    ] = "ch",
    page_ranges: Annotated[
        str | None,
        Field(
            description='指定页码范围，格式为逗号分隔的字符串。例如："2,4-6"：表示选取第2页、第4页至第6页；"2--2"：表示从第2页一直选取到倒数第二页。（远程API）,默认None'
        ),
    ] = None,
) -> Dict[str, Any]:
    """
    统一接口，将文件转换为Markdown格式。支持本地文件和URL，会根据USE_LOCAL_API配置自动选择合适的处理方式。
    """
    sources = parse_list_input(file_sources)
    if not sources:
        return {"status": "error", "error": "未提供有效的文件路径或URL"}

    sources = list(dict.fromkeys(sources))

    url_paths = []
    file_paths = []

    for source in sources:
        if source.lower().startswith(("http://", "https://")):
            url_paths.append(source)
        else:
            file_paths.append(source)

    results = []
    client = state.get_client()
    output_dir = state.output_dir

    if config.USE_LOCAL_API:
        results = await _handle_local_api(file_paths, enable_ocr)
    else:
        if url_paths:
            results.extend(
                await _handle_remote_urls(client, url_paths, enable_ocr, language, page_ranges, output_dir)
            )
        if file_paths:
            results.extend(
                await _handle_remote_files(client, file_paths, enable_ocr, language, page_ranges, output_dir)
            )

    if not results:
        return {"status": "error", "error": "未处理任何文件"}

    if len(results) == 1:
        result = results[0].copy()
        for key in ("filename", "source_path", "source_url"):
            result.pop(key, None)
        return result

    success_count = len([r for r in results if r.get("status") == "success"])
    error_count = len([r for r in results if r.get("status") == "error"])

    overall_status = "success"
    if success_count == 0:
        overall_status = "error"
    elif error_count > 0:
        overall_status = "partial_success"

    return {
        "status": overall_status,
        "results": results,
        "summary": {
            "total_files": len(results),
            "success_count": success_count,
            "error_count": error_count,
        },
    }


@mcp.tool()
async def get_ocr_languages() -> Dict[str, Any]:
    """获取 OCR 支持的语言列表。"""
    try:
        languages = get_language_list()
        return {"status": "success", "languages": languages}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _handle_local_api(file_paths, enable_ocr):
    """使用本地API处理文件。"""
    if not file_paths:
        return [
            {
                "status": "warning",
                "message": "在本地API模式下，无法处理URL，且未提供有效的本地文件路径",
            }
        ]

    config.logger.info(f"使用本地API处理 {len(file_paths)} 个文件")
    results = []

    for path in file_paths:
        try:
            if not Path(path).exists():
                results.append(
                    {
                        "filename": Path(path).name,
                        "source_path": path,
                        "status": "error",
                        "error_message": f"文件不存在: {path}",
                    }
                )
                continue

            result = await local_parse_file(
                file_path=path,
                parse_method="ocr" if enable_ocr else "txt",
            )

            result_with_filename = {
                "filename": Path(path).name,
                "source_path": path,
                **result,
            }
            results.append(result_with_filename)

        except Exception as e:
            config.logger.error(f"处理文件 {path} 时出现错误: {str(e)}")
            results.append(
                {
                    "filename": Path(path).name,
                    "source_path": path,
                    "status": "error",
                    "error_message": f"处理文件时出现异常: {str(e)}",
                }
            )

    return results


async def _handle_remote_urls(client, url_paths, enable_ocr, language, page_ranges, output_dir):
    """使用远程API处理URL。"""
    results = []
    config.logger.info(f"使用远程API处理 {len(url_paths)} 个文件URL")

    try:
        url_result = await convert_file_url(
            client=client,
            url=",".join(url_paths),
            enable_ocr=enable_ocr,
            language=language,
            page_ranges=page_ranges,
            output_dir=output_dir,
        )

        if url_result["status"] == "success":
            for url in url_paths:
                result_item = await process_conversion_result(
                    url_result, url, is_url=True
                )
                results.append(result_item)
        else:
            for url in url_paths:
                results.append(
                    {
                        "filename": url.split("/")[-1].split("?")[0],
                        "source_url": url,
                        "status": "error",
                        "error_message": url_result.get("error", "URL处理失败"),
                    }
                )

    except Exception as e:
        config.logger.error(f"处理URL时出现错误: {str(e)}")
        for url in url_paths:
            results.append(
                {
                    "filename": url.split("/")[-1].split("?")[0],
                    "source_url": url,
                    "status": "error",
                    "error_message": f"处理URL时出现异常: {str(e)}",
                }
            )

    return results


async def _handle_remote_files(client, file_paths, enable_ocr, language, page_ranges, output_dir):
    """使用远程API处理本地文件。"""
    results = []
    config.logger.info(f"使用远程API处理 {len(file_paths)} 个本地文件")

    existing_files = []
    for file_path in file_paths:
        if not Path(file_path).exists():
            results.append(
                {
                    "filename": Path(file_path).name,
                    "source_path": file_path,
                    "status": "error",
                    "error_message": f"文件不存在: {file_path}",
                }
            )
        else:
            existing_files.append(file_path)

    if existing_files:
        try:
            file_result = await convert_file_path(
                client=client,
                file_path=",".join(existing_files),
                enable_ocr=enable_ocr,
                language=language,
                page_ranges=page_ranges,
                output_dir=output_dir,
            )

            config.logger.debug(f"file_result: {file_result}")

            if file_result["status"] == "success":
                for file_path in existing_files:
                    result_item = await process_conversion_result(
                        file_result, file_path, is_url=False
                    )
                    results.append(result_item)
            else:
                for file_path in existing_files:
                    results.append(
                        {
                            "filename": Path(file_path).name,
                            "source_path": file_path,
                            "status": "error",
                            "error_message": file_result.get("error", "文件处理失败"),
                        }
                    )

        except Exception as e:
            config.logger.error(f"处理本地文件时出现错误: {str(e)}")
            for file_path in existing_files:
                results.append(
                    {
                        "filename": Path(file_path).name,
                        "source_path": file_path,
                        "status": "error",
                        "error_message": f"处理文件时出现异常: {str(e)}",
                    }
                )

    return results


def run_server(mode=None, port=8001, host="127.0.0.1"):
    """运行 FastMCP 服务器。

    Args:
        mode: 运行模式，支持stdio、sse、streamable-http
        port: 服务器端口，默认为8001，仅在HTTP模式下有效
        host: 服务器主机地址，默认为127.0.0.1，仅在HTTP模式下有效
    """
    config.ensure_output_dir(state.output_dir)

    if not config.MINERU_API_KEY:
        config.logger.warning("警告: MINERU_API_KEY 环境变量未设置。")
        config.logger.warning("使用以下命令设置: export MINERU_API_KEY=your_api_key")

    transport = mode or "stdio"

    try:
        if transport in ("sse", "streamable-http"):
            config.logger.info(f"启动{transport}服务器: {host}:{port}")
            mcp.run(transport=transport, host=host, port=port)
        else:
            config.logger.info("启动STDIO服务器")
            mcp.run(transport="stdio")
    except Exception as e:
        config.logger.error(f"\n❌ 服务异常退出: {str(e)}")
        traceback.print_exc()
