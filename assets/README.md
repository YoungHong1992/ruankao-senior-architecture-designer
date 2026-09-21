# assets —— 图片与图表资产

本目录存放**依法取得、并与原图逐一对照**后落盘的图片与矢量图，供正文以 Markdown 图片语法引用。
目前为空：仓库尚未收录任何原书插图。

## 目录约定

```text
assets/figures/<语料 id>/<章节 slug>/<原图号>.<svg|png>
```

- `<语料 id>` 取 [catalog/corpora.json](../catalog/corpora.json) 中的 `outline` / `textbook` / `exams`；
- `<章节 slug>` 取该文件 frontmatter 的 `slug`，例如 `ch07-architecture-design-fundamentals`；
- `<原图号>` 用原书图号，例如 `figure-7-3`；无编号图用 `figure-7-unnumbered-1`。

例：教材第 7 章图 7-3 → `assets/figures/textbook/ch07-architecture-design-fundamentals/figure-7-3.svg`。

## 硬性前提

**手中没有原图就不要画图。** 仅凭 OCR 残留标签串、上下文散文或领域常识"还原"的图是生成内容，
一律禁止入库——仓库此前 325 个凭空生成的 Mermaid 示意图即因此被全部移除，
位置登记在 [verification/待重画图表清单.md](../verification/待重画图表清单.md)。

补画与形式选择（表格 / Mermaid / 独立 SVG）的完整规则见
[AGENTS.md 的「图表与公式处理」](../AGENTS.md#图表与公式处理)。其中两条最容易踩：

1. SVG 必须是**独立文件**并用图片语法引用——GitHub 会剥掉内联 `<svg>`，内联图在网页上不显示；
2. 落盘前移除水印、个人信息与无关页边内容，并补 `<title>` / `<desc>` 无障碍标注。

## 体积

引入大批量位图前先评估 Git LFS 与再分发权利；能用 SVG 或 Markdown 表格表达的，不要放位图。
