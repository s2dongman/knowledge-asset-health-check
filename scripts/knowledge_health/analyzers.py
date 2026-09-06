from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .models import FileRecord
from .parsers import DIRECT, SPECIAL, UNAVAILABLE, ParseResult


READY = "可直接使用"
NEEDS_WORK = "整理后使用"
NOT_READY = "暂不能使用"

HIGH = "优先处理"
MEDIUM = "建议处理"
LOW = "后续优化"


@dataclass(frozen=True)
class AnalysisInput:
    path: Path
    record: FileRecord
    parsed: ParseResult


@dataclass
class Findings:
    status: str
    issues: list[str]
    recommendations: list[str]
    priority: str
    duplicate_group: str = ""
    version_group: str = ""
    sensitive_risks: dict[str, int] | None = None


PRIORITY_RANK = {"": 0, LOW: 1, MEDIUM: 2, HIGH: 3}
STATUS_RANK = {READY: 0, NEEDS_WORK: 1, NOT_READY: 2}

BAD_NAME_PATTERNS = (
    re.compile(r"^(新建(文档|文件|文件夹)?|未命名|副本|复件)(\s*\(\d+\)|\s*\d+)?$", re.I),
    re.compile(r"^\d{1,4}$"),
    re.compile(r"^(最终|最新版|新版本|final)(版)?\s*\d*$", re.I),
)
BAD_FOLDER_NAMES = {"新建文件夹", "临时", "临时资料", "其他", "未分类", "待整理"}
DUPLICATE_COPY_MARKERS = ("副本", "复件", "备份", "copy", "旧版", "历史版", "废弃")
VERSION_MARKER = re.compile(
    r"(?ix)(?:"
    r"[\s_\-（(\[]*(?:最终|最新版|新版本|修订版?|更新版|定稿|草稿|送审稿|发布版|正式版|旧版|历史版|废弃版|备份|副本|复件|copy|final)\s*\d*"
    r"|[\s_\-（(\[]*v(?:er(?:sion)?)?\.?\s*\d+(?:\.\d+)*"
    r"|[\s_\-（(\[]*(?:19|20)\d{2}(?:[-_.年]\d{1,2})?(?:[-_.月]\d{1,2})?日?版?"
    r"|[\s_\-（(\[]*第?\d+(?:\.\d+)*版"
    r")[\s_\-）)\]]*"
)
NON_TITLE_CHARACTERS = re.compile(r"[^\u3400-\u9fffA-Za-z0-9]+")
ATTACHMENT_TEMPLATE_PATTERN = re.compile(r"附件|模[板版]", re.I)

PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_PATTERN = re.compile(r"(?<!\d)(?:\d{17}[0-9Xx]|\d{15})(?!\d)")
BANK_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){15,19}(?!\d)")
BANK_CARD_CONTEXT_PATTERN = re.compile(r"银行卡号?|银行账号|银行账户|卡号|账户号码|收款账号")
EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9_.-])", re.I)
CONFIDENTIAL_PATTERN = re.compile(
    r"(?:(?:文件)?密级|保密级别)\s*[:：]\s*(?:绝密|机密|秘密)"
    r"|^\s*[【\[]?(?:绝密|机密|秘密)[】\]]?\s*[★☆]\s*(?:\d+年)?\s*$"
    r"|^\s*(?:内部机密|仅限内部使用|仅限内部传阅|禁止外传|严禁外传)\s*$",
    re.I | re.M,
)
SALARY_PATTERN = re.compile(
    r"(?:基本工资|岗位工资|月工资|月薪|年薪|应发工资|实发工资|税前工资|税后工资|"
    r"工资标准|薪资标准|薪酬标准|工资明细|薪资明细|薪酬明细)"
    r"[^\n。；;]{0,20}(?:\d[\d,.]*\s*(?:元|万元|人民币|RMB|￥|¥))",
    re.I,
)
CONTRACT_AMOUNT_PATTERN = re.compile(
    r"(?:本合同(?:总)?金额|本协议(?:总)?金额|本合同总价|双方约定的合同金额)"
    r"\s*(?:为|是|[:：=])\s*(?:人民币\s*)?(?:RMB\s*)?[￥¥]?\s*"
    r"(?:\d[\d,.]*\s*(?:万元|元)|[￥¥]\s*\d[\d,.]*)",
    re.I,
)
HIGH_IMPACT_RISK_CATEGORIES = {
    "身份证号码",
    "银行卡号码",
    "明确密级标识",
    "个人薪酬数据",
    "合同金额",
}


