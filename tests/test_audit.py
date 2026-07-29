"""canonmark.audit 的稳定口径测试（自 agong docs-audit 测试迁移）。

默认 config = agong 现值，因此断言逐条沿用；仅把模块加载方式从「按路径 importlib
加载 docs-audit.py」换成「import canonmark.audit」。
"""

from __future__ import annotations

import contextlib
from datetime import date
import io
import tempfile
import unittest
from pathlib import Path

from canonmark import audit as DOCS_AUDIT
from canonmark.config import GovernanceConfig

# 结构性缺失（缺 frontmatter / 缺 README）判失败的口径。默认模式是 gradual，
# 只把这类缺失记为提示，因此断言「该报得出来」的用例显式声明 strict。
STRICT = GovernanceConfig(adoption_mode="strict")


class AuditTestBase(unittest.TestCase):
  """临时仓库夹具与断言辅助，供各测试类复用（自身不含用例）。"""

  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.root = Path(self.temp_dir.name)
    self.docs_dir = self.root / "docs"
    self.docs_dir.mkdir()

  def tearDown(self) -> None:
    self.temp_dir.cleanup()

  def write(self, relative: str, content: str = "") -> Path:
    """写入临时仓库文件，并返回绝对路径。"""
    path = self.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path

  def key_document(self, relative: str, content: str) -> bool:
    """按生产逻辑判定单个临时文档。"""
    path = self.write(relative, content)
    frontmatter = DOCS_AUDIT.parse_frontmatter(path)
    return DOCS_AUDIT.is_key_document(
        path, self.docs_dir, frontmatter, content
    )

  def valid_key_document(
      self,
      title: str = "Key Document",
      authority: str = "contract-current",
  ) -> str:
    """生成可复用的完整关键文档。"""
    return f"""---
status: current
applies_when: 处理当前文档定义的任务
not_for: 相邻但不受本文件约束的任务
current_authority: {authority}
supersedes: []
superseded_by: []
owner: engineering
last_reviewed: 2026-07-10
---
# {title}
"""

  def write_required_v5_documents(self) -> None:
    """写入几篇合法关键文档作为背景，让断言只落在被测文件上。

    这几个路径是 agong 旧默认清单的遗留命名，现已不是任何内置默认值
    （见 config.required_key_documents 现为空）；此处仅当测试数据用。
    """
    for relative in (
        "docs/_restructure/README.md",
        "docs/_restructure/PLAN.md",
        "docs/_restructure/TASKS.md",
        "docs/engineering/agong-docs-standard.md",
    ):
      self.write(relative, self.valid_key_document())

  def v5_issues_for(
      self, relative: str, config: GovernanceConfig | None = None
  ) -> list[object]:
    """只返回指定文件的 V5 问题。"""
    return [
        issue
        for issue in DOCS_AUDIT.audit_v5(self.root, config).issues
        if issue.path == relative
    ]

  def v5_notices_for(
      self, relative: str, config: GovernanceConfig | None = None
  ) -> list[object]:
    """只返回指定文件的 V5 提示（不判失败的那一类）。"""
    return [
        note
        for note in DOCS_AUDIT.audit_v5(self.root, config).notices
        if note.path == relative
    ]


