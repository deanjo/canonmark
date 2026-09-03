"""`canon hook`：Claude Code PreToolUse 闸机——把内置 Read 与 Bash 读取也纳入权威契约。

`canon_read`（MCP）是给 agent 的正门，但正门旁边始终开着内置 Read 这扇侧门：
工具摆在工具面上，agent 仍可以不用（A19 实证）。本模块把契约装到侧门上——
agent 用内置 Read 读 docs 下的退休文档时，hook 输出 deny 与替代去处。
判定与文案复用 `canon read` 的同一逻辑源（``read_document`` /
``render_read_result``），不存在第二份可以各自漂移的规则。

Bash 是第二扇侧门（2026-09-03 起纳入）：auto 模式下 agent 读文件默认走 Bash 的
cat / sed / head，只拦 Read 形同虚设。本模块把 Bash 命令切成管道 / 串联的段，
只有段首动词落在 ``READ_VERBS`` 里、且点名了 docs 下的退休文档时才拦；
通配符先展开再判定。

**fail-open 铁律**（哲学同 V11）：闸机故障不得锁死全库。坏 JSON、缺字段、
编码错误、配置损坏、引号不配对……任何异常一律静默放行 exit 0。V11 不把「久未复核」
判失败，是因为全库突然变红时团队的第一反应是关掉整个门禁；hook 若在故障时拒绝读取，
用户的第一反应同样是删掉这个 hook。deny 因此只发生在一条路径上：
输入完好、目标确认是 docs 下的退休文档。

已知边界：Bash 只拦 ``READ_VERBS`` 点名退休文档；python / perl / xxd 等其他读取形态、
`cd` 之后的相对路径漂移不封。具名证据需要时走 `canon read --evidence <path>`，
拒绝文案里直接给出可运行的命令。
"""

from __future__ import annotations

import glob
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Mapping, TextIO

from .config import DEFAULT_CONFIG, GovernanceConfig, load_config
from .read import ReadResult, read_document, render_read_result

# Bash 里算「读取」的动词：只有它们点名退休文档时才拦。git / mv / rm / wc / ls /
# canon 等一律不管——误锁一次合法操作的代价，比漏拦一次高（fail-open 铁律）。
READ_VERBS = frozenset(
    {
        "cat", "head", "tail", "less", "more", "bat", "tac", "nl", "sed",
        "awk", "grep", "egrep", "fgrep", "rg", "cut", "strings",
    }
)
# 段首要跳过的包装命令：它们之后才是真正的动词。
COMMAND_WRAPPERS = frozenset({"sudo", "command", "exec", "nohup", "time"})
# shlex punctuation_chars 模式下，管道 / 串联分隔符与重定向各自成串出现。
SEPARATOR_CHARS = frozenset("|&;()")
REDIRECT_CHARS = frozenset("<>")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
GLOB_CHARS = ("*", "?", "[")


