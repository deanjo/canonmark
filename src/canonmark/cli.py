"""canonmark 命令行入口（``canon``）。

子命令（本表由 tests/test_contract.py 守住，不许与实际注册的 parser 漂移）：
  ``canon audit [PATH] [--config FILE] [--all | --gates V2,V4,...]``
      审计 PATH 指向的 docs 目录（省略则从当前目录向上发现仓库根 + config.docs_root）。
      任一 gate FAIL 退出 1，全过退出 0。
  ``canon read PATH [--config FILE]``
      按权威契约读取一篇文档：作废文档不返回正文，只给状态与替代目标。
      正文被扣下时退出 1，让脚本能察觉「这篇不能用」。
  ``canon index [PATH] [--dir SUBDIR] [--current-only] [--json]``
      列出 docs 下文档的权威标签，一篇一行。按需工具，不是读文档的必经路径。
  ``canon mcp [--config FILE]``
      以 MCP server 运行（stdio JSON-RPC），把 canon_read 送进 agent 的工具面。
  ``canon hook [--config FILE]``
      作为 Claude Code PreToolUse hook 运行（stdin 收事件 JSON）：内置 Read
      读 docs 下退休文档时输出 deny 与替代去处；其余情况一律静默放行 exit 0。
  ``canon init [DIR] [--force] [--print-mcp] [--print-hook]``
      在 DIR（默认当前目录）写一份 canonmark.toml 起步配置，并打印 MCP 接线片段。
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .audit import AUDITORS, SUPPORTED_GATES, discover_repo_root, print_result
from .config import load_config
from .hook import run_hook
from .index import IndexUnavailable, build_index, render_index
from .mcp import serve as serve_mcp
from .read import read_document, render_read_result


INIT_TEMPLATE = """\
# canonmark 治理配置。省略的字段都用内置默认值（= 通用治理模型）。
# 只需覆盖本项目差异化的部分。

# 采用模式：决定「尚未治理」的部分怎么处理。
#   gradual（默认）——没做的事不罚，做错的事才罚。没贴 frontmatter 的文档、
#     还没建的 README、既有的目录命名与坏链，一律只提示，不判失败；
#     已经贴了标签却写错的照旧判失败。存量项目装上不会当场变红。
#   strict —— 上述结构性缺失同样判失败。适合已完成治理的文档库。
adoption_mode = "gradual"

# docs 根目录名（相对仓库根）。
docs_root = "docs"

# V2 目录命名白名单（产品代号 / 元目录例外）。通用默认建议留空。
v2_path_exceptions = []

# V5 固定必备关键文档（相对 docs 根）：列在这里的文档「必须存在」，缺了就报错。
# 留空 = 不强制任何文档存在，只治理实际写了 frontmatter 的文档。
# 想要求某几篇权威文档常驻时再填，例如 ["roadmap.md", "acceptance.md"]。
required_key_documents = []
required_key_document_globs = []

# 触发治理的路径前缀（供 pre-commit / CI hook 使用）。
trigger_paths = ["docs/"]
"""


MCP_CONFIG_SNIPPET = """\
{
  "mcpServers": {
    "canonmark": {
      "command": "canon",
      "args": ["mcp"]
    }
  }
}"""

# §7.7 的正确版本。这段话只要求 agent 换一个工具，不要求它记住任何判定规则——
# 规则全部下沉到工具里。反面教材是「读 docs 前先执行 canon index」：那会把整库
# 标签灌进上下文，与按需加载的初衷直接冲突。
HOST_INSTRUCTION = (
    "按目录 README 导航定位文档；读取 docs 下任何文档时使用 `canon_read`，"
    "不要直接读取文件。"
)

MCP_HELP = f"""\
# 1) 把下面这段写进项目根的 .mcp.json（已有则合并 mcpServers 字段）

{MCP_CONFIG_SNIPPET}

# 2) 把下面这句写进宿主指令文件（CLAUDE.md / AGENTS.md 等）

{HOST_INSTRUCTION}

# 之后 agent 每次启动都会看到 canon_read 出现在它的工具列表里——
# 能力出现在工具面，而不是只躺在文档约定里。
"""


HOOK_CONFIG_SNIPPET = """\
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "canon hook --config \\"$CLAUDE_PROJECT_DIR/canonmark.toml\\""
          }
        ]
      }
    ]
  }
}"""

HOOK_HELP = f"""\
# 把下面这段写进项目的 .claude/settings.json（已有则合并 hooks 字段）

{HOOK_CONFIG_SNIPPET}

# hook 由 Claude Code 直接执行，`canon` 须在它的 PATH 上；装在 venv 里时把
# command 里的 canon 换成绝对形式："$CLAUDE_PROJECT_DIR/.venv/bin/canon" hook ...