def add_finding(
    findings: Findings,
    issue: str,
    recommendation: str,
    *,
    status: str = NEEDS_WORK,
    priority: str = MEDIUM,
) -> None:
    if issue not in findings.issues:
        findings.issues.append(issue)
    if recommendation and recommendation not in findings.recommendations:
        findings.recommendations.append(recommendation)
    if STATUS_RANK[status] > STATUS_RANK[findings.status]:
        findings.status = status
    if PRIORITY_RANK[priority] > PRIORITY_RANK[findings.priority]:
        findings.priority = priority


def normalized_text_hash(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"\s+", "", normalized)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def valid_mainland_id(value: str) -> bool:
    if len(value) == 15:
        return value.isdigit()
    if len(value) != 18 or not value[:17].isdigit():
        return False
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    checks = "10X98765432"
    expected = checks[sum(int(number) * weight for number, weight in zip(value[:17], weights)) % 11]
    return value[-1].upper() == expected


def valid_luhn(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if not 16 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    parity = len(digits) % 2
    for index, character in enumerate(digits):
        number = int(character)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def detect_sensitive_risks(text: str) -> dict[str, int]:
    """仅返回风险类别和数量，绝不返回命中的原文。"""
    risks: dict[str, int] = {}
    phone_count = len(PHONE_PATTERN.findall(text))
    id_count = sum(1 for match in ID_PATTERN.finditer(text) if valid_mainland_id(match.group()))
    card_count = 0
    for match in BANK_CARD_PATTERN.finditer(text):
        context = text[max(0, match.start() - 18) : min(len(text), match.end() + 18)]
        if BANK_CARD_CONTEXT_PATTERN.search(context) and valid_luhn(match.group()):
            card_count += 1
    checks = (
        ("手机号码", phone_count),
        ("身份证号码", id_count),
        ("银行卡号码", card_count),
        ("电子邮箱", len(EMAIL_PATTERN.findall(text))),
        ("明确密级标识", len(CONFIDENTIAL_PATTERN.findall(text))),
        ("个人薪酬数据", len(SALARY_PATTERN.findall(text))),
        ("合同金额", len(CONTRACT_AMOUNT_PATTERN.findall(text))),
    )
    for label, count in checks:
        if count:
            risks[label] = count
    return risks


def version_title_key(path: Path) -> tuple[str, bool]:
    title = unicodedata.normalize("NFKC", path.stem).casefold()
    explicit_marker = bool(VERSION_MARKER.search(title))
    title = VERSION_MARKER.sub("", title)
    title = NON_TITLE_CHARACTERS.sub("", title)
    return title, explicit_marker


def binary_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def garbled_ratio(text: str) -> float:
    if not text:
        return 0.0
    suspicious = 0
    considered = 0
    for character in text:
        if character.isspace():
            continue
        considered += 1
        category = unicodedata.category(character)
        if character == "\ufffd" or category in {"Cc", "Co", "Cs", "Cn"}:
            suspicious += 1
    return suspicious / considered if considered else 0.0


def has_bad_name(path: Path) -> bool:
    stem = path.stem.strip()
    if any(pattern.fullmatch(stem) for pattern in BAD_NAME_PATTERNS):
        return True
    return any(part.strip().casefold() in {name.casefold() for name in BAD_FOLDER_NAMES} for part in path.parts[:-1])


def is_attachment_or_template(path: Path) -> bool:
    """识别更适合集中下载、而不是作为主要检索内容的附件或模板文件。"""
    normalized_name = unicodedata.normalize("NFKC", path.stem)
    return ATTACHMENT_TEMPLATE_PATTERN.search(normalized_name) is not None


def age_in_years(modified_at: str, now: datetime) -> float:
    modified = datetime.fromisoformat(modified_at)
    if modified.tzinfo is None:
        modified = modified.replace(tzinfo=timezone.utc)
    return max(0.0, (now - modified).days / 365.25)


def initial_findings(item: AnalysisInput, now: datetime) -> Findings:
    record = item.record
    parsed = item.parsed
    findings = Findings(READY, [], [], "")

    if parsed.status == UNAVAILABLE:
        add_finding(
            findings,
            parsed.issue or "当前无法读取",
            "请转换为工具支持的常用文档格式",
            status=NOT_READY,
            priority=HIGH,
        )
    elif parsed.status == SPECIAL:
        issue = parsed.issue or "需要特殊处理"
        unavailable_now = any(word in issue for word in ("损坏", "加密", "无法访问"))
        add_finding(
            findings,
            issue,
            "请按问题说明处理后重新体检",
            status=NOT_READY if unavailable_now else NEEDS_WORK,
            priority=HIGH if unavailable_now else MEDIUM,
        )

    if parsed.status == DIRECT:
        if parsed.content_length == 0:
            add_finding(
                findings,
                "没有读取到有效内容",
                "请确认文件是否为空，或重新提供包含正文的版本",
                status=NOT_READY,
                priority=HIGH,
            )
        elif parsed.content_length < 50:
            add_finding(
                findings,
                "有效内容过少",
                "请确认内容是否完整、是否需要保留",
                status=NEEDS_WORK,
                priority=MEDIUM,
            )
        # Excel中的小型对比表、参数表常常字数不多但信息完整，不能仅凭不足200字
        # 就判断为残缺；接近空表（不足50个有效字符）仍保留提示。
        elif parsed.content_length < 200 and item.path.suffix.lower() != ".xlsx":
            add_finding(
                findings,
                "内容较短",
                "建议人工确认内容是否完整",
                status=NEEDS_WORK,
                priority=LOW,
            )

    bad_ratio = garbled_ratio(parsed.text)
    if bad_ratio >= 0.3:
        add_finding(
            findings,
            "内容主要是乱码",
            "建议重新导出或转换文件格式",
            status=NOT_READY,
            priority=HIGH,
        )
    elif bad_ratio >= 0.1:
        add_finding(
            findings,
            "部分文字可能是乱码",
            "建议检查正文并重新导出文件",
            status=NEEDS_WORK,
            priority=MEDIUM,
        )

    years = age_in_years(record.modified_at, now)
    if years >= 5:
        add_finding(
            findings,
            "超过5年未更新",
            "请确认资料目前是否仍然有效",
            status=NEEDS_WORK,
            priority=LOW,
        )
    elif years >= 3:
        add_finding(
            findings,
            "超过3年未更新",
            "建议确认资料目前是否仍在使用",
            status=NEEDS_WORK,
            priority=LOW,
        )

    if has_bad_name(item.path):
        add_finding(
            findings,
            "文件名称或归档位置不清楚",
            "建议改成能够说明内容和版本的名称",
            status=NEEDS_WORK,
            priority=LOW,
        )

    if parsed.layout_warnings:
        if item.path.suffix.lower() == ".xlsx":
            light_warnings = [
                warning for warning in parsed.layout_warnings if "正式表头前" in warning
            ]
            complex_warnings = [
                warning for warning in parsed.layout_warnings if "正式表头前" not in warning
            ]
            if light_warnings:
                add_finding(
                    findings,
                    f"Excel表头前有标题或说明（{'、'.join(light_warnings)}）",
                    "建议把表格标题写入文件名或单独的资料说明，并让正式数据区域从单行表头开始；删除表头前不必要的空行，确保每行是一条完整记录",
                    status=NEEDS_WORK,
                    priority=LOW,
                )
            if complex_warnings:
                add_finding(
                    findings,
                    f"Excel排版较复杂（{'、'.join(complex_warnings)}）",
                    "建议整理成单行表头、每行一条记录的明细表；公式列应补充字段说明或保留可核对的结果值，复杂原表可作为附件下载",
                    status=NEEDS_WORK,
                    priority=MEDIUM,
                )
        elif item.path.suffix.lower() == ".pptx":
            details = "、".join(parsed.layout_warnings)
            add_finding(
                findings,
                f"PPT排版较复杂（{details}）",
                "建议按页面补充标题和文字摘要；重要流程、图表和图片另写文字说明，复杂原PPT可作为参考附件下载",
                status=NEEDS_WORK,
                priority=MEDIUM,
            )

    if is_attachment_or_template(item.path):
        add_finding(
            findings,
            "附件/模板资料，建议单独管理",
            "建议集中放到附件/模板下载区，并在相关知识说明中补充下载地址或获取路径；不建议把附件正文作为主要检索内容",
            status=READY,
            priority=MEDIUM,
        )

    risks = detect_sensitive_risks(parsed.text)
    if risks:
        findings.sensitive_risks = risks
        high_impact_risks = set(risks) & HIGH_IMPACT_RISK_CATEGORIES
        if high_impact_risks:
            add_finding(
                findings,
                "可能包含敏感信息",
                "请确认资料的使用对象和访问范围",
                status=NEEDS_WORK,
                priority=MEDIUM,
            )
        else:
            add_finding(
                findings,
                "包含联系方式，建议确认展示范围",
                "如属于公开业务联系方式可直接保留，否则建议脱敏或限制展示",
                status=READY,
                priority=LOW,
            )

    return findings


def choose_primary(indexes: list[int], items: list[AnalysisInput]) -> int:
    def score(index: int) -> tuple[int, int, float, int, str]:
        item = items[index]
        modified = datetime.fromisoformat(item.record.modified_at).timestamp()
        name = item.path.stem.casefold()
        looks_like_copy = any(marker in name for marker in DUPLICATE_COPY_MARKERS)
        return (
            1 if item.parsed.status == DIRECT else 0,
            0 if looks_like_copy else 1,
            modified,
            item.record.content_length,
            item.record.relative_path.casefold(),
        )

    return max(indexes, key=score)


def find_duplicate_groups(items: list[AnalysisInput]) -> list[list[int]]:
    signatures: dict[str, list[int]] = {}
    for index, item in enumerate(items):
        if item.record.size_bytes > 0:
            try:
                file_signature = f"binary:{binary_hash(item.path)}"
                signatures.setdefault(file_signature, []).append(index)
            except OSError:
                pass

        text_signature = normalized_text_hash(item.parsed.text)
        if text_signature and item.parsed.content_length >= 20:
            signatures.setdefault(f"text:{text_signature}", []).append(index)

    candidate_groups = [set(indexes) for indexes in signatures.values() if len(indexes) > 1]
    merged: list[set[int]] = []
    for group in candidate_groups:
        overlaps = [existing for existing in merged if existing & group]
        if not overlaps:
            merged.append(set(group))
            continue
        combined = set(group)
        for existing in overlaps:
            combined.update(existing)
            merged.remove(existing)
        merged.append(combined)
    return [sorted(group) for group in sorted(merged, key=lambda value: min(value))]


def find_version_groups(items: list[AnalysisInput]) -> list[list[int]]:
    candidates: dict[tuple[str, str], list[tuple[int, bool]]] = {}
    for index, item in enumerate(items):
        key, explicit_marker = version_title_key(item.path)
        if len(key) < 3:
            continue
        parent = str(item.path.parent).casefold()
        candidates.setdefault((parent, key), []).append((index, explicit_marker))

    groups: list[list[int]] = []
    for members in candidates.values():
        if len(members) < 2 or not any(has_marker for _, has_marker in members):
            continue
        indexes = [index for index, _ in members]
        distinct_texts = {normalized_text_hash(items[index].parsed.text) for index in indexes}
        distinct_texts.discard("")
        distinct_files = {items[index].record.file_name.casefold() for index in indexes}
        if len(distinct_files) > 1 and (len(distinct_texts) > 1 or not distinct_texts):
            groups.append(sorted(indexes))
    return sorted(groups, key=lambda group: min(group))


def analyze_documents(items: list[AnalysisInput], *, now: datetime | None = None) -> list[FileRecord]:
    current_time = now or datetime.now().astimezone()
    findings = [initial_findings(item, current_time) for item in items]

    for group_number, indexes in enumerate(find_duplicate_groups(items), start=1):
        group_id = f"重复组{group_number:03d}"
        primary = choose_primary(indexes, items)
        for index in indexes:
            findings[index].duplicate_group = group_id
            if index == primary:
                add_finding(
                    findings[index],
                    "发现完全相同的资料（建议保留本文件）",
                    "请确认保留本文件，其余相同资料不重复入库",
                    priority=MEDIUM,
                )
            else:
                add_finding(
                    findings[index],
                    "完全重复资料（不建议重复入库）",
                    "请与同组资料核对，本文件不建议重复放入知识库",
                    status=NOT_READY,
                    priority=MEDIUM,
                )

    for group_number, indexes in enumerate(find_version_groups(items), start=1):
        group_id = f"版本组{group_number:03d}"
        for index in indexes:
            findings[index].version_group = group_id
            add_finding(
                findings[index],
                "疑似存在多个版本",
                "请确认当前正式有效的版本，其余版本不建议重复入库",
                status=NEEDS_WORK,
                priority=MEDIUM,
            )

    output: list[FileRecord] = []
    for item, result in zip(items, findings):
        output.append(
            replace(
                item.record,
                use_status=result.status,
                issues="；".join(result.issues),
                priority=result.priority,
                recommendation="；".join(result.recommendations),
                duplicate_group=result.duplicate_group,
                version_group=result.version_group,
                sensitive_risks="；".join(
                    f"{label}（{count}处）" for label, count in (result.sensitive_risks or {}).items()
                ),
                sensitive_risk_count=sum((result.sensitive_risks or {}).values()),
            )
        )
    return output
