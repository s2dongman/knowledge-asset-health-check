from __future__ import annotations

import html
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .contact_assets import WECHAT_QR_BASE64
from .parsers import DIRECT
from .scanner import ScanResult


BRAND_NAME = "申悦｜悦览杉合科技有限公司"
BRAND_POSITIONING = "专注企业知识库规划、知识治理与RAG项目落地"
CONTACT = "15811157318"
WECHAT_OFFICIAL = "互联网悦读笔记"
XIAOHONGSHU = "申老师的AI赋能笔记"


def wechat_qr_data_uri() -> str:
    return f"data:image/jpeg;base64,{WECHAT_QR_BASE64}"


TYPE_COLORS = {
    "Word": "#2563eb",
    "PDF": "#f59e0b",
    "Excel": "#10b981",
    "PPT": "#ef4444",
    "文本": "#8b5cf6",
    "其他": "#94a3b8",
}
STATUS_COLORS = {
    "可直接使用": "#16a34a",
    "整理后使用": "#f59e0b",
    "暂不能使用": "#dc2626",
}


@dataclass(frozen=True)
class Metric:
    label: str
    value: str
    note: str
    tone: str = "blue"


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def format_size(size_bytes: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value):,} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size_bytes:,} B"


def percent(count: int, total: int) -> str:
    return f"{round(count * 100 / total) if total else 0}%"


def metrics(result: ScanResult) -> list[Metric]:
    parse_counts = Counter(record.parse_status for record in result.records)
    duplicate_documents = sum(
        1 for record in result.records if record.duplicate_group or record.version_group
    )
    duplicate_groups = len({record.duplicate_group for record in result.records if record.duplicate_group})
    version_groups = len({record.version_group for record in result.records if record.version_group})
    total = result.total_files
    direct = parse_counts["可直接解析"]
    special = parse_counts["需特殊处理"]
    unavailable = parse_counts["暂无法解析"]
    return [
        Metric("总文档数", f"{total:,}份", "本次盘点的全部资料"),
        Metric("总数据量", format_size(result.total_size_bytes), "资料占用的本地空间"),
        Metric("可直接解析", f"{direct:,}份", f"占全部资料的{percent(direct, total)}", "green"),
        Metric("需特殊处理", f"{special:,}份", "含扫描、加密、损坏或旧格式", "orange"),
        Metric(
            "疑似重复文档",
            f"{duplicate_documents:,}份",
            f"涉及{duplicate_groups + version_groups:,}组重复或多版本资料",
            "orange",
        ),
        Metric("暂无法解析", f"{unavailable:,}份", f"占全部资料的{percent(unavailable, total)}", "red"),
    ]


def grouped_types(result: ScanResult) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for record in result.records:
        kind = record.display_type.split("（", 1)[0]
        if kind not in {"Word", "PDF", "Excel", "PPT", "文本"}:
            kind = "其他"
        counts[kind] += 1
    order = ("Word", "PDF", "Excel", "PPT", "文本", "其他")
    return [(kind, counts[kind]) for kind in order if counts[kind]]


def donut_chart(items: list[tuple[str, int]], total: int) -> str:
    radius = 70
    circumference = 2 * math.pi * radius
    offset = 0.0
    circles: list[str] = []
    legend: list[str] = []
    for label, count in items:
        fraction = count / total if total else 0
        length = fraction * circumference
        color = TYPE_COLORS[label]
        circles.append(
            f'<circle cx="100" cy="100" r="{radius}" fill="none" stroke="{color}" '
            f'stroke-width="28" stroke-dasharray="{length:.3f} {circumference - length:.3f}" '
            f'stroke-dashoffset="{-offset:.3f}" transform="rotate(-90 100 100)" />'
        )
        offset += length
        legend.append(
            f'<li><span class="legend-dot" style="background:{color}"></span>'
            f'<span>{escape(label)}</span><strong>{count:,}份 · {percent(count, total)}</strong></li>'
        )
    return (
        '<div class="donut-wrap"><svg class="donut" viewBox="0 0 200 200" role="img" '
        'aria-label="文件格式分布">'
        '<circle cx="100" cy="100" r="70" fill="none" stroke="#e8eef7" stroke-width="28" />'
        + "".join(circles)
        + f'<text x="100" y="94" text-anchor="middle" class="donut-number">{total:,}</text>'
        '<text x="100" y="116" text-anchor="middle" class="donut-label">份资料</text></svg>'
        f'<ul class="legend">{"".join(legend)}</ul></div>'
    )


