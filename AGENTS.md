# AGENTS.md

本仓库**不是应用程序**，而是一个受治理的中文知识库：系统架构设计师考试的大纲、教材（OCR 提取）与历年真题，用 Python 脚本 + CI 强制一组内容不变量。完整规范见 [CLAUDE.md](CLAUDE.md)；下面是不读完整规范也**必须**遵守的部分。

## 运行环境：只能用 uv

解释器固定 Python 3.13（`.python-version`），依赖锁在 `uv.lock`。**不要调用系统 `python`/`python3`**：

```bash
uv run python scripts/validate_knowledge_base.py         # 主门禁，交付前必跑
uv run python scripts/build_exam_asset_audit.py --check   # 需要完整 git 历史
uv lock --check                                          # 改了 pyproject.toml 后必跑
```

主门禁只依赖标准库，**不要给它加第三方依赖**。第三方依赖只允许出现在 `audit` 依赖组（仅 `scripts/audit_textbook_pdf.py` 用，运行时加 `--group audit`）。

## 内容红线

1. **不造假。** 无法验证的题面、选项、空号、连线、答案，一律显式标“未恢复/不可裁决/待复核”，绝不写成已确认。不得臆造或重绘图表冒充原图（见 [FIGURE_POLICY.md](FIGURE_POLICY.md)）。
2. **17 组同名冲突禁止自动合并。** `02.历年真题/` 与 `02.历年真题(补充)/` 存在同名但内容不同的文件，禁止随机选择、自动拼接、覆盖或去重合并；2023 下半年综合知识的 B75 与 A65 两套题序同样禁止拼接。
3. **回忆版/解析版不是官方答案。** 来源冲突或证据不足时保留多版本并标“待复核”。
4. **不得提交**盗版 PDF、下载链接或访问凭据。教材/大纲/真题均为第三方内容，仓库不主张版权（见 [CONTENT_POLICY.md](CONTENT_POLICY.md)）。

## 读取约定：先索引，再按需加载

每个内容目录都有 `INDEX.md`；真题的统一入口是 [02.历年真题总索引.md](02.历年真题总索引.md)（机器可读版 `data/exams.json`）。**先读索引，再只打开需要的单章/单卷**，不要一次性载入全部 159 个 Markdown 文件。查真题只用索引标注的“首选文件”。

## 改内容必须同步账本

正文、`data/*.json` 三份账本、两份索引与校验脚本中的数字必须同时成立，否则 CI 必红。具体不变量清单见 [CLAUDE.md](CLAUDE.md#关键不变量改内容必须同步更新)。

## 换行符

`.md` 用 **CRLF**；`.py`/`.json`/`.yml`/`.yaml`/`.toml`/`uv.lock`/`.python-version` 用 **LF**（见 `.gitattributes`）。改错行尾会让 `data/exams.json` 的 `content_sha256` 漂移，CI 会失败。

## 提交

经 Pull Request 合并，不要直接推送受保护的 `main`。commit message 中不要添加任何 AI 工具署名或 `Co-Authored-By` 之类的尾注。流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。