class DocsAuditTest(AuditTestBase):
  """用最小临时仓库锁定 V2/V4/V5/V9/V10 行为。"""

  def test_v10_validates_file_and_same_file_line_fragments(self) -> None:
    self.write("docs/target.md", "one\ntwo\nthree\n")
    self.write(
        "docs/source.md",
        "\n".join(
            (
                "[valid](target.md#L2)",
                "[valid-range](target.md#L1-L3)",
                "[past-end](target.md#L4)",
                "[reverse](target.md#L3-L2)",
                "[same-file](#L99)",
            )
        ),
    )

    result = DOCS_AUDIT.audit_v10(self.root, STRICT)

    self.assertEqual(3, len(result.issues))
    messages = [issue.message for issue in result.issues]
    self.assertTrue(all("行号 fragment 越界" in message for message in messages))
    self.assertTrue(any("target.md#L4" in message for message in messages))
    self.assertTrue(any("target.md#L3-L2" in message for message in messages))
    self.assertTrue(any("#L99" in message for message in messages))

  def test_v10_heading_fragment_only_keeps_target_existence_check(self) -> None:
    self.write("docs/target.md", "# Existing Heading\n")
    self.write(
        "docs/source.md",
        "[existing](target.md#not-inferred)\n"
        "[missing](missing.md#not-inferred)\n",
    )

    result = DOCS_AUDIT.audit_v10(self.root, STRICT)

    self.assertEqual(1, len(result.issues))
    self.assertIn("相对链接目标不存在", result.issues[0].message)
    self.assertIn("missing.md#not-inferred", result.issues[0].message)

  def test_v10_checks_archive_readme_and_skips_historical_bodies(self) -> None:
    self.write(
        "docs/archive/README.md",
        "[missing archive index](missing-index.md)\n",
    )
    self.write(
        "docs/archive/old.md",
        "[ignored archived body](missing-archived.md)\n",
    )
    self.write(
        "docs/superseded.md",
        """---
status: superseded
---
[ignored superseded body](missing-superseded.md)
""",
    )

    result = DOCS_AUDIT.audit_v10(self.root, STRICT)

    self.assertEqual(
        ["docs/archive/README.md"],
        [issue.path for issue in result.issues],
    )
    self.assertIn("missing-index.md", result.issues[0].message)

  def test_v10_checks_markdown_images(self) -> None:
    self.write(
        "docs/source.md",
        "![missing diagram](assets/missing-diagram.png)\n",
    )

    result = DOCS_AUDIT.audit_v10(self.root, STRICT)

    self.assertEqual(1, len(result.issues))
    self.assertIn("assets/missing-diagram.png", result.issues[0].message)

  def test_v10_checks_html_links_and_images(self) -> None:
    self.write(
        "docs/source.md",
        '<a href="missing-page.md">page</a>\n'
        '<img src="assets/missing-image.png" />\n'
        '<a href="https://example.com/external">external</a>\n'
        '`<a href="ignored-inline.md">inline code</a>`\n'
        "```html\n"
        '<img src="ignored-fenced.png">\n'
        "```\n",
    )

    result = DOCS_AUDIT.audit_v10(self.root, STRICT)

    self.assertEqual(2, len(result.issues))
    self.assertEqual([1, 2], [issue.line for issue in result.issues])
    messages = [issue.message for issue in result.issues]
    self.assertTrue(any("missing-page.md" in message for message in messages))
    self.assertTrue(
        any("assets/missing-image.png" in message for message in messages)
    )

  def test_v10_checks_reference_style_links(self) -> None:
    self.write(
        "docs/source.md",
        "[guide][guide-ref]\n\n[guide-ref]: missing-guide.md\n",
    )

    result = DOCS_AUDIT.audit_v10(self.root, STRICT)

    self.assertEqual(1, len(result.issues))
    self.assertEqual(3, result.issues[0].line)
    self.assertIn("missing-guide.md", result.issues[0].message)

  def test_v10_checks_explicit_docs_line_references(self) -> None:
    self.write("docs/target.md", "one\ntwo\n")
    self.write("docs/source.md", "证据：docs/target.md:3\n")

    result = DOCS_AUDIT.audit_v10(self.root, STRICT)

    self.assertEqual(1, len(result.issues))
    self.assertIn("显式 docs 引用行号越界", result.issues[0].message)
    self.assertIn("docs/target.md:3", result.issues[0].message)

  def test_v10_fails_clearly_when_pyyaml_is_unavailable(self) -> None:
    original_yaml = DOCS_AUDIT.yaml
    original_error = DOCS_AUDIT.YAML_IMPORT_ERROR
    try:
      DOCS_AUDIT.yaml = None
      DOCS_AUDIT.YAML_IMPORT_ERROR = "No module named 'yaml'"

      result = DOCS_AUDIT.audit_v10(self.root, STRICT)
    finally:
      DOCS_AUDIT.yaml = original_yaml
      DOCS_AUDIT.YAML_IMPORT_ERROR = original_error

    self.assertEqual(1, len(result.issues))
    self.assertIn("缺少 PyYAML 依赖", result.issues[0].message)

  def test_frontmatter_multiline_lists_are_not_treated_as_empty(self) -> None:
    path = self.write(
        "docs/design/contract.md",
        """---
status: superseded
applies_when: 处理新链路
not_for: 历史链路
current_authority: historical-evidence
supersedes:
  - docs/design/older.md
superseded_by:
  - docs/design/newer.md
owner: design
last_reviewed: 2026-07-10
---
# Contract
""",
    )

    frontmatter = DOCS_AUDIT.parse_frontmatter(path)

    self.assertIsNone(frontmatter.error)
    self.assertTrue(
        DOCS_AUDIT.frontmatter_collection_has_items(
            path, frontmatter, "supersedes"
        )
    )
    self.assertTrue(
        DOCS_AUDIT.frontmatter_collection_has_items(
            path, frontmatter, "superseded_by"
        )
    )
    self.assertTrue(
        DOCS_AUDIT.frontmatter_collection_is_list(
            path, frontmatter, "supersedes"
        )
    )

  def test_frontmatter_collections_reject_scalar_values(self) -> None:
    path = self.write(
        "docs/design/contract.md",
        """---
status: current
applies_when: 处理当前契约
not_for: 历史证据
current_authority: contract-current
supersedes: older.md
superseded_by: [] # no replacement
owner: design
last_reviewed: 2026-07-10
---
# Contract
""",
    )
    frontmatter = DOCS_AUDIT.parse_frontmatter(path)

    self.assertFalse(
        DOCS_AUDIT.frontmatter_collection_is_list(
            path, frontmatter, "supersedes"
        )
    )
    self.assertTrue(
        DOCS_AUDIT.frontmatter_collection_is_list(
            path, frontmatter, "superseded_by"
        )
    )

  def test_v5_rejects_unclosed_yaml_quote(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/payments/README.md"
    self.write(
        relative,
        """---
status: current
applies_when: "处理当前契约
not_for: 历史证据
current_authority: contract-current
supersedes: []
superseded_by: []
owner: design
last_reviewed: 2026-07-10
---
# Payments 文档入口
""",
    )

    issues = self.v5_issues_for(relative)

    self.assertEqual(1, len(issues))
    self.assertIn("YAML frontmatter 非法", issues[0].message)

  def test_v5_fails_clearly_when_pyyaml_is_unavailable(self) -> None:
    original_yaml = DOCS_AUDIT.yaml
    original_error = DOCS_AUDIT.YAML_IMPORT_ERROR
    try:
      DOCS_AUDIT.yaml = None
      DOCS_AUDIT.YAML_IMPORT_ERROR = "No module named 'yaml'"

      result = DOCS_AUDIT.audit_v5(self.root)
    finally:
      DOCS_AUDIT.yaml = original_yaml
      DOCS_AUDIT.YAML_IMPORT_ERROR = original_error

    self.assertEqual(1, len(result.issues))
    self.assertIn("缺少 PyYAML 依赖", result.issues[0].message)

  def test_v5_invalid_yaml_date_fails_without_crashing(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/design/invalid-yaml-date.md"
    content = self.valid_key_document().replace(
        "last_reviewed: 2026-07-10",
        "last_reviewed: 2026-02-30",
    )
    self.write(relative, content)

    issues = self.v5_issues_for(relative)

    self.assertEqual(1, len(issues))
    self.assertEqual(9, issues[0].line)
    self.assertIn("YAML frontmatter 构造失败", issues[0].message)

  def test_v5_semantic_fields_must_be_non_empty_strings(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/design/semantic-type.md"
    cases = (
        ("status", "status: current", "status: 1"),
        (
            "applies_when",
            "applies_when: 处理当前文档定义的任务",
            "applies_when: false",
        ),
        (
            "not_for",
            "not_for: 相邻但不受本文件约束的任务",
            "not_for: 7",
        ),
        (
            "current_authority",
            "current_authority: contract-current",
            "current_authority: true",
        ),
        ("owner", "owner: engineering", "owner: 42"),
    )
    for field_name, original, replacement in cases:
      with self.subTest(field=field_name):
        self.write(
            relative,
            self.valid_key_document().replace(original, replacement),
        )

        issues = self.v5_issues_for(relative)

        self.assertEqual(1, len(issues))
        self.assertIn(
            f"{field_name} 必须是非空字符串",
            issues[0].message,
        )

  def test_v5_last_reviewed_accepts_date_or_valid_string(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/design/valid-review-date.md"
    for reviewed_value in ("2026-07-10", '"2026-07-10"'):
      with self.subTest(last_reviewed=reviewed_value):
        self.write(
            relative,
            self.valid_key_document().replace(
                "last_reviewed: 2026-07-10",
                f"last_reviewed: {reviewed_value}",
            ),
        )

        self.assertEqual([], self.v5_issues_for(relative))

  def test_v5_last_reviewed_rejects_invalid_string_and_non_date_type(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/design/invalid-review-date.md"
    for reviewed_value in ('"2026-02-30"', "20260710", "true"):
      with self.subTest(last_reviewed=reviewed_value):
        self.write(
            relative,
            self.valid_key_document().replace(
                "last_reviewed: 2026-07-10",
                f"last_reviewed: {reviewed_value}",
            ),
        )

        issues = self.v5_issues_for(relative)

        self.assertEqual(1, len(issues))
        self.assertIn("last_reviewed 必须是有效", issues[0].message)

  def test_v5_rejects_duplicate_top_level_status(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/design/duplicate-status.md"
    self.write(
        relative,
        """---
status: current
status: background
applies_when: 处理当前契约
not_for: 历史证据
current_authority: contract-current
supersedes: []
superseded_by: []
owner: design
last_reviewed: 2026-07-10
---
# Contract
""",
    )

    issues = self.v5_issues_for(relative)

    self.assertEqual(1, len(issues))
    self.assertIn("重复一级字段：status", issues[0].message)
    self.assertEqual(3, issues[0].line)

  def test_v5_rejects_non_string_collection_items(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/design/invalid-list.md"
    self.write(
        relative,
        """---
status: current
applies_when: 处理当前契约
not_for: 历史证据
current_authority: contract-current
supersedes:
  - docs/design/older.md: current
superseded_by: []
owner: design
last_reviewed: 2026-07-10
---
# Contract
""",
    )

    issues = self.v5_issues_for(relative)

    self.assertEqual(1, len(issues))
    self.assertIn("supersedes 列表第 1 项必须是非空字符串", issues[0].message)

  def test_v5_status_and_authority_must_match(self) -> None:
    self.assertTrue(
        DOCS_AUDIT.authority_matches_status("current", "contract-current")
    )
    self.assertTrue(
        DOCS_AUDIT.authority_matches_status(
            "current", "background-reference"
        )
    )
    self.assertFalse(
        DOCS_AUDIT.authority_matches_status(
            "current", "historical-evidence"
        )
    )
    self.assertTrue(
        DOCS_AUDIT.authority_matches_status(
            "background", "historical-evidence"
        )
    )
    self.assertFalse(
        DOCS_AUDIT.authority_matches_status(
            "superseded", "background-reference"
        )
    )

  def test_v5_current_document_must_not_declare_replacement(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/design/current-with-replacement.md"
    self.write(
        "docs/design/replacement.md",
        self.valid_key_document(title="Replacement Contract"),
    )
    self.write(
        relative,
        """---
status: current
applies_when: 处理当前契约
not_for: 历史证据
current_authority: contract-current
supersedes: []
superseded_by:
  - docs/design/replacement.md
owner: design
last_reviewed: 2026-07-11
---
# Current Contract
""",
    )

    issues = self.v5_issues_for(relative)

    self.assertEqual(1, len(issues))
    self.assertIn(
        "status=current 时 superseded_by 必须为空", issues[0].message
    )

  def test_v5_technical_plan_roadmap_uses_strict_mapping(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/payments/payment-roadmap.md"
    self.write(
        relative,
        self.valid_key_document(
            title="Payment Roadmap",
            authority="background-reference",
        ),
    )

    issues = self.v5_issues_for(relative)

    self.assertEqual(1, len(issues))
    self.assertIn(
        "current->roadmap-current",
        issues[0].message,
    )

  def test_v5_technical_plan_roadmap_allows_background_and_history(self) -> None:
    for status, authority in (
        ("background", "background-reference"),
        ("archive", "historical-evidence"),
        ("superseded", "historical-evidence"),
    ):
      with self.subTest(status=status):
        self.assertTrue(
            DOCS_AUDIT.technical_plan_authority_matches_status(
                status, authority, "roadmap-current"
            )
        )

  def test_v5_technical_plan_type_detection_uses_name_or_h1_only(self) -> None:
    cases = (
        ("docs/plan/00_ROADMAP.md", "# 启动入口", "roadmap-current"),
        (
            "docs/plan/runtime.md",
            "# Runtime Contract",
            "contract-current",
        ),
        ("docs/plan/tasks/T1_runtime.md", "# Runtime", "task-current"),
        (
            "docs/plan/08_acceptance_matrix.md",
            "# Verification",
            "acceptance-current",
        ),
        (
            "docs/plan/verification.md",
            "# 验收矩阵",
            "acceptance-current",
        ),
        (
            "docs/plan/tasks/agent_T1_contract.md",
            "# T1 强预检契约",
            "task-current",
        ),
        (
            "docs/plan/implementation.md",
            "# 实现计划与验收矩阵",
            "task-current",
        ),
        (
            "docs/plan/phase-three.md",
            "# 第三阶段实现计划",
            "task-current",
        ),
        (
            "docs/plan/retirement.md",
            "# 供应商详情轮间退场任务分片",
            "task-current",
        ),
    )
    for relative, heading, expected in cases:
      with self.subTest(relative=relative):
        path = self.root / relative
        self.assertEqual(
            expected,
            DOCS_AUDIT.technical_plan_expected_authority(path, heading),
        )

    ordinary_path = self.root / "docs/notes/overview.md"
    ordinary_text = (
        "# 普通说明\n"
        "正文提到 Roadmap、contract shard、task shard 和 acceptance matrix。\n"
    )
    self.assertIsNone(
        DOCS_AUDIT.technical_plan_expected_authority(
            ordinary_path, ordinary_text
        )
    )
    evidence_path = self.root / "docs/plan/evidence/protocol-contract.md"
    self.assertIsNone(
        DOCS_AUDIT.technical_plan_expected_authority(
            evidence_path, "# Historical Contract Evidence"
        )
    )

  def test_v5_superseded_by_rejects_missing_target(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/design/old.md"
    content = self.valid_key_document(
        title="Old Notes",
        authority="historical-evidence",
    )
    content = content.replace("status: current", "status: superseded")
    content = content.replace(
        "superseded_by: []",
        "superseded_by:\n  - missing.md",
    )
    self.write(relative, content)

    issues = self.v5_issues_for(relative)

    self.assertEqual(1, len(issues))
    self.assertIn("superseded_by 目标不存在：missing.md", issues[0].message)

  def test_v5_superseded_by_rejects_cycle(self) -> None:
    self.write_required_v5_documents()
    for relative, target in (
        ("docs/design/old-a.md", "old-b.md"),
        ("docs/design/old-b.md", "old-a.md"),
    ):
      content = self.valid_key_document(
          title="Historical Notes",
          authority="historical-evidence",
      )
      content = content.replace("status: current", "status: superseded")
      content = content.replace(
          "superseded_by: []",
          f"superseded_by:\n  - {target}",
      )
      self.write(relative, content)

    issues = self.v5_issues_for("docs/design/old-a.md")

    self.assertEqual(1, len(issues))
    self.assertIn("superseded_by 替代链形成环路", issues[0].message)
    self.assertIn(
        "docs/design/old-a.md -> docs/design/old-b.md -> "
        "docs/design/old-a.md",
        issues[0].message,
    )

  def test_v5_superseded_by_accepts_valid_multi_target_paths(self) -> None:
    self.write_required_v5_documents()
    # 两个目标都认领 old.md：反向指针对称是 T10 的要求，本用例只验路径口径。
    self.write(
        "docs/design/new-relative.md",
        self.valid_key_document(title="Relative Replacement").replace(
            "supersedes: []", "supersedes:\n  - old.md"
        ),
    )
    self.write(
        "docs/design/new-root.md",
        self.valid_key_document(title="Root Replacement").replace(
            "supersedes: []", "supersedes:\n  - docs/design/old.md"
        ),
    )
    relative = "docs/design/old.md"
    content = self.valid_key_document(
        title="Old Notes",
        authority="historical-evidence",
    )
    content = content.replace("status: current", "status: superseded")
    content = content.replace(
        "superseded_by: []",
        "superseded_by:\n"
        "  - new-relative.md\n"
        "  - docs/design/new-root.md",
    )
    self.write(relative, content)

    self.assertEqual([], self.v5_issues_for(relative))

  def test_v5_superseded_by_requires_metadata_for_non_readme_target(self) -> None:
    self.write_required_v5_documents()
    self.write("docs/design/notes.md", "# Notes\n")
    relative = "docs/design/old.md"
    content = self.valid_key_document(
        title="Old Notes",
        authority="historical-evidence",
    )
    content = content.replace("status: current", "status: superseded")
    content = content.replace(
        "superseded_by: []",
        "superseded_by:\n  - notes.md",
    )
    self.write(relative, content)

    issues = self.v5_issues_for(relative, STRICT)

    self.assertEqual(1, len(issues))
    self.assertIn(
        "superseded_by 非 README 目标无法执行五步门禁",
        issues[0].message,
    )

  def test_v5_superseded_by_allows_readme_as_navigation_router(self) -> None:
    self.write_required_v5_documents()
    self.write("docs/design/README.md", "# design/\n")
    relative = "docs/design/old.md"
    content = self.valid_key_document(
        title="Old Notes",
        authority="historical-evidence",
    )
    content = content.replace("status: current", "status: superseded")
    content = content.replace(
        "superseded_by: []",
        "superseded_by:\n  - README.md",
    )
    self.write(relative, content)

    self.assertEqual([], self.v5_issues_for(relative))

  def test_v5_key_document_detection_has_narrow_exclusions(self) -> None:
    template_text = """---
status: current
current_authority: contract-current
---
# 模板
本文件是执行契约，包含 Definition of Done。
"""
    self.assertFalse(
        self.key_document(
            "docs/ai-development/templates/execution-ledger.template.md",
            template_text,
        )
    )
    self.assertFalse(
        self.key_document(
            "docs/reviews/agent_审阅报告模板.md",
            template_text,
        )
    )
    self.assertTrue(
        self.key_document(
            "docs/payments/design/payment-flow.md",
            "# Payment Flow\n普通正文。\n",
        )
    )
    self.assertTrue(
        self.key_document(
            "docs/payments/payment-contract.md",
            "# Payment Contract\n普通正文。\n",
        )
    )

  def test_v5_readme_uses_explicit_authority_not_broad_body_signal(self) -> None:
    signal_text = "# 导航\n本文件是执行契约，冲突时以本文为准。\n"
    self.assertFalse(
        self.key_document("docs/legacy/README.md", signal_text)
    )
    self.assertFalse(
        self.key_document("docs/legacy/readmap.md", signal_text)
    )
    self.assertFalse(
        self.key_document(
            "docs/ordinary/README.md",
            """---
status: current
owner: ordinary
last_reviewed: 2026-07-10
---
# Ordinary Navigation
本文件是执行契约，冲突时以本文为准。
""",
        )
    )
    self.assertTrue(
        self.key_document(
            "docs/current/README.md",
            """---
status: current
current_authority: roadmap-current
---
# Current Navigation
""",
        )
    )
    self.assertFalse(
        self.key_document(
            "docs/old/readmap.md",
            """---
status: superseded
current_authority: historical-evidence
---
# Old Navigation
""",
        )
    )

  def test_v5_readme_recognizes_governed_h1_signals(self) -> None:
    titles = (
        "支付执行计划",
        "Payments Implementation Plan",
        "支付设计方案",
        "Payments Design",
        "Payments Roadmap",
        "支付契约",
        "Payments Contract",
        "支付任务",
        "Payments Task",
        "支付验收",
        "Payments Acceptance",
        "支付规范",
        "Payments Standard",
        "Payments Security",
        "Payments RCA",
        "Payments Rollout",
    )
    for title in titles:
      with self.subTest(title=title):
        self.assertTrue(
            self.key_document(
                "docs/payments/README.md",
                f"# {title}\n\n普通正文。\n",
            )
        )

  def test_v5_readme_recognizes_indented_atx_and_setext_h1(self) -> None:
    for content in (
        "   # Payments Roadmap\n\n普通正文。\n",
        "Payments Roadmap\n================\n\n普通正文。\n",
        "Payments Implementation\nPlan\n=======================\n\n普通正文。\n",
    ):
      with self.subTest(content=content):
        self.assertTrue(
            self.key_document("docs/payments/README.md", content)
        )

  def test_v5_plain_directory_readme_titles_stay_simplified(self) -> None:
    for relative, title in (
        ("docs/design/README.md", "design"),
        ("docs/tasks/README.md", "tasks"),
        ("docs/security/README.md", "security"),
        ("docs/standard/README.md", "standard"),
    ):
      with self.subTest(relative=relative):
        self.assertFalse(
            self.key_document(
                relative,
                f"# {title}\n\n本目录文件清单。\n",
            )
        )

  def test_v5_key_readme_with_missing_fields_fails(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/payments/README.md"
    self.write(
        relative,
        """---
status: current
owner: payments
last_reviewed: 2026-07-10
---
# Payments Roadmap

当前支付改造的路线图入口。
""",
    )

    issues = self.v5_issues_for(relative)

    self.assertEqual(1, len(issues))
    self.assertIn("关键文档 frontmatter 缺字段", issues[0].message)
    self.assertIn("current_authority", issues[0].message)

  def test_v5_ordinary_readme_with_simple_frontmatter_passes(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/payments/README.md"
    content = """---
status: current
owner: payments
last_reviewed: 2026-07-10
---
# Payments 文档导航

本目录收录支付模块的文档和历史记录。
"""
    self.write(relative, content)

    result = DOCS_AUDIT.audit_v5(self.root)

    self.assertFalse(self.key_document(relative, content))
    self.assertEqual([], result.issues)
    self.assertEqual("4 篇关键文档", result.checked)

  def test_v5_ordinary_readme_with_malformed_frontmatter_fails(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/payments/README.md"
    self.write(
        relative,
        """---
status: [current
owner: payments
last_reviewed: 2026-07-10
---
# Payments 文档导航
""",
    )

    issues = self.v5_issues_for(relative)

    self.assertEqual(1, len(issues))
    self.assertIn("YAML frontmatter 非法", issues[0].message)
    self.assertNotIn("必需字段", issues[0].message)

  def test_v5_ordinary_readme_with_duplicate_field_fails(self) -> None:
    self.write_required_v5_documents()
    relative = "docs/payments/README.md"
    self.write(
        relative,
        """---
status: current
status: background
owner: payments
last_reviewed: 2026-07-10
---
# Payments 文档导航
""",
    )

    issues = self.v5_issues_for(relative)

    self.assertEqual(1, len(issues))
    self.assertIn("重复一级字段：status", issues[0].message)
    self.assertNotIn("必需字段", issues[0].message)

  def test_v2_checks_live_and_archive_first_level_names(self) -> None:
    for relative in (
        "docs/live-good",
        "docs/Bad_Name",
        "docs/deep_search6.0",
        "docs/_restructure",
        "docs/archive/Bad_First",
        "docs/archive/good-first/Legacy_Name",
    ):
      (self.root / relative).mkdir(parents=True, exist_ok=True)

    # 白名单天生项目特有，已不再有内置默认值；本用例验的是白名单机制本身，
    # 故由用例自己声明这两个例外（原先它们是 agong 带进来的默认值）。
    config = GovernanceConfig(
        adoption_mode="strict",
        v2_path_exceptions=("deep_search6.0", "_restructure"),
    )
    result = DOCS_AUDIT.audit_v2(self.root, config)

    self.assertEqual(
        {"docs/Bad_Name", "docs/archive/Bad_First"},
        {issue.path for issue in result.issues},
    )

  def test_v4_requires_readme_only_for_non_asset_candidates(self) -> None:
    self.write("docs/needs-readme/a.md", "# A\n")
    self.write("docs/needs-readme/data.json", "{}\n")
    self.write("docs/has-readme/README.md", "# Index\n")
    self.write("docs/has-readme/a.md", "# A\n")
    self.write("docs/assets/a.png", "png")
    self.write("docs/assets/data.json", "{}\n")

    result = DOCS_AUDIT.audit_v4(self.root, STRICT)

    self.assertEqual(["docs/needs-readme"], [issue.path for issue in result.issues])

  def test_v9_requires_meta_directory_navigation(self) -> None:
    self.write("docs/feature/README.md", "# Feature\n")
    self.write("docs/_restructure/README.md", "# Control Plane\n")
    readme = self.write(
        "docs/README.md",
        "[feature](./feature/README.md)\n",
    )

    missing = DOCS_AUDIT.audit_v9(self.root, STRICT)
    self.assertEqual(1, len(missing.issues))
    self.assertIn("docs/_restructure/", missing.issues[0].message)

    readme.write_text(
        "[feature](./feature/README.md)\n"
        "[control](./_restructure/README.md)\n",
        encoding="utf-8",
    )
    self.assertEqual([], DOCS_AUDIT.audit_v9(self.root, STRICT).issues)

  def test_v9_rejects_parallel_docs_root_even_when_linked(self) -> None:
    self.write("docs/docs/README.md", "# Parallel Root\n")
    self.write("docs/README.md", "[parallel](./docs/README.md)\n")

    result = DOCS_AUDIT.audit_v9(self.root, STRICT)

    self.assertEqual(1, len(result.issues))
    self.assertEqual("docs/docs", result.issues[0].path)
    self.assertIn("平行文档根目录", result.issues[0].message)

  def test_result_output_format_remains_stable(self) -> None:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
      DOCS_AUDIT.print_result(
          DOCS_AUDIT.GateResult("V2", "docs:1", "3 个受治理目录")
      )
      failed = DOCS_AUDIT.GateResult("V4", "docs:1", "1 个候选目录")
      failed.add(
          self.root / "docs" / "missing",
          1,
          "缺少 README.md",
          self.root,
      )
      DOCS_AUDIT.print_result(failed)

    self.assertEqual(
        "V2 PASS docs:1 - 已检查 3 个受治理目录\n"
        "V4 FAIL docs:1 - 1 个问题；已检查 1 个候选目录\n"
        "  docs/missing:1 - 缺少 README.md\n",
        output.getvalue(),
    )


class SupersessionSymmetryTest(AuditTestBase):
  """T10 反向指针对称：旧文档自称退位，新文档必须认领。

  单边声明是最难靠人自查的一类腐烂——读到新文档的人无从知道它是否真的
  接管了旧职责，而读到旧文档的人被指向一个并不认账的目标。
  """

  def write_superseded(self, relative: str, target: str) -> None:
    """写一篇声明「我已被 target 取代」的旧文档。"""
    content = self.valid_key_document(authority="historical-evidence")
    content = content.replace("status: current", "status: superseded")
    content = content.replace(
        "superseded_by: []", f"superseded_by:\n  - {target}"
    )
    self.write(relative, content)

  def test_one_sided_supersession_is_rejected(self) -> None:
    self.write("docs/design/new.md", self.valid_key_document())
    self.write_superseded("docs/design/old.md", "new.md")

    issues = self.v5_issues_for("docs/design/old.md")

    self.assertEqual(1, len(issues))
    self.assertIn("替代关系是单边声明", issues[0].message)
    self.assertIn("docs/design/new.md 的 supersedes", issues[0].message)

  def test_symmetric_supersession_passes(self) -> None:
    self.write(
        "docs/design/new.md",
        self.valid_key_document().replace(
            "supersedes: []", "supersedes:\n  - old.md"
        ),
    )
    self.write_superseded("docs/design/old.md", "new.md")

    self.assertEqual([], self.v5_issues_for("docs/design/old.md"))

  def test_symmetry_accepts_docs_root_path_form(self) -> None:
    """两端可以各用一种路径口径，比对的是解析后的真实路径。"""
    self.write(
        "docs/design/new.md",
        self.valid_key_document().replace(
            "supersedes: []", "supersedes:\n  - docs/design/old.md"
        ),
    )
    self.write_superseded("docs/design/old.md", "new.md")

    self.assertEqual([], self.v5_issues_for("docs/design/old.md"))

  def test_current_status_conflict_does_not_also_report_symmetry(self) -> None:
    """已判「自称现行却声明被取代」时，再要求对方认领是错误的修复指导。"""
    self.write("docs/design/new.md", self.valid_key_document())
    content = self.valid_key_document()
    content = content.replace(
        "superseded_by: []", "superseded_by:\n  - new.md"
    )
    self.write("docs/design/old.md", content)

    issues = self.v5_issues_for("docs/design/old.md")

    self.assertEqual(1, len(issues))
    self.assertIn("status=current", issues[0].message)

  def test_cycle_does_not_also_report_symmetry(self) -> None:
    """成环时让对方认领只会把环缠得更紧，交给环路报错处理。"""
    self.write_superseded("docs/design/a.md", "b.md")
    self.write_superseded("docs/design/b.md", "a.md")

    issues = self.v5_issues_for("docs/design/a.md")

    self.assertEqual(1, len(issues))
    self.assertIn("替代链形成环路", issues[0].message)

  def test_readme_target_is_exempt_from_symmetry(self) -> None:
    """README 是导航入口，按 protocol §3 是替代目标的例外，不要求认领。"""
    self.write("docs/design/README.md", "# Design\n")
    self.write_superseded("docs/design/old.md", "README.md")

    self.assertEqual([], self.v5_issues_for("docs/design/old.md"))

  def test_one_sided_supersedes_claim_is_rejected(self) -> None:
    """protocol §2 明文举例的方向：新文档声称取代，旧文档必须承认。

    这一半更危险——漏掉时旧文档继续自称 current，两篇文档同时以现行权威
    示人，正是本项目要防的核心故障。
    """
    self.write(
        "docs/design/new.md",
        self.valid_key_document().replace(
            "supersedes: []", "supersedes:\n  - old.md"
        ),
    )
    self.write("docs/design/old.md", self.valid_key_document())

    issues = self.v5_issues_for("docs/design/new.md")

    self.assertEqual(1, len(issues))
    self.assertIn("本文档声称取代 old.md", issues[0].message)
    self.assertIn("status: superseded", issues[0].message)

  def test_supersedes_claim_passes_when_old_document_admits_it(self) -> None:
    self.write(
        "docs/design/new.md",
        self.valid_key_document().replace(
            "supersedes: []", "supersedes:\n  - old.md"
        ),
    )
    self.write_superseded("docs/design/old.md", "new.md")

    self.assertEqual([], self.v5_issues_for("docs/design/new.md"))

  def test_supersedes_target_untagged_is_only_a_notice_in_gradual(self) -> None:
    """对称地拆掉传染陷阱：被取代方还没贴标签时不判失败。"""
    self.write("docs/design/old.md", "# Old\n")
    self.write(
        "docs/design/new.md",
        self.valid_key_document().replace(
            "supersedes: []", "supersedes:\n  - old.md"
        ),
    )

    self.assertEqual([], self.v5_issues_for("docs/design/new.md"))
    self.assertIn(
        "被取代方尚未纳入治理",
        " ".join(
            note.message for note in self.v5_notices_for("docs/design/new.md")
        ),
    )

  def test_repair_guidance_converges_in_one_step(self) -> None:
    """照抄报错里的指导必须一次修完，不能把人骗进第二轮报错。

    只提示改 status 会立刻撞上 §4 矩阵（superseded 不允许配 *-current），
    这正是 T15 批评过的那类体验。
    """
    self.write(
        "docs/design/new.md",
        self.valid_key_document().replace(
            "supersedes: []", "supersedes:\n  - old.md"
        ),
    )
    self.write("docs/design/old.md", self.valid_key_document())
    issues = self.v5_issues_for("docs/design/new.md")
    self.assertEqual(1, len(issues))
    self.assertIn("current_authority: historical-evidence", issues[0].message)

    # 完全照抄指导修一遍，不做任何额外推断。
    repaired = self.valid_key_document(authority="historical-evidence")
    repaired = repaired.replace("status: current", "status: superseded")
    repaired = repaired.replace(
        "superseded_by: []", "superseded_by:\n  - new.md"
    )
    self.write("docs/design/old.md", repaired)

    self.assertEqual([], DOCS_AUDIT.audit_v5(self.root).issues)

  def test_missing_supersedes_target_is_reported(self) -> None:
    self.write(
        "docs/design/new.md",
        self.valid_key_document().replace(
            "supersedes: []", "supersedes:\n  - ghost.md"
        ),
    )

    issues = self.v5_issues_for("docs/design/new.md")

    self.assertEqual(1, len(issues))
    self.assertIn("supersedes 目标不存在：ghost.md", issues[0].message)


class AntiRotTest(AuditTestBase):
  """V11 防腐烂：能指认「谁和谁打架」的判失败，只能猜的一律降级为提示。"""

  def test_navigation_pointing_at_superseded_document_fails(self) -> None:
    """T12：README 把一篇自称作废的文档列为可读入口，两者必有一错。"""
    old = self.valid_key_document(authority="historical-evidence")
    old = old.replace("status: current", "status: superseded")
    old = old.replace("superseded_by: []", "superseded_by:\n  - new.md")
    self.write("docs/design/old.md", old)
    self.write("docs/design/README.md", "# Design\n\n[old](./old.md)\n")

    result = DOCS_AUDIT.audit_v11(self.root)

    self.assertEqual(
        ["docs/design/README.md"], [issue.path for issue in result.issues]
    )
    self.assertIn("导航仍指向已作废文档", result.issues[0].message)

  def test_navigation_pointing_at_current_document_passes(self) -> None:
    self.write("docs/design/live.md", self.valid_key_document())
    self.write("docs/design/README.md", "# Design\n\n[live](./live.md)\n")

    self.assertEqual([], DOCS_AUDIT.audit_v11(self.root).issues)

  def test_orphan_document_is_only_a_notice(self) -> None:
    """孤儿只提示：能确定的是「没人链接它」，不能确定的是「它是否该被删」。"""
    self.write("docs/design/orphan.md", self.valid_key_document())
    self.write("docs/design/README.md", "# Design\n")

    result = DOCS_AUDIT.audit_v11(self.root)

    self.assertEqual([], result.issues)
    self.assertEqual(
        ["docs/design/orphan.md"], [note.path for note in result.notices]
    )
    self.assertIn("孤儿文档", result.notices[0].message)

  def test_linked_document_is_not_an_orphan(self) -> None:
    self.write("docs/design/linked.md", self.valid_key_document())
    self.write("docs/design/README.md", "# Design\n\n[x](./linked.md)\n")

    self.assertEqual([], DOCS_AUDIT.audit_v11(self.root).notices)

  def test_untagged_document_is_out_of_scope(self) -> None:
    """未纳入治理的文档谈不上该被导航到，不产生孤儿噪音。"""
    self.write("docs/design/notes.md", "# Notes\n")
    self.write("docs/design/README.md", "# Design\n")

    result = DOCS_AUDIT.audit_v11(self.root)

    self.assertEqual([], result.issues)
    self.assertEqual([], result.notices)

  def test_stale_review_is_only_a_notice(self) -> None:
    """超期永不判失败：某天全库突然变红而当天无人改动，门禁就会被关掉。"""
    self.write("docs/design/aged.md", self.valid_key_document())
    self.write("docs/design/README.md", "# Design\n\n[x](./aged.md)\n")

    result = DOCS_AUDIT.audit_v11(
        self.root, today=date(2027, 6, 1)
    )

    self.assertEqual([], result.issues)
    self.assertEqual(
        ["docs/design/aged.md"], [note.path for note in result.notices]
    )
    self.assertIn("天未复核", result.notices[0].message)

  def test_recent_review_is_silent(self) -> None:
    self.write("docs/design/fresh.md", self.valid_key_document())
    self.write("docs/design/README.md", "# Design\n\n[x](./fresh.md)\n")

    result = DOCS_AUDIT.audit_v11(self.root, today=date(2026, 7, 27))

    self.assertEqual([], result.notices)

  def test_archive_readme_may_list_archived_documents(self) -> None:
    """archive 索引的本职就是列出归档文档，不能拿导航互检去打它。"""
    archived = self.valid_key_document(authority="historical-evidence")
    archived = archived.replace("status: current", "status: archive")
    self.write("docs/archive/2025/old.md", archived)
    self.write(
        "docs/archive/2025/README.md", "# 归档\n\n[旧设计](./old.md)\n"
    )

    result = DOCS_AUDIT.audit_v11(self.root)

    self.assertEqual([], result.issues)

  def test_superseded_document_is_not_flagged_as_orphan(self) -> None:
    """作废文档本就不该被导航链接，劝人加进 README 等于劝人踩另一个错。"""
    old = self.valid_key_document(authority="historical-evidence")
    old = old.replace("status: current", "status: superseded")
    old = old.replace("superseded_by: []", "superseded_by:\n  - new.md")
    self.write("docs/design/old.md", old)
    self.write(
        "docs/design/new.md",
        self.valid_key_document().replace(
            "supersedes: []", "supersedes:\n  - old.md"
        ),
    )
    self.write("docs/design/README.md", "# Design\n\n[new](./new.md)\n")

    result = DOCS_AUDIT.audit_v11(self.root)

    self.assertEqual([], result.issues)
    self.assertEqual([], result.notices)

  def test_directory_without_readme_does_not_flag_every_document(self) -> None:
    """目录还没建导航时，V4 提示一次即可，不该对每篇文档各报一次。"""
    for name in ("a", "b", "c"):
      self.write(f"docs/design/{name}.md", self.valid_key_document())

    result = DOCS_AUDIT.audit_v11(self.root)

    self.assertEqual([], result.notices)

  def test_stale_threshold_is_configurable(self) -> None:
    self.write("docs/design/aged.md", self.valid_key_document())
    self.write("docs/design/README.md", "# Design\n\n[x](./aged.md)\n")
    config = GovernanceConfig(last_reviewed_max_age_days=5)

    result = DOCS_AUDIT.audit_v11(
        self.root, config, today=date(2026, 7, 27)
    )

    self.assertEqual(1, len(result.notices))
    self.assertIn("已 17 天未复核（阈值 5 天）", result.notices[0].message)


class AdoptionModeTest(AuditTestBase):
  """渐进采用语义：没做的事不罚，做错的事才罚。

  存量项目装上 canonmark 时，「所有文档都没有 frontmatter」是常态而非过错。
  把它判失败会让工具在第一分钟就变红，团队的第一反应是卸载或关掉门禁。
  """

  def untagged(self, relative: str) -> None:
    """写一篇完全没有 frontmatter 的普通文档（存量项目的常态）。"""
    self.write(relative, f"# {Path(relative).stem}\n\n正文。\n")

  def test_gradual_downgrades_untagged_key_document_to_notice(self) -> None:
    self.untagged("docs/design/payment-design.md")

    result = DOCS_AUDIT.audit_v5(self.root)

    self.assertEqual([], result.issues)
    self.assertEqual(
        ["docs/design/payment-design.md"],
        [note.path for note in result.notices],
    )
    self.assertIn("未纳入治理", result.notices[0].message)

  def test_strict_still_fails_untagged_key_document(self) -> None:
    self.untagged("docs/design/payment-design.md")

    result = DOCS_AUDIT.audit_v5(self.root, STRICT)

    self.assertEqual(
        ["docs/design/payment-design.md"],
        [issue.path for issue in result.issues],
    )
    self.assertEqual([], result.notices)

  def test_gradual_still_fails_documents_listed_as_required(self) -> None:
    """项目显式声明「这几篇必须治理」时，缺标签就是没兑现自己的声明。"""
    self.untagged("docs/roadmap.md")
    config = GovernanceConfig(required_key_documents=("roadmap.md",))

    result = DOCS_AUDIT.audit_v5(self.root, config)

    self.assertEqual(
        ["docs/roadmap.md"], [issue.path for issue in result.issues]
    )

  def test_gradual_still_fails_malformed_frontmatter(self) -> None:
    """写了标签却写坏了 YAML 属于「做错」，任何模式下都判失败。"""
    self.write(
        "docs/design/broken.md",
        "---\nstatus: current\n  bad-indent: x\n---\n# Broken\n",
    )

    result = DOCS_AUDIT.audit_v5(self.root)

    self.assertEqual(
        ["docs/design/broken.md"], [issue.path for issue in result.issues]
    )

  def test_gradual_treats_leading_horizontal_rule_as_untagged(self) -> None:
    """以 --- 分隔线开头的存量笔记不是「写坏的标签」，是没贴标签。

    首行 --- 之后的首个非空行不像 YAML 键值对时，这个 --- 是 Markdown
    水平线；按「有 frontmatter 但缺字段」判失败会打破「没做的事不罚」。
    """
    self.write(
        "docs/design/payment-design.md",
        "---\n\n# 旧笔记\n\n早于治理规范的存量内容。\n\n---\n\n尾注。\n",
    )

    result = DOCS_AUDIT.audit_v5(self.root)

    self.assertEqual([], result.issues)
    self.assertEqual(
        ["docs/design/payment-design.md"],
        [note.path for note in result.notices],
    )
    self.assertIn("未纳入治理", result.notices[0].message)

  def test_strict_still_treats_leading_horizontal_rule_as_frontmatter(
      self,
  ) -> None:
    """strict 面向已完成治理的库：分隔线开头照旧按 frontmatter 缺陷判失败。"""
    self.write(
        "docs/design/payment-design.md",
        "---\n\n# 旧笔记\n\n早于治理规范的存量内容。\n\n---\n\n尾注。\n",
    )

    result = DOCS_AUDIT.audit_v5(self.root, STRICT)

    self.assertEqual(
        ["docs/design/payment-design.md"],
        [issue.path for issue in result.issues],
    )
    self.assertEqual([], result.notices)

  def test_unclosed_frontmatter_with_yaml_key_fails_in_both_modes(self) -> None:
    """--- 后紧跟键值对说明真在写标签；忘了闭合不能被水平线放宽漏掉。"""
    self.write(
        "docs/design/unclosed.md", "---\nstatus: current\n\n# 文档\n"
    )

    for config in (None, STRICT):
      with self.subTest(mode=config.adoption_mode if config else "gradual"):
        issues = self.v5_issues_for("docs/design/unclosed.md", config)
        self.assertEqual(1, len(issues))
        self.assertIn("缺少结束分隔符", issues[0].message)

  def test_bom_plus_horizontal_rule_is_untagged_in_gradual(self) -> None:
    """BOM 剥离与水平线宽松判定叠加：既不炸，也不误判成写坏的标签。"""
    self.write(
        "docs/design/payment-design.md",
        "﻿---\n\n# 旧笔记\n\n正文。\n",
    )

    result = DOCS_AUDIT.audit_v5(self.root)

    self.assertEqual([], result.issues)
    self.assertEqual(
        ["docs/design/payment-design.md"],
        [note.path for note in result.notices],
    )
    self.assertIn("未纳入治理", result.notices[0].message)

  def test_gradual_exempts_untagged_supersession_target(self) -> None:
    """贴一张作废标签是收益最高的第一步，不该被目标文档缺标签连坐。"""
    self.untagged("docs/design/payment-design-v2.md")
    content = self.valid_key_document(authority="historical-evidence")
    content = content.replace("status: current", "status: superseded")
    content = content.replace(
        "superseded_by: []", "superseded_by:\n  - payment-design-v2.md"
    )
    self.write("docs/design/payment-design.md", content)

    result = DOCS_AUDIT.audit_v5(self.root)

    self.assertEqual([], result.issues)
    self.assertIn(
        "替代目标尚未纳入治理",
        " ".join(note.message for note in result.notices),
    )

  def test_missing_supersession_target_reports_path_convention(self) -> None:
    """报「不存在」而不说期望什么口径，等于让第一次贴标签的人猜谜。"""
    self.write("docs/design/new-design.md", self.valid_key_document())
    content = self.valid_key_document(authority="historical-evidence")
    content = content.replace("status: current", "status: superseded")
    content = content.replace(
        "superseded_by: []", "superseded_by:\n  - design/new-design.md"
    )
    self.write("docs/design/old-design.md", content)

    issues = self.v5_issues_for("docs/design/old-design.md")

    self.assertEqual(1, len(issues))
    self.assertIn("是否想写 new-design.md", issues[0].message)

  def test_gradual_downgrades_missing_navigation(self) -> None:
    self.untagged("docs/guides/a.md")
    self.untagged("docs/guides/b.md")

    v4 = DOCS_AUDIT.audit_v4(self.root)
    v9 = DOCS_AUDIT.audit_v9(self.root)

    self.assertEqual([], v4.issues)
    self.assertEqual(["docs/guides"], [note.path for note in v4.notices])
    self.assertEqual([], v9.issues)
    self.assertEqual(["docs/README.md"], [note.path for note in v9.notices])

  def test_strict_still_fails_missing_navigation(self) -> None:
    self.untagged("docs/guides/a.md")
    self.untagged("docs/guides/b.md")

    self.assertEqual(
        ["docs/guides"],
        [issue.path for issue in DOCS_AUDIT.audit_v4(self.root, STRICT).issues],
    )
    self.assertEqual(
        ["docs/README.md"],
        [issue.path for issue in DOCS_AUDIT.audit_v9(self.root, STRICT).issues],
    )

  def test_gradual_downgrades_incomplete_navigation(self) -> None:
    """否则与 V4 直接打架：V4 说这个目录的 README 可以不建，V9 却要求链接它。"""
    self.write("docs/README.md", "# 文档\n\n[设计](./design/README.md)\n")
    self.write("docs/design/README.md", "# 设计\n")
    self.untagged("docs/guides/start.md")

    result = DOCS_AUDIT.audit_v9(self.root)

    self.assertEqual([], result.issues)
    self.assertIn("未导航正式顶层目录", result.notices[0].message)

  def test_gradual_downgrades_legacy_directory_names(self) -> None:
    """存量项目的 API_Reference 是既成事实，改名要连带改掉所有链接。"""
    self.untagged("docs/API_Reference/index.md")

    result = DOCS_AUDIT.audit_v2(self.root)

    self.assertEqual([], result.issues)
    self.assertEqual(["docs/API_Reference"], [n.path for n in result.notices])

  def test_gradual_downgrades_broken_links_in_untagged_docs(self) -> None:
    """存量坏链不是这次治理造成的；贴过标签的文档仍要为自己的链接负责。"""
    self.write("docs/legacy.md", "见 [详情](./nowhere.md)\n")
    self.write(
        "docs/tagged.md",
        self.valid_key_document() + "\n见 [详情](./missing.md)\n",
    )

    result = DOCS_AUDIT.audit_v10(self.root)

    self.assertEqual(["docs/tagged.md"], [i.path for i in result.issues])
    self.assertEqual(["docs/legacy.md"], [n.path for n in result.notices])

  def test_invalid_adoption_mode_is_rejected(self) -> None:
    with self.assertRaises(ValueError) as caught:
      GovernanceConfig(adoption_mode="lenient")

    self.assertIn("adoption_mode", str(caught.exception))

  def test_notices_print_without_failing_the_gate(self) -> None:
    output = io.StringIO()
    result = DOCS_AUDIT.GateResult("V5", "docs:1", "2 篇关键文档")
    result.notice(self.root / "docs" / "a.md", 1, "未纳入治理", self.root)
    with contextlib.redirect_stdout(output):
      DOCS_AUDIT.print_result(result)

    self.assertEqual(
        "V5 PASS docs:1 - 已检查 2 篇关键文档；1 条提示\n"
        "  提示 docs/a.md:1 - 未纳入治理\n",
        output.getvalue(),
    )


if __name__ == "__main__":
  unittest.main()