def _resolve_base(
    payload: Mapping[str, object], environ: Mapping[str, str]
) -> Path:
  """解析基准目录：CLAUDE_PROJECT_DIR > stdin JSON 的 cwd > 进程 cwd。

  相对 file_path 与 docs 根都以它为基准——两者必须同源，否则「这条路径
  落在 docs 下吗」这个问题本身就没有稳定答案。
  """
  for candidate in (environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd")):
    if isinstance(candidate, str) and candidate.strip():
      return Path(candidate)
  return Path.cwd()


def _docs_target(raw: str, base: Path, docs_dir: Path) -> Path | None:
  """把一个路径字符串解析成 docs 根内的现存 .md 文件；不是就返回 None。"""
  target = Path(raw)
  if not target.is_absolute():
    target = base / target
  # realpath 判定：符号链接以真实位置为准——docs 里的链接指向库外的照常
  # 放行（那不归本契约管），库外的链接指进 docs 的照常拦。
  target = target.resolve()
  if target.suffix.lower() != ".md":
    return None
  if target == docs_dir or not target.is_relative_to(docs_dir):
    return None
  if not target.is_file():
    return None
  return target


def _segments(command: str) -> list[list[str]]:
  """按管道 / 串联把命令切段；引号不配对等解析失败抛 ValueError，交上层放行。"""
  lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
  lexer.whitespace_split = True
  segments: list[list[str]] = [[]]
  skip_next = False
  for token in lexer:
    if skip_next:
      skip_next = False
      continue
    characters = set(token)
    if token and characters <= SEPARATOR_CHARS:
      segments.append([])
      continue
    if token and characters & REDIRECT_CHARS and characters <= (
        REDIRECT_CHARS | {"&"}
    ):
      # `>` 后面的是输出目标不是读取对象，跳过它；`<` 后面的才是读取对象。
      skip_next = ">" in token
      continue
    segments[-1].append(token)
  return [segment for segment in segments if segment]


def _verb(segment: list[str]) -> tuple[str, list[str]]:
  """跳过环境变量赋值与包装命令，返回 (动词的 basename, 其余参数)。"""
  index = 0
  while index < len(segment):
    token = segment[index]
    if ENV_ASSIGNMENT.match(token) or os.path.basename(token) in COMMAND_WRAPPERS:
      index += 1
      continue
    break
  if index >= len(segment):
    return "", []
  return os.path.basename(segment[index]), segment[index + 1 :]


def _sed_edits_in_place(arguments: list[str]) -> bool:
  """`sed -i` / `--in-place` 是写入不是读取，放行。"""
  for token in arguments:
    if token == "--in-place" or token.startswith("--in-place="):
      return True
    if token.startswith("-") and not token.startswith("--") and "i" in token[1:]:
      return True
  return False


def _expand(token: str, base: Path) -> list[str]:
  """通配符先按基准目录展开，`cat docs/archive/*.md` 才躲不过判定。"""
  if not any(char in token for char in GLOB_CHARS):
    return [token]
  pattern = token if os.path.isabs(token) else str(base / token)
  return sorted(glob.glob(pattern))


def _bash_targets(command: str, base: Path, docs_dir: Path) -> list[Path]:
  """列出命令里被读取动词点名的、docs 根内的现存 .md 文件（去重保序）。"""
  try:
    segments = _segments(command)
  except ValueError:
    return []
  targets: list[Path] = []
  for segment in segments:
    verb, arguments = _verb(segment)
    if verb not in READ_VERBS:
      continue
    if verb == "sed" and _sed_edits_in_place(arguments):
      continue
    for token in arguments:
      if token.startswith("-") or not token.lower().endswith(".md"):
        continue
      for candidate in _expand(token, base):
        target = _docs_target(candidate, base, docs_dir)
        if target is not None and target not in targets:
          targets.append(target)
  return targets


def _canon_executable() -> str:
  """拒绝文案里给出的命令头：优先本次被调用的绝对路径——canon 常常不在 PATH 上。"""
  argv0 = sys.argv[0] if sys.argv else ""
  if argv0 and os.path.isabs(argv0):
    if os.path.basename(argv0) == "canon":
      return argv0
    if argv0.endswith(".py"):
      return f"{sys.executable} -m canonmark.cli"
  return "canon"


def _deny(result: ReadResult, target: Path, base: Path) -> str:
  """拒绝：复用 canon read 的文案，再给出具名证据通道的可运行命令。"""
  try:
    shown: Path | str = target.relative_to(base)
  except ValueError:
    shown = target
  reason = (
      f"{render_read_result(result)}\n"
      f"具名证据需要时：{_canon_executable()} read --evidence {shown}"
  )
  return json.dumps(
      {
          "hookSpecificOutput": {
              "hookEventName": "PreToolUse",
              "permissionDecision": "deny",
              "permissionDecisionReason": reason,
          }
      },
      ensure_ascii=False,
  )


def decide(
    payload: Mapping[str, object],
    config: GovernanceConfig,
    environ: Mapping[str, str],
) -> str | None:
  """对一次 PreToolUse 事件裁决：deny 返回待输出的 JSON，放行返回 None。"""
  tool_name = payload.get("tool_name")
  tool_input = payload.get("tool_input")
  if tool_name not in ("Read", "Bash") or not isinstance(tool_input, dict):
    return None

  base = _resolve_base(payload, environ).resolve()
  docs_dir = (base / config.docs_root).resolve()
  if tool_name == "Read":
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
      return None
    target = _docs_target(file_path, base, docs_dir)
    targets = [] if target is None else [target]
  else:
    command = tool_input.get("command")
    # 快速退出：连 .md 都没提到的命令，不值得起一次 shlex。
    if not isinstance(command, str) or ".md" not in command.lower():
      return None
    targets = _bash_targets(command, base, docs_dir)

  for target in targets:
    result = read_document(target, base, config)
    # 只拦「退休态」——historical_statuses，与 canon read 扣正文的是同一集合。
    # current / background 有正文可放行；未贴标签、元数据残缺的也放行：
    # 闸机只拦确定已作废的文档，拿不准的交回正常权限流。
    if result.status not in config.historical_statuses:
      continue
    if not result.body_withheld:
      continue
    return _deny(result, target, base)
  return None


def run_hook(
    config_path: str | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
  """`canon hook` 入口：读 stdin 事件、判定、必要时输出 deny；永远 exit 0。"""
  try:
    try:
      config = load_config(config_path)
    except Exception:
      # 配置缺失或损坏：退回内置默认（docs_root="docs"），不因此锁门。
      config = DEFAULT_CONFIG
    payload = json.loads((stdin or sys.stdin).read())
    if not isinstance(payload, dict):
      return 0
    verdict = decide(
        payload, config, os.environ if environ is None else environ
    )
    if verdict is not None:
      print(verdict, file=stdout or sys.stdout)
  except Exception:
    # fail-open 铁律：闸机故障不得锁死全库（见模块 docstring）。
    pass
  return 0
