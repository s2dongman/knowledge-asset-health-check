from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from .analyzers import AnalysisInput
from .models import FileRecord, KnowledgeBasePlan


PENDING = "待确认资料"
MAX_KNOWLEDGE_BASES = 6


@dataclass(frozen=True)
class KnowledgeCategory:
    name: str
    description: str
    keywords: tuple[str, ...]


CATEGORIES = (
    KnowledgeCategory(
        "IT系统与运维知识库",
        "IT系统使用、账号权限、故障处理、网络安全和运维资料",
        (
            "IT",
            "信息技术",
            "信息化",
            "信息系统",
            "系统",
            "软件",
            "平台",
            "账号",
            "权限",
            "登录",
            "网络",
            "服务器",
            "数据库",
            "接口",
            "API",
            "运维",
            "故障",
            "安装",
            "配置",
            "备份",
            "恢复",
            "监控",
            "工单",
            "VPN",
            "防火墙",
        ),
    ),
    KnowledgeCategory(
        "员工办事知识库",
        "人事、行政、考勤、福利和员工日常办事资料",
        ("人力", "人事", "人资", "HR", "员工", "招聘", "入职", "离职", "考勤", "休假", "社保", "福利", "培训", "行政", "办公", "报销", "差旅"),
    ),
    KnowledgeCategory(
        "销售与客户服务知识库",
        "销售流程、客户资料、销售话术、案例和客户服务资料",
        ("销售", "客户", "商机", "线索", "销售话术", "报价", "投标", "案例", "售前", "售后", "客服", "渠道", "经销商"),
    ),
    KnowledgeCategory(
        "产品与解决方案知识库",
        "产品介绍、功能说明、解决方案和技术资料",
        ("产品", "解决方案", "功能", "技术参数", "使用说明", "用户手册", "产品手册", "版本发布", "研发", "需求说明"),
    ),
    KnowledgeCategory(
        "生产与操作规范知识库",
        "生产、质量、安全、设备、项目交付和操作规范",
        ("生产", "质量", "安全", "设备", "操作", "作业", "工艺", "检验", "仓储", "物流", "供应链", "采购", "交付", "项目实施"),
    ),
    KnowledgeCategory(
        "公司制度与管理知识库",
        "公司制度、管理办法、组织职责和工作规范",
        ("公司制度", "管理制度", "管理办法", "工作规范", "组织架构", "部门职责", "岗位职责", "内控", "会议", "公文", "印章", "档案"),
    ),
    KnowledgeCategory(
        "财经与金融知识库",
        "财经资讯、金融市场、证券基金、宏观经济和投资理财资料",
        (
            "财经",
            "金融",
            "股票",
            "证券",
            "基金",
            "债券",
            "期货",
            "外汇",
            "银行",
            "保险",
            "理财",
            "投资",
            "行情",
            "宏观经济",
            "经济数据",
            "财报",
            "上市公司",
        ),
    ),
    KnowledgeCategory(
        "财务与经营知识库",
        "财务制度、预算、付款、税务和经营分析资料",
        (
            "财务",
            "财经",
            "财经共享",
            "会计",
            "总账",
            "预算",
            "付款",
            "报销",
            "费用",
            "发票",
            "税务",
            "成本",
            "资金",
            "资产",
            "经营分析",
            "审计",
            "结算",
        ),
    ),
    KnowledgeCategory(
        "合同与法务知识库",
        "合同模板、法律事务、合规和风险管理资料",
        ("合同", "协议", "法务", "法律", "合规", "风险", "诉讼", "知识产权", "保密协议", "授权书"),
    ),
)

SPECIALIZED_CATEGORIES = {
    "经销商与客户服务知识库": KnowledgeCategory(
        "经销商与客户服务知识库",
        "经销商政策、渠道业务、客户服务、常见问题和售后案例",
        (),
    ),
    "门店销售助手知识库": KnowledgeCategory(
        "门店销售助手知识库",
        "门店销售流程、产品知识、导购话术、销售技巧和售后应对资料",
        (),
    ),
}

