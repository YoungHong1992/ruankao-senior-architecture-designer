#!/usr/bin/env python3
"""Validate the repository's Markdown knowledge-base invariants.

This script intentionally uses only the Python standard library so the same
checks run locally and in GitHub Actions without installing dependencies.
It is executed through uv (``uv run python scripts/validate_knowledge_base.py``),
which prepares an interpreter satisfying ``requires-python`` in pyproject.toml.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import unquote

# The floor is declared once, in pyproject.toml's requires-python.  Running the
# validator with an older system Python would otherwise fail deep inside the
# script (for example on tomllib, which is 3.11+); fail fast with an actionable
# message instead.
REQUIRED_PYTHON = (3, 13)
if sys.version_info < REQUIRED_PYTHON:
    raise SystemExit(
        "ERROR: this repository requires Python "
        f"{'.'.join(map(str, REQUIRED_PYTHON))}+ (see requires-python in "
        "pyproject.toml), but this is Python "
        f"{'.'.join(map(str, sys.version_info[:3]))}. Run the script "
        "through uv instead: `uv run python scripts/validate_knowledge_base.py`. "
        "Install uv from https://docs.astral.sh/uv/getting-started/installation/"
    )

# Imported after the interpreter check above, because tomllib is 3.11+ and the
# check produces a better message than an ImportError traceback.
import tomllib  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONTENT_ROOT = ROOT / "content"
SOURCES_ROOT = ROOT / "sources"
CATALOG_ROOT = ROOT / "catalog"
ASSETS_ROOT = ROOT / "assets"
# content/ holds the cleaned prose that the site and the AI knowledge base read;
# sources/ keeps the third-party material the cleaned prose derives from.
OUTLINE_DIR = CONTENT_ROOT / "00-系统架构设计师考试大纲-清洗版"
TEXTBOOK_DIR = CONTENT_ROOT / "01-系统架构设计师教材-清洗版"
CLEAN_EXAM_DIR = CONTENT_ROOT / "02-历年真题-清洗版"
EXAM_SOURCE_DIRS = (
    SOURCES_ROOT / "02-历年真题",
    SOURCES_ROOT / "02-历年真题(补充)",
)
CONTENT_DIRS = (CONTENT_ROOT, OUTLINE_DIR, TEXTBOOK_DIR, CLEAN_EXAM_DIR, *EXAM_SOURCE_DIRS)
CLEAN_DIRS = (OUTLINE_DIR, TEXTBOOK_DIR, CLEAN_EXAM_DIR)
CHAPTER_DIRS = (OUTLINE_DIR, TEXTBOOK_DIR)
# Scanned books are not redistributable, so these directories only carry a
# README describing the expected local file and its checksum.
SOURCE_PDF_DIRS = (
    SOURCES_ROOT / "00-系统架构设计师考试大纲",
    SOURCES_ROOT / "01-系统架构设计师教材",
)
CORPORA_PATH = CATALOG_ROOT / "corpora.json"
MANIFEST_PATH = CATALOG_ROOT / "exams.json"
MASTER_INDEX_PATH = CONTENT_ROOT / "02-历年真题总索引.md"
CLEAN_EXAM_INDEX_PATH = CLEAN_EXAM_DIR / "INDEX.md"
DATA_SOURCES_PATH = ROOT / "DATA_SOURCES.md"
# Layer roots that must exist and must explain themselves to a first-time reader.
LAYER_READMES = (
    CONTENT_ROOT / "INDEX.md",
    SOURCES_ROOT / "README.md",
    CATALOG_ROOT / "README.md",
    ASSETS_ROOT / "README.md",
)

# uv toolchain pins.  requires-python is repeated in pyproject.toml and
# uv.lock; these checks keep the two copies from drifting.
PYPROJECT_PATH = ROOT / "pyproject.toml"
UV_LOCK_PATH = ROOT / "uv.lock"
REQUIRES_PYTHON = ">=3.13"
# Non-default dependency group, pinning exactly one package.  It is not
# installed for the main gate, which must keep running on the standard library.
DEPENDENCY_GROUPS = {"lint": "ruff"}

# Unbracketed link targets may contain one level of balanced parentheses so
# that paths like ../sources/02-历年真题(补充)/x.md parse without angle brackets;
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
    r"(?:catalog/exams\.json|统一清单).{0,120}"
    r"(?:应后续|尚未|待)(?:更新|更正|改为)"
)
SOURCE_VERSION_FIELDS = {
    "source_id",
    "path",
    "item_count",
    "item_unit",
}

# Front matter is a deliberately flat "key: value" block (no nesting, no lists)
# so that the validator can parse it with the standard library alone, and so
# that a static site generator or a retrieval pipeline can read it without a
# YAML dependency.
FRONT_MATTER_FENCE = "---"
FRONT_MATTER_LINE_RE = re.compile(r"^(?P<key>[a-z][a-z0-9_]*): (?P<value>.+)$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SOURCE_PAGES_RE = re.compile(r"^\d+-\d+$")
REQUIRED_FRONT_MATTER = ("id", "corpus", "slug", "title", "kind")
FRONT_MATTER_CORPORA = {"root", "outline", "textbook", "exams"}
FRONT_MATTER_KINDS = {
    "root-index",
    "index",
    "master-index",
    "preface",
    "chapter",
    "section",
    "exam",
    "exam-variant",
}
# Which extra keys each kind must carry beyond REQUIRED_FRONT_MATTER.
FRONT_MATTER_EXTRA_KEYS = {
    "preface": ("order",),
    "chapter": ("order",),
    "section": ("order", "parent", "source_pages"),
    "exam": ("year", "session", "subject"),
    "exam-variant": ("year", "session", "subject"),
}
INTEGER_FRONT_MATTER_KEYS = frozenset({"order", "year"})
EXAM_SESSIONS = {"h1", "h2"}
EXAM_SUBJECTS = {"comprehensive", "case-analysis", "essay"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

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
        ".ruff_cache",
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
        self._corpora: dict[str, object] | None = None
        self.exam_front_matter_ids: set[str] = set()

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

    def load_corpora(self) -> dict[str, object] | None:
        """Read catalog/corpora.json, the single source of truth for structure.

        Counts that used to be hardcoded here (36 exams, 20 chapters, ...) live
        in that file so content, indexes and this validator cannot drift apart.
        """
        if self._corpora is not None:
            return self._corpora
        if not CORPORA_PATH.is_file():
            self.error(CORPORA_PATH, "corpus catalog is missing")
            return None
        try:
            data = json.loads(CORPORA_PATH.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.error(CORPORA_PATH, f"invalid JSON: {exc}")
            return None
        if not isinstance(data, dict):
            self.error(CORPORA_PATH, "corpus catalog must be an object")
            return None
        self._corpora = data
        return data

    def corpus_entries(self) -> dict[str, dict[str, object]]:
        data = self.load_corpora() or {}
        entries = data.get("corpora")
        if not isinstance(entries, list):
            return {}
        return {str(entry["id"]): entry for entry in entries if isinstance(entry, dict) and "id" in entry}

    def parse_front_matter(self, path: Path) -> dict[str, str] | None:
        """Parse the flat ``key: value`` block delimited by ``---`` lines."""
        text = self.read_text(path)
        if text is None:
            return None
        lines = text.splitlines()
        if not lines or lines[0].strip() != FRONT_MATTER_FENCE:
            self.error(path, "missing front matter block")
            return None
        fields: dict[str, str] = {}
        for line_number, line in enumerate(lines[1:], start=2):
            if line.strip() == FRONT_MATTER_FENCE:
                if not fields:
                    self.error(path, "front matter block is empty")
                    return None
                return fields
            match = FRONT_MATTER_LINE_RE.match(line)
            if not match:
                self.error(path, f"front matter line {line_number} is not `key: value`: {line!r}")
                return None
            key = match.group("key")
            if key in fields:
                self.error(path, f"duplicate front matter key at line {line_number}: {key}")
                return None
            fields[key] = match.group("value").strip()
        self.error(path, "front matter block is not closed")
        return None

    @staticmethod
    def front_matter_value(raw: str) -> str | int | None:
        """Unwrap a quoted string or an unquoted integer; None if neither.

        Quotes must not appear inside the value: the parser has no escaping
        rules, so an embedded quote would silently change where the string
        ends.
        """
        if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
            inner = raw[1:-1]
            return None if '"' in inner else inner
        if re.fullmatch(r"-?\d+", raw):
            return int(raw)
        return None

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

    def extract_local_links(self, path: Path) -> set[Path]:
        """Resolved targets of every local link in a file.

        Targets resolve to absolute paths rather than bare file names: a
        two-level index links many files that are all called INDEX.md, and
        comparing names alone would let any one of them stand in for the rest.
        """
        text = self.read_text(path) or ""
        targets: set[Path] = set()
        for match in LINK_RE.finditer(text):
            target = unquote(match.group("target").strip("<>").split("#", 1)[0])
            if target and not target.startswith(("http://", "https://", "mailto:")):
                targets.add((path.parent / target).resolve())
        return targets

    def indexed_directories(self) -> list[Path]:
        """Every directory that holds knowledge-base Markdown and must index it.

        Textbook chapters are directories of section files, so the set cannot
        be a fixed tuple any more; it is derived from where the Markdown
        actually sits.
        """
        directories = {directory for directory in CONTENT_DIRS if directory.is_dir()}
        for directory in CONTENT_DIRS:
            if not directory.is_dir():
                continue
            directories.update(child for child in directory.iterdir() if child.is_dir() and any(child.glob("*.md")))
        return sorted(directories)

    def check_content_directories(self) -> None:
        for directory in CONTENT_DIRS:
            if not directory.is_dir():
                self.error(directory, "content directory is missing")

        for directory in self.indexed_directories():
            index = directory / "INDEX.md"
            if not index.is_file():
                self.error(index, "required INDEX.md is missing")
                continue
            index_text = self.read_text(index)
            if index_text is not None and len(index_text.splitlines()) > 200:
                self.error(index, "INDEX.md exceeds 200 lines")
            linked = self.extract_local_links(index)
            # A directory is indexed when the index links its Markdown files and
            # the entry document of every sub-directory hanging off it.
            expected = {path.resolve() for path in directory.glob("*.md") if path.name != "INDEX.md"}
            expected.update(
                (child / "INDEX.md").resolve()
                for child in directory.iterdir()
                if child.is_dir() and (child / "INDEX.md").is_file()
            )
            missing = sorted(self.relative(path) for path in expected - linked)
            if missing:
                self.error(index, f"unindexed Markdown files: {', '.join(missing)}")

        for directory in CHAPTER_DIRS:
            # The outline is not organised into numbered chapters: its parts are
            # the front matter, the exam overview, the three exam subjects and
            # the question-type samples.  Numbering them 第XX章 would assert a
            # chapter structure the scanned book does not have, so the outline
            # files only carry a two-digit reading-order prefix.
            if directory == OUTLINE_DIR:
                filename_re, filename_hint = r"\d{2}-.+\.md", "NN-标题.md"
            else:
                filename_re, filename_hint = r"第\d{2}章-.+\.md", "第XX章-标题.md"
            for path in directory.glob("*.md"):
                if path.name in {"INDEX.md", "前言.md"}:
                    continue
                if not re.fullmatch(filename_re, path.name):
                    self.error(path, f"chapter filename must match {filename_hint}")
            # Chapters split into sections become directories; the sections
            # inside them are numbered within the chapter.
            for child in directory.iterdir():
                if not child.is_dir():
                    continue
                if not re.fullmatch(r"第\d{2}章-.+", child.name):
                    self.error(child, "chapter directory must match 第XX章-标题")
                for path in child.glob("*.md"):
                    if path.name == "INDEX.md":
                        continue
                    if not re.fullmatch(r"第\d{2}节-.+\.md", path.name):
                        self.error(path, "section filename must match 第XX节-标题.md")

    def check_layer_layout(self) -> None:
        """The four top-level layers must exist and describe themselves.

        content/ is what the site and the retrieval index read, sources/ keeps
        the third-party originals, catalog/ holds the machine manifests and
        assets/ holds figures.  A missing entry file is how this layout silently
        degrades back into an undocumented pile of folders.
        """
        for path in LAYER_READMES:
            if not path.is_file():
                self.error(path, "layer entry document is missing")

        for directory in SOURCE_PDF_DIRS:
            if not directory.is_dir():
                self.error(directory, "source directory is missing")
                continue
            readme = directory / "README.md"
            if not readme.is_file():
                self.error(readme, "source directory must document its expected local file")

        # Scanned books are third-party material: the repository records only
        # the bibliographic facts, so the ignore rule that keeps the binaries
        # out must stay in place.
        gitignore_text = self.read_text(ROOT / ".gitignore") or ""
        if "*.pdf" not in gitignore_text.splitlines():
            self.error(ROOT / ".gitignore", "must keep the '*.pdf' rule so source scans stay out of the repository")

    def check_corpora_catalog(self) -> None:
        data = self.load_corpora()
        if data is None:
            return
        required_top = {"schema_version", "updated_at", "layers", "root_index", "corpora"}
        missing_top = required_top - set(data)
        if missing_top:
            self.error(CORPORA_PATH, f"missing top-level fields: {sorted(missing_top)}")
            return
        if data.get("schema_version") != 1:
            self.error(CORPORA_PATH, "schema_version must be 1")
        try:
            date.fromisoformat(str(data["updated_at"]))
        except ValueError:
            self.error(CORPORA_PATH, "updated_at must be an ISO date (YYYY-MM-DD)")

        layers = data.get("layers")
        if isinstance(layers, dict):
            for name, relative_path in sorted(layers.items()):
                if not (ROOT / str(relative_path)).is_dir():
                    self.error(CORPORA_PATH, f"layer '{name}' points at a missing directory: {relative_path}")
        else:
            self.error(CORPORA_PATH, "layers must be an object")

        root_index = data.get("root_index")
        if isinstance(root_index, dict):
            root_path = ROOT / str(root_index.get("path", ""))
            if root_path != CONTENT_ROOT / "INDEX.md":
                self.error(CORPORA_PATH, "root_index.path must be content/INDEX.md")
        else:
            self.error(CORPORA_PATH, "root_index must be an object")

        entries = data.get("corpora")
        if not isinstance(entries, list):
            self.error(CORPORA_PATH, "corpora must be an array")
            return
        expected_ids = {"outline", "textbook", "exams"}
        seen_ids: set[str] = set()
        data_sources_text = self.read_text(DATA_SOURCES_PATH) or ""
        for position, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                self.error(CORPORA_PATH, f"corpus #{position} is not an object")
                continue
            missing = {"id", "label", "content_root", "source_roots", "expected_documents", "source"} - set(entry)
            if missing:
                self.error(CORPORA_PATH, f"corpus #{position} missing fields: {sorted(missing)}")
                continue
            corpus_id = str(entry["id"])
            if corpus_id in seen_ids:
                self.error(CORPORA_PATH, f"duplicate corpus id: {corpus_id}")
            seen_ids.add(corpus_id)
            for relative_path in [entry["content_root"], *entry["source_roots"]]:
                if not (ROOT / str(relative_path)).is_dir():
                    self.error(CORPORA_PATH, f"{corpus_id}: directory is missing: {relative_path}")
            expected_documents = entry["expected_documents"]
            if not isinstance(expected_documents, dict) or not expected_documents:
                self.error(CORPORA_PATH, f"{corpus_id}: expected_documents must be a non-empty object")
            else:
                for kind, count in sorted(expected_documents.items()):
                    if kind not in FRONT_MATTER_KINDS:
                        self.error(CORPORA_PATH, f"{corpus_id}: unknown document kind '{kind}'")
                    if not isinstance(count, int) or count < 0:
                        self.error(
                            CORPORA_PATH, f"{corpus_id}: expected_documents['{kind}'] must be a non-negative int"
                        )
            source = entry["source"]
            if not isinstance(source, dict):
                self.error(CORPORA_PATH, f"{corpus_id}: source must be an object")
                continue
            checksum = source.get("sha256")
            if checksum is not None:
                # The same checksum is printed in DATA_SOURCES.md for humans;
                # requiring both copies keeps a re-scanned PDF from being
                # recorded in one place only.
                if not SHA256_RE.fullmatch(str(checksum)):
                    self.error(CORPORA_PATH, f"{corpus_id}: sha256 must be 64 lowercase hex characters")
                elif str(checksum) not in data_sources_text:
                    self.error(CORPORA_PATH, f"{corpus_id}: sha256 is not recorded in DATA_SOURCES.md")
            if source.get("committed") is True and corpus_id != "exams":
                self.error(CORPORA_PATH, f"{corpus_id}: scanned sources must not be marked as committed")
            if source.get("kind") == "pdf":
                self.check_local_source_pdf(corpus_id, entry, source)
        if seen_ids != expected_ids:
            self.error(CORPORA_PATH, f"corpora ids must be {sorted(expected_ids)}, found {sorted(seen_ids)}")

        exam_invariants = self.exam_invariants()
        source_documents = exam_invariants.get("source_documents")
        if isinstance(source_documents, int):
            actual = sum(
                1 for directory in EXAM_SOURCE_DIRS for path in directory.glob("*.md") if path.name != "INDEX.md"
            )
            if actual != source_documents:
                self.error(
                    CORPORA_PATH,
                    f"exams: expected {source_documents} source documents, found {actual}",
                )

    def check_local_source_pdf(
        self,
        corpus_id: str,
        entry: dict[str, object],
        source: dict[str, object],
    ) -> None:
        """Compare a locally held scan against the facts recorded for it.

        The scan itself is never committed, so CI simply finds nothing here.
        A maintainer who does hold the file gets told when it is not the one
        the repository documents, which is how page numbers and ``source_pages``
        quietly stop meaning anything.
        """
        file_name = source.get("file")
        expected_bytes = source.get("bytes")
        if not isinstance(file_name, str) or not file_name:
            self.error(CORPORA_PATH, f"{corpus_id}: pdf source must name its file")
            return
        if not isinstance(expected_bytes, int) or expected_bytes <= 0:
            self.error(CORPORA_PATH, f"{corpus_id}: pdf source must record a positive byte count")
            return
        source_roots = entry.get("source_roots")
        if not isinstance(source_roots, list) or not source_roots:
            return
        local_path = ROOT / str(source_roots[0]) / file_name
        if not local_path.is_file():
            return
        actual_bytes = local_path.stat().st_size
        if actual_bytes != expected_bytes:
            self.warn(
                local_path,
                f"local scan is {actual_bytes} bytes but catalog/corpora.json records {expected_bytes}; "
                "recompute the checksum and update catalog/corpora.json and DATA_SOURCES.md",
            )

    def exam_invariants(self) -> dict[str, object]:
        entry = self.corpus_entries().get("exams", {})
        invariants = entry.get("invariants")
        return invariants if isinstance(invariants, dict) else {}

    def check_front_matter(self) -> None:
        """Every content document carries machine-readable metadata.

        The web front end routes on ``slug`` and the retrieval index keys on
        ``id``; both must therefore exist, be well formed and stay unique, and
        the per-corpus document counts must match catalog/corpora.json.
        """
        counts: dict[tuple[str, str], int] = {}
        seen_ids: dict[str, Path] = {}
        seen_slugs: dict[tuple[str, str], Path] = {}
        section_parents: dict[str, tuple[Path, str]] = {}
        section_pages: dict[str, str] = {}
        chapter_pages: dict[str, str] = {}
        self.exam_front_matter_ids = set()
        for path in sorted(CONTENT_ROOT.rglob("*.md")):
            fields = self.parse_front_matter(path)
            if fields is None:
                continue
            missing = [key for key in REQUIRED_FRONT_MATTER if key not in fields]
            if missing:
                self.error(path, f"front matter missing keys: {missing}")
                continue
            values: dict[str, str | int] = {}
            malformed = False
            for key, raw in fields.items():
                value = self.front_matter_value(raw)
                if value is None:
                    self.error(path, f"front matter value for '{key}' must be a quoted string or an integer")
                    malformed = True
                    continue
                if key in INTEGER_FRONT_MATTER_KEYS and not isinstance(value, int):
                    self.error(path, f"front matter '{key}' must be an unquoted integer")
                    malformed = True
                    continue
                values[key] = value
            if malformed:
                continue

            corpus = str(values["corpus"])
            kind = str(values["kind"])
            document_id = str(values["id"])
            slug = str(values["slug"])
            if corpus not in FRONT_MATTER_CORPORA:
                self.error(path, f"unknown corpus '{corpus}'")
                continue
            if kind not in FRONT_MATTER_KINDS:
                self.error(path, f"unknown kind '{kind}'")
                continue
            if not SLUG_RE.fullmatch(slug):
                self.error(path, f"slug must be lowercase ASCII words joined by '-': {slug!r}")
            if not str(values["title"]).strip():
                self.error(path, "title must not be empty")
            if document_id in seen_ids:
                self.error(path, f"duplicate id '{document_id}', also used by {self.relative(seen_ids[document_id])}")
            seen_ids[document_id] = path
            if (corpus, slug) in seen_slugs:
                self.error(path, f"duplicate slug '{slug}' within corpus '{corpus}'")
            seen_slugs[(corpus, slug)] = path

            for key in FRONT_MATTER_EXTRA_KEYS.get(kind, ()):
                if key not in values:
                    self.error(path, f"kind '{kind}' requires front matter key '{key}'")
            if corpus == "textbook" and kind in {"chapter", "section"}:
                pages = values.get("source_pages")
                if pages is None:
                    self.error(path, f"textbook {kind}s must record source_pages")
                elif not SOURCE_PAGES_RE.fullmatch(str(pages)):
                    self.error(path, f"source_pages must look like '248-270': {pages!r}")
            if kind == "section":
                parent = str(values.get("parent", ""))
                section_parents[document_id] = (path, parent)
                # A section's pages must sit inside its chapter's range, which
                # is how a mis-filed section or a stale page range shows up.
                section_pages[document_id] = str(values.get("source_pages", ""))
            if kind == "chapter":
                chapter_pages[document_id] = str(values.get("source_pages", ""))
            if kind in {"exam", "exam-variant"}:
                if str(values.get("session")) not in EXAM_SESSIONS:
                    self.error(path, f"session must be one of {sorted(EXAM_SESSIONS)}")
                if str(values.get("subject")) not in EXAM_SUBJECTS:
                    self.error(path, f"subject must be one of {sorted(EXAM_SUBJECTS)}")
            if kind == "exam":
                self.exam_front_matter_ids.add(document_id)
            counts[(corpus, kind)] = counts.get((corpus, kind), 0) + 1

        for section_id, (path, parent) in sorted(section_parents.items()):
            if parent not in chapter_pages:
                self.error(path, f"parent '{parent}' is not the id of a chapter")
                continue
            if section_id != f"{parent}-s{str(section_id).rsplit('-s', 1)[-1]}":
                self.error(path, f"section id must extend its parent id: {section_id} vs {parent}")
            own = SOURCE_PAGES_RE.fullmatch(section_pages.get(section_id, ""))
            chapter = SOURCE_PAGES_RE.fullmatch(chapter_pages[parent])
            if not own or not chapter:
                continue
            first, last = (int(part) for part in own.string.split("-"))
            chapter_first, chapter_last = (int(part) for part in chapter.string.split("-"))
            if first < chapter_first or last > chapter_last:
                self.error(
                    path,
                    f"source_pages {own.string} falls outside its chapter's {chapter.string}",
                )

        for corpus_id, entry in sorted(self.corpus_entries().items()):
            expected = entry.get("expected_documents")
            if not isinstance(expected, dict):
                continue
            for kind, expected_count in sorted(expected.items()):
                actual = counts.get((corpus_id, str(kind)), 0)
                if actual != expected_count:
                    self.error(
                        CORPORA_PATH,
                        f"{corpus_id}: expected {expected_count} document(s) of kind '{kind}', found {actual}",
                    )

    def check_clean_ocr(self) -> None:
        # Every cleaned directory is scanned, not just the textbook: the outline
        # clean-up went unscanned for its whole history because this check used
        # to hardcode a single directory.
        for directory in CLEAN_DIRS:
            # rglob, not glob: textbook chapters are directories of section
            # files, and a top-level scan would skip every one of them.
            for path in sorted(directory.rglob("*.md")):
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

    def check_path_naming(self) -> None:
        """File and directory names must separate segments with '-', never '.'.

        Dots inside names make paths ambiguous for tooling that splits on the
        extension separator, so the only dot allowed in a file name is the one
        introducing its suffix.  Dot-prefixed names such as .github or
        .gitignore are fixed ecosystem conventions and are exempt.
        """
        for path in sorted(ROOT.rglob("*")):
            if not EXCLUDED_DIR_NAMES.isdisjoint(path.parts):
                continue
            name = path.name
            if name.startswith("."):
                continue
            stem = name.rsplit(".", 1)[0] if path.is_file() else name
            if "." in stem:
                kind = "File" if path.is_file() else "Directory"
                self.error(path, f"{kind} name must not contain '.'; use '-' to separate segments")

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
        invariants = self.exam_invariants()
        expected_exams = invariants.get("canonical_exams")
        expected_conflicts = invariants.get("same_name_conflicts")
        expected_source_versions = invariants.get("source_versions")
        if not all(isinstance(value, int) for value in (expected_exams, expected_conflicts, expected_source_versions)):
            self.error(CORPORA_PATH, "exams.invariants must define canonical_exams/same_name_conflicts/source_versions")
            return
        if len(exams) != expected_exams:
            self.error(MANIFEST_PATH, f"expected {expected_exams} canonical exams, found {len(exams)}")
        conflict_count = sum(bool(exam.get("same_name_conflict")) for exam in exams)
        if conflict_count != expected_conflicts:
            self.error(MANIFEST_PATH, f"expected {expected_conflicts} same-name conflicts, found {conflict_count}")
        if source_version_count != expected_source_versions:
            self.error(
                MANIFEST_PATH,
                f"expected {expected_source_versions} source_versions, found {source_version_count}",
            )
        # Front matter ids are what the site and the retrieval index address the
        # exams by, so they must be exactly the manifest's canonical ids.
        if self.exam_front_matter_ids and self.exam_front_matter_ids != ids:
            missing = sorted(ids - self.exam_front_matter_ids)
            extra = sorted(self.exam_front_matter_ids - ids)
            self.error(
                MANIFEST_PATH,
                f"front matter exam ids do not match the manifest; missing={missing}, extra={extra}",
            )

        for exam in valid_exams:
            self.check_canonical_clean_exam(exam)

        # Both indexes live inside content/, so a row links to the preferred
        # file by its path relative to that index.
        index_specs = (
            (
                MASTER_INDEX_PATH,
                {"period": 0, "subject": 1, "count": 3, "notes": 6},
            ),
            (
                CLEAN_EXAM_INDEX_PATH,
                {"period": 0, "subject": 1, "count": 4, "notes": 5},
            ),
        )
        for index_path, columns in index_specs:
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
                try:
                    target = (ROOT / preferred).relative_to(index_path.parent).as_posix()
                except ValueError:
                    self.error(
                        MANIFEST_PATH,
                        f"{exam_id}: preferred file is not reachable from {self.relative(index_path)}",
                    )
                    continue
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

        clean_relative = f"content/02-历年真题-清洗版/{year}年{session}-系统架构设计师-{subject}.md"
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
        directory = CLEAN_EXAM_DIR
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
        self.check_layer_layout()
        self.check_corpora_catalog()
        self.check_content_directories()
        self.check_front_matter()
        self.check_markdown_encoding()
        self.check_path_naming()
        self.check_clean_ocr()
        self.check_exam_manifest()
        self.check_clean_exam_counts()
        self.check_python_toolchain()

        print(
            f"Checked {len(markdown_files)} Markdown files, "
            f"{len(CONTENT_DIRS)} content directories, the corpus catalog, "
            "the exam manifest and the uv toolchain pins."
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
