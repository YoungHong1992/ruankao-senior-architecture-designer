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
                        "expansion_basis": expansion_basis,
                        "context": short_context(lines, line_index, f"表 {number}"),
                        "proof_scope": BASELINE_PROOF_SCOPE,
                    }
                )

    kind_counts = Counter(str(record["kind"]) for record in records)
    if kind_counts != {"figure": 272, "table": 8}:
        raise AssertionError(f"unexpected baseline marker counts: {dict(kind_counts)}")
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
    return {
        "reported_positions": 14,
        "mapping_status": "ids_not_preserved",
        "ids_not_preserved": True,
        "count_first_recorded_in_commit": HISTORICAL_COUNT_COMMIT,
        "count_field_locations_in_that_commit": count_locations,
        "commit_diff_contains_14_item_manifest": False,
        "baseline_explicit_shifted_table_numbers_in_separate_8_item_category": (
            explicitly_named_shifted
        ),
        "investigation_conclusion": (
            "固定基线只明确命名了另行计入 8 个缺失或部分表位置中的 7 张拼栏/列错位表；"
            "提交差异首次加入数值 14 时没有保存逐项 ID 清单。无法仅凭大范围 Markdown 差异"
            "客观判定那 14 个历史位置，故不生成候选 ID。"
        ),
        "current_state_evidence": {
            "official_pdf_table_inventory": 59,
            "markdown_table_carriers": 59,
            "table_structure_risks": table_risks,
        },
        "proof_scope": (
            "当前 59 表结构扫描为空，只证明现态没有同类启发式残余；"
            "它不构成历史 14/14 身份映射闭环。"
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
    pdf_figure_pages = pdf_reference_pages(pages, "figure")
    pdf_table_pages = pdf_reference_pages(pages, "table")
    chapters: list[dict[str, object]] = []
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
    figure_by_number = {str(item["number"]): item for item in figure_inventory}
    additional_unmarked_figures = [
        {
            "id": f"textbook-additional-unmarked-figure-{number}",
            **figure_by_number[number],
            "reason": (
                "官方 PDF 全量图号存在，但固定基线 272 个原图未收录标记中没有该图号。"
            ),
            "proof_scope": INVENTORY_PROOF_SCOPE,
        }
        for number in additional_numbers
    ]
    if any(item["baseline_marker_ids"] for item in additional_unmarked_figures):
        raise AssertionError("additional unmarked figure unexpectedly has a baseline marker")

    historical_spliced_tables = historical_spliced_table_investigation(
        baseline_table_records, all_table_structure_risks
    )
    itemized_proven_positions = 272 + 12 + 2 + 8
    original_minimum = 272 + 2 + 8 + 14
    corrected_minimum = itemized_proven_positions + 14
    if (itemized_proven_positions, original_minimum, corrected_minimum) != (
        294,
        296,
        308,
    ):
        raise AssertionError("debt arithmetic changed")

    return {
        "schema_version": 2,
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
            "status": "completed" if manual_review_completed else "pending",
            "scope": "所有低覆盖风险页、全部新增图表载体及第 8/10 章完整物理页范围",
            "checks": [
                "PDF 页面渲染与原始结构目视核对",
                "新增及实质修改 Mermaid CLI 渲染",
                "复杂 Markdown 表格浏览器渲染抽检",
                "来源页码、图号、表号与残余限制复核",
            ],
            "description": "该字段是人工验收声明；自动覆盖率本身不能替代视觉或语义复核。",
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
        "historical_spliced_tables": historical_spliced_tables,
        "debt_scope": {
            "original_minimum": original_minimum,
            "corrected_minimum": corrected_minimum,
            "legacy_marked_figure_positions": 272,
            "additional_unmarked_figure_positions": len(additional_unmarked_figures),
            "known_formula_positions": 2,
            "explicit_missing_or_partial_table_positions": len(baseline_table_records),
            "reported_spliced_table_positions": 14,
            "itemized_proven_positions": itemized_proven_positions,
            "historical_unitemized_positions": 14,
            "arithmetic": "272 + 12 + 2 + 8 + 14 = 308",
            "description": (
                "逐项证据可直接覆盖 272 个基线图、12 个新增图、2 个公式和 8 个表，"
                "合计 294 项；历史数值 14 未保存逐项 ID，只作为单独的未枚举历史口径，"
                "因此 308 不能表述为 308 个均已逐项映射。"
            ),
        },
        "summary": {
            "chapters": 20,
            "baseline_explicit_marker_records": len(baseline_records),
            "itemized_proven_positions": itemized_proven_positions,
            "historical_unitemized_positions": 14,
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
        help="record that the risk-page and rendered-asset review has been completed",
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
            "280 baseline records, 284 figures, 59 tables"
        )
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(
        f"Audited {audit['summary']['chapters']} chapters; "
        f"figures={audit['summary']['pdf_unique_figure_numbers']}, "
        f"tables={audit['summary']['pdf_unique_table_numbers']}; output={args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
