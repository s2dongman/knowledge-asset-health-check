from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeBasePlan:
    """面向客户展示的候选知识库建议。"""

    name: str
    description: str
    document_count: int
    current_situation: str
    main_issue: str


@dataclass(frozen=True)
class FileRecord:
    """一次只读扫描得到的单个文件记录。"""

    file_name: str
    relative_path: str
    category: str
    display_type: str
    extension: str
    size_bytes: int
    modified_at: str
    scan_status: str
    scan_note: str
    parse_status: str = "尚未解析"
    content_length: int = 0
    document_scale: int = 0
    scale_unit: str = ""
    parse_issue: str = ""
    use_status: str = "尚未判断"
    issues: str = ""
    priority: str = ""
    recommendation: str = ""
    duplicate_group: str = ""
    version_group: str = ""
    sensitive_risks: str = ""
    sensitive_risk_count: int = 0
    suggested_knowledge_base: str = "待确认资料"

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)

    @classmethod
    def from_path(
        cls,
        path: Path,
        root: Path,
        *,
        category: str,
        display_type: str,
        scan_status: str = "已盘点",
        scan_note: str = "",
        parse_status: str = "尚未解析",
        content_length: int = 0,
        document_scale: int = 0,
        scale_unit: str = "",
        parse_issue: str = "",
        use_status: str = "尚未判断",
        issues: str = "",
        priority: str = "",
        recommendation: str = "",
        duplicate_group: str = "",
        version_group: str = "",
        sensitive_risks: str = "",
        sensitive_risk_count: int = 0,
        suggested_knowledge_base: str = "待确认资料",
    ) -> "FileRecord":
        stat = path.stat()
        return cls(
            file_name=path.name,
            relative_path=str(path.relative_to(root)),
            category=category,
            display_type=display_type,
            extension=path.suffix.lower() or "无扩展名",
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            scan_status=scan_status,
            scan_note=scan_note,
            parse_status=parse_status,
            content_length=content_length,
            document_scale=document_scale,
            scale_unit=scale_unit,
            parse_issue=parse_issue,
            use_status=use_status,
            issues=issues,
            priority=priority,
            recommendation=recommendation,
            duplicate_group=duplicate_group,
            version_group=version_group,
            sensitive_risks=sensitive_risks,
            sensitive_risk_count=sensitive_risk_count,
            suggested_knowledge_base=suggested_knowledge_base,
        )
