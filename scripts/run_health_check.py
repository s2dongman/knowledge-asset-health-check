#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import traceback
import venv
from collections import Counter
from datetime import datetime
from pathlib import Path


ENGINE_VERSION = "1.0.5"
RESULT_NAMES = (
    "知识资产体检报告.html",
    "文档整改清单.xlsx",
    "完整文档台账.xlsx",
)
REQUIRED_MODULES = ("openpyxl", "pypdf", "docx", "pptx")


class SkillRunError(RuntimeError):
    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def emit_error(message: str, exit_code: int) -> int:
    print(
        json.dumps(
            {"status": "error", "exit_code": exit_code, "message": message},
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    return exit_code


def missing_modules() -> list[str]:
    return [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]


def requirements_path() -> Path:
    return Path(__file__).resolve().with_name("requirements.txt")


def runtime_root() -> Path:
    override = os.environ.get("KNOWLEDGE_HEALTH_SKILL_RUNTIME")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    digest = hashlib.sha256(requirements_path().read_bytes()).hexdigest()[:12]
    return base / "shenyue-knowledge-health" / f"runtime-{ENGINE_VERSION}-{digest}"


def runtime_python(runtime: Path) -> Path:
    if os.name == "nt":
        return runtime / "Scripts" / "python.exe"
    return runtime / "bin" / "python"


def ensure_runtime() -> Path:
    runtime = runtime_root()
    python = runtime_python(runtime)
    ready = runtime / ".ready"
    if python.exists() and ready.exists():
        return python

    print("首次运行：正在准备本地文档解析环境。只下载程序依赖，不上传待体检文档。", file=sys.stderr)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not python.exists():
            venv.EnvBuilder(with_pip=True, clear=False).create(runtime)
        completed = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--requirement",
                str(requirements_path()),
            ],
            stdout=sys.stderr,
            stderr=sys.stderr,
            check=False,
        )
        if completed.returncode != 0:
            raise SkillRunError("无法安装本地解析组件，请检查网络或 Python 环境。", 4)
        ready.write_text(ENGINE_VERSION, encoding="utf-8")
    except SkillRunError:
        raise
    except Exception as error:
        raise SkillRunError(f"无法准备本地解析环境：{error}", 4) from error
    return python


def maybe_relaunch_in_runtime(argv: list[str]) -> int | None:
    if "--version" in argv:
        return None
    missing = missing_modules()
    if not missing:
        return None
    if "--no-bootstrap" in argv:
        raise SkillRunError(f"缺少本地解析组件：{', '.join(missing)}", 4)
    python = ensure_runtime()
    command = [str(python), str(Path(__file__).resolve()), *argv, "--no-bootstrap"]
    return subprocess.run(command, check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="知识资产体检 Skill 本地执行器")
    parser.add_argument("source", nargs="?", help="待体检资料目录")
    parser.add_argument("--company", help="企业名称（选填）")
    parser.add_argument("--output", help="结果输出目录（选填）")
    parser.add_argument("--overwrite", action="store_true", help="覆盖三个既有同名成果")
    parser.add_argument("--quiet", action="store_true", help="不显示阶段进度")
    parser.add_argument("--no-bootstrap", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="store_true", help="显示引擎版本")
    return parser


def sanitize_folder_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip().rstrip(". ")
    return cleaned[:80] or "资料"


