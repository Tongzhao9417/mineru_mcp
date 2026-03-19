"""文件操作工具函数。"""

import re
from pathlib import Path
from typing import Any, Dict, List

from . import config


def parse_list_input(input_str: str) -> List[str]:
    """
    解析可能包含由逗号或换行符分隔的多个项目的字符串输入。

    Args:
        input_str: 可能包含多个项目的字符串

    Returns:
        解析出的项目列表
    """
    if not input_str:
        return []

    items = re.split(r"[,\n\s]+", input_str)

    result = []
    for item in items:
        item = item.strip()
        if (item.startswith('"') and item.endswith('"')) or (
            item.startswith("'") and item.endswith("'")
        ):
            item = item[1:-1]

        if item:
            result.append(item)

    return result


async def read_converted_file(file_path: str) -> Dict[str, Any]:
    """
    读取解析后的文件内容。主要支持Markdown和其他文本文件格式。
    """
    try:
        target_file = Path(file_path)
        parent_dir = target_file.parent
        suffix = target_file.suffix.lower()

        text_extensions = [".md", ".txt", ".json", ".html", ".tex", ".latex"]

        if suffix not in text_extensions:
            return {
                "status": "error",
                "error": f"不支持的文件格式: {suffix}。目前仅支持以下格式: {', '.join(text_extensions)}",
            }

        if not target_file.exists():
            if not parent_dir.exists():
                return {"status": "error", "error": f"目录 {parent_dir} 不存在"}

            similar_files_paths = [
                str(f) for f in parent_dir.rglob(f"*{suffix}") if f.is_file()
            ]

            if similar_files_paths:
                if len(similar_files_paths) == 1:
                    alternative_file = similar_files_paths[0]
                    try:
                        with open(alternative_file, "r", encoding="utf-8") as f:
                            content = f.read()
                        return {
                            "status": "success",
                            "content": content,
                            "message": f"未找到文件 {target_file.name}，但找到了 {Path(alternative_file).name}，已返回其内容",
                        }
                    except Exception as e:
                        return {
                            "status": "error",
                            "error": f"尝试读取替代文件时出错: {str(e)}",
                        }
                else:
                    suggestion = f"你是否在找: {', '.join(similar_files_paths)}?"
                    return {
                        "status": "error",
                        "error": f"文件 {target_file.name} 不存在。在 {parent_dir} 及其子目录下找到以下同类型文件。{suggestion}",
                    }
            else:
                return {
                    "status": "error",
                    "error": f"文件 {target_file.name} 不存在，且在目录 {parent_dir} 及其子目录下未找到其他 {suffix} 文件。",
                }

        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()
        return {"status": "success", "content": content}

    except Exception as e:
        config.logger.error(f"读取文件时出错: {str(e)}")
        return {"status": "error", "error": str(e)}


async def find_and_read_markdown_content(result_path: str) -> Dict[str, Any]:
    """
    在给定的路径中寻找并读取Markdown文件内容。
    """
    if not result_path:
        return {"status": "warning", "message": "未提供有效的结果路径"}

    base_path = Path(result_path)
    if not base_path.exists():
        return {"status": "warning", "message": f"结果路径不存在: {result_path}"}

    unique_files = set()

    common_files = [
        base_path / "full.md",
        base_path / "full.txt",
        base_path / "output.md",
        base_path / "result.md",
    ]
    for f in common_files:
        if f.exists():
            unique_files.add(str(f))

    for subdir in base_path.iterdir():
        if subdir.is_dir():
            subdir_files = [
                subdir / "full.md",
                subdir / "full.txt",
                subdir / "output.md",
                subdir / "result.md",
            ]
            for f in subdir_files:
                if f.exists():
                    unique_files.add(str(f))

    for md_file in base_path.glob("**/*.md"):
        unique_files.add(str(md_file))
    for txt_file in base_path.glob("**/*.txt"):
        unique_files.add(str(txt_file))

    possible_files = [Path(f) for f in unique_files]

    config.logger.debug(f"找到 {len(possible_files)} 个可能的文件")

    found_contents = []

    for file_path in possible_files:
        if file_path.exists():
            result = await read_converted_file(str(file_path))
            if result["status"] == "success":
                config.logger.debug(f"成功读取文件内容: {file_path}")
                found_contents.append(
                    {"file_path": str(file_path), "content": result["content"]}
                )

    if found_contents:
        config.logger.debug(f"在结果目录中找到了 {len(found_contents)} 个可读取的文件")
        if len(found_contents) == 1:
            return {
                "status": "success",
                "content": found_contents[0]["content"],
                "file_path": found_contents[0]["file_path"],
            }
        else:
            return {"status": "success", "contents": found_contents}

    return {
        "status": "warning",
        "message": f"无法在结果目录中找到可读取的Markdown文件: {result_path}",
    }
