"""让「工具对自己的描述」也受机器检查。

P5 期间同一类错误连犯四次：模块 docstring 说「五门」而实际六门、`pyproject.toml`
的依赖声明漏掉新门、验收矩阵里手抄的用例数被后续改动弄失真。每一次写的人都
确信这回是对的。结论是：**靠人记得同步自述文字，防不住。**

于是把两类自述接进测试——它们不是在测审计逻辑，而是在测「canonmark 关于
canonmark 的说法还算不算数」，正是这个项目对外主张的那件事。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from canonmark import audit as AUDIT

REPO_ROOT = Path(__file__).resolve().parents[1]


class SelfDescriptionTest(unittest.TestCase):
  """模块自述与代码事实必须一致。"""

  def test_module_docstring_lists_every_supported_gate(self) -> None:
    """docstring 里的门清单不得与 SUPPORTED_GATES 漂移。

    加一道门却忘了改开篇说明，正是 P5 犯过的错——一个检查「文档是否说实话」
    的工具，自己的第一行不知道自己有第六道门。
    """
    documented = set(re.findall(r"^  (V\d+)\s", AUDIT.__doc__, re.MULTILINE))

    self.assertEqual(
        set(AUDIT.SUPPORTED_GATES),
        documented,
        "audit.py 的模块 docstring 与 SUPPORTED_GATES 不一致；"
        "新增或删除 gate 时两处必须同步",
    )

  def test_cli_docstring_lists_every_subcommand(self) -> None:
    """守卫必须随自述面一起长大。

    P5 为「模块 docstring 说五门而实际六门」建了本文件的第一个守卫；P6 新增
    了 read/index/mcp 三个子命令，而 `cli.py` 的 docstring 只提 audit 与 init
    ——**同一个错误在隔壁文件原样复发，守卫却还是绿的，因为它只盯着 gate**。
    这条把守卫扩到子命令清单上。
    """
    from canonmark import cli

    parser = cli.build_parser()
    registered = set()
    for action in parser._subparsers._group_actions:  # noqa: SLF001
      registered.update(action.choices)
    documented = set(re.findall(r"^  ``canon (\w+)", cli.__doc__, re.MULTILINE))

    self.assertEqual(
        registered,
        documented,
        "cli.py 的模块 docstring 与实际注册的子命令不一致；"
        "新增或删除子命令时两处必须同步",
    )

  def test_every_supported_gate_is_registered_and_callable(self) -> None:
    self.assertEqual(set(AUDIT.SUPPORTED_GATES), set(AUDIT.AUDITORS))
    for gate in AUDIT.SUPPORTED_GATES:
      with self.subTest(gate=gate):
        self.assertTrue(callable(AUDIT.AUDITORS[gate]))

  def test_pyproject_dependency_note_matches_measured_behaviour(self) -> None:
    """pyproject 声称哪些门不需要 PyYAML，就必须真的不需要。

    这是给下游用户看的依赖承诺，写错会让人在没装 PyYAML 的环境里踩空。
    """
    note = "".join(
        line
        for line in (REPO_ROOT / "pyproject.toml")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.lstrip().startswith("#") and ("PyYAML" in line or "标准库" in line)
    )
    before, marker, after = note.partition("纯标准库")
    self.assertTrue(marker, "pyproject.toml 中未找到依赖划分说明")
    claimed_pure = set(re.findall(r"V\d+", before))
    claimed_yaml = set(re.findall(r"V\d+", after))
    self.assertEqual(
        set(AUDIT.SUPPORTED_GATES),
        claimed_pure | claimed_yaml,
        "依赖说明未覆盖全部 gate",
    )

    measured_pure = set()
    original = AUDIT.yaml
    try:
      AUDIT.yaml = None
      for gate in AUDIT.SUPPORTED_GATES:
        result = AUDIT.AUDITORS[gate](REPO_ROOT)
        if not any("PyYAML" in issue.message for issue in result.issues):
          measured_pure.add(gate)
    finally:
      AUDIT.yaml = original

    self.assertEqual(
        claimed_pure,
        measured_pure,
        f"pyproject.toml 声称 {sorted(claimed_pure)} 不需要 PyYAML，"
        f"实测不需要的是 {sorted(measured_pure)}",
    )


class NoYamlBehaviourTest(unittest.TestCase):
  """没有 PyYAML 时，每条读标签的路径都必须明说，不许静默降级。

  依赖声明此前只按 gate 划分，于是 P6 新增的三个子命令整个在守卫射程之外：
  `canon index` 会把全库标成「无标签」并 exit 0，`--current-only` 更会安静地
  回答「没有现行文档」。在这个项目里，「解析不出来就当没有」是最不该犯的错。
  """

  def setUp(self) -> None:
    self.original = AUDIT.yaml
    AUDIT.yaml = None

  def tearDown(self) -> None:
    AUDIT.yaml = self.original

  def test_index_refuses_instead_of_reporting_an_empty_library(self) -> None:
    from canonmark.index import IndexUnavailable, build_index

    with self.assertRaises(IndexUnavailable) as caught:
      build_index(REPO_ROOT)

    self.assertIn("PyYAML", str(caught.exception))

  def test_read_fails_closed(self) -> None:
    from canonmark.read import INSUFFICIENT_METADATA, read_document

    result = read_document(
        REPO_ROOT / "docs" / "roadmap.md", REPO_ROOT
    )

    self.assertEqual(INSUFFICIENT_METADATA, result.verdict)
    self.assertIsNone(result.body)


if __name__ == "__main__":
  unittest.main()
