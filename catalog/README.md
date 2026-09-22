# catalog —— 机器可读清单

本目录是知识库结构的**唯一真相来源**。规模数字、目录归属、来源校验值只写在这里，
脚本和文档都从这里读取，不再在 README、AGENTS.md 和各索引里各抄一份。

## 文件

| 文件 | 内容 | 消费者 |
|---|---|---|
| [corpora.json](corpora.json) | 三套语料的目录归属、文档数量、来源 PDF 事实（页数、SHA-256、有无文本层） | `scripts/validate_knowledge_base.py`、将来的网页构建与 RAG 索引 |
| [exams.json](exams.json) | 真题 manifest：36 份 canonical、90 份来源版本路径、17 组同名冲突映射 | 同上，另供人工核对 [历年真题总索引](../content/02-历年真题总索引.md) |

## 约定

1. **数字只写一次。** `corpora.json` 的 `expected_documents` 与 `invariants` 是断言来源；
   校验器按它统计 `content/` 下的 frontmatter，不再硬编码 36、17、90。
2. **路径都相对仓库根**，使用 `/` 分隔，与 `exams.json` 保持一致。
3. **来源校验值以 `corpora.json` 为准**；[DATA_SOURCES.md](../DATA_SOURCES.md) 里的同一串 SHA-256
   由校验器断言必须出现，防止两处说法不一致。
4. 改动语料规模（新增一年真题、补一章正文）时，**先改这里，再改正文和索引**，最后跑
   `uv run python scripts/validate_knowledge_base.py`。

JSON 一律 LF 换行、UTF-8 无 BOM（见 `.gitattributes`）。
