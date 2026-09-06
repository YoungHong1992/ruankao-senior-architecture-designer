# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 项目规范：软考高级系统架构设计师备考资料

本仓库不是应用程序，而是一个**受治理的知识库**：把系统架构设计师考试的大纲、教材（OCR 提取）和历年真题整理为可检索的 Markdown，并用 Python 脚本 + CI 强制一组不变量，保证内容可复核、可追溯、不冒充官方。编辑时真正的难点不在改字，而在**同步维护正文、数据账本、人工索引与校验脚本这四者之间的一致性**。

## 内容架构与数据流

三类资料各有“原始稿 → 清洗稿”两层，真题另有补充来源：

| 资料 | 原始稿 | 清洗稿（首选阅读） | 规模 |
|---|---|---|---|
| 大纲 | `00.系统架构设计师考试大纲/` | `00.…-清洗版/` | 前言 + 5 篇正文 + INDEX |
| 教材 | `01.系统架构设计师教材/` | `01.…-清洗版/` | 《系统架构设计师教程》2022 第 2 版，前言 + 20 章 + INDEX |
| 真题 | `02.历年真题/` + `02.历年真题(补充)/` | `02.历年真题-清洗版/` | 36 份唯一试卷 + INDEX |

治理层把正文与四份机器可读账本绑定，校验脚本据此判定一致性：

- `02.历年真题总索引.md` — 人工/AI 查询真题的统一入口，规定每卷的“首选文件”。
- `data/exams.json`（schema 3）— 真题 manifest：36 份 canonical、90 份 source_versions、来源目录、SHA-256 完整性策略、快照归档策略、终审策略。每份 source_version 记 `content_sha256`，校验器会重算比对。
- `data/exam_asset_audit.json`（schema 2）— 真题缺图/缺表的 120 个逐项点位（116 固定基线 + 4 续审）。
- `data/textbook_audit.json`（schema 4）— 教材逐页（708 页）+ 图号/表号（284 图 / 59 表）审计账本。
- `data/outline_audit.json`（schema 1）— 大纲核查账本：源扫描件 SHA-256、PDF 图像页↔印刷页映射、逐页视觉核对结论、逐项 findings（`verdict` 区分“清洗缺陷”与“忠于原书但已过时”）、外部证据哈希、落盘图表清单。

数据流：**清洗稿正文** →（脚本按固定 Git 基线提交枚举缺失标记、按本地 PDF 统计覆盖率）→ **审计账本 JSON** →（`validate_knowledge_base.py` 断言账本、manifest、两份索引与正文彼此一致）→ **CI 门禁**。

## 命令

环境由 **uv** 管理，解释器固定 **Python 3.13**（`.python-version`），依赖锁定在 `uv.lock`。**所有脚本必须经 `uv run` 执行**，不要直接调用系统 `python`/`python3`。首次运行时 uv 会自动下载 3.13 并在项目内创建 `.venv/`（已被 `.gitignore` 忽略），无需手动 `venv`/`pip`。

```bash
# 主校验门禁（仅标准库；CI 必跑，本地交付前必跑）
uv run python scripts/validate_knowledge_base.py

# 校验真题资产账本可由固定基线复现（CI 必跑）
uv run python scripts/build_exam_asset_audit.py --check
# 真题点位变化后重建账本：
uv run python scripts/build_exam_asset_audit.py

# 重建大纲核查账本（CI 必跑 --check；不依赖源 PDF，改了大纲正文后必须重建）
uv run python scripts/build_outline_audit.py
uv run python scripts/build_outline_audit.py --check

# 重建教材审计账本（不在 CI；需合法持有源 PDF + 完整 Git 历史；pypdf 由 audit 组提供）
uv run --group audit python scripts/audit_textbook_pdf.py <PDF路径> --manual-review-completed
uv run --group audit python scripts/audit_textbook_pdf.py <PDF路径> --manual-review-completed --check

# 依赖/锁文件维护
uv lock --check   # 断言 uv.lock 与 pyproject.toml 一致（CI 必跑）
uv lock           # 改了 pyproject.toml 后重新锁定，并提交 uv.lock

# 代码风格（CI 必跑；ruff 固定在 lint 组，默认不装）
uv run --group lint ruff check scripts/
uv run --group lint ruff format scripts/          # CI 用 ruff format --check
```

