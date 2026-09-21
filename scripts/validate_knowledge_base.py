#!/usr/bin/env python3
"""Validate the repository's Markdown knowledge-base invariants.

This script intentionally uses only the Python standard library so the same
checks run locally and in GitHub Actions without installing dependencies.
It is executed through uv (``uv run python scripts/validate_knowledge_base.py``),
which pins the interpreter to the version in ``.python-version``.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import unquote

# The pinned interpreter is declared in .python-version.  Running the validator
# with an older system Python would otherwise fail deep inside the script (for
# example on tomllib, which is 3.11+); fail fast with an actionable message
# instead.
REQUIRED_PYTHON = (3, 13)
if sys.version_info < REQUIRED_PYTHON:
    raise SystemExit(
        "ERROR: this repository pins Python "
        f"{'.'.join(map(str, REQUIRED_PYTHON))} (see .python-version), but this "
        f"is Python {'.'.join(map(str, sys.version_info[:3]))}. Run the script "
        "through uv instead: `uv run python scripts/validate_knowledge_base.py`. "
        "Install uv from https://docs.astral.sh/uv/getting-started/installation/"
    )

# Imported after the interpreter check above, because tomllib is 3.11+ and the
# check produces a better message than an ImportError traceback.
import tomllib  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
# Raw (pre-clean) archives live under data/; the cleaned versions stay at the
# repository root.
CONTENT_DIRS = (
    DATA_DIR / "00.系统架构设计师考试大纲",
    ROOT / "00.系统架构设计师考试大纲-清洗版",
    DATA_DIR / "01.系统架构设计师教材",
    ROOT / "01.系统架构设计师教材-清洗版",
    DATA_DIR / "02.历年真题",
    ROOT / "02.历年真题-清洗版",
    DATA_DIR / "02.历年真题(补充)",
)
CLEAN_DIRS = tuple(path for path in CONTENT_DIRS if path.name.endswith("-清洗版"))
CHAPTER_DIRS = CONTENT_DIRS[:4]
EXAM_SOURCE_DIRS = (DATA_DIR / "02.历年真题", DATA_DIR / "02.历年真题(补充)")
MANIFEST_PATH = ROOT / "data" / "exams.json"
MASTER_INDEX_PATH = ROOT / "02.历年真题总索引.md"
CLEAN_EXAM_INDEX_PATH = ROOT / "02.历年真题-清洗版" / "INDEX.md"

# uv toolchain pins.  The Python version and the lockfile are declared in
# separate files; these checks keep the copies from drifting.
PYPROJECT_PATH = ROOT / "pyproject.toml"
PYTHON_VERSION_PATH = ROOT / ".python-version"
UV_LOCK_PATH = ROOT / "uv.lock"
PYTHON_VERSION = "3.13"
REQUIRES_PYTHON = ">=3.13"
# Non-default dependency group, pinning exactly one package.  It is not
# installed for the main gate, which must keep running on the standard library.
DEPENDENCY_GROUPS = {"lint": "ruff"}

# Unbracketed link targets may contain one level of balanced parentheses so
# that paths like ../data/02.历年真题(补充)/x.md parse without angle brackets;
# unbalanced parentheses still fail to match and surface as broken links.
LINK_RE = re.compile(
    r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^\s()]+(?:\([^\s()]*\)[^\s()]*)*)"
    r"(?:\s+[\"'][^)]*[\"'])?\)"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+")
# CommonMark fenced code blocks: backtick or tilde fences of length >= 3,
# indented by at most three spaces.  A fence closes only with the same marker
# character at a length >= the opening run.
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
EXAM_NAME_RE = re.compile(
    r"^(?P<year>\d{4})年(?P<session>上半年|下半年)-系统架构设计师-"
    r"(?P<subject>综合知识|案例分析|论文)\.md$"
)
EXAM_COUNT_RE = re.compile(r"(?:题目数量|主试题数量|主试题数)(?:\*\*)?[：:](?:\*\*)?\s*(\d+)")
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
STALE_EXAM_METADATA_RE = re.compile(
    r"(?:data/exams\.json|统一清单).{0,120}"
    r"(?:应后续|尚未|待)(?:更新|更正|改为)"
)
SOURCE_VERSION_FIELDS = {
    "source_id",
    "path",
    "item_count",
    "item_unit",
}

# Directories that never contain knowledge-base content.  rglob does not read
# .gitignore, so these (notably .venv/, which local uv environments create
# inside the project) must be excluded explicitly to keep local runs identical
# to CI.
EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "tmp",
        "__pycache__",
        ".idea",
        ".vscode",
        ".claude",
    }
)


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
        return sorted(path for path in ROOT.rglob("*.md") if EXCLUDED_DIR_NAMES.isdisjoint(path.parts))

    def check_markdown_file(self, path: Path) -> None:
        text = self.read_text(path)
        if text is None:
            return
        if not text.strip():
            self.error(path, "empty Markdown file")
            return

        lines = text.splitlines()
        fence_char = ""
        fence_length = 0
        # The first heading may be H1 or H2 (the exam-outline clean files
        # legitimately start at H2); anything deeper is a jump from the
        # implicit document root.
        previous_level = 1
        check_heading_jumps = any(path.is_relative_to(directory) for directory in CLEAN_DIRS)
        for line_number, line in enumerate(lines, start=1):
            fence_match = FENCE_RE.match(line)
            if fence_match:
                marker = fence_match.group(1)
                if fence_char:
                    if marker[0] == fence_char and len(marker) >= fence_length:
                        fence_char = ""
                        fence_length = 0
                else:
                    fence_char = marker[0]
                    fence_length = len(marker)
                continue
            if fence_char:
                continue
            match = HEADING_RE.match(line)
            if not match:
                continue
            level = len(match.group(1))
            if check_heading_jumps and level > previous_level + 1:
                self.error(
                    path,
                    f"heading level jumps H{previous_level}->H{level} at line {line_number}",
                )
            previous_level = level
        if fence_char:
            self.error(path, "unbalanced fenced code block")

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
        for directory in CONTENT_DIRS:
            if not directory.is_dir():
                self.error(directory, "content directory is missing")
                continue
            index = directory / "INDEX.md"
            if not index.is_file():
                self.error(index, "required INDEX.md is missing")
                continue
            index_text = self.read_text(index)
            if index_text is not None and len(index_text.splitlines()) > 200:
                self.error(index, "INDEX.md exceeds 200 lines")
            linked_names = self.extract_local_links(index)
            content_names = {path.name for path in directory.glob("*.md") if path.name != "INDEX.md"}
            missing = sorted(content_names - linked_names)
            if missing:
                self.error(index, f"unindexed Markdown files: {', '.join(missing)}")

        for directory in CHAPTER_DIRS:
            for path in directory.glob("*.md"):
                if path.name in {"INDEX.md", "前言.md"}:
                    continue
                if not re.fullmatch(r"第\d{2}章-.+\.md", path.name):
                    self.error(path, "chapter filename must match 第XX章-标题.md")

    def check_clean_ocr(self) -> None:
        # Every cleaned directory is scanned, not just the textbook: the outline
        # clean-up went unscanned for its whole history because this check used
        # to hardcode a single directory.
        for directory in CLEAN_DIRS:
            for path in sorted(directory.glob("*.md")):
                text = self.read_text(path) or ""
                for label, pattern in OCR_PATTERNS.items():
                    matches = list(pattern.finditer(text))
                    if matches:
                        line_number = text.count("\n", 0, matches[0].start()) + 1
                        self.error(
                            path,
                            f"high-risk OCR residue '{label}' "
                            f"({len(matches)} occurrence(s), first at line {line_number})",
                        )

    def check_markdown_encoding(self) -> None:
        """All Markdown must be UTF-8 without BOM and use CRLF line endings.

        A BOM is decoded away by utf-8-sig, so it silently survives every other
        check while breaking line-start matching and some third-party tooling.
        Git attributes require CRLF for Markdown; enforce it byte-for-byte so
        mixed LF/CRLF files cannot pass locally and then churn on checkout.
        """
        for path in self.markdown_files():
            data = path.read_bytes()
            if data.startswith(b"\xef\xbb\xbf"):
                self.error(path, "Markdown must be UTF-8 without BOM")
            if b"\r" in data.replace(b"\r\n", b""):
                self.error(path, "Markdown must not contain bare CR characters")
            if b"\n" in data.replace(b"\r\n", b""):
                self.error(path, "Markdown must use CRLF line endings")

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

        required_top = {
            "schema_version",
            "updated_at",
            "source_catalog",
            "exams",
        }
        missing_top = required_top - set(manifest)
        if missing_top:
            self.error(MANIFEST_PATH, f"missing top-level fields: {sorted(missing_top)}")
            return
        if manifest.get("schema_version") != 4:
            self.error(MANIFEST_PATH, "schema_version must be 4")
        try:
            date.fromisoformat(str(manifest["updated_at"]))
        except ValueError:
            self.error(MANIFEST_PATH, "updated_at must be an ISO date (YYYY-MM-DD)")
        source_catalog = manifest.get("source_catalog")
        if not isinstance(source_catalog, dict):
            self.error(MANIFEST_PATH, "source_catalog must be an object")
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
            "item_unit",
            "preferred",
            "alternatives",
            "same_name_conflict",
            "source_versions",
            "notes",
        }
        ids: set[str] = set()
        manifest_keys: set[tuple[int, str, str]] = set()
        referenced_paths: set[str] = set()
        source_version_paths: set[str] = set()
        source_version_count = 0
        valid_exams: list[dict[str, object]] = []
        for position, exam in enumerate(exams, start=1):
            if not isinstance(exam, dict):
                self.error(MANIFEST_PATH, f"exam #{position} is not an object")
                continue
            missing = required_fields - set(exam)
            if missing:
                self.error(MANIFEST_PATH, f"exam #{position} missing fields: {sorted(missing)}")
                continue
            exam_id = str(exam["id"])
            try:
                key = (int(exam["year"]), str(exam["session"]), str(exam["subject"]))
            except (TypeError, ValueError) as exc:
                self.error(
                    MANIFEST_PATH,
                    f"{exam_id}: invalid year/session/subject metadata ({exc})",
                )
                continue
            valid_exams.append(exam)
            if exam_id in ids:
                self.error(MANIFEST_PATH, f"duplicate exam id: {exam_id}")
            ids.add(exam_id)
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

            source_versions = exam["source_versions"]
            if not isinstance(source_versions, list):
                self.error(MANIFEST_PATH, f"{exam_id}: source_versions must be an array")
                continue
            source_version_count += len(source_versions)
            exam_version_paths: set[str] = set()
            for version_position, version in enumerate(source_versions, start=1):
                label = f"{exam_id}: source_versions #{version_position}"
                if not isinstance(version, dict):
                    self.error(MANIFEST_PATH, f"{label} is not an object")
                    continue
                raw_relative_path = version.get("path")
                if isinstance(raw_relative_path, str):
                    exam_version_paths.add(raw_relative_path)
                missing_version_fields = SOURCE_VERSION_FIELDS - set(version)
                if missing_version_fields:
                    self.error(
                        MANIFEST_PATH,
                        f"{label} missing fields: {sorted(missing_version_fields)}",
                    )
                    continue

                source_id = version["source_id"]
                if not isinstance(source_id, str) or source_id not in source_catalog:
                    self.error(MANIFEST_PATH, f"{label} has unknown source_id {source_id!r}")
                    continue
                catalog_entry = source_catalog[source_id]
                if not isinstance(catalog_entry, dict) or not isinstance(catalog_entry.get("root"), str):
                    self.error(
                        MANIFEST_PATH,
                        f"source_catalog.{source_id}.root must be text",
                    )
                    continue

                relative_path = version["path"]
                if not isinstance(relative_path, str):
                    self.error(MANIFEST_PATH, f"{label} path is not text")
                    continue
                if relative_path in source_version_paths:
                    self.error(
                        MANIFEST_PATH,
                        f"{label} duplicates source-version path {relative_path}",
                    )
                source_version_paths.add(relative_path)
                expected_root = str(catalog_entry["root"]).rstrip("/")
                if not relative_path.startswith(f"{expected_root}/"):
                    self.error(
                        MANIFEST_PATH,
                        f"{label} path is outside source root {expected_root}",
                    )

                candidate = (ROOT / Path(relative_path)).resolve()
                if not candidate.is_relative_to(ROOT):
                    self.error(MANIFEST_PATH, f"{label} path escapes repository root")
                    continue
                if not candidate.is_file():
                    self.error(MANIFEST_PATH, f"{label} file is missing: {relative_path}")
                    continue

            expected_version_paths = {
                relative_path for relative_path in [exam["preferred"], *alternatives] if isinstance(relative_path, str)
            }
            if exam_version_paths != expected_version_paths:
                missing_versions = sorted(expected_version_paths - exam_version_paths)
                extra_versions = sorted(exam_version_paths - expected_version_paths)
                self.error(
                    MANIFEST_PATH,
                    f"{exam_id}: source_versions path mismatch; missing={missing_versions}, extra={extra_versions}",
                )

        source_keys: set[tuple[int, str, str]] = set()
        source_paths: set[str] = set()
        for directory in EXAM_SOURCE_DIRS:
            for path in directory.glob("*.md"):
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
        conflict_count = sum(bool(exam.get("same_name_conflict")) for exam in exams)
        if conflict_count != 17:
            self.error(MANIFEST_PATH, f"expected 17 same-name conflicts, found {conflict_count}")
        if source_version_count != 90:
            self.error(
                MANIFEST_PATH,
                f"expected 90 source_versions, found {source_version_count}",
            )

        for exam in valid_exams:
            self.check_canonical_clean_exam(exam)

        index_specs = (
            (
                MASTER_INDEX_PATH,
                lambda preferred: preferred,
                {"period": 0, "subject": 1, "count": 3, "notes": 6},
            ),
            (
                CLEAN_EXAM_INDEX_PATH,
                lambda preferred: Path(preferred).name,
                {"period": 0, "subject": 1, "count": 4, "notes": 5},
            ),
        )
        for index_path, target_for, columns in index_specs:
            if not index_path.is_file():
                self.error(index_path, "exam index is missing")
                continue
            index_text = self.read_text(index_path) or ""
            index_lines = index_text.splitlines()
            for exam in valid_exams:
                exam_id = str(exam.get("id", "unknown"))
                preferred = exam.get("preferred")
                if not isinstance(preferred, str):
                    continue
                target = target_for(preferred)
                rows = [line for line in index_lines if line.startswith("|") and target in line]
                if len(rows) != 1:
                    self.error(
                        index_path,
                        f"expected one row for {exam_id} ({target}), found {len(rows)}",
                    )
                    continue
                cells = [cell.strip() for cell in rows[0].strip().strip("|").split("|")]
                if len(cells) <= max(columns.values()):
                    self.error(
                        index_path,
                        f"row for {exam_id} has too few columns ({len(cells)})",
                    )
                    continue
                session_label = "上" if exam.get("session") == "上半年" else "下"
                expected_cells = {
                    "period": f"{exam.get('year')}{session_label}",
                    "subject": str(exam.get("subject", "")),
                    "count": f"{exam.get('item_count')}{exam.get('item_unit')}",
                }
                for field, expected in expected_cells.items():
                    actual = cells[columns[field]]
                    if not expected:
                        self.error(
                            MANIFEST_PATH,
                            f"{exam_id}: unsupported {field} value for index mapping",
                        )
                    elif actual != expected:
                        self.error(
                            index_path,
                            f"row for {exam_id} has {field} {actual!r}, expected {expected!r}",
                        )
                notes = exam.get("notes")
                if not isinstance(notes, str) or not notes.strip():
                    self.error(MANIFEST_PATH, f"{exam_id}: notes must be non-empty text")
                else:
                    expected_notes = notes
                    if index_path == MASTER_INDEX_PATH and exam.get("same_name_conflict"):
                        expected_notes = f"**同名冲突，禁止自动混并。** {notes}"
                if isinstance(notes, str) and cells[columns["notes"]] != expected_notes:
                    self.error(
                        index_path,
                        f"row for {exam_id} does not match manifest notes",
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

        clean_relative = f"02.历年真题-清洗版/{year}年{session}-系统架构设计师-{subject}.md"
        clean_path = ROOT / clean_relative
        if not clean_path.is_file():
            self.error(clean_path, f"canonical clean file for {exam_id} is missing")
            return
        if exam.get("preferred") != clean_relative:
            self.error(
                MANIFEST_PATH,
                f"{exam_id}: preferred must be canonical clean file {clean_relative}",
            )

        text = self.read_text(clean_path) or ""
        stale_match = STALE_EXAM_METADATA_RE.search(text)
        if stale_match:
            line_number = text.count("\n", 0, stale_match.start()) + 1
            self.error(
                clean_path,
                f"stale manifest/index correction note at line {line_number}",
            )
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

        numbers = [self.main_question_number(value) for value in MAIN_QUESTION_HEADING_RE.findall(text)]
        if any(number is None for number in numbers):
            self.error(clean_path, "contains an unsupported main-question numeral")
            return
        if len(numbers) != declared or numbers != sorted(set(numbers)):
            self.error(
                clean_path,
                f"expected {declared} unique ascending main-question headings, found {numbers}",
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
            question_matches = list(QUESTION_HEADING_RE.finditer(text))
            numbers = [int(match.group(1)) for match in question_matches]
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

    def check_python_toolchain(self) -> None:
        """Assert the uv toolchain pins agree across all files that repeat them."""
        pinned = PYTHON_VERSION_PATH.read_text(encoding="utf-8-sig").strip()
        if pinned != PYTHON_VERSION:
            self.error(
                PYTHON_VERSION_PATH,
                f"pinned Python must be {PYTHON_VERSION}, found {pinned!r}",
            )

        try:
            pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8-sig"))
        except tomllib.TOMLDecodeError as exc:
            self.error(PYPROJECT_PATH, f"is not valid TOML ({exc})")
            return

        project = pyproject.get("project")
        if not isinstance(project, dict):
            self.error(PYPROJECT_PATH, "[project] table is missing")
            return
        if project.get("requires-python") != REQUIRES_PYTHON:
            self.error(
                PYPROJECT_PATH,
                f"project.requires-python must be {REQUIRES_PYTHON!r}, found {project.get('requires-python')!r}",
            )
        if project.get("dependencies") != []:
            self.error(
                PYPROJECT_PATH,
                "project.dependencies must stay empty; the validator runs on the standard library alone",
            )
        if pyproject.get("tool", {}).get("uv", {}).get("package") is not False:
            self.error(PYPROJECT_PATH, "tool.uv.package must be false")

        groups = pyproject.get("dependency-groups")
        if not isinstance(groups, dict) or set(groups) != set(DEPENDENCY_GROUPS):
            self.error(
                PYPROJECT_PATH,
                f"dependency-groups must declare exactly {sorted(DEPENDENCY_GROUPS)}",
            )
            return
        # Every group holds a single, exactly pinned requirement: the committed
        # formatting is only reproducible at one version.
        for group_name, expected_package in DEPENDENCY_GROUPS.items():
            requirements = groups[group_name]
            if (
                not isinstance(requirements, list)
                or len(requirements) != 1
                or not str(requirements[0]).startswith(f"{expected_package}==")
            ):
                self.error(
                    PYPROJECT_PATH,
                    f"dependency-groups.{group_name} must hold exactly one `{expected_package}==<version>` requirement",
                )
                return

        lock_text = UV_LOCK_PATH.read_text(encoding="utf-8-sig")
        try:
            lock = tomllib.loads(lock_text)
        except tomllib.TOMLDecodeError as exc:
            self.error(UV_LOCK_PATH, f"is not valid TOML ({exc})")
            return
        if lock.get("requires-python") != REQUIRES_PYTHON:
            self.error(
                UV_LOCK_PATH,
                f"requires-python must be {REQUIRES_PYTHON!r}; run `uv lock`",
            )

    def run(self) -> int:
        markdown_files = self.markdown_files()
        for path in markdown_files:
            self.check_markdown_file(path)
        self.check_content_directories()
        self.check_markdown_encoding()
        self.check_clean_ocr()
        self.check_exam_manifest()
        self.check_clean_exam_counts()
        self.check_python_toolchain()

        print(
            f"Checked {len(markdown_files)} Markdown files, "
            f"{len(CONTENT_DIRS)} content directories, the exam manifest "
            "and the uv toolchain pins."
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
