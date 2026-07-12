#!/usr/bin/env python3
"""Build the deterministic, item-level exam asset audit.

The fixed baseline is a repository commit, so every legacy marker can be
recovered with ``git show`` without depending on the mutable working tree.
The script writes governance metadata only; it does not edit exam Markdown.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "exam_asset_audit.json"
BASELINE_COMMIT = "e02f60ca93e78217b3b6b9bdf7a6db964781741c"
BASELINE_TAG = "v2026.07.11"
REVIEWED_AT = "2026-07-12"

MARKER_RE = re.compile(r"原图未收录|原表未收录")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
QUESTION_TITLE_RE = re.compile(
    r"^(?:第\s*\d+\s*题|试题\s*(?:[一二三四五六七八九十]+|\d+))"
)
EXAM_NAME_RE = re.compile(
    r"^(?P<year>\d{4})年(?P<session>上半年|下半年)-系统架构设计师-"
    r"(?P<subject>综合知识|案例分析|论文)\.md$"
)

EXPECTED_FILE_COUNTS = {
    "02.历年真题-清洗版/2016年下半年-系统架构设计师-案例分析.md": 9,
    "02.历年真题-清洗版/2016年下半年-系统架构设计师-综合知识.md": 4,
    "02.历年真题-清洗版/2017年下半年-系统架构设计师-案例分析.md": 7,
    "02.历年真题-清洗版/2017年下半年-系统架构设计师-综合知识.md": 9,
    "02.历年真题-清洗版/2018年下半年-系统架构设计师-案例分析.md": 7,
    "02.历年真题-清洗版/2018年下半年-系统架构设计师-综合知识.md": 7,
    "02.历年真题-清洗版/2019年下半年-系统架构设计师-案例分析.md": 6,
    "02.历年真题-清洗版/2019年下半年-系统架构设计师-论文.md": 1,
    "02.历年真题-清洗版/2019年下半年-系统架构设计师-综合知识.md": 9,
    "02.历年真题-清洗版/2020年下半年-系统架构设计师-案例分析.md": 8,
    "02.历年真题-清洗版/2020年下半年-系统架构设计师-论文.md": 2,
    "02.历年真题-清洗版/2020年下半年-系统架构设计师-综合知识.md": 3,
    "02.历年真题-清洗版/2021年下半年-系统架构设计师-案例分析.md": 4,
    "02.历年真题-清洗版/2021年下半年-系统架构设计师-综合知识.md": 7,
    "02.历年真题-清洗版/2022年下半年-系统架构设计师-案例分析.md": 6,
    "02.历年真题-清洗版/2022年下半年-系统架构设计师-综合知识.md": 5,
    "02.历年真题-清洗版/2023年下半年-系统架构设计师-案例分析.md": 3,
    "02.历年真题-清洗版/2024年上半年-系统架构设计师-案例分析.md": 4,
    "02.历年真题-清洗版/2024年上半年-系统架构设计师-综合知识.md": 1,
    "02.历年真题-清洗版/2024年下半年-系统架构设计师-案例分析.md": 6,
    "02.历年真题-清洗版/2025年上半年-系统架构设计师-案例分析.md": 5,
    "02.历年真题-清洗版/2025年下半年-系统架构设计师-案例分析.md": 3,
}

PATH_2018_H2_COMPREHENSIVE = (
    "02.历年真题-清洗版/2018年下半年-系统架构设计师-综合知识.md"
)
PATH_2019_H2_ESSAY = "02.历年真题-清洗版/2019年下半年-系统架构设计师-论文.md"
PATH_2020_H2_ESSAY = "02.历年真题-清洗版/2020年下半年-系统架构设计师-论文.md"
PATH_2024_H1_CASE = "02.历年真题-清洗版/2024年上半年-系统架构设计师-案例分析.md"
PATH_2024_H1_COMPREHENSIVE = (
    "02.历年真题-清洗版/2024年上半年-系统架构设计师-综合知识.md"
)
PATH_2024_H2_CASE = "02.历年真题-清洗版/2024年下半年-系统架构设计师-案例分析.md"

# The six current manual limitations do not map one-to-one to the fixed legacy
# markers.  In particular, the legacy lines at 2024 H1 L201/L209 describe the
# embedded-reliability variant, while the current DDS/AP limitations come from
# another retained variant; 2024 H2 L139 is a ROS prompt, not the Nginx slot.
# Keep the manual limitations unbound instead of creating false provenance.
SOURCE_LIMITED_BINDINGS: dict[tuple[str, int], str] = {}
NON_ORIGINAL_BINDINGS = {
    (PATH_2019_H2_ESSAY, 111): "2019-h2-essay-q3-comparison-table",
}
RECOVERED_BINDINGS = {
    (PATH_2018_H2_COMPREHENSIVE, 19): "2018-h2-comprehensive-q1-table",
    (PATH_2020_H2_ESSAY, 69): "2020-h2-essay-q2-cloud-native-diagram-marker",
    (PATH_2020_H2_ESSAY, 71): "2020-h2-essay-q2-cloud-native-source-marker",
    (PATH_2024_H1_COMPREHENSIVE, 182): "2024-h1-comprehensive-q15-network",
}

# Baseline headings are immutable provenance.  When a later source-backed
# correction moves a carrier, record the current location separately instead
# of rewriting the historical nearest_question/nearest_heading values.
CURRENT_LOCATION_OVERRIDES = {
    (PATH_2024_H1_COMPREHENSIVE, 182): "第15题",
}

PROOF_SCOPES = {
    "reviewed_current_carrier": (
        "标记消失只证明载体已处理，语义证据见现行段落来源注，不单独证明官方性。"
    ),
    "source_limited": (
        "仅证明现行载体已明确记录来源限制；不证明原卷几何、空号或答案已恢复。"
    ),
    "non_original_substitute": (
        "仅证明现行载体有明确来源的学习性替代表；不证明其等同原解析图表或官方原表。"
    ),
    "recovered_structural": (
        "现行载体已完成结构化恢复；恢复范围与证据见现行题目来源注，"
        "本记录不单独证明其为官方原卷。"
    ),
}

SOURCE_LIMITED_VISUAL_ITEMS = [
    {
        "id": "2024-h1-case-q2-uml",
        "path": PATH_2024_H1_CASE,
        "location": "试题二 UML（1）～（9）",
        "limitation": (
            "唯一近时点图的作者明确称只记得大概；同日、次日独立回忆只能交叉确认"
            "“访客流程序列图补全”题型。该图与后期培训 PDF 在生命线名称、请求处理节点"
            "和消息编号分配上冲突，仍无官方逐空答案。"
        ),
        "current_handling": "两套结构及候选答案隔离记录，不合并为唯一官方版本。",
    },
    {
        "id": "2024-h1-case-q4-communication",
        "path": PATH_2024_H1_CASE,
        "location": "试题四 DDS/SOME-IP 通信框图",
        "limitation": (
            "近时回忆明确共有 6 个协议空，并提供已填技术参考图，但未保存原考试空白框图，"
            "无法确定具体挖掉哪 6 条协议边。"
        ),
        "current_handling": (
            "按 2024-05-27 参考图逐边恢复完整模块与 DDS/SOME-IP 标签，"
            "并明确不反推官方六空位置。"
        ),
    },
    {
        "id": "2024-h1-case-q4-ap-flow",
        "path": PATH_2024_H1_CASE,
        "location": "试题四自动驾驶 AP 流程图",
        "limitation": (
            "取得近时回忆的六空框图及九条箭头，但该图是考后重绘、没有（1）～（6）编号；"
            "节点名称来自同页转载的旧技术答案图，仍非官方原卷。"
        ),
        "current_handling": (
            "完整转录六个待填节点、已给高精地图及九条箭头，"
            "继续保留原卷版式、空号分配和官方答案限制。"
        ),
    },
    {
        "id": "2024-h2-case-q1-quality-table",
        "path": PATH_2024_H2_CASE,
        "location": "试题一质量属性分类表",
        "limitation": (
            "考试次日腾讯初始正文和修订只保存 a～e、g、h 的部分格位，并可裁定 b 预填可靠性、c 为（1）；"
            "其余行标签发生漂移，未固定（4）～（7）。2025-11-27 后期完整图又在 b/c 位置上冲突，"
            "仍缺官方原卷裁决。"
        ),
        "current_handling": "按近时材料裁定 b/c，晚期完整表单独隔离；不把漂移片段与后期行序拼成单一卷面。",
    },
    {
        "id": "2024-h2-case-q4-nginx-slot",
        "path": PATH_2024_H2_CASE,
        "location": "试题四 Web 架构 Nginx 空位",
        "limitation": (
            "前端顶部位置及后端预填 Nginx 可确认；腾讯文档考试次日 17:57 与 18:29 的两张"
            "考生重构分别记（3）和（7），后期模板另记（8），但无原卷截图可供裁决。"
        ),
        "current_handling": "恢复共同几何结构，并继续隔离（3）/（7）/（8）三套编号，不指定唯一最强候选。",
    },
    {
        "id": "2025-h2-case-q5-3-petri",
        "path": "02.历年真题-清洗版/2025年下半年-系统架构设计师-案例分析.md",
        "location": "试题五问题 3",
        "limitation": (
            "仅有裁切图 2；只能确认未知库所→T1→P2→T2→未知库所的局部链，"
            "缺完整 Petri 网、具体指令和可靠答案，固定页答案栏为“无”。"
        ),
        "current_handling": (
            "完整恢复问题 2 的货物接运网及表格，并逐项记录问题 3 的残片、表 2、"
            "固定 Git 历史与公开归档检索边界。"
        ),
    },
]

SOURCE_SEARCH_REFRESH = {
    "reviewed_at": REVIEWED_AT,
    "tool": "GitHub CLI 2.96.0 code search",
    "queries": [
        "2024年上半年 系统架构设计师 UML",
        "AP流程图 系统架构设计师",
        "SOME/IP DDS 2024",
        "2024年下半年 系统架构设计师 质量属性 Nginx",
        "质量属性分类表 系统架构设计师",
        "2025年下半年 系统架构设计师 Petri 货物接运",
        "货物接运 Petri",
    ],
    "indexed_code_results": 0,
    "revision_replay": {
        "document": "https://docs.qq.com/doc/DRlNVSkZLZkZ6eHF6",
        "revision_range": "1..14022",
        "initial_payload_sha256": "6d9f02975257f8673aa933e4d2ae42b678702f99fe6e91c071b8761a715fb256",
        "new_evidence": "考试次日 17:57 与 18:29 的 Nginx 重构分别采用（3）与（7），未能裁决唯一空号。",
    },
    "conclusion": (
        "2026-07-12 使用已登录的官方 GitHub CLI 刷新公开代码索引，并回放腾讯文档公开修订；"
        "新增证据纠正了 Nginx 的来源先后，却同时确认（3）/（7）同日冲突，仍未裁决六个来源受限视觉细节。"
    ),
    "proof_scope": (
        "零结果只覆盖 GitHub 当时向该账户返回的代码索引，不证明互联网、私有仓库、"
        "已删除历史或未索引二进制中不存在材料。"
    ),
}

NON_ORIGINAL_SUBSTITUTES = [
    {
        "id": "2019-h2-essay-q3-comparison-table",
        "path": PATH_2019_H2_ESSAY,
        "location": "试题三数据湖与数据仓库对照",
        "description": (
            "原解析图表未入库；当前表格是依据 AWS 与 Google Cloud 官方技术文档整理的"
            "非官方学习对照，不冒充原解析表。"
        ),
    }
]

ADDITIONAL_POSITIONS = [
    {
        "id": "2024-h1-comprehensive-q68-table",
        "origin": "additional_review",
        "path": "02.历年真题-清洗版/2024年上半年-系统架构设计师-综合知识.md",
        "baseline_line": None,
        "marker": None,
        "nearest_question": "第68题",
        "nearest_heading": "第68题",
        "context": (
            "甲、乙乳制品的两类原料消耗、库存与利润跨页表；现行载体已从固定"
            "第三方 PDF 第 5～6 页恢复，并完成线性规划计算校核。"
        ),
        "disposition": "recovered_structural",
        "proof_scope": PROOF_SCOPES["recovered_structural"],
        "description": "旧基线没有缺表标记；续审发现题干引用表格但正文无载体，并据固定 PDF 恢复和复算。",
    },
    {
        "id": "2024-h1-comprehensive-q69-table",
        "origin": "additional_review",
        "path": "02.历年真题-清洗版/2024年上半年-系统架构设计师-综合知识.md",
        "baseline_line": None,
        "marker": None,
        "nearest_question": "第69题",
        "nearest_heading": "第69题",
        "context": (
            "A～H 八项作业的紧前关系、工期与用工表；现行载体已从固定第三方 PDF"
            "逐格恢复，并记录其资源排程和非官方答案边界。"
        ),
        "disposition": "recovered_structural",
        "proof_scope": PROOF_SCOPES["recovered_structural"],
        "description": "旧基线没有缺表标记；续审发现表 1 仍缺失，并据固定 PDF 第 6/22 页恢复和核对。",
    },
    {
        "id": "2024-h2-comprehensive-q73-table",
        "origin": "additional_review",
        "path": "02.历年真题-清洗版/2024年下半年-系统架构设计师-综合知识.md",
        "baseline_line": None,
        "marker": None,
        "nearest_question": "第73题",
        "nearest_heading": "第73题",
        "context": (
            "项目 A、B、C、D 四道工序的赶工题；现行载体已恢复完整六列表、选项、"
            "答案和工程费用计算校核。"
        ),
        "disposition": "recovered_structural",
        "proof_scope": PROOF_SCOPES["recovered_structural"],
        "description": "旧基线没有统一缺表标记；终审时发现并恢复六列表、选项、答案和计算校核。",
    },
    {
        "id": "2025-h1-comprehensive-q43-table",
        "origin": "additional_review",
        "path": "02.历年真题-清洗版/2025年上半年-系统架构设计师-综合知识.md",
        "baseline_line": None,
        "marker": None,
        "nearest_question": "第43题",
        "nearest_heading": "第43题",
        "context": (
            "A～J 十项作业的紧前关系与工期表；现行载体已从固定公开图片恢复完整表格，"
            "并校核 D 推迟开始后总工期由 24 天变为 25 天。"
        ),
        "disposition": "recovered_structural",
        "proof_scope": PROOF_SCOPES["recovered_structural"],
        "description": "旧基线没有缺表标记；终审时发现题干缺失作业表，并据固定图片恢复和复算。",
    },
]


def run_git(*args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return process.stdout.decode("utf-8-sig")


def baseline_text(relative_path: str) -> str:
    return run_git("show", f"{BASELINE_COMMIT}:{relative_path}")


def exam_slug(relative_path: str) -> str:
    match = EXAM_NAME_RE.match(Path(relative_path).name)
    if not match:
        raise AssertionError(f"unexpected canonical exam name: {relative_path}")
    session = {"上半年": "h1", "下半年": "h2"}[match.group("session")]
    subject = {
        "综合知识": "comprehensive",
        "案例分析": "case-analysis",
        "论文": "essay",
    }[match.group("subject")]
    return f"{match.group('year')}-{session}-{subject}"


def clipped(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def compact_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def clipped_around(text: str, needle: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    position = text.find(needle)
    if position < 0:
        return clipped(text, limit)
    start = max(0, position - 40)
    end = min(len(text), start + limit - 2)
    start = max(0, end - (limit - 2))
    body = text[start:end]
    return f"{'…' if start else ''}{body}{'…' if end < len(text) else ''}"


def short_context(lines: list[str], line_index: int, marker: str) -> str:
    def adjacent(step: int) -> str | None:
        index = line_index + step
        while 0 <= index < len(lines):
            value = compact_line(lines[index])
            if value and value not in {">", "---"}:
                return clipped(value, 100)
            index += step
        return None

    marker_line = clipped_around(compact_line(lines[line_index]), marker, 100)
    parts = [adjacent(-1), marker_line, adjacent(1)]
    return clipped(" | ".join(part for part in parts if part), 280)


def headings_at(lines: list[str], line_index: int) -> tuple[str, str]:
    nearest_heading = ""
    nearest_question = ""
    for line in lines[: line_index + 1]:
        match = HEADING_RE.match(line)
        if not match:
            continue
        title = compact_line(match.group(2))
        nearest_heading = title
        if QUESTION_TITLE_RE.match(title):
            nearest_question = title
    if not nearest_heading:
        nearest_heading = "（无 Markdown 标题）"
    if not nearest_question:
        nearest_question = nearest_heading
    return nearest_question, nearest_heading


def disposition_for(relative_path: str, line_number: int) -> tuple[str, str | None]:
    key = (relative_path, line_number)
    if key in RECOVERED_BINDINGS:
        return "recovered_structural", RECOVERED_BINDINGS[key]
    if key in SOURCE_LIMITED_BINDINGS:
        return "source_limited", SOURCE_LIMITED_BINDINGS[key]
    if key in NON_ORIGINAL_BINDINGS:
        return "non_original_substitute", NON_ORIGINAL_BINDINGS[key]
    return "reviewed_current_carrier", None


def baseline_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for relative_path in EXPECTED_FILE_COUNTS:
        lines = baseline_text(relative_path).splitlines()
        for line_index, line in enumerate(lines):
            for occurrence, match in enumerate(MARKER_RE.finditer(line), start=1):
                line_number = line_index + 1
                marker = match.group(0)
                marker_slug = {"原图未收录": "figure", "原表未收录": "table"}[marker]
                nearest_question, nearest_heading = headings_at(lines, line_index)
                disposition, manual_item_id = disposition_for(relative_path, line_number)
                record: dict[str, object] = {
                    "id": (
                        f"{exam_slug(relative_path)}-baseline-l{line_number:04d}-"
                        f"{marker_slug}-{occurrence:02d}"
                    ),
                    "origin": "baseline_marker",
                    "path": relative_path,
                    "baseline_line": line_number,
                    "marker": marker,
                    "nearest_question": nearest_question,
                    "nearest_heading": nearest_heading,
                    "context": short_context(lines, line_index, marker),
                    "disposition": disposition,
                    "proof_scope": PROOF_SCOPES[disposition],
                }
                if manual_item_id:
                    record["manual_item_id"] = manual_item_id
                current_location = CURRENT_LOCATION_OVERRIDES.get(
                    (relative_path, line_number)
                )
                if current_location:
                    record["current_location"] = current_location
                records.append(record)
    return records


def count_current_markers(relative_path: str) -> int:
    text = (ROOT / relative_path).read_text(encoding="utf-8-sig")
    return len(MARKER_RE.findall(text))


def attach_manual_mappings(
    items: list[dict[str, object]], records: list[dict[str, object]], disposition: str
) -> list[dict[str, object]]:
    manual_to_position = {
        str(record["manual_item_id"]): str(record["id"])
        for record in records
        if record.get("manual_item_id") and record["disposition"] == disposition
    }
    enriched: list[dict[str, object]] = []
    for original in items:
        item = dict(original)
        position_id = manual_to_position.get(str(item["id"]))
        item["baseline_position_id"] = position_id
        item["baseline_mapping"] = (
            "mapped_to_fixed_baseline_marker"
            if position_id
            else "no_matching_legacy_marker_in_fixed_baseline"
        )
        item["disposition"] = disposition
        item["proof_scope"] = PROOF_SCOPES[disposition]
        enriched.append(item)
    return enriched


def validate_records(
    baseline: list[dict[str, object]], positions: list[dict[str, object]], files: list[dict[str, object]]
) -> None:
    if len(EXPECTED_FILE_COUNTS) != 22:
        raise AssertionError("expected 22 canonical files")
    if sum(EXPECTED_FILE_COUNTS.values()) != 116:
        raise AssertionError("expected file baseline counts to sum to 116")
    if len(baseline) != 116:
        raise AssertionError(f"expected 116 baseline records, found {len(baseline)}")
    if len(positions) != 120:
        raise AssertionError(f"expected 116 + 4 = 120 records, found {len(positions)}")

    ids = [str(record["id"]) for record in positions]
    if len(ids) != len(set(ids)):
        duplicates = sorted(key for key, value in Counter(ids).items() if value > 1)
        raise AssertionError(f"duplicate position ids: {duplicates}")

    observed = Counter(str(record["path"]) for record in baseline)
    if dict(observed) != EXPECTED_FILE_COUNTS:
        raise AssertionError(
            "per-file baseline counts changed:\n"
            + json.dumps(dict(observed), ensure_ascii=False, indent=2)
        )
    if any(int(item["current_legacy_marker_count"]) for item in files):
        raise AssertionError("current canonical files still contain legacy markers")

    required = {
        "id",
        "origin",
        "path",
        "baseline_line",
        "marker",
        "nearest_question",
        "nearest_heading",
        "context",
        "disposition",
        "proof_scope",
    }
    for record in positions:
        missing = required - set(record)
        if missing:
            raise AssertionError(f"{record.get('id')}: missing fields {sorted(missing)}")
        if record["disposition"] not in PROOF_SCOPES:
            raise AssertionError(f"{record['id']}: unknown disposition")
        if record["proof_scope"] != PROOF_SCOPES[str(record["disposition"])]:
            raise AssertionError(f"{record['id']}: proof scope does not match disposition")


def build_audit() -> dict[str, object]:
    resolved = run_git("rev-parse", f"{BASELINE_COMMIT}^{{commit}}").strip()
    if resolved != BASELINE_COMMIT:
        raise AssertionError(f"baseline commit mismatch: {resolved}")

    baseline = baseline_records()
    positions = [*baseline, *(dict(item) for item in ADDITIONAL_POSITIONS)]
    files = [
        {
            "path": relative_path,
            "baseline_positions": expected_count,
            "current_legacy_marker_count": count_current_markers(relative_path),
        }
        for relative_path, expected_count in EXPECTED_FILE_COUNTS.items()
    ]
    validate_records(baseline, positions, files)

    source_limited = attach_manual_mappings(
        SOURCE_LIMITED_VISUAL_ITEMS, baseline, "source_limited"
    )
    if len(source_limited) != 6:
        raise AssertionError("expected six source-limited visual items after recovering 2018 Q1")
    if any(item["id"] == "2018-h2-comprehensive-q1-table" for item in source_limited):
        raise AssertionError("recovered 2018 Q1 must not remain source-limited")
    if any(item["baseline_position_id"] is not None for item in source_limited):
        raise AssertionError("current manual limits must not be falsely mapped to legacy markers")

    substitutes = attach_manual_mappings(
        NON_ORIGINAL_SUBSTITUTES, baseline, "non_original_substitute"
    )
    if substitutes[0]["baseline_position_id"] is None:
        raise AssertionError("2019 essay substitute must map to its baseline marker")

    disposition_counts = Counter(str(record["disposition"]) for record in positions)
    expected_dispositions = {
        "reviewed_current_carrier": 111,
        "recovered_structural": 8,
        "non_original_substitute": 1,
    }
    if dict(disposition_counts) != expected_dispositions:
        raise AssertionError(
            "position disposition counts changed: "
            + json.dumps(dict(disposition_counts), ensure_ascii=False, sort_keys=True)
        )
    disposition_summary = {
        name: disposition_counts.get(name, 0)
        for name in (
            "reviewed_current_carrier",
            "recovered_structural",
            "source_limited",
            "non_original_substitute",
        )
    }

    return {
        "schema_version": 2,
        "reviewed_at": REVIEWED_AT,
        "field_definitions": {
            "positions": "120 个逐项审计记录；前 116 项来自固定基线标记，后 4 项为续审新增 2024 上 Q68/Q69、2024 下 Q73 与 2025 上 Q43。",
            "id": "由考试、固定基线行号、标记类型和行内序号组成的稳定唯一标识。",
            "origin": "baseline_marker 表示固定基线标记；additional_review 表示终审新增点位。",
            "baseline_line": "标记在固定基线文件中的 1 基行号；终审新增点位为 null。",
            "marker": "固定基线中的原图未收录/原表未收录标记；终审新增点位为 null。",
            "nearest_question": "标记之前最近的题号或主试题标题。",
            "nearest_heading": "标记之前最近的 Markdown 标题，可能细化到问题或解析小节。",
            "current_location": "来源校正导致题号移动时记录现行位置；不覆盖固定基线中的历史题号。",
            "context": "基线标记前后相邻非空行组成的截短上下文。",
            "disposition": "现行载体的处理归类，不等同于官方性结论。",
            "proof_scope": "该归类能够证明及不能证明的证据边界。",
        },
        "baseline": {
            "commit": BASELINE_COMMIT,
            "tag": BASELINE_TAG,
            "marker_patterns": ["原图未收录", "原表未收录"],
            "explicit_positions": len(baseline),
            "description": (
                "固定基线中 22 份 canonical 正文的显式图表缺失标记；"
                "索引汇总标记不计入，逐项记录由 git show 直接生成。"
            ),
        },
        "additional_positions": [dict(item) for item in ADDITIONAL_POSITIONS],
        "summary": {
            "total_positions_reviewed": len(positions),
            "baseline_positions": len(baseline),
            "additional_positions": len(ADDITIONAL_POSITIONS),
            "files_with_baseline_positions": len(files),
            "current_legacy_marker_count": sum(
                int(item["current_legacy_marker_count"]) for item in files
            ),
            "source_limited_visual_items": len(source_limited),
            "positions_by_disposition": disposition_summary,
            "conclusion": (
                "120 个点位均有逐项载体记录；标记消失只证明载体已处理。"
                "语义证据、来源限制和非原版替代边界以现行段落来源注及人工限制清单为准。"
            ),
        },
        "files": files,
        "positions": positions,
        "source_limited_visual_items": source_limited,
        "source_search_refresh": dict(SOURCE_SEARCH_REFRESH),
        "non_original_substitutes": substitutes,
    }


def rendered_json() -> str:
    return json.dumps(build_audit(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that data/exam_asset_audit.json exactly matches generated output",
    )
    args = parser.parse_args()

    try:
        content = rendered_json()
    except (AssertionError, OSError, RuntimeError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8-sig") if OUTPUT_PATH.is_file() else ""
        if current != content:
            print(f"ERROR: {OUTPUT_PATH.relative_to(ROOT)} is not reproducible", file=sys.stderr)
            return 1
        print("exam asset audit is reproducible: 116 baseline + 4 additional = 120 records")
        return 0

    OUTPUT_PATH.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT_PATH.relative_to(ROOT)}: 120 item-level records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