# 之后 agent 用内置 Read 读 docs 下退休文档时会被拒绝并收到替代去处；
# hook 自身故障一律放行（fail-open），不会锁死正常读取。
"""


def parse_gate_list(raw: str) -> list[str]:
  """解析逗号分隔 gate，保持用户顺序并去重。"""
  gates: list[str] = []
  for item in raw.split(","):
    gate = item.strip().upper()
    if not gate:
      continue
    if gate not in SUPPORTED_GATES:
      supported = ", ".join(SUPPORTED_GATES)
      raise argparse.ArgumentTypeError(
          f"不支持 gate {gate!r}；可选值：{supported}"
      )
    if gate not in gates:
      gates.append(gate)
  if not gates:
    raise argparse.ArgumentTypeError("--gates 至少指定一个 gate")
  return gates


def build_parser() -> argparse.ArgumentParser:
  """构建命令行参数。"""
  parser = argparse.ArgumentParser(
      prog="canon",
      description="给 docs/ 一个可机检的权威契约；逐 gate 输出 PASS/FAIL。",
  )
  subparsers = parser.add_subparsers(dest="command")

  audit = subparsers.add_parser(
      "audit",
      help="审计一个 docs 目录的治理 gate",
      description=(
          "审计 PATH 指向的 docs 目录（省略则自动发现仓库根 + config.docs_root）；"
          "任一 gate FAIL 退出 1。"
      ),
  )
  audit.add_argument(
      "path",
      nargs="?",
      help="要审计的 docs 目录；省略则从当前目录向上发现仓库根",
  )
  audit.add_argument(
      "--config",
      metavar="FILE",
      help="治理配置文件（YAML 或 TOML）；省略则使用内置默认值",
  )
  selection = audit.add_mutually_exclusive_group()
  selection.add_argument(
      "--gates",
      type=parse_gate_list,
      metavar="V2,V4,...",
      help="执行指定 gate，可选 V2,V4,V5,V9,V10,V11,V12,V13",
  )
  selection.add_argument(
      "--all",
      action="store_true",
      help="执行全部 gate（缺省行为）：V2,V4,V5,V9,V10,V11,V12,V13",
  )

  read = subparsers.add_parser(
      "read",
      help="按权威契约读取一篇文档（作废文档不返回正文）",
      description=(
          "读 docs 下任何文档时用它替代直接打开文件：作废文档只返回状态与"
          "替代目标，正文不进入你的上下文；现行文档连同适用场景一并给出。"
      ),
  )
  read.add_argument("path", help="要读取的文档路径")
  read.add_argument(
      "--config",
      metavar="FILE",
      help="治理配置文件（YAML 或 TOML）；省略则使用内置默认值",
  )

  index = subparsers.add_parser(
      "index",
      help="列出 docs 下文档的权威标签（按需工具，不要每次读文档前跑）",
      description=(
          "跨目录检索、体检与 CI 报告用的全局清单。**不要**把它写进"
          "「读文档前先执行」的接线指引——那会污染上下文，见 protocol §7.5。"
      ),
  )
  index.add_argument(
      "path",
      nargs="?",
      help="docs 目录；省略则从当前目录向上发现仓库根",
  )
  index.add_argument(
      "--config",
      metavar="FILE",
      help="治理配置文件（YAML 或 TOML）；省略则使用内置默认值",
  )
  index.add_argument("--dir", metavar="SUBDIR", help="只列该子目录下的文档")
  index.add_argument(
      "--current-only", action="store_true", help="只列 status=current 的文档"
  )
  index.add_argument("--json", action="store_true", help="输出机器可读的 JSON")

  mcp = subparsers.add_parser(
      "mcp",
      help="以 MCP server 运行（stdio），把 canon_read 送进 agent 的工具面",
      description=(
          "供 MCP 客户端（Claude Code 等）以子进程方式启动；不是给人直接跑的。"
          "接线片段由 `canon init` 生成。"
      ),
  )
  mcp.add_argument(
      "--config",
      metavar="FILE",
      help="治理配置文件（YAML 或 TOML）；省略则使用内置默认值",
  )

  hook = subparsers.add_parser(
      "hook",
      help="作为 Claude Code PreToolUse hook 运行（stdin 收事件 JSON）",
      description=(
          "供 Claude Code 在每次内置 Read 前调用：目标是 docs 下的退休文档时"
          "输出 deny 与替代去处；其余情况（含 hook 自身故障）一律静默放行，"
          "exit 0。接线片段由 `canon init --print-hook` 生成。"
      ),
  )
  hook.add_argument(
      "--config",
      metavar="FILE",
      help="治理配置文件（YAML 或 TOML）；缺失或无法读取时用内置默认值",
  )

  init = subparsers.add_parser(
      "init",
      help="生成一份 canonmark.toml 起步配置",
  )
  init.add_argument(
      "--print-mcp",
      action="store_true",
      help="只打印 MCP 接线片段与宿主指令话术，不写任何文件",
  )
  init.add_argument(
      "--print-hook",
      action="store_true",
      help="只打印 PreToolUse hook 接线片段，不写任何文件",
  )
  init.add_argument(
      "directory",
      nargs="?",
      default=".",
      help="写入目录，默认当前目录",
  )
  init.add_argument(
      "--force",
      action="store_true",
      help="已存在时覆盖",
  )
  return parser


def run_audit(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
  """执行 audit 子命令。"""
  try:
    config = load_config(args.config)
  except (FileNotFoundError, RuntimeError, ValueError) as error:
    parser.error(str(error))

  if args.path:
    docs_path = Path(args.path).expanduser().resolve()
    if not docs_path.is_dir():
      parser.error(f"要审计的 docs 目录不存在：{docs_path}")
    root = docs_path.parent
    # 让 root/docs_root 精确等于用户指向的目录：以其目录名作为本次的 docs 根。
    config = replace(config, docs_root=docs_path.name)
  else:
    try:
      root = discover_repo_root(config)
    except FileNotFoundError as error:
      parser.error(str(error))

  gates = args.gates if args.gates else SUPPORTED_GATES
  failed = False
  for gate in gates:
    result = AUDITORS[gate](root, config)
    print_result(result)
    failed = failed or bool(result.issues)
  return 1 if failed else 0


def run_read(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
  """执行 read 子命令：按权威契约交付（或拒绝交付）正文。"""
  try:
    config = load_config(args.config)
  except (FileNotFoundError, RuntimeError, ValueError) as error:
    parser.error(str(error))

  target = Path(args.path).expanduser().resolve()
  # 从**目标文件**向上找 docs 根，而不是从当前工作目录——否则在 A 项目里
  # 读 B 项目的文档时，会拿 A 的 docs 根去解析 B 的替代目标，把存在的目标
  # 判成「越界」。
  root = None
  for parent in target.parents:
    if parent.name == config.docs_root:
      root = parent.parent
      break
  if root is None:
    try:
      candidate = discover_repo_root(config)
      # 只有当目标确实落在该仓库的 docs 树内时才认它当 root；否则用文件
      # 自身所在目录，让 `canon read` 也能读仓库外/非 docs 命名的文档。
      docs_dir = (candidate / config.docs_root).resolve()
      root = candidate if target.is_relative_to(docs_dir) else target.parent
    except FileNotFoundError:
      root = target.parent

  result = read_document(target, root, config)
  print(render_read_result(result))
  # 正文被扣下时以非零退出，让脚本能察觉「这篇不能用」。
  return 1 if result.body_withheld else 0


def run_index(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
  """执行 index 子命令。"""
  try:
    config = load_config(args.config)
  except (FileNotFoundError, RuntimeError, ValueError) as error:
    parser.error(str(error))

  if args.path:
    docs_path = Path(args.path).expanduser().resolve()
    if not docs_path.is_dir():
      parser.error(f"目录不存在：{docs_path}")
    root = docs_path.parent
    config = replace(config, docs_root=docs_path.name)
  else:
    try:
      root = discover_repo_root(config)
    except FileNotFoundError as error:
      parser.error(str(error))

  try:
    entries = build_index(
        root, config, directory=args.dir, current_only=args.current_only
    )
  except IndexUnavailable as error:
    parser.error(str(error))
  output = render_index(entries, as_json=args.json)
  if output:
    print(output)
  return 0


def run_init(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
  """执行 init 子命令：写起步配置，并给出 MCP 接线指引。"""
  if args.print_mcp or args.print_hook:
    if args.print_mcp:
      print(MCP_HELP, end="")
    if args.print_hook:
      print(HOOK_HELP, end="")
    return 0

  target_dir = Path(args.directory).expanduser().resolve()
  if not target_dir.is_dir():
    parser.error(f"目标目录不存在：{target_dir}")
  target = target_dir / "canonmark.toml"
  if target.exists() and not args.force:
    parser.error(f"{target} 已存在；加 --force 覆盖")
  target.write_text(INIT_TEMPLATE, encoding="utf-8")
  print(f"已写入 {target}")
  print()
  print("下一步：把 canon_read 接进 agent 的工具面（`canon init --print-mcp` 可再看一次）")
  print()
  print(MCP_HELP, end="")
  return 0


def main(argv: Sequence[str] | None = None) -> int:
  """CLI 入口。"""
  parser = build_parser()
  args = parser.parse_args(argv)
  if args.command == "audit":
    return run_audit(args, parser)
  if args.command == "read":
    return run_read(args, parser)
  if args.command == "index":
    return run_index(args, parser)
  if args.command == "mcp":
    return serve_mcp(args.config)
  if args.command == "hook":
    return run_hook(args.config)
  if args.command == "init":
    return run_init(args, parser)
  parser.print_help()
  return 2


if __name__ == "__main__":
  raise SystemExit(main())
