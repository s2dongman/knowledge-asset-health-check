# 知识资产体检 Skill

一个纯本地运行的 Codex Skill，用确定性规则引擎盘点企业知识库资料，生成可离线查看的 HTML 体检报告和两份 Excel 清单。

## 特点

- 不使用大模型分析文档；
- 待体检文档不上传，不修改，不删除；
- 支持 DOCX、PDF、XLSX、PPTX、TXT 和 Markdown 正文读取；
- 识别无法解析、空白/过短、乱码、长期未更新、命名不规范、重复与多版本文档；
- 输出“可直接使用、整理后使用、暂不能使用”及处理优先级；
- 默认不覆盖历史结果，并阻止把输出写入待体检目录内部。

## 生成的成果

每次体检会生成：

1. `知识资产体检报告.html`
2. `文档整改清单.xlsx`
3. `完整文档台账.xlsx`

## 安装

仓库根目录就是完整的 Skill。将本仓库克隆或复制到 Codex Skill 目录：

```bash
git clone https://github.com/s2dongman/knowledge-asset-health-check.git \
  ~/.codex/skills/knowledge-asset-health-check
```

重新打开 Codex 后，可以直接调用：

```text
使用 $knowledge-asset-health-check 体检 /path/to/documents
```

## 直接运行

即使不使用 Codex，也可以直接运行内置执行器：

```bash
python3 scripts/run_health_check.py "/path/to/documents" \
  --company "示例公司"
```

企业名称和输出目录都是可选项。默认会在源目录旁边新建带时间戳的结果目录。

首次运行如果本机缺少解析组件，执行器会在用户缓存目录建立隔离的 Python 环境并安装固定版本依赖。该步骤需要联网，实际文档体检过程不发起网络请求。

## 环境要求

- Python 3.9+
- Windows、macOS 或 Linux

命令行参数、JSON 输出与退出码见 [references/output-contract.md](references/output-contract.md)。

## 开发与验证

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

## 许可证

[MIT License](LICENSE)