- 工具链文件：`pyproject.toml`（`requires-python = ">=3.13"`、`[tool.uv] package = false` + `required-version = ">=0.11.7"`、`[dependency-groups] audit = ["pypdf==6.14.2"]` 与 `lint = ["ruff==0.16.4"]`、`[tool.ruff]` 行宽 120）、`.python-version`（`3.13`）、`uv.lock`（必须入库）。本仓库不是可安装的包，uv 只负责固定解释器与两组按需依赖。
- `validate_knowledge_base.py` 与 `build_exam_asset_audit.py` 只依赖标准库，**不要**给它们加第三方依赖；`audit` 与 `lint` 都是非默认组（`--group` 按需同步），因此主门禁在没有任何第三方包的环境里也必须通过。两个 audit 脚本依赖 `git`。
- ruff 配置刻意不启用 `E501`（中文字符串无法拆行）和 `RUF001/002/003`（全角标点对中文项目是纯误报，会触发 305 次）。
- pypdf 版本必须精确匹配，否则 OCR 文本层输出漂移、账本无法复现；该版本号同时写在 `pyproject.toml`、`uv.lock` 和 `scripts/audit_textbook_pdf.py:PYPDF_VERSION` 中，校验器断言三者一致。
- CI（`.github/workflows/knowledge-base-quality.yml`）以 `fetch-depth: 0` 检出（基线提交祖先校验需要完整历史），用 `astral-sh/setup-uv`（按 SHA 固定）装 uv，再跑 `uv lock --check` + 前两条命令 + `py_compile` + `ruff check` + `ruff format --check`；`uv run --locked` 保证 CI 不会偷偷改锁文件。**教材 PDF 不入库，故教材账本不在 CI 复核**；改动教材图表后须在本地跑 `audit_textbook_pdf.py` 并提交更新后的 `data/textbook_audit.json`。
- 无测试框架：`validate_knowledge_base.py` 是单文件顺序执行的 `Validator` 类，校验器本身即“测试”。改脚本后整跑即可，没有单测可单独运行。
- 不带 `--manual-review-completed` 重新生成教材账本，会把人工复核状态写回 `pending`，校验器随即拒绝。

## 关键不变量（改内容必须同步更新）

校验器把大量“魔数”硬编码为断言，且这些数字同时出现在 JSON 账本、两份索引和 README 中。改动任何正文/题目/图表时，必须让下列数字在**脚本 + JSON + 索引**里同时成立，否则校验必红：

- 真题：36 份 canonical、17 组同名冲突、90 份 source_versions；每份 source_version 的 `content_sha256` 必须等于文件按 `utf8_bom_stripped_lf` 归一后的哈希。
- 真题资产：22 个受审文件、116 固定基线 + 4 续审 = 120 点位、6 项来源受限视觉项、1 项非原版替代；处置计数 111 已复核 / 8 结构恢复 / 1 非原版替代（列在 `positions[]` 的 120 项中）。
- 教材：物理页 13–720 共 708 个正文页、PDF 721 页、284 图、59 表、272 图标记 + 8 表 = 280 基线记录；资产债下限 296→314、关键内容债 198/199/208。
- 源 PDF SHA-256 固定为 `ee45900f…5135c2f8`；`build_*` 与 `audit_*` 依赖固定基线提交 `e02f60ca…`。
- 工具链：`.python-version` = `3.13`、`pyproject.toml` 的 `requires-python` = `>=3.13`、`project.dependencies` 必须为空、`tool.uv.package` = `false`、`dependency-groups` 必须恰好是 `audit` 与 `lint` 两组、每组只含一条 `==` 精确 pin（分别是 `pypdf`、`ruff`）；pypdf 版本须与 `scripts/audit_textbook_pdf.py:PYPDF_VERSION` 及 `uv.lock` 中锁定的完全一致，`uv.lock` 的 `requires-python` 也须为 `>=3.13`。改任一处都要跑 `uv lock` 并提交锁文件。
- “统计日期 / updated_at”三处必须一致（当前 `2026-07-12`）：`data/exams.json`、`02.历年真题总索引.md`、`02.历年真题-清洗版/INDEX.md`。
- 大纲：`data/outline_audit.json` 的 `reviewed_at` 必须等于 `00.…考试大纲-清洗版/INDEX.md` 的 `**统计日期：**`（当前 `2026-09-06`，与真题那组日期相互独立）；该 INDEX 必须同时记录 ISBN `978-7-302-62003-7` 与源扫描件 SHA-256。账本中每个 `files[].content_sha256` 由校验器按 `utf8_bom_stripped_lf` 重算比对，**改动大纲任一正文后必须重跑 `build_outline_audit.py`**。
- 大纲证据纪律（校验器强制）：`disposition = fixed_in_clean` 的 finding，其目标文件必须留有可见的 `清洗勘误` / `整理者注（非原文）` / `转录范围` / `已知限制` 标记；`verdict = source_faithful_but_outdated` 不得配 `disposition = no_change`；`agreement` 为 `confirms`/`contradicts` 的外部证据必须带 `excerpt_sha256`。
- 全部 Markdown 必须是**标准 UTF-8（无 BOM）+ CRLF**，不得含裸 CR；校验器逐字节检查。去 BOM 不影响 `data/exams.json` 的哈希（其口径本就是 `utf8_bom_stripped_lf`）。

