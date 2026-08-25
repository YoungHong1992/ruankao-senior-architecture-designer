# 贡献指南

感谢帮助校对知识库。提交前请先阅读 [CLAUDE.md](CLAUDE.md)、[教材 Markdown 清洗与校对标准](教材Markdown清洗与校对标准.md)、[CONTENT_POLICY.md](CONTENT_POLICY.md) 和 [FIGURE_POLICY.md](FIGURE_POLICY.md)。

## 可接受的贡献

- 有原书页码或可靠来源支撑的 OCR 勘误；
- 标题、列表、表格、代码块和题号结构修复；
- 真题来源、题量、版本差异及答案争议的可追溯补录；
- 索引、验证脚本和工作流改进；
- 在有权提交的前提下恢复必要图表。

不要提交未获授权的源 PDF/扫描件、盗版下载链接、访问凭据、付费内容绕过方法，或把 AI 推测内容标成原文、原图、官方题面或官方答案。

## 内容修改流程

0. 安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)（macOS/Linux：`curl -LsSf https://astral.sh/uv/install.sh | sh`；Windows PowerShell：`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`）。本仓库脚本的解释器（Python 3.13）与依赖均由 uv 管理，一律用 `uv run ...` 执行，不要直接调用系统 `python`；首次运行会自动准备虚拟环境，无需手动 `pip install`。克隆时**不要用 `--depth`**：`build_exam_asset_audit.py` 需要按固定基线提交读取历史，浅克隆会失败（已浅克隆时执行 `git fetch --unshallow`）。
1. 先读目标目录的 `INDEX.md`；真题先读 `02.历年真题总索引.md`。
2. 教材清洗应同时对照原始提取稿和依法取得的原资料，优先做最小、可验证的修正。
3. 在文件说明或 `DATA_SOURCES.md` 中记录来源、版本、页码/题号、链接和访问日期；历史 URL 不可追溯时，不得猜测，使用 `data/exams.json` 的固定仓库快照策略保留具体文本版本。
4. 来源冲突时保留多个版本，说明差异和首选依据，不得直接拼接。
5. 教材图表变更后运行 `uv run --group audit python scripts/audit_textbook_pdf.py <PDF路径> --manual-review-completed` 更新 `data/textbook_audit.json`（`<PDF路径>` 为必填，指向合法持有的源 PDF；不带 `--manual-review-completed` 重新生成会把人工复核状态写回 `pending`，校验器将拒绝）；真题图表点位变化同步 `data/exam_asset_audit.json`。
6. 跑完 CI 会跑的**全部三条检查**，全绿再提交：

   ```bash
   uv lock --check                                          # pyproject.toml 与 uv.lock 一致
   uv run python scripts/validate_knowledge_base.py         # 主门禁，应输出 PASSED: 0 errors
   uv run python scripts/build_exam_asset_audit.py --check   # 真题账本可由固定基线重现
   uv run python scripts/build_outline_audit.py --check      # 大纲账本可重现；改过大纲正文要先去掉 --check 重建
   uv run --group lint ruff check scripts/                   # 仅在改了 scripts/ 时需要
   uv run --group lint ruff format scripts/                  # 同上；CI 用 --check 断言已格式化
   ```

   CI 用的是 `uv run --locked`，本地加 `--locked` 可以完全对齐（改过 `pyproject.toml` 但没跑 `uv lock` 时它会直接报错，而不是静默改写锁文件）。
7. 通过 Pull Request 合并；不要直接推送受保护的 `main`。

## 修改脚本依赖

- `validate_knowledge_base.py`、`build_exam_asset_audit.py` 和 `build_outline_audit.py` 只能使用 Python 标准库，以保证质量门禁不依赖任何第三方包。
- 只有 `audit_textbook_pdf.py` 允许第三方依赖，声明在 `pyproject.toml` 的 `audit` 依赖组中，运行时加 `--group audit`。
- 代码风格由 ruff 统一（配置在 `pyproject.toml` 的 `[tool.ruff]`，行宽 120），ruff 本身固定在 `lint` 依赖组。`audit` 与 `lint` 都是非默认组，因此主门禁在无第三方包的环境里也必须通过。
- pypdf 的版本在 `pyproject.toml`、`uv.lock` 和 `scripts/audit_textbook_pdf.py` 的 `PYPDF_VERSION` 三处必须一致（校验器会断言）；它决定 `data/textbook_audit.json` 能否复现，升级前须重新生成并复核该账本。
- 改动 `pyproject.toml` 后运行 `uv lock` 并把更新后的 `uv.lock` 一并提交。

## Pull Request 要求

- 标题说明资料、章节/年份和修改类型；
- 正文列出修改文件、证据、已知限制和验证结果；
- 不混入无关格式化或大规模改写；
- 内容修改优先由另一名维护者复核；单人维护且暂无独立复核人时，可由提交者完成逐项自查，并在来源、已知限制和验证结果记录完整且自动检查通过后合并。

项目自有脚本和工作流采用 [LICENSE-CODE](LICENSE-CODE)；提交第三方内容不表示其采用该许可证。提交者应确认自己有权提交相关变更。
