"""双向 oracle：invalid fixture 该报的一处不漏，valid fixture 一处不报。

这两个 fixture 目录原先只有人工跑 CLI 才会碰到，不被任何测试引用——于是
P5 新增的对称性检查悄无声息地打破了它们，直到独立验收才被发现。把它们接进
pytest 就是为了让同一件事不再发生第二次：验收矩阵 A8 / A9 的通过条件，
从此由测试直接守住。
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from canonmark.audit import AUDITORS, SUPPORTED_GATES
from canonmark.config import load_config

FIXTURES = Path(__file__).parent / "fixtures"

# invalid fixture 里埋的 6 类问题。改动审计逻辑后若数量或内容变化，
# 说明双向 oracle 已经漂移，必须先确认是有意为之再更新此处。
EXPECTED_INVALID_ISSUES = (
    ("Bad_Dir", "目录名不是 kebab-case"),
    ("contract.md", "缺少顶部 YAML frontmatter"),
    ("guide.md", "相对链接目标不存在"),
    ("old-notes.md", "superseded_by 目标不存在"),
    ("reference", "缺少 README.md"),
    ("spec.md", "status 取值非法"),
)


class FixtureOracleTest(unittest.TestCase):
  """A8 / A9：两个 fixture 目录构成双向 oracle。"""

  def audit(self, name: str) -> tuple[list, list]:
    """按 fixture 自带配置跑全部 gate，返回 (问题, 提示)。"""
    directory = FIXTURES / name
    config = load_config(str(directory / "canonmark.toml"))
    # 与 cli.run_audit 用同一种方式改写 docs 根，避免测试和 CLI 静默分叉。
    config = replace(config, docs_root=directory.name)
    issues, notices = [], []
    for gate in SUPPORTED_GATES:
      result = AUDITORS[gate](directory.parent, config)
      issues.extend(result.issues)
      notices.extend(result.notices)
    return issues, notices

  def test_valid_fixture_reports_nothing(self) -> None:
    """A9：修好后的 fixture 必须一处不报，含提示也应为空。"""
    issues, notices = self.audit("valid")

    self.assertEqual([], [f"{i.path}:{i.line} {i.message}" for i in issues])
    self.assertEqual([], [f"{n.path}:{n.line} {n.message}" for n in notices])

  def test_invalid_fixture_reports_exactly_the_planted_issues(self) -> None:
    """A8：恰好报中 6 处埋雷，不多不少。"""
    issues, _ = self.audit("invalid")

    self.assertEqual(
        len(EXPECTED_INVALID_ISSUES),
        len(issues),
        f"埋雷数量漂移：{[f'{i.path} {i.message}' for i in issues]}",
    )
    for fragment, message_fragment in EXPECTED_INVALID_ISSUES:
      with self.subTest(fragment=fragment):
        self.assertTrue(
            any(
                fragment in issue.path and message_fragment in issue.message
                for issue in issues
            ),
            f"未报中埋雷 {fragment} / {message_fragment}",
        )


if __name__ == "__main__":
  unittest.main()