def length_distribution(result: ScanResult) -> list[tuple[str, int]]:
    bins = [
        ("500字以内", 0, 500),
        ("500～2,000字", 500, 2000),
        ("2,000～5,000字", 2000, 5000),
        ("5,000～10,000字", 5000, 10000),
        ("10,000字以上", 10000, None),
    ]
    output: list[tuple[str, int]] = []
    readable_records = [record for record in result.records if record.parse_status == DIRECT]
    for label, lower, upper in bins:
        count = sum(
            lower <= record.content_length and (upper is None or record.content_length < upper)
            for record in readable_records
        )
        output.append((label, count))
    unavailable = result.total_files - len(readable_records)
    if unavailable:
        output.append(("暂无法统计", unavailable))
    return output


def length_distribution_note(result: ScanResult) -> str:
    scanned = [
        record
        for record in result.records
        if record.display_type.startswith("PDF") and "疑似扫描文件" in record.parse_issue
    ]
    if scanned:
        total_pages = sum(record.document_scale for record in scanned)
        return (
            f"其中{len(scanned):,}份扫描版PDF共{total_pages:,}页，因没有可读取的文字层，"
            "单独列为“暂无法统计”，不计入500字以内。"
        )
    unavailable = sum(record.parse_status != DIRECT for record in result.records)
    if unavailable:
        return (
            f"有{unavailable:,}份资料暂时无法可靠统计字数，已单独列出。"
            "其余篇幅按工具能够读取到的文字统计。"
        )
    return "篇幅根据工具能够读取到的文字统计，仅用于了解资料的大致情况。"


def bar_chart(items: list[tuple[str, int]], *, color: str = "#2563eb", label_width: int = 130) -> str:
    maximum = max((count for _, count in items), default=0)
    rows = []
    for label, count in items:
        width = 100 * count / maximum if maximum else 0
        rows.append(
            '<div class="bar-row">'
            f'<span class="bar-label" style="width:{label_width}px">{escape(label)}</span>'
            '<span class="bar-track">'
            f'<span class="bar-fill" style="width:{width:.2f}%;background:{color}"></span>'
            '</span>'
            f'<strong>{count:,}份</strong></div>'
        )
    return f'<div class="bar-chart">{"".join(rows)}</div>'


def status_chart(result: ScanResult) -> str:
    counts = Counter(record.use_status for record in result.records)
    total = result.total_files
    segments = []
    legend = []
    for label in ("可直接使用", "整理后使用", "暂不能使用"):
        count = counts[label]
        width = count * 100 / total if total else 0
        color = STATUS_COLORS[label]
        if count:
            segments.append(
                f'<span style="width:{width:.4f}%;background:{color}" title="{label} {count}份"></span>'
            )
        legend.append(
            f'<div><i style="background:{color}"></i><span>{label}</span>'
            f'<strong>{count:,}份 · {percent(count, total)}</strong></div>'
        )
    return (
        f'<div class="status-stack">{"".join(segments)}</div>'
        f'<div class="status-legend">{"".join(legend)}</div>'
    )


PROBLEM_RULES = (
    (
        "重复或多个版本",
        ("完全重复资料", "发现完全相同", "疑似存在多个版本"),
        "把同组文件交给业务负责人确认正式版本。例如保留“员工手册V3（2026正式版）”，将V1、V2标记为历史版本，不要同时进入知识库。",
    ),
    (
        "扫描文件",
        ("疑似扫描文件",),
        "先用OCR识别文字，再重点抽查标题、表格、日期和数字是否准确；确认无误后，保存为可以搜索和复制文字的PDF或Word。",
    ),
    (
        "内容为空或过少",
        ("没有读取到有效内容", "有效内容过少", "内容较短"),
        "打开原文件核对是否为空、是否只有封面或附件说明。例如只有几十个字的制度文件，应补齐正文，或者确认无保留价值后移出待入库范围。",
    ),
    (
        "无法正常读取",
        ("损坏", "加密", "无法访问", "暂不支持", "旧版Office"),
        "加密文件需提供有权限读取的副本；损坏文件需从备份恢复；旧版或不支持格式建议另存为DOCX、XLSX、PPTX、PDF等常用格式，再重新体检。",
    ),
    (
        "可能包含敏感信息",
        ("可能包含敏感信息",),
        "先确认谁可以使用，再决定脱敏或单独建受限知识库。例如隐藏身份证号、银行卡号和手机号中间位；薪酬、合同金额等资料应限制可见部门。",
    ),
    (
        "长期未更新",
        ("超过3年未更新", "超过5年未更新"),
        "请资料负责人确认是否仍有效。例如旧考勤制度如已被新制度替代，应标记失效日期并移出正式知识库，只保留在历史档案中。",
    ),
    (
        "命名或归档不清楚",
        ("文件名称或归档位置不清楚",),
        "把“新建文档、最终版、资料1”等名称改为“主题＋版本/日期＋状态”。例如改为“差旅报销制度_V2_2026正式版.docx”。",
    ),
    (
        "附件或模板需单独管理",
        ("附件/模板资料，建议单独管理",),
        "把附件、表单和模板集中放到统一的下载位置；在相关知识说明中补充下载地址，或写明从哪个系统、共享目录获取。通常不需要把附件正文作为主要检索内容。",
    ),
    (
        "Excel表头前有标题或说明",
        ("Excel表头前有标题或说明",),
        "这类表格可以读取，但标题、说明或空行可能被误当成字段名。建议把标题写入文件名或资料说明，让数据区域从单行表头开始，并删除表头前不必要的空行。",
    ),
    (
        "复杂表格或演示文稿",
        ("Excel排版较复杂", "PPT排版较复杂"),
        "Excel建议整理成单行表头、每行一条记录的明细表，并为公式列补充说明；PPT建议按页面补充标题和文字摘要，把重要流程、图表和图片改写成可独立理解的文字。复杂原文件可保留为下载附件。",
    ),
    (
        "文字读取异常",
        ("乱码", "读取异常"),
        "用原软件重新导出或转换格式，并抽查正文是否可正常复制。例如PDF打开正常但复制后是乱码，应重新生成带文本层的PDF。",
    ),
)


