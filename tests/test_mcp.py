"""MCP server 的协议实现与接线话术测试。

除了跑通握手，这里还机检两条**设计约束**——它们此前只是文档里的规矩，
而这个项目的全部教训就是「写在文档里的规矩防不住」：

  1. 工具描述里不许出现「读文档前先跑 index」这类话术（protocol §7.5）。
     一旦出现，agent 每次都会先拉全库标签，正是早期被废止的那个设计。
  2. `canon init` 吐出的宿主指令必须是 §7.7 的正确版本。
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from canonmark import mcp as MCP
from canonmark.cli import HOST_INSTRUCTION, MCP_HELP
from canonmark.config import DEFAULT_CONFIG

SENTINEL = "SENTINEL-固定重试三次-SENTINEL"


class McpServerTest(unittest.TestCase):

  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.root = Path(self.temp_dir.name)
    design = self.root / "docs" / "design"
    design.mkdir(parents=True)
    (design / "new.md").write_text(
        "---\nstatus: current\napplies_when: 实现支付重试\n"
        "not_for: 对账流程\ncurrent_authority: contract-current\n"
        "supersedes: [old.md]\nsuperseded_by: []\nowner: pay\n"
        "last_reviewed: 2026-07-27\n---\n\n# 新设计\n\n熔断 + 死信队列。\n",
        encoding="utf-8",
    )
    (design / "old.md").write_text(
        "---\nstatus: superseded\napplies_when: 追溯历史设计\n"
        "not_for: 当前实现依据\ncurrent_authority: historical-evidence\n"
        "supersedes: []\nsuperseded_by: [new.md]\nowner: pay\n"
        "last_reviewed: 2026-01-01\n---\n\n# 旧设计\n\n" + SENTINEL + "\n",
        encoding="utf-8",
    )

  def tearDown(self) -> None:
    self.temp_dir.cleanup()

  def exchange(self, *messages: dict) -> list[dict]:
    """把若干消息喂给 server，收回响应。"""
    stdin = io.StringIO(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages)
    )
    stdout = io.StringIO()
    MCP.CanonMcpServer(self.root, DEFAULT_CONFIG, stdin, stdout).serve()
    return [
        json.loads(line) for line in stdout.getvalue().splitlines() if line
    ]

  def call(self, name: str, arguments: dict) -> str:
    responses = self.exchange(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    return responses[0]["result"]["content"][0]["text"]

  def test_initialize_handshake(self) -> None:
    responses = self.exchange(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
        }
    )

    result = responses[0]["result"]
    self.assertEqual("2025-06-18", result["protocolVersion"])
    self.assertEqual("canonmark", result["serverInfo"]["name"])
    self.assertIn("tools", result["capabilities"])

  def test_initialize_does_not_claim_unsupported_versions(self) -> None:
    """不回显客户端的任意版本——回显等于声称支持它。

    某些旧版规范允许 JSON-RPC 批量数组，本 server 不支持批量；声称支持却
    不支持，会让一个完全合规的客户端在第一个请求上翻车。
    """
    for requested in ("2024-11-05", "1999-01-01", 12345, None):
      with self.subTest(requested=requested):
        responses = self.exchange(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": requested},
            }
        )

        self.assertEqual(
            MCP.PROTOCOL_VERSION, responses[0]["result"]["protocolVersion"]
        )

  def test_notifications_get_no_response(self) -> None:
    """通知没有 id，回响应会破坏协议。"""
    responses = self.exchange({"jsonrpc": "2.0", "method": "notifications/initialized"})

    self.assertEqual([], responses)

  def test_tools_list_exposes_both_tools(self) -> None:
    responses = self.exchange(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )

    names = [tool["name"] for tool in responses[0]["result"]["tools"]]
    self.assertEqual(["canon_read", "canon_index"], names)

  def test_tool_call_withholds_superseded_body(self) -> None:
    """A17 在工具调用这一层同样成立——正文不进 agent 的上下文。"""
    text = self.call("canon_read", {"path": "docs/design/old.md"})

    self.assertNotIn(SENTINEL, text)
    self.assertIn("已作废", text)
    self.assertIn("docs/design/new.md", text)

  def test_tool_call_returns_current_body(self) -> None:
    text = self.call("canon_read", {"path": "docs/design/new.md"})

    self.assertIn("熔断 + 死信队列", text)

  def test_tool_call_accepts_absolute_path(self) -> None:
    absolute = str(self.root / "docs" / "design" / "old.md")

    text = self.call("canon_read", {"path": absolute})

    self.assertNotIn(SENTINEL, text)

  def test_index_tool_lists_documents(self) -> None:
    text = self.call("canon_index", {"current_only": True})

    self.assertIn("docs/design/new.md", text)
    self.assertNotIn("docs/design/old.md", text)

  def test_unknown_tool_is_a_protocol_error(self) -> None:
    responses = self.exchange(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "canon_delete_everything", "arguments": {}},
        }
    )

    self.assertIn("error", responses[0])

  def test_tool_error_is_reported_as_result_not_crash(self) -> None:
    responses = self.exchange(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "canon_read", "arguments": {}},
        }
    )

    self.assertTrue(responses[0]["result"]["isError"])

  def test_valid_json_that_is_not_an_object_does_not_kill_the_server(self) -> None:
    """比「畸形 JSON」更危险的一类：能解析、但不是对象。

    批量数组是旧版 MCP 规范的合法请求形态，裸标量也能通过 json.loads。
    此前 `handle()` 直接 `.get()`，任何这类行都会抛 AttributeError 打死进程，
    之后的请求静默丢失——而覆盖它的测试只测了不可解析的文本，给了虚假信心。
    """
    for payload in (
        '[{"jsonrpc":"2.0","id":9,"method":"ping"}]',
        '"hello"',
        "123",
        "null",
        "true",
    ):
      with self.subTest(payload=payload):
        stdin = io.StringIO(
            payload
            + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            + "\n"
        )
        stdout = io.StringIO()
        MCP.CanonMcpServer(self.root, DEFAULT_CONFIG, stdin, stdout).serve()

        responses = [
            json.loads(line) for line in stdout.getvalue().splitlines() if line
        ]
        self.assertIn("error", responses[0])
        # 关键：server 活着，后续请求照常处理。
        self.assertEqual(2, responses[1]["id"])
        self.assertIn("tools", responses[1]["result"])

  def test_malformed_json_does_not_kill_the_server(self) -> None:
    stdin = io.StringIO(
        "{ not json\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        + "\n"
    )
    stdout = io.StringIO()
    MCP.CanonMcpServer(self.root, DEFAULT_CONFIG, stdin, stdout).serve()

    responses = [
        json.loads(line) for line in stdout.getvalue().splitlines() if line
    ]
    self.assertIn("error", responses[0])
    self.assertEqual(2, responses[1]["id"])


class WiringPhrasingTest(unittest.TestCase):
  """把 §7.5 / §7.7 的措辞约束变成机器检查。"""

  def test_index_description_ends_with_the_canonical_prohibition(self) -> None:
    """早期设计曾把「每次先跑全库索引」当默认路径，已废止——话术不许复活它。

    强制**原样**出现而非「含某几个关键词」：独立验收用 5 组变异测过上一版的
    关键词黑名单，4 组静默放过（「工作流的第一步就执行 canon index」「建议先跑
    canon index」去掉一个空格即可绕开）。自然语言的等价改写挡不住，所以把措辞
    固定成常量，任何改写都会让这条红。
    """
    self.assertTrue(
        MCP.INDEX_DESCRIPTION.endswith(MCP.NOT_A_PREREQUISITE),
        "canon_index 的描述必须以 NOT_A_PREREQUISITE 原文结尾",
    )

  def test_no_prerequisite_phrasing_anywhere_in_the_wiring(self) -> None:
    """关键词黑名单：抓得住直白的说法，抓不住语义等价的改写。

    **这道检查的局限必须写明**——它是第二道网，不是保证。上一条（禁令原样固定）
    保证的是禁令**不被改写或删除**，但**挡不住增写**：验收实测，在禁令原样保留的
    前提下，前面加一句「开始任何任务前请务必先调用本工具」仍会静默放过。增写这条
    路只能靠人工审阅。这里把「先…canon index」的空格去掉再匹配，堵掉最省事的绕法。
    """
    haystacks = {
        "INDEX_DESCRIPTION": MCP.INDEX_DESCRIPTION,
        "READ_DESCRIPTION": MCP.READ_DESCRIPTION,
        "MCP_HELP": MCP_HELP,
        "HOST_INSTRUCTION": HOST_INSTRUCTION,
    }
    forbidden = (
        "先执行canonindex",
        "先跑canonindex",
        "先运行canonindex",
        "先调用canonindex",
        "第一步就执行canonindex",
        "第一步是canonindex",
    )
    for name, text in haystacks.items():
      squashed = "".join(text.split()).replace("_", "")
      for phrase in forbidden:
        with self.subTest(where=name, phrase=phrase):
          self.assertNotIn(phrase, squashed)

  def test_read_tool_description_tells_agents_to_replace_direct_reads(self) -> None:
    """工具描述本身就是接线话术：不说死「替代直接读文件」，agent 就会绕过它。"""
    self.assertIn("替代直接读文件", MCP.READ_DESCRIPTION)

  def test_host_instruction_matches_protocol_wording(self) -> None:
    self.assertIn("按目录 README 导航定位文档", HOST_INSTRUCTION)
    self.assertIn("使用 `canon_read`", HOST_INSTRUCTION)
    self.assertIn("不要直接读取文件", HOST_INSTRUCTION)
    self.assertIn(HOST_INSTRUCTION, MCP_HELP)

  def test_mcp_snippet_is_valid_json(self) -> None:
    from canonmark.cli import MCP_CONFIG_SNIPPET

    parsed = json.loads(MCP_CONFIG_SNIPPET)

    self.assertEqual(
        ["mcp"], parsed["mcpServers"]["canonmark"]["args"]
    )
    self.assertEqual("canon", parsed["mcpServers"]["canonmark"]["command"])


if __name__ == "__main__":
  unittest.main()
