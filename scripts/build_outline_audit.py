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
REVIEWED_AT = "2026-09-01"

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
    "external_verification": "通过浏览器读取主管机构公开页面，记录可见页面 DOM 快照 SHA-256 与被引用正文摘录 SHA-256；网页可能动态变化。",
    "integrity_normalization": "utf8_bom_stripped_lf",
    "limitation": (
        "源扫描件不入库，故本账本不能仅凭版本库复现视觉核对过程；"
        "逐页结论以 reviewed_pages 中记录的印刷页号与核查人结论为准。"
    ),
}

# PDF image page -> printed page.  The scan contains six captures of printed
# page 1 (PDF pages 6--11); pages 7--11 are the five duplicate captures.
# Pages 12--74 then follow the printed numbering consecutively, and page 75
# is the unnumbered back cover.  The observed mapping is recorded explicitly
# rather than inferred from a presumed arithmetic offset across the front matter.
PAGE_MAP = {
    1: "封面",
    2: "扉页",
    3: "版权页/内容简介",
    4: "I",
    5: "II",
    6: "1",
    75: "封底",
}
PAGE_MAP.update({page: "1（重复扫描）" for page in range(7, 12)})
PAGE_MAP.update({page: str(page - 10) for page in range(12, 75)})

DUPLICATE_PAGES = [7, 8, 9, 10, 11]

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
    (16, "6", "第02章-相关文件.md", "暂行规定第十六条续至第十七条，逐字核对一致"),
    (17, "7", "第02章-相关文件.md", "实施办法第一至第三条及第四条开头，逐字核对一致"),
    (18, "8", "第02章-相关文件.md", "实施办法第四条续至第九条开头，逐字核对一致"),
    (19, "9", "第02章-相关文件.md", "实施办法第九条续至第十五条，逐字核对一致"),
    (20, "10", "第02章-相关文件.md", "附表：二维表被压平、6 项资格缺失、文号误作国人部发"),
    (21, "11", "第02章-相关文件.md", "主题词/抄送/印发块，原缺失，本轮补录"),
    (22, "12", "第02章-相关文件.md", "软考办〔2005〕1 号文件头与首段，抬头与过渡句原缺失"),
    (23, "13", "第02章-相关文件.md", "中日互认表 5 行及“二”至“五”四项，原缺 2 行、1 值错、4 项缺失"),
    (24, "14", "第02章-相关文件.md", "软考办〔2006〕2 号文件头、首段与中韩互认表 2 行，表值一致"),
    (25, "15", "第02章-相关文件.md", "中韩“二”至“五”四项与落款，四项原缺失"),
    (26, "16", "第01章-考试说明.md", "考试目标与考试要求（1）—（8），发现两处转录错误并已修正"),
    (27, "17", "第01章-考试说明.md", "考试要求（9）—（12）、考试科目设置及考试范围开头，逐条一致"),
    (27, "17", "第03章-考试科目1-综合知识.md", "考试范围开头及 1.1—1.2.2 条目，处理器两处转录差异已修正"),
    (
        61,
        "51",
        "第03章-考试科目1-综合知识.md",
        "印刷页 51 上半为本章结尾（和文档标准/标准化机构/知识产权/第 12、13 节），逐条一致",
    ),
    (71, "61", "第05章-考试科目3-论文与题型举例.md", "论文选题范围与开头句，‘按照规定的要求撰写论文’已按源修正"),
    (72, "62", "第05章-考试科目3-论文与题型举例.md", "选择题 1 的‘响应’表述及（2）选项，已按源修正"),
    (73, "63", "第05章-考试科目3-论文与题型举例.md", "问答题背景，补回‘操作系统’一词"),
    (74, "64", "第05章-考试科目3-论文与题型举例.md", "论文题正文与三个问题；问题 2‘就你所下过功夫的地方’二轮按源修正"),
]

