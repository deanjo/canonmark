"""最小 MCP server：把 canon_read / canon_index 送进 agent 的工具面。

为什么这一层不可省（protocol §7.3、§7.7）：写在文档里的约定，agent 得先读到
那篇文档才知道；注册进工具面的能力，它睁眼就看见。T14 的原话是「让能力出现在
消费者工具面，而非仅存在于文档约定」。

为什么手写而不用官方 SDK：canonmark 的承诺是 ``pip install`` 后纯标准库即可跑
（见 pyproject 的依赖说明）。MCP 的 stdio 传输就是逐行 JSON-RPC 2.0，自己实现
不到两百行，换取的是不把 pydantic 那一串依赖压给每个使用者。

协议实现范围：``initialize`` / ``tools/list`` / ``tools/call`` 三个方法，外加
``notifications/*`` 通知（不回响应）。够跑通工具调用，不实现 resources/prompts。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, TextIO

from .audit import discover_repo_root
from .config import GovernanceConfig, load_config
from .index import build_index, render_index
from .read import read_document, render_read_result

# 我们实现的协议版本。**不回显客户端的任意版本**：回显等于声称支持它，
# 而某些旧版规范允许 JSON-RPC 批量数组，本 server 不支持批量。声称支持却
# 不支持，会让一个完全合规的客户端在第一个请求上翻车。
PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = frozenset({PROTOCOL_VERSION})
SERVER_NAME = "canonmark"

# 工具描述就是接线话术本身（§7.7）：agent 靠它决定用不用。措辞必须把
# 「替代直接读文件」说死，而且绝不能把 canon_index 写成必经路径。
READ_DESCRIPTION = (
    "读取 docs/ 下任何文档时使用本工具替代直接读文件。它按文档头部的权威标签"
    "过滤：已作废的文档不会返回正文，只告诉你该改读哪一篇；现行文档连同它的"
    "适用/不适用场景一并给出。这样你不会照着一份三个月前就被取代的设计写代码。"
)
# 这句禁令是 protocol §7.5 第三条硬约束的落地，**必须原样出现在描述末尾**，
# 由测试守住。为什么强制原样而不允许等价改写：自然语言的等价改写无法被可靠
# 机检——实测「工作流的第一步就执行 canon index」这类说法能绕过任何合理的
# 关键词黑名单。统一措辞是让这条约束可机检的前提。
NOT_A_PREREQUISITE = (
    "不要在每次读文档前调用它——定位文档的常规路径是逐层读目录 README。"
)

INDEX_DESCRIPTION = (
    "列出 docs/ 下文档的权威标签（路径 + status + 权威角色），一篇一行。"
    "按需使用：跨目录检索、体检、找某类文档时才调用。" + NOT_A_PREREQUISITE
)

TOOLS: list[dict[str, Any]] = [
    {
        "name": "canon_read",
        "description": READ_DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文档路径（相对仓库根或绝对路径）",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "canon_index",
        "description": INDEX_DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {
                "dir": {
                    "type": "string",
                    "description": "只列该子目录（相对 docs 根）",
                },
                "current_only": {
                    "type": "boolean",
                    "description": "只列 status=current 的文档",
                },
            },
        },
    },
]


class CanonMcpServer:
  """stdio 上的 JSON-RPC 2.0 循环。"""

  def __init__(
      self,
      root: Path,
      config: GovernanceConfig,
      stdin: TextIO | None = None,
      stdout: TextIO | None = None,
  ) -> None:
    self.root = root
    self.config = config
    self.stdin = stdin if stdin is not None else sys.stdin
    self.stdout = stdout if stdout is not None else sys.stdout

  # ---- 工具实现 --------------------------------------------------------
  def call_read(self, arguments: dict[str, Any]) -> str:
    raw = str(arguments.get("path", "")).strip()
    if not raw:
      raise ValueError("缺少参数 path")
    target = Path(raw)
    if not target.is_absolute():
      target = self.root / target
    # restrict_to_docs=True：这是给 agent 的接口，必须钉在受治理的 docs 树内。
    return render_read_result(
        read_document(
            target.resolve(), self.root, self.config, restrict_to_docs=True
        )
    )

  def call_index(self, arguments: dict[str, Any]) -> str:
    entries = build_index(
        self.root,
        self.config,
        directory=arguments.get("dir") or None,
        current_only=bool(arguments.get("current_only")),
    )
    return render_index(entries) or "(docs 下没有 Markdown 文档)"

  @property
  def handlers(self) -> dict[str, Callable[[dict[str, Any]], str]]:
    return {"canon_read": self.call_read, "canon_index": self.call_index}

  # ---- JSON-RPC ---------------------------------------------------------
  def handle(self, message: Any) -> dict[str, Any] | None:
    """处理一条消息；返回 None 表示这是通知，不该回响应。

    ``message`` 刻意不标注为 dict：**任何**能被 json.loads 解析的东西都可能
    到达这里——数组（旧版规范的批量请求）、裸标量、null。假定它是对象会让
    server 在一行合法 JSON 上崩掉，之后的所有请求静默丢失。
    """
    if not isinstance(message, dict):
      kind = "批量数组" if isinstance(message, list) else type(message).__name__
      return self._error(
          None, -32600, f"JSON-RPC 消息必须是单个对象，收到 {kind}（不支持批量）"
      )

    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
      return None  # 通知（含 notifications/initialized），静默接受

    if method == "initialize":
      params = message.get("params") or {}
      requested = params.get("protocolVersion")
      # 只认自己实现的版本；其余一律回自己的，让客户端自行决定要不要继续。
      negotiated = (
          requested
          if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS
          else PROTOCOL_VERSION
      )
      return self._ok(
          request_id,
          {
              "protocolVersion": negotiated,
              "capabilities": {"tools": {}},
              "serverInfo": {"name": SERVER_NAME, "version": _version()},
          },
      )

    if method == "tools/list":
      return self._ok(request_id, {"tools": TOOLS})

    if method == "tools/call":
      params = message.get("params") or {}
      name = params.get("name")
      handler = self.handlers.get(name)
      if handler is None:
        return self._error(request_id, -32602, f"未知工具：{name}")
      try:
        text = handler(params.get("arguments") or {})
      except Exception as error:  # 工具级错误按 MCP 约定放进结果，不是协议错误
        return self._ok(
            request_id,
            {
                "content": [{"type": "text", "text": f"canon 工具出错：{error}"}],
                "isError": True,
            },
        )
      return self._ok(
          request_id, {"content": [{"type": "text", "text": text}]}
      )

    if method == "ping":
      return self._ok(request_id, {})

    return self._error(request_id, -32601, f"未实现的方法：{method}")

  def serve(self) -> int:
    """读一行处理一行，直到 stdin 关闭。"""
    for line in self.stdin:
      line = line.strip()
      if not line:
        continue
      try:
        message = json.loads(line)
      except json.JSONDecodeError as error:
        self._write(self._error(None, -32700, f"JSON 解析失败：{error}"))
        continue
      response = self.handle(message)
      if response is not None:
        self._write(response)
    return 0

  # ---- 输出 -------------------------------------------------------------
  def _write(self, payload: dict[str, Any]) -> None:
    self.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    self.stdout.flush()

  @staticmethod
  def _ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}

  @staticmethod
  def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _version() -> str:
  from . import __version__

  return __version__


def serve(config_path: str | None = None) -> int:
  """`canon mcp` 的入口。"""
  try:
    config = load_config(config_path)
  except (FileNotFoundError, RuntimeError, ValueError) as error:
    # 与其余子命令一致：配置错误给一行人话，而不是把 traceback 甩给
    # MCP 客户端的日志（那边通常只显示「server 启动失败」）。
    sys.stderr.write(f"canon mcp: 配置读取失败：{error}\n")
    return 2
  try:
    root = discover_repo_root(config)
  except FileNotFoundError:
    root = Path.cwd()
  return CanonMcpServer(root, config).serve()
