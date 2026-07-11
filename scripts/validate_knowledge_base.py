#!/usr/bin/env python3
"""Validate the repository's Markdown knowledge-base invariants.

This script intentionally uses only the Python standard library so the same
checks run locally and in GitHub Actions without installing dependencies.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIRS = (
    "00.系统架构设计师考试大纲",
    "00.系统架构设计师考试大纲-清洗版",
    "01.系统架构设计师教材",
    "01.系统架构设计师教材-清洗版",
    "02.历年真题",
    "02.历年真题-清洗版",
    "02.历年真题(补充)",
)
CLEAN_DIRS = tuple(name for name in CONTENT_DIRS if name.endswith("-清洗版"))
CHAPTER_DIRS = CONTENT_DIRS[:4]
EXAM_SOURCE_DIRS = ("02.历年真题", "02.历年真题(补充)")
MANIFEST_PATH = ROOT / "data" / "exams.json"
MASTER_INDEX_PATH = ROOT / "02.历年真题总索引.md"

LINK_RE = re.compile(
    r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^\s)]+)(?:\s+[\"'][^)]*[\"'])?\)"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+")
EXAM_NAME_RE = re.compile(
    r"^(?P<year>\d{4})年(?P<session>上半年|下半年)-系统架构设计师-"
    r"(?P<subject>综合知识|案例分析|论文)\.md$"
)
EXAM_COUNT_RE = re.compile(
    r"(?:题目数量|主试题数量|主试题数)(?:\*\*)?[：:](?:\*\*)?\s*(\d+)"
)
ANSWER_RE = re.compile(r"\*\*正确答案[：:]")
QUESTION_HEADING_RE = re.compile(r"^#{2,3}\s+第(\d+)题\s*$", re.MULTILINE)
MAIN_QUESTION_HEADING_RE = re.compile(
    r"^##\s+试题\s*([一二三四五六七八九十]+|\d+)(?=[（(:：\s]|$)",
    re.MULTILINE,
)
OPTION_RE = re.compile(r"^-\s+\*\*[A-D]\.\*\*", re.MULTILINE)
CHINESE_NUMERALS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

OCR_PATTERNS = {
    "watermark": re.compile(r"兰亭图书阁"),
    "raw page header": re.compile(r"系统架构设计师教程\s*[（(]第2版[）)]"),
    "Outer Jion": re.compile(r"Outer Jion", re.IGNORECASE),
    "broken Information": re.compile(r"Infor-mation"),
    "broken Key-Value": re.compile(r"Key-Valuc"),
    "broken Recommended": re.compile(r"Recommand Practice"),
    "broken NB-IoT": re.compile(r"NB-loT"),
    "broken BaseManager": re.compile(r"BascManagcr"),
    "broken Federation": re.compile(r"Federetion Wait"),
    "unknown process symbol": re.compile(r"\bP\?"),
}


class Validator:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.text_cache: dict[Path, str] = {}

    @staticmethod
    def relative(path: Path) -> str:
        return path.relative_to(ROOT).as_posix()

    def error(self, path: Path | str, message: str) -> None:
        label = self.relative(path) if isinstance(path, Path) else path
        self.errors.append(f"{label}: {message}")

    def warn(self, path: Path | str, message: str) -> None:
        label = self.relative(path) if isinstance(path, Path) else path
        self.warnings.append(f"{label}: {message}")

    def read_text(self, path: Path) -> str | None:
        if path in self.text_cache:
            return self.text_cache[path]
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            self.error(path, f"not valid UTF-8 ({exc})")
            return None
        self.text_cache[path] = text
        return text

    def markdown_files(self) -> list[Path]:
        return sorted(
            path
            for path in ROOT.rglob("*.md")
            if ".git" not in path.parts
        )

    def check_markdown_file(self, path: Path) -> None:
        text = self.read_text(path)
        if text is None:
            return
        if not text.strip():
            self.error(path, "empty Markdown file")
            return

        lines = text.splitlines()
        if sum(1 for line in lines if line.startswith("```")) % 2:
            self.error(path, "unbalanced fenced code block")

        in_fence = False
        previous_level = 0
        check_heading_jumps = any(
            path.is_relative_to(ROOT / directory) for directory in CLEAN_DIRS
        )
        for line_number, line in enumerate(lines, start=1):
            if line.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            match = HEADING_RE.match(line)
            if not match:
                continue
            level = len(match.group(1))
            if check_heading_jumps and previous_level and level > previous_level + 1:
                self.error(
                    path,
                    f"heading level jumps H{previous_level}->H{level} at line {line_number}",
                )
            previous_level = level

        for match in LINK_RE.finditer(text):
            raw_target = match.group("target").strip("<>")
            if raw_target.startswith(("http://", "https://", "mailto:", "#", "data:")):
                continue
            file_part = unquote(raw_target.split("#", 1)[0])
            if not file_part:
                continue
            target = (path.parent / file_part).resolve()
            if not target.exists():
                line_number = text.count("\n", 0, match.start()) + 1
                self.error(path, f"broken local link at line {line_number}: {raw_target}")

    def extract_local_links(self, path: Path) -> set[str]:
        text = self.read_text(path) or ""
        targets: set[str] = set()
        for match in LINK_RE.finditer(text):
            target = unquote(match.group("target").strip("<>").split("#", 1)[0])
            if target and not target.startswith(("http://", "https://", "mailto:")):
                targets.add(Path(target).name)
        return targets

    def check_content_directories(self) -> None:
        for directory_name in CONTENT_DIRS:
            directory = ROOT / directory_name
            if not directory.is_dir():
                self.error(directory_name, "content directory is missing")
                continue
            index = directory / "INDEX.md"
            if not index.is_file():
                self.error(index, "required INDEX.md is missing")
                continue
            index_text = self.read_text(index)
            if index_text is not None and len(index_text.splitlines()) > 200:
                self.error(index, "INDEX.md exceeds 200 lines")
            linked_names = self.extract_local_links(index)
            content_names = {
                path.name for path in directory.glob("*.md") if path.name != "INDEX.md"
            }
            missing = sorted(content_names - linked_names)
            if missing:
                self.error(index, f"unindexed Markdown files: {', '.join(missing)}")

        for directory_name in CHAPTER_DIRS:
            directory = ROOT / directory_name
            for path in directory.glob("*.md"):
                if path.name in {"INDEX.md", "前言.md"}:
                    continue
                if not re.fullmatch(r"第\d{2}章-.+\.md", path.name):
                    self.error(path, "chapter filename must match 第XX章-标题.md")

    def check_clean_ocr(self) -> None:
        directory = ROOT / "01.系统架构设计师教材-清洗版"
        for path in sorted(directory.glob("*.md")):
            text = self.read_text(path) or ""
            for label, pattern in OCR_PATTERNS.items():
                matches = list(pattern.finditer(text))
                if matches:
                    line_number = text.count("\n", 0, matches[0].start()) + 1
                    self.error(
                        path,
                        f"high-risk OCR residue '{label}' ({len(matches)} occurrence(s), first at line {line_number})",
                    )

    @staticmethod
    def exam_key_from_name(path: Path) -> tuple[int, str, str] | None:
        match = EXAM_NAME_RE.fullmatch(path.name)
        if not match:
            return None
        return (
            int(match.group("year")),
            match.group("session"),
            match.group("subject"),
        )

    def check_exam_manifest(self) -> None:
        if not MANIFEST_PATH.is_file():
            self.error(MANIFEST_PATH, "exam manifest is missing")
            return
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.error(MANIFEST_PATH, f"invalid JSON: {exc}")
            return

        required_top = {"schema_version", "updated_at", "source_catalog", "exams"}
        missing_top = required_top - set(manifest)
        if missing_top:
            self.error(MANIFEST_PATH, f"missing top-level fields: {sorted(missing_top)}")
            return
        exams = manifest.get("exams")
        if not isinstance(exams, list):
            self.error(MANIFEST_PATH, "exams must be an array")
            return

        required_fields = {
            "id",
            "year",
            "session",
            "subject",
            "item_count",
            "completeness",
            "answer_confidence",
            "clean_status",
            "preferred",
            "alternatives",
            "notes",
        }
        ids: set[str] = set()
        manifest_keys: set[tuple[int, str, str]] = set()
        referenced_paths: set[str] = set()
        valid_exams: list[dict[str, object]] = []
        for position, exam in enumerate(exams, start=1):
            if not isinstance(exam, dict):
                self.error(MANIFEST_PATH, f"exam #{position} is not an object")
                continue
            missing = required_fields - set(exam)
            if missing:
                self.error(MANIFEST_PATH, f"exam #{position} missing fields: {sorted(missing)}")
                continue
            valid_exams.append(exam)
            exam_id = str(exam["id"])
            if exam_id in ids:
                self.error(MANIFEST_PATH, f"duplicate exam id: {exam_id}")
            ids.add(exam_id)
            key = (int(exam["year"]), str(exam["session"]), str(exam["subject"]))
            if key in manifest_keys:
                self.error(MANIFEST_PATH, f"duplicate canonical exam: {key}")
            manifest_keys.add(key)
            alternatives = exam["alternatives"]
            if not isinstance(alternatives, list):
                self.error(MANIFEST_PATH, f"{exam_id}: alternatives must be an array")
                alternatives = []
            for relative_path in [exam["preferred"], *alternatives]:
                if not isinstance(relative_path, str):
                    self.error(MANIFEST_PATH, f"{exam_id}: path is not a string")
                    continue
                referenced_paths.add(relative_path)
                if not (ROOT / Path(relative_path)).is_file():
                    self.error(MANIFEST_PATH, f"{exam_id}: missing file {relative_path}")

        source_keys: set[tuple[int, str, str]] = set()
        source_paths: set[str] = set()
        for directory_name in EXAM_SOURCE_DIRS:
            for path in (ROOT / directory_name).glob("*.md"):
                if path.name == "INDEX.md":
                    continue
                key = self.exam_key_from_name(path)
                if key is None:
                    self.error(path, "unexpected exam filename")
                    continue
                source_keys.add(key)
                source_paths.add(self.relative(path))

        if manifest_keys != source_keys:
            missing = sorted(source_keys - manifest_keys)
            extra = sorted(manifest_keys - source_keys)
            if missing:
                self.error(MANIFEST_PATH, f"canonical source exams missing from manifest: {missing}")
            if extra:
                self.error(MANIFEST_PATH, f"manifest exams have no source file: {extra}")
        unreferenced_sources = sorted(source_paths - referenced_paths)
        if unreferenced_sources:
            self.error(
                MANIFEST_PATH,
                f"source variants not mapped as preferred/alternative: {unreferenced_sources}",
            )
        if len(exams) != 36:
            self.error(MANIFEST_PATH, f"expected 36 canonical exams, found {len(exams)}")

        for exam in valid_exams:
            self.check_canonical_clean_exam(exam)

        if not MASTER_INDEX_PATH.is_file():
            self.error(MASTER_INDEX_PATH, "master exam index is missing")
        else:
            master_text = self.read_text(MASTER_INDEX_PATH) or ""
            for exam in exams:
                preferred = exam.get("preferred")
                if isinstance(preferred, str) and preferred not in master_text:
                    self.error(
                        MASTER_INDEX_PATH,
                        f"preferred path for {exam.get('id')} is not listed",
                    )

    @staticmethod
    def main_question_number(value: str) -> int | None:
        if value.isdigit():
            return int(value)
        return CHINESE_NUMERALS.get(value)

    def check_canonical_clean_exam(self, exam: dict[str, object]) -> None:
        exam_id = str(exam.get("id", "unknown"))
        try:
            year = int(exam["year"])
            session = str(exam["session"])
            subject = str(exam["subject"])
            item_count = int(exam["item_count"])
        except (KeyError, TypeError, ValueError) as exc:
            self.error(MANIFEST_PATH, f"{exam_id}: invalid clean-exam metadata ({exc})")
            return

        clean_relative = (
            f"02.历年真题-清洗版/{year}年{session}-系统架构设计师-{subject}.md"
        )
        clean_path = ROOT / clean_relative
        if not clean_path.is_file():
            self.error(clean_path, f"canonical clean file for {exam_id} is missing")
            return
        if exam.get("preferred") != clean_relative:
            self.error(
                MANIFEST_PATH,
                f"{exam_id}: preferred must be canonical clean file {clean_relative}",
            )
        if exam.get("clean_status") not in {"cleaned", "cleaned_needs_review"}:
            self.error(
                MANIFEST_PATH,
                f"{exam_id}: clean_status must identify a completed clean draft",
            )

        text = self.read_text(clean_path) or ""
        count_match = EXAM_COUNT_RE.search(text)
        if not count_match:
            self.error(clean_path, "missing 题目数量/主试题数量 metadata")
            return
        declared = int(count_match.group(1))
        if declared != item_count:
            self.error(
                clean_path,
                f"declares {declared} item(s), manifest records {item_count}",
            )

        if subject == "综合知识":
            return

        numbers = [
            self.main_question_number(value)
            for value in MAIN_QUESTION_HEADING_RE.findall(text)
        ]
        if any(number is None for number in numbers):
            self.error(clean_path, "contains an unsupported main-question numeral")
            return
        expected = list(range(1, declared + 1))
        if len(numbers) != declared or numbers != sorted(set(numbers)):
            self.error(
                clean_path,
                f"expected {declared} unique ascending main-question headings, found {numbers}",
            )
        elif exam.get("completeness") == "complete_structural" and numbers != expected:
            self.error(
                clean_path,
                f"main-question headings must be continuous {expected}, found {numbers}",
            )

    def check_clean_exam_counts(self) -> None:
        directory = ROOT / "02.历年真题-清洗版"
        for path in sorted(directory.glob("*综合知识*.md")):
            text = self.read_text(path) or ""
            total_match = EXAM_COUNT_RE.search(text)
            if not total_match:
                self.error(path, "missing 题目数量 metadata")
                continue
            declared = int(total_match.group(1))
            answers = len(ANSWER_RE.findall(text))
            if declared != answers:
                self.error(path, f"declares {declared} questions but has {answers} answers")
            numbers = [int(value) for value in QUESTION_HEADING_RE.findall(text)]
            expected = list(range(1, declared + 1))
            if numbers != expected:
                self.error(
                    path,
                    f"question headings must be continuous {expected}, found {numbers}",
                )
            options = len(OPTION_RE.findall(text))
            if options != declared * 4:
                self.error(
                    path,
                    f"expected {declared * 4} A-D options, found {options}",
                )

    def run(self) -> int:
        markdown_files = self.markdown_files()
        for path in markdown_files:
            self.check_markdown_file(path)
        self.check_content_directories()
        self.check_clean_ocr()
        self.check_exam_manifest()
        self.check_clean_exam_counts()

        print(
            f"Checked {len(markdown_files)} Markdown files, "
            f"{len(CONTENT_DIRS)} content directories and the exam manifest."
        )
        for warning in self.warnings:
            print(f"WARNING: {warning}")
        for error in self.errors:
            print(f"ERROR: {error}")
        if self.errors:
            print(f"FAILED: {len(self.errors)} error(s), {len(self.warnings)} warning(s).")
            return 1
        print(f"PASSED: 0 errors, {len(self.warnings)} warning(s).")
        return 0


if __name__ == "__main__":
    sys.exit(Validator().run())