CH3_PAGE_NOTES = {
    28: "印刷页 18：数据库括号与 1.4.1 小节标题按源修正；二轮将外部设备条目恢复为‘鼠标’",
    30: "印刷页 20：1.4.3 小节、DO-178 标点、网络指标与 WLAN 拓扑按源修正；二轮恢复 1.4.2/1.4.4‘安全攸关’用字（3 处）",
    31: "印刷页 21：1.6.1/1.6.2 标题层级恢复，其他条目一致",
    32: "印刷页 22：二轮将 1.8.3‘渐进迭代式开发’按源修正，其余条目一致",
    33: "印刷页 23：信息系统顶层标题按源修正，其他条目一致",
    34: "印刷页 24：本页条目逐条核对一致",
    35: "印刷页 25：DSS 标题层级与九项功能表述按源修正",
    36: "印刷页 26：专家系统、办公自动化系统与 ERP 条目逐条核对一致",
    37: "印刷页 27：本页条目逐条核对一致",
    38: "印刷页 28：二轮恢复 3.3.1‘计算机网络安全’",
    39: "印刷页 29：密钥缩写按源页照录；二轮补回 3.5.1‘密钥的分配方法’并把 3.5.2 标题改为‘公钥加密体制的密钥管理’",
    40: "印刷页 30：漏洞扫描标题与安全协议括号按源修正",
    41: "印刷页 31：敏捷开发核心思想表述按源修正",
    42: "印刷页 32：二轮将 4.1.4 首条恢复为‘RUP 的核心概念和特点’",
    43: "印刷页 33：OOD/JDO 条目按源修正；二轮将 4.3.1 恢复为‘使用的手段’",
    44: "印刷页 34：本页条目逐条核对一致",
    45: "印刷页 35：本页条目逐条核对一致",
    46: "印刷页 36：二轮将 4.7.3‘SCM 核心内容’按源收敛为‘版本控制和变更控制’",
    47: "印刷页 37：二轮恢复 5.1.4‘物理层’与 5.2.1‘目或度’",
    48: "印刷页 38：二轮将 5.3.1 标题恢复为‘数据库设计的基本步骤’、5.3.6 改回源书无括号写法",
    49: "印刷页 39：二轮将 5.5.1 标题恢复为‘分类与特点’",
    50: "印刷页 40：ABSD 概念与标题条目按源修正",
    51: "印刷页 41：ABSD 模型涵盖阶段条目补回",
    52: "印刷页 42：架构复用标题与能力/优势条目按源修正",
    53: "印刷页 43：DSSA 域条目、质量定义表述按源修正；二轮将 7.1.3 末条恢复为‘内涵’",
    54: "印刷页 44：架构评估重要概念的三项条目恢复，ATAM 标识按源页保留；二轮恢复 8.1.1 首条（去‘和联系’）与第三条（软件可靠性工程的定义和阶段）",
    55: "印刷页 45：可靠性度量指标、影响因素、模型和管理措施按源修正；二轮恢复 8.1.3—8.1.5 三个小节标题及 8.1.4 首条",
    56: "印刷页 46：容错分类、方法及系统配置条目按源页照录/补回；二轮将 8.4.1 标题恢复为‘容错设计技术’",
    58: "印刷页 48：软件架构演化标题、条目及对象/复合片段内涵按源修正；二轮恢复 9.1.1‘的原因’、9.2.4‘实质’并补回 8.6.4‘软件可靠性定量方法的灵活使用’",
    59: "印刷页 49：二轮按源恢复 9.3.2 五条目（含‘静态演化需求’），其余条目一致",
    60: "印刷页 50：架构维护条目及第 10 节标题层级按源修正",
}
for _pdf_page in range(28, 61):
    REVIEWED_PAGES.append(
        (
            _pdf_page,
            str(_pdf_page - 10),
            "第03章-考试科目1-综合知识.md",
            CH3_PAGE_NOTES.get(_pdf_page, f"印刷页 {_pdf_page - 10}：逐页核对，未见需修订差异"),
        )
    )
CH4_PAGE_NOTES = {
    61: "印刷页 51：第 1 节编号、2.1 开头条目与考试科目标题按源修正",
    62: "印刷页 52：2.1 四种模型/企业总体框架及 2.2—2.4 层级按源恢复；二轮将 2.3 下五项恢复为‘信息化工程建设方法’的子条目",
    63: "印刷页 53：3.1 层次式架构标题和两项组成条目按源修正",
    64: "印刷页 54：云原生架构模式、BPEL 术语按源修正",
    65: "印刷页 55：嵌入式系统硬件体系结构和软件架构概述按源恢复",
    66: "印刷页 56：嵌入式中间件/开发环境层级及鸿蒙、GeneSys 案例按源修正",
    67: "印刷页 57：局域网/广域网架构、IPV4/IPV6 和网络需求条目按源修正",
    68: "印刷页 58：安全模型与系统安全体系规划层级按源恢复",
    69: "印刷页 59：WPDRRC、网络安全框架及抗抵赖框架按源恢复",
    70: "印刷页 60：工业安全案例和 kappa 大小写按源修正",
}
for _pdf_page in range(61, 71):
    REVIEWED_PAGES.append(
        (
            _pdf_page,
            str(_pdf_page - 10),
            "第04章-考试科目2-案例分析.md",
            CH4_PAGE_NOTES[_pdf_page],
        )
    )
REVIEWED_PAGES.sort(key=lambda entry: (entry[0], entry[2]))

