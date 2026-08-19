"""`canon hook`：Claude Code PreToolUse 闸机——把内置 Read 也纳入权威契约。

`canon_read`（MCP）是给 agent 的正门，但正门旁边始终开着内置 Read 这扇侧门：
工具摆在工具面上，agent 仍可以不用（A19 实证）。本模块把契约装到侧门上——
agent 用内置 Read 读 docs 下的退休文档时，hook 输出 deny 与替代去处。
判定与文案复用 `canon read` 的同一逻辑源（``read_document`` /
``render_read_result``），不存在第二份可以各自漂移的规则。

**fail-open 铁律**（哲学同 V11）：闸机故障不得锁死全库。坏 JSON、缺字段、
编码错误、配置损坏……任何异常一律静默放行 exit 0。V11 不把「久未复核」判失败，
是因为全库突然变红时团队的第一反应是关掉整个门禁；hook 若在故障时拒绝读取，
用户的第一反应同样是删掉这个 hook。deny 因此只发生在一条路径上：
输入完好、目标确认是 docs 下的退休文档。

已知边界：只拦 Read 工具；`Bash` 里 `cat` 作废文档仍是现成的绕过路径，本模块不封。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Mapping, TextIO

from .config import DEFAULT_CONFIG, GovernanceConfig, load_config
from .read import read_document, render_read_result


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


def decide(
    payload: Mapping[str, object],
    config: GovernanceConfig,
    environ: Mapping[str, str],
) -> str | None:
  """对一次 PreToolUse 事件裁决：deny 返回待输出的 JSON，放行返回 None。"""
  if payload.get("tool_name") != "Read":
    return None
  tool_input = payload.get("tool_input")
  if not isinstance(tool_input, dict):
    return None
  file_path = tool_input.get("file_path")
  if not isinstance(file_path, str) or not file_path.strip():
    return None

  base = _resolve_base(payload, environ).resolve()
  target = Path(file_path)
  if not target.is_absolute():
    target = base / target
  # realpath 判定：符号链接以真实位置为准——docs 里的链接指向库外的照常
  # 放行（那不归本契约管），库外的链接指进 docs 的照常拦。
  target = target.resolve()
  docs_dir = (base / config.docs_root).resolve()
  if target.suffix.lower() != ".md":
    return None
  if target == docs_dir or not target.is_relative_to(docs_dir):
    return None
  if not target.is_file():
    return None

  result = read_document(target, base, config)
  # 只拦「退休态」——historical_statuses，与 canon read 扣正文的是同一集合。
  # current / background 有正文可放行；未贴标签、元数据残缺的也放行：
  # 闸机只拦确定已作废的文档，拿不准的交回正常权限流。
  if result.status not in config.historical_statuses:
    return None
  if not result.body_withheld:
    return None
  return json.dumps(
      {
          "hookSpecificOutput": {
              "hookEventName": "PreToolUse",
              "permissionDecision": "deny",
              "permissionDecisionReason": render_read_result(result),
          }
      },
      ensure_ascii=False,
  )


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
