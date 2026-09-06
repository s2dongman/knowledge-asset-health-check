from __future__ import annotations

import os
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .analyzers import AnalysisInput, analyze_documents
from .models import FileRecord, KnowledgeBasePlan
from .parsers import parse_document
from .planner import plan_knowledge_bases


SUPPORTED_DOCUMENTS = {
    ".docx": "Word",
    ".pdf": "PDF",
    ".xlsx": "Excel",
    ".pptx": "PPT",
    ".txt": "文本",
    ".md": "文本",
}

LEGACY_DOCUMENTS = {
    ".doc": "Word（旧格式）",
    ".xls": "Excel（旧格式）",
    ".ppt": "PPT（旧格式）",
}

OTHER_BUSINESS_FILES = {
    ".csv": "表格数据",
    ".rtf": "富文本",
    ".odt": "开放文档",
    ".ods": "开放表格",
    ".odp": "开放演示文稿",
}

IGNORED_NAMES = {"thumbs.db", ".ds_store", "desktop.ini"}
IGNORED_PREFIXES = ("~$", ".~lock.")
IGNORED_DIRECTORIES = {"$recycle.bin", "system volume information", "__pycache__"}


@dataclass
class ScanResult:
    root: Path
    records: list[FileRecord]
    skipped_system_files: int
    access_errors: list[str]
    knowledge_base_plans: list[KnowledgeBasePlan]

    @property
    def total_files(self) -> int:
        return len(self.records)

    @property
    def total_size_bytes(self) -> int:
        return sum(record.size_bytes for record in self.records)

    def category_counts(self) -> dict[str, int]:
        return dict(Counter(record.category for record in self.records))

    def type_counts(self) -> dict[str, int]:
        return dict(Counter(record.display_type for record in self.records))


def classify_file(path: Path) -> tuple[str, str, str]:
    extension = path.suffix.lower()
    if extension in SUPPORTED_DOCUMENTS:
        return "首批支持文档", SUPPORTED_DOCUMENTS[extension], ""
    if extension in LEGACY_DOCUMENTS:
        return "待转换文档", LEGACY_DOCUMENTS[extension], "建议转换为常用格式"
    if extension in OTHER_BUSINESS_FILES:
        return "其他业务文件", OTHER_BUSINESS_FILES[extension], "第一版暂不读取正文"
    if not extension:
        return "其他文件", "无扩展名文件", "需要人工确认文件类型"
    return "其他文件", "其他", "第一版仅盘点，不读取正文"


def should_ignore(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered.startswith("."):
        return True
    if lowered in IGNORED_NAMES or lowered in IGNORED_DIRECTORIES:
        return True
    if lowered.startswith(IGNORED_PREFIXES):
        return True
    try:
        attributes = getattr(path.stat(), "st_file_attributes", 0)
    except OSError:
        attributes = 0
    hidden = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x2)
    system = getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 0x4)
    return bool(attributes & (hidden | system))


ProgressCallback = Callable[[str, int, int], None]


def scan_folder(
    folder: str | Path,
    *,
    parse_content: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> ScanResult:
    root = Path(folder).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"找不到待体检文件夹：{root}")
    if not root.is_dir():
        raise NotADirectoryError(f"请选择文件夹，而不是文件：{root}")

    records: list[FileRecord] = []
    analysis_inputs: list[AnalysisInput] = []
    access_errors: list[str] = []
    skipped_system_files = 0

    def on_walk_error(error: OSError) -> None:
        access_errors.append(str(error))

    file_paths: list[Path] = []
    for current_folder, directory_names, file_names in os.walk(root, onerror=on_walk_error, followlinks=False):
        visible_directories: list[str] = []
        for directory_name in directory_names:
            directory = Path(current_folder) / directory_name
            if directory.is_symlink() or should_ignore(directory):
                skipped_system_files += 1
                continue
            visible_directories.append(directory_name)
        directory_names[:] = visible_directories
        for file_name in file_names:
            path = Path(current_folder) / file_name
            if path.is_symlink():
                continue
            if should_ignore(path):
                skipped_system_files += 1
                continue
            file_paths.append(path)

    total_paths = len(file_paths)
    if progress_callback:
        progress_callback("正在盘点资料", 0, total_paths)

    for current_index, path in enumerate(file_paths, start=1):
        try:
            category, display_type, note = classify_file(path)
            parsed = parse_document(path) if parse_content else None
            record = FileRecord.from_path(
                path,
                root,
                category=category,
                display_type=display_type,
                scan_note=note,
                parse_status=parsed.status if parsed else "尚未解析",
                content_length=parsed.content_length if parsed else 0,
                document_scale=parsed.document_scale if parsed else 0,
                scale_unit=parsed.scale_unit if parsed else "",
                parse_issue=parsed.issue if parsed else "",
            )
            records.append(record)
            if parsed is not None:
                analysis_inputs.append(AnalysisInput(path, record, parsed))
        except (OSError, ValueError) as error:
            access_errors.append(f"{path}: {error}")
        if progress_callback:
            progress_callback("正在检查资料能否读取", current_index, total_paths)

    if parse_content:
        if progress_callback:
            progress_callback("正在查找重复资料和多个版本", total_paths, total_paths)
        records = analyze_documents(analysis_inputs)
        if progress_callback:
            progress_callback("正在整理知识库建议", total_paths, total_paths)
        records, knowledge_base_plans = plan_knowledge_bases(analysis_inputs, records)
    else:
        knowledge_base_plans = []
    records.sort(key=lambda item: (item.relative_path.casefold(), item.file_name.casefold()))
    return ScanResult(
        root=root,
        records=records,
        skipped_system_files=skipped_system_files,
        access_errors=access_errors,
        knowledge_base_plans=knowledge_base_plans,
    )