EXTERNAL_SOURCES = [
    {
        "id": "ruankao-qualification-roster",
        "url": "https://www.ruankao.org.cn/introduction/main.html",
        "title": "中国计算机技术职业资格网 · 考试介绍 / 资格设置",
        "fetched_at": "2026-08-25",
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
        "fetched_at": "2026-08-29",
        "full_page_sha256": "6a806e6e83ba3bb3af7aa6b0f7d8309ec8f7592f4ac264b469ce720a8f0303aa",
        "excerpt_chars": 258,
        "excerpt_sha256": "7a1da044e490e6a74d9dcdd833b19fb4e9c57ac4934a764cab9eb388dfc34710",
        "used_for": ["outline-ch02-registration-currency"],
        "agreement": "confirms",
        "conclusion": (
            "该通知明确废止证书登记（信办人〔2004〕47 号）、继续教育（信办人〔2004〕48 号）及两份配套文件，"
            "与暂行规定第十二条、第十三条的登记制度直接相关；清洗稿已保留原文并补充时效性提示。"
        ),
        "proof_scope": "可见页面 DOM 快照与四项废止文件摘录均已固化哈希；该证据确认配套文件已废止，"
        "不单独裁定《暂行规定》其他条款或现行证书管理制度。",
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
        "id": "outline-ch01-coordination-role",
        "chapter": "第01章",
        "path": f"{CLEAN_DIR}/第01章-考试说明.md",
        "unit_type": "prose",
        "source_pages": ["16"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "考试目标将‘项目管理师相互协作、配合工作’误写为‘项目经理协同工作’。",
        "detail": (
            "原书印刷页 16 为‘能够与系统分析师、项目管理师相互协作、配合工作’；"
            "清洗稿与原始整理稿均误作‘能够与系统分析师、项目经理协同工作’。本轮按源修正清洗稿。"
        ),
        "proof_scope": "证明该短语已与印刷页 16 一致；不改写原始整理稿。",
    },
    {
        "id": "outline-ch01-hardware-wording",
        "chapter": "第01章",
        "path": f"{CLEAN_DIR}/第01章-考试说明.md",
        "unit_type": "prose",
        "source_pages": ["16"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "考试要求第 8 项漏‘硬件’二字，将‘软硬件技术’误作‘软件技术’。",
        "detail": "原书印刷页 16 为‘了解计算机软硬件技术的综合应用’，清洗稿与原始整理稿均漏‘硬件’二字；本轮补回。",
        "proof_scope": "证明考试要求第 8 项已按印刷页 16 修正。",
    },
    {
        "id": "outline-ch05-essay-instruction",
        "chapter": "第05章",
        "path": f"{CLEAN_DIR}/第05章-考试科目3-论文与题型举例.md",
        "unit_type": "prose",
        "source_pages": ["61"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "论文科目开头句被误写为‘分别从以下三个方面进行论述’。",
        "detail": (
            "原书印刷页 61 为‘选择其中一个专题，按照规定的要求撰写论文’；"
            "清洗稿与原始整理稿均误作‘分别从以下三个方面进行论述’，本轮按源修正。"
        ),
        "proof_scope": "证明开头句已与印刷页 61 一致；不扩展原书未列出的写作要求。",
    },
    {
        "id": "outline-ch05-snmp-response-wording",
        "chapter": "第05章",
        "path": f"{CLEAN_DIR}/第05章-考试科目3-论文与题型举例.md",
        "unit_type": "question_text",
        "source_pages": ["62"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "SNMP 示例将‘请求/响应协议’误写为‘请求/应答协议’。",
        "detail": "原书印刷页 62 的题干明确使用‘请求/响应协议’，本轮据源修正清洗稿。",
        "proof_scope": "仅证明题干术语已与印刷页 62 一致；不裁定示例答案。",
    },
    {
        "id": "outline-ch05-snmp-options",
        "chapter": "第05章",
        "path": f"{CLEAN_DIR}/第05章-考试科目3-论文与题型举例.md",
        "unit_type": "question_options",
        "source_pages": ["62", "63"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "SNMP 示例第（2）空的 C、D 选项被错误转录。",
        "detail": (
            "原书印刷页 63 列为‘A. 异步、B. 同步、C. 主从、D. 面向连接’；"
            "清洗稿与原始整理稿均将 C、D 误作‘报告、异常报告’，本轮逐项修正。"
        ),
        "proof_scope": "证明四个选项文字与印刷页 63 一致；不补写原书未提供的标准答案。",
    },
    {
        "id": "outline-ch05-ie-os-word",
        "chapter": "第05章",
        "path": f"{CLEAN_DIR}/第05章-考试科目3-论文与题型举例.md",
        "unit_type": "question_text",
        "source_pages": ["63"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "问答题背景漏‘操作’二字，将‘Windows 操作系统’写成‘Windows 系统’。",
        "detail": "原书印刷页 63 为‘Windows 操作系统自带的 IE 浏览器’，本轮补回漏字。",
        "proof_scope": "证明该句已与印刷页 63 一致；不更新原书中的历史软件名称。",
    },
    {
        "id": "outline-ch03-foundation-entries",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_entries",
        "source_pages": ["17", "18"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "处理器与数据库条目存在错词、标点和括号缺陷。",
        "detail": (
            "文件标题恢复原书科目名‘系统架构设计综合知识’（保留目录用‘第3章’前缀）；"
            "印刷页 17 的‘指令集：CISC 和 RISC 结构’被写成逗号，‘国产处理器芯片结构’被误作‘多核处理器技术’；"
            "印刷页 18 的数据库产品列表缺内层括号，均已按源页修正。"
        ),
        "proof_scope": "证明所列条目与印刷页 17—18 一致；不对源书术语作现代化扩写。",
    },
    {
        "id": "outline-ch03-embedded-network-terms",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_entries",
        "source_pages": ["18", "20"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "嵌入式软件小节标题、网络指标和 WLAN 拓扑表述被误录。",
        "detail": (
            "印刷页 18、20 的 1.4.1/1.4.3 标题及两条嵌入式条目按源恢复，DO-178 后标点改为冒号；"
            "‘速率、带宽、吞吐量、时延和利用率’与‘三类拓扑’亦据源页修正。"
        ),
        "proof_scope": "证明所列标题和条目与印刷页 18、20 一致。",
    },
    {
        "id": "outline-ch03-heading-hierarchy",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "heading_structure",
        "source_pages": ["21", "22", "25", "40", "44", "50"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "多个编号小节标题被压成普通条目，信息层级丢失。",
        "detail": (
            "恢复印刷页 21 的 1.6.1/1.6.2、印刷页 22 的 1.8.1/1.8.2、印刷页 25 的 2.4.3/2.4.4、"
            "印刷页 44 的评估条目层级、印刷页 50 的 10.1—10.6 标题，以及 6.1.3 小节标题；"
            "同时将第 2 节顶层标题按源改为‘信息系统基础知识’。"
        ),
        "proof_scope": "证明标题层级和编号已按所记印刷页恢复；不声称源书层级设计代表现行考试大纲。",
    },
    {
        "id": "outline-ch03-dss-wording",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_entries",
        "source_pages": ["23", "25"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "信息系统与 DSS 条目出现标题、漏字和分隔符错误。",
        "detail": (
            "印刷页 23 的顶层标题恢复为‘信息系统基础知识’；印刷页 25 的‘功能-过程结构图’、"
            "DSS 九项功能中的‘为决策整理和提供数据’及末段分号按源页修正。"
        ),
        "proof_scope": "证明所列文字与印刷页 23、25 一致；不补写源书未列出的 DSS 功能。",
    },
    {
        "id": "outline-ch03-architecture-methods",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_entries",
        "source_pages": ["40", "41", "42", "43"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "ABSD、架构复用和 DSSA 条目存在错词、整段缺失及标题错位。",
        "detail": (
            "印刷页 40 将‘发动因素’修正为‘设计元素’；印刷页 41 补回 ABSD 模型涵盖的六个阶段；"
            "印刷页 42 将复用小节标题改为‘对象及形式’并恢复‘能力和优势’；印刷页 43 补回 DSSA 的‘垂直域和水平域’。"
        ),
        "proof_scope": "证明所列条目与印刷页 40—43 一致；不扩展 ABSD/DSSA 的现行方法定义。",
    },
    {
        "id": "outline-ch03-security-terms",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "security_entries",
        "source_pages": ["30"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "系统漏洞扫描条目被简写，安全协议内层括号丢失。",
        "detail": "印刷页 30 的‘系统漏洞扫描的基本原理和意义’及‘安全协议（SSL、PGP 和 IPSec）’均已按源页恢复。",
        "proof_scope": "证明两条安全相关条目与印刷页 30 一致。",
    },
    {
        "id": "outline-ch03-database-spelling",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "terminology",
        "source_pages": ["29", "39", "40"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "密钥、ORM 和 No SQL 术语被清洗稿改写，现按源页照录。",
        "detail": (
            "印刷页 29 的缩写为 DK/KK，印刷页 39—40 的产品/数据库类别写作‘hibernate’和‘No SQL’；"
            "清洗稿此前分别写作 DEK/KEK、Hibernate 和 NoSQL，现恢复源页写法，并在正文注记其可能是源书术语或印刷问题。"
        ),
        "proof_scope": "证明术语拼写与所记印刷页一致；不裁定 DK/KK 是否为源书笔误或替代缩写。",
    },
    {
        "id": "outline-ch03-agile-ood",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_entries",
        "source_pages": ["31", "33"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "敏捷开发、OOD 与数据库接口条目存在转录差异。",
        "detail": (
            "印刷页 31 的敏捷核心思想恢复‘以人为本和迭代增量式’；印刷页 33 的 OOD 恢复‘内涵’，"
            "数据持久化接口恢复为 SQL、JDBC 和 JDO。"
        ),
        "proof_scope": "证明所列表述与印刷页 31、33 一致；不对方法论内容作额外解释。",
    },
    {
        "id": "outline-ch03-quality-evaluation",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_entries",
        "source_pages": ["44"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "架构评估重要概念缺少两项条目且核心概念被压缩。",
        "detail": "印刷页 44 的‘架构评估的基本概念’、核心概念（含利益相关人）和评估方法分类三项已恢复，ATAM 标识亦按源页保留。",
        "proof_scope": "证明三项条目与印刷页 44 一致；不将其视为现行评估标准清单。",
    },
    {
        "id": "outline-ch03-reliability-terms",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "reliability_entries",
        "source_pages": ["43", "45"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "可靠性质量定义、度量指标、影响因素和管理措施存在多处源文差异。",
        "detail": (
            "按印刷页 43、45 恢复‘具体内涵’、8.1.2 标题‘软件可靠性的定量描述’及其‘软件可靠性的度量方法和意义’条目，"
            "并恢复失效强度/平均恢复前时间/平均故障间隔时间、‘运行剖面’、‘十类常用模型的内涵’及‘修正措施’等原文表述。"
        ),
        "proof_scope": "证明所列词语与印刷页 43、45 一致；源书度量术语是否为印刷或时代差异另见正文注，不作静默现代化。",
    },
    {
        "id": "outline-ch03-fault-tolerance",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "reliability_entries",
        "source_pages": ["46"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "容错分类、容错方法和系统配置条目被改写或漏列。",
        "detail": (
            "印刷页 46 的分类原文第三项与第一项同为‘信息容错’，方法条目恢复‘指令复执和程序卷回、冗余、N 版本’；"
            "并补回‘服务器集群技术’。源文重复项已在正文注记，未静默改为‘时间容错’。"
        ),
        "proof_scope": "证明条目与印刷页 46 一致；不裁定源书重复术语是否为作者笔误。",
    },
    {
        "id": "outline-ch03-evolution-maintenance",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_structure",
        "source_pages": ["48", "50"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "软件架构演化与维护条目的标题、内涵和度量缩写多处误录。",
        "detail": (
            "印刷页 48 恢复 9.1 概述、9.1.1 演化的重要性及其三条源文、对象/复合片段的‘内涵’条目，"
            "并删除清洗稿误加的‘演化包含的内容/演化的方式’；"
            "印刷页 50 将架构修改管理改为‘隔离区域’，将耦合因子缩写改为 FFC，并恢复第 10 节六个编号标题。"
        ),
        "proof_scope": "证明所列标题和术语与印刷页 48、50 一致；不判断源书术语与现行标准的兼容性。",
    },
    {
        "id": "outline-page-map-correction",
        "chapter": "全目录",
        "path": f"{CLEAN_DIR}/INDEX.md",
        "unit_type": "page_mapping",
        "source_pages": [],
        "verdict": "cleaning_defect",
        "disposition": "annotated_limitation",
        "summary": "源扫描件页码映射曾将 PDF 第 16、17 页误标为重复页，重复页计数因此偏大。",
        "detail": (
            "对同一 SHA-256 源扫描件逐页渲染确认：PDF 6—11 是印刷页 1 的六次拍摄，"
            "只有 PDF 7—11 为重复；PDF 16、17 分别是印刷页 6、7 的唯一内容页。"
            "本轮将映射改为 PDF 12—74 对应印刷页 2—64，PDF 75 为封底，并将重复页数从 7 改为 5。"
        ),
        "proof_scope": "证明账本页映射与所持源扫描件一致；不使未入账的视觉核对自动变为已完成。",
    },
    {
        "id": "outline-ch04-section-structure",
        "chapter": "第04章",
        "path": f"{CLEAN_DIR}/第04章-考试科目2-案例分析.md",
        "unit_type": "heading_structure",
        "source_pages": ["51", "52"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "第 1 节编号丢失，2.1 下的模型与企业总体框架被错移，2.2—2.4 标题编号整体错位。",
        "detail": (
            "文件标题恢复原书科目名‘系统架构设计案例分析’（保留目录用‘第4章’前缀）；"
            "印刷页 51—52 恢复 1.1—1.4 四个编号；在 2.1 下补回单机应用模式、客户机/服务器模式、"
            "面向服务架构模式、企业数据交换总线和企业信息系统总体框架及四个子项；"
            "并按源页将 ADM、信息化总体架构方法、案例分析分别归为 2.2、2.3、2.4。"
        ),
        "proof_scope": "证明章节层级与条目已按印刷页 51—52 恢复；不据此判断其他版本大纲的章节编号。",
    },
    {
        "id": "outline-ch04-layered-architecture",
        "chapter": "第04章",
        "path": f"{CLEAN_DIR}/第04章-考试科目2-案例分析.md",
        "unit_type": "outline_entries",
        "source_pages": ["53"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "3.1 被改写为另一套‘体系结构设计’条目，层次式架构的两项源文缺失。",
        "detail": "印刷页 53 将标题及条目恢复为‘层次式架构概述’、‘层次式架构的定义和特性’和‘层次式架构的一般组成（表现层、中间层、数据访问层和数据层）’。",
        "proof_scope": "证明 3.1 标题和两项条目与印刷页 53 一致。",
    },
    {
        "id": "outline-ch04-cloud-soa-terms",
        "chapter": "第04章",
        "path": f"{CLEAN_DIR}/第04章-考试科目2-案例分析.md",
        "unit_type": "terminology",
        "source_pages": ["54"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "云原生架构模式和 BPEL 条目各有一个术语被改写。",
        "detail": "印刷页 54 的原文为‘服务化架构模式’和‘面向 Web 服务的业务流程执行语言（BPEL）’，清洗稿此前分别写作‘微服务化’和‘基于 Web 服务’，现已恢复。",
        "proof_scope": "证明两处术语与印刷页 54 一致；不评价这些术语在现行技术语境中的推荐写法。",
    },
    {
        "id": "outline-ch04-embedded-structure",
        "chapter": "第04章",
        "path": f"{CLEAN_DIR}/第04章-考试科目2-案例分析.md",
        "unit_type": "outline_structure",
        "source_pages": ["55", "56"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "6.1/6.2 的嵌入式硬件、中间件和开发环境层级被压缩、替换或漏列。",
        "detail": (
            "印刷页 55—56 恢复 6.1 的‘定义和发展现状’、硬件体系结构四个子项及软件架构概述；"
            "将中间件恢复为定义/特点/分类、一般架构、主要功能和典型产品四项；"
            "将嵌入式系统软件开发环境恢复为定义/特点/分类、一般架构、主要功能和典型环境四项。"
        ),
        "proof_scope": "证明所列层级和条目与印刷页 55—56 一致；源页的产品名称疑似笔误另见整理者注。",
    },
    {
        "id": "outline-ch04-embedded-cases",
        "chapter": "第04章",
        "path": f"{CLEAN_DIR}/第04章-考试科目2-案例分析.md",
        "unit_type": "case_titles",
        "source_pages": ["56"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "6.4 两个案例标题被误写，鸿蒙和‘安全攸关/GeneSys 系统架构’信息丢失。",
        "detail": "印刷页 56 的原文为‘鸿蒙操作系统架构案例分析’和‘面向安全攸关系统的跨领域 GeneSys 系统架构’，清洗稿此前写作‘航空操作系统’及‘安全关键…GeneSys 架构’。",
        "proof_scope": "证明两个案例标题与印刷页 56 一致；不证明案例正文或现行产品状态。",
    },
    {
        "id": "outline-ch04-network-terms",
        "chapter": "第04章",
        "path": f"{CLEAN_DIR}/第04章-考试科目2-案例分析.md",
        "unit_type": "network_entries",
        "source_pages": ["57"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "网络架构拓扑、IP 版本大小写、需求分析和地址规划条目存在增删或改写。",
        "detail": (
            "印刷页 57 恢复局域网/广域网的‘环型’架构、源文 IPV4/IPV6 大写、"
            "删除源文没有的‘应用需求’，并补回‘地址规划模型’。"
        ),
        "proof_scope": "证明网络条目与印刷页 57 一致；不将源文大小写当作现行 IETF 书写规范。",
    },
    {
        "id": "outline-ch04-security-hierarchy",
        "chapter": "第04章",
        "path": f"{CLEAN_DIR}/第04章-考试科目2-案例分析.md",
        "unit_type": "security_structure",
        "source_pages": ["58", "59"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "安全模型、系统安全体系规划和整体架构设计的标题层级及关键条目被错并或漏列。",
        "detail": (
            "印刷页 58—59 将主要安全模型置于 8.1 下，恢复状态机/BLP、CWM、ChineseWall 的源文写法；"
            "恢复 8.2‘系统安全体系架构规划框架’及其‘安全技术体系架构’，并将 WPDRRC 整体架构和面向企业安全控制系统的条目归入 8.3。"
        ),
        "proof_scope": "证明标题层级与列举条目与印刷页 58—59 一致；不判断模型命名的现代标准化写法。",
    },
    {
        "id": "outline-ch04-security-framework",
        "chapter": "第04章",
        "path": f"{CLEAN_DIR}/第04章-考试科目2-案例分析.md",
        "unit_type": "security_entries",
        "source_pages": ["59"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "OSI 安全体系框架漏列‘抗抵赖框架’。",
        "detail": "印刷页 59 在完整性框架之后还列有‘抗抵赖框架’，清洗稿此前未转录，本轮补回。",
        "proof_scope": "证明该条目已按印刷页 59 补回。",
    },
    {
        "id": "outline-ch04-industrial-kappa",
        "chapter": "第04章",
        "path": f"{CLEAN_DIR}/第04章-考试科目2-案例分析.md",
        "unit_type": "case_titles",
        "source_pages": ["60"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "安全案例把‘工业安全’误作‘工控安全’，kappa 变形架构的大小写与源文不一致。",
        "detail": "印刷页 60 的案例为‘基于混合云的工业安全架构设计’，且条目写作‘常见 kappa 架构的变形架构’；清洗稿已按源页修正并去除非原文加粗。",
        "proof_scope": "证明案例名称和 kappa 字面与印刷页 60 一致；不据此推断工业安全与工控安全概念等价。",
    },
    {
        "id": "outline-ch03-safety-youguan",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "terminology",
        "source_pages": ["20"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "1.4.2/1.4.4 三处‘安全攸关’被误作‘安全关键’。",
        "detail": (
            "原书印刷页 20 印为‘安全攸关系统’（1.4.2 条目）与‘安全攸关软件的安全性设计’"
            "‘安全攸关软件的定义和作用’（1.4.4 标题及条目）；清洗稿三处均写作‘安全关键’。"
            "二轮独立逐页复核以四倍放大确认用字后按源恢复；同目录第04章 6.4 的‘安全攸关’此前已改对，可互为参照。"
        ),
        "proof_scope": "证明三处用字与印刷页 20 一致；不判断‘攸关/关键’在其他语料的规范写法。",
    },
    {
        "id": "outline-ch03-devices-mouse",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_entries",
        "source_pages": ["18"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "1.2.6 外部设备条目多写‘键盘’二字。",
        "detail": "原书印刷页 18 为‘鼠标、显示器、扫描仪和摄像头等’，清洗稿误作‘键盘鼠标、显示器、扫描仪和摄像头等’；二轮按源删去。",
        "proof_scope": "证明该条目与印刷页 18 一致。",
    },
    {
        "id": "outline-ch03-lifecycle-iterative",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_entries",
        "source_pages": ["22"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "1.8.3‘渐进迭代式开发’被误作‘渐进和迭代式开发’。",
        "detail": "原书印刷页 22 为‘计划驱动方法、渐进迭代式开发、精益开发和敏捷开发’；二轮放大确认后按源修正。",
        "proof_scope": "证明该方法名与印刷页 22 一致。",
    },
    {
        "id": "outline-ch03-security-key-sections",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "security_entries",
        "source_pages": ["28", "29"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "3.3.1 漏‘计算机’前缀，3.5.1 缺‘密钥的分配方法’条目，3.5.2 标题被改写。",
        "detail": (
            "印刷页 28 的技术体系组成为‘基础安全设备、计算机网络安全、操作系统安全、数据库安全和终端设备安全’；"
            "印刷页 29 顶部‘密钥的分配方法’是 3.5.1 的第二条（清洗稿漏录），"
            "且 3.5.2 标题原书为‘公钥加密体制的密钥管理’，清洗稿误作‘公钥的分配与管理’。二轮一并按源修正。"
        ),
        "proof_scope": "证明所列条目与标题与印刷页 28—29 一致；不裁定原书小节命名的学术严谨性。",
    },
    {
        "id": "outline-ch03-se-round2-wording",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_entries",
        "source_pages": ["32", "33", "36"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "RUP 首条、结构化方法‘使用的手段’和 SCM 核心内容三处与源不符。",
        "detail": (
            "印刷页 32 的 4.1.4 首条为‘RUP 的核心概念和特点’（清洗稿误作‘RUP 模型的基本原理和特点’）；"
            "印刷页 33 的 4.3.1 首条为‘结构化方法的定义、合理性准则和使用的手段’（误作‘使用的方法’）；"
            "印刷页 36 的 4.7.3 为‘SCM 核心内容：版本控制和变更控制’，"
            "清洗稿多出源书没有的‘配置状态报告和配置审计’。二轮一并按源修正。"
        ),
        "proof_scope": "证明三处文字与印刷页 32、33、36 一致；不为源书补写其未列的 SCM 内容。",
    },
    {
        "id": "outline-ch03-db-round2",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_entries",
        "source_pages": ["37", "38", "39"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "数据库小节的层级括号、术语、标题和无括号写法五处与源不符。",
        "detail": (
            "印刷页 37 的 5.1.4 为‘数据库系统的体系结构（物理层、逻辑层和视图层）’（误作‘概念层’），"
            "5.2.1 为‘基本术语（属性、域、目或度和候选码等）’（‘目或度’被改写为‘元组’）；"
            "印刷页 38 的 5.3.1 标题为‘数据库设计的基本步骤’（误作‘概述’），"
            "5.3.6 末条原书无括号，为‘试运行和评价目标、测试要求’；"
            "印刷页 39 的 5.5.1 标题为‘分类与特点’（误作‘分类与特征’）。二轮一并按源修正；"
            "‘目或度’疑为原书‘目或度（基数）’类表述，照录不作现代化替换。"
        ),
        "proof_scope": "证明五处与印刷页 37—39 一致；不裁定‘目或度’是否为原书笔误。",
    },
    {
        "id": "outline-ch03-quality-scene-connotation",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_entries",
        "source_pages": ["43"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "7.1.3 末条‘重点关注的 6 个属性场景的内涵’被误作‘内容’。",
        "detail": "原书印刷页 43 末条为‘……的内涵’，二轮放大确认后按源修正。",
        "proof_scope": "证明该条与印刷页 43 一致。",
    },
    {
        "id": "outline-ch03-reliability-headings-round2",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "reliability_entries",
        "source_pages": ["44", "45", "46"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "8.1 可靠性小节的标题体系整体错位，8.1.1 两条目与 8.4.1 标题不符。",
        "detail": (
            "印刷页 44 的 8.1.1 首条为‘软件可靠性的定义、目标与硬件可靠性的区别’（清洗稿多‘和联系’），"
            "第三条为‘软件可靠性工程的定义和阶段（分配、设计、分析、测试和评估）’"
            "（清洗稿误作‘软件可靠性的定量描述（规定时间：自然尺度……）’，该内容源书并无）；"
            "印刷页 45 的三个小节标题为‘可靠性目标’‘可靠性测试的意义’‘广义的可靠性测试与狭义的可靠性测试’"
            "（清洗稿作‘软件可靠性目标’‘软件可靠性与硬件可靠性对比’‘软件可靠性测试的意义’），"
            "且 8.1.4 首条为‘软件可靠性测试的目的和意义’（清洗稿误作‘软件可靠性与硬件可靠性的区别’）；"
            "印刷页 46 的 8.4.1 标题为‘容错设计技术’。二轮一并按源恢复。"
        ),
        "proof_scope": "证明标题与条目与印刷页 44—46 一致；源书小节命名是否严谨另见正文注，不作静默改写。",
    },
    {
        "id": "outline-ch03-reliability-eval-bullet",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "reliability_entries",
        "source_pages": ["48"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "8.6.4 缺末条‘软件可靠性定量方法的灵活使用’。",
        "detail": "原书印刷页 48 顶部还有一条‘软件可靠性定量方法的灵活使用’，属 8.6.4 的第三条，清洗稿漏录；二轮补回。",
        "proof_scope": "证明该条目已按印刷页 48 补回。",
    },
    {
        "id": "outline-ch03-evolution-round2",
        "chapter": "第03章",
        "path": f"{CLEAN_DIR}/第03章-考试科目1-综合知识.md",
        "unit_type": "outline_structure",
        "source_pages": ["48", "49"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "9.1.1‘的原因’、9.2.4‘实质’用字错误，9.3.2 条目组与源不一致。",
        "detail": (
            "印刷页 48 的 9.1.1 第二条为‘软件架构的演化能更好地保证软件演化的原因’（误作‘的原则’），"
            "9.2.4 末条为‘约束演化的实质’（误作‘实施’）；"
            "印刷页 49 的 9.3.2 原书列五条：‘软件架构静态演化基本概念、静态演化需求、一般过程、"
            "原子演化操作、正交软件架构的演化实例’，清洗稿作四条且首条被改写为‘软件架构静态演化的定义’、"
            "缺‘静态演化需求’。二轮一并按源恢复。"
        ),
        "proof_scope": "证明所列标题与条目与印刷页 48—49 一致。",
    },
    {
        "id": "outline-ch04-informatization-hierarchy",
        "chapter": "第04章",
        "path": f"{CLEAN_DIR}/第04章-考试科目2-案例分析.md",
        "unit_type": "heading_structure",
        "source_pages": ["52"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "2.3 下‘信息化工程建设方法’的五项子条目被压平为同级条目。",
        "detail": (
            "原书印刷页 52 中，信息化架构模式、信息化建设生命周期、信息化工程总体规划的方法论、"
            "信息化资源管理、国际和国内有关信息化的标准、法律和规定五项是‘信息化工程建设方法’的"
            "下级子条目；清洗稿将其与父条目并列。二轮恢复父子层级；"
            "2.3 标题‘信息化总体架构方法’经四倍放大核对与源一致，维持不变。"
        ),
        "proof_scope": "证明 2.3 内部层级与印刷页 52 一致；不声称源书层级设计代表现行考试大纲。",
    },
    {
        "id": "outline-ch05-essay-q2-wording",
        "chapter": "第05章",
        "path": f"{CLEAN_DIR}/第05章-考试科目3-论文与题型举例.md",
        "unit_type": "question_text",
        "source_pages": ["64"],
        "verdict": "cleaning_defect",
        "disposition": "fixed_in_clean",
        "summary": "论述问题 2 开头‘就你所下过功夫的地方’被误作‘结合你所下过功夫的地方’。",
        "detail": "原书印刷页 64 为‘就你所下过功夫的地方进行叙述’，二轮放大确认后按源修正；本章其余部分经二次逐段对照无差异。",
        "proof_scope": "证明该句与印刷页 64 一致；不补写原书未提供的参考答案。",
    },
    {
        "id": "outline-ch02-registration-currency",
        "chapter": "第02章",
        "path": f"{CLEAN_DIR}/第02章-相关文件.md",
        "unit_type": "regulatory_article",
        "source_pages": ["5"],
        "verdict": "source_faithful_but_outdated",
        "disposition": "annotated_currency",
        "summary": "暂行规定第十二、十三条仍按原书照录；相关证书登记和继续教育配套文件已废止，正文已加时效性注。",
        "detail": (
            "第十二条“每 3 年登记一次”、第十三条登记条件与再次登记的继续教育证明要求，"
            "经与原书印刷页 5 核对属逐字忠实转录，不是清洗缺陷。"
            "工信厅人〔2019〕50 号明确废止信办人〔2004〕47 号证书登记通知、"
            "信办人〔2004〕48 号继续教育通知及两份配套文件。"
            "本轮保留原条文，并用整理者注说明证据边界和现行办理要求须以主管机构最新公告为准。"
        ),
        "proof_scope": "确认原条文转录忠实且四份配套文件已被通知废止；不单独裁定《暂行规定》其他条款或现行证书管理制度。",
    },
]

# Chapters whose verification is complete this round vs. still pending.
CHAPTER_STATUS = {
    "前言.md": "source_verified",
    "第01章-考试说明.md": "source_verified",
    "第02章-相关文件.md": "source_verified",
    "第03章-考试科目1-综合知识.md": "source_verified",
    "第04章-考试科目2-案例分析.md": "source_verified",
    "第05章-考试科目3-论文与题型举例.md": "source_verified",
}

FILE_SOURCE_PAGES = {
    "前言.md": [3, 4, 5],
    "第01章-考试说明.md": [26, 27],
    "第02章-相关文件.md": [6, *range(12, 26)],
    "第03章-考试科目1-综合知识.md": list(range(27, 62)),
    "第04章-考试科目2-案例分析.md": list(range(61, 71)),
    "第05章-考试科目3-论文与题型举例.md": list(range(71, 75)),
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
                "source_pdf_pages": list(FILE_SOURCE_PAGES[name]),
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
    if set(FILE_SOURCE_PAGES) != set(CHAPTER_STATUS):
        raise AssertionError("FILE_SOURCE_PAGES keys must exactly match CHAPTER_STATUS")
    for name, pages in FILE_SOURCE_PAGES.items():
        if len(pages) != len(set(pages)):
            raise AssertionError(f"{name}: source PDF page list contains duplicates")
        unknown = sorted(set(pages) - set(PAGE_MAP))
        if unknown:
            raise AssertionError(f"{name}: source PDF pages are absent from PAGE_MAP: {unknown}")
    expected_pdf_pages = set(range(1, int(SOURCE["pdf_pages"]) + 1))
    if set(PAGE_MAP) != expected_pdf_pages:
        missing = sorted(expected_pdf_pages - set(PAGE_MAP))
        extra = sorted(set(PAGE_MAP) - expected_pdf_pages)
        raise AssertionError(f"PAGE_MAP must cover every PDF page; missing={missing}, extra={extra}")
    mapped_duplicates = sorted(page for page, printed in PAGE_MAP.items() if "重复扫描" in str(printed))
    if mapped_duplicates != sorted(DUPLICATE_PAGES):
        raise AssertionError(
            f"DUPLICATE_PAGES disagrees with PAGE_MAP: declared={DUPLICATE_PAGES}, mapped={mapped_duplicates}"
        )
    if int(SOURCE["pdf_pages"]) - len(DUPLICATE_PAGES) != 70:
        raise AssertionError("unexpected unique_scan_pages; verify duplicate-page accounting")
    reviewed_keys = [(int(pdf_page), str(name)) for pdf_page, _printed, name, _note in REVIEWED_PAGES]
    if len(reviewed_keys) != len(set(reviewed_keys)):
        raise AssertionError("duplicate reviewed_pages entries")
    known_names = set(CHAPTER_STATUS)
    reviewed_by_file: dict[str, set[int]] = {}
    for pdf_page, printed, name, _note in REVIEWED_PAGES:
        if name not in known_names:
            raise AssertionError(f"reviewed page references unknown file: {name}")
        if pdf_page not in PAGE_MAP:
            raise AssertionError(f"reviewed page is absent from PAGE_MAP: PDF {pdf_page}")
        if printed != PAGE_MAP[pdf_page].replace("（重复扫描）", ""):
            raise AssertionError(f"reviewed page label disagrees with PAGE_MAP: PDF {pdf_page} -> {printed!r}")
        reviewed_by_file.setdefault(name, set()).add(pdf_page)
    for name, status in CHAPTER_STATUS.items():
        if status != "source_verified":
            continue
        expected = set(FILE_SOURCE_PAGES[name])
        actual = reviewed_by_file.get(name, set())
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise AssertionError(
                f"{name}: source_verified page set mismatch; missing PDF pages {missing}, extra PDF pages {extra}"
            )
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
    unique_reviewed_pdf_pages = {entry[0] for entry in REVIEWED_PAGES}
    reviewed_printed: list[str] = []
    seen_printed: set[str] = set()
    for _pdf_page, printed, _name, _note in REVIEWED_PAGES:
        if printed in seen_printed:
            continue
        seen_printed.add(printed)
        reviewed_printed.append(printed)

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
            "pages_reviewed_this_round": len(unique_reviewed_pdf_pages),
            "review_records": len(REVIEWED_PAGES),
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
                f"前言及第01—05章已完成本轮所列源页的逐页视觉核对，共记录 {len(findings)} 项 findings；"
                "其中清洗稿与页码治理问题已修正并留有可见说明，另有 1 项忠于原书但已过时的登记制度条文"
                "已保留原文并补充时效性注。"
                "本结论不等同于出版社或考试主管机构认证。"
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
