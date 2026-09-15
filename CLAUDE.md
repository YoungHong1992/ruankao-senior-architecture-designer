# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 项目规范：软考高级系统架构设计师备考资料

本仓库不是应用程序，而是一个**受治理的知识库**：把系统架构设计师考试的大纲、教材（OCR 提取）和历年真题整理为可检索的 Markdown，并用 Python 脚本 + CI 强制一组不变量，保证内容可复核、可追溯、不冒充官方。编辑时真正的难点不在改字，而在**同步维护正文、数据清单、人工索引与校验脚本四者之间的一致性**。

## 内容架构与数据流

三类资料各有“原始稿 → 清洗稿”两层，真题另有补充来源：

| 资料 | 原始稿 | 清洗稿（首选阅读） | 规模 |
|---|---|---|---|
| 大纲 | `00.系统架构设计师考试大纲/` | `00.…-清洗版/` | 前言 + 5 篇正文 + INDEX |
| 教材 | `01.系统架构设计师教材/` | `01.…-清洗版/` | 《系统架构设计师教程》2022 第 2 版，前言 + 20 章 + INDEX |
| 真题 | `02.历年真题/` + `02.历年真题(补充)/` | `02.历年真题-清洗版/` | 36 份唯一试卷 + INDEX |

治理层把正文与真题机器清单绑定，校验脚本据此判定一致性：

- `02.历年真题总索引.md` — 人工/AI 查询真题的统一入口，规定每卷的“首选文件”。
- `data/exams.json`（schema 4）— 真题 manifest：36 份 canonical、90 份 source_versions 路径、来源目录与同名冲突映射。校验器断言 manifest、两份索引与正文彼此一致。

数据流：**正文与清单** →（`validate_knowledge_base.py` 断言 manifest、两份索引与正文彼此一致，并做编码与结构检查）→ **CI 门禁**。

## 命令

环境由 **uv** 管理，解释器固定 **Python 3.13**（`.python-version`），依赖锁定在 `uv.lock`。**所有脚本必须经 `uv run` 执行**，不要直接调用系统 `python`/`python3`。首次运行时 uv 会自动下载 3.13 并在项目内创建 `.venv/`（已被 `.gitignore` 忽略），无需手动 `venv`/`pip`。

```bash
# 主校验门禁（仅标准库；CI 必跑，本地交付前必跑）
uv run python scripts/validate_knowledge_base.py

# 依赖/锁文件维护
uv lock --check   # 断言 uv.lock 与 pyproject.toml 一致（CI 必跑）
uv lock           # 改了 pyproject.toml 后重新锁定，并提交 uv.lock

# 代码风格（CI 必跑；ruff 固定在 lint 组，默认不装）
uv run --group lint ruff check scripts/
uv run --group lint ruff format scripts/          # CI 用 ruff format --check
```

- 工具链文件：`pyproject.toml`（`requires-python = ">=3.13"`、`[tool.uv] package = false` + `required-version = ">=0.11.7"`、`[dependency-groups]` 仅 `lint = ["ruff==0.16.4"]`、`[tool.ruff]` 行宽 120）、`.python-version`（`3.13`）、`uv.lock`（必须入库）。本仓库不是可安装的包，uv 只负责固定解释器与按需依赖。
- `validate_knowledge_base.py` 只依赖标准库，**不要**给它加第三方依赖；`lint` 是非默认组（`--group` 按需同步），因此主门禁在没有任何第三方包的环境里也必须通过。
- ruff 配置刻意不启用 `E501`（中文字符串无法拆行）和 `RUF001/002/003`（全角标点对中文项目是纯误报，会触发 305 次）。
- CI（`.github/workflows/knowledge-base-quality.yml`）检出后用 `astral-sh/setup-uv`（按 SHA 固定）装 uv，再跑 `uv lock --check` + 主门禁 + `py_compile` + `ruff check` + `ruff format --check`；`uv run --locked` 保证 CI 不会偷偷改锁文件。
- 无测试框架：`validate_knowledge_base.py` 是单文件顺序执行的 `Validator` 类，校验器本身即“测试”。改脚本后整跑即可，没有单测可单独运行。

