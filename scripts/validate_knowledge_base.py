#!/usr/bin/env python3
"""Validate the repository's Markdown knowledge-base invariants.

This script intentionally uses only the Python standard library so the same
checks run locally and in GitHub Actions without installing dependencies.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date
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
EXAM_ASSET_AUDIT_PATH = ROOT / "data" / "exam_asset_audit.json"
TEXTBOOK_AUDIT_PATH = ROOT / "data" / "textbook_audit.json"
MASTER_INDEX_PATH = ROOT / "02.历年真题总索引.md"
CLEAN_EXAM_INDEX_PATH = ROOT / "02.历年真题-清洗版" / "INDEX.md"

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
UNTRACKED_ASSET_DEBT_RE = re.compile(
    r"待复核[：:].{0,120}(?:缺少|缺失)(?:表|图)|当前仅保留题面、选项与答案"
)
VISUAL_CUE_RE = re.compile(r"如下表|下表|见表\s*\d+|下图|见图\s*\d+|如图\s*\d+")
STRUCTURED_ASSET_CARRIERS = (
    "|---",
    "```mermaid",
    "<svg",
    "$$",
    "**图示",
    "**结构化",
    "**表格",
    "完整结构化重绘见",
)
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
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
INDEX_STAT_DATE_RE = re.compile(r"统计日期：(\d{4}-\d{2}-\d{2})")
SOURCE_VERSION_FIELDS = {
    "source_id",
    "path",
    "content_sha256",
    "verified_at",
    "item_count",
    "item_unit",
}
INTEGRITY_ALGORITHM = "sha256"
INTEGRITY_NORMALIZATION = "utf8_bom_stripped_lf"
ARCHIVE_COVERAGE = "all_90_source_versions"
REVIEW_STATUS = "source_limited_terminal_review"
EXAM_CLEAN_STATUS = "source_limited_reviewed"
COMPLETENESS_INDEX_LABELS = {
    "complete_structural": "结构齐*",
    "needs_review": "待复核",
    "partial": "部分",
}
ANSWER_CONFIDENCE_INDEX_LABELS = {
    "medium_non_official": "中·非官方",
    "low_non_official": "低·非官方",
    "very_low_non_official": "极低·非官方",
    "no_answer": "无可用答案",
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

    @staticmethod
    def normalized_lf_sha256(path: Path) -> str:
        text = path.read_bytes().decode("utf-8-sig")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

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

        required_top = {
            "schema_version",
            "updated_at",
            "integrity_policy",
            "archive_policy",
            "review_policy",
            "source_catalog",
            "exams",
        }
        missing_top = required_top - set(manifest)
        if missing_top:
            self.error(MANIFEST_PATH, f"missing top-level fields: {sorted(missing_top)}")
            return
        if manifest.get("schema_version") != 3:
            self.error(MANIFEST_PATH, "schema_version must be 3")
        try:
            date.fromisoformat(str(manifest["updated_at"]))
        except ValueError:
            self.error(MANIFEST_PATH, "updated_at must be an ISO date (YYYY-MM-DD)")
        integrity_policy = manifest.get("integrity_policy")
        if not isinstance(integrity_policy, dict):
            self.error(MANIFEST_PATH, "integrity_policy must be an object")
        else:
            if integrity_policy.get("algorithm") != INTEGRITY_ALGORITHM:
                self.error(
                    MANIFEST_PATH,
                    f"integrity_policy.algorithm must be {INTEGRITY_ALGORITHM}",
                )
            if integrity_policy.get("normalization") != INTEGRITY_NORMALIZATION:
                self.error(
                    MANIFEST_PATH,
                    f"integrity_policy.normalization must be {INTEGRITY_NORMALIZATION}",
                )
        archive_policy = manifest.get("archive_policy")
        if not isinstance(archive_policy, dict):
            self.error(MANIFEST_PATH, "archive_policy must be an object")
        else:
            archive_fields = {
                "repository_url",
                "snapshot_commit",
                "snapshot_verified_at",
                "blob_url_template",
                "coverage",
                "description",
            }
            missing_archive = archive_fields - set(archive_policy)
            if missing_archive:
                self.error(
                    MANIFEST_PATH,
                    f"archive_policy missing fields: {sorted(missing_archive)}",
                )
            repository_url = archive_policy.get("repository_url")
            if not isinstance(repository_url, str) or not repository_url.startswith(
                "https://github.com/"
            ):
                self.error(
                    MANIFEST_PATH,
                    "archive_policy.repository_url must be an HTTPS GitHub repository URL",
                )
            snapshot_commit = archive_policy.get("snapshot_commit")
            if not isinstance(snapshot_commit, str) or not GIT_COMMIT_RE.fullmatch(
                snapshot_commit
            ):
                self.error(
                    MANIFEST_PATH,
                    "archive_policy.snapshot_commit must be a 40-character lowercase Git commit",
                )
            try:
                date.fromisoformat(str(archive_policy.get("snapshot_verified_at")))
            except ValueError:
                self.error(
                    MANIFEST_PATH,
                    "archive_policy.snapshot_verified_at must be an ISO date",
                )
            blob_template = archive_policy.get("blob_url_template")
            if (
                not isinstance(blob_template, str)
                or "{commit}" not in blob_template
                or "{path}" not in blob_template
            ):
                self.error(
                    MANIFEST_PATH,
                    "archive_policy.blob_url_template must contain {commit} and {path}",
                )
            if archive_policy.get("coverage") != ARCHIVE_COVERAGE:
                self.error(
                    MANIFEST_PATH,
                    f"archive_policy.coverage must be {ARCHIVE_COVERAGE}",
                )
        review_policy = manifest.get("review_policy")
        if not isinstance(review_policy, dict):
            self.error(MANIFEST_PATH, "review_policy must be an object")
        else:
            review_fields = {
                "status",
                "reviewed_at",
                "canonical_exam_count",
                "conflict_disposition",
                "outcome_summary",
                "scope",
                "excludes",
                "description",
            }
            missing_review = review_fields - set(review_policy)
            if missing_review:
                self.error(
                    MANIFEST_PATH,
                    f"review_policy missing fields: {sorted(missing_review)}",
                )
            if review_policy.get("status") != REVIEW_STATUS:
                self.error(
                    MANIFEST_PATH,
                    f"review_policy.status must be {REVIEW_STATUS}",
                )
            try:
                date.fromisoformat(str(review_policy.get("reviewed_at")))
            except ValueError:
                self.error(MANIFEST_PATH, "review_policy.reviewed_at must be an ISO date")
            for field in ("scope", "excludes"):
                value = review_policy.get(field)
                if not isinstance(value, list) or not value or not all(
                    isinstance(item, str) and item.strip() for item in value
                ):
                    self.error(
                        MANIFEST_PATH,
                        f"review_policy.{field} must be a non-empty text array",
                    )
            conflict_disposition = review_policy.get("conflict_disposition")
            if not isinstance(conflict_disposition, dict):
                self.error(
                    MANIFEST_PATH,
                    "review_policy.conflict_disposition must be an object",
                )
            elif conflict_disposition.get("status") != (
                "retained_separate_source_limited"
            ):
                self.error(
                    MANIFEST_PATH,
                    "review_policy.conflict_disposition has an unsupported status",
                )
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
            "completeness",
            "completeness_note",
            "answer_confidence",
            "clean_status",
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
            valid_exams.append(exam)
            exam_id = str(exam["id"])
            if exam.get("clean_status") != EXAM_CLEAN_STATUS:
                self.error(
                    MANIFEST_PATH,
                    f"{exam_id}: clean_status must be {EXAM_CLEAN_STATUS}",
                )
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
                if not isinstance(catalog_entry, dict) or not isinstance(
                    catalog_entry.get("root"), str
                ):
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

                recorded_hash = version["content_sha256"]
                if not isinstance(recorded_hash, str) or not SHA256_RE.fullmatch(
                    recorded_hash
                ):
                    self.error(MANIFEST_PATH, f"{label} content_sha256 is invalid")
                else:
                    try:
                        actual_hash = self.normalized_lf_sha256(candidate)
                    except UnicodeDecodeError as exc:
                        self.error(
                            MANIFEST_PATH,
                            f"{label} cannot be normalized as UTF-8 ({exc})",
                        )
                    else:
                        if recorded_hash != actual_hash:
                            self.error(
                                MANIFEST_PATH,
                                f"{label} content_sha256 mismatch for {relative_path}",
                            )

                verified_at = version["verified_at"]
                try:
                    date.fromisoformat(str(verified_at))
                except ValueError:
                    self.error(
                        MANIFEST_PATH,
                        f"{label} verified_at must be an ISO date (YYYY-MM-DD)",
                    )

            expected_version_paths = {
                relative_path
                for relative_path in [exam["preferred"], *alternatives]
                if isinstance(relative_path, str)
            }
            if exam_version_paths != expected_version_paths:
                missing_versions = sorted(expected_version_paths - exam_version_paths)
                extra_versions = sorted(exam_version_paths - expected_version_paths)
                self.error(
                    MANIFEST_PATH,
                    f"{exam_id}: source_versions path mismatch; "
                    f"missing={missing_versions}, extra={extra_versions}",
                )

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
        if isinstance(review_policy, dict) and review_policy.get(
            "canonical_exam_count"
        ) != len(exams):
            self.error(
                MANIFEST_PATH,
                "review_policy.canonical_exam_count must match the exams array",
            )
        conflict_count = sum(bool(exam.get("same_name_conflict")) for exam in exams)
        if isinstance(review_policy, dict):
            conflict_disposition = review_policy.get("conflict_disposition")
            if isinstance(conflict_disposition, dict) and conflict_disposition.get(
                "same_name_conflict_count"
            ) != conflict_count:
                self.error(
                    MANIFEST_PATH,
                    "review_policy conflict count must match same_name_conflict flags",
                )
        if conflict_count != 17:
            self.error(MANIFEST_PATH, f"expected 17 same-name conflicts, found {conflict_count}")
        if isinstance(review_policy, dict):
            outcome_summary = review_policy.get("outcome_summary")
            expected_outcomes = {
                "complete_structural": sum(
                    exam.get("completeness") == "complete_structural" for exam in exams
                ),
                "needs_review": sum(
                    exam.get("completeness") == "needs_review" for exam in exams
                ),
                "partial": sum(exam.get("completeness") == "partial" for exam in exams),
                "medium_non_official_answers": sum(
                    exam.get("answer_confidence") == "medium_non_official"
                    for exam in exams
                ),
                "low_non_official_answers": sum(
                    exam.get("answer_confidence") == "low_non_official"
                    for exam in exams
                ),
                "official_or_high_confidence_answers": 0,
            }
            if not isinstance(outcome_summary, dict):
                self.error(MANIFEST_PATH, "review_policy.outcome_summary must be an object")
            else:
                for field, expected in expected_outcomes.items():
                    if outcome_summary.get(field) != expected:
                        self.error(
                            MANIFEST_PATH,
                            f"review_policy.outcome_summary.{field} must be {expected}",
                        )
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
                {"period": 0, "subject": 1, "count": 3, "completeness": 4,
                 "answer": 5, "notes": 9},
            ),
            (
                CLEAN_EXAM_INDEX_PATH,
                lambda preferred: Path(preferred).name,
                {"period": 0, "subject": 1, "count": 4, "completeness": 5,
                 "answer": 6, "notes": 7},
            ),
        )
        for index_path, target_for, columns in index_specs:
            if not index_path.is_file():
                self.error(index_path, "exam index is missing")
                continue
            index_text = self.read_text(index_path) or ""
            stat_date = INDEX_STAT_DATE_RE.search(index_text[:500])
            if stat_date is None:
                self.error(index_path, "missing statistics date in index header")
            elif stat_date.group(1) != str(manifest.get("updated_at")):
                self.error(
                    index_path,
                    "statistics date does not match manifest updated_at",
                )
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
                    "completeness": COMPLETENESS_INDEX_LABELS.get(
                        str(exam.get("completeness")), ""
                    ),
                    "answer": ANSWER_CONFIDENCE_INDEX_LABELS.get(
                        str(exam.get("answer_confidence")), ""
                    ),
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
        if exam.get("clean_status") not in {
            "cleaned",
            "cleaned_needs_review",
            EXAM_CLEAN_STATUS,
        }:
            self.error(
                MANIFEST_PATH,
                f"{exam_id}: clean_status must identify a completed clean draft",
            )

        text = self.read_text(clean_path) or ""
        stale_match = STALE_EXAM_METADATA_RE.search(text)
        if stale_match:
            line_number = text.count("\n", 0, stale_match.start()) + 1
            self.error(
                clean_path,
                f"stale manifest/index correction note at line {line_number}",
            )
        if exam.get("completeness_note") != exam.get("notes"):
            self.error(
                MANIFEST_PATH,
                f"{exam_id}: completeness_note and notes must stay synchronized",
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
            unresolved_match = UNTRACKED_ASSET_DEBT_RE.search(text)
            if unresolved_match:
                self.error(
                    path,
                    "contains an untracked unresolved asset phrase: "
                    + unresolved_match.group(0),
                )
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
            for index, question_match in enumerate(question_matches):
                end = (
                    question_matches[index + 1].start()
                    if index + 1 < len(question_matches)
                    else len(text)
                )
                block = text[question_match.start() : end]
                cue = VISUAL_CUE_RE.search(block)
                if cue and not any(carrier in block for carrier in STRUCTURED_ASSET_CARRIERS):
                    self.error(
                        path,
                        f"question {question_match.group(1)} cites {cue.group(0)!r} without a structured carrier",
                    )
            options = len(OPTION_RE.findall(text))
            if options != declared * 4:
                self.error(
                    path,
                    f"expected {declared * 4} A-D options, found {options}",
                )

    def check_exam_asset_audit(self) -> None:
        if not EXAM_ASSET_AUDIT_PATH.is_file():
            self.error(EXAM_ASSET_AUDIT_PATH, "exam asset audit is missing")
            return
        try:
            audit = json.loads(EXAM_ASSET_AUDIT_PATH.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.error(EXAM_ASSET_AUDIT_PATH, f"invalid JSON: {exc}")
            return
        required = {
            "schema_version",
            "reviewed_at",
            "field_definitions",
            "baseline",
            "additional_positions",
            "summary",
            "files",
            "positions",
            "source_limited_visual_items",
            "source_search_refresh",
            "non_original_substitutes",
        }
        missing = required - set(audit)
        if missing:
            self.error(
                EXAM_ASSET_AUDIT_PATH,
                f"missing top-level fields: {sorted(missing)}",
            )
            return
        if audit.get("schema_version") != 2:
            self.error(EXAM_ASSET_AUDIT_PATH, "schema_version must be 2")
        try:
            date.fromisoformat(str(audit.get("reviewed_at")))
        except ValueError:
            self.error(EXAM_ASSET_AUDIT_PATH, "reviewed_at must be an ISO date")
        baseline = audit.get("baseline")
        if not isinstance(baseline, dict):
            self.error(EXAM_ASSET_AUDIT_PATH, "baseline must be an object")
            return
        commit = baseline.get("commit")
        if not isinstance(commit, str) or not GIT_COMMIT_RE.fullmatch(commit):
            self.error(EXAM_ASSET_AUDIT_PATH, "baseline.commit must be a Git commit")
        if baseline.get("explicit_positions") != 116:
            self.error(EXAM_ASSET_AUDIT_PATH, "baseline must record 116 positions")
        files = audit.get("files")
        if not isinstance(files, list):
            self.error(EXAM_ASSET_AUDIT_PATH, "files must be an array")
            return
        seen_paths: set[str] = set()
        expected_counts_by_path: dict[str, int] = {}
        baseline_total = 0
        current_marker_total = 0
        for position, item in enumerate(files, start=1):
            label = f"files #{position}"
            if not isinstance(item, dict):
                self.error(EXAM_ASSET_AUDIT_PATH, f"{label} must be an object")
                continue
            relative_path = item.get("path")
            count = item.get("baseline_positions")
            if not isinstance(relative_path, str) or not relative_path:
                self.error(EXAM_ASSET_AUDIT_PATH, f"{label}.path must be text")
                continue
            if relative_path in seen_paths:
                self.error(EXAM_ASSET_AUDIT_PATH, f"duplicate path: {relative_path}")
            seen_paths.add(relative_path)
            if not isinstance(count, int) or count <= 0:
                self.error(
                    EXAM_ASSET_AUDIT_PATH,
                    f"{label}.baseline_positions must be positive",
                )
                continue
            baseline_total += count
            expected_counts_by_path[relative_path] = count
            path = ROOT / relative_path
            if not path.is_file():
                self.error(EXAM_ASSET_AUDIT_PATH, f"missing audited file {relative_path}")
                continue
            text = self.read_text(path) or ""
            current_marker_total += text.count("原图未收录") + text.count("原表未收录")
        if len(files) != 22:
            self.error(EXAM_ASSET_AUDIT_PATH, f"expected 22 files, found {len(files)}")
        if baseline_total != 116:
            self.error(
                EXAM_ASSET_AUDIT_PATH,
                f"baseline position counts sum to {baseline_total}, expected 116",
            )
        positions = audit.get("positions")
        position_dispositions: Counter[str] = Counter()
        position_path_counts: Counter[str] = Counter()
        baseline_record_count = 0
        additional_record_count = 0
        seen_position_ids: set[str] = set()
        if not isinstance(positions, list):
            self.error(EXAM_ASSET_AUDIT_PATH, "positions must be an array")
            positions = []
        elif len(positions) != 120:
            self.error(
                EXAM_ASSET_AUDIT_PATH,
                f"expected 120 item-level positions, found {len(positions)}",
            )
        position_fields = {
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
        allowed_dispositions = {
            "reviewed_current_carrier",
            "recovered_structural",
            "source_limited",
            "non_original_substitute",
        }
        for position, item in enumerate(positions, start=1):
            label = f"positions #{position}"
            if not isinstance(item, dict):
                self.error(EXAM_ASSET_AUDIT_PATH, f"{label} must be an object")
                continue
            missing_fields = position_fields - set(item)
            if missing_fields:
                self.error(
                    EXAM_ASSET_AUDIT_PATH,
                    f"{label} missing fields: {sorted(missing_fields)}",
                )
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                self.error(EXAM_ASSET_AUDIT_PATH, f"{label}.id must be text")
            elif item_id in seen_position_ids:
                self.error(EXAM_ASSET_AUDIT_PATH, f"duplicate position id: {item_id}")
            else:
                seen_position_ids.add(item_id)
            relative_path = item.get("path")
            if not isinstance(relative_path, str) or not (ROOT / relative_path).is_file():
                self.error(EXAM_ASSET_AUDIT_PATH, f"{label}.path is invalid")
            disposition = item.get("disposition")
            if disposition not in allowed_dispositions:
                self.error(
                    EXAM_ASSET_AUDIT_PATH,
                    f"{label}.disposition is invalid: {disposition!r}",
                )
            else:
                position_dispositions[str(disposition)] += 1
            for field in ("nearest_question", "nearest_heading", "context", "proof_scope"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    self.error(EXAM_ASSET_AUDIT_PATH, f"{label}.{field} must be text")
            origin = item.get("origin")
            if origin == "baseline_marker":
                baseline_record_count += 1
                if isinstance(relative_path, str) and relative_path in seen_paths:
                    position_path_counts[relative_path] += 1
                else:
                    self.error(
                        EXAM_ASSET_AUDIT_PATH,
                        f"{label}.path is not in the fixed baseline file list",
                    )
                if not isinstance(item.get("baseline_line"), int) or item["baseline_line"] <= 0:
                    self.error(
                        EXAM_ASSET_AUDIT_PATH,
                        f"{label}.baseline_line must be positive",
                    )
                if item.get("marker") not in {"原图未收录", "原表未收录"}:
                    self.error(EXAM_ASSET_AUDIT_PATH, f"{label}.marker is invalid")
            elif origin == "additional_review":
                additional_record_count += 1
                if item.get("baseline_line") is not None or item.get("marker") is not None:
                    self.error(
                        EXAM_ASSET_AUDIT_PATH,
                        f"{label} additional record must have null baseline fields",
                    )
            else:
                self.error(EXAM_ASSET_AUDIT_PATH, f"{label}.origin is invalid")
        if baseline_record_count != 116:
            self.error(
                EXAM_ASSET_AUDIT_PATH,
                f"expected 116 baseline position records, found {baseline_record_count}",
            )
        if additional_record_count != 4:
            self.error(
                EXAM_ASSET_AUDIT_PATH,
                f"expected four additional position records, found {additional_record_count}",
            )
        for relative_path, expected_count in expected_counts_by_path.items():
            actual_count = position_path_counts.get(relative_path, 0)
            if actual_count != expected_count:
                self.error(
                    EXAM_ASSET_AUDIT_PATH,
                    f"{relative_path}: positions has {actual_count}, expected {expected_count}",
                )
        additional = audit.get("additional_positions")
        if not isinstance(additional, list) or len(additional) != 4:
            self.error(EXAM_ASSET_AUDIT_PATH, "expected four additional positions")
            additional = []
        limited = audit.get("source_limited_visual_items")
        if not isinstance(limited, list) or len(limited) != 6:
            self.error(
                EXAM_ASSET_AUDIT_PATH,
                "expected six source-limited visual items",
            )
            limited = []
        search_refresh = audit.get("source_search_refresh")
        if (
            not isinstance(search_refresh, dict)
            or search_refresh.get("reviewed_at") != audit.get("reviewed_at")
            or search_refresh.get("tool") != "GitHub CLI 2.96.0 code search"
            or not isinstance(search_refresh.get("queries"), list)
            or len(search_refresh.get("queries", [])) != 7
            or search_refresh.get("indexed_code_results") != 0
            or not isinstance(search_refresh.get("proof_scope"), str)
            or not search_refresh.get("proof_scope")
        ):
            self.error(
                EXAM_ASSET_AUDIT_PATH,
                "source_search_refresh must record the dated GitHub CLI search boundary",
            )
        for group_name, group in (
            ("additional_positions", additional),
            ("source_limited_visual_items", limited),
        ):
            for position, item in enumerate(group, start=1):
                if not isinstance(item, dict):
                    self.error(
                        EXAM_ASSET_AUDIT_PATH,
                        f"{group_name} #{position} must be an object",
                    )
                    continue
                relative_path = item.get("path")
                if not isinstance(relative_path, str) or not (ROOT / relative_path).is_file():
                    self.error(
                        EXAM_ASSET_AUDIT_PATH,
                        f"{group_name} #{position} has an invalid path",
                    )
                item_id = item.get("id")
                if not isinstance(item_id, str) or not item_id:
                    self.error(
                        EXAM_ASSET_AUDIT_PATH,
                        f"{group_name} #{position}.id must be text",
                    )
                if group_name == "additional_positions":
                    if item_id not in seen_position_ids:
                        self.error(
                            EXAM_ASSET_AUDIT_PATH,
                            f"{group_name} #{position} is absent from positions[]",
                        )
                else:
                    if (
                        item.get("baseline_position_id") is not None
                        or item.get("baseline_mapping")
                        != "no_matching_legacy_marker_in_fixed_baseline"
                    ):
                        self.error(
                            EXAM_ASSET_AUDIT_PATH,
                            f"{group_name} #{position} must not claim a false baseline mapping",
                        )
                    if item.get("disposition") != "source_limited":
                        self.error(
                            EXAM_ASSET_AUDIT_PATH,
                            f"{group_name} #{position}.disposition must be source_limited",
                        )
        substitutes = audit.get("non_original_substitutes")
        if not isinstance(substitutes, list) or len(substitutes) != 1:
            self.error(EXAM_ASSET_AUDIT_PATH, "expected one non-original substitute")
        else:
            substitute = substitutes[0]
            if (
                not isinstance(substitute, dict)
                or substitute.get("disposition") != "non_original_substitute"
                or substitute.get("baseline_position_id") not in seen_position_ids
            ):
                self.error(
                    EXAM_ASSET_AUDIT_PATH,
                    "non-original substitute must map to its item-level position",
                )
        summary = audit.get("summary")
        if not isinstance(summary, dict):
            self.error(EXAM_ASSET_AUDIT_PATH, "summary must be an object")
        else:
            expected_summary = {
                "total_positions_reviewed": baseline_total + len(additional),
                "baseline_positions": baseline_total,
                "additional_positions": len(additional),
                "files_with_baseline_positions": len(files),
                "current_legacy_marker_count": current_marker_total,
                "source_limited_visual_items": len(limited),
            }
            for field, expected in expected_summary.items():
                if summary.get(field) != expected:
                    self.error(
                        EXAM_ASSET_AUDIT_PATH,
                        f"summary.{field} must be {expected}",
                    )
            disposition_summary = summary.get("positions_by_disposition")
            expected_dispositions = {
                name: position_dispositions.get(name, 0)
                for name in (
                    "reviewed_current_carrier",
                    "recovered_structural",
                    "source_limited",
                    "non_original_substitute",
                )
            }
            if disposition_summary != expected_dispositions:
                self.error(
                    EXAM_ASSET_AUDIT_PATH,
                    "summary.positions_by_disposition does not match positions[]",
                )
        if current_marker_total != 0:
            self.error(
                EXAM_ASSET_AUDIT_PATH,
                f"audited files still contain {current_marker_total} legacy marker(s)",
            )

    def check_textbook_audit(self) -> None:
        if not TEXTBOOK_AUDIT_PATH.is_file():
            self.error(TEXTBOOK_AUDIT_PATH, "textbook PDF audit is missing")
            return
        try:
            audit = json.loads(TEXTBOOK_AUDIT_PATH.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.error(TEXTBOOK_AUDIT_PATH, f"invalid JSON: {exc}")
            return
        if not isinstance(audit, dict):
            self.error(TEXTBOOK_AUDIT_PATH, "top-level JSON value must be an object")
            return
        required = {
            "schema_version",
            "reviewed_at",
            "field_definitions",
            "source",
            "method",
            "manual_review",
            "baseline_evidence",
            "asset_inventory",
            "additional_unmarked_figures",
            "additional_unmarked_formulas",
            "formula_status_items",
            "historical_spliced_tables",
            "key_content_debt",
            "debt_scope",
            "summary",
            "page_records",
            "chapters",
        }
        missing = required - set(audit)
        if missing:
            self.error(
                TEXTBOOK_AUDIT_PATH,
                f"missing top-level fields: {sorted(missing)}",
            )
            return
        if audit.get("schema_version") != 4:
            self.error(TEXTBOOK_AUDIT_PATH, "schema_version must be 4")
        try:
            date.fromisoformat(str(audit.get("reviewed_at")))
        except ValueError:
            self.error(TEXTBOOK_AUDIT_PATH, "reviewed_at must be an ISO date")
        source = audit.get("source")
        expected_source = {
            "sha256": "ee45900f4622d71539980cfe1bddbcd898fba97ca13ada6df1cbdc215135c2f8",
            "pages": 721,
            "chapter_content_pages": 708,
        }
        if not isinstance(source, dict):
            self.error(TEXTBOOK_AUDIT_PATH, "source must be an object")
        else:
            for field, expected in expected_source.items():
                if source.get(field) != expected:
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"source.{field} must be {expected}",
                    )
        manual_review = audit.get("manual_review")
        declared_manual_pages: set[int] = set()
        manual_reason_pages: dict[str, set[int]] = {}
        if not isinstance(manual_review, dict):
            self.error(TEXTBOOK_AUDIT_PATH, "manual_review must be an object")
        else:
            if manual_review.get("status") != "full_scope_completed":
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "full-page PDF/render review must be completed",
                )
            explicit_pages = manual_review.get("explicit_physical_pages")
            if (
                not isinstance(explicit_pages, list)
                or explicit_pages != list(range(13, 721))
            ):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "manual_review.explicit_physical_pages must cover physical pages 13-720",
                )
            else:
                declared_manual_pages = set(explicit_pages)
            expected_manual_scalars = {
                "explicit_page_count": 708,
                "chapter_content_pages": 708,
                "outside_declared_manual_scope_pages": 0,
            }
            for field, expected in expected_manual_scalars.items():
                if manual_review.get(field) != expected:
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"manual_review.{field} must be {expected}",
                    )
            components = manual_review.get("scope_components")
            if not isinstance(components, dict):
                self.error(TEXTBOOK_AUDIT_PATH, "manual_review.scope_components is invalid")
            else:
                expected_component_counts = {
                    "low_ngram_coverage_pages": 20,
                    "additional_unmarked_figure_pages": 11,
                    "additional_unmarked_formula_pages": 6,
                    "full_chapter_8_or_10_pages": 73,
                    "full_page_visual_text_review_pages": 708,
                }
                component_reasons = {
                    "low_ngram_coverage_pages": "low_ngram_coverage",
                    "additional_unmarked_figure_pages": "additional_unmarked_figure",
                    "additional_unmarked_formula_pages": "additional_unmarked_formula",
                    "full_chapter_8_or_10_pages": "full_chapter_8_or_10",
                    "full_page_visual_text_review_pages": "full_page_visual_text_review",
                }
                component_union: set[int] = set()
                for field, expected_count in expected_component_counts.items():
                    values = components.get(field)
                    if (
                        not isinstance(values, list)
                        or len(values) != expected_count
                        or not all(type(page) is int for page in values)
                        or values != sorted(set(values))
                    ):
                        self.error(
                            TEXTBOOK_AUDIT_PATH,
                            f"manual_review.scope_components.{field} is invalid",
                        )
                    elif any(not 13 <= page <= 720 for page in values):
                        self.error(
                            TEXTBOOK_AUDIT_PATH,
                            f"manual_review.scope_components.{field} has invalid physical pages",
                        )
                    else:
                        component_union.update(values)
                        manual_reason_pages[component_reasons[field]] = set(values)
                if components.get("additional_unmarked_formula_pages") != [
                    61, 70, 113, 162, 170, 171
                ]:
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        "manual_review.scope_components.additional_unmarked_formula_pages is invalid",
                    )
                if components.get("full_page_visual_text_review_pages") != list(
                    range(13, 721)
                ):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        "manual_review.scope_components.full_page_visual_text_review_pages must cover 13-720",
                    )
                if declared_manual_pages and component_union != declared_manual_pages:
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        "manual review component pages do not match explicit page union",
                    )
            expected_review_phases = [
                {
                    "phase": "prior_detailed",
                    "chapters": [8, 10],
                    "physical_page_ranges": [[281, 314], [340, 378]],
                    "page_count": 73,
                    "generated_contact_sheet_count": 9,
                    "contact_sheets_used_for_review": 0,
                    "review_origin": "prior_detailed_review",
                    "review_basis": (
                        "既有逐页渲染与详细目视复核；本轮生成的9张联系表"
                        "不作为完成声明依据"
                    ),
                    "status": "completed",
                },
                {
                    "phase": "A",
                    "chapters": [1, 2, 3, 4, 5, 6],
                    "physical_page_ranges": [[13, 257]],
                    "page_count": 245,
                    "generated_contact_sheet_count": 30,
                    "contact_sheets_used_for_review": 30,
                    "review_origin": "additional_full_review",
                    "status": "completed",
                },
                {
                    "phase": "B",
                    "chapters": [7, 9, 11, 12, 13],
                    "physical_page_ranges": [
                        [258, 280],
                        [315, 339],
                        [379, 489],
                    ],
                    "page_count": 159,
                    "generated_contact_sheet_count": 20,
                    "contact_sheets_used_for_review": 20,
                    "review_origin": "additional_full_review",
                    "status": "completed",
                },
                {
                    "phase": "C",
                    "chapters": [14, 15, 16, 17, 18],
                    "physical_page_ranges": [[490, 683]],
                    "page_count": 194,
                    "generated_contact_sheet_count": 24,
                    "contact_sheets_used_for_review": 24,
                    "review_origin": "additional_full_review",
                    "status": "completed",
                },
                {
                    "phase": "D",
                    "chapters": [19, 20],
                    "physical_page_ranges": [[684, 720]],
                    "page_count": 37,
                    "generated_contact_sheet_count": 5,
                    "contact_sheets_used_for_review": 5,
                    "review_origin": "additional_full_review",
                    "status": "completed",
                },
            ]
            if manual_review.get("review_phases") != expected_review_phases:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "manual_review.review_phases must preserve the real non-contiguous review batches",
                )
            expected_render_review = {
                "generated_contact_sheet_count": 88,
                "prior_phase_generated_contact_sheet_count": 9,
                "contact_sheets_used_for_current_full_review": 79,
                "prior_detailed_page_count": 73,
                "additional_full_review_page_count": 635,
                "combined_review_page_count": 708,
                "contact_sheet_grid": "3x3",
                "maximum_pages_per_contact_sheet": 9,
                "inspection_detail": "original",
                "single_page_escalation": (
                    "低覆盖、复杂图表、疑似截断、错页或异常空白页单独放大复核"
                ),
                "temporary_artifact_root": "tmp/pdfs/textbook_full_review",
                "artifacts_committed": False,
            }
            if manual_review.get("render_review") != expected_render_review:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "manual_review.render_review must record 79 current/88 generated contact sheets",
                )
        debt_scope = audit.get("debt_scope")
        expected_debt = {
            "original_minimum": 296,
            "corrected_minimum": 314,
            "legacy_marked_figure_positions": 272,
            "additional_unmarked_figure_positions": 12,
            "known_formula_positions": 7,
            "explicit_missing_or_partial_table_positions": 8,
            "reported_spliced_table_positions": 14,
            "conservatively_reconstructed_spliced_table_positions": 15,
            "itemized_proven_positions": 314,
            "historical_unitemized_positions": 0,
            "key_content_historical_minimum": 198,
            "key_content_historical_conservative_positions": 199,
            "key_content_current_conservative_positions": 208,
        }
        if not isinstance(debt_scope, dict):
            self.error(TEXTBOOK_AUDIT_PATH, "debt_scope must be an object")
        else:
            for field, expected in expected_debt.items():
                if debt_scope.get(field) != expected:
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"debt_scope.{field} must be {expected}",
                    )
        summary = audit.get("summary")
        expected_summary = {
            "chapters": 20,
            "baseline_explicit_marker_records": 280,
            "itemized_proven_positions": 314,
            "historical_unitemized_positions": 0,
            "key_content_historical_minimum": 198,
            "key_content_historical_conservative_positions": 199,
            "key_content_current_conservative_positions": 208,
            "page_records": 708,
            "declared_manual_review_pages": 708,
            "conservatively_reconstructed_spliced_table_positions": 15,
            "pdf_unique_figure_numbers": 284,
            "markdown_unique_figure_carriers": 284,
            "missing_figure_carriers": [],
            "pdf_unique_table_numbers": 59,
            "markdown_unique_table_titles": 59,
            "missing_table_titles": [],
            "table_structure_risks": [],
        }
        if not isinstance(summary, dict):
            self.error(TEXTBOOK_AUDIT_PATH, "summary must be an object")
        else:
            for field, expected in expected_summary.items():
                if summary.get(field) != expected:
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"summary.{field} must be {expected}",
                    )

        baseline_evidence = audit.get("baseline_evidence")
        baseline_ids: set[str] = set()
        baseline_kind_counts: Counter[str] = Counter()
        baseline_impact_counts: Counter[str] = Counter()
        critical_figure_id_order: list[str] = []
        explicit_table_id_order: list[str] = []
        if not isinstance(baseline_evidence, dict):
            self.error(TEXTBOOK_AUDIT_PATH, "baseline_evidence must be an object")
        else:
            baseline_commit = baseline_evidence.get("commit")
            if not isinstance(baseline_commit, str) or not GIT_COMMIT_RE.fullmatch(
                baseline_commit
            ):
                self.error(TEXTBOOK_AUDIT_PATH, "baseline_evidence.commit is invalid")
            counts = baseline_evidence.get("counts")
            expected_counts = {
                "figure_markers": 272,
                "table_issue_positions": 8,
                "total_records": 280,
            }
            if counts != expected_counts:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    f"baseline_evidence.counts must be {expected_counts}",
                )
            records = baseline_evidence.get("records")
            if not isinstance(records, list) or len(records) != 280:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "baseline_evidence.records must contain 280 items",
                )
                records = []
            for position, record in enumerate(records, start=1):
                label = f"baseline_evidence.records #{position}"
                if not isinstance(record, dict):
                    self.error(TEXTBOOK_AUDIT_PATH, f"{label} must be an object")
                    continue
                record_id = record.get("id")
                if not isinstance(record_id, str) or not record_id:
                    self.error(TEXTBOOK_AUDIT_PATH, f"{label}.id must be text")
                elif record_id in baseline_ids:
                    self.error(TEXTBOOK_AUDIT_PATH, f"duplicate baseline id {record_id}")
                else:
                    baseline_ids.add(record_id)
                kind = record.get("kind")
                if kind not in {"figure", "table"}:
                    self.error(TEXTBOOK_AUDIT_PATH, f"{label}.kind is invalid")
                else:
                    baseline_kind_counts[str(kind)] += 1
                content_impact = record.get("content_impact")
                if content_impact not in {
                    "critical_content_incomplete",
                    "graphic_detail_only",
                }:
                    self.error(TEXTBOOK_AUDIT_PATH, f"{label}.content_impact is invalid")
                elif kind == "table" and content_impact != "critical_content_incomplete":
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"{label} table must be critical_content_incomplete",
                    )
                else:
                    baseline_impact_counts[str(content_impact)] += 1
                    if (
                        kind == "figure"
                        and content_impact == "critical_content_incomplete"
                        and isinstance(record_id, str)
                    ):
                        critical_figure_id_order.append(record_id)
                    if kind == "table" and isinstance(record_id, str):
                        explicit_table_id_order.append(record_id)
                relative_path = record.get("path")
                if not isinstance(relative_path, str) or not (ROOT / relative_path).is_file():
                    self.error(TEXTBOOK_AUDIT_PATH, f"{label}.path is invalid")
                if not isinstance(record.get("baseline_line"), int) or record["baseline_line"] <= 0:
                    self.error(TEXTBOOK_AUDIT_PATH, f"{label}.baseline_line is invalid")
                if not isinstance(record.get("nearest_asset_number"), str):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"{label}.nearest_asset_number must be text",
                    )
                carrier_lines = record.get("current_markdown_carrier_lines")
                if not isinstance(carrier_lines, list) or not carrier_lines or not all(
                    isinstance(line, int) and line > 0 for line in carrier_lines
                ):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"{label} must have current carrier lines",
                    )
                if record.get("current_status") not in {
                    "current_carrier_present",
                    "current_structured_carrier_present",
                }:
                    self.error(TEXTBOOK_AUDIT_PATH, f"{label}.current_status is invalid")
            if baseline_kind_counts != Counter({"figure": 272, "table": 8}):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "baseline record kinds must total 272 figures and 8 tables",
                )
            if baseline_impact_counts != Counter(
                {"critical_content_incomplete": 182, "graphic_detail_only": 98}
            ):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "baseline impacts must total 174 critical figures, 8 critical tables and 98 detail-only figures",
                )

        inventory = audit.get("asset_inventory")
        inventory_numbers: dict[str, set[str]] = {"figures": set(), "tables": set()}
        if not isinstance(inventory, dict):
            self.error(TEXTBOOK_AUDIT_PATH, "asset_inventory must be an object")
        else:
            for group_name, expected_count, expected_status in (
                ("figures", 284, "current_carrier_present"),
                ("tables", 59, "current_structured_carrier_present"),
            ):
                group = inventory.get(group_name)
                if not isinstance(group, list) or len(group) != expected_count:
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"asset_inventory.{group_name} must contain {expected_count} items",
                    )
                    continue
                for position, item in enumerate(group, start=1):
                    label = f"asset_inventory.{group_name} #{position}"
                    if not isinstance(item, dict):
                        self.error(TEXTBOOK_AUDIT_PATH, f"{label} must be an object")
                        continue
                    number = item.get("number")
                    if not isinstance(number, str) or not re.fullmatch(r"\d{1,2}-\d{1,2}", number):
                        self.error(TEXTBOOK_AUDIT_PATH, f"{label}.number is invalid")
                    elif number in inventory_numbers[group_name]:
                        self.error(
                            TEXTBOOK_AUDIT_PATH,
                            f"duplicate {group_name} number {number}",
                        )
                    else:
                        inventory_numbers[group_name].add(number)
                    relative_path = item.get("path")
                    if not isinstance(relative_path, str) or not (ROOT / relative_path).is_file():
                        self.error(TEXTBOOK_AUDIT_PATH, f"{label}.path is invalid")
                    for field in ("pdf_reference_pages", "markdown_carrier_lines"):
                        values = item.get(field)
                        if not isinstance(values, list) or not values or not all(
                            isinstance(value, int) and value > 0 for value in values
                        ):
                            self.error(
                                TEXTBOOK_AUDIT_PATH,
                                f"{label}.{field} must contain positive integers",
                            )
                    if item.get("status") != expected_status:
                        self.error(TEXTBOOK_AUDIT_PATH, f"{label}.status is invalid")
                    marker_ids = item.get("baseline_marker_ids")
                    if not isinstance(marker_ids, list) or any(
                        marker_id not in baseline_ids for marker_id in marker_ids
                    ):
                        self.error(
                            TEXTBOOK_AUDIT_PATH,
                            f"{label}.baseline_marker_ids is invalid",
                        )

        additional_figures = audit.get("additional_unmarked_figures")
        expected_additional_numbers = [
            "2-4",
            "2-25",
            "2-26",
            "3-1",
            "3-12",
            "4-8",
            "17-15",
            "17-17",
            "17-19",
            "19-12",
            "19-13",
            "19-14",
        ]
        additional_critical_ids: list[str] = []
        additional_detail_ids: list[str] = []
        if not isinstance(additional_figures, list) or len(additional_figures) != 12:
            self.error(
                TEXTBOOK_AUDIT_PATH,
                "additional_unmarked_figures must contain 12 items",
            )
        else:
            numbers = [
                item.get("number") if isinstance(item, dict) else None
                for item in additional_figures
            ]
            if numbers != expected_additional_numbers:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "additional_unmarked_figures has unexpected numbers or order",
                )
            if any(
                not isinstance(item, dict) or item.get("baseline_marker_ids") != []
                for item in additional_figures
            ):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "additional unmarked figures must not claim baseline marker IDs",
                )
            for position, item in enumerate(additional_figures, start=1):
                if not isinstance(item, dict):
                    continue
                item_id = item.get("id")
                impact = item.get("content_impact")
                policy_class = item.get("policy_class")
                if (
                    not isinstance(item_id, str)
                    or not item_id
                    or impact
                    not in {"critical_content_incomplete", "graphic_detail_only"}
                    or policy_class not in {"A", "B"}
                    or (impact == "critical_content_incomplete") != (policy_class == "A")
                    or not isinstance(item.get("classification_basis"), str)
                    or not item.get("classification_basis")
                ):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"additional_unmarked_figures #{position} has invalid A/B classification",
                    )
                    continue
                if impact == "critical_content_incomplete":
                    additional_critical_ids.append(item_id)
                else:
                    additional_detail_ids.append(item_id)
            if (len(additional_critical_ids), len(additional_detail_ids)) != (4, 8):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "additional unmarked figures must classify as 4 critical and 8 detail-only",
                )

        additional_formula_items = audit.get("additional_unmarked_formulas")
        expected_additional_formulas = (
            {
                "id": "textbook-ch02-full-review-p0061-formula-reliability-range",
                "topic": "reliability_range",
                "path": "01.系统架构设计师教材-清洗版/第02章-计算机系统基础知识.md",
                "pdf_reference_pages": [61],
                "printed_pages": [51],
            },
            {
                "id": "textbook-ch02-full-review-p0070-formula-shannon-capacity",
                "topic": "shannon_capacity",
                "path": "01.系统架构设计师教材-清洗版/第02章-计算机系统基础知识.md",
                "pdf_reference_pages": [70],
                "printed_pages": [60],
            },
            {
                "id": "textbook-ch02-full-review-p0113-formula-amdahl-speedup",
                "topic": "amdahl_speedup",
                "path": "01.系统架构设计师教材-清洗版/第02章-计算机系统基础知识.md",
                "pdf_reference_pages": [113],
                "printed_pages": [103],
            },
            {
                "id": "textbook-ch04-full-review-p0162-formula-rsa-exponents",
                "topic": "rsa_exponents",
                "path": "01.系统架构设计师教材-清洗版/第04章-信息安全技术基础知识.md",
                "pdf_reference_pages": [162],
                "printed_pages": [152],
            },
            {
                "id": "textbook-ch04-full-review-p0170-formula-keyspace-primality",
                "topic": "keyspace_primality",
                "path": "01.系统架构设计师教材-清洗版/第04章-信息安全技术基础知识.md",
                "pdf_reference_pages": [170, 171],
                "printed_pages": [160, 161],
            },
        )
        additional_formula_ids: list[str] = []
        if (
            not isinstance(additional_formula_items, list)
            or len(additional_formula_items) != len(expected_additional_formulas)
        ):
            self.error(
                TEXTBOOK_AUDIT_PATH,
                "additional_unmarked_formulas must contain the five full-review formula items",
            )
        else:
            for position, (item, expected) in enumerate(
                zip(additional_formula_items, expected_additional_formulas, strict=True),
                start=1,
            ):
                label = f"additional_unmarked_formulas #{position}"
                if not isinstance(item, dict):
                    self.error(TEXTBOOK_AUDIT_PATH, f"{label} must be an object")
                    continue
                for field in (
                    "id",
                    "topic",
                    "path",
                    "pdf_reference_pages",
                    "printed_pages",
                ):
                    if item.get(field) != expected[field]:
                        self.error(
                            TEXTBOOK_AUDIT_PATH,
                            f"{label}.{field} must be {expected[field]!r}",
                        )
                if (
                    item.get("discovery_origin") != "full_page_visual_text_review"
                    or item.get("status") != "current_formula_carrier_present"
                    or item.get("content_impact") != "critical_content_incomplete"
                ):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"{label} review/status metadata is invalid",
                    )
                for field in ("label", "nearest_heading", "proof_scope"):
                    if not isinstance(item.get(field), str) or not item[field].strip():
                        self.error(
                            TEXTBOOK_AUDIT_PATH,
                            f"{label}.{field} must be a non-empty string",
                        )
                if (
                    type(item.get("nearest_heading_line")) is not int
                    or item["nearest_heading_line"] <= 0
                ):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"{label}.nearest_heading_line must be a positive integer",
                    )
                carrier_lines = item.get("markdown_carrier_lines")
                if (
                    not isinstance(carrier_lines, list)
                    or not carrier_lines
                    or not all(
                        type(line) is int and line > 0 for line in carrier_lines
                    )
                    or carrier_lines != sorted(set(carrier_lines))
                ):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"{label}.markdown_carrier_lines must contain unique positive integers",
                    )
                baseline_needles = item.get("baseline_needles")
                if (
                    not isinstance(baseline_needles, list)
                    or not baseline_needles
                    or not all(
                        isinstance(needle, str) and needle.strip()
                        for needle in baseline_needles
                    )
                ):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"{label}.baseline_needles must contain non-empty strings",
                    )
                baseline_lines = item.get("baseline_markdown_lines")
                if (
                    not isinstance(baseline_lines, list)
                    or not baseline_lines
                    or not all(
                        type(line) is int and line > 0 for line in baseline_lines
                    )
                    or baseline_lines != sorted(set(baseline_lines))
                ):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"{label}.baseline_markdown_lines must contain unique positive integers",
                    )
                baseline_context = item.get("baseline_context")
                if (
                    not isinstance(baseline_context, str)
                    or not baseline_context.strip()
                ):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"{label}.baseline_context must be a non-empty string",
                    )
                if position == 1:
                    supporting_evidence = item.get("supporting_evidence")
                    expected_supporting_evidence = {
                        "repository": "FreeSky-X/systemarchitect",
                        "commit": "0e9b17f3fbd1590ecc0e5f664c2031068e52b9d0",
                        "path": "files/unit2/2.4.3嵌入式软件的组成及特点.md",
                        "git_blob": "de5c8cf984f8f5844cc7b37af5edc84c0a4e7b1b",
                        "fixed_excerpt": "10-6O10-9",
                        "purpose": "本地 PDF 上标不可辨时的固定第三方 OCR 补证",
                    }
                    if not isinstance(supporting_evidence, dict):
                        self.error(
                            TEXTBOOK_AUDIT_PATH,
                            f"{label}.supporting_evidence must be an object",
                        )
                    else:
                        for field, expected_value in expected_supporting_evidence.items():
                            if supporting_evidence.get(field) != expected_value:
                                self.error(
                                    TEXTBOOK_AUDIT_PATH,
                                    f"{label}.supporting_evidence.{field} "
                                    f"must be {expected_value!r}",
                                )
                item_id = item.get("id")
                if isinstance(item_id, str) and item_id:
                    additional_formula_ids.append(item_id)
            if len(additional_formula_ids) != len(set(additional_formula_ids)):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "additional_unmarked_formulas IDs must be unique",
                )

        formula_items = audit.get("formula_status_items")
        historical_formula_ids: set[str] = set()
        historical_formula_id_order: list[str] = []
        if not isinstance(formula_items, list) or len(formula_items) != 2:
            self.error(TEXTBOOK_AUDIT_PATH, "formula_status_items must contain 2 items")
        else:
            topics = [
                item.get("topic") if isinstance(item, dict) else None
                for item in formula_items
            ]
            if topics != ["natural_join", "random_walk"]:
                self.error(TEXTBOOK_AUDIT_PATH, "formula_status_items topics are invalid")
            for position, item in enumerate(formula_items, start=1):
                if not isinstance(item, dict) or item.get("status") != "current_formula_carrier_present":
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"formula_status_items #{position} has invalid status",
                    )
                elif not isinstance(item.get("id"), str) or not item["id"]:
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"formula_status_items #{position}.id is invalid",
                    )
                else:
                    formula_id = str(item["id"])
                    historical_formula_ids.add(formula_id)
                    historical_formula_id_order.append(formula_id)
        expected_historical_formula_id_order = [
            "textbook-ch06-baseline-l0321-formula-natural_join",
            "textbook-ch08-baseline-l0345-formula-random_walk",
        ]
        if historical_formula_id_order != expected_historical_formula_id_order:
            self.error(
                TEXTBOOK_AUDIT_PATH,
                "formula_status_items must preserve the two historical formula IDs in order",
            )
        if (
            len(set(additional_formula_ids) | historical_formula_ids) != 7
            or set(additional_formula_ids) & historical_formula_ids
        ):
            self.error(
                TEXTBOOK_AUDIT_PATH,
                "historical and additional formula inventories must form seven unique items",
            )

        spliced = audit.get("historical_spliced_tables")
        spliced_candidate_id_order: list[str] = []
        if not isinstance(spliced, dict):
            self.error(TEXTBOOK_AUDIT_PATH, "historical_spliced_tables must be an object")
        else:
            if (
                spliced.get("reported_positions") != 14
                or spliced.get("mapping_status")
                != "conservative_reconstruction_covers_reported_minimum"
                or spliced.get("ids_not_preserved") is not True
                or spliced.get("commit_diff_contains_14_item_manifest") is not False
                or spliced.get("conservatively_reconstructed_positions") != 15
                or spliced.get("reported_minimum_covered") is not True
            ):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "historical spliced-table reconstruction metadata is invalid",
                )
            candidates = spliced.get("reconstructed_candidates")
            expected_candidate_numbers = [
                "2-2",
                "2-4",
                "2-5",
                "2-6",
                "2-7",
                "3-1",
                "4-1",
                "4-2",
                "4-3",
                "5-1",
                "5-2",
                "12-13",
                "17-1",
                "18-2",
                "19-1",
            ]
            if not isinstance(candidates, list) or len(candidates) != 15:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "historical spliced-table reconstruction must contain 15 candidates",
                )
            else:
                candidate_numbers: list[str] = []
                candidate_ids: list[str] = []
                for position, item in enumerate(candidates, start=1):
                    if not isinstance(item, dict):
                        self.error(
                            TEXTBOOK_AUDIT_PATH,
                            f"reconstructed spliced-table candidate #{position} must be an object",
                        )
                        continue
                    number = item.get("number")
                    item_id = item.get("id")
                    if isinstance(number, str):
                        candidate_numbers.append(number)
                    if isinstance(item_id, str):
                        candidate_ids.append(item_id)
                    if (
                        not isinstance(item_id, str)
                        or not item_id
                        or not isinstance(number, str)
                        or not number
                        or not isinstance(item.get("path"), str)
                        or not item.get("path")
                        or not isinstance(item.get("baseline_title_line"), int)
                        or not isinstance(item.get("baseline_flattened_lines"), list)
                        or len(item.get("baseline_flattened_lines", [])) != 2
                        or not isinstance(item.get("pdf_reference_pages"), list)
                        or not item.get("pdf_reference_pages")
                        or not isinstance(item.get("current_markdown_carrier_lines"), list)
                        or not item.get("current_markdown_carrier_lines")
                        or item.get("status") != "recovered_structural"
                        or not isinstance(item.get("proof_scope"), str)
                        or not item.get("proof_scope")
                    ):
                        self.error(
                            TEXTBOOK_AUDIT_PATH,
                            f"reconstructed spliced-table candidate #{position} is incomplete",
                        )
                if candidate_numbers != expected_candidate_numbers:
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        "reconstructed spliced-table candidate numbers are invalid",
                    )
                if len(candidate_ids) != len(set(candidate_ids)):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        "reconstructed spliced-table candidate IDs must be unique",
                    )
                spliced_candidate_id_order = candidate_ids
                explicit_shifted = spliced.get(
                    "baseline_explicit_shifted_table_numbers_in_separate_8_item_category"
                )
                if not isinstance(explicit_shifted, list) or set(candidate_numbers).intersection(
                    str(value) for value in explicit_shifted
                ):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        "reconstructed spliced tables overlap the separate baseline table category",
                    )
            current_evidence = spliced.get("current_state_evidence")
            if not isinstance(current_evidence, dict) or current_evidence != {
                "official_pdf_table_inventory": 59,
                "markdown_table_carriers": 59,
                "table_structure_risks": [],
            }:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "historical_spliced_tables.current_state_evidence is invalid",
                )

        key_content = audit.get("key_content_debt")
        if not isinstance(key_content, dict):
            self.error(TEXTBOOK_AUDIT_PATH, "key_content_debt must be an object")
        else:
            if key_content.get("historical_reported_content_minimum") != 198:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "key_content_debt.historical_reported_content_minimum must be 198",
                )
            if (
                key_content.get("derivation_status")
                != "conservative_reconstruction_from_baseline_markers"
                or key_content.get("historical_item_ids_preserved") is not False
                or key_content.get("baseline_content_incomplete_figures") != 174
                or key_content.get("baseline_graphic_detail_only_figures") != 98
            ):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "key_content_debt derivation metadata is invalid",
                )
            if (
                key_content.get("historical_conservative_reconstructed_positions")
                != 199
                or key_content.get("current_conservative_reconstructed_positions")
                != 208
            ):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "key_content_debt must record 199 historical and 208 current conservative positions",
                )
            additional_classification = key_content.get(
                "additional_unmarked_figures_content_classification"
            )
            if not isinstance(additional_classification, dict) or {
                "status": additional_classification.get("status"),
                "positions": additional_classification.get("positions"),
                "critical_content_incomplete": additional_classification.get(
                    "critical_content_incomplete"
                ),
                "graphic_detail_only": additional_classification.get(
                    "graphic_detail_only"
                ),
            } != {
                "status": "completed",
                "positions": 12,
                "critical_content_incomplete": 4,
                "graphic_detail_only": 8,
            }:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "key_content_debt additional figure classification is invalid",
                )
            expected_key_groups = (
                (
                    "critical_figure_position_ids",
                    critical_figure_id_order,
                    174,
                ),
                ("formula_position_ids", historical_formula_id_order, 2),
                ("explicit_table_position_ids", explicit_table_id_order, 8),
                (
                    "conservative_spliced_table_position_ids",
                    spliced_candidate_id_order,
                    15,
                ),
            )
            ordered_key_ids: list[str] = []
            for field, expected_id_order, expected_count in expected_key_groups:
                values = key_content.get(field)
                if (
                    not isinstance(values, list)
                    or len(values) != expected_count
                    or not all(isinstance(value, str) and value for value in values)
                    or len(values) != len(set(values))
                    or values != expected_id_order
                ):
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"key_content_debt.{field} must contain the {expected_count} referenced IDs in canonical order",
                    )
                ordered_key_ids.extend(expected_id_order)
            key_additional_critical = key_content.get(
                "additional_critical_figure_position_ids"
            )
            key_additional_detail = key_content.get(
                "additional_detail_only_figure_position_ids"
            )
            key_additional_formulas = key_content.get(
                "additional_formula_position_ids"
            )
            if key_additional_critical != additional_critical_ids:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "key_content_debt.additional_critical_figure_position_ids is invalid",
                )
                key_additional_critical = []
            if key_additional_detail != additional_detail_ids:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "key_content_debt.additional_detail_only_figure_position_ids is invalid",
                )
            if key_additional_formulas != additional_formula_ids:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "key_content_debt.additional_formula_position_ids is invalid",
                )
                key_additional_formulas = []
            historical_position_ids = key_content.get("historical_position_ids")
            if (
                not isinstance(historical_position_ids, list)
                or len(historical_position_ids) != 199
                or not all(
                    isinstance(item_id, str) and item_id
                    for item_id in historical_position_ids
                )
                or len(historical_position_ids) != len(set(historical_position_ids))
                or historical_position_ids != ordered_key_ids
            ):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "key_content_debt.historical_position_ids must be the ordered 199-item union",
                )
            current_position_ids = key_content.get("current_position_ids")
            expected_current_ids = [
                *ordered_key_ids,
                *key_additional_critical,
                *key_additional_formulas,
            ]
            if (
                not isinstance(current_position_ids, list)
                or len(current_position_ids) != 208
                or not all(
                    isinstance(item_id, str) and item_id
                    for item_id in current_position_ids
                )
                or len(current_position_ids) != len(set(current_position_ids))
                or current_position_ids != expected_current_ids
            ):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    "key_content_debt.current_position_ids must be the ordered 208-item union",
                )

        page_records = audit.get("page_records")
        page_numbers: list[int] = []
        manual_page_statuses: Counter[str] = Counter()
        if not isinstance(page_records, list) or len(page_records) != 708:
            self.error(TEXTBOOK_AUDIT_PATH, "page_records must contain 708 items")
            page_records = []
        for position, item in enumerate(page_records, start=1):
            label = f"page_records #{position}"
            if not isinstance(item, dict):
                self.error(TEXTBOOK_AUDIT_PATH, f"{label} must be an object")
                continue
            physical_page = item.get("physical_page")
            if not isinstance(physical_page, int):
                self.error(TEXTBOOK_AUDIT_PATH, f"{label}.physical_page is invalid")
                continue
            page_numbers.append(physical_page)
            if not isinstance(item.get("chapter"), int) or not 1 <= item["chapter"] <= 20:
                self.error(TEXTBOOK_AUDIT_PATH, f"{label}.chapter is invalid")
            relative_path = item.get("path")
            if not isinstance(relative_path, str) or not (ROOT / relative_path).is_file():
                self.error(TEXTBOOK_AUDIT_PATH, f"{label}.path is invalid")
            if not isinstance(item.get("normalized_pdf_chars"), int) or item["normalized_pdf_chars"] < 0:
                self.error(TEXTBOOK_AUDIT_PATH, f"{label}.normalized_pdf_chars is invalid")
            coverage = item.get("ngram_coverage")
            if not isinstance(coverage, (int, float)) or not 0 <= coverage <= 1:
                self.error(TEXTBOOK_AUDIT_PATH, f"{label}.ngram_coverage is invalid")
            if item.get("ngram_width") != 10:
                self.error(TEXTBOOK_AUDIT_PATH, f"{label}.ngram_width must be 10")
            reasons = item.get("declared_manual_review_reasons")
            allowed_reasons = {
                "low_ngram_coverage",
                "additional_unmarked_figure",
                "additional_unmarked_formula",
                "full_chapter_8_or_10",
                "full_page_visual_text_review",
            }
            if (
                not isinstance(reasons, list)
                or not all(isinstance(reason, str) for reason in reasons)
                or len(reasons) != len(set(reasons))
                or any(reason not in allowed_reasons for reason in reasons)
            ):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    f"{label}.declared_manual_review_reasons is invalid",
                )
                reasons = []
            status = item.get("declared_manual_review_status")
            if status != "completed":
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    f"{label}.declared_manual_review_status must be completed",
                )
            else:
                manual_page_statuses[str(status)] += 1
            if physical_page not in declared_manual_pages:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    f"{label} is not included in the declared full-page review scope",
                )
            if "full_page_visual_text_review" not in reasons:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    f"{label} must record full_page_visual_text_review",
                )
            expected_reasons = [
                reason
                for reason, pages in manual_reason_pages.items()
                if physical_page in pages
            ]
            if reasons != expected_reasons:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    f"{label}.declared_manual_review_reasons do not match scope components in canonical order",
                )
        if page_numbers != list(range(13, 721)):
            self.error(TEXTBOOK_AUDIT_PATH, "page_records must cover physical pages 13-720")
        if manual_page_statuses != Counter({"completed": 708}):
            self.error(
                TEXTBOOK_AUDIT_PATH,
                "page record manual statuses must total 708 completed and 0 outside scope",
            )

        chapters = audit.get("chapters")
        if not isinstance(chapters, list) or len(chapters) != 20:
            self.error(TEXTBOOK_AUDIT_PATH, "chapters must contain 20 entries")
            return
        chapter_numbers: list[int] = []
        page_ranges: list[tuple[int, int]] = []
        for position, chapter in enumerate(chapters, start=1):
            if not isinstance(chapter, dict):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    f"chapters #{position} must be an object",
                )
                continue
            number = chapter.get("chapter")
            if isinstance(number, int):
                chapter_numbers.append(number)
            relative_path = chapter.get("path")
            if not isinstance(relative_path, str) or not (ROOT / relative_path).is_file():
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    f"chapters #{position} has an invalid path",
                )
            pages = chapter.get("physical_pages")
            if isinstance(pages, dict):
                start, end = pages.get("start"), pages.get("end")
                if isinstance(start, int) and isinstance(end, int):
                    page_ranges.append((start, end))
                else:
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"chapters #{position} has invalid page bounds",
                    )
                    continue
                if pages.get("count") != end - start + 1:
                    self.error(
                        TEXTBOOK_AUDIT_PATH,
                        f"chapters #{position} has inconsistent page count",
                    )
            else:
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    f"chapters #{position}.physical_pages must be an object",
                )
            assets = chapter.get("assets")
            if not isinstance(assets, dict):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    f"chapters #{position}.assets must be an object",
                )
            elif (
                assets.get("missing_figure_carriers")
                or assets.get("missing_table_titles")
                or assets.get("table_structure_risks")
            ):
                self.error(
                    TEXTBOOK_AUDIT_PATH,
                    f"chapters #{position} still has missing asset carriers",
                )
        if chapter_numbers != list(range(1, 21)):
            self.error(TEXTBOOK_AUDIT_PATH, "chapter numbers must be continuous 1-20")
        if page_ranges and (
            page_ranges[0][0] != 13
            or page_ranges[-1][1] != 720
            or any(
                current[1] + 1 != following[0]
                for current, following in zip(page_ranges, page_ranges[1:])
            )
        ):
            self.error(TEXTBOOK_AUDIT_PATH, "chapter physical page ranges must cover 13-720")

    def run(self) -> int:
        markdown_files = self.markdown_files()
        for path in markdown_files:
            self.check_markdown_file(path)
        self.check_content_directories()
        self.check_clean_ocr()
        self.check_exam_manifest()
        self.check_clean_exam_counts()
        self.check_exam_asset_audit()
        self.check_textbook_audit()

        print(
            f"Checked {len(markdown_files)} Markdown files, "
            f"{len(CONTENT_DIRS)} content directories, the exam manifest "
            "and the exam/textbook asset audits."
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
