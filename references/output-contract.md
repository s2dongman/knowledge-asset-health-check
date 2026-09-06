# 执行与输出契约

## 必填与选填参数

```text
run_health_check.py SOURCE [--company NAME] [--output DIR] [--overwrite] [--quiet]
```

- `SOURCE`：唯一必填项，必须是可访问的本地目录。
- `--company`：选填；报告抬头使用，默认采用源目录名称。
- `--output`：选填；默认在源目录旁创建带时间的结果目录。
- `--overwrite`：允许覆盖指定输出目录中已有的三个同名成果；只有用户明确要求时才可使用。
- `--quiet`：不显示阶段进度，最终 JSON 不受影响。

输出目录不能等于源目录，也不能位于源目录内部。

## 标准输出

成功时，标准输出的最后一行是 UTF-8 JSON。进度和依赖安装信息只写入标准错误，不污染机器结果。

关键字段：

```json
{
  "status": "success",
  "engine_version": "1.0.5",
  "total_files": 100,
  "total_size_bytes": 123456,
  "parse_counts": {},
  "use_counts": {},
  "access_errors_count": 0,
  "output_dir": "绝对路径",
  "report": "绝对路径/知识资产体检报告.html",
  "rectification": "绝对路径/文档整改清单.xlsx",
  "inventory": "绝对路径/完整文档台账.xlsx"
}
```

## 退出码

- `0`：成功，三个成果均已生成并通过基本完整性检查。
- `2`：输入参数或源目录不正确。
- `3`：输出目录不安全、不可写或会覆盖既有成果。
- `4`：Python 或解析依赖准备失败。
- `5`：扫描、分析或导出失败。
- `6`：成果生成后校验失败。

## 兼容范围

- 引擎支持 Python 3.9 及以上版本。
- 源码型 Skill 可在 Windows、macOS 和 Linux 上运行，但首次准备依赖通常需要联网。
- 文档体检本身不发起网络请求；依赖准备完成后可以离线运行。
- 支持正文读取的首批格式为 DOCX、PDF、XLSX、PPTX、TXT 和 Markdown；旧版 Office 及其他格式会盘点并给出转换或人工确认建议。
