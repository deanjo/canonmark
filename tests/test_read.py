"""`canon_read` 与 `canon index` 的行为契约测试。

最要紧的一条是 `test_superseded_body_never_appears`：作废文档的正文一个字都
不能出现在输出里。这不是「少返回一点」的优化，而是整个 P6 的立论——协议从
「写给消费者遵守的规矩」变成「消费者拿到的数据已经过滤」，靠的就是这条。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from canonmark import read as READ
from canonmark.config import GovernanceConfig
from canonmark.index import IndexUnavailable, build_index, render_index

STRICT = GovernanceConfig(adoption_mode="strict")

# 作废文档正文里的哨兵串：只要它出现在输出中，就说明过滤失效。
SENTINEL = "SENTINEL-固定重试三次-SENTINEL"


class ReadTestBase(unittest.TestCase):

  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.root = Path(self.temp_dir.name)
    (self.root / "docs").mkdir()

  def tearDown(self) -> None:
    self.temp_dir.cleanup()

  def write(self, relative: str, content: str) -> Path:
    path = self.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path

  def doc(
      self,
      status: str = "current",
      authority: str = "contract-current",
      superseded_by: str = "[]",
      supersedes: str = "[]",
      body: str = "正文占位。",
  ) -> str:
    return (
        f"---\nstatus: {status}\napplies_when: 实现或修改支付重试逻辑\n"
        f"not_for: 对账与退款流程\ncurrent_authority: {authority}\n"
        f"supersedes: {supersedes}\nsuperseded_by: {superseded_by}\n"
        f"owner: payments\nlast_reviewed: 2026-07-27\n---\n\n# 标题\n\n{body}\n"
    )

  def read(self, relative: str, config=None) -> READ.ReadResult:
    return READ.read_document(self.root / relative, self.root, config)


class CanonReadTest(ReadTestBase):

  def test_superseded_body_never_appears(self) -> None:
    """A17 的核心判据：作废文档的正文不得进入调用方上下文。"""
    self.write("docs/design/new.md", self.doc(supersedes="[old.md]"))
    self.write(
        "docs/design/old.md",
        self.doc(
            status="superseded",
            authority="historical-evidence",
            superseded_by="[new.md]",
            body=SENTINEL,
        ),
    )

    result = self.read("docs/design/old.md")
    rendered = READ.render_read_result(result)

    self.assertEqual(READ.SUPERSEDED, result.verdict)
    self.assertIsNone(result.body)
    self.assertTrue(result.body_withheld)
    self.assertNotIn(SENTINEL, rendered)
    self.assertIn("docs/design/new.md", rendered)

  def test_superseded_output_does_not_grow_with_document_length(self) -> None:
    """作废文档越长，省下的上下文越多——这是 canon_read 可量化的增量价值。

    对照实验里两组都答对了，因为夹具文档只有几百字节，读全文的代价可以忽略。
    真实设计文档是几十 KB 量级，那时「正文根本不进上下文」不再是细节。
    """
    self.write("docs/design/new.md", self.doc(supersedes="[old.md]"))
    old = self.doc(
        status="superseded",
        authority="historical-evidence",
        superseded_by="[new.md]",
        body=SENTINEL,
    )
    self.write("docs/design/old.md", old)
    short = len(
        READ.render_read_result(self.read("docs/design/old.md")).encode("utf-8")
    )

    self.write("docs/design/old.md", old + "压测数据。\n" * 2000)
    long = len(
        READ.render_read_result(self.read("docs/design/old.md")).encode("utf-8")
    )

    self.assertEqual(short, long)

  def test_superseded_without_target_still_withholds_body(self) -> None:
    """指不出替代目标时更要扣下正文——否则等于放行一篇公认过时的文档。"""
    self.write(
        "docs/design/old.md",
        self.doc(
            status="archive", authority="historical-evidence", body=SENTINEL
        ),
    )

    result = self.read("docs/design/old.md")

    self.assertIsNone(result.body)
    self.assertNotIn(SENTINEL, READ.render_read_result(result))

  def test_current_document_returns_body_without_frontmatter(self) -> None:
    """正文不该把 frontmatter 再附一遍：那些字段头部摘要里已经给过。"""
    self.write("docs/design/live.md", self.doc(body="真正的正文。"))

    result = self.read("docs/design/live.md")

    self.assertEqual(READ.CURRENT, result.verdict)
    self.assertIn("真正的正文。", result.body)
    self.assertNotIn("last_reviewed", result.body)
    self.assertNotIn("current_authority", result.body)

  def test_current_document_surfaces_scope_fields(self) -> None:
    """not_for/applies_when 原样交出，由调用方自己判断是否命中。"""
    self.write("docs/design/live.md", self.doc())

    rendered = READ.render_read_result(self.read("docs/design/live.md"))

    self.assertIn("实现或修改支付重试逻辑", rendered)
    self.assertIn("对账与退款流程", rendered)
    self.assertIn("适用性由你判断", rendered)

  def test_ungoverned_document_is_delivered_with_a_warning(self) -> None:
    """gradual 下放行正文 + 警告；拒绝返回只会把 agent 逼回内置读取工具。"""
    self.write("docs/notes.md", "# 随手笔记\n\n没有标签。\n")

    result = self.read("docs/notes.md")

    self.assertEqual(READ.UNGOVERNED, result.verdict)
    self.assertIn("没有标签。", result.body)
    self.assertIn("无法验证时效性", " ".join(result.diagnostics))

  def test_leading_horizontal_rule_document_is_ungoverned_in_gradual(
      self,
  ) -> None:
    """以 --- 分隔线开头的存量笔记按未纳入治理放行，而不是扣下正文。

    与审计器共用 parse_frontmatter 这一个判定入口，行为必须同步：
    gradual 下这个 --- 是 Markdown 水平线，不是写坏的 frontmatter。
    """
    self.write("docs/notes.md", "---\n\n# 随手笔记\n\n正文在此。\n")

    result = self.read("docs/notes.md")

    self.assertEqual(READ.UNGOVERNED, result.verdict)
    self.assertIn("正文在此。", result.body)
    self.assertIn("未纳入治理", " ".join(result.diagnostics))

  def test_ungoverned_document_is_withheld_under_strict(self) -> None:
    self.write("docs/notes.md", "# 随手笔记\n\n" + SENTINEL + "\n")

    result = self.read("docs/notes.md", STRICT)

    self.assertEqual(READ.INSUFFICIENT_METADATA, result.verdict)
    self.assertIsNone(result.body)
    self.assertNotIn(SENTINEL, READ.render_read_result(result))

  def test_metadata_conflict_withholds_body(self) -> None:
    """自称现行却声明被取代——先修元数据，正文不作为权威返回。"""
    self.write("docs/design/new.md", self.doc())
    self.write(
        "docs/design/broken.md",
        self.doc(status="current", superseded_by="[new.md]", body=SENTINEL),
    )

    result = self.read("docs/design/broken.md")

    self.assertEqual(READ.METADATA_CONFLICT, result.verdict)
    self.assertIsNone(result.body)
    self.assertNotIn(SENTINEL, READ.render_read_result(result))

  def test_missing_fields_withhold_body(self) -> None:
    self.write(
        "docs/design/partial.md",
        "---\nstatus: current\n---\n\n" + SENTINEL + "\n",
    )

    result = self.read("docs/design/partial.md")

    self.assertEqual(READ.INSUFFICIENT_METADATA, result.verdict)
    self.assertNotIn(SENTINEL, READ.render_read_result(result))

  def test_missing_file_is_reported_not_crashed(self) -> None:
    result = self.read("docs/design/ghost.md")

    self.assertEqual(READ.INSUFFICIENT_METADATA, result.verdict)
    self.assertIn("文件不存在", " ".join(result.diagnostics))


class BoundaryRegressionTest(ReadTestBase):
  """守住四项「改了行为却没人守」的修复。

  独立验收用回退法证过：把下面每一项各自改回原样，全量测试仍然全绿——
  意味着它们能被无声打破，其中 `restrict_to_docs` 还是一条安全边界。
  根因是建守卫的动作只跟着「阻塞项」走，没跟着「所有行为改动」走。
  """

  def test_bom_prefixed_document_is_still_parsed_as_frontmatter(self) -> None:
    """带 BOM 的作废文档一样不能泄漏正文。

    BOM 让首行变成 `\\ufeff---`，若判定处不剥它，文档会被当成「没有
    frontmatter」而在 gradual 下原样放行——作废文档的正文就漏出去了。
    """
    self.write("docs/design/new.md", self.doc(supersedes="[old.md]"))
    body = self.doc(
        status="superseded",
        authority="historical-evidence",
        superseded_by="[new.md]",
        body=SENTINEL,
    )
    (self.root / "docs/design/old.md").write_bytes(
        ("﻿" + body).encode("utf-8")
    )

    result = self.read("docs/design/old.md")

    self.assertEqual(READ.SUPERSEDED, result.verdict)
    self.assertNotIn(SENTINEL, READ.render_read_result(result))

  def test_mcp_layer_refuses_paths_outside_the_docs_tree(self) -> None:
    """安全边界：给 agent 的接口不能变成不受限的任意文件读取器。"""
    outside = self.root / "secrets.env"
    outside.write_text("API_KEY=" + SENTINEL, encoding="utf-8")

    result = READ.read_document(
        outside, self.root, None, restrict_to_docs=True
    )

    self.assertIsNone(result.body)
    self.assertNotIn(SENTINEL, READ.render_read_result(result))

  def test_cli_layer_may_read_outside_the_docs_tree(self) -> None:
    """CLI 不设这条边界——否则连本仓 tests/fixtures 下的夹具都读不了。"""
    outside = self.root / "notes.md"
    outside.write_text("# 随手\n\n正文。\n", encoding="utf-8")

    result = READ.read_document(outside, self.root, None)

    self.assertEqual(READ.UNGOVERNED, result.verdict)
    self.assertIn("正文。", result.body)


class CanonIndexTest(ReadTestBase):

  def populate(self) -> None:
    self.write("docs/design/live.md", self.doc())
    self.write(
        "docs/design/old.md",
        self.doc(status="superseded", authority="historical-evidence",
                 superseded_by="[live.md]", body=SENTINEL),
    )
    self.write("docs/guides/start.md", "# 入门\n\n没有标签。\n")

  def test_index_is_one_line_per_document(self) -> None:
    self.populate()

    entries = build_index(self.root)
    rendered = render_index(entries)

    self.assertEqual(3, len(entries))
    self.assertEqual(3, len(rendered.splitlines()))

  def test_index_never_leaks_document_bodies(self) -> None:
    """A18 的实质：清单是标签的清单，不是正文的搬运。"""
    self.populate()

    self.assertNotIn(SENTINEL, render_index(build_index(self.root)))
    self.assertNotIn(
        SENTINEL, render_index(build_index(self.root), as_json=True)
    )

  def test_index_size_is_independent_of_body_length(self) -> None:
    """紧凑的本质：索引大小只与篇数有关，与正文多长无关。

    这比「小于全文的 10%」更能表达 protocol §7.5 的意图——后者在文档很短时
    会失真（三篇迷你文档的索引占比自然偏高），而这条断言在任何规模下都成立。
    """
    self.populate()
    before = len(render_index(build_index(self.root)).encode("utf-8"))

    for path in (self.root / "docs").rglob("*.md"):
      path.write_text(
          path.read_text(encoding="utf-8") + "补充说明。\n" * 500,
          encoding="utf-8",
      )
    after = len(render_index(build_index(self.root)).encode("utf-8"))

    self.assertEqual(before, after)

  def test_index_stays_far_smaller_than_a_realistic_corpus(self) -> None:
    """A18 的原始判据：真实体量下索引 < 全文的 10%。"""
    self.populate()
    for path in (self.root / "docs").rglob("*.md"):
      path.write_text(
          path.read_text(encoding="utf-8") + "章节正文。\n" * 200,
          encoding="utf-8",
      )
    corpus = sum(
        path.stat().st_size for path in (self.root / "docs").rglob("*.md")
    )

    size = len(render_index(build_index(self.root)).encode("utf-8"))

    self.assertLess(size, corpus * 0.10)

  def test_directory_filter(self) -> None:
    self.populate()

    entries = build_index(self.root, directory="design")

    self.assertEqual(
        ["docs/design/live.md", "docs/design/old.md"],
        [entry.path for entry in entries],
    )

  def test_current_only_filter(self) -> None:
    self.populate()

    entries = build_index(self.root, current_only=True)

    self.assertEqual(["docs/design/live.md"], [e.path for e in entries])

  def test_multiline_status_cannot_forge_extra_rows(self) -> None:
    """「一篇一行」是硬约束：字段值来自被审计文档，是不可信输入。

    status 写成含换行的 YAML 块标量时，原样拼进 TSV 会凭空多出几行，
    且伪造行与真条目长得一模一样，下游 agent 无从分辨。
    """
    self.write(
        "docs/design/inject.md",
        "---\nstatus: |\n  current\n  FORGED-LINE\tfake-status\tfake-authority\n"
        "applies_when: x\nnot_for: y\ncurrent_authority: contract-current\n"
        "supersedes: []\nsuperseded_by: []\nowner: z\n"
        "last_reviewed: 2026-07-27\n---\n\n# 注入\n",
    )
    self.write("docs/design/clean.md", self.doc())

    rendered = render_index(build_index(self.root))

    self.assertEqual(2, len(rendered.splitlines()))
    self.assertNotIn("\nFORGED-LINE", rendered)

  def test_directory_filter_rejects_traversal(self) -> None:
    """`--dir ..` 静默返回整棵树，看起来像「这个目录下就是这些」。"""
    self.populate()

    for escape in ("..", "../..", "design/../.."):
      with self.subTest(escape=escape):
        with self.assertRaises(IndexUnavailable):
          build_index(self.root, directory=escape)

  def test_directory_filter_rejects_missing_directory(self) -> None:
    """返回 0 行与「该目录确实没文档」无法区分，所以必须报错。"""
    self.populate()

    with self.assertRaises(IndexUnavailable):
      build_index(self.root, directory="nonexistent")

  def test_untagged_documents_are_listed_with_placeholders(self) -> None:
    """未治理文档也要出现在清单里——否则它们会成为看不见的盲区。"""
    self.populate()

    entries = {e.path: e for e in build_index(self.root)}

    self.assertEqual("-", entries["docs/guides/start.md"].status)


if __name__ == "__main__":
  unittest.main()
