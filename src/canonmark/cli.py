"""canonmark 命令行入口（``canon``）。

子命令：
  ``canon audit [PATH] [--config FILE] [--all | --gates V2,V4,...]``
      审计 PATH 指向的 docs 目录（省略则从当前目录向上发现仓库根 + config.docs_root）。
      任一 gate FAIL 退出 1，全过退出 0。
  ``canon init [DIR] [--force]``
      在 DIR（默认当前目录）写一份 canonmark.toml 起步配置。
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .audit import AUDITORS, SUPPORTED_GATES, discover_repo_root, print_result
from .config import load_config


INIT_TEMPLATE = """\
# canonmark 治理配置。省略的字段都用内置默认值（= 通用治理模型）。
# 只需覆盖本项目差异化的部分。

# docs 根目录名（相对仓库根）。
docs_root = "docs"

# V2 目录命名白名单（产品代号 / 元目录例外）。通用默认建议留空。
v2_path_exceptions = []

# V5 固定必备关键文档（相对 docs 根）。改成你项目里实际存在的权威文档。
required_key_documents = ["roadmap.md", "acceptance.md"]
required_key_document_globs = []

# 触发治理的路径前缀（供 pre-commit / CI hook 使用）。
trigger_paths = ["docs/"]
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
      help="执行指定 gate，可选 V2,V4,V5,V9,V10",
  )
  selection.add_argument(
      "--all",
      action="store_true",
      help="执行全部 gate（缺省行为）：V2,V4,V5,V9,V10",
  )

  init = subparsers.add_parser(
      "init",
      help="生成一份 canonmark.toml 起步配置",
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


def run_init(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
  """执行 init 子命令：写起步配置。"""
  target_dir = Path(args.directory).expanduser().resolve()
  if not target_dir.is_dir():
    parser.error(f"目标目录不存在：{target_dir}")
  target = target_dir / "canonmark.toml"
  if target.exists() and not args.force:
    parser.error(f"{target} 已存在；加 --force 覆盖")
  target.write_text(INIT_TEMPLATE, encoding="utf-8")
  print(f"已写入 {target}")
  return 0


def main(argv: Sequence[str] | None = None) -> int:
  """CLI 入口。"""
  parser = build_parser()
  args = parser.parse_args(argv)
  if args.command == "audit":
    return run_audit(args, parser)
  if args.command == "init":
    return run_init(args, parser)
  parser.print_help()
  return 2


if __name__ == "__main__":
  raise SystemExit(main())
