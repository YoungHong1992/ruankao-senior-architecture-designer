---
id: "content-index"
corpus: "root"
slug: "index"
title: "知识库正文总索引"
kind: "root-index"
---

# 知识库正文总索引

本目录是**正文层**：第三方清洗稿与独立标识的 AI 辅助学习手册都在这里，也是将来网页展示与
AI 知识库索引的唯一取数根目录。原始材料在 [`sources/`](../sources/README.md)，
机器清单在 [`catalog/`](../catalog/README.md)，核查记录在 [`verification/`](../verification/README.md)。

## 语料入口

| 语料 | 入口 | 规模 | 来源形态 |
|---|---|---|---|
| 考试大纲 | [00-系统架构设计师考试大纲-清洗版/INDEX.md](00-系统架构设计师考试大纲-清洗版/INDEX.md) | 前言 + 卷首文件材料 + 考试说明 + 3 个考试范围科目 + 题型举例 | 69 页扫描件（无文本层）的 OCR 清洗稿 |
| 教材 | [01-系统架构设计师教材-清洗版/INDEX.md](01-系统架构设计师教材-清洗版/INDEX.md) | 前言 + 20 章 / 119 节 | 720 页扫描件（含 OCR 文本层）的清洗稿 |
| 历年真题 | [02-历年真题-清洗版/INDEX.md](02-历年真题-清洗版/INDEX.md) | 36 份首选 + 1 份独立备选 | 本地原始版与补充版的交叉校对稿 |
| 核心考点精要 | [03-核心考点精要/INDEX.md](03-核心考点精要/INDEX.md) | 随教学逐篇形成，已完成范围见索引 | AI 辅助编写的非官方学习手册，与清洗稿区分 |

真题的选用规则、同名冲突处置与备选来源，统一走
[历年真题总索引](02-历年真题总索引.md)；机器读取走 [catalog/exams.json](../catalog/exams.json)。

## 读取顺序

1. 先读对应语料的 `INDEX.md`，定位需要的章节或试卷；
2. 教材还有一层：章目录的 `INDEX.md` 列出本章各节，再按需打开单节文件；
3. 不要一次性载入整套语料或整章；
4. 跨章问题分别读取相关章节后综合回答；
5. 真题必须经总索引选定“首选文件”，**不要在同名的原始版/补充版之间随机选择或自动合并**。

## 文件头标签（frontmatter）

`content/` 下每个 Markdown 文件开头都有一段扁平的 YAML 标签，供网页路由与知识库索引使用：

| 字段 | 含义 | 出现在 |
|---|---|---|
| `id` | 全仓库唯一标识；真题的 `id` 与 [catalog/exams.json](../catalog/exams.json) 一致 | 全部 |
| `corpus` | 所属语料：`outline` / `textbook` / `exams` / `study` / `root` | 全部 |
| `slug` | ASCII 短名，用于将来生成网址，避免中文路径被百分号编码 | 全部 |
| `title` | 中文标题 | 全部 |
| `kind` | `root-index` / `index` / `master-index` / `preface` / `chapter` / `section` / `exam` / `exam-variant` / `guide` | 全部 |
| `order` | 章节序号，前言为 0；节为章内序号；学习手册为建议学习顺序 | 大纲、教材、学习手册 |
| `derivation` / `authority` | 学习资料固定为 `ai-assisted` / `unofficial`，包括系列索引 | 核心考点精要 |
| `parent` | 所属章的 `id` | 教材节 |
| `source_pages` | 原书印刷页范围，可回溯核对 | 教材章、节 |
| `year` / `session` / `subject` | 年份、场次（`h1`/`h2`）、科目（`comprehensive`/`case-analysis`/`essay`） | 真题 |

字段取值由 [catalog/corpora.json](../catalog/corpora.json) 约束，并由
`scripts/validate_knowledge_base.py` 逐项校验；新增文件时必须一并补齐。

## 内容限制

第三方清洗稿来自 OCR 与人工整理；核心考点精要是 AI 辅助编写的学习摘要。它们**不是官方教材、官方题库或官方答案**，可能含错字、断句、
题量差异与未经确认的答案。原书插图未随仓库收录，原图缺位处只保留图题与文字说明，
不放推测出来的示意图；待补画位置登记在 [verification/待重画图表清单.md](../verification/待重画图表清单.md)。

权利边界见 [AGENTS.md 的「内容与权利政策」](../AGENTS.md#内容与权利政策)，
来源与派生关系见 [DATA_SOURCES.md](../DATA_SOURCES.md)。
