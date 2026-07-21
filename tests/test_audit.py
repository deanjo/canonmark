"""canonmark.audit 的稳定口径测试（自 agong docs-audit 测试迁移）。

默认 config = agong 现值，因此断言逐条沿用；仅把模块加载方式从「按路径 importlib
加载 docs-audit.py」换成「import canonmark.audit」。
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from canonmark import audit as DOCS_AUDIT


class DocsAuditTest(unittest.TestCase):
  """用最小临时仓库锁定 V2/V4/V5/V9/V10 行为。"""

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
    """补齐 V5 固定关键文档，避免目标断言被缺文件噪声干扰。"""
    for relative in (
        "docs/_restructure/README.md",
        "docs/_restructure/PLAN.md",
        "docs/_restructure/TASKS.md",
        "docs/engineering/agong-docs-standard.md",
    ):
      self.write(relative, self.valid_key_document())

  def v5_issues_for(self, relative: str) -> list[object]:
    """只返回指定文件的 V5 问题。"""
    return [
        issue
        for issue in DOCS_AUDIT.audit_v5(self.root).issues
        if issue.path == relative
    ]

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

    result = DOCS_AUDIT.audit_v10(self.root)

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

    result = DOCS_AUDIT.audit_v10(self.root)

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

    result = DOCS_AUDIT.audit_v10(self.root)

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

    result = DOCS_AUDIT.audit_v10(self.root)

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

    result = DOCS_AUDIT.audit_v10(self.root)

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

    result = DOCS_AUDIT.audit_v10(self.root)

    self.assertEqual(1, len(result.issues))
    self.assertEqual(3, result.issues[0].line)
    self.assertIn("missing-guide.md", result.issues[0].message)

  def test_v10_checks_explicit_docs_line_references(self) -> None:
    self.write("docs/target.md", "one\ntwo\n")
    self.write("docs/source.md", "证据：docs/target.md:3\n")

    result = DOCS_AUDIT.audit_v10(self.root)

    self.assertEqual(1, len(result.issues))
    self.assertIn("显式 docs 引用行号越界", result.issues[0].message)
    self.assertIn("docs/target.md:3", result.issues[0].message)

  def test_v10_fails_clearly_when_pyyaml_is_unavailable(self) -> None:
    original_yaml = DOCS_AUDIT.yaml
    original_error = DOCS_AUDIT.YAML_IMPORT_ERROR
    try:
      DOCS_AUDIT.yaml = None
      DOCS_AUDIT.YAML_IMPORT_ERROR = "No module named 'yaml'"

      result = DOCS_AUDIT.audit_v10(self.root)
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
    self.write(
        "docs/design/new-relative.md",
        self.valid_key_document(title="Relative Replacement"),
    )
    self.write(
        "docs/design/new-root.md",
        self.valid_key_document(title="Root Replacement"),
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

    issues = self.v5_issues_for(relative)

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

    result = DOCS_AUDIT.audit_v2(self.root)

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

    result = DOCS_AUDIT.audit_v4(self.root)

    self.assertEqual(["docs/needs-readme"], [issue.path for issue in result.issues])

  def test_v9_requires_meta_directory_navigation(self) -> None:
    self.write("docs/feature/README.md", "# Feature\n")
    self.write("docs/_restructure/README.md", "# Control Plane\n")
    readme = self.write(
        "docs/README.md",
        "[feature](./feature/README.md)\n",
    )

    missing = DOCS_AUDIT.audit_v9(self.root)
    self.assertEqual(1, len(missing.issues))
    self.assertIn("docs/_restructure/", missing.issues[0].message)

    readme.write_text(
        "[feature](./feature/README.md)\n"
        "[control](./_restructure/README.md)\n",
        encoding="utf-8",
    )
    self.assertEqual([], DOCS_AUDIT.audit_v9(self.root).issues)

  def test_v9_rejects_parallel_docs_root_even_when_linked(self) -> None:
    self.write("docs/docs/README.md", "# Parallel Root\n")
    self.write("docs/README.md", "[parallel](./docs/README.md)\n")

    result = DOCS_AUDIT.audit_v9(self.root)

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


if __name__ == "__main__":
  unittest.main()
