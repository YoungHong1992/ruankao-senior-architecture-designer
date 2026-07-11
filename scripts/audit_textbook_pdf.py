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
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - depends on the local audit runtime
    raise SystemExit("pypdf is required: install it or use the bundled Codex runtime") from exc


ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "01.系统架构设计师教材-清洗版"
EXPECTED_SHA256 = "ee45900f4622d71539980cfe1bddbcd898fba97ca13ada6df1cbdc215135c2f8"

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


def build_audit(
    pdf_path: Path, reviewed_at: str, width: int, manual_review_completed: bool
) -> dict[str, object]:
    sha256 = file_sha256(pdf_path)
    if sha256 != EXPECTED_SHA256:
        raise SystemExit(
            f"unexpected PDF SHA-256: {sha256}; expected {EXPECTED_SHA256}"
        )
    reader = PdfReader(str(pdf_path))
    if len(reader.pages) != 721:
        raise SystemExit(f"unexpected page count: {len(reader.pages)}; expected 721")
    pages = [(page.extract_text() or "") for page in reader.pages]
    chapters: list[dict[str, object]] = []
    all_pdf_figure_numbers: set[str] = set()
    all_pdf_table_numbers: set[str] = set()
    all_md_figure_numbers: set[str] = set()
    all_md_table_numbers: set[str] = set()
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
                },
            }
        )
    return {
        "schema_version": 1,
        "reviewed_at": reviewed_at,
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
            "limitation": "覆盖率用于定位风险页，不单独证明语义或版式正确；复杂图表另需渲染和目视核验。",
        },
        "manual_review": {
            "status": "completed" if manual_review_completed else "pending",
            "scope": "所有低覆盖风险页、全部新增图表载体及第 8/10 章完整物理页范围",
            "checks": [
                "PDF 页面渲染与原始结构目视核对",
                "新增及实质修改 Mermaid CLI 渲染",
                "复杂 Markdown 表格浏览器渲染抽检",
                "来源页码、图号、表号与残余限制复核"
            ],
            "description": "该字段是人工验收声明；自动覆盖率本身不能替代视觉或语义复核。"
        },
        "debt_scope": {
            "original_minimum": 296,
            "corrected_minimum": 308,
            "legacy_marked_figure_positions": 272,
            "additional_unmarked_figure_positions": 12,
            "known_formula_positions": 2,
            "explicit_missing_or_partial_table_positions": 8,
            "reported_spliced_table_positions": 14,
            "description": "原 296 口径由 272 图、2 公式、8 张缺失或部分表及至少 14 个拼栏表位置组成；逐页 PDF 审计另发现 12 幅未进入旧清单的图，因此下限修正为 308。",
        },
        "summary": {
            "chapters": 20,
            "pdf_unique_figure_numbers": len(all_pdf_figure_numbers),
            "markdown_unique_figure_carriers": len(all_md_figure_numbers),
            "missing_figure_carriers": sorted(
                all_pdf_figure_numbers - all_md_figure_numbers
            ),
            "pdf_unique_table_numbers": len(all_pdf_table_numbers),
            "markdown_unique_table_titles": len(all_md_table_numbers),
            "missing_table_titles": sorted(all_pdf_table_numbers - all_md_table_numbers),
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
    args = parser.parse_args()
    audit = build_audit(
        args.pdf.resolve(),
        args.reviewed_at,
        args.ngram_width,
        args.manual_review_completed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Audited {audit['summary']['chapters']} chapters; "
        f"figures={audit['summary']['pdf_unique_figure_numbers']}, "
        f"tables={audit['summary']['pdf_unique_table_numbers']}; output={args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
