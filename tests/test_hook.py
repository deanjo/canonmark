"""`canon hook`（Claude Code PreToolUse 闸机）的行为契约测试。

deny 只该发生在一条路径上：输入完好、目标确认是 docs 下的退休文档。
其余一切——现行文档、未贴标签、docs 外路径、非 Read 工具、坏输入——
都必须静默放行：fail-open 是这道闸机的第一契约（哲学同 V11），
「绝不误锁」比「多拦一篇」重要得多。
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from canonmark.hook import run_hook

VENV_CANON = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "canon"

# 退休文档正文里的哨兵串：只要它出现在输出中，就说明泄漏。
SENTINEL = "SENTINEL-固定重试三次-SENTINEL"


class HookTestBase(unittest.TestCase):

  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.root = Path(self.temp_dir.name).resolve()
    (self.root / "docs").mkdir()
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
    self.write(
        "docs/archived.md",
        self.doc(
            status="archive", authority="historical-evidence", body=SENTINEL
        ),
    )
    self.write("docs/notes.md", "# 随手笔记\n\n没有标签。\n")
    self.write("outside.md", self.doc(status="superseded"))

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

  def event(self, file_path: str, tool_name: str = "Read", **extra) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path, **extra},
        "cwd": str(self.root),
    }

  def hook(
      self,
      payload: dict | str,
      environ: dict | None = None,
      config_path: str | None = None,
  ) -> tuple[str, int]:
    """跑一次 run_hook，返回 (stdout, exit code)。

    environ 默认给空字典而不是继承 os.environ：本测试自己可能就跑在
    Claude Code 里，继承进来的 CLAUDE_PROJECT_DIR 会把解析基准劫走。
    """
    raw = (
        payload
        if isinstance(payload, str)
        else json.dumps(payload, ensure_ascii=False)
    )
    stdout = io.StringIO()
    code = run_hook(config_path, io.StringIO(raw), stdout, environ or {})
    return stdout.getvalue(), code

  def assert_allowed(self, payload: dict | str) -> None:
    output, code = self.hook(payload)
    self.assertEqual("", output)
    self.assertEqual(0, code)


class HookDenyTest(HookTestBase):

  def test_superseded_document_is_denied_with_replacement(self) -> None:
    output, code = self.hook(
        self.event(str(self.root / "docs/design/old.md"))
    )

    self.assertEqual(0, code)
    decision = json.loads(output)["hookSpecificOutput"]
    self.assertEqual(
        {"hookEventName", "permissionDecision", "permissionDecisionReason"},
        set(decision),
    )
    self.assertEqual("PreToolUse", decision["hookEventName"])
    self.assertEqual("deny", decision["permissionDecision"])
    self.assertIn(
        "docs/design/new.md", decision["permissionDecisionReason"]
    )
    self.assertNotIn(SENTINEL, output)

  def test_archived_document_is_denied(self) -> None:
    output, _ = self.hook(self.event(str(self.root / "docs/archived.md")))

    decision = json.loads(output)["hookSpecificOutput"]
    self.assertEqual("deny", decision["permissionDecision"])
    self.assertNotIn(SENTINEL, output)

  def test_relative_path_resolves_against_json_cwd(self) -> None:
    output, _ = self.hook(self.event("docs/design/old.md"))

    decision = json.loads(output)["hookSpecificOutput"]
    self.assertEqual("deny", decision["permissionDecision"])

  def test_pagination_arguments_do_not_bypass_the_gate(self) -> None:
    """带 offset/limit 的分页 Read 一样要拦——分页读的还是同一篇作废文档。"""
    output, _ = self.hook(
        self.event(
            str(self.root / "docs/design/old.md"), offset=10, limit=50
        )
    )

    decision = json.loads(output)["hookSpecificOutput"]
    self.assertEqual("deny", decision["permissionDecision"])

  def test_missing_config_file_falls_back_to_defaults_not_lockdown(
      self,
  ) -> None:
    """--config 指向不存在的文件：用内置默认继续判定，而不是锁死或崩溃。"""
    output, code = self.hook(
        self.event(str(self.root / "docs/design/old.md")),
        config_path=str(self.root / "no-such-config.toml"),
    )

    self.assertEqual(0, code)
    decision = json.loads(output)["hookSpecificOutput"]
    self.assertEqual("deny", decision["permissionDecision"])

  def test_claude_project_dir_beats_json_cwd(self) -> None:
    """解析基准优先级：CLAUDE_PROJECT_DIR > stdin JSON 的 cwd。"""
    other = self.root / "elsewhere"
    other_doc = other / "docs/design/old.md"
    other_doc.parent.mkdir(parents=True)
    other_doc.write_text(self.doc(), encoding="utf-8")
    payload = self.event("docs/design/old.md")
    payload["cwd"] = str(other)

    # 无环境变量：按 JSON cwd 解析到 elsewhere 的现行文档，放行。
    output, code = self.hook(payload)
    self.assertEqual("", output)
    self.assertEqual(0, code)

    # 有环境变量：解析基准被 CLAUDE_PROJECT_DIR 接管，命中退休文档，拦下。
    output, _ = self.hook(
        payload, environ={"CLAUDE_PROJECT_DIR": str(self.root)}
    )
    decision = json.loads(output)["hookSpecificOutput"]
    self.assertEqual("deny", decision["permissionDecision"])


class HookAllowTest(HookTestBase):
  """放行 = 不输出任何内容 + exit 0，把决定交回正常权限流。"""

  def test_current_document_is_allowed(self) -> None:
    self.assert_allowed(self.event(str(self.root / "docs/design/new.md")))

  def test_ungoverned_document_is_allowed(self) -> None:
    self.assert_allowed(self.event(str(self.root / "docs/notes.md")))

  def test_retired_document_outside_docs_root_is_allowed(self) -> None:
    self.assert_allowed(self.event(str(self.root / "outside.md")))

  def test_non_read_tool_is_allowed(self) -> None:
    self.assert_allowed(
        self.event(str(self.root / "docs/design/old.md"), tool_name="Write")
    )

  def test_bad_json_on_stdin_fails_open(self) -> None:
    self.assert_allowed("这不是 JSON{{{")

  def test_missing_file_is_allowed(self) -> None:
    self.assert_allowed(self.event(str(self.root / "docs/ghost.md")))


class HookExecutableTest(HookTestBase):

  def test_real_canon_hook_denies_superseded_document(self) -> None:
    """走一遍真实可执行文件，证明接线（entry point + stdin/stdout）是通的。"""
    if not VENV_CANON.is_file():
      self.skipTest(f"未找到 {VENV_CANON}")

    completed = subprocess.run(
        [str(VENV_CANON), "hook"],
        input=json.dumps(
            self.event(str(self.root / "docs/design/old.md")),
            ensure_ascii=False,
        ),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)},
    )

    self.assertEqual(0, completed.returncode)
    decision = json.loads(completed.stdout)["hookSpecificOutput"]
    self.assertEqual("deny", decision["permissionDecision"])
    self.assertNotIn(SENTINEL, completed.stdout)


if __name__ == "__main__":
  unittest.main()