def is_inside(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


def next_default_output(source: Path, company: str | None) -> Path:
    label = sanitize_folder_name((company or source.name or "资料").strip())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = source.parent / f"{label}_知识资产体检结果_{timestamp}"
    candidate = base
    index = 2
    while candidate.exists():
        candidate = source.parent / f"{base.name}_{index}"
        index += 1
    return candidate.resolve()


def choose_output(source: Path, output: str | None, company: str | None, overwrite: bool) -> Path:
    target = Path(output).expanduser().resolve() if output else next_default_output(source, company)
    if target == source or is_inside(target, source):
        raise SkillRunError("输出目录不能等于待体检目录，也不能位于待体检目录内部。", 3)
    existing = [target / name for name in RESULT_NAMES if (target / name).exists()]
    if existing and not overwrite:
        raise SkillRunError("输出目录中已经存在体检成果。请更换输出目录；仅在明确需要时使用 --overwrite。", 3)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise SkillRunError(f"无法创建输出目录：{error}", 3) from error
    return target


def make_progress_callback(quiet: bool):
    last_status = ""
    last_percent = -1

    def progress(status: str, current: int, total: int) -> None:
        nonlocal last_status, last_percent
        if quiet:
            return
        percent = round(current * 100 / total) if total else 100
        if status != last_status or percent == 100 or percent - last_percent >= 5:
            print(f"{status}：{percent}%", file=sys.stderr)
            last_status = status
            last_percent = percent

    return progress


def verify_outputs(report: Path, rectification: Path, inventory: Path) -> None:
    for path in (report, rectification, inventory):
        if not path.is_file() or path.stat().st_size == 0:
            raise SkillRunError(f"成果生成不完整：{path.name}", 6)

    report_text = report.read_text(encoding="utf-8")
    for marker in ("知识资产体检报告", "格式分布", "文档长度分布", 'id="contact-modal"'):
        if marker not in report_text:
            raise SkillRunError(f"HTML 报告缺少必要内容：{marker}", 6)

    from openpyxl import load_workbook

    for path in (rectification, inventory):
        workbook = load_workbook(path, read_only=True, data_only=False)
        workbook.close()


def run_health_check(args: argparse.Namespace) -> int:
    if not args.source:
        raise SkillRunError("请提供待体检资料目录。", 2)
    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise SkillRunError(f"找不到待体检目录：{source}", 2)
    if not source.is_dir():
        raise SkillRunError(f"请选择目录，而不是文件：{source}", 2)

    output = choose_output(source, args.output, args.company, args.overwrite)

    from knowledge_health import __version__
    from knowledge_health.exporters import export_scan_result
    from knowledge_health.scanner import scan_folder

    if __version__ != ENGINE_VERSION:
        raise SkillRunError(f"体检引擎版本不一致：期望 {ENGINE_VERSION}，实际 {__version__}", 5)

    try:
        result = scan_folder(source, progress_callback=make_progress_callback(args.quiet))
        report, rectification, inventory = export_scan_result(result, output, args.company)
        verify_outputs(report, rectification, inventory)
    except SkillRunError:
        raise
    except (OSError, ValueError) as error:
        raise SkillRunError(f"体检失败：{error}", 5) from error
    except Exception as error:
        raise SkillRunError(f"体检过程中出现未预期错误：{error}", 5) from error

    payload = {
        "status": "success",
        "engine_version": __version__,
        "total_files": result.total_files,
        "total_size_bytes": result.total_size_bytes,
        "parse_counts": dict(Counter(record.parse_status for record in result.records)),
        "use_counts": dict(Counter(record.use_status for record in result.records)),
        "skipped_system_files": result.skipped_system_files,
        "access_errors_count": len(result.access_errors),
        "output_dir": str(output),
        "report": str(report),
        "rectification": str(rectification),
        "inventory": str(inventory),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    actual_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        relaunched = maybe_relaunch_in_runtime(actual_argv)
        if relaunched is not None:
            return relaunched
        args = build_parser().parse_args(actual_argv)
        if args.version:
            print(ENGINE_VERSION)
            return 0
        return run_health_check(args)
    except SkillRunError as error:
        return emit_error(str(error), error.exit_code)
    except Exception as error:
        if os.environ.get("KNOWLEDGE_HEALTH_DEBUG") == "1":
            traceback.print_exc()
        return emit_error(f"无法运行知识资产体检：{error}", 5)


if __name__ == "__main__":
    raise SystemExit(main())