GENERIC_FOLDER_NAMES = {
    "资料",
    "文档",
    "文件",
    "知识库",
    "测试用知识库",
    "公司资料",
    "共享资料",
    "其他",
    "临时资料",
    "待整理",
}
ISSUE_LABELS = (
    "疑似存在多个版本",
    "完全重复资料",
    "疑似扫描文件",
    "可能包含敏感信息",
    "没有读取到有效内容",
    "有效内容过少",
    "文件名称或归档位置不清楚",
    "附件/模板资料，建议单独管理",
    "超过5年未更新",
    "超过3年未更新",
)


def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def contains_keyword(text: str, keyword: str) -> bool:
    normalized = normalize(text)
    target = normalize(keyword)
    if target.isascii() and target.isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(target)}(?![a-z0-9])", normalized) is not None
    return target in normalized


def keyword_score(text: str, keywords: tuple[str, ...], weight: int) -> int:
    return sum(weight for keyword in keywords if contains_keyword(text, keyword))


def root_folder_name(item: AnalysisInput, relative: Path) -> str:
    try:
        return item.path.parents[len(relative.parts) - 1].name
    except IndexError:
        return ""


def theme_anchor_text(item: AnalysisInput, relative: Path) -> str:
    """返回本次资料的主题文件夹；汇总目录下使用第一层业务文件夹。"""
    root_text = root_folder_name(item, relative)
    generic_names = {normalize(name) for name in GENERIC_FOLDER_NAMES}
    if normalize(root_text) in generic_names:
        return relative.parts[0] if len(relative.parts) > 1 else ""
    return root_text


def source_scores(item: AnalysisInput) -> dict[str, int]:
    relative = Path(item.record.relative_path)
    folders = [part for part in relative.parts[:-1] if normalize(part) not in {normalize(name) for name in GENERIC_FOLDER_NAMES}]
    folder_text = " ".join(folders)
    file_text = relative.stem
    body_text = item.parsed.text[:50000]
    # 用户可能一次扫描“测试用知识库/公司资料”等汇总目录。此时真正的业务主题
    # 往往是下一层的“财经、经销商、销售助手、人资”等文件夹，不能丢掉。
    root_text = theme_anchor_text(item, relative)

    scores: dict[str, int] = {}
    for category in CATEGORIES:
        # 用户选中的最外层文件夹代表本次体检主题，应高于正文中零散业务词。
        score = keyword_score(root_text, category.keywords, 20)
        score += keyword_score(folder_text, category.keywords, 8)
        score += keyword_score(file_text, category.keywords, 5)
        score += min(keyword_score(body_text, category.keywords, 1), 5)
        scores[category.name] = score
    return scores


def choose_category(item: AnalysisInput) -> str:
    scores = source_scores(item)
    ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    best_name, best_score = ranked[0]
    second_score = ranked[1][1]

    # 正文只作辅助：至少要有一个目录/文件名命中，或正文有3个不同的强信号。
    if best_score < 3:
        return PENDING
    if best_score == second_score and best_score < 8:
        return PENDING
    return best_name


def specialize_category(item: AnalysisInput, category_name: str) -> str:
    """对使用对象非常明确的销售场景给出更贴近业务的知识库名称。"""
    if category_name != "销售与客户服务知识库":
        return category_name
    anchor = theme_anchor_text(item, Path(item.record.relative_path))
    if contains_keyword(anchor, "经销商"):
        return "经销商与客户服务知识库"
    if contains_keyword(anchor, "销售助手"):
        return "门店销售助手知识库"
    return category_name