def top_problems(result: ScanResult) -> list[tuple[str, int, str]]:
    problems: list[tuple[str, int, str]] = []
    for label, markers, recommendation in PROBLEM_RULES:
        count = sum(any(marker in record.issues for marker in markers) for record in result.records)
        if count:
            problems.append((label, count, recommendation))
    ranked = sorted(problems, key=lambda item: (-item[1], item[0]))
    selected = ranked[:5]
    sensitive = next((item for item in ranked if item[0] == "可能包含敏感信息"), None)
    if sensitive and sensitive not in selected:
        selected[-1] = sensitive
        selected.sort(key=lambda item: (-item[1], item[0]))
    return selected


def problem_markers(label: str) -> tuple[str, ...]:
    for rule_label, markers, _ in PROBLEM_RULES:
        if rule_label == label:
            return markers
    return ()


def affected_records(result: ScanResult, label: str) -> list:
    markers = problem_markers(label)
    return [record for record in result.records if any(marker in record.issues for marker in markers)]


def example_detail(record, label: str) -> str:
    if label == "可能包含敏感信息":
        return record.sensitive_risks or "检测到敏感信息特征"
    if label == "重复或多个版本":
        group = record.duplicate_group or record.version_group
        return f"{record.issues}{f'；所属{group}' if group else ''}"
    if label in {"扫描文件", "无法正常读取"} and record.parse_issue:
        return record.parse_issue
    markers = problem_markers(label)
    details = [part for part in record.issues.split("；") if any(marker in part for marker in markers)]
    return "；".join(details) or record.issues


def problem_examples(result: ScanResult, label: str, *, limit: int = 4) -> str:
    records = affected_records(result, label)
    items = []
    for record in records[:limit]:
        items.append(
            f'<li><strong>{escape(record.relative_path)}</strong><span>{escape(example_detail(record, label))}</span></li>'
        )
    remaining = len(records) - len(items)
    if remaining > 0:
        items.append(f'<li class="more">另有 {remaining:,} 份，请在《文档整改清单》中查看</li>')
    return f'<ul class="example-list">{"".join(items)}</ul>'


def conclusion_paragraphs(result: ScanResult) -> list[str]:
    counts = Counter(record.use_status for record in result.records)
    parse_counts = Counter(record.parse_status for record in result.records)
    total = result.total_files
    top = top_problems(result)
    issue_text = "、".join(f"{label}（{count:,}份）" for label, count, _ in top[:3]) if top else "未发现集中问题"
    duplicate_documents = sum(
        1 for record in result.records if record.duplicate_group or record.version_group
    )
    knowledge_bases = [
        plan.name for plan in result.knowledge_base_plans if plan.name != "待确认资料"
    ]
    knowledge_base_text = "、".join(knowledge_bases) if knowledge_bases else "暂未形成明确建议"
    return [
        f"本次共检查{total:,}份资料，总数据量{format_size(result.total_size_bytes)}。",
        f"从读取情况看：{parse_counts['可直接解析']:,}份可直接解析，{parse_counts['需特殊处理']:,}份需特殊处理，{duplicate_documents:,}份疑似重复，{parse_counts['暂无法解析']:,}份暂时无法解析。",
        f"从入库情况看：{counts['可直接使用']:,}份（{percent(counts['可直接使用'], total)}）未发现明显阻碍；{counts['整理后使用']:,}份（{percent(counts['整理后使用'], total)}）需要先整理；{counts['暂不能使用']:,}份（{percent(counts['暂不能使用'], total)}）不建议现在进入知识库。",
        f"其中最需要处理的问题是：{issue_text}。",
        f"建议规划知识库：{knowledge_base_text}。",
    ]


