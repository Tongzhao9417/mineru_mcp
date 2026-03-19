"""转换结果处理模块。"""

from pathlib import Path
from typing import Any, Dict

from . import config
from .file_utils import find_and_read_markdown_content


async def process_conversion_result(
    result: Dict[str, Any], source: str, is_url: bool = False
) -> Dict[str, Any]:
    """
    处理转换结果，统一格式化输出。

    Args:
        result: 转换函数返回的结果
        source: 源文件路径或URL
        is_url: 是否为URL

    Returns:
        格式化后的结果字典
    """
    filename = source.split("/")[-1]
    if is_url and "?" in filename:
        filename = filename.split("?")[0]
    elif not is_url:
        filename = Path(source).name

    base_result = {
        "filename": filename,
        "source_url" if is_url else "source_path": source,
    }

    if result["status"] == "success":
        result_path = result.get("result_path")

        config.logger.debug(f"处理结果 result_path 类型: {type(result_path)}")

        if result_path:
            if isinstance(result_path, dict) and "results" in result_path:
                return await _process_batch_result(result_path, base_result, source, filename, is_url)
            elif isinstance(result_path, str):
                return await _process_string_result(result_path, base_result)
            elif isinstance(result_path, dict):
                return await _process_dict_result(result_path, base_result)
            else:
                base_result.update(
                    {
                        "status": "error",
                        "error_message": f"无法识别的result_path类型: {type(result_path)}",
                    }
                )
        else:
            base_result.update(
                {"status": "error", "error_message": "转换成功但未返回结果路径"}
            )
    else:
        base_result.update(
            {"status": "error", "error_message": result.get("error", "未知错误")}
        )

    return base_result


async def _process_batch_result(
    result_path: Dict, base_result: Dict, source: str, filename: str, is_url: bool
) -> Dict[str, Any]:
    """处理批量处理结果格式。"""
    config.logger.debug("检测到批量处理结果格式")

    for item in result_path.get("results", []):
        if item.get("filename") == filename or (
            not is_url and Path(source).name == item.get("filename")
        ):
            if item.get("status") == "success" and "content" in item:
                base_result.update(
                    {
                        "status": "success",
                        "content": item.get("content", ""),
                    }
                )
                if "extract_path" in item:
                    base_result["extract_path"] = item["extract_path"]
                return base_result
            elif item.get("status") == "error":
                base_result.update(
                    {
                        "status": "error",
                        "error_message": item.get("error_message", "文件处理失败"),
                    }
                )
                return base_result

    if "extract_dir" in result_path:
        config.logger.debug(f"尝试从extract_dir读取: {result_path['extract_dir']}")
        try:
            content_result = await find_and_read_markdown_content(
                result_path["extract_dir"]
            )
            if content_result.get("status") == "success":
                base_result.update(
                    {
                        "status": "success",
                        "content": content_result.get("content", ""),
                        "extract_path": result_path["extract_dir"],
                    }
                )
                return base_result
        except Exception as e:
            config.logger.error(f"从extract_dir读取内容时出错: {str(e)}")

    base_result.update(
        {
            "status": "error",
            "error_message": "未能在批量处理结果中找到匹配的内容",
        }
    )
    return base_result


async def _process_string_result(result_path: str, base_result: Dict) -> Dict[str, Any]:
    """处理传统字符串格式结果路径。"""
    config.logger.debug(f"处理传统格式结果路径: {result_path}")
    content_result = await find_and_read_markdown_content(result_path)
    if content_result.get("status") == "success":
        base_result.update(
            {
                "status": "success",
                "content": content_result.get("content", ""),
                "extract_path": result_path,
            }
        )
    else:
        base_result.update(
            {
                "status": "error",
                "error_message": f"无法读取转换结果: {content_result.get('message', '')}",
            }
        )
    return base_result


async def _process_dict_result(result_path: Dict, base_result: Dict) -> Dict[str, Any]:
    """处理其他字典格式结果路径。"""
    config.logger.debug(f"处理其他字典格式: {result_path}")
    extract_path = (
        result_path.get("extract_dir")
        or result_path.get("path")
        or result_path.get("dir")
    )
    if extract_path and isinstance(extract_path, str):
        try:
            content_result = await find_and_read_markdown_content(extract_path)
            if content_result.get("status") == "success":
                base_result.update(
                    {
                        "status": "success",
                        "content": content_result.get("content", ""),
                        "extract_path": extract_path,
                    }
                )
                return base_result
        except Exception as e:
            config.logger.error(f"从extract_path读取内容时出错: {str(e)}")

    base_result.update(
        {"status": "error", "error_message": "转换结果格式无法识别"}
    )
    return base_result
