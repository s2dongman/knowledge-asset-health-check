from __future__ import annotations

from pathlib import Path

from .report import export_report
from .scanner import ScanResult
from .workbooks import export_workbooks


def export_scan_result(
    result: ScanResult, output_folder: str | Path, company_name: str | None = None
) -> tuple[Path, Path, Path]:
    output = Path(output_folder).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    report_path = export_report(result, output, company_name)
    rectification_path, inventory_path = export_workbooks(result, output, company_name)
    return report_path, rectification_path, inventory_path