## 关键不变量（改内容必须同步更新）

校验器把一批“魔数”硬编码为断言，且这些数字同时出现在清单、两份索引和 README 中。改动任何正文/题目时，必须让下列数字在**脚本 + JSON + 索引**里同时成立，否则校验必红：

- 真题：36 份 canonical、17 组同名冲突、90 份 source_versions；每份 source_version 的 `path` 必须真实存在、落在 `source_catalog` 对应根目录下，且与该卷的 `preferred`/`alternatives` 完全对应；canonical 集合必须与两个来源目录中的试卷文件一一对应，无遗漏、无多余。
- 真题清洗稿结构：`题目数量/主试题数量` 声明必须与 manifest 的 `item_count` 一致；综合知识须有连续 `第N题` 标题、等量 `**正确答案：` 和 4×题量个 A–D 选项；案例分析/论文的主试题标题须唯一升序且数量一致。
- manifest（schema 4）：顶层仅有 `schema_version`、`updated_at`、`source_catalog`、`exams`；每卷 `notes` 非空且与两份索引的说明列逐字一致（总索引中同名冲突卷的说明带 `**同名冲突，禁止自动混并。**` 前缀）。
- 工具链：`.python-version` = `3.13`、`pyproject.toml` 的 `requires-python` = `>=3.13`、`project.dependencies` 必须为空、`tool.uv.package` = `false`、`dependency-groups` 必须恰好是 `lint` 一组且只含一条 `==` 精确 pin（ruff）；`uv.lock` 的 `requires-python` 也须为 `>=3.13`。改任一处都要跑 `uv lock` 并提交锁文件。
- 全部 Markdown 必须是**标准 UTF-8（无 BOM）+ CRLF**，不得含裸 CR；校验器逐字节检查。每个内容目录的 `INDEX.md` 不得超过 200 行且必须收录目录内全部章节文件；清洗目录内标题不得跳级；`01.…教材-清洗版` 强制扫描 `兰亭图书阁`、`Outer Jion` 等高风险 OCR 残留词。

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

- **教材清洗/校对**：遵循 [教材Markdown清洗与校对标准.md](教材Markdown清洗与校对标准.md)——忠于原文、先纠错后美化、可读优先。
- **图表/公式**：遵循 [FIGURE_POLICY.md](FIGURE_POLICY.md)——不得臆造或重绘冒充原图。缺图分 A（改变题意，标“原图未收录/信息不完整”）、B（正文可独立理解）、C（纯装饰）三级。
- **不造假**：无法验证的题面、选项、空号、连线、答案一律显式标“未恢复/不可裁决/待复核”，不写成已确认。
- **权利边界**：教材/大纲/真题/答案及其 OCR/清洗派生文本均为第三方内容，仓库不主张版权；仅 `scripts/` 与 `.github/workflows/` 适用 [LICENSE-CODE](LICENSE-CODE)（MIT）。边界与来源见 [CONTENT_POLICY.md](CONTENT_POLICY.md)、[DATA_SOURCES.md](DATA_SOURCES.md)。不得提交盗版 PDF、下载链接或访问凭据。

## 提交与协作

- 流程见 [CONTRIBUTING.md](CONTRIBUTING.md)：改动 → 更新来源与清单 → 跑 `uv run python scripts/validate_knowledge_base.py` → 经 PR 合并；**不要直接推送受保护的 `main`**。PR 用 `.github/pull_request_template.md`，勘误/下架走 `.github/ISSUE_TEMPLATE/`。
- 换行符：`.md` 用 **CRLF**，`.py`/`.json`/`.yml`/`.yaml`/`.toml`/`uv.lock`/`.python-version` 用 **LF**（见 `.gitattributes`、`.editorconfig`）；**所有文本文件统一为标准 UTF-8，不加 BOM**。
- 不入库：源 PDF（`教材相关/*.pdf`、`本地pdf参考/`、`PDF文档资料/`）、渲染/提取草稿（`tmp/`）、虚拟环境（`.venv/`）、`.claude/`。**`uv.lock` 必须入库。**
