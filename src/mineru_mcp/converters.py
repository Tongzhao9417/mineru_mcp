"""文件转换功能模块。"""

import json
from pathlib import Path
from typing import Any, Dict

import httpx

from . import config
from .api import MinerUClient
from .file_utils import parse_list_input


async def convert_file_url(
    client: MinerUClient,
    url: str,
    enable_ocr: bool = False,
    language: str = "ch",
    page_ranges: str | None = None,
    output_dir: str = "",
) -> Dict[str, Any]:
    """
    从URL转换文件到Markdown格式。支持单个或多个URL处理。
    """
    urls_to_process = None

    if isinstance(url, dict):
        urls_to_process = url
    elif isinstance(url, list) and len(url) > 0 and isinstance(url[0], dict):
        urls_to_process = url
    elif isinstance(url, str):
        if url.strip().startswith("[") and url.strip().endswith("]"):
            try:
                url_configs = json.loads(url)
                if not isinstance(url_configs, list):
                    raise ValueError("JSON URL配置必须是列表格式")
                urls_to_process = url_configs
            except json.JSONDecodeError:
                pass

    if urls_to_process is None:
        urls = parse_list_input(url)
        if not urls:
            raise ValueError("未提供有效的 URL")

        if len(urls) == 1:
            urls_to_process = {"url": urls[0], "is_ocr": enable_ocr}
        else:
            urls_to_process = [{"url": url_item, "is_ocr": enable_ocr} for url_item in urls]

    try:
        result_path = await client.process_file_to_markdown(
            lambda urls, o: client.submit_file_url_task(
                urls, o, language=language, page_ranges=page_ranges,
            ),
            urls_to_process,
            enable_ocr,
            output_dir,
        )
        return {"status": "success", "result_path": result_path}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def convert_file_path(
    client: MinerUClient,
    file_path: str,
    enable_ocr: bool = False,
    language: str = "ch",
    page_ranges: str | None = None,
    output_dir: str = "",
) -> Dict[str, Any]:
    """
    将本地文件转换为Markdown格式。支持单个或多个文件批量处理。
    """
    files_to_process = None

    if isinstance(file_path, dict):
        files_to_process = file_path
    elif (
        isinstance(file_path, list)
        and len(file_path) > 0
        and isinstance(file_path[0], dict)
    ):
        files_to_process = file_path
    elif isinstance(file_path, str):
        if file_path.strip().startswith("[") and file_path.strip().endswith("]"):
            try:
                file_configs = json.loads(file_path)
                if not isinstance(file_configs, list):
                    raise ValueError("JSON 文件配置必须是列表格式")
                files_to_process = file_configs
            except json.JSONDecodeError:
                pass

    if files_to_process is None:
        file_paths = parse_list_input(file_path)
        if not file_paths:
            raise ValueError("未提供有效的文件路径")

        if len(file_paths) == 1:
            files_to_process = {"path": file_paths[0], "is_ocr": enable_ocr}
        else:
            files_to_process = [{"path": path, "is_ocr": enable_ocr} for path in file_paths]

    try:
        result_path = await client.process_file_to_markdown(
            lambda files, o: client.submit_file_task(
                files, o, language=language, page_ranges=page_ranges,
            ),
            files_to_process,
            enable_ocr,
            output_dir,
        )
        return {"status": "success", "result_path": result_path}
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "params": {
                "file_path": file_path,
                "enable_ocr": enable_ocr,
                "language": language,
            },
        }


async def local_parse_file(
    file_path: str,
    parse_method: str = "auto",
) -> Dict[str, Any]:
    """
    根据环境变量设置使用本地API解析文件。
    """
    file_path = Path(file_path)

    if not file_path.exists():
        return {"status": "error", "error": f"文件不存在: {file_path}"}

    try:
        if config.USE_LOCAL_API:
            config.logger.debug(f"使用本地API: {config.LOCAL_MINERU_API_BASE}")
            return await _parse_file_local(
                file_path=str(file_path),
                parse_method=parse_method,
            )
        else:
            return {"status": "error", "error": "远程API未配置"}
    except Exception as e:
        config.logger.error(f"解析文件时出错: {str(e)}")
        return {"status": "error", "error": str(e)}


async def _parse_file_local(
    file_path: str,
    parse_method: str = "auto",
) -> Dict[str, Any]:
    """使用本地API解析文件。"""
    api_url = f"{config.LOCAL_MINERU_API_BASE}/file_parse"

    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    with open(file_path_obj, "rb") as f:
        file_data = f.read()

    config.logger.debug(f"发送本地API请求到: {api_url}")
    config.logger.debug(f"上传文件: {file_path_obj.name} (大小: {len(file_data)} 字节)")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            response = await client.post(
                api_url,
                files={"file": (file_path_obj.name, file_data)},
                data={"parse_method": parse_method},
            )

            if response.status_code != 200:
                error_text = response.text
                config.logger.error(
                    f"API返回错误状态码: {response.status_code}, 错误信息: {error_text}"
                )
                raise RuntimeError(f"API返回错误: {response.status_code}, {error_text}")

            result = response.json()

            config.logger.debug(f"本地API响应: {result}")

            if "error" in result:
                return {"status": "error", "error": result["error"]}

            return {"status": "success", "result": result}
    except httpx.HTTPError as e:
        error_msg = f"与本地API通信时出错: {str(e)}"
        config.logger.error(error_msg)
        raise RuntimeError(error_msg)
