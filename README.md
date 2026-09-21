# 系统架构设计师备考知识库



> 全国计算机技术与软件专业技术资格（水平）考试 · 高级资格 · 系统架构设计师



[![Knowledge Base Quality](https://github.com/YoungHong1992/ruankao-senior-architecture-designer/actions/workflows/knowledge-base-quality.yml/badge.svg)](https://github.com/YoungHong1992/ruankao-senior-architecture-designer/actions/workflows/knowledge-base-quality.yml)



本仓库把考试大纲、教材和历年试题整理为可检索的 Markdown，采用 **INDEX 索引 + 按需加载** 的方式，便于个人复习及 AI 辅助检索。正文、来源、机器清单与核查记录分层存放，每篇正文都带机器可读的文件头标签，便于将来做网页展示和知识库索引。



本项目是非官方学习资料库，与考试主管机构、原作者及出版社不存在隶属或授权关系。仓库内容可能含 OCR 错误、回忆版差异和缺失图表，不能替代依法取得的原书、考试主管机构发布的信息或其他权威资料。



## 快速开始



**只想看资料**（无需安装任何东西）：直接在 GitHub 上浏览，或 `git clone` 后用任意 Markdown 阅读器打开。入口是 [content/INDEX.md](content/INDEX.md)，再往下是三套语料各自的 `INDEX.md` 和 [content/02-历年真题总索引.md](content/02-历年真题总索引.md)——先读索引，再按需打开单章，详见[使用方式](#使用方式)。



**想校对内容并提 PR**：需要装 [uv](https://docs.astral.sh/uv/)，然后



```bash

git clone https://github.com/YoungHong1992/ruankao-senior-architecture-designer.git

cd ruankao-senior-architecture-designer

uv run python scripts/validate_knowledge_base.py   # 应输出 PASSED: 0 errors

```



看到 `PASSED` 说明环境就绪。修改流程与红线见 [AGENTS.md](AGENTS.md)（含 RULES 规则章节），完整命令见[质量检查](#质量检查)。



**用 AI 辅助检索**：先让工具读 [AGENTS.md](AGENTS.md)（Claude Code 等各家 AI 编码工具通用），里面写明了必须遵守的内容红线、索引优先的读取方式和不得自动合并的同名冲突。



## 当前内容与完成度



以下统计以各目录的实际情况为准。“已清洗”只表示已有对应 Markdown，不代表逐页、逐题完成权威校对。



| 目录 | 当前内容 | 状态 |

|---|---:|---|

| [`content/00-系统架构设计师考试大纲-清洗版`](content/00-系统架构设计师考试大纲-清洗版/) | 前言 + 5 篇正文 + 1 个索引 | 大纲首轮清洗稿 |

| [`content/01-系统架构设计师教材-清洗版`](content/01-系统架构设计师教材-清洗版/) | 前言 + 20 章 + 1 个索引 | 教材首轮清洗稿；原图未收录处只保留图题；仍非出版社校正版 |

| [`content/02-历年真题-清洗版`](content/02-历年真题-清洗版/) | 37 份试题正文 + 1 个索引 | 36 份标准名首选稿 + 1 份独立备选；均为非官方整理，不代表官方认证 |

| [`sources/00-系统架构设计师考试大纲`](sources/00-系统架构设计师考试大纲/) | 来源说明 | 69 页扫描件（无文本层），PDF 不入库 |

| [`sources/01-系统架构设计师教材`](sources/01-系统架构设计师教材/) | 来源说明 | 2022 年第 2 版、720 页扫描件（含 OCR 文本层），PDF 不入库 |

| [`sources/02-历年真题`](sources/02-历年真题/) | 33 份试题文件 | 本地原始材料；质量、题量和答案来源不一 |

| [`sources/02-历年真题(补充)`](sources/02-历年真题%28补充%29/) | 20 份试题文件 | 补充来源；与原始材料存在同名但内容不同的文件 |



当前 36 份唯一试卷均有标准名首选稿；清洗目录另保留 2023 年下半年综合知识回忆版 A（65 题），因此共有 37 份试题正文。两个来源目录的 53 份原始版/补充版正文均已映射为备选，17 组同名冲突继续隔离为独立版本、不强行混并。这些数字统一记录在 [`catalog/corpora.json`](catalog/corpora.json) 与 [`catalog/exams.json`](catalog/exams.json) 中，由质量门禁比对，不在正文里各写一份。



大纲与教材的 OCR 提取稿已不再单独保留：清洗稿是唯一正文层，复核时直接对照 `sources/` 下登记的源扫描件。



## 教材范围



仓库中的教材为《系统架构设计师教程》**2022 年 11 月第 2 版**，不是第 4 版。书目信息为：叶宏主编，清华大学出版社，ISBN `978-7-302-61992-5`。全书共 20 章：



| 篇章 | 覆盖范围 |

|:---:|---|

| 上篇：基础知识 | 计算机系统、信息系统、信息安全、软件工程、数据库设计、架构设计基础、质量属性与评估、可靠性、架构演化、未来信息技术 |

| 下篇：架构设计理论与实践 | 信息系统架构、层次式架构、云原生架构、SOA、嵌入式系统架构、通信系统架构、安全架构、大数据架构、论文写作 |



版次依据见教材清洗稿中的 [前言](content/01-系统架构设计师教材-清洗版/前言.md)；详细来源和派生关系见 [DATA_SOURCES.md](DATA_SOURCES.md)。



## 目录结构



仓库按**职责**分层，而不是按资料堆放：



```text

content/                             # 正文层：网页展示与 AI 检索的唯一取数根目录

  INDEX.md                           # 正文总索引

  00-系统架构设计师考试大纲-清洗版/  # 大纲清洗稿

  01-系统架构设计师教材-清洗版/      # 教材清洗稿

  02-历年真题-清洗版/                # 经整理、交叉校对的优先阅读稿

  02-历年真题总索引.md               # 人工/AI 查询真题的统一入口与首选文件规则

sources/                             # 来源层：第三方原始材料与其书目事实

  00-系统架构设计师考试大纲/         # 源扫描件说明（PDF 不入库）

  01-系统架构设计师教材/             # 源扫描件说明（PDF 不入库）

  02-历年真题/                       # 真题本地原始材料

  02-历年真题(补充)/                 # 真题补充材料（含同名冲突文件）

catalog/                             # 清单层：结构与数量的唯一真相

  corpora.json                       # 语料总清单：层根、各语料文档数、来源校验值

  exams.json                         # 真题机器可读清单（36 份 canonical、来源版本与同名冲突映射）

assets/                              # 资产层：依法取得并逐一对照后落盘的图片与矢量图

verification/                        # 核查记录旁路目录（与正文隔离，不纳入内容门禁）

scripts/validate_knowledge_base.py   # 知识库质量检查入口

pyproject.toml                       # uv 工具链声明：Python 3.13 与 lint 依赖组

.python-version                      # 固定解释器版本（3.13）

uv.lock                              # 锁定依赖版本

.github/workflows/knowledge-base-quality.yml # 持续集成质量门禁

AGENTS.md                            # 唯一治理文件：项目规范 + RULES 规则章节（清洗标准、图表处理、权利边界、贡献流程）

DATA_SOURCES.md                      # 出版信息、来源链与可追溯性限制

SECURITY.md                          # 脚本安全问题与敏感材料的私密上报渠道

LICENSE                              # 许可范围说明：代码 MIT，第三方内容未授权

LICENSE-CODE                         # 仅适用于项目自有脚本和工作流的 MIT 许可证

```



教材和大纲遵循 `INDEX.md + 分章文件` 结构。读取资料时先看对应目录的 `INDEX.md`，再只打开需要的章节，避免一次载入全部内容。



### 文件头标签



`content/` 下每个 Markdown 都以一段扁平的 YAML 标签开头，供将来的网页路由和知识库索引使用：



```yaml

---

id: "textbook-ch07"

corpus: "textbook"

slug: "ch07-architecture-design-fundamentals"

title: "系统架构设计基础知识"

kind: "chapter"

order: 7

source_pages: "248-270"

---

```



`slug` 是纯 ASCII 短名，用来生成不含中文的网址；`id` 全仓库唯一，真题的 `id` 与 `catalog/exams.json` 逐条对应。取值范围由 `catalog/corpora.json` 约束，并由质量门禁逐项校验。新增正文文件时必须一并补齐，否则检查不通过。



## 使用方式



1. **查大纲或教材**：先读 [content/INDEX.md](content/INDEX.md)，再进入对应语料的 `INDEX.md`；遇到语义可疑、公式、表格或图示时，对照 `sources/` 下登记的源扫描件和依法取得的原资料。

2. **做历年真题**：必须先读 [content/02-历年真题总索引.md](content/02-历年真题总索引.md)，再打开其中标注的“首选文件”；不要在两个同名来源中随机选择。自动化工具可读取 [`catalog/exams.json`](catalog/exams.json)。

3. **使用 AI**：先提供索引，再提供与问题直接相关的章节；要求 AI 区分原文与推断，不要让它替你裁定答案。

4. **引用或作出重要判断**：回到考试主管机构、出版社或其他权威来源复核。本仓库不提供正确性、完整性或时效性保证。



适合的使用场景包括按考点检索、章节讲解、知识串联、错题整理和论文框架练习；不适合把仓库内容直接视为官方答案或逐字可靠的教材电子版。



## 图表与 OCR 限制



- 当前仓库没有随 Markdown 提交教材扫描图片或独立图表资产，`content/` 下只有文本，[`assets/`](assets/README.md) 仍为空。

- **原图未收录的位置只保留图题与正文说明，不放示意图。** 仓库此前曾有 325 个由 AI 依据 OCR 标签串和领域常识生成的 Mermaid 示意图，因无法对照原图核实等价性，已于 2026-09 全部移除，位置登记在 [verification/待重画图表清单.md](verification/待重画图表清单.md)。

- 只有在手中有原始图像并逐节点、逐连线对照的前提下，才能补画图表。

- 清洗稿仍可能含错字、断句、拼栏、标题层级错误或未经确认的答案。

- 大纲与教材的源 PDF 未纳入版本库（见 [DATA_SOURCES.md](DATA_SOURCES.md) 与 `sources/*/README.md`）；仓库保存其书目信息、页数与 SHA-256 校验值，但仅凭版本库仍不能完整复现 OCR 提取过程。



图题保留与图表转写规则见 [AGENTS.md 的「图表与公式处理」](AGENTS.md#图表与公式处理)。



## 数据来源与内容政策



- 教材、大纲、试题、答案及其 OCR/清洗派生文本仍可能受第三方著作权或其他权利保护；本仓库不主张拥有这些第三方内容的版权。

- 仓库内试题包括公开回忆版和解析资料的汇编，并非全部来自官方发布，答案也并非官方标准答案。

- 只有项目原创的脚本和 GitHub Actions 工作流适用 [LICENSE-CODE](LICENSE-CODE) 中的 MIT 许可证；该许可不覆盖任何第三方内容、OCR 文本、试题、答案、图片或出版物版式。

- 详细边界、贡献要求、勘误和权利人下架流程见 [AGENTS.md 的「内容与权利政策」](AGENTS.md#内容与权利政策)。



## 质量检查



### 安装 uv



本仓库的检查脚本用 [uv](https://docs.astral.sh/uv/) 管理运行环境：解释器固定为 Python 3.13（见 `.python-version`），依赖锁定在 `uv.lock`。**只需安装 uv**，Python 与依赖都由它自动准备，不需要手动 `venv` 或 `pip install`。



```bash

# macOS / Linux

curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows（PowerShell）

powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或者用已有的 Python 工具链

pipx install uv    # 亦可 pip install uv

```



### 运行检查



在仓库根目录执行（首次运行会自动下载 Python 3.13 并创建 `.venv/`，约需一分钟；之后都是秒级）：



```bash

uv run python scripts/validate_knowledge_base.py        # 主质量门禁

uv lock --check                                         # 验证 uv.lock 与 pyproject.toml 一致

uv run --group lint ruff check scripts/                 # 脚本 lint

uv run --group lint ruff format scripts/                # 脚本格式化（CI 用 --check）

```



通过时主门禁输出 `PASSED: 0 errors`。脚本不联网、不修改正文，只读取仓库文件并打印结论；`validate_knowledge_base.py` 仅用标准库。



`validate_knowledge_base.py` 检查四层目录是否齐备、正文文件头标签是否完整且唯一、各语料文档数是否与 `catalog/corpora.json` 一致、索引与本地链接、章节文件名、题量元数据、标题层级、高风险 OCR 词、真题 manifest 与两份索引的一致性、UTF-8/CRLF 字节规范，以及 uv 工具链各处版本固定值是否互相一致。`.github/workflows/knowledge-base-quality.yml` 用同一套 uv 命令执行质量门禁；检查通过不等同于内容已获考试主管机构或出版社认证。



## 勘误与反馈



发现 OCR 错误、内容缺失、来源标注问题或答案争议时，请在 [GitHub Issues](https://github.com/YoungHong1992/ruankao-senior-architecture-designer/issues) 提交可复核证据，并写明文件路径和位置。权利人或其授权代表提出下架、署名或许可相关请求时，请按 [AGENTS.md 的「内容与权利政策」](AGENTS.md#内容与权利政策)中的流程联系维护者；不要在公开 Issue 中提交身份证件、合同等敏感材料。