## 懒加载与阅读约定

- 每个内容目录都有 `INDEX.md`（≤ 200 行）：章节编号、标题、文件路径，可含摘要与页码范围。**先读 INDEX，再按需打开单章**，不要一次性载入全部章节。
- 章节文件名固定 `第XX章-标题.md`（两位编号），每文件开头带章节标题层级，保留原文标题/表格/列表结构。
- 跨章问题分别读取相关章节后综合回答。

## 真题加载规则

- 查真题先读 `02.历年真题总索引.md`（自动化读 `data/exams.json`），只用索引标注的“首选文件”；36 个首选均为清洗目录标准名文件。
- `02.历年真题` 与 `02.历年真题(补充)` 中的同名文件内容可能不同：**17 组同名冲突禁止随机选择、自动拼接、覆盖或去重合并**，只能在取得可复核证据后人工吸收差异。
- 2023 下综合知识有 B75（首选）与 A65（独立备选）两套题序，同样禁止拼接。
- 回忆版、公开解析版、原始整理版都不是官方标准答案；来源冲突或证据不足时保留多版本并标“待复核”。

## 内容治理红线

以下规则由根目录标准文件定义，编辑相关内容时必须遵循：

- **教材清洗/校对**：遵循 [教材Markdown清洗与校对标准.md](教材Markdown清洗与校对标准.md)——忠于原文、先纠错后美化、可读优先；清除页眉页脚/水印/营销等 OCR 噪声（校验器对 `01.…教材-清洗版` 强制扫描 `兰亭图书阁`、`Outer Jion` 等高风险残留词）。
- **图表/公式**：遵循 [FIGURE_POLICY.md](FIGURE_POLICY.md)——不得臆造或重绘冒充原图。缺图分 A（改变题意，标“原图未收录/信息不完整”）、B（正文可独立理解）、C（纯装饰）三级。真题缺依赖图表时完整度不得标“完整”，答案可信度最高只能到“低/待复核”。
- **不造假**：无法验证的题面、选项、空号、连线、答案一律显式标“未恢复/不可裁决/待复核”，不写成已确认。
- **权利边界**：教材/大纲/真题/答案及其 OCR/清洗派生文本均为第三方内容，仓库不主张版权；仅 `scripts/` 与 `.github/workflows/` 适用 [LICENSE-CODE](LICENSE-CODE)（MIT）。边界与来源见 [CONTENT_POLICY.md](CONTENT_POLICY.md)、[DATA_SOURCES.md](DATA_SOURCES.md)。不得提交盗版 PDF、下载链接或访问凭据。

## 提交与协作

- 流程见 [CONTRIBUTING.md](CONTRIBUTING.md)：改动 → 更新来源与账本 → 跑 `uv run python scripts/validate_knowledge_base.py` → 经 PR 合并；**不要直接推送受保护的 `main`**。PR 用 `.github/pull_request_template.md`，勘误/下架走 `.github/ISSUE_TEMPLATE/`。
- 换行符：`.md` 用 **CRLF**，`.py`/`.json`/`.yml`/`.yaml`/`.toml`/`uv.lock`/`.python-version` 用 **LF**（见 `.gitattributes`、`.editorconfig`）；**所有文本文件统一为标准 UTF-8，不加 BOM**。校验器以 `utf-8-sig` 读取并归一，但提交前别改错行尾，否则 manifest 哈希会漂移。
- 不入库：源 PDF（`本地pdf参考/`、`教材相关/*.pdf`）、渲染/提取草稿（`tmp/`）、虚拟环境（`.venv/`）、`.claude/`。**`uv.lock` 必须入库。**
