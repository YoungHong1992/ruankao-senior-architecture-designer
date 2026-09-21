# 00-系统架构设计师考试大纲（来源层）

本目录放置考试大纲的**源 PDF**。该文件不入库，只在维护者本地存在。

## 期望的本地文件

| 文件名 | 大小 | SHA-256 |
|---|---:|---|
| `系统架构设计师考试大纲.pdf` | 10,346,226 字节 | `3a25e4530acd65fe12963985b4c09e61b5fb6db53c81dc3d766d1abe3b51d5ca` |

机器可读版本见 [catalog/corpora.json](../../catalog/corpora.json) 的 `outline.source`。

## 已知事实与限制

- 共 **69 页**，整页扫描图像，**没有文本层**：无法直接抽取文字，任何正文都必须经 OCR。
- 现有清洗稿 [`content/00-系统架构设计师考试大纲-清洗版/`](../../content/00-系统架构设计师考试大纲-清洗版/INDEX.md)
  来自更早的一份 **75 页**扫描件（`/Creator: vFlat`）的 OCR 结果。本 PDF 是那份文件
  **删除冗余页与重复页后的修订版**（正文页无删减），但两版的 PDF 页序已偏移、
  **逐页对照关系未建立**，因此清洗稿的 frontmatter 不标注 `source_pages`。
- 该 PDF 由 pdf-lib 重新导出，不是出版社电子版。
- 本文件已归档到维护者私有仓库
  [ruankao-senior-architecture-designer-sources](https://github.com/YoungHong1992/ruankao-senior-architecture-designer-sources)
  的 `00、[官方]系统架构设计师考试大纲.pdf`，固定提交号见
  [DATA_SOURCES.md](../../DATA_SOURCES.md) 的「源 PDF 私有归档清单」。

## 使用方式

把源 PDF 放到本目录后即可用于人工比对；`.gitignore` 会挡住 `*.pdf`，不会被误提交。
不要把 PDF、扫描页图或其下载链接提交到版本库，理由见 [AGENTS.md 的「内容与权利政策」](../../AGENTS.md#内容与权利政策)。
