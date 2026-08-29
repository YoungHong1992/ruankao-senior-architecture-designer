## 修改内容

- （请简要说明）

## 来源与证据

- 资料/版本：
- 页码/题号/URL：
- 访问日期：

## 已知限制

- （请说明已知限制；如无则填写“无”）

## 验证

- [ ] 已阅读 `CLAUDE.md`（或 `AGENTS.md`）、内容政策和适用的清洗/图表规范
- [ ] 未提交无权公开的源文件、凭据或敏感信息
- [ ] 已运行 `uv lock --check`
- [ ] 已运行 `uv run python scripts/validate_knowledge_base.py`（输出 `PASSED: 0 errors`）
- [ ] 已运行 `uv run python scripts/build_exam_asset_audit.py --check`
- [ ] 已运行 `uv run python scripts/build_outline_audit.py --check`（改过大纲正文时先去掉 `--check` 重建并提交账本）
- [ ] 自动检查通过
