#!/usr/bin/env python3
"""Build a reproducible page-level audit for the locally held tutorial PDF.

This helper is intentionally not part of CI because the copyrighted source PDF is
not stored in the repository. It requires pypdf and writes only measurements and
source hashes, never extracted textbook text or scanned pages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - depends on the local audit runtime
    raise SystemExit("pypdf is required: install it or use the bundled Codex runtime") from exc


ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "01.系统架构设计师教材-清洗版"
EXPECTED_SHA256 = "ee45900f4622d71539980cfe1bddbcd898fba97ca13ada6df1cbdc215135c2f8"
BASELINE_COMMIT = "e02f60ca93e78217b3b6b9bdf7a6db964781741c"
HISTORICAL_COUNT_COMMIT = "3ce44b168efdd68d4c876631710c1b938af145ba"

# The scalar historical report said "at least 14" spliced tables but did not
# preserve its original selection.  The fixed baseline nevertheless contains
# a larger, independently reproducible set of table carriers whose cells were
# visibly flattened into one or more concatenated lines.  Each entry below is
# verified against the fixed baseline, the locally held PDF page inventory and
# a current pipe-table carrier.  This conservative reconstruction deliberately
# does not claim that its 15 entries are the exact undocumented original 14.
HISTORICAL_SPLICED_TABLE_CANDIDATES: dict[str, dict[str, object]] = {
    "2-2": {
        "chapter": 2,
        "baseline_title_line": 397,
        "baseline_flattened_lines": (399, 399),
        "baseline_needles": ("ALPHA BETA REPORT SQRT", "张军 RWX"),
        "pdf_reference_pages": [50],
    },
    "2-4": {
        "chapter": 2,
        "baseline_title_line": 682,
        "baseline_flattened_lines": (684, 684),
        "baseline_needles": ("等级失效状态简要说明目标数量", "A级灾难性"),
        "pdf_reference_pages": [63],
    },
    "2-5": {
        "chapter": 2,
        "baseline_title_line": 1115,
        "baseline_flattened_lines": (1117, 1117),
        "baseline_needles": ("VT DS FTMA CNIP/CMIS MHS", "物理层 802.3"),
        "pdf_reference_pages": [82],
    },
    "2-6": {
        "chapter": 2,
        "baseline_title_line": 1129,
        "baseline_flattened_lines": (1131, 1131),
        "baseline_needles": (
            "ISO/OSI模型 TCP/IP协议 TCP/IP模型",
            "Token-Ring/IEEE 802.3",
        ),
        "pdf_reference_pages": [82, 83],
    },
    "2-7": {
        "chapter": 2,
        "baseline_title_line": 1560,
        "baseline_flattened_lines": (1562, 1562),
        "baseline_needles": ("利用计算机形成三维交互场景", "增强式VR"),
        "pdf_reference_pages": [101],
    },
    "3-1": {
        "chapter": 3,
        "baseline_title_line": 578,
        "baseline_flattened_lines": (580, 580),
        "baseline_needles": (
            "系统专家系统一般计算机系统功能",
            "处理问题种类",
        ),
        "pdf_reference_pages": [139],
    },
    "4-1": {
        "chapter": 4,
        "baseline_title_line": 599,
        "baseline_flattened_lines": (601, 601),
        "baseline_needles": ("值名称值(REG_DWORD)", "TcpMaxPortsExhausted"),
        "pdf_reference_pages": [177],
    },
    "4-2": {
        "chapter": 4,
        "baseline_title_line": 608,
        "baseline_flattened_lines": (610, 610),
        "baseline_needles": ("值名称值(REG_DWORD)EnableICMPRedirect",),
        "pdf_reference_pages": [178],
    },
    "4-3": {
        "chapter": 4,
        "baseline_title_line": 618,
        "baseline_flattened_lines": (620, 620),
        "baseline_needles": ("值名称值(REG_DWORD)EnableDcadGWDetect",),
        "pdf_reference_pages": [178],
    },
    "5-1": {
        "chapter": 5,
        "baseline_title_line": 595,
        "baseline_flattened_lines": (597, 597),
        "baseline_needles": (
            "非直接耦合两个模块之间没有直接关系",
            "一个模块直接访问另一个模块的内部数据",
        ),
        "pdf_reference_pages": [206],
    },
    "5-2": {
        "chapter": 5,
        "baseline_title_line": 602,
        "baseline_flattened_lines": (604, 604),
        "baseline_needles": ("功能内聚完成一个单一功能", "偶然内聚"),
        "pdf_reference_pages": [207],
    },
    "12-13": {
        "chapter": 12,
        "baseline_title_line": 863,
        "baseline_flattened_lines": (865, 865),
        "baseline_needles": ("企业最大的业务范围是什么", "时间周期"),
        "pdf_reference_pages": [441],
    },
    "17-1": {
        "chapter": 17,
        "baseline_title_line": 699,
        "baseline_flattened_lines": (701, 710),
        "baseline_needles": ("无环路，不启用STP", "模型四", "生成树"),
        "pdf_reference_pages": [635, 636],
    },
    "18-2": {
        "chapter": 18,
        "baseline_title_line": 674,
        "baseline_flattened_lines": (674, 674),
        "baseline_needles": (
            "Oracle支持的基于DBMS的完整性约束",
            "非空约束",
            "通过触发器",
        ),
        "pdf_reference_pages": [671],
    },
    "19-1": {
        "chapter": 19,
        "baseline_title_line": 349,
        "baseline_flattened_lines": (351, 351),
        "baseline_needles": (
            "对比内容 Lambda架构 Kappa架构",
            "流式全量处理",
        ),
        "pdf_reference_pages": [698],
    },
}

NUMBER_PATTERNS = {
    "figure": re.compile(r"图\s*(\d{1,2})\s*[-—]\s*(\d{1,2})"),
    "table": re.compile(r"表\s*(\d{1,2})\s*[-—]\s*(\d{1,2})"),
}
MARKDOWN_CARRIER_PATTERNS = {
    "figure": re.compile(
        r"^\s*>\s*(?:\*\*)?图\s*(\d{1,2})\s*[-—]\s*(\d{1,2})"
    ),
    "table": re.compile(
        r"^\s*(?:>\s*)?(?:\*\*)?表\s*(\d{1,2})\s*[-—]\s*(\d{1,2})"
    ),
}
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")

BASELINE_PROOF_SCOPE = (
    "固定基线行只证明当时存在缺图、缺表或错位状态；现行载体行只证明载体存在，"
    "语义、数值与版式准确性仍以各章来源注和人工复核为准。"
)
INVENTORY_PROOF_SCOPE = (
    "PDF 页码来自文本层中的图表号引用，Markdown 行号来自独立载体标题；"
    "二者建立编号级可追溯性，不单独证明图形几何或表格单元格逐项一致。"
)

FORMULA_TOPICS = {
    "natural_join": {
        "label": "第 6 章自然连接公式",
        "current_needles": (r"R\bowtie S=", r"\pi_{X\cup B\cup Y}"),
    },
    "random_walk": {
        "label": "第 8 章随机游走相似度递推公式",
        "current_needles": (r"K(A_x,A_y)=", r"R_\infty(h_1,h'_1)="),
    },
}

# These formula positions were not represented by the two explicit formula-status
# markers in the fixed baseline.  They were discovered independently during the
# full 708-page visual/text review, so they remain separate from the historical
# two-item formula inventory and do not change the historical 199-position set.
ADDITIONAL_UNMARKED_FORMULA_SPECS: tuple[dict[str, object], ...] = (
    {
        "id": "textbook-ch02-full-review-p0061-formula-reliability-range",
        "topic": "reliability_range",
        "label": "第 2 章安全攸关系统可靠性指标数量级",
        "chapter": 2,
        "pdf_reference_pages": [61],
        "printed_pages": [51],
        "current_needles": (
            r"$10^{-6}～10^{-9}$",
            "FreeSky-X/systemarchitect 固定提交",
        ),
        "baseline_needles": ("10?～10°",),
        "supporting_evidence": {
            "repository": "FreeSky-X/systemarchitect",
            "commit": "0e9b17f3fbd1590ecc0e5f664c2031068e52b9d0",
            "path": "files/unit2/2.4.3嵌入式软件的组成及特点.md",
            "git_blob": "de5c8cf984f8f5844cc7b37af5edc84c0a4e7b1b",
            "fixed_excerpt": "10-6O10-9",
            "purpose": "本地 PDF 上标不可辨时的固定第三方 OCR 补证",
        },
        "proof_scope": (
            "本地 PDF 物理页 61 的两个上标在文本层及高分辨率渲染中均不可辨；"
            "固定第三方 OCR 同段转录 `10-6O10-9` 为恢复 `10^{-6}～10^{-9}` "
            "提供透明补证，不声称本地 PDF 字形直接清晰可读。"
        ),
    },
    {
        "id": "textbook-ch02-full-review-p0070-formula-shannon-capacity",
        "topic": "shannon_capacity",
        "label": "第 2 章香农信道容量公式",
        "chapter": 2,
        "pdf_reference_pages": [70],
        "printed_pages": [60],
        "current_needles": (
            r"C=B\log_2\left(1+\frac{S}{N}\right)",
            "香农公式（2-1）",
        ),
        "baseline_needles": ("C=B×log (1+)",),
    },
    {
        "id": "textbook-ch02-full-review-p0113-formula-amdahl-speedup",
        "topic": "amdahl_speedup",
        "label": "第 2 章阿姆达尔加速比公式组",
        "chapter": 2,
        "pdf_reference_pages": [113],
        "printed_pages": [103],
        "current_needles": (
            r"S=\frac{T_{\mathrm{old}}}{T_{\mathrm{new}}}",
            r"T_{\mathrm{new}}=T_{\mathrm{old}}\left[(1-F)+\frac{F}{S_e}\right]",
            r"\frac{1}{(1-F)+\frac{F}{S_e}}",
            "恢复式（2-2）～（2-4）",
        ),
        "baseline_needles": (
            "新的执行时间=原来的执行时间",
            "总加速比= 1",
        ),
    },
    {
        "id": "textbook-ch04-full-review-p0162-formula-rsa-exponents",
        "topic": "rsa_exponents",
        "label": "第 4 章 RSA 指数与模运算公式组",
        "chapter": 4,
        "pdf_reference_pages": [162],
        "printed_pages": [152],
        "current_needles": (
            r"$10^{100}$",
            r"$2^k<n$",
            r"ed\equiv1\pmod z",
            r"C=P^e\pmod n",
            r"P=C^d\pmod n",
            "PDF 物理页 162",
        ),
        "baseline_needles": ("1010°", "2k<n", "P°", "Cd(modn)"),
    },
    {
        "id": "textbook-ch04-full-review-p0170-formula-keyspace-primality",
        "topic": "keyspace_primality",
        "label": "第 4 章密钥空间与素性试除公式组",
        "chapter": 4,
        "pdf_reference_pages": [170, 171],
        "printed_pages": [160, 161],
        "current_needles": (
            "密钥空间为 $2^N$",
            r"$N^{1/2}$",
            r"$10^{160}$",
            "PDF 物理页 170～171",
        ),
        "baseline_needles": ("密钥空间为2^", "N1/2", "10160"),
    },
)

ADDITIONAL_FIGURE_CONTENT_CLASSIFICATION = {
    "2-4": {
        "policy_class": "B",
        "content_impact": "graphic_detail_only",
        "classification_basis": "相邻正文已说明关系模型和二维表语义；图仅给学生/选课关系的版式实例。",
    },
    "2-25": {
        "policy_class": "A",
        "content_impact": "critical_content_incomplete",
        "classification_basis": "正文只列 UML 结构事物名称；图中的类、接口、构件等标准图形记法承载独立知识。",
    },
    "2-26": {
        "policy_class": "A",
        "content_impact": "critical_content_incomplete",
        "classification_basis": "正文只列 UML 行为事物名称；消息、状态和活动的图形记法需要图表才能完整表达。",
    },
    "3-1": {
        "policy_class": "A",
        "content_impact": "critical_content_incomplete",
        "classification_basis": "图承载传票、账簿、报表与统计/分类之间的事务处理流向，正文未逐边列出。",
    },
    "3-12": {
        "policy_class": "B",
        "content_impact": "graphic_detail_only",
        "classification_basis": "正文已明确数据库、模型库和对话三个子系统的三角关系，图只可视化该关系。",
    },
    "4-8": {
        "policy_class": "B",
        "content_impact": "graphic_detail_only",
        "classification_basis": "正文已逐项说明 Client、Handler、Agent 的部署位置、控制方向和攻击目标。",
    },
    "17-15": {
        "policy_class": "B",
        "content_impact": "graphic_detail_only",
        "classification_basis": "正文已说明用户计算机经 LAN/WAN 远程访问专用 NAS，图不增加必要协议语义。",
    },
    "17-17": {
        "policy_class": "B",
        "content_impact": "graphic_detail_only",
        "classification_basis": "正文已完整说明应用、控制、数据三平面以及 NBI/SBI 接口方向。",
    },
    "17-19": {
        "policy_class": "B",
        "content_impact": "graphic_detail_only",
        "classification_basis": "正文已列明双栈节点同时支持 IPv4/IPv6、TCP/UDP 及共同链路/物理层。",
    },
    "19-12": {
        "policy_class": "B",
        "content_impact": "graphic_detail_only",
        "classification_basis": "正文已明确 Kafka 后分流至 Flink 与 ElasticSearch 的完整 Kappa 数据路径。",
    },
    "19-13": {
        "policy_class": "A",
        "content_impact": "critical_content_incomplete",
        "classification_basis": "里约奥运案例的平台层次、具体组件和批/速两条链路未由相邻正文逐项展开。",
    },
    "19-14": {
        "policy_class": "B",
        "content_impact": "graphic_detail_only",
        "classification_basis": "相邻案例正文已分段说明 Kafka、批处理、实时处理、第三方数据缺口与应用需求。",
    },
}

# Physical PDF pages are 1-based. Page 721 is a back-cover advertisement and is
# excluded from chapter 20 under the repository cleaning rules.
CHAPTER_RANGES = {
    1: (13, 33),
    2: (34, 114),
    3: (115, 154),
    4: (155, 184),
    5: (185, 227),
    6: (228, 257),
    7: (258, 280),
    8: (281, 314),
    9: (315, 339),
    10: (340, 378),
    11: (379, 412),
    12: (413, 458),
    13: (459, 489),
    14: (490, 519),
    15: (520, 548),
    16: (549, 606),
    17: (607, 640),
    18: (641, 683),
    19: (684, 709),
    20: (710, 720),
}

# Full-review work combines the earlier detailed reviews of chapters 8 and 10
# with four additional non-overlapping visual batches.  Contact sheets use a
# maximum 3x3 grid; ambiguous or low-coverage pages were reopened as individual
# renders at original detail.  The renders are temporary local review aids and
# are intentionally not committed to the repository.
FULL_REVIEW_PHASES: tuple[dict[str, object], ...] = (
    {
        "phase": "prior_detailed",
        "chapters": [8, 10],
        "physical_page_ranges": [[281, 314], [340, 378]],
        "page_count": 73,
        "generated_contact_sheet_count": 9,
        "contact_sheets_used_for_review": 0,
        "review_origin": "prior_detailed_review",
        "review_basis": "既有逐页渲染与详细目视复核；本轮生成的9张联系表不作为完成声明依据",
    },
    {
        "phase": "A",
        "chapters": [1, 2, 3, 4, 5, 6],
        "physical_page_ranges": [[13, 257]],
        "page_count": 245,
        "generated_contact_sheet_count": 30,
        "contact_sheets_used_for_review": 30,
        "review_origin": "additional_full_review",
    },
    {
        "phase": "B",
        "chapters": [7, 9, 11, 12, 13],
        "physical_page_ranges": [[258, 280], [315, 339], [379, 489]],
        "page_count": 159,
        "generated_contact_sheet_count": 20,
        "contact_sheets_used_for_review": 20,
        "review_origin": "additional_full_review",
    },
    {
        "phase": "C",
        "chapters": [14, 15, 16, 17, 18],
        "physical_page_ranges": [[490, 683]],
        "page_count": 194,
        "generated_contact_sheet_count": 24,
        "contact_sheets_used_for_review": 24,
        "review_origin": "additional_full_review",
    },
    {
        "phase": "D",
        "chapters": [19, 20],
        "physical_page_ranges": [[684, 720]],
        "page_count": 37,
        "generated_contact_sheet_count": 5,
        "contact_sheets_used_for_review": 5,
        "review_origin": "additional_full_review",
    },
)

FULL_REVIEW_RENDER_METADATA: dict[str, object] = {
    "generated_contact_sheet_count": 88,
    "prior_phase_generated_contact_sheet_count": 9,
    "contact_sheets_used_for_current_full_review": 79,
    "prior_detailed_page_count": 73,
    "additional_full_review_page_count": 635,
    "combined_review_page_count": 708,
    "contact_sheet_grid": "3x3",
    "maximum_pages_per_contact_sheet": 9,
    "inspection_detail": "original",
    "single_page_escalation": "低覆盖、复杂图表、疑似截断、错页或异常空白页单独放大复核",
    "temporary_artifact_root": "tmp/pdfs/textbook_full_review",
    "artifacts_committed": False,
}

CHAPTER_FILES = {
    int(match.group(1)): path
    for path in CLEAN_DIR.glob("第*.md")
    if (match := re.match(r"第(\d+)章-", path.name))
}


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
        raise SystemExit(f"git {' '.join(args)} failed: {message}")
    return process.stdout.decode("utf-8-sig")


def baseline_text(path: Path) -> str:
    relative_path = path.relative_to(ROOT).as_posix()
    return run_git("show", f"{BASELINE_COMMIT}:{relative_path}")


def number_key(number: str) -> tuple[int, int]:
    chapter, item = number.split("-", maxsplit=1)
    return int(chapter), int(item)


def number_from_match(match: re.Match[str]) -> str:
    return f"{int(match.group(1))}-{int(match.group(2))}"


def compact_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def clipped(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def clipped_around(text: str, needle: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    position = text.find(needle)
    if position < 0:
        return clipped(text, limit)
    start = max(0, position - 45)
    end = min(len(text), start + limit - 2)
    start = max(0, end - (limit - 2))
    body = text[start:end]
    return f"{'…' if start else ''}{body}{'…' if end < len(text) else ''}"


def short_context(lines: list[str], line_index: int, needle: str) -> str:
    def adjacent(step: int) -> str | None:
        index = line_index + step
        while 0 <= index < len(lines):
            value = compact_line(lines[index])
            if value and value not in {">", "---"}:
                return clipped(value, 100)
            index += step
        return None

    marker_line = clipped_around(compact_line(lines[line_index]), needle, 110)
    parts = [adjacent(-1), marker_line, adjacent(1)]
    return clipped(" | ".join(part for part in parts if part), 300)


def nearest_heading(lines: list[str], line_index: int) -> tuple[int | None, str]:
    for index in range(line_index, -1, -1):
        match = HEADING_PATTERN.match(lines[index])
        if match:
            return index + 1, compact_line(match.group(2))
    return None, "（无 Markdown 标题）"


def nearest_asset(
    lines: list[str], line_index: int, kind: str
) -> tuple[str, int, str]:
    pattern = MARKDOWN_CARRIER_PATTERNS[kind]
    for index in range(line_index - 1, -1, -1):
        match = pattern.match(lines[index])
        if match:
            return number_from_match(match), index + 1, compact_line(lines[index])
    raise AssertionError(f"no preceding {kind} number before baseline line {line_index + 1}")


def markdown_carrier_lines(text: str, kind: str) -> dict[str, list[int]]:
    occurrences: dict[str, list[int]] = defaultdict(list)
    pattern = MARKDOWN_CARRIER_PATTERNS[kind]
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = pattern.match(line)
        if match:
            occurrences[number_from_match(match)].append(line_number)
    return dict(occurrences)


def pdf_reference_pages(pages: list[str], kind: str) -> dict[str, list[int]]:
    occurrences: dict[str, set[int]] = defaultdict(set)
    pattern = NUMBER_PATTERNS[kind]
    for physical_page in range(13, 721):
        for match in pattern.finditer(pages[physical_page - 1]):
            occurrences[number_from_match(match)].add(physical_page)
    return {
        number: sorted(page_numbers)
        for number, page_numbers in occurrences.items()
    }


def expand_table_status_numbers(line: str) -> tuple[list[str], str]:
    numbers = [number_from_match(match) for match in NUMBER_PATTERNS["table"].finditer(line)]
    if "至" in line and len(numbers) == 2:
        start_chapter, start_item = number_key(numbers[0])
        end_chapter, end_item = number_key(numbers[1])
        if start_chapter != end_chapter or start_item > end_item:
            raise AssertionError(f"invalid table status range: {line}")
        return (
            [f"{start_chapter}-{item}" for item in range(start_item, end_item + 1)],
            "explicit_range_in_status_line",
        )
    return list(dict.fromkeys(numbers)), "explicit_list_in_status_line"


def build_baseline_marker_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for chapter in range(1, 21):
        path = CHAPTER_FILES.get(chapter)
        if path is None:
            raise AssertionError(f"missing chapter file {chapter}")
        relative_path = path.relative_to(ROOT).as_posix()
        lines = baseline_text(path).splitlines()
        for line_index, line in enumerate(lines):
            for occurrence, match in enumerate(re.finditer(r"原图未收录", line), start=1):
                number, asset_line, asset_title = nearest_asset(lines, line_index, "figure")
                if number_key(number)[0] != chapter:
                    raise AssertionError(
                        f"chapter {chapter} marker points to unexpected figure {number}"
                    )
                if "本段信息不完整" in line:
                    content_impact = "critical_content_incomplete"
                elif "仅保留图题与正文说明" in line:
                    content_impact = "graphic_detail_only"
                else:
                    raise AssertionError(
                        f"chapter {chapter} figure marker has unknown impact wording: {line}"
                    )
                records.append(
                    {
                        "id": (
                            f"textbook-ch{chapter:02d}-baseline-l{line_index + 1:04d}-"
                            f"figure-{number}-{occurrence:02d}"
                        ),
                        "kind": "figure",
                        "path": relative_path,
                        "baseline_line": line_index + 1,
                        "marker": match.group(0),
                        "nearest_asset_number": number,
                        "nearest_asset_line": asset_line,
                        "nearest_asset_title": asset_title,
                        "content_impact": content_impact,
                        "context": short_context(lines, line_index, match.group(0)),
                        "proof_scope": BASELINE_PROOF_SCOPE,
                    }
                )

            table_numbers: list[str] = []
            expansion_basis = ""
            marker = ""
            if "原表未收录" in line:
                number, asset_line, asset_title = nearest_asset(lines, line_index, "table")
                table_numbers = [number]
                expansion_basis = "nearest_preceding_table_title"
                marker = "原表未收录"
            elif "**表格状态" in line and ("拼栏" in line or "列错位" in line):
                table_numbers, expansion_basis = expand_table_status_numbers(line)
                asset_line = line_index + 1
                asset_title = ""
                marker = "表格状态：拼栏/字段或列错位"

            for number in table_numbers:
                if number_key(number)[0] != chapter:
                    raise AssertionError(
                        f"chapter {chapter} status points to unexpected table {number}"
                    )
                records.append(
                    {
                        "id": (
                            f"textbook-ch{chapter:02d}-baseline-l{line_index + 1:04d}-"
                            f"table-{number}"
                        ),
                        "kind": "table",
                        "path": relative_path,
                        "baseline_line": line_index + 1,
                        "marker": marker,
                        "nearest_asset_number": number,
                        "nearest_asset_line": asset_line,
                        "nearest_asset_title": asset_title or f"表 {number}（由状态行展开）",
                        "content_impact": "critical_content_incomplete",
                        "expansion_basis": expansion_basis,
                        "context": short_context(lines, line_index, f"表 {number}"),
                        "proof_scope": BASELINE_PROOF_SCOPE,
                    }
                )

    kind_counts = Counter(str(record["kind"]) for record in records)
    if kind_counts != {"figure": 272, "table": 8}:
        raise AssertionError(f"unexpected baseline marker counts: {dict(kind_counts)}")
    figure_impact_counts = Counter(
        str(record["content_impact"])
        for record in records
        if record["kind"] == "figure"
    )
    if figure_impact_counts != {
        "critical_content_incomplete": 174,
        "graphic_detail_only": 98,
    }:
        raise AssertionError(
            f"unexpected baseline figure impact counts: {dict(figure_impact_counts)}"
        )
    ids = [str(record["id"]) for record in records]
    if len(ids) != len(set(ids)):
        raise AssertionError("baseline marker IDs are not unique")
    return records


def build_formula_status_items() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for chapter in range(1, 21):
        path = CHAPTER_FILES[chapter]
        relative_path = path.relative_to(ROOT).as_posix()
        baseline_lines = baseline_text(path).splitlines()
        current_lines = path.read_text(encoding="utf-8-sig").splitlines()
        for line_index, line in enumerate(baseline_lines):
            if "**公式状态" not in line:
                continue
            if "自然连接" in line:
                topic = "natural_join"
            elif "随机游走" in line:
                topic = "random_walk"
            else:
                raise AssertionError(f"unrecognized formula status: {line}")
            heading_line, heading = nearest_heading(baseline_lines, line_index)
            needles = FORMULA_TOPICS[topic]["current_needles"]
            carrier_lines = sorted(
                {
                    current_index + 1
                    for current_index, current_line in enumerate(current_lines)
                    if any(needle in current_line for needle in needles)
                }
            )
            if not all(any(needle in current_line for current_line in current_lines) for needle in needles):
                status = "current_formula_carrier_incomplete"
            else:
                status = "current_formula_carrier_present"
            items.append(
                {
                    "id": f"textbook-ch{chapter:02d}-baseline-l{line_index + 1:04d}-formula-{topic}",
                    "topic": topic,
                    "label": FORMULA_TOPICS[topic]["label"],
                    "path": relative_path,
                    "baseline_line": line_index + 1,
                    "marker": "公式状态",
                    "nearest_heading_line": heading_line,
                    "nearest_heading": heading,
                    "context": short_context(baseline_lines, line_index, "公式状态"),
                    "markdown_carrier_lines": carrier_lines,
                    "status": status,
                    "proof_scope": (
                        "基线状态证明公式曾损坏；现行行号证明公式载体已出现，"
                        "公式语义与符号正确性仍以现行来源注和人工校对为准。"
                    ),
                }
            )
    if len(items) != 2 or any(item["status"] != "current_formula_carrier_present" for item in items):
        raise AssertionError(f"unexpected formula status inventory: {items}")
    return items


def build_additional_unmarked_formulas() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for spec in ADDITIONAL_UNMARKED_FORMULA_SPECS:
        chapter = int(spec["chapter"])
        path = CHAPTER_FILES[chapter]
        relative_path = path.relative_to(ROOT).as_posix()
        baseline_lines = baseline_text(path).splitlines()
        current_lines = path.read_text(encoding="utf-8-sig").splitlines()
        needles = tuple(str(needle) for needle in spec["current_needles"])
        baseline_needles = tuple(str(needle) for needle in spec["baseline_needles"])
        matched_lines = {
            needle: [
                line_index + 1
                for line_index, current_line in enumerate(current_lines)
                if needle in current_line
            ]
            for needle in needles
        }
        baseline_matched_lines = {
            needle: [
                line_index + 1
                for line_index, baseline_line in enumerate(baseline_lines)
                if needle in baseline_line
            ]
            for needle in baseline_needles
        }
        carrier_lines = sorted(
            {
                line_number
                for line_numbers in matched_lines.values()
                for line_number in line_numbers
            }
        )
        baseline_markdown_lines = sorted(
            {
                line_number
                for line_numbers in baseline_matched_lines.values()
                for line_number in line_numbers
            }
        )
        status = (
            "current_formula_carrier_present"
            if all(matched_lines.values()) and all(baseline_matched_lines.values())
            else "current_formula_carrier_incomplete"
        )
        anchor_index = carrier_lines[0] - 1 if carrier_lines else 0
        heading_line, heading = nearest_heading(current_lines, anchor_index)
        item: dict[str, object] = {
            "id": str(spec["id"]),
            "topic": str(spec["topic"]),
            "label": str(spec["label"]),
            "path": relative_path,
            "discovery_origin": "full_page_visual_text_review",
            "pdf_reference_pages": list(spec["pdf_reference_pages"]),
            "printed_pages": list(spec["printed_pages"]),
            "baseline_needles": list(baseline_needles),
            "baseline_markdown_lines": baseline_markdown_lines,
            "baseline_context": clipped(
                " | ".join(
                    compact_line(baseline_lines[line_number - 1])
                    for line_number in baseline_markdown_lines
                ),
                600,
            ),
            "nearest_heading_line": heading_line,
            "nearest_heading": heading,
            "markdown_carrier_lines": carrier_lines,
            "status": status,
            "content_impact": "critical_content_incomplete",
            "proof_scope": str(
                spec.get(
                    "proof_scope",
                    "全页视觉/文本联合复核证明源 PDF 的公式曾被 OCR 压平或破坏；"
                    "固定基线损坏文本、PDF 页码、现行公式载体及相邻编校说明"
                    "建立逐项闭环。",
                )
            ),
        }
        if "supporting_evidence" in spec:
            item["supporting_evidence"] = dict(spec["supporting_evidence"])
        items.append(item)
    ids = [str(item["id"]) for item in items]
    if (
        len(items) != 5
        or len(ids) != len(set(ids))
        or any(item["status"] != "current_formula_carrier_present" for item in items)
    ):
        raise AssertionError(f"unexpected additional formula inventory: {items}")
    return items


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(text: str) -> str:
    text = re.sub(r"兰亭图书阁", "", text)
    text = re.sub(r"系统架构设计师教程\s*[（(]?第?2版[）)]?", "", text)
    text = re.sub(r"第\s*\d+\s*章[^\n]{0,30}", "", text)
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", text)).lower()


def ngram_coverage(source: str, target: str, width: int) -> float:
    if len(source) < width:
        return 1.0
    total = len(source) - width + 1
    matched = sum(source[index : index + width] in target for index in range(total))
    return matched / total


def unique_numbers(texts: list[str], kind: str) -> set[str]:
    pattern = re.compile(rf"{kind}\s*(\d{{1,2}})\s*[-—]\s*(\d{{1,2}})")
    return {f"{left}-{right}" for text in texts for left, right in pattern.findall(text)}


def independent_numbers(text: str, kind: str) -> set[str]:
    prefix = r">\s*(?:\*\*)?" if kind == "图" else r"(?:>\s*)?(?:\*\*)?"
    pattern = re.compile(
        rf"^{prefix}{kind}\s*(\d{{1,2}})\s*[-—]\s*(\d{{1,2}})",
        re.MULTILINE,
    )
    return {f"{left}-{right}" for left, right in pattern.findall(text)}


def table_structure_risks(text: str) -> list[dict[str, object]]:
    """Find table-number lines that are only OCR sprawl, not usable carriers.

    A title alone is not enough to prove that a table was restored.  Require a
    nearby Markdown table, fenced diagram, HTML table, or structured list, and
    flag implausibly long title lines that commonly contain concatenated cells.
    The result deliberately stores only locations and measurements, not source
    table text.
    """

    title_pattern = re.compile(
        r"^\s*(?:>\s*)?(?:\*\*)?表\s*(\d{1,2})\s*[-—]\s*(\d{1,2})"
    )
    structured_pattern = re.compile(
        r"^\s*(?:>\s*)?(?:\|.*\|\s*|```|(?:[-*]|\d+[.)])\s+|<table\b)",
        re.IGNORECASE,
    )
    lines = text.splitlines()
    risks: list[dict[str, object]] = []
    for index, line in enumerate(lines):
        match = title_pattern.match(line)
        if match is None:
            continue
        reasons: list[str] = []
        if len(line.strip()) > 120:
            reasons.append("title_line_over_120_chars")
        following = lines[index + 1 : index + 26]
        if not any(structured_pattern.match(candidate) for candidate in following):
            reasons.append("no_structured_block_within_25_lines")
        if reasons:
            risks.append(
                {
                    "number": f"{match.group(1)}-{match.group(2)}",
                    "line": index + 1,
                    "title_line_chars": len(line.strip()),
                    "reasons": reasons,
                }
            )
    return risks


def build_asset_inventory(
    kind: str,
    pdf_pages: dict[str, list[int]],
    markdown_lines: dict[str, list[int]],
    baseline_records: list[dict[str, object]],
    table_risks: list[dict[str, object]],
) -> list[dict[str, object]]:
    baseline_ids: dict[str, list[str]] = defaultdict(list)
    for record in baseline_records:
        if record["kind"] == kind:
            baseline_ids[str(record["nearest_asset_number"])].append(str(record["id"]))
    risk_numbers = {str(risk["number"]) for risk in table_risks}
    inventory: list[dict[str, object]] = []
    for number in sorted(pdf_pages, key=number_key):
        chapter, _ = number_key(number)
        path = CHAPTER_FILES.get(chapter)
        if path is None:
            raise AssertionError(f"PDF {kind} {number} has no canonical chapter")
        carrier_lines = sorted(markdown_lines.get(number, []))
        if not carrier_lines:
            status = "missing_current_carrier"
        elif kind == "table" and number in risk_numbers:
            status = "current_carrier_structure_risk"
        elif kind == "table":
            status = "current_structured_carrier_present"
        else:
            status = "current_carrier_present"
        inventory.append(
            {
                "number": number,
                "chapter": chapter,
                "path": path.relative_to(ROOT).as_posix(),
                "pdf_reference_pages": pdf_pages[number],
                "markdown_carrier_lines": carrier_lines,
                "status": status,
                "baseline_marker_ids": sorted(baseline_ids.get(number, [])),
            }
        )
    return inventory


def link_baseline_records_to_inventory(
    records: list[dict[str, object]],
    figures: list[dict[str, object]],
    tables: list[dict[str, object]],
) -> None:
    inventory = {
        (kind, str(item["number"])): item
        for kind, items in (("figure", figures), ("table", tables))
        for item in items
    }
    for record in records:
        key = (str(record["kind"]), str(record["nearest_asset_number"]))
        item = inventory.get(key)
        if item is None:
            raise AssertionError(f"baseline record has no PDF inventory entry: {record['id']}")
        record["current_markdown_carrier_lines"] = item["markdown_carrier_lines"]
        record["current_status"] = item["status"]


def historical_spliced_table_investigation(
    table_records: list[dict[str, object]],
    table_risks: list[dict[str, object]],
    table_inventory: list[dict[str, object]],
) -> dict[str, object]:
    history = run_git(
        "log",
        "--all",
        "--reverse",
        "--format=%H",
        "-Sreported_spliced_table_positions",
        "--",
        "scripts/audit_textbook_pdf.py",
        "data/textbook_audit.json",
        "scripts/validate_knowledge_base.py",
    ).splitlines()
    # Later governance commits can legitimately add another occurrence of the
    # field name.  The provenance claim is only that the oldest -S hit is the
    # commit where the scalar count first appeared.
    if not history or history[0] != HISTORICAL_COUNT_COMMIT:
        raise AssertionError(f"unexpected history for reported count: {history}")

    count_locations = []
    for relative_path in (
        "scripts/audit_textbook_pdf.py",
        "data/textbook_audit.json",
        "scripts/validate_knowledge_base.py",
    ):
        committed_text = run_git("show", f"{HISTORICAL_COUNT_COMMIT}:{relative_path}")
        if "reported_spliced_table_positions" not in committed_text:
            raise AssertionError(f"historical count missing from {relative_path}")
        count_locations.append(relative_path)

    explicitly_named_shifted = sorted(
        {
            str(record["nearest_asset_number"])
            for record in table_records
            if str(record["marker"]).startswith("表格状态")
        },
        key=number_key,
    )
    if len(explicitly_named_shifted) != 7:
        raise AssertionError(
            f"expected seven separately counted baseline table issues, found {explicitly_named_shifted}"
        )

    inventory_by_number = {
        str(item["number"]): item for item in table_inventory
    }
    reconstructed: list[dict[str, object]] = []
    for number, specification in HISTORICAL_SPLICED_TABLE_CANDIDATES.items():
        chapter = int(specification["chapter"])
        path = CHAPTER_FILES.get(chapter)
        if path is None:
            raise AssertionError(f"missing chapter path for reconstructed table {number}")
        relative_path = path.relative_to(ROOT).as_posix()
        baseline_lines = baseline_text(path).splitlines()
        title_line = int(specification["baseline_title_line"])
        title_index = title_line - 1
        title_match = MARKDOWN_CARRIER_PATTERNS["table"].match(
            baseline_lines[title_index]
        )
        if title_match is None or number_from_match(title_match) != number:
            raise AssertionError(
                f"baseline title mismatch for reconstructed table {number}: "
                f"{baseline_lines[title_index]}"
            )
        flattened_start, flattened_end = (
            int(value) for value in specification["baseline_flattened_lines"]
        )
        flattened_text = " ".join(
            compact_line(line)
            for line in baseline_lines[flattened_start - 1 : flattened_end]
        )
        needles = tuple(str(value) for value in specification["baseline_needles"])
        if not all(needle in flattened_text for needle in needles):
            raise AssertionError(
                f"baseline flattened evidence changed for table {number}"
            )

        inventory_item = inventory_by_number.get(number)
        if inventory_item is None:
            raise AssertionError(f"reconstructed table {number} is absent from inventory")
        expected_pages = list(specification["pdf_reference_pages"])
        if inventory_item["pdf_reference_pages"] != expected_pages:
            raise AssertionError(
                f"PDF page inventory changed for table {number}: "
                f"{inventory_item['pdf_reference_pages']}"
            )
        if inventory_item["status"] != "current_structured_carrier_present":
            raise AssertionError(
                f"reconstructed table {number} has invalid status: {inventory_item['status']}"
            )
        current_lines = path.read_text(encoding="utf-8-sig").splitlines()
        carrier_lines = [int(value) for value in inventory_item["markdown_carrier_lines"]]
        if not carrier_lines or not any(
            any(
                candidate.strip().startswith("|")
                and candidate.strip().endswith("|")
                for candidate in current_lines[carrier_line : carrier_line + 8]
            )
            for carrier_line in carrier_lines
        ):
            raise AssertionError(
                f"reconstructed table {number} lacks a current pipe-table carrier"
            )
        reconstructed.append(
            {
                "id": (
                    f"textbook-ch{chapter:02d}-baseline-l{title_line:04d}-"
                    f"spliced-table-{number}"
                ),
                "number": number,
                "chapter": chapter,
                "path": relative_path,
                "baseline_title_line": title_line,
                "baseline_flattened_lines": [flattened_start, flattened_end],
                "baseline_evidence": clipped(flattened_text, 240),
                "pdf_reference_pages": expected_pages,
                "current_markdown_carrier_lines": carrier_lines,
                "status": "recovered_structural",
                "proof_scope": (
                    "固定基线证明该表的单元格曾被压平或拼栏；PDF 页码与现行管道表标题"
                    "建立逐项载体闭环。单元格语义仍以相邻来源注和人工逐页核对为准。"
                ),
            }
        )
    reconstructed.sort(key=lambda item: number_key(str(item["number"])))
    if len(reconstructed) != 15:
        raise AssertionError(
            f"expected 15 conservative reconstructed tables, found {len(reconstructed)}"
        )
    reconstructed_numbers = {str(item["number"]) for item in reconstructed}
    if reconstructed_numbers.intersection(explicitly_named_shifted):
        raise AssertionError(
            "conservative reconstructed tables overlap the separate baseline table category"
        )
    return {
        "reported_positions": 14,
        "mapping_status": "conservative_reconstruction_covers_reported_minimum",
        "ids_not_preserved": True,
        "count_first_recorded_in_commit": HISTORICAL_COUNT_COMMIT,
        "count_field_locations_in_that_commit": count_locations,
        "commit_diff_contains_14_item_manifest": False,
        "baseline_explicit_shifted_table_numbers_in_separate_8_item_category": (
            explicitly_named_shifted
        ),
        "conservatively_reconstructed_positions": len(reconstructed),
        "reported_minimum_covered": len(reconstructed) >= 14,
        "reconstructed_candidates": reconstructed,
        "investigation_conclusion": (
            "固定基线只明确命名了另行计入 8 个缺失或部分表位置中的 7 张拼栏/列错位表；"
            "提交差异首次加入数值 14 时没有保存原选择的逐项 ID 清单。重新以固定基线中的"
            "压平单元格、PDF 表号页和现行管道表三重条件保守识别出 15 张互不重叠的表，"
            "足以覆盖“至少 14 张”的历史下限；这不等同于声称已找回原报告恰好选择的 14 张。"
        ),
        "current_state_evidence": {
            "official_pdf_table_inventory": 59,
            "markdown_table_carriers": 59,
            "table_structure_risks": table_risks,
        },
        "proof_scope": (
            "15 张候选均有固定基线行、PDF 页和现行管道表证据，并已逐页目视核对；"
            "原报告的恰好 14 个 ID 仍未保存，因此这里只证明独立重建集合覆盖其数量下限。"
        ),
    }


def build_audit(
    pdf_path: Path, reviewed_at: str, width: int, manual_review_completed: bool
) -> dict[str, object]:
    resolved_baseline = run_git("rev-parse", f"{BASELINE_COMMIT}^{{commit}}").strip()
    if resolved_baseline != BASELINE_COMMIT:
        raise SystemExit(f"unexpected baseline commit: {resolved_baseline}")
    sha256 = file_sha256(pdf_path)
    if sha256 != EXPECTED_SHA256:
        raise SystemExit(
            f"unexpected PDF SHA-256: {sha256}; expected {EXPECTED_SHA256}"
        )
    reader = PdfReader(str(pdf_path))
    if len(reader.pages) != 721:
        raise SystemExit(f"unexpected page count: {len(reader.pages)}; expected 721")
    pages = [(page.extract_text() or "") for page in reader.pages]
    baseline_records = build_baseline_marker_records()
    formula_status_items = build_formula_status_items()
    additional_unmarked_formulas = build_additional_unmarked_formulas()
    pdf_figure_pages = pdf_reference_pages(pages, "figure")
    pdf_table_pages = pdf_reference_pages(pages, "table")
    chapters: list[dict[str, object]] = []
    page_records: list[dict[str, object]] = []
    all_pdf_figure_numbers: set[str] = set()
    all_pdf_table_numbers: set[str] = set()
    all_md_figure_numbers: set[str] = set()
    all_md_table_numbers: set[str] = set()
    all_md_figure_lines: dict[str, list[int]] = defaultdict(list)
    all_md_table_lines: dict[str, list[int]] = defaultdict(list)
    all_table_structure_risks: list[dict[str, object]] = []
    for chapter in range(1, 21):
        clean_path = CHAPTER_FILES.get(chapter)
        if clean_path is None:
            raise SystemExit(f"missing clean chapter file for chapter {chapter}")
        start, end = CHAPTER_RANGES[chapter]
        page_texts = pages[start - 1 : end]
        clean_text = clean_path.read_text(encoding="utf-8-sig")
        clean_normalized = normalize(clean_text)
        normalized_pages = [normalize(text) for text in page_texts]
        coverages = [
            ngram_coverage(page_text, clean_normalized, width)
            for page_text in normalized_pages
        ]
        for offset, (normalized_page, coverage) in enumerate(
            zip(normalized_pages, coverages, strict=True)
        ):
            page_records.append(
                {
                    "physical_page": start + offset,
                    "chapter": chapter,
                    "path": clean_path.relative_to(ROOT).as_posix(),
                    "normalized_pdf_chars": len(normalized_page),
                    "ngram_width": width,
                    "ngram_coverage": round(coverage, 6),
                }
            )
        pdf_figures = unique_numbers(page_texts, "图")
        pdf_tables = unique_numbers(page_texts, "表")
        md_figures = independent_numbers(clean_text, "图")
        md_tables = independent_numbers(clean_text, "表")
        chapter_figure_lines = markdown_carrier_lines(clean_text, "figure")
        chapter_table_lines = markdown_carrier_lines(clean_text, "table")
        for number, line_numbers in chapter_figure_lines.items():
            if number_key(number)[0] != chapter:
                raise AssertionError(
                    f"chapter {chapter} contains carrier for figure {number}"
                )
            all_md_figure_lines[number].extend(line_numbers)
        for number, line_numbers in chapter_table_lines.items():
            if number_key(number)[0] != chapter:
                raise AssertionError(f"chapter {chapter} contains carrier for table {number}")
            all_md_table_lines[number].extend(line_numbers)
        table_risks = table_structure_risks(clean_text)
        for risk in table_risks:
            all_table_structure_risks.append(
                {"path": clean_path.relative_to(ROOT).as_posix(), **risk}
            )
        all_pdf_figure_numbers.update(pdf_figures)
        all_pdf_table_numbers.update(pdf_tables)
        all_md_figure_numbers.update(md_figures)
        all_md_table_numbers.update(md_tables)
        chapters.append(
            {
                "chapter": chapter,
                "path": clean_path.relative_to(ROOT).as_posix(),
                "physical_pages": {"start": start, "end": end, "count": end - start + 1},
                "normalized_pdf_chars": sum(map(len, normalized_pages)),
                "normalized_markdown_chars": len(clean_normalized),
                "markdown_to_pdf_char_ratio": round(
                    len(clean_normalized) / max(1, sum(map(len, normalized_pages))), 6
                ),
                "page_ngram_coverage": {
                    "width": width,
                    "mean": round(statistics.mean(coverages), 6),
                    "median": round(statistics.median(coverages), 6),
                    "minimum": round(min(coverages), 6),
                    "below_0_35": [
                        start + offset
                        for offset, value in enumerate(coverages)
                        if value < 0.35
                    ],
                },
                "assets": {
                    "pdf_figure_numbers": len(pdf_figures),
                    "markdown_figure_carriers": len(md_figures),
                    "missing_figure_carriers": sorted(pdf_figures - md_figures),
                    "pdf_table_numbers": len(pdf_tables),
                    "markdown_table_titles": len(md_tables),
                    "missing_table_titles": sorted(pdf_tables - md_tables),
                    "table_structure_risks": table_risks,
                },
            }
        )

    if set(pdf_figure_pages) != all_pdf_figure_numbers:
        raise AssertionError("global and per-chapter PDF figure inventories differ")
    if set(pdf_table_pages) != all_pdf_table_numbers:
        raise AssertionError("global and per-chapter PDF table inventories differ")
    if set(all_md_figure_lines) != all_md_figure_numbers:
        raise AssertionError("Markdown figure carrier line inventory differs from title set")
    if set(all_md_table_lines) != all_md_table_numbers:
        raise AssertionError("Markdown table carrier line inventory differs from title set")
    if len(pdf_figure_pages) != 284 or len(pdf_table_pages) != 59:
        raise AssertionError(
            f"expected official inventory 284 figures/59 tables, found "
            f"{len(pdf_figure_pages)}/{len(pdf_table_pages)}"
        )
    if set(all_md_figure_lines) != set(pdf_figure_pages):
        raise AssertionError("current Markdown figure carriers do not match official inventory")
    if set(all_md_table_lines) != set(pdf_table_pages):
        raise AssertionError("current Markdown table carriers do not match official inventory")
    if all_table_structure_risks:
        raise AssertionError(
            "current full-table scan still has structure risks: "
            + json.dumps(all_table_structure_risks, ensure_ascii=False)
        )
    if len(page_records) != 708:
        raise AssertionError(f"expected 708 page records, found {len(page_records)}")
    if [int(item["physical_page"]) for item in page_records] != list(range(13, 721)):
        raise AssertionError("page records do not cover physical pages 13 through 720")

    figure_inventory = build_asset_inventory(
        "figure",
        pdf_figure_pages,
        dict(all_md_figure_lines),
        baseline_records,
        all_table_structure_risks,
    )
    table_inventory = build_asset_inventory(
        "table",
        pdf_table_pages,
        dict(all_md_table_lines),
        baseline_records,
        all_table_structure_risks,
    )
    link_baseline_records_to_inventory(
        baseline_records, figure_inventory, table_inventory
    )

    baseline_figure_numbers = {
        str(record["nearest_asset_number"])
        for record in baseline_records
        if record["kind"] == "figure"
    }
    baseline_table_records = [
        record for record in baseline_records if record["kind"] == "table"
    ]
    if len(baseline_figure_numbers) != 272:
        raise AssertionError(
            f"expected 272 unique baseline figure numbers, found {len(baseline_figure_numbers)}"
        )
    if not baseline_figure_numbers <= set(pdf_figure_pages):
        raise AssertionError("baseline figure numbers are not a subset of official inventory")
    additional_numbers = sorted(
        set(pdf_figure_pages) - baseline_figure_numbers, key=number_key
    )
    if len(additional_numbers) != 12:
        raise AssertionError(
            f"expected 12 additional unmarked figures, found {additional_numbers}"
        )
    if set(additional_numbers) != set(ADDITIONAL_FIGURE_CONTENT_CLASSIFICATION):
        raise AssertionError("additional figure content classification is incomplete")
    figure_by_number = {str(item["number"]): item for item in figure_inventory}
    additional_unmarked_figures = [
        {
            "id": f"textbook-additional-unmarked-figure-{number}",
            **figure_by_number[number],
            **ADDITIONAL_FIGURE_CONTENT_CLASSIFICATION[number],
            "reason": (
                "官方 PDF 全量图号存在，但固定基线 272 个原图未收录标记中没有该图号。"
            ),
            "proof_scope": INVENTORY_PROOF_SCOPE,
        }
        for number in additional_numbers
    ]
    if any(item["baseline_marker_ids"] for item in additional_unmarked_figures):
        raise AssertionError("additional unmarked figure unexpectedly has a baseline marker")

    low_coverage_pages = {
        int(item["physical_page"])
        for item in page_records
        if float(item["ngram_coverage"]) < 0.35
    }
    additional_figure_pages = {
        int(page)
        for item in additional_unmarked_figures
        for page in item["pdf_reference_pages"]
    }
    additional_formula_pages = {
        int(page)
        for item in additional_unmarked_formulas
        for page in item["pdf_reference_pages"]
    }
    full_chapter_review_pages = {
        page
        for chapter in (8, 10)
        for page in range(CHAPTER_RANGES[chapter][0], CHAPTER_RANGES[chapter][1] + 1)
    }
    full_page_review_pages = set(range(13, 721))
    declared_manual_pages = set(full_page_review_pages)
    phase_page_numbers = [
        page
        for phase in FULL_REVIEW_PHASES
        for page_range in phase["physical_page_ranges"]
        for page in range(int(page_range[0]), int(page_range[1]) + 1)
    ]
    if (
        len(low_coverage_pages),
        len(additional_figure_pages),
        len(additional_formula_pages),
        len(full_chapter_review_pages),
        len(full_page_review_pages),
        len(declared_manual_pages),
    ) != (20, 11, 6, 73, 708, 708):
        raise AssertionError(
            "manual page scope changed: "
            f"low={len(low_coverage_pages)}, figures={len(additional_figure_pages)}, "
            f"formulas={len(additional_formula_pages)}, "
            f"chapter8_10={len(full_chapter_review_pages)}, "
            f"full={len(full_page_review_pages)}, union={len(declared_manual_pages)}"
        )
    if (
        len(phase_page_numbers) != len(set(phase_page_numbers))
        or sorted(phase_page_numbers) != list(range(13, 721))
        or sum(int(phase["page_count"]) for phase in FULL_REVIEW_PHASES) != 708
        or sum(
            int(phase["generated_contact_sheet_count"])
            for phase in FULL_REVIEW_PHASES
        )
        != int(FULL_REVIEW_RENDER_METADATA["generated_contact_sheet_count"])
        or sum(
            int(phase["contact_sheets_used_for_review"])
            for phase in FULL_REVIEW_PHASES
        )
        != int(FULL_REVIEW_RENDER_METADATA["contact_sheets_used_for_current_full_review"])
    ):
        raise AssertionError("full-review batch/render metadata is inconsistent")
    for item in page_records:
        physical_page = int(item["physical_page"])
        reasons: list[str] = []
        if physical_page in low_coverage_pages:
            reasons.append("low_ngram_coverage")
        if physical_page in additional_figure_pages:
            reasons.append("additional_unmarked_figure")
        if physical_page in additional_formula_pages:
            reasons.append("additional_unmarked_formula")
        if physical_page in full_chapter_review_pages:
            reasons.append("full_chapter_8_or_10")
        if physical_page in full_page_review_pages:
            reasons.append("full_page_visual_text_review")
        item["declared_manual_review_reasons"] = reasons
        item["declared_manual_review_status"] = (
            "completed"
            if physical_page in declared_manual_pages and manual_review_completed
            else "pending"
            if physical_page in declared_manual_pages
            else "outside_declared_manual_scope"
        )

    historical_spliced_tables = historical_spliced_table_investigation(
        baseline_table_records, all_table_structure_risks, table_inventory
    )
    reconstructed_spliced_positions = int(
        historical_spliced_tables["conservatively_reconstructed_positions"]
    )
    critical_figure_position_ids = [
        str(record["id"])
        for record in baseline_records
        if record["kind"] == "figure"
        and record["content_impact"] == "critical_content_incomplete"
    ]
    formula_position_ids = [str(item["id"]) for item in formula_status_items]
    additional_formula_position_ids = [
        str(item["id"]) for item in additional_unmarked_formulas
    ]
    explicit_table_position_ids = [str(record["id"]) for record in baseline_table_records]
    conservative_spliced_table_position_ids = [
        str(item["id"])
        for item in historical_spliced_tables["reconstructed_candidates"]
    ]
    additional_critical_figure_position_ids = [
        str(item["id"])
        for item in additional_unmarked_figures
        if item["content_impact"] == "critical_content_incomplete"
    ]
    additional_detail_only_figure_position_ids = [
        str(item["id"])
        for item in additional_unmarked_figures
        if item["content_impact"] == "graphic_detail_only"
    ]
    historical_key_content_position_ids = [
        *critical_figure_position_ids,
        *formula_position_ids,
        *explicit_table_position_ids,
        *conservative_spliced_table_position_ids,
    ]
    current_key_content_position_ids = [
        *historical_key_content_position_ids,
        *additional_critical_figure_position_ids,
        *additional_formula_position_ids,
    ]
    if (
        len(critical_figure_position_ids),
        len(formula_position_ids),
        len(additional_formula_position_ids),
        len(explicit_table_position_ids),
        len(conservative_spliced_table_position_ids),
        len(additional_critical_figure_position_ids),
        len(additional_detail_only_figure_position_ids),
        len(historical_key_content_position_ids),
        len(set(historical_key_content_position_ids)),
        len(current_key_content_position_ids),
        len(set(current_key_content_position_ids)),
    ) != (174, 2, 5, 8, 15, 4, 8, 199, 199, 208, 208):
        raise AssertionError("key content debt reconstruction changed")
    itemized_proven_positions = (
        272
        + 12
        + len(formula_position_ids)
        + len(additional_formula_position_ids)
        + 8
        + reconstructed_spliced_positions
    )
    original_minimum = 272 + 2 + 8 + 14
    corrected_minimum = itemized_proven_positions
    if (itemized_proven_positions, original_minimum, corrected_minimum) != (
        314,
        296,
        314,
    ):
        raise AssertionError("debt arithmetic changed")

    return {
        "schema_version": 4,
        "reviewed_at": reviewed_at,
        "field_definitions": {
            "baseline_marker_records": (
                "固定提交中 272 个缺图标记与展开后的 8 个缺失/部分表位置。"
            ),
            "nearest_asset_number": "标记之前最近的图号，或表格状态行明确列出的表号。",
            "pdf_reference_pages": "官方 PDF 内容页文本层中出现该图表号的物理页集合。",
            "markdown_carrier_lines": "现行 canonical Markdown 中独立图题或表题的 1 基行号。",
            "status": "编号级当前载体状态；不等同于语义或像素级复核结论。",
            "context": "固定基线状态行前后相邻非空行组成的截短上下文。",
            "content_impact": (
                "critical_content_incomplete 来自固定基线的“本段信息不完整”标记；"
                "graphic_detail_only 来自“仅保留图题与正文说明”标记。"
            ),
            "page_records": "物理页 13～720 的 708 条逐页文本覆盖与全页人工复核记录。",
            "additional_unmarked_formulas": (
                "全页复核补发现、但不属于固定基线两条公式状态标记的独立公式位置。"
            ),
        },
        "source": {
            "path_hint": "本地pdf参考/1. 系统架构设计师教材（官方教程-）.pdf",
            "sha256": sha256,
            "pages": len(pages),
            "chapter_content_pages": sum(
                end - start + 1 for start, end in CHAPTER_RANGES.values()
            ),
            "excluded_pages": {
                "1-12": "封面、版权、前言和目录；前言另有独立清洗稿",
                "721": "封底考试宣传，按清洗标准排除",
            },
        },
        "method": {
            "text_extraction": "pypdf",
            "normalization": "remove known headers/watermark/punctuation; keep Han and alphanumerics",
            "page_coverage": f"sliding normalized {width}-character n-grams",
            "baseline_enumeration": f"git show {BASELINE_COMMIT}:<canonical chapter path>",
            "asset_inventory": (
                "official PDF number references joined to current Markdown independent carrier titles"
            ),
            "limitation": "覆盖率用于定位风险页，不单独证明语义或版式正确；复杂图表另需渲染和目视核验。",
        },
        "manual_review": {
            "status": "full_scope_completed" if manual_review_completed else "pending",
            "scope": "物理页 13～720 共 708 个正文页的视觉/文本联合复核",
            "explicit_page_count": len(declared_manual_pages),
            "explicit_physical_pages": sorted(declared_manual_pages),
            "scope_components": {
                "low_ngram_coverage_pages": sorted(low_coverage_pages),
                "additional_unmarked_figure_pages": sorted(additional_figure_pages),
                "additional_unmarked_formula_pages": sorted(additional_formula_pages),
                "full_chapter_8_or_10_pages": sorted(full_chapter_review_pages),
                "full_page_visual_text_review_pages": sorted(full_page_review_pages),
            },
            "review_phases": [
                {
                    **phase,
                    "status": "completed" if manual_review_completed else "pending",
                }
                for phase in FULL_REVIEW_PHASES
            ],
            "render_review": dict(FULL_REVIEW_RENDER_METADATA),
            "chapter_content_pages": len(page_records),
            "outside_declared_manual_scope_pages": len(page_records)
            - len(declared_manual_pages),
            "checks": [
                "联系表以 original detail 逐页目视核对，并对疑似异常页单页放大",
                "PDF 页序、章界、异常空白、裁切、错页及跨页连续性复核",
                "page_records 自动文本覆盖与 canonical Markdown 联合对照",
                "新增及实质修改 Mermaid CLI 渲染",
                "复杂 Markdown 表格浏览器渲染抽检",
                "来源页码、图号、表号与残余限制复核",
            ],
            "description": (
                "第 8/10 章 73 页沿用既有逐页详细复核；其余 635 页通过 A～D 四批"
                "79 张联系表完成本轮目视复核。全部 708 页均有 page_records 自动文本覆盖，"
                "共生成 88 张联系表，其中 prior 阶段的 9 张不作为既有完成声明依据。"
            ),
        },
        "baseline_evidence": {
            "commit": BASELINE_COMMIT,
            "counts": {
                "figure_markers": 272,
                "table_issue_positions": 8,
                "total_records": len(baseline_records),
            },
            "proof_scope": BASELINE_PROOF_SCOPE,
            "records": baseline_records,
        },
        "asset_inventory": {
            "proof_scope": INVENTORY_PROOF_SCOPE,
            "figures": figure_inventory,
            "tables": table_inventory,
        },
        "additional_unmarked_figures": additional_unmarked_figures,
        "formula_status_items": formula_status_items,
        "additional_unmarked_formulas": additional_unmarked_formulas,
        "historical_spliced_tables": historical_spliced_tables,
        "key_content_debt": {
            "historical_reported_content_minimum": 198,
            "derivation_status": "conservative_reconstruction_from_baseline_markers",
            "historical_item_ids_preserved": False,
            "historical_arithmetic": "174 + 2 + 8 + 14 = 198",
            "historical_identity_status": (
                "仓库和 Git 历史未保存数字 198 或其 manifest；该下限由固定基线 A/B 标记"
                "语义及历史 296=272+2+8+14 算式反推。174 个关键缺图、2 个公式和 8 个"
                "显式缺表可逐项重建；历史报告恰好选择的 14 张拼栏表 ID 未保存。"
            ),
            "baseline_content_incomplete_figures": 174,
            "baseline_content_incomplete_figure_wording": {
                "exact_policy_a": 168,
                "semantic_variants": 6,
            },
            "baseline_graphic_detail_only_figures": 98,
            "additional_unmarked_figures_content_classification": {
                "status": "completed",
                "positions": 12,
                "critical_content_incomplete": 4,
                "graphic_detail_only": 8,
                "method": "逐项对照 PDF、现行载体及 FIGURE_POLICY A/B 的正文独立可读性测试。",
            },
            "critical_figure_position_ids": critical_figure_position_ids,
            "additional_critical_figure_position_ids": (
                additional_critical_figure_position_ids
            ),
            "additional_detail_only_figure_position_ids": (
                additional_detail_only_figure_position_ids
            ),
            "formula_position_ids": formula_position_ids,
            "additional_formula_position_ids": additional_formula_position_ids,
            "explicit_table_position_ids": explicit_table_position_ids,
            "conservative_spliced_table_position_ids": (
                conservative_spliced_table_position_ids
            ),
            "historical_conservative_reconstructed_positions": len(
                historical_key_content_position_ids
            ),
            "historical_conservative_arithmetic": "174 + 2 + 8 + 15 = 199",
            "historical_position_ids": historical_key_content_position_ids,
            "current_conservative_reconstructed_positions": len(
                current_key_content_position_ids
            ),
            "current_conservative_arithmetic": "174 + 4 + 7 + 8 + 15 = 208",
            "current_position_ids": current_key_content_position_ids,
            "proof_scope": (
                "199 个稳定 ID 形成覆盖历史至少 198 项的高置信保守重建集合；12 个后补图"
                "经逐项 A/B 复核后有 4 个进入当前关键集合，全页复核另补发现 5 个关键公式"
                "位置，因此当前为 208 项。基线 A/B 只证明"
                "固定基线维护者当时的风险判断；最后 15 项是独立三重证据识别的拼栏表候选，"
                "不声称与历史报告未保存的恰好 14 个 ID 一一对应。"
            ),
        },
        "debt_scope": {
            "original_minimum": original_minimum,
            "corrected_minimum": corrected_minimum,
            "legacy_marked_figure_positions": 272,
            "additional_unmarked_figure_positions": len(additional_unmarked_figures),
            "known_formula_positions": 7,
            "explicit_missing_or_partial_table_positions": len(baseline_table_records),
            "reported_spliced_table_positions": 14,
            "conservatively_reconstructed_spliced_table_positions": (
                reconstructed_spliced_positions
            ),
            "itemized_proven_positions": itemized_proven_positions,
            "historical_unitemized_positions": 0,
            "key_content_historical_minimum": 198,
            "key_content_historical_conservative_positions": len(
                historical_key_content_position_ids
            ),
            "key_content_current_conservative_positions": len(
                current_key_content_position_ids
            ),
            "arithmetic": "272 + 12 + 7 + 8 + 15 = 314",
            "description": (
                "逐项证据覆盖 272 个基线图、12 个新增图、2 个历史公式、5 个全页复核"
                "补发现公式、8 个显式缺失或部分表，"
                "以及 15 个由固定基线压平文本、PDF 页和现行管道表独立重建的拼栏表，"
                "合计 314 项。原报告恰好选择的 14 个 ID 未保存，但独立重建集合已覆盖"
                "“至少 14 张”的数量下限。"
            ),
        },
        "summary": {
            "chapters": 20,
            "baseline_explicit_marker_records": len(baseline_records),
            "itemized_proven_positions": itemized_proven_positions,
            "historical_unitemized_positions": 0,
            "key_content_historical_minimum": 198,
            "key_content_historical_conservative_positions": len(
                historical_key_content_position_ids
            ),
            "key_content_current_conservative_positions": len(
                current_key_content_position_ids
            ),
            "page_records": len(page_records),
            "declared_manual_review_pages": len(declared_manual_pages),
            "conservatively_reconstructed_spliced_table_positions": (
                reconstructed_spliced_positions
            ),
            "pdf_unique_figure_numbers": len(all_pdf_figure_numbers),
            "markdown_unique_figure_carriers": len(all_md_figure_numbers),
            "missing_figure_carriers": sorted(
                all_pdf_figure_numbers - all_md_figure_numbers
            ),
            "pdf_unique_table_numbers": len(all_pdf_table_numbers),
            "markdown_unique_table_titles": len(all_md_table_numbers),
            "missing_table_titles": sorted(all_pdf_table_numbers - all_md_table_numbers),
            "table_structure_risks": all_table_structure_risks,
        },
        "page_records": page_records,
        "chapters": chapters,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "textbook_audit.json")
    parser.add_argument("--reviewed-at", default="2026-07-12")
    parser.add_argument("--ngram-width", type=int, default=10)
    parser.add_argument(
        "--manual-review-completed",
        action="store_true",
        help="record that all 708 textbook content pages completed visual/text review",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that the output JSON exactly matches a live PDF/baseline rerun",
    )
    args = parser.parse_args()
    audit = build_audit(
        args.pdf.resolve(),
        args.reviewed_at,
        args.ngram_width,
        args.manual_review_completed,
    )
    rendered = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        current = (
            args.output.read_text(encoding="utf-8-sig")
            if args.output.is_file()
            else ""
        )
        if current != rendered:
            print(f"ERROR: {args.output} is not reproducible", file=sys.stderr)
            return 1
        print(
            "textbook audit is reproducible: "
            "280 baseline records, 284 figures, 59 tables, 7 formulas, "
            "708 fully reviewed pages"
        )
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(
        f"Audited {audit['summary']['chapters']} chapters; "
        f"figures={audit['summary']['pdf_unique_figure_numbers']}, "
        f"tables={audit['summary']['pdf_unique_table_numbers']}, "
        "formulas=7, full_review_pages=708; "
        f"output={args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
