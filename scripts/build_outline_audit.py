#!/usr/bin/env python3
"""Build the deterministic outline (考试大纲) verification audit.

The outline was the only content directory without a content-level ledger: no
source hash, no page anchoring, no clean-vs-raw comparison.  This script builds
that ledger.

Two things make the outline different from the textbook and the exams:

* Its source scan has **no text layer at all** (75 image-only pages produced by
  a phone scanner), so the sliding n-gram coverage used by
  ``audit_textbook_pdf.py`` is impossible.  Verification is therefore
  page-by-page *visual* reading, and the per-page verdicts are recorded here as
  reviewed evidence rather than recomputed from the PDF.
* The source PDF is not in the repository, so this script must stay runnable
  without it.  Only the recorded hash and page count tie the ledger to the
  scan; anyone holding the same file can re-derive them.

Everything this script emits is derived either from the working tree (file
hashes, line counts, marker counts) or from the reviewed-findings tables below,
so ``--check`` gives byte-for-byte reproducibility in CI.  The script writes
governance metadata only; it never edits outline Markdown.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "outline_audit.json"
CLEAN_DIR = "00.系统架构设计师考试大纲-清洗版"
RAW_DIR = "00.系统架构设计师考试大纲"
REVIEWED_AT = "2026-08-25"

# The source scan is held locally by the maintainer and deliberately not
# committed (CONTENT_POLICY.md, DATA_SOURCES.md).  Recording the hash lets a
# holder of the same file confirm they are looking at the same evidence.
SOURCE = {
    "title": "系统架构设计师考试大纲",
    "editor": "全国计算机专业技术资格考试办公室 编",
    "publisher": "清华大学出版社",
    "published": "2022.11（2023.01 重印）",
    "edition": "2022 年 11 月第 1 版，2023 年 1 月第 2 次印刷",
    "isbn": "978-7-302-62003-7",
    "cip": "(2022)第 187029 号",
    "approval": "2022 年审定通过",
    "path_hint": "PDF文档资料/00、[官方]系统架构设计师考试大纲.pdf",
    "sha256": "0fb39827f11b636847f4969a49732134fd984eddbba09cb8ecc9bfa727986a3b",
    "pdf_pages": 75,
    "text_layer": "absent",
    "scanner_creator": "vFlat",
    "committed": False,
}

METHOD = {
    "clean_vs_raw": "按归一化文本比较清洗版与原始整理稿，定位结构与条目差异。",
    "source_verification": "逐页视觉阅读图像扫描件（无文本层，无法做 n-gram 覆盖率），与清洗版逐条对照。",
    "external_verification": "以 urllib 抓取主管机构公开页面，记录整页 SHA-256 与被引用段落摘录 SHA-256。",
    "integrity_normalization": "utf8_bom_stripped_lf",
    "limitation": (
        "源扫描件不入库，故本账本不能仅凭版本库复现视觉核对过程；"
        "逐页结论以 reviewed_pages 中记录的印刷页号与核查人结论为准。"
    ),
}

# PDF image page -> printed page.  The scan contains duplicate captures
# (printed page 1 was photographed six times), so no arithmetic mapping is
# valid; the observed mapping is recorded explicitly.
PAGE_MAP = {
    1: "封面",
    2: "扉页",
    3: "版权页/内容简介",
    4: "I",
    5: "II",
    6: "1",
    7: "1（重复扫描）",
    8: "1（重复扫描）",
    9: "1（重复扫描）",
    10: "1（重复扫描）",
    11: "1（重复扫描）",
    12: "2",
    13: "3",
    14: "4",
    15: "5",
    16: "II（重复扫描）",
    17: "3（重复扫描）",
    18: "8",
    19: "9",
    20: "10",
    21: "11",
    22: "12",
    23: "13",
    24: "14",
    25: "15",
}

DUPLICATE_PAGES = [7, 8, 9, 10, 11, 16, 17]

# Pages read visually this round, with the outline section each one carries.
REVIEWED_PAGES = [
    (3, "版权页/内容简介", "前言.md", "书目信息与内容简介逐字核对一致"),
    (4, "I", "前言.md", "前言第 1—4 段，原缺失，本轮补录"),
    (5, "II", "前言.md", "前言第 5 段与落款“编者 2022 年 9 月”，原缺失，本轮补录"),
    (6, "1", "第02章-相关文件.md", "国人部发〔2003〕39 号文件头与通知首段，一致"),
    (12, "2", "第02章-相关文件.md", "通知末段、废止条款与两部落款，一致"),
    (13, "3", "第02章-相关文件.md", "暂行规定第一条至第五条，一致"),
    (14, "4", "第02章-相关文件.md", "暂行规定第五条续至第十条，一致"),
    (15, "5", "第02章-相关文件.md", "暂行规定第十一条至第十六条，一致"),
    (20, "10", "第02章-相关文件.md", "附表：二维表被压平、6 项资格缺失、文号误作国人部发"),
    (21, "11", "第02章-相关文件.md", "主题词/抄送/印发块，原缺失，本轮补录"),
    (22, "12", "第02章-相关文件.md", "软考办〔2005〕1 号文件头与首段，抬头与过渡句原缺失"),
    (23, "13", "第02章-相关文件.md", "中日互认表 5 行及“二”至“五”四项，原缺 2 行、1 值错、4 项缺失"),
    (24, "14", "第02章-相关文件.md", "软考办〔2006〕2 号文件头、首段与中韩互认表 2 行，表值一致"),
    (25, "15", "第02章-相关文件.md", "中韩“二”至“五”四项与落款，四项原缺失"),
]

EXTERNAL_SOURCES = [
    {
        "id": "ruankao-qualification-roster",
        "url": "https://www.ruankao.org.cn/introduction/main.html",
        "title": "中国计算机技术职业资格网 · 考试介绍 / 资格设置",
        "fetched_at": REVIEWED_AT,
        "full_page_sha256": "1a180193073f6145b3bf96afde813530eb04b4934582577efdbf7daed7eaf9a4",
        "excerpt_chars": 267,
        "excerpt_sha256": "b94a7a10e73e5d65f506986a4d76e186aee7ca0b28adae2de20d68198b009fb1",
        "used_for": ["outline-ch02-annex-table"],
        "agreement": "confirms",
        "conclusion": "现行资格设置为 5 个专业领域、3 个级别层次、27 项资格，27 项名称与原书附表完全一致。",
        "proof_scope": ("整页哈希会随网站改版漂移；摘录哈希只锁定被引用的资格清单文本，不证明该页其余内容或原书版式。"),
    },
    {
        "id": "miit-abolition-2019",
        "url": "https://www.ruankao.org.cn/article/content/2506051147209075632471954.html",
        "title": "工业和信息化部办公厅关于废止部分文件的通知（工信厅人〔2019〕50 号）",
        "fetched_at": REVIEWED_AT,
        "full_page_sha256": None,
        "excerpt_chars": None,
        "excerpt_sha256": None,
        "used_for": ["outline-ch02-registration-currency"],
        "agreement": "pending",
        "conclusion": (
            "该通知废止了证书登记（信办人〔2004〕47 号）与继续教育系列文件，"
            "与暂行规定第十二条、第十三条的登记制度相关；时效性注尚未撰写，本项待办。"
        ),
        "proof_scope": "已确认页面可达并读取正文；哈希与逐条时效性结论留待续审固化，本轮不声称已完成。",
    },
]

# Reviewed findings.  Hardcoded here (matching build_exam_asset_audit.py's
# convention) so the emitted ledger stays reproducible under --check.
FINDINGS = [
    {
        "id": "outline-preface-missing",
        "chapter": "前言",
        "path": f"{CLEAN_DIR}/前言.md",
        "unit_type": "prose",
        "source_pages": ["版权页", "I", "II"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "原书内容简介与前言（印刷页 I—II）在清洗版和原始整理稿中均完全缺失。",
        "detail": (
            "前言载明 5 个专业领域、3 个级别层次和 27 个专业技术资格，是校核第02章附表条目是否完整的直接依据；"
            "缺失使该校核线索一并丢失。本轮据印刷页 I—II 补录，并保留原书两处不同表述"
            "（前言作“计算机应用”，附表作“计算机应用技术”）。"
        ),
        "proof_scope": "证明补录内容来自所记印刷页；不证明其余章节已完成同等核对。",
    },
    {
        "id": "outline-ch02-annex-table",
        "chapter": "第02章",
        "path": f"{CLEAN_DIR}/第02章-相关文件.md",
        "unit_type": "table",
        "source_pages": ["10"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "附表由“专业类别 × 级别层次”二维表被压平为三个一维列表，专业类别维度整体丢失，并漏 6 项资格。",
        "detail": (
            "原表 5 个专业类别（计算机软件、计算机网络、计算机应用技术、信息系统、信息服务）"
            "× 3 个级别层次，共 27 项资格，“高级资格”行跨 5 个类别合并。"
            "清洗版与原始整理稿均只按级别列出 5+11+5=21 项：中级漏计算机辅助设计师、电子商务设计师、"
            "信息安全工程师、信息系统管理工程师；初级漏多媒体应用制作技术员、信息系统运行管理员。"
            "本轮恢复为二维 Markdown 表并补回 6 项，与前言“27 个专业技术资格”及官网现行清单双向校核一致。"
        ),
        "proof_scope": "证明表格结构与 27 项条目已按印刷页 10 恢复；结构化重绘不复刻原表斜线分区与版式。",
    },
    {
        "id": "outline-ch02-annex-docnumber",
        "chapter": "第02章",
        "path": f"{CLEAN_DIR}/第02章-相关文件.md",
        "unit_type": "citation",
        "source_pages": ["10"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "附表标题文号误作“国人部发[2007] 139 号”，原书为“国人厅发〔2007〕139 号”。",
        "detail": "发文机关字号由“国人部发”误作与主文件相同的字号；原书用六角括号。已按印刷页 10 更正并统一括号。",
        "proof_scope": "仅证明文号已与原书一致；不单独判定该文件现行效力。",
    },
    {
        "id": "outline-ch02-japan-table",
        "chapter": "第02章",
        "path": f"{CLEAN_DIR}/第02章-相关文件.md",
        "unit_type": "table",
        "source_pages": ["13"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "中日互认表原仅 3 行（应为 5 行），且“软件设计师”对应值错误。",
        "detail": (
            "原书表为 5 行：系统分析师｜系统分析师·项目经理·应用系统开发师；软件设计师｜软件开发师；"
            "网络工程师｜网络系统工程师；数据库系统工程师｜数据库系统工程师；程序员｜基本信息技术师。"
            "清洗版将“软件设计师”对应值写作“高级系统管理员”（原书为“软件开发师”），"
            "并缺“数据库系统工程师”“程序员”两行。缺失的数据库系统工程师与本节正文"
            "“增加了网络工程师和数据库系统工程师的互认”自相矛盾——该矛盾可在无外部来源时独立发现。"
        ),
        "proof_scope": "证明 5 行表值已按印刷页 13 恢复；不证明互认协议现行有效。",
    },
    {
        "id": "outline-ch02-mutual-recognition-body",
        "chapter": "第02章",
        "path": f"{CLEAN_DIR}/第02章-相关文件.md",
        "unit_type": "prose",
        "source_pages": ["12", "13", "14", "15"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "软考办〔2005〕1 号与〔2006〕2 号的“二”至“五”共八项政策正文、抬头与过渡句均未转录。",
        "detail": (
            "两份文件各含“一”至“五”五项，清洗版只保留“一”的表格与落款，"
            "丢失抬头“各地计算机软件考试实施管理机构：”、过渡句及“二”至“五”四项内容，两份共八项。"
            "表头列内副标题“（考试大纲）”“（技能标准）”亦丢失。本轮据印刷页 12—15 全部补录。"
        ),
        "proof_scope": "证明八项正文已按所记印刷页补录；不证明其现行效力。",
    },
    {
        "id": "outline-ch02-issuance-block",
        "chapter": "第02章",
        "path": f"{CLEAN_DIR}/第02章-相关文件.md",
        "unit_type": "prose",
        "source_pages": ["11"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "国人部发〔2003〕39 号的主题词/抄送/印发结尾块（印刷页 11）整块缺失。",
        "detail": "该块是公文标准结尾，含主题词、抄送范围与“人事部办公厅 2003 年 10 月 27 日印发”。本轮补录。",
        "proof_scope": "证明结尾块已按印刷页 11 补录。",
    },
    {
        "id": "outline-encoding-uniformity",
        "chapter": "全目录",
        "path": CLEAN_DIR,
        "unit_type": "encoding",
        "source_pages": [],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "清洗版 6 个文件带 UTF-8 BOM，与仓库其余 154 个 Markdown 文件不一致。",
        "detail": (
            "BOM 会被部分跨平台工具链误读为正文首字符，也使 `^# ` 之类的行首匹配失效。"
            "本轮将全仓 Markdown 统一为标准 UTF-8（无 BOM）+ CRLF；"
            "因 data/exams.json 的完整性口径为 utf8_bom_stripped_lf，去 BOM 不影响任何既有 content_sha256。"
        ),
        "proof_scope": "证明编码已统一；不涉及正文语义。",
    },
    {
        "id": "outline-ch02-registration-currency",
        "chapter": "第02章",
        "path": f"{CLEAN_DIR}/第02章-相关文件.md",
        "unit_type": "regulatory_article",
        "source_pages": ["5"],
        "verdict": "source_faithful_but_outdated",
        "disposition": "pending",
        "summary": "暂行规定第十二条、第十三条的证书定期登记制度已被后续文件废止，正文尚未加时效性注。",
        "detail": (
            "第十二条“每 3 年登记一次”、第十三条登记条件与再次登记的继续教育证明要求，"
            "经与原书印刷页 5 核对属逐字忠实转录，不是清洗缺陷。"
            "但工信厅人〔2019〕50 号已废止证书登记与继续教育系列文件，"
            "且人事部、信息产业部已分别改为人力资源和社会保障部、工业和信息化部。"
            "按“忠于原文”原则不得改写条文，须另加时效性注。本项本轮未完成。"
        ),
        "proof_scope": "已确认条文转录忠实且废止文件可达；逐条时效性注与哈希固化留待续审。",
    },
]

# Chapters whose verification is complete this round vs. still pending.
CHAPTER_STATUS = {
    "前言.md": "source_verified",
    "第01章-考试说明.md": "pending_source_verification",
    "第02章-相关文件.md": "source_verified",
    "第03章-考试科目1-综合知识.md": "pending_source_verification",
    "第04章-考试科目2-案例分析.md": "pending_source_verification",
    "第05章-考试科目3-论文与题型举例.md": "pending_source_verification",
}

ASSET_INVENTORY = [
    {
        "id": "outline-ch02-annex-svg",
        "path": "assets/figures/00.考试大纲/第02章/附表-专业类别资格名称和级别对应表.svg",
        "kind": "structural_redraw",
        "carried_in": f"{CLEAN_DIR}/第02章-相关文件.md",
        "source_basis": "原书印刷页 10（PDF 图像页 20）",
        "redraw_declaration": "结构化重绘，不是原书图片；斜线分区、列宽与绝对尺寸未复刻。",
        "renders_checked_at": REVIEWED_AT,
    }
]

VERDICTS = {
    "consistent",
    "cleaning_defect",
    "source_faithful_but_outdated",
    "source_conflict",
    "unverifiable",
}
DISPOSITIONS = {
    "no_change",
    "fixed_in_clean",
    "annotated_currency",
    "annotated_limitation",
    "pending",
    "escalated",
}
CHAPTER_STATES = {"source_verified", "pending_source_verification"}

HEADING_RE = re.compile(r"^(#{1,6})\s+\S")


def normalized_lf_sha256(path: Path) -> str:
    """Repo-wide integrity convention: strip BOM, CRLF/CR -> LF, then sha256."""
    text = path.read_text(encoding="utf-8-sig")
    return hashlib.sha256(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def file_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for name, status in CHAPTER_STATUS.items():
        clean_path = ROOT / CLEAN_DIR / name
        if not clean_path.is_file():
            raise AssertionError(f"missing clean outline file: {CLEAN_DIR}/{name}")
        text = clean_path.read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        raw_path = ROOT / RAW_DIR / name
        records.append(
            {
                "path": f"{CLEAN_DIR}/{name}",
                "verification_status": status,
                "content_sha256": normalized_lf_sha256(clean_path),
                "lines": len(lines),
                "headings": sum(1 for line in lines if HEADING_RE.match(line)),
                "tables": sum(1 for line in lines if line.startswith("|---") or line.startswith("|--")),
                "editor_notes": text.count("整理者注（非原文）"),
                "cleaning_errata": text.count("清洗勘误"),
                "raw_counterpart": f"{RAW_DIR}/{name}" if raw_path.is_file() else None,
            }
        )
    return records


def validate(findings: list[dict[str, object]], files: list[dict[str, object]]) -> None:
    ids = [str(item["id"]) for item in findings]
    if len(ids) != len(set(ids)):
        duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
        raise AssertionError(f"duplicate finding ids: {duplicates}")
    for finding in findings:
        if finding["verdict"] not in VERDICTS:
            raise AssertionError(f"{finding['id']}: unknown verdict {finding['verdict']!r}")
        if finding["disposition"] not in DISPOSITIONS:
            raise AssertionError(f"{finding['id']}: unknown disposition {finding['disposition']!r}")
        if not str(finding.get("proof_scope", "")).strip():
            raise AssertionError(f"{finding['id']}: proof_scope must not be empty")
        target = str(finding["path"])
        if not (ROOT / target).exists():
            raise AssertionError(f"{finding['id']}: path does not exist: {target}")
    for record in files:
        if record["verification_status"] not in CHAPTER_STATES:
            raise AssertionError(f"{record['path']}: unknown verification_status")
    for asset in ASSET_INVENTORY:
        if not (ROOT / str(asset["path"])).is_file():
            raise AssertionError(f"missing asset: {asset['path']}")
    # A finding that claims the text was fixed must leave a visible errata or
    # editor note in that file, so the ledger can never silently outrun 正文.
    for finding in findings:
        if finding["disposition"] != "fixed_in_clean":
            continue
        target = ROOT / str(finding["path"])
        if not target.is_file():
            continue
        body = target.read_text(encoding="utf-8-sig")
        if "清洗勘误" not in body and "整理者注（非原文）" not in body and "转录范围" not in body:
            raise AssertionError(f"{finding['id']}: fixed_in_clean but no visible note in {finding['path']}")


def build_audit() -> dict[str, object]:
    files = file_records()
    findings = [dict(item) for item in FINDINGS]
    validate(findings, files)

    verdict_counts = Counter(str(item["verdict"]) for item in findings)
    disposition_counts = Counter(str(item["disposition"]) for item in findings)
    verified = [record for record in files if record["verification_status"] == "source_verified"]
    reviewed_printed = sorted({entry[1] for entry in REVIEWED_PAGES})

    return {
        "schema_version": 1,
        "reviewed_at": REVIEWED_AT,
        "field_definitions": {
            "source": "原书书目信息与本地扫描件校验值；扫描件不入库。",
            "page_map": "PDF 图像页 -> 印刷页；扫描含重复拍摄，故不存在算术映射。",
            "reviewed_pages": "本轮逐页视觉核对的图像页、印刷页、对应清洗版文件与结论。",
            "findings": "逐项核查结论；verdict 区分“清洗缺陷”与“忠于原书但已过时”。",
            "verdict": "consistent/cleaning_defect/source_faithful_but_outdated/source_conflict/unverifiable。",
            "disposition": "no_change/fixed_in_clean/annotated_currency/annotated_limitation/pending/escalated。",
            "external_sources": "外部证据的 URL、整页哈希、被引用摘录哈希与访问日期。",
            "asset_inventory": "落盘图表资产及其来源与重绘声明。",
            "proof_scope": "该结论能够证明及不能证明的证据边界。",
        },
        "source": dict(SOURCE),
        "method": dict(METHOD),
        "scope": {
            "clean_dir": CLEAN_DIR,
            "raw_dir": RAW_DIR,
            "files_total": len(files),
            "files_source_verified": len(verified),
            "files_pending": len(files) - len(verified),
            "pdf_pages": SOURCE["pdf_pages"],
            "duplicate_scan_pages": list(DUPLICATE_PAGES),
            "unique_scan_pages": SOURCE["pdf_pages"] - len(DUPLICATE_PAGES),
            "pages_reviewed_this_round": len(REVIEWED_PAGES),
            "printed_pages_reviewed": reviewed_printed,
        },
        "page_map": {str(key): value for key, value in sorted(PAGE_MAP.items())},
        "reviewed_pages": [
            {"pdf_page": pdf_page, "printed_page": printed, "path": f"{CLEAN_DIR}/{name}", "conclusion": note}
            for pdf_page, printed, name, note in REVIEWED_PAGES
        ],
        "files": files,
        "findings": findings,
        "external_sources": [dict(item) for item in EXTERNAL_SOURCES],
        "asset_inventory": [dict(item) for item in ASSET_INVENTORY],
        "summary": {
            "findings_total": len(findings),
            "findings_by_verdict": dict(sorted(verdict_counts.items())),
            "findings_by_disposition": dict(sorted(disposition_counts.items())),
            "external_sources": len(EXTERNAL_SOURCES),
            "assets": len(ASSET_INVENTORY),
            "conclusion": (
                "第02章与前言已完成逐页视觉核对，发现 7 项清洗缺陷（含 1 处表值错误、"
                "8 项政策正文缺失、6 项资格条目缺失和 1 处文号误写）并全部修订；"
                "1 项忠于原书但已过时的登记制度条文仍待补时效性注。"
                "第01、03、04、05 章尚未完成源件核对，不得据本账本认为其已核准。"
            ),
            "proof_scope": (
                "本账本只证明所列印刷页已被逐页视觉核对且结论已落到正文；"
                "不证明未列章节的正确性，也不冒充出版社或考试主管机构的认证。"
            ),
        },
    }


def rendered_json() -> str:
    return json.dumps(build_audit(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that data/outline_audit.json exactly matches generated output",
    )
    args = parser.parse_args()

    try:
        content = rendered_json()
    except (AssertionError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8-sig") if OUTPUT_PATH.is_file() else ""
        if current != content:
            print(f"ERROR: {OUTPUT_PATH.relative_to(ROOT)} is not reproducible", file=sys.stderr)
            return 1
        audit = json.loads(content)
        print(
            "outline audit is reproducible: "
            f"{audit['summary']['findings_total']} findings, "
            f"{audit['scope']['files_source_verified']}/{audit['scope']['files_total']} files source-verified"
        )
        return 0

    OUTPUT_PATH.write_text(content, encoding="utf-8", newline="\n")
    audit = json.loads(content)
    print(
        f"wrote {OUTPUT_PATH.relative_to(ROOT)}: "
        f"{audit['summary']['findings_total']} findings, "
        f"{audit['scope']['pages_reviewed_this_round']} pages reviewed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
