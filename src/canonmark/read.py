"""`canon_read`：按权威契约过滤后再交付文档内容。

设计意图（protocol §7.4）：把协议从「写给消费者遵守的规矩」变成「消费者拿到的
数据已经过协议过滤」。前者依赖自觉——一个忙着改代码的 agent 不会记得先读头部；
后者是机制——作废文档的正文根本不会进入它的上下文。

**能判什么、不能判什么**（对应 protocol §3 的五步）：

  第 1/2/5 步（`superseded_by` / `status` / `current_authority`）是客观事实，
  本模块判定并据此过滤。

  第 3/4 步（`not_for` / `applies_when` 是否命中「当前任务」）是语义判断，
  本模块**不假装能做**——它不知道调用方在干什么。改为把这两个字段原样交出，
  由调用方自己比对。假装能匹配比不匹配更危险：一次错误的「不适用」会让 agent
  跳过真正该读的文档。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .audit import (
    Frontmatter,
    display_path,
    parse_frontmatter,
    resolve_superseded_target,
)
from .config import GovernanceConfig, DEFAULT_CONFIG


# 判定结果。名字直接对应 protocol §7.4 表格的行。
CURRENT = "current"
SUPERSEDED = "superseded"
UNGOVERNED = "ungoverned"
INSUFFICIENT_METADATA = "INSUFFICIENT_METADATA"
METADATA_CONFLICT = "METADATA_CONFLICT"

# 只有这一类会交付正文之外的「权威」资格。
BODY_WITHHELD = (SUPERSEDED, INSUFFICIENT_METADATA, METADATA_CONFLICT)


@dataclass
class ReadResult:
  """一次 ``canon_read`` 的结果。

  ``body`` 为 None 表示**正文按协议不予返回**——这正是本模块存在的理由，
  调用方拿不到过时正文，也就无从被它误导。
  """

  path: str
  verdict: str
  body: str | None = None
  status: str = ""
  authority: str = ""
  applies_when: str = ""
  not_for: str = ""
  replacements: list[str] = field(default_factory=list)
  diagnostics: list[str] = field(default_factory=list)

  @property
  def body_withheld(self) -> bool:
    return self.body is None


def _body_after_frontmatter(text: str, frontmatter: Frontmatter) -> str:
  """返回 frontmatter 之后的正文。closing_line 是 1-based 的闭合 --- 行号。"""
  if frontmatter.closing_line is None:
    return text
  return "\n".join(text.splitlines()[frontmatter.closing_line :]).lstrip("\n")


def _text_field(frontmatter: Frontmatter, name: str) -> str:
  value = frontmatter.values.get(name)
  return str(value).strip() if isinstance(value, str) else ""


def _replacement_targets(
    path: Path,
    frontmatter: Frontmatter,
    root: Path,
    docs_dir: Path,
    config: GovernanceConfig,
) -> tuple[list[str], list[str]]:
  """解析 superseded_by 指向的替代目标，返回 (可用目标, 诊断)。"""
  targets: list[str] = []
  problems: list[str] = []
  raw = frontmatter.values.get("superseded_by")
  if not isinstance(raw, list):
    return targets, problems
  for item in raw:
    if not isinstance(item, str) or not item.strip():
      continue
    resolved = resolve_superseded_target(path, item, root, docs_dir, config)
    if resolved is None or not resolved.is_file():
      problems.append(f"替代目标不存在或越界：{item}")
      continue
    targets.append(display_path(resolved, root))
  return targets, problems


def read_document(
    path: Path,
    root: Path,
    config: GovernanceConfig | None = None,
    restrict_to_docs: bool = False,
) -> ReadResult:
  """按 protocol §7.4 判定该不该交付正文。

  判定顺序与五步协议一致：先看是否被取代，再看生死，最后才谈正文。

  ``restrict_to_docs`` 是**调用方的策略**，不是契约的一部分：
  MCP 层传 True——那是给 agent 的受限接口，不设边界时它就成了一个不受限的
  任意文件读取器，当 agent 只被给了 canonmark 工具时那是条现成的绕过路径。
  CLI 层传 False——人手动跑 `canon read` 时知道自己在读什么，强行限制只会
  让它没法用于仓库外的文档（例如本仓 tests/fixtures 下的实验夹具）。
  """
  config = config if config is not None else DEFAULT_CONFIG
  docs_dir = root / config.docs_root
  shown = display_path(path, root)

  if restrict_to_docs:
    try:
      inside_docs = path.resolve().is_relative_to(docs_dir.resolve())
    except OSError:
      inside_docs = False
    if not inside_docs:
      return ReadResult(
          shown,
          INSUFFICIENT_METADATA,
          diagnostics=[
              f"路径不在受治理的 {config.docs_root}/ 树内，本工具不予读取",
          ],
      )

  if not path.is_file():
    return ReadResult(
        shown,
        INSUFFICIENT_METADATA,
        diagnostics=[f"文件不存在：{shown}"],
    )

  try:
    text = path.read_text(encoding="utf-8", errors="replace")
  except OSError as error:
    return ReadResult(
        shown, INSUFFICIENT_METADATA, diagnostics=[f"读取失败：{error}"]
    )
  frontmatter = parse_frontmatter(path, config)

  # 未纳入治理：gradual 下放行正文并说明无法验证时效性。理由见 protocol §7.4——
  # 拒绝返回会把 agent 逼回内置读取工具，那时连这句警告都收不到，比放行更糟。
  if frontmatter.absent:
    if config.is_gradual:
      return ReadResult(
          shown,
          UNGOVERNED,
          body=text,
          diagnostics=["此文档未纳入治理（无 frontmatter），无法验证时效性"],
      )
    return ReadResult(
        shown,
        INSUFFICIENT_METADATA,
        diagnostics=["缺少顶部 YAML frontmatter；正文不得作为当前权威"],
    )

  if frontmatter.error:
    return ReadResult(
        shown,
        INSUFFICIENT_METADATA,
        diagnostics=[frontmatter.error, "正文不得作为当前权威"],
    )

  missing = [
      name
      for name in config.required_frontmatter_fields
      if name not in frontmatter.fields
  ]
  if missing:
    return ReadResult(
        shown,
        INSUFFICIENT_METADATA,
        diagnostics=[
            f"frontmatter 缺字段：{', '.join(missing)}",
            "正文不得作为当前权威",
        ],
    )

  status = _text_field(frontmatter, "status").casefold()
  authority = _text_field(frontmatter, "current_authority").casefold()
  applies_when = _text_field(frontmatter, "applies_when")
  not_for = _text_field(frontmatter, "not_for")
  targets, problems = _replacement_targets(
      path, frontmatter, root, docs_dir, config
  )

  conflicts: list[str] = []
  if status not in config.allowed_statuses:
    conflicts.append(f"status 取值非法：{status or '空'}")
  if authority not in config.allowed_authorities:
    conflicts.append(f"current_authority 取值非法：{authority or '空'}")
  allowed = config.status_authority_matrix.get(status)
  if allowed is not None and authority and authority not in allowed:
    conflicts.append(
        f"status={status} 不允许配 current_authority={authority}"
    )
  if status == CURRENT and targets:
    conflicts.append("status=current 却声明被取代")
  if status == SUPERSEDED and not targets and not problems:
    conflicts.append("status=superseded 却未指出取代者")

  if conflicts:
    return ReadResult(
        shown,
        METADATA_CONFLICT,
        status=status,
        authority=authority,
        diagnostics=conflicts + ["先修元数据再使用；正文不作为权威返回"],
    )

  # 已作废：正文不予返回，只给去处。这是本模块最核心的一行行为。
  if status in config.historical_statuses:
    return ReadResult(
        shown,
        SUPERSEDED,
        status=status,
        authority=authority,
        replacements=targets,
        diagnostics=problems,
    )

  return ReadResult(
      shown,
      CURRENT,
      # 剥掉 frontmatter：它的内容已在头部摘要里给过，再随正文附一遍等于把
      # 同样的字节收两次费，与「零额外上下文开销」的主张相悖。
      body=_body_after_frontmatter(text, frontmatter),
      status=status,
      authority=authority,
      applies_when=applies_when,
      not_for=not_for,
  )


def render_read_result(result: ReadResult) -> str:
  """渲染成交给消费者（人或 agent）的文本。"""
  lines: list[str] = []
  if result.verdict == SUPERSEDED:
    lines.append(f"{result.path} — 已作废（status: {result.status}）")
    lines.append("本文档不再有效，正文按权威契约不予返回。")
    if result.replacements:
      lines.append("请改读以下现行文档：")
      lines.extend(f"  - {target}" for target in result.replacements)
    elif not result.diagnostics:
      # 只有在「确实一个替代目标都没声明」时才这么说。声明了但解析失败时，
      # 下面的诊断会讲清楚是哪一个坏了——那种情况下说「没有指出替代目标」
      # 与事实相反，会把人引向错误的修法。
      lines.append("⚠ 它没有指出替代目标，请回到所在目录的 README 找入口。")
    else:
      lines.append("⚠ 它声明了替代目标，但无法定位：")
    lines.extend(f"⚠ {item}" for item in result.diagnostics)
    return "\n".join(lines)

  if result.verdict in (INSUFFICIENT_METADATA, METADATA_CONFLICT):
    lines.append(f"{result.path} — {result.verdict}")
    lines.extend(f"⚠ {item}" for item in result.diagnostics)
    lines.append("正文不作为权威依据返回。可回到目录 README 另找入口。")
    return "\n".join(lines)

  if result.verdict == UNGOVERNED:
    lines.append(f"{result.path} — 未纳入治理")
    lines.extend(f"⚠ {item}" for item in result.diagnostics)
  else:
    lines.append(
        f"{result.path} — status: {result.status}"
        f" | current_authority: {result.authority}"
    )
    if result.applies_when:
      lines.append(f"适用于：{result.applies_when}")
    if result.not_for:
      lines.append(f"不适用于：{result.not_for}")
    # 适用性是语义判断，机器不越权替调用方下结论（见模块 docstring）。
    lines.append(
        "（适用性由你判断：当前任务若落在「不适用」里，"
        "这篇不能主导，请另找依据）"
    )
  lines.append("---")
  lines.append(result.body or "")
  return "\n".join(lines)
