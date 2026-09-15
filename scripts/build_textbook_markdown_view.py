#!/usr/bin/env python3
"""Refresh the Markdown-derived ("current view") fields of the textbook audit.

``scripts/audit_textbook_pdf.py`` produces ``data/textbook_audit.json`` from the
source PDF (hash-pinned, deliberately not committed) plus the pinned baseline
commit, so it cannot run in CI.  Everything the ledger derives from the *current*
clean Markdown can still be recomputed from the repository alone; this script
does exactly that and makes the recomputation a gate:

    uv run python scripts/build_textbook_markdown_view.py          # rewrite ledger
    uv run python scripts/build_textbook_markdown_view.py --check  # report drift

Recomputed fields
-----------------
* ``chapters[].normalized_markdown_chars`` / ``markdown_to_pdf_char_ratio``
* ``chapters[].assets.markdown_figure_carriers`` / ``markdown_table_titles``
* ``chapters[].assets.missing_figure_carriers`` / ``missing_table_titles``
* ``chapters[].assets.table_structure_risks``
* ``asset_inventory.{figures,tables}[].markdown_carrier_lines`` / ``status``
* ``additional_unmarked_figures[].markdown_carrier_lines`` / ``status``
* ``baseline_evidence.records[].current_markdown_carrier_lines`` / ``current_status``
* ``historical_spliced_tables.reconstructed_candidates[].current_markdown_carrier_lines``
* ``historical_spliced_tables.current_state_evidence``
* ``formula_status_items[].markdown_carrier_lines`` / ``status``
* ``additional_unmarked_formulas[].markdown_carrier_lines`` / ``status`` /
  ``nearest_heading_line`` / ``nearest_heading``
* ``summary.markdown_unique_figure_carriers`` / ``markdown_unique_table_titles`` /
  ``missing_figure_carriers`` / ``missing_table_titles`` / ``table_structure_risks``

Frozen fields (PDF side)
------------------------
Page numbers, ``normalized_pdf_chars``, ``page_ngram_coverage``, every ``baseline_*``
measurement and the per-chapter PDF number counts stay frozen against the
uncommitted source PDF and the pinned baseline commit.  They are evidence about
the recorded review, not claims about the current Markdown, so they are never
rewritten here: a value that contradicts the ledger's own asset inventory is
reported as an integrity error instead of being silently updated.

Formula carrier lines are recomputed from the ``current_needles`` stored on each
formula item (written by ``audit_textbook_pdf.py``), so the ledger stays
self-contained and this script needs no copy of the generator's specification
tables.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "data" / "textbook_audit.json"

# Kept verbatim in sync with scripts/audit_textbook_pdf.py, which remains the
# producer of this ledger.
MARKDOWN_CARRIER_PATTERNS = {
    "figure": re.compile(r"^\s*>\s*(?:\*\*)?图\s*(\d{1,2})\s*[-—]\s*(\d{1,2})"),
    "table": re.compile(r"^\s*(?:>\s*)?(?:\*\*)?表\s*(\d{1,2})\s*[-—]\s*(\d{1,2})"),
}
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
TABLE_TITLE_PATTERN = re.compile(r"^\s*(?:>\s*)?(?:\*\*)?表\s*(\d{1,2})\s*[-—]\s*(\d{1,2})")
STRUCTURED_BLOCK_PATTERN = re.compile(
    r"^\s*(?:>\s*)?(?:\|.*\|\s*|```|(?:[-*]|\d+[.)])\s+|<table\b)",
    re.IGNORECASE,
)

FIGURE_GROUP = "figures"
TABLE_GROUP = "tables"

MISSING_CARRIER_STATUS = "missing_current_carrier"
STRUCTURE_RISK_STATUS = "current_carrier_structure_risk"
STRUCTURED_CARRIER_STATUS = "current_structured_carrier_present"
CARRIER_STATUS = "current_carrier_present"
FORMULA_PRESENT_STATUS = "current_formula_carrier_present"
FORMULA_INCOMPLETE_STATUS = "current_formula_carrier_incomplete"

CHAPTER_ASSET_FIELDS = (
    ("figure", "markdown_figure_carriers", "pdf_figure_numbers", "missing_figure_carriers"),
    ("table", "markdown_table_titles", "pdf_table_numbers", "missing_table_titles"),
)


def number_from_match(match: re.Match[str]) -> str:
    return f"{int(match.group(1))}-{int(match.group(2))}"


def number_key(number: str) -> tuple[int, int]:
    chapter, item = number.split("-", maxsplit=1)
    return int(chapter), int(item)


def compact_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def nearest_heading(lines: list[str], line_index: int) -> tuple[int | None, str]:
    for index in range(line_index, -1, -1):
        match = HEADING_PATTERN.match(lines[index])
        if match:
            return index + 1, compact_line(match.group(2))
    return None, "（无 Markdown 标题）"


def markdown_carrier_lines(text: str, kind: str) -> dict[str, list[int]]:
    occurrences: dict[str, list[int]] = defaultdict(list)
    pattern = MARKDOWN_CARRIER_PATTERNS[kind]
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = pattern.match(line)
        if match:
            occurrences[number_from_match(match)].append(line_number)
    return dict(occurrences)


def independent_numbers(text: str, kind: str) -> set[str]:
    prefix = r"[ \t]*>\s*(?:\*\*)?" if kind == "图" else r"[ \t]*(?:>\s*)?(?:\*\*)?"
    pattern = re.compile(rf"^{prefix}{kind}\s*(\d{{1,2}})\s*[-—]\s*(\d{{1,2}})", re.MULTILINE)
    return {f"{int(left)}-{int(right)}" for left, right in pattern.findall(text)}


def table_structure_risks(text: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    risks: list[dict[str, object]] = []
    for index, line in enumerate(lines):
        match = TABLE_TITLE_PATTERN.match(line)
        if match is None:
            continue
        reasons: list[str] = []
        if len(line.strip()) > 120:
            reasons.append("title_line_over_120_chars")
        following = lines[index + 1 : index + 26]
        if not any(STRUCTURED_BLOCK_PATTERN.match(candidate) for candidate in following):
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


def normalize(text: str) -> str:
    text = re.sub(r"兰亭图书阁", "", text)
    text = re.sub(r"系统架构设计师教程\s*[（(]?第?2版[）)]?", "", text)
    text = re.sub(r"第\s*\d+\s*章[^\n]{0,30}", "", text)
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", text)).lower()


def formula_carrier_lines(lines: list[str], needles: list[str]) -> tuple[list[int], bool]:
    matched = {needle: [index + 1 for index, line in enumerate(lines) if needle in line] for needle in needles}
    carrier_lines = sorted({line_number for numbers in matched.values() for line_number in numbers})
    return carrier_lines, all(matched.values())


class MarkdownView:
    """Recomputes every Markdown-derived field of the textbook audit ledger."""

    def __init__(self, ledger: dict[str, object]) -> None:
        self.ledger = ledger
        self.issues: list[str] = []
        self.lines: dict[str, list[str]] = {}
        self.normalized_chars: dict[str, int] = {}
        self.risks: dict[str, list[dict[str, object]]] = {}
        self.carrier_lines: dict[str, dict[str, list[int]]] = {"figure": {}, "table": {}}
        self.pdf_numbers: dict[str, dict[int, set[str]]] = {"figure": {}, "table": {}}

    def issue(self, message: str) -> None:
        if message not in self.issues:
            self.issues.append(message)

    def read_chapter(self, chapter: int, relative_path: str) -> None:
        if relative_path in self.lines:
            return
        text = (ROOT / relative_path).read_text(encoding="utf-8-sig")
        self.lines[relative_path] = text.splitlines()
        self.normalized_chars[relative_path] = len(normalize(text))
        self.risks[relative_path] = table_structure_risks(text)
        for kind, marker in (("figure", "图"), ("table", "表")):
            carriers = markdown_carrier_lines(text, kind)
            for number, line_numbers in carriers.items():
                merged = sorted({*self.carrier_lines[kind].get(number, []), *line_numbers})
                self.carrier_lines[kind][number] = merged
            declared = independent_numbers(text, marker)
            if set(carriers) != declared:
                self.issue(
                    f"chapter {chapter} {marker} carriers ({len(carriers)}) disagree with independent "
                    f"{marker} numbers ({len(declared)})"
                )
            for number in carriers:
                if number_key(number)[0] != chapter:
                    self.issue(f"chapter {chapter} carries {kind} {number} outside its own chapter")

    def collect(self) -> None:
        chapters = self.ledger.get("chapters")
        if not isinstance(chapters, list):
            raise SystemExit("ledger chapters must be a list")
        for chapter in chapters:
            assert isinstance(chapter, dict)
            self.read_chapter(int(chapter["chapter"]), str(chapter["path"]))
        inventory = self.ledger.get("asset_inventory")
        assert isinstance(inventory, dict)
        for kind, group in (("figure", FIGURE_GROUP), ("table", TABLE_GROUP)):
            for item in inventory[group]:
                self.pdf_numbers[kind].setdefault(int(item["chapter"]), set()).add(str(item["number"]))

    def all_pdf_numbers(self, kind: str) -> set[str]:
        return {number for numbers in self.pdf_numbers[kind].values() for number in numbers}

    def all_risks(self) -> list[dict[str, object]]:
        return [copy.deepcopy(risk) for path in sorted(self.risks) for risk in self.risks[path]]

    def apply(self) -> dict[str, object]:
        self.collect()
        updated = copy.deepcopy(self.ledger)
        assert isinstance(updated, dict)
        risk_numbers = {str(risk["number"]) for risk in self.all_risks()}

        for chapter in updated["chapters"]:
            number = int(chapter["chapter"])
            relative_path = str(chapter["path"])
            chapter["normalized_markdown_chars"] = self.normalized_chars[relative_path]
            chapter["markdown_to_pdf_char_ratio"] = round(
                self.normalized_chars[relative_path] / max(1, int(chapter["normalized_pdf_chars"])), 6
            )
            assets = chapter["assets"]
            for kind, key, count_key, missing_key in CHAPTER_ASSET_FIELDS:
                owned = self.pdf_numbers[kind].get(number, set())
                found = {value for value in self.carrier_lines[kind] if number_key(value)[0] == number}
                assets[key] = len(found)
                assets[missing_key] = sorted(owned - found, key=number_key)
                if int(assets[count_key]) != len(owned):
                    self.issue(
                        f"chapter {number} frozen {count_key}={assets[count_key]} differs from the "
                        f"{len(owned)} inventory numbers owned by that chapter"
                    )
            assets["table_structure_risks"] = copy.deepcopy(self.risks[relative_path])

        inventory = updated["asset_inventory"]
        for kind, group, status in (
            ("figure", FIGURE_GROUP, CARRIER_STATUS),
            ("table", TABLE_GROUP, STRUCTURED_CARRIER_STATUS),
        ):
            for item in inventory[group]:
                number = str(item["number"])
                lines = sorted(self.carrier_lines[kind].get(number, []))
                item["markdown_carrier_lines"] = lines
                if not lines:
                    item["status"] = MISSING_CARRIER_STATUS
                elif kind == "table" and number in risk_numbers:
                    item["status"] = STRUCTURE_RISK_STATUS
                else:
                    item["status"] = status

        inventory_by_key = {
            (kind, str(item["number"])): item
            for kind, group in (("figure", FIGURE_GROUP), ("table", TABLE_GROUP))
            for item in inventory[group]
        }
        for record in updated["baseline_evidence"]["records"]:
            item = inventory_by_key.get((str(record["kind"]), str(record["nearest_asset_number"])))
            if item is None:
                self.issue(f"baseline record {record['id']} has no asset inventory entry")
                continue
            record["current_markdown_carrier_lines"] = list(item["markdown_carrier_lines"])
            record["current_status"] = item["status"]
        for item in updated["additional_unmarked_figures"]:
            source = inventory_by_key.get(("figure", str(item["number"])))
            if source is None:
                self.issue(f"additional unmarked figure {item['id']} has no asset inventory entry")
                continue
            item["markdown_carrier_lines"] = list(source["markdown_carrier_lines"])
            item["status"] = source["status"]

        for candidate in updated["historical_spliced_tables"]["reconstructed_candidates"]:
            number = str(candidate["number"])
            source = inventory_by_key.get(("table", number))
            if source is None:
                self.issue(f"reconstructed spliced table {number} has no asset inventory entry")
                continue
            carrier_lines = list(source["markdown_carrier_lines"])
            candidate["current_markdown_carrier_lines"] = carrier_lines
            lines = self.lines[str(candidate["path"])]
            if not any(
                line.strip().startswith("|") and line.strip().endswith("|")
                for carrier_line in carrier_lines
                for line in lines[carrier_line : carrier_line + 8]
            ):
                self.issue(f"reconstructed spliced table {number} lacks a current pipe-table carrier")

        updated["historical_spliced_tables"]["current_state_evidence"] = {
            "official_pdf_table_inventory": len(inventory[TABLE_GROUP]),
            "markdown_table_carriers": len(self.carrier_lines["table"]),
            "table_structure_risks": self.all_risks(),
        }

        for item in updated["formula_status_items"]:
            carrier_lines, complete = self.formula_view(item)
            item["markdown_carrier_lines"] = carrier_lines
            item["status"] = FORMULA_PRESENT_STATUS if complete else FORMULA_INCOMPLETE_STATUS

        for item in updated["additional_unmarked_formulas"]:
            carrier_lines, complete = self.formula_view(item)
            anchor_index = carrier_lines[0] - 1 if carrier_lines else 0
            heading_line, heading = nearest_heading(self.lines[str(item["path"])], anchor_index)
            item["markdown_carrier_lines"] = carrier_lines
            item["nearest_heading_line"] = heading_line
            item["nearest_heading"] = heading
            item["status"] = FORMULA_PRESENT_STATUS if complete else FORMULA_INCOMPLETE_STATUS

        summary = updated["summary"]
        summary["markdown_unique_figure_carriers"] = len(self.carrier_lines["figure"])
        summary["markdown_unique_table_titles"] = len(self.carrier_lines["table"])
        summary["missing_figure_carriers"] = sorted(
            self.all_pdf_numbers("figure") - set(self.carrier_lines["figure"]), key=number_key
        )
        summary["missing_table_titles"] = sorted(
            self.all_pdf_numbers("table") - set(self.carrier_lines["table"]), key=number_key
        )
        summary["table_structure_risks"] = self.all_risks()
        return updated

    def formula_view(self, item: dict[str, object]) -> tuple[list[int], bool]:
        needles = item.get("current_needles")
        if not isinstance(needles, list) or not needles:
            self.issue(f"formula item {item.get('id')} has no current_needles to recompute from")
            committed = item.get("markdown_carrier_lines")
            return ([int(value) for value in committed] if isinstance(committed, list) else []), False
        return formula_carrier_lines(self.lines[str(item["path"])], [str(needle) for needle in needles])


def diff_fields(expected: object, actual: object, path: str = "") -> list[str]:
    """Report every field where the recomputed ledger differs from the committed one."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        changes: list[str] = []
        for key in sorted(set(expected) | set(actual), key=str):
            child = f"{path}.{key}" if path else str(key)
            if key not in expected:
                changes.append(f"{child}: only in the committed ledger")
            elif key not in actual:
                changes.append(f"{child}: only in the recomputed ledger")
            else:
                changes.extend(diff_fields(expected[key], actual[key], child))
        return changes
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{path}: list length {len(expected)} -> {len(actual)}"]
        changes = []
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual, strict=True)):
            changes.extend(diff_fields(expected_item, actual_item, f"{path}[{index}]"))
        return changes
    if expected != actual:
        return [f"{path}: {expected!r} -> {actual!r}"]
    return []