def conclusion_html(result: ScanResult) -> str:
    paragraphs = "".join(f"<p>{escape(text)}</p>" for text in conclusion_paragraphs(result))
    return f'<div class="lead">{paragraphs}</div>'


def status_example_detail(record) -> str:
    detail = record.issues or record.parse_issue or record.scan_note or "需要人工确认"
    if record.sensitive_risks and "敏感信息" in detail:
        detail = f"{detail}（{record.sensitive_risks}）"
    return detail


def status_examples(result: ScanResult, status: str, *, limit: int = 3) -> str:
    records = [record for record in result.records if record.use_status == status]
    if not records:
        return ""
    suffix = "需整理后再入库" if status == "整理后使用" else "当前不建议入库"
    items = [
        f'<li><strong>{escape(record.relative_path)}</strong><span>{escape(status_example_detail(record))}，{suffix}。</span></li>'
        for record in records[:limit]
    ]
    remaining = len(records) - len(items)
    if remaining > 0:
        items.append(f'<li class="more">另有 {remaining:,} 份，请在《文档整改清单》中查看</li>')
    return f'<ul class="status-example-list">{"".join(items)}</ul>'


def use_status_standards(result: ScanResult) -> str:
    counts = Counter(record.use_status for record in result.records)
    standards = (
        (
            "可直接使用",
            "正文可读取，且未发现明显的格式、内容或版本问题。正式上线前仍需业务负责人确认。",
        ),
        (
            "整理后使用",
            "资料仍有利用价值，但存在可以修复的问题，需要先完成整理。",
        ),
        (
            "暂不能使用",
            "当前无法可靠读取，或者属于不应重复入库的文件，需要处理后重新体检。",
        ),
    )
    cards = []
    for label, description in standards:
        tone = {"可直接使用": "ready", "整理后使用": "work", "暂不能使用": "blocked"}[label]
        cards.append(
            f'<article class="standard-card {tone}"><div><h3>{escape(label)}</h3>'
            f'<strong>{counts[label]:,}份 · {percent(counts[label], result.total_files)}</strong></div>'
            f'<p>{escape(description)}</p>'
            f'{status_examples(result, label) if label != "可直接使用" else ""}</article>'
        )
    return f'<div class="standards">{"".join(cards)}</div>'


def metric_cards(result: ScanResult) -> str:
    return "".join(
        '<article class="metric-card '
        + escape(metric.tone)
        + '"><span>'
        + escape(metric.label)
        + "</span><strong>"
        + escape(metric.value)
        + "</strong><small>"
        + escape(metric.note)
        + "</small></article>"
        for metric in metrics(result)
    )


def knowledge_base_cards(result: ScanResult) -> str:
    cards = []
    for plan in result.knowledge_base_plans:
        pending = " pending" if plan.name == "待确认资料" else ""
        cards.append(
            f'<article class="kb-card{pending}"><div class="kb-head"><h3>{escape(plan.name)}</h3>'
            f'<strong>{plan.document_count:,}份</strong></div>'
            f'<p>{escape(plan.description)}</p><dl><div><dt>当前情况</dt><dd>{escape(plan.current_situation)}</dd></div>'
            f'<div><dt>主要问题</dt><dd>{escape(plan.main_issue)}</dd></div></dl></article>'
        )
    return "".join(cards) or '<p class="empty">暂无足够资料形成候选知识库建议。</p>'


def render_report(result: ScanResult, company_name: str | None = None) -> str:
    company = (company_name or result.root.name or "企业").strip()
    generated = datetime.now().astimezone().strftime("%Y年%m月%d日")
    types = grouped_types(result)
    lengths = length_distribution(result)
    problems = top_problems(result)
    problems_table = "".join(
        f'<tr><td><strong>{escape(label)}</strong><div class="problem-count">{count:,}份</div></td>'
        f'<td>{problem_examples(result, label)}</td><td class="recommendation">{escape(action)}</td></tr>'
        for label, count, action in problems
    ) or '<tr><td colspan="3">未发现集中问题</td></tr>'
    problems_bars = bar_chart([(label, count) for label, count, _ in problems], color="#f59e0b", label_width=150)

    template = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(company)}知识资产体检报告</title>
