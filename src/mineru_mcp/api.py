"""MinerU File转Markdown转换的API客户端。"""

import asyncio
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

from . import config


class MinerUClient:
    """
    用于与 MinerU API 交互以将 File 转换为 Markdown 的客户端。
    """

    def __init__(self, api_base: Optional[str] = None, api_key: Optional[str] = None):
        """
        初始化 MinerU API 客户端。

        Args:
            api_base: MinerU API 的基础 URL (默认: 从环境变量获取)
            api_key: 用于向 MinerU 进行身份验证的 API 密钥 (默认: 从环境变量获取)
        """
        self.api_base = api_base or config.MINERU_API_BASE
        self.api_key = api_key or config.MINERU_API_KEY

        if not self.api_key:
            raise ValueError(
                "错误: MinerU API 密钥 (MINERU_API_KEY) 未设置或为空。\n"
                "请确保已设置 MINERU_API_KEY 环境变量，例如:\n"
                "  export MINERU_API_KEY='your_actual_api_key'\n"
                "或者，在项目根目录的 `.env` 文件中定义该变量。"
            )

        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx.AsyncClient 实例。"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
        return self._http_client

    async def close(self):
        """关闭 HTTP 客户端。"""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        向 MinerU API 发出请求。

        Args:
            method: HTTP 方法 (GET, POST 等)
            endpoint: API 端点路径 (不含基础 URL)
            **kwargs: 传递给 httpx 请求的其他参数

        Returns:
            dict: API 响应 (JSON 格式)
        """
        url = f"{self.api_base}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        if "headers" in kwargs:
            kwargs["headers"].update(headers)
        else:
            kwargs["headers"] = headers

        config.logger.debug(f"API请求: {method} {url}")

        client = await self._get_http_client()
        response = await client.request(method, url, **kwargs)
        response.raise_for_status()
        response_json = response.json()

        config.logger.debug(f"API响应: {response_json}")

        return response_json

    async def submit_file_url_task(
        self,
        urls: Union[str, List[Union[str, Dict[str, Any]]], Dict[str, Any]],
        enable_ocr: bool = True,
        language: str = "ch",
        page_ranges: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        提交 File URL 以转换为 Markdown。支持单个URL或多个URL批量处理。
        """
        url_count = 1
        if isinstance(urls, list):
            url_count = len(urls)
        config.logger.debug(
            f"调用submit_file_url_task: {url_count}个URL, "
            + f"ocr={enable_ocr}, "
            + f"language={language}"
        )

        urls_config = []

        if isinstance(urls, str):
            urls_config.append(
                {"url": urls, "is_ocr": enable_ocr, "page_ranges": page_ranges}
            )
        elif isinstance(urls, list):
            for url_item in urls:
                if isinstance(url_item, str):
                    urls_config.append(
                        {
                            "url": url_item,
                            "is_ocr": enable_ocr,
                            "page_ranges": page_ranges,
                        }
                    )
                elif isinstance(url_item, dict):
                    if "url" not in url_item:
                        raise ValueError(f"URL配置必须包含 'url' 字段: {url_item}")
                    url_is_ocr = url_item.get("is_ocr", enable_ocr)
                    url_page_ranges = url_item.get("page_ranges", page_ranges)
                    url_config = {"url": url_item["url"], "is_ocr": url_is_ocr}
                    if url_page_ranges is not None:
                        url_config["page_ranges"] = url_page_ranges
                    urls_config.append(url_config)
                else:
                    raise TypeError(f"不支持的URL配置类型: {type(url_item)}")
        elif isinstance(urls, dict):
            if "url" not in urls:
                raise ValueError(f"URL配置必须包含 'url' 字段: {urls}")
            url_is_ocr = urls.get("is_ocr", enable_ocr)
            url_page_ranges = urls.get("page_ranges", page_ranges)
            url_config = {"url": urls["url"], "is_ocr": url_is_ocr}
            if url_page_ranges is not None:
                url_config["page_ranges"] = url_page_ranges
            urls_config.append(url_config)
        else:
            raise TypeError(f"urls 必须是字符串、列表或字典，而不是 {type(urls)}")

        payload = {
            "language": language,
            "files": urls_config,
        }

        response = await self._request(
            "POST", "/api/v4/extract/task/batch", json=payload
        )

        if "data" not in response or "batch_id" not in response["data"]:
            raise ValueError(f"提交批量URL任务失败: {response}")

        batch_id = response["data"]["batch_id"]

        config.logger.info(f"开始处理 {len(urls_config)} 个文件URL")
        config.logger.debug(f"批量URL任务提交成功，批次ID: {batch_id}")

        result = {
            "data": {
                "batch_id": batch_id,
                "uploaded_files": [url_config.get("url") for url_config in urls_config],
            }
        }

        if len(urls_config) == 1:
            url = urls_config[0]["url"]
            file_name = url.split("/")[-1]
            result["data"]["file_name"] = file_name

        return result

    async def submit_file_task(
        self,
        files: Union[str, List[Union[str, Dict[str, Any]]], Dict[str, Any]],
        enable_ocr: bool = True,
        language: str = "ch",
        page_ranges: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        提交本地 File 文件以转换为 Markdown。支持单个文件路径或多个文件配置。
        """
        file_count = 1
        if isinstance(files, list):
            file_count = len(files)
        config.logger.debug(
            f"调用submit_file_task: {file_count}个文件, "
            + f"ocr={enable_ocr}, "
            + f"language={language}"
        )

        files_config = self._normalize_files_input(files, enable_ocr, page_ranges)

        # 构建API请求payload
        files_payload = []
        for file_config in files_config:
            file_payload = {
                "name": file_config["name"],
                "is_ocr": file_config["is_ocr"],
            }
            if "page_ranges" in file_config and file_config["page_ranges"] is not None:
                file_payload["page_ranges"] = file_config["page_ranges"]
            files_payload.append(file_payload)

        payload = {
            "language": language,
            "files": files_payload,
        }

        # 获取文件上传URL
        response = await self._request("POST", "/api/v4/file-urls/batch", json=payload)

        if (
            "data" not in response
            or "batch_id" not in response["data"]
            or "file_urls" not in response["data"]
        ):
            raise ValueError(f"获取上传URL失败: {response}")

        batch_id = response["data"]["batch_id"]
        file_urls = response["data"]["file_urls"]

        if len(file_urls) != len(files_config):
            raise ValueError(
                f"上传URL数量 ({len(file_urls)}) 与文件数量 ({len(files_config)}) 不匹配"
            )

        config.logger.info(f"开始上传 {len(file_urls)} 个本地文件")
        config.logger.debug(f"获取上传URL成功，批次ID: {batch_id}")

        # 上传所有文件
        uploaded_files = []
        client = await self._get_http_client()

        for file_config, upload_url in zip(files_config, file_urls):
            file_path = file_config["path"]
            if file_path is None:
                raise ValueError(f"文件 {file_config['name']} 没有有效的路径")

            try:
                with open(file_path, "rb") as f:
                    response = await client.put(upload_url, content=f.read())

                    if response.status_code != 200:
                        raise ValueError(
                            f"文件上传失败，状态码: {response.status_code}, 响应: {response.text}"
                        )

                    config.logger.debug(f"文件 {file_path.name} 上传成功")
                    uploaded_files.append(file_path.name)
            except Exception as e:
                raise ValueError(f"文件 {file_path.name} 上传失败: {str(e)}")

        config.logger.info(f"文件上传完成，共 {len(uploaded_files)} 个文件")

        result = {"data": {"batch_id": batch_id, "uploaded_files": uploaded_files}}

        if len(uploaded_files) == 1:
            result["data"]["file_name"] = uploaded_files[0]

        return result

    def _normalize_files_input(
        self,
        files: Union[str, List[Union[str, Dict[str, Any]]], Dict[str, Any]],
        enable_ocr: bool,
        page_ranges: Optional[str],
    ) -> List[Dict[str, Any]]:
        """将各种文件输入格式标准化为文件配置列表。"""
        files_config = []

        if isinstance(files, str):
            file_path = Path(files)
            if not file_path.exists():
                raise FileNotFoundError(f"未找到 File 文件: {file_path}")
            files_config.append(
                {"path": file_path, "name": file_path.name, "is_ocr": enable_ocr, "page_ranges": page_ranges}
            )
        elif isinstance(files, list):
            for file_item in files:
                if isinstance(file_item, str):
                    file_path = Path(file_item)
                    if not file_path.exists():
                        raise FileNotFoundError(f"未找到 File 文件: {file_path}")
                    files_config.append(
                        {"path": file_path, "name": file_path.name, "is_ocr": enable_ocr, "page_ranges": page_ranges}
                    )
                elif isinstance(file_item, dict):
                    if "path" not in file_item and "name" not in file_item:
                        raise ValueError(f"文件配置必须包含 'path' 或 'name' 字段: {file_item}")
                    if "path" in file_item:
                        file_path = Path(file_item["path"])
                        if not file_path.exists():
                            raise FileNotFoundError(f"未找到 File 文件: {file_path}")
                        file_name = file_path.name
                    else:
                        file_name = file_item["name"]
                        file_path = None
                    file_config = {
                        "path": file_path,
                        "name": file_name,
                        "is_ocr": file_item.get("is_ocr", enable_ocr),
                    }
                    file_page_ranges = file_item.get("page_ranges", page_ranges)
                    if file_page_ranges is not None:
                        file_config["page_ranges"] = file_page_ranges
                    files_config.append(file_config)
                else:
                    raise TypeError(f"不支持的文件配置类型: {type(file_item)}")
        elif isinstance(files, dict):
            if "path" not in files and "name" not in files:
                raise ValueError(f"文件配置必须包含 'path' 或 'name' 字段: {files}")
            if "path" in files:
                file_path = Path(files["path"])
                if not file_path.exists():
                    raise FileNotFoundError(f"未找到 File 文件: {file_path}")
                file_name = file_path.name
            else:
                file_name = files["name"]
                file_path = None
            file_config = {
                "path": file_path,
                "name": file_name,
                "is_ocr": files.get("is_ocr", enable_ocr),
            }
            file_page_ranges = files.get("page_ranges", page_ranges)
            if file_page_ranges is not None:
                file_config["page_ranges"] = file_page_ranges
            files_config.append(file_config)
        else:
            raise TypeError(f"files 必须是字符串、列表或字典，而不是 {type(files)}")

        return files_config

    async def get_batch_task_status(self, batch_id: str) -> Dict[str, Any]:
        """获取批量转换任务的状态。"""
        return await self._request(
            "GET", f"/api/v4/extract-results/batch/{batch_id}"
        )

    async def process_file_to_markdown(
        self,
        task_fn,
        task_arg: Union[str, List[Dict[str, Any]], Dict[str, Any]],
        enable_ocr: bool = True,
        output_dir: Optional[str] = None,
        max_retries: int = 180,
        retry_interval: int = 10,
    ) -> Union[str, Dict[str, Any]]:
        """
        从开始到结束处理 File 到 Markdown 的转换。

        Args:
            task_fn: 提交任务的函数 (submit_file_url_task 或 submit_file_task)
            task_arg: 任务函数的参数
            enable_ocr: 是否启用 OCR
            output_dir: 结果的输出目录
            max_retries: 最大状态检查重试次数
            retry_interval: 状态检查之间的时间间隔 (秒)

        Returns:
            Union[str, Dict[str, Any]]: 单文件返回目录路径，多文件返回结果字典
        """
        try:
            task_info = await task_fn(task_arg, enable_ocr)
            batch_id = task_info["data"]["batch_id"]

            uploaded_files = task_info["data"].get("uploaded_files", [])
            if not uploaded_files and "file_name" in task_info["data"]:
                uploaded_files = [task_info["data"]["file_name"]]

            if not uploaded_files:
                raise ValueError("无法获取上传文件的信息")

            config.logger.debug(f"批量任务提交成功。Batch ID: {batch_id}")

            files_status = {}
            files_download_urls = {}
            failed_files = {}

            output_path = config.ensure_output_dir(output_dir)

            for i in range(max_retries):
                status_info = await self.get_batch_task_status(batch_id)

                config.logger.debug(f"轮训结果：{status_info}")

                if (
                    "data" not in status_info
                    or "extract_result" not in status_info["data"]
                ):
                    config.logger.error(f"获取批量任务状态失败: {status_info}")
                    await asyncio.sleep(retry_interval)
                    continue

                has_progress = False

                for result in status_info["data"]["extract_result"]:
                    file_name = result.get("file_name")
                    if not file_name:
                        continue

                    if file_name not in files_status:
                        files_status[file_name] = "pending"

                    state = result.get("state")
                    files_status[file_name] = state

                    if state == "done":
                        full_zip_url = result.get("full_zip_url")
                        if full_zip_url:
                            files_download_urls[file_name] = full_zip_url
                            config.logger.info(f"文件 {file_name} 处理完成")
                        else:
                            config.logger.debug(
                                f"文件 {file_name} 标记为完成但没有下载链接"
                            )
                    elif state in ["failed", "error"]:
                        err_msg = result.get("err_msg", "未知错误")
                        failed_files[file_name] = err_msg
                        config.logger.warning(f"文件 {file_name} 处理失败: {err_msg}")
                    else:
                        if state == "running" and "extract_progress" in result:
                            has_progress = True
                            progress = result["extract_progress"]
                            extracted = progress.get("extracted_pages", 0)
                            total = progress.get("total_pages", 0)
                            if total > 0:
                                percent = (extracted / total) * 100
                                config.logger.info(
                                    f"处理进度: {file_name} "
                                    + f"{extracted}/{total} 页 "
                                    + f"({percent:.1f}%)"
                                )

                expected_file_count = len(uploaded_files)
                processed_file_count = len(files_status)
                completed_file_count = len(files_download_urls) + len(failed_files)

                if (
                    processed_file_count > 0
                    and processed_file_count >= expected_file_count
                    and completed_file_count >= processed_file_count
                ):
                    if files_download_urls or failed_files:
                        config.logger.info("文件处理完成")
                        if failed_files:
                            config.logger.warning(
                                f"有 {len(failed_files)} 个文件处理失败"
                            )
                        break

                if not has_progress:
                    config.logger.info(f"等待文件处理完成... ({i+1}/{max_retries})")

                await asyncio.sleep(retry_interval)
            else:
                if not files_download_urls and not failed_files:
                    raise TimeoutError(f"批量任务 {batch_id} 未在允许的时间内完成")
                else:
                    config.logger.warning(
                        "警告: 部分文件未在允许的时间内完成，继续处理已完成的文件"
                    )

            return await self._download_and_extract_results(
                files_download_urls, failed_files, output_path, batch_id
            )

        except Exception as e:
            config.logger.error(f"处理 File 到 Markdown 失败: {str(e)}")
            raise

    async def _download_and_extract_results(
        self,
        files_download_urls: Dict[str, str],
        failed_files: Dict[str, str],
        output_path: Path,
        batch_id: str,
    ) -> Dict[str, Any]:
        """下载并解压处理结果。"""
        extract_dir = output_path / batch_id
        extract_dir.mkdir(exist_ok=True)

        results = []
        client = await self._get_http_client()

        for file_name, download_url in files_download_urls.items():
            try:
                config.logger.debug(f"下载文件处理结果: {file_name}")

                zip_file_name = download_url.split("/")[-1]
                zip_dir_name = os.path.splitext(zip_file_name)[0]

                file_extract_dir = extract_dir / zip_dir_name
                file_extract_dir.mkdir(exist_ok=True)

                zip_path = output_path / f"{batch_id}_{zip_file_name}"

                response = await client.get(
                    download_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                with open(zip_path, "wb") as f:
                    f.write(response.content)

                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(file_extract_dir)

                zip_path.unlink()

                markdown_content = ""
                markdown_files = list(file_extract_dir.glob("*.md"))
                if markdown_files:
                    with open(markdown_files[0], "r", encoding="utf-8") as f:
                        markdown_content = f.read()

                results.append(
                    {
                        "filename": file_name,
                        "status": "success",
                        "content": markdown_content,
                        "extract_path": str(file_extract_dir),
                    }
                )

                config.logger.debug(
                    f"文件 {file_name} 的结果已解压到: {file_extract_dir}"
                )

            except Exception as e:
                error_msg = f"下载结果失败: {str(e)}"
                config.logger.error(f"文件 {file_name} {error_msg}")
                results.append(
                    {
                        "filename": file_name,
                        "status": "error",
                        "error_message": error_msg,
                    }
                )

        for file_name, error_msg in failed_files.items():
            results.append(
                {
                    "filename": file_name,
                    "status": "error",
                    "error_message": f"处理失败: {error_msg}",
                }
            )

        success_count = len(files_download_urls)
        fail_count = len(failed_files)
        total_count = success_count + fail_count

        config.logger.info(f"文件处理结果统计: 总计{total_count}, 成功{success_count}, 失败{fail_count}")

        return {
            "results": results,
            "extract_dir": str(extract_dir),
            "success_count": success_count,
            "fail_count": fail_count,
            "total_count": total_count,
        }