def extract_main_issue(records: list[FileRecord]) -> str:
    counts: Counter[str] = Counter()
    for record in records:
        if any(
            marker in record.issues
            for marker in ("损坏", "加密", "无法访问", "暂不支持", "旧版Office")
        ):
            counts["无法正常读取"] += 1
        if any(marker in record.issues for marker in ("Excel排版较复杂", "PPT排版较复杂")):
            counts["复杂排版文件"] += 1
        if "Excel表头前有标题或说明" in record.issues:
            counts["Excel表头需整理"] += 1
        for label in ISSUE_LABELS:
            if label in record.issues:
                counts[label] += 1
    if not counts:
        return "未发现集中问题"
    label, count = counts.most_common(1)[0]
    friendly = {
        "疑似存在多个版本": "需要确认正式版本",
        "完全重复资料": "需要清理重复资料",
        "疑似扫描文件": "扫描文件需要先识别文字",
        "可能包含敏感信息": "需要确认使用范围",
        "没有读取到有效内容": "部分资料没有有效内容",
        "有效内容过少": "部分资料内容过少",
        "文件名称或归档位置不清楚": "部分资料命名或归档不清楚",
        "附件/模板资料，建议单独管理": "附件或模板需要集中管理",
        "超过5年未更新": "部分资料需要确认是否仍然有效",
        "超过3年未更新": "部分资料需要确认是否仍在使用",
        "无法正常读取": "部分资料无法正常读取",
        "复杂排版文件": "复杂表格或演示文稿需要先整理",
        "Excel表头需整理": "部分Excel需要规范表头",
    }[label]
    return f"{friendly}（{count}份）"


def situation(records: list[FileRecord]) -> str:
    if not records:
        return "暂无资料"
    direct = sum(record.use_status == "可直接使用" for record in records)
    unavailable = sum(record.use_status == "暂不能使用" for record in records)
    direct_ratio = direct / len(records)
    unavailable_ratio = unavailable / len(records)
    if direct_ratio >= 0.7:
        return "大部分可以使用"
    if unavailable_ratio >= 0.3:
        return "需要优先整理"
    return "部分资料需要整理"


def plan_knowledge_bases(
    items: list[AnalysisInput], records: list[FileRecord]
) -> tuple[list[FileRecord], list[KnowledgeBasePlan]]:
    if len(items) != len(records):
        raise ValueError("文档分析结果与规划输入数量不一致")

    assignments = [specialize_category(item, choose_category(item)) for item in items]

    # 一个主题高度集中的资料包里，偶尔会出现差旅、员工、合同等交叉用词。
    # 零星资料不足以支撑单独建库时，归回主知识库，避免给客户过多、过碎的建议。
    official_counts = Counter(name for name in assignments if name != PENDING)
    official_total = sum(official_counts.values())
    if official_total >= 10 and official_counts:
        dominant_name, dominant_count = official_counts.most_common(1)[0]
        tiny_limit = max(1, int(official_total * 0.03))
        if dominant_count / official_total >= 0.8:
            assignments = [
                dominant_name
                if name != PENDING
                and name != dominant_name
                and official_counts[name] <= tiny_limit
                else name
                for name in assignments
            ]

    category_counts = Counter(name for name in assignments if name != PENDING)
    selected = {name for name, _ in category_counts.most_common(MAX_KNOWLEDGE_BASES)}
    final_assignments = [name if name in selected else PENDING for name in assignments]

    updated_records = [
        replace(record, suggested_knowledge_base=assignment)
        for record, assignment in zip(records, final_assignments)
    ]

    plans: list[KnowledgeBasePlan] = []
    category_by_name = {category.name: category for category in CATEGORIES}
    category_by_name.update(SPECIALIZED_CATEGORIES)
    order = [name for name, _ in Counter(final_assignments).most_common()]
    for name in order:
        grouped = [record for record in updated_records if record.suggested_knowledge_base == name]
        if name == PENDING:
            plans.append(
                KnowledgeBasePlan(
                    PENDING,
                    "暂时无法明确归类，需要结合实际用途人工确认",
                    len(grouped),
                    "需要人工确认",
                    extract_main_issue(grouped),
                )
            )
            continue
        category = category_by_name[name]
        plans.append(
            KnowledgeBasePlan(
                category.name,
                category.description,
                len(grouped),
                situation(grouped),
                extract_main_issue(grouped),
            )
        )
    return updated_records, plans