<style>
:root{{--blue:#1746a2;--blue2:#2563eb;--ink:#172033;--muted:#64748b;--line:#dfe7f2;--bg:#f4f7fb;--green:#16a34a;--orange:#f59e0b;--red:#dc2626}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;line-height:1.65}}
.report{{max-width:1120px;margin:0 auto;background:white;box-shadow:0 20px 55px rgba(23,70,162,.10)}}
.hero{{background:linear-gradient(135deg,#133b8d,#1f5bc1);color:white;padding:54px 64px 48px;position:relative;overflow:hidden}}
.hero:after{{content:"";position:absolute;width:330px;height:330px;border-radius:50%;right:-110px;top:-165px;border:50px solid rgba(255,255,255,.08)}}
.eyebrow{{font-size:15px;letter-spacing:.08em;opacity:.82}}h1{{font-size:44px;line-height:1.2;margin:14px 0 8px}}.hero .subtitle{{font-size:20px;margin:0;opacity:.92}}
.hero-meta{{display:flex;gap:32px;margin-top:38px;font-size:14px;opacity:.82}}.brand-line{{margin-top:30px;font-weight:700;font-size:17px}}
main{{padding:42px 64px 54px}}section{{margin:0 0 46px}}.section-head{{display:flex;align-items:end;justify-content:space-between;gap:24px;margin-bottom:20px}}
h2{{font-size:27px;line-height:1.3;margin:0;color:#153b7e}}.section-no{{color:#8aa4cb;font-size:14px;font-weight:700;margin-right:8px}}
.lead{{font-size:17px;line-height:1.85;background:#edf4ff;border-left:5px solid var(--blue2);padding:18px 24px;margin:0 0 24px;border-radius:0 10px 10px 0}}.lead p{{margin:0 0 10px}}.lead p:last-child{{margin-bottom:0}}
.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.metric-card{{border:1px solid var(--line);border-radius:14px;padding:20px;background:linear-gradient(180deg,#fff,#f9fbff)}}
.metric-card span{{font-size:15px;color:#4b6285}}.metric-card strong{{display:block;font-size:31px;line-height:1.3;margin:5px 0;color:#143b7f}}.metric-card small{{display:block;color:var(--muted)}}
.metric-card.green strong{{color:var(--green)}}.metric-card.orange strong{{color:#d97706}}.metric-card.red strong{{color:var(--red)}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}.panel{{border:1px solid var(--line);border-radius:16px;padding:24px;background:#fff}}.panel h3{{margin:0 0 18px;font-size:19px}}
.donut-wrap{{display:flex;align-items:center;gap:24px}}.donut{{width:210px;height:210px;flex:0 0 210px}}.donut-number{{font-size:25px;font-weight:800;fill:#173d7f}}.donut-label{{font-size:12px;fill:#64748b}}
.legend{{list-style:none;margin:0;padding:0;flex:1}}.legend li{{display:grid;grid-template-columns:14px 1fr auto;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid #eef2f7;font-size:13px}}.legend-dot{{width:10px;height:10px;border-radius:50%}}.legend strong{{font-weight:600}}
.bar-chart{{display:flex;flex-direction:column;gap:12px}}.bar-row{{display:flex;align-items:center;gap:10px;font-size:13px}}.bar-label{{flex:0 0 auto;color:#475569}}.bar-track{{height:20px;background:#edf2f8;border-radius:5px;overflow:hidden;flex:1}}.bar-fill{{display:block;height:100%;border-radius:5px}}.bar-row strong{{width:62px;text-align:right}}
.note{{font-size:13px;color:var(--muted);margin:16px 0 0}}.status-stack{{display:flex;height:44px;border-radius:10px;overflow:hidden;background:#e8eef7}}.status-stack span{{display:block;height:100%}}
.status-legend{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:18px}}.status-legend div{{display:grid;grid-template-columns:12px 1fr;gap:3px 8px}}.status-legend i{{width:10px;height:10px;border-radius:50%;margin-top:7px}}.status-legend strong{{grid-column:2;color:#253858}}
table{{width:100%;border-collapse:collapse;margin-top:22px;font-size:14px;table-layout:fixed}}th{{background:#eef4fc;color:#31527c;text-align:left}}th,td{{padding:14px;border-bottom:1px solid var(--line);vertical-align:top}}th:first-child{{width:18%}}th:nth-child(2){{width:38%}}.problem-count{{color:#c26500;font-weight:700;margin-top:5px}}td.recommendation{{line-height:1.75}}.example-list{{list-style:none;margin:0;padding:0}}.example-list li{{margin:0 0 9px;padding:0 0 9px;border-bottom:1px dashed #dfe7f2;overflow-wrap:anywhere}}.example-list li:last-child{{margin-bottom:0;border-bottom:0;padding-bottom:0}}.example-list strong{{display:block;color:#173d7f}}.example-list span{{display:block;color:#52647e;font-size:13px;margin-top:2px}}.example-list .more{{color:var(--muted);font-size:13px}}
.standards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:20px}}.standard-card{{border:1px solid var(--line);border-top:4px solid #94a3b8;border-radius:12px;padding:17px;background:#fff}}.standard-card.ready{{border-top-color:var(--green)}}.standard-card.work{{border-top-color:var(--orange)}}.standard-card.blocked{{border-top-color:var(--red)}}.standard-card div{{display:flex;justify-content:space-between;gap:10px;align-items:center}}.standard-card h3{{font-size:17px;margin:0}}.standard-card strong{{font-size:13px;white-space:nowrap}}.standard-card p{{font-size:13px;color:#52647e;margin:10px 0 0;line-height:1.7}}.status-example-list{{list-style:none;margin:13px 0 0;padding:12px 0 0;border-top:1px dashed #d8e1ee}}.status-example-list li{{margin:0 0 10px;overflow-wrap:anywhere}}.status-example-list li:last-child{{margin-bottom:0}}.status-example-list strong{{display:block;color:#173d7f;white-space:normal}}.status-example-list span{{display:block;color:#52647e;font-size:12px;line-height:1.65;margin-top:2px}}.status-example-list .more{{color:var(--muted);font-size:12px}}
.actions{{background:#fff8eb;border:1px solid #f9dba6;border-radius:12px;padding:18px 22px;margin-top:20px}}.actions strong{{color:#9a5600}}.actions ol{{margin:8px 0 0;padding-left:22px}}
.kb-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}}.kb-card{{border:1px solid var(--line);border-radius:14px;padding:20px;border-top:4px solid var(--blue2)}}.kb-card.pending{{border-top-color:#94a3b8;background:#fafafa}}
.kb-head{{display:flex;justify-content:space-between;gap:16px;align-items:start}}.kb-head h3{{margin:0;font-size:18px}}.kb-head strong{{color:var(--blue2);white-space:nowrap}}.kb-card p{{color:#52647e;margin:10px 0 14px;font-size:14px}}
.kb-card dl{{margin:0}}.kb-card dl div{{display:grid;grid-template-columns:72px 1fr;gap:8px;font-size:13px;margin-top:6px}}.kb-card dt{{color:#718096}}.kb-card dd{{margin:0}}
.cta{{background:linear-gradient(135deg,#112e68,#174ba5);color:white;border-radius:18px;padding:34px 38px}}.cta h2{{color:white}}.cta p{{max-width:850px}}.contact-grid{{display:grid;grid-template-columns:1.1fr 1fr;gap:24px;margin-top:22px}}
.contact-box{{background:rgba(255,255,255,.1);padding:18px;border-radius:12px}}.contact-box strong{{display:block;font-size:17px}}.contact-box span{{display:block;margin-top:5px;opacity:.86}}
.cta-button-wrap{{text-align:center}}.cta-button{{display:inline-block;margin:22px auto 0;background:#fff;color:#1746a2;padding:12px 22px;border-radius:9px;font-weight:800;text-decoration:none}}.footnote{{font-size:12px;color:#78879b;text-align:center;margin:36px 0 0}}
.contact-modal{{position:fixed;inset:0;z-index:1000;display:none;align-items:center;justify-content:center;padding:24px;background:rgba(15,23,42,.66);backdrop-filter:blur(3px)}}.contact-modal.is-open{{display:flex}}
.contact-dialog{{position:relative;width:min(820px,100%);display:grid;grid-template-columns:minmax(240px,300px) 1fr;overflow:hidden;background:#fff;color:var(--ink);border-radius:22px;box-shadow:0 28px 80px rgba(15,23,42,.32)}}
.contact-qr{{display:flex;align-items:center;justify-content:center;padding:36px;background:#f2f6fd}}.contact-qr img{{display:block;width:100%;max-width:260px;height:auto;border-radius:14px;box-shadow:0 8px 28px rgba(23,70,162,.12)}}
.contact-detail{{padding:42px 40px 36px}}.contact-detail .modal-eyebrow{{margin:0 0 8px;color:var(--blue2);font-size:13px;font-weight:800;letter-spacing:.08em}}.contact-detail h2{{margin:0 42px 22px 0;font-size:27px}}.contact-name{{margin:0 0 4px;font-size:20px;font-weight:800;color:#153b7e}}.contact-number{{margin:0 0 18px;font-size:16px;font-weight:700}}.contact-note{{margin:0 0 12px;color:#334155}}.contact-explain{{margin:0;color:#52647e}}
.contact-modal-actions{{display:flex;gap:12px;margin-top:26px}}.modal-button{{appearance:none;border:0;border-radius:9px;padding:11px 18px;font:inherit;font-weight:800;cursor:pointer}}.modal-button.primary{{background:var(--blue);color:#fff}}.modal-button.secondary{{background:#e8eef7;color:#29405f}}.modal-button.copy-success{{background:var(--green)}}
.modal-close{{position:absolute;right:18px;top:16px;width:38px;height:38px;border:0;border-radius:50%;background:#edf2f8;color:#415a77;font-size:25px;line-height:1;cursor:pointer}}.modal-close:hover,.modal-close:focus-visible{{background:#dce6f3;color:#173d7f}}.modal-button:focus-visible,.cta-button:focus-visible{{outline:3px solid #93c5fd;outline-offset:3px}}
.empty{{color:var(--muted)}}
@media(max-width:800px){{.hero,main{{padding-left:24px;padding-right:24px}}h1{{font-size:34px}}.metrics{{grid-template-columns:repeat(2,1fr)}}.two-col,.kb-grid,.contact-grid,.standards{{grid-template-columns:1fr}}.donut-wrap{{flex-direction:column}}.status-legend{{grid-template-columns:1fr}}table{{table-layout:auto;display:block;overflow-x:auto;white-space:normal}}}}
@media(max-width:680px){{.contact-modal{{padding:14px}}.contact-dialog{{grid-template-columns:1fr;max-height:calc(100vh - 28px);overflow-y:auto}}.contact-qr{{padding:28px 28px 18px}}.contact-qr img{{max-width:220px}}.contact-detail{{padding:26px 24px 28px}}.contact-detail h2{{font-size:23px;margin-right:38px}}.contact-modal-actions{{flex-direction:column}}.modal-button{{width:100%}}}}
@media print{{body{{background:white}}.report{{box-shadow:none;max-width:none}}.hero{{print-color-adjust:exact;-webkit-print-color-adjust:exact}}section,.panel,.kb-card,.cta{{break-inside:avoid}}.cta-button,.contact-modal{{display:none!important}}}}
</style>
</head>
<body><div class="report">
<header class="hero"><div class="eyebrow">{escape(company)}</div><h1>知识资产体检报告</h1>
<p class="subtitle">本次共盘点 {result.total_files:,} 份资料</p>
<div class="hero-meta"><span>体检日期：{generated}</span><span>体检范围：{escape(result.root.name)}</span></div>
<div class="brand-line">{BRAND_NAME}<br><span style="font-weight:400;font-size:14px;opacity:.8">{BRAND_POSITIONING}</span></div></header>
<main>
<section><div class="section-head"><h2><span class="section-no">01</span>体检结论与关键指标</h2></div>{conclusion_html(result)}<div class="metrics">{metric_cards(result)}</div>
<p class="note">说明：可直接解析、需特殊处理、暂无法解析三项之和等于总文档数；疑似重复文档是交叉指标，不参与相加。</p></section>
<section><div class="section-head"><h2><span class="section-no">02</span>现有资料是什么</h2></div><div class="two-col">
<article class="panel"><h3>格式分布</h3>{donut_chart(types, result.total_files)}</article>
<article class="panel"><h3>文档长度分布</h3>{bar_chart(lengths)}<p class="note">{escape(length_distribution_note(result))}</p></article>
</div></section>
<section><div class="section-head"><h2><span class="section-no">03</span>现有资料能不能用</h2></div><article class="panel">{status_chart(result)}
<p class="note">“可以直接解析”只代表电脑能够读取；是否适合进入知识库，还要考虑重复版本、敏感信息和内容质量等问题。</p>
<h3 style="margin-top:26px">三种结果是怎么判断的</h3>{use_status_standards(result)}</article></section>
<section><div class="section-head"><h2><span class="section-no">04</span>最需要处理的问题</h2></div><article class="panel">{problems_bars}
<table><thead><tr><th>主要问题</th><th>涉及文档举例</th><th>建议处理方式</th></tr></thead><tbody>{problems_table}</tbody></table>
<p class="note">同一份资料可能同时存在多个问题，以上数量不与资料总数直接相加。敏感信息只显示风险类别和命中数量，不在报告中展示具体号码或原文。</p></article>
<div class="actions"><strong>建议按这个顺序开始整改：</strong><ol><li>打开《文档整改清单》，先筛选“优先处理”，给每份资料指定负责人和完成时间；</li><li>优先解决无法读取、扫描件、空白内容和乱码问题，处理后抽查正文、表格、数字和日期；</li><li>把重复或多版本资料放在一起确认正式版，历史版单独归档，不与正式版同时入库；</li><li>把附件和模板集中到统一下载位置，并在相关知识说明中补充下载地址或获取路径；</li><li>对含敏感信息的资料确认使用对象：可以脱敏的先脱敏，不能脱敏的放入限制访问的知识库；</li><li>完成一轮整改后重新运行本工具，确认“暂不能使用”和“整理后使用”的数量是否下降。</li></ol></div></section>
<section><div class="section-head"><h2><span class="section-no">05</span>建议规划的知识库</h2></div><div class="kb-grid">{knowledge_base_cards(result)}</div>
<p class="note">以上建议根据文件夹、文件名称和内容中的常见词语自动整理。正式建设时，还需要结合实际用途和使用范围进行确认。</p></section>
<section class="cta"><h2>下一步：知识治理</h2>
<p>知识库建设，不是只把文件导入系统。在这之前，还要完成版本确认、资料清理、格式处理、使用范围划分和知识库规划。</p>
<p>如果您不知道应该先处理哪些问题，或者希望有人协助完成后续知识治理与知识库建设，可以免费预约一次30分钟报告解读。我们将结合本次体检结果，帮您确认哪些问题最值得先处理，以及知识库项目应该从哪里开始。</p>
<div class="contact-grid"><div class="contact-box"><strong>{BRAND_NAME}</strong><span>{BRAND_POSITIONING}</span><span>手机/微信：{CONTACT}</span></div>
<div class="contact-box"><strong>关注更多企业AI实践</strong><span>微信公众号：{WECHAT_OFFICIAL}</span><span>小红书：{XIAOHONGSHU}</span></div></div>
<div class="cta-button-wrap"><a class="cta-button" id="open-contact-modal" href="#contact-modal">免费预约30分钟报告解读</a></div>
</section><p class="footnote">本报告由本地工具自动生成，结果用于知识库建设前的初步盘点，不替代企业内部的业务、法律与安全判断。</p>
</main></div>
<div class="contact-modal" id="contact-modal" role="dialog" aria-modal="true" aria-labelledby="contact-modal-title" aria-hidden="true">
<div class="contact-dialog">
<button class="modal-close" type="button" data-close-contact aria-label="关闭联系窗口">&times;</button>
<div class="contact-qr"><img src="{wechat_qr_data_uri()}" alt="申悦个人微信二维码"></div>
<div class="contact-detail">
<p class="modal-eyebrow">免费预约30分钟报告解读</p>
<h2 id="contact-modal-title">添加微信，沟通体检结果</h2>
<p class="contact-name">申悦</p>
<p class="contact-number">微信（同电话）：{CONTACT}</p>
<p class="contact-note">添加微信时，请备注“报告解读”。</p>
<p class="contact-explain">你也可以把体检报告一并发给我，我会结合报告说明问题和后续治理思路。</p>
<div class="contact-modal-actions"><button class="modal-button primary" id="copy-wechat" type="button" data-contact="{CONTACT}">复制微信号</button><button class="modal-button secondary" type="button" data-close-contact>关闭</button></div>
</div></div></div>
<script>
(function(){{
  var modal=document.getElementById('contact-modal');
  var openButton=document.getElementById('open-contact-modal');
  var copyButton=document.getElementById('copy-wechat');
  var previousFocus=null;
  function openModal(event){{
    if(event)event.preventDefault();
    previousFocus=document.activeElement;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden','false');
    document.body.style.overflow='hidden';
    copyButton.focus();
  }}
  function closeModal(){{
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden','true');
    document.body.style.overflow='';
    if(previousFocus)previousFocus.focus();
  }}
  function fallbackCopy(value){{
    var input=document.createElement('textarea');
    input.value=value;
    input.setAttribute('readonly','');
    input.style.position='fixed';
    input.style.opacity='0';
    document.body.appendChild(input);
    input.select();
    var copied=document.execCommand('copy');
    document.body.removeChild(input);
    return copied;
  }}
  function showCopyResult(copied){{
    copyButton.textContent=copied?'✓ 已复制微信号':'复制失败，请手动选择号码';
    if(copied)copyButton.classList.add('copy-success');
    window.setTimeout(function(){{copyButton.textContent='复制微信号';copyButton.classList.remove('copy-success');}},2200);
  }}
  openButton.addEventListener('click',openModal);
  modal.querySelectorAll('[data-close-contact]').forEach(function(button){{button.addEventListener('click',closeModal);}});
  modal.addEventListener('click',function(event){{if(event.target===modal)closeModal();}});
  document.addEventListener('keydown',function(event){{if(event.key==='Escape'&&modal.classList.contains('is-open'))closeModal();}});
  copyButton.addEventListener('click',function(){{
    var value=copyButton.getAttribute('data-contact');
    if(navigator.clipboard&&window.isSecureContext){{
      navigator.clipboard.writeText(value).then(function(){{showCopyResult(true);}}).catch(function(){{showCopyResult(fallbackCopy(value));}});
    }}else{{showCopyResult(fallbackCopy(value));}}
  }});
}})();
</script>
</body></html>"""
    return template


def export_report(result: ScanResult, output_folder: str | Path, company_name: str | None = None) -> Path:
    output = Path(output_folder).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    path = output / "知识资产体检报告.html"
    path.write_text(render_report(result, company_name), encoding="utf-8")
    return path