def render(ledger: dict[str, object]) -> str:
    return json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify the committed ledger without writing it")
    parser.add_argument("--limit", type=int, default=40, help="maximum drift lines to print in --check mode")
    args = parser.parse_args(argv)

    relative_path = AUDIT_PATH.relative_to(ROOT).as_posix()
    ledger = json.loads(AUDIT_PATH.read_text(encoding="utf-8-sig"))
    view = MarkdownView(ledger)
    updated = view.apply()
    changes = diff_fields(ledger, updated)

    if args.check:
        for issue in view.issues:
            print(f"integrity: {issue}", file=sys.stderr)
        if not changes and not view.issues:
            print(
                f"PASSED: {relative_path} matches the current clean Markdown "
                f"({len(ledger['chapters'])} chapters, {len(view.carrier_lines['figure'])} figure carriers, "
                f"{len(view.carrier_lines['table'])} table carriers)."
            )
            return 0
        for change in changes[: args.limit]:
            print(f"drift: {change}", file=sys.stderr)
        if len(changes) > args.limit:
            print(f"drift: … {len(changes) - args.limit} more field(s)", file=sys.stderr)
        print(
            f"FAILED: {len(changes)} Markdown-derived field(s) no longer match the clean Markdown; run "
            "`uv run python scripts/build_textbook_markdown_view.py` and commit the refreshed ledger.",
            file=sys.stderr,
        )
        return 1

    for issue in view.issues:
        print(f"integrity (not auto-fixable here): {issue}", file=sys.stderr)
    if changes:
        AUDIT_PATH.write_text(render(updated), encoding="utf-8", newline="\n")
        print(f"updated {len(changes)} Markdown-derived field(s) in {relative_path}.")
    else:
        print(f"{relative_path} is already up to date.")
    return 1 if view.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
