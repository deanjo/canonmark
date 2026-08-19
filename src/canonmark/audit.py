"""canonmark 只读文档审计器。

从 agong ``docs-audit.py`` 抽取而来。所有原来读模块级项目常量的地方，
都改成读传入的 :class:`~canonmark.config.GovernanceConfig`；未显式传 config 时
回退到 :data:`~canonmark.config.DEFAULT_CONFIG`。

各门（权威清单是 :data:`SUPPORTED_GATES`，本表由测试守住不许与之漂移）：
  V2  目录命名（kebab-case + 白名单 + archive 历史豁免）
  V4  含 ≥2 文件的非纯资产目录必须有 README
  V5  frontmatter 契约（本模块最大的一块）：关键文档查全字段；
      其余贴了标签的文档查底线（status 枚举 + superseded 指针一致）
  V9  总导航必须链接全部正式顶层目录
  V10 活文档相对链接与 docs/...:line 引用不得断
  V11 防腐烂：导航与标签互检判失败；久未复核与孤儿文档只提示
  V12 任务框架预算：框架文档与 evidence 体量超软阈值提示、超硬阈值判失败，
      状态文件的 `批准:` 行可显式放行
  V13 状态登记表：状态文件必须恰好有一张 id|status|updated_at 登记表，
      状态词出现在登记表之外即绊线报错

判失败与只提示的分界见 :meth:`GateResult.notice` 与 ``config.adoption_mode``。
"""

from __future__ import annotations

import html
import os
from dataclasses import dataclass, field
from datetime import date
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator
from urllib.parse import unquote as _unquote
from urllib.parse import urlsplit as _urlsplit

from .config import DEFAULT_CONFIG, GovernanceConfig

try:
  import yaml
except ImportError as error:
  yaml = None
  YAML_IMPORT_ERROR = str(error)
else:
  YAML_IMPORT_ERROR = None


SUPPORTED_GATES = ("V2", "V4", "V5", "V9", "V10", "V11", "V12", "V13")
# Markdown 结构性正则（与项目无关，保持模块常量）。
REFERENCE_DEFINITION_RE = re.compile(
    r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|[^\s]+)"
)
LINE_FRAGMENT_RE = re.compile(r"^L([0-9]+)(?:-L([0-9]+))?$", re.IGNORECASE)
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
# gradual 宽松判定用：frontmatter 首个非空行应形如 `key:` / `key: value`，
# 键名为常规标识符。不像的按 Markdown 水平线对待（见 parse_frontmatter）。
FRONTMATTER_KEY_RE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_-]*\s*:(\s|$)")


def _cfg(config: GovernanceConfig | None) -> GovernanceConfig:
  """未传 config 时回退到默认配置。"""
  return config if config is not None else DEFAULT_CONFIG


@dataclass(frozen=True, order=True)
class Issue:
  """单个可定位的审计问题。"""

  path: str
  line: int
  message: str


@dataclass
class GateResult:
  """单个 gate（验收门）的结果。"""

  gate: str
  anchor: str
  checked: str
  issues: list[Issue] = field(default_factory=list)
  notices: list[Issue] = field(default_factory=list)

  def add(self, path: Path | str, line: int, message: str, root: Path) -> None:
    """加入问题，并统一输出仓库相对路径。"""
    self.issues.append(
        Issue(display_path(path, root), max(1, line), message)
    )

  def notice(self, path: Path | str, line: int, message: str, root: Path) -> None:
    """加入提示：会打印，但不判失败、不影响退出码。

    用于「本可以更好，但现在这样不算错」的情况：未纳入治理的文档、
    超期未复核、孤儿文档。判失败会促使团队关掉整个门禁，与目的相反。
    """
    self.notices.append(
        Issue(display_path(path, root), max(1, line), message)
    )


@dataclass(frozen=True)
class Frontmatter:
  """Markdown 文件顶部 frontmatter 的字段与边界。"""

  fields: dict[str, int]
  values: dict[str, object]
  closing_line: int | None
  error: str | None
  error_line: int | None = None
  # 完全没有 frontmatter（首行不是 ---）。区别于「写了但写错」：
  # 前者是「尚未纳入治理」，后者是「已纳入但有错」，两者在 gradual 模式下待遇不同。
  absent: bool = False


def display_path(path: Path | str, root: Path) -> str:
  """把路径转换为稳定的仓库相对 POSIX 路径。"""
  candidate = Path(path)
  if not candidate.is_absolute():
    return candidate.as_posix()
  try:
    return candidate.relative_to(root).as_posix()
  except ValueError:
    return candidate.as_posix()


def discover_repo_root(config: GovernanceConfig | None = None) -> Path:
  """从当前目录向上寻找含 docs 根的仓库根。"""
  config = _cfg(config)
  candidates = [Path.cwd().resolve()]
  seen: set[Path] = set()
  for candidate in candidates:
    for parent in (candidate, *candidate.parents):
      if parent in seen:
        continue
      seen.add(parent)
      if (parent / config.docs_root).is_dir():
        return parent
  raise FileNotFoundError(
      f"无法定位仓库根：向上未找到 {config.docs_root}/ 目录"
  )


def markdown_files(docs_dir: Path) -> list[Path]:
  """列出 docs 根下全部 Markdown 文件，排序保证输出稳定。"""
  return sorted(
      path
      for path in docs_dir.rglob("*")
      if path.is_file() and path.suffix.lower() == ".md"
  )


def is_ignored_tool_directory(name: str, config: GovernanceConfig | None = None) -> bool:
  """识别 Python、Git 和常见隐藏工具缓存目录。"""
  config = _cfg(config)
  if name in config.ignored_directory_names:
    return True
  return name.startswith(".") and "cache" in name.casefold()


def iter_governed_directories(
    docs_dir: Path,
    include_root: bool = False,
    config: GovernanceConfig | None = None,
) -> Iterator[Path]:
  """遍历治理目录，并剪枝工具缓存目录。"""
  config = _cfg(config)
  for current, directory_names, _ in os.walk(docs_dir):
    directory_names[:] = sorted(
        name
        for name in directory_names
        if not is_ignored_tool_directory(name, config)
    )
    current_path = Path(current)
    if include_root or current_path != docs_dir:
      yield current_path


def starts_frontmatter(first_line: str) -> bool:
  """首行是否是 frontmatter 起始分隔符。

  统一入口：BOM 必须先剥掉，否则带 BOM 的文档会被判成「没有 frontmatter」。
  这条判定散落在三处，此前修 BOM 时只改了两处、漏掉第三处——所以收敛成一个
  函数，让「改一处漏一处」在结构上不可能发生。
  """
  return first_line.lstrip("\ufeff").strip() == "---"


def parse_frontmatter(
    path: Path, config: GovernanceConfig | None = None
) -> Frontmatter:
  """用 PyYAML 解析顶部 frontmatter，并拒绝重复一级字段。

  ``config`` 为 gradual 时启用宽松判定：首行是 ``---``、但其后首个非空行
  不像 YAML 键值对的，把这个 ``---`` 按 Markdown 水平线对待，整篇视为
  未纳入治理（absent）——以分隔线开头的存量笔记不是「写了标签却写错」。
  只要那行像键值对（哪怕忘了闭合 ``---``），任何模式下都仍按 frontmatter
  尝试并照常报错。不传 config 即保持既有判定；这里刻意不回退
  DEFAULT_CONFIG，否则「忘了传」会静默变成宽松模式。
  """
  lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
  if not lines or not starts_frontmatter(lines[0]):
    return Frontmatter(
        {}, {}, None, "缺少顶部 YAML frontmatter", 1, absent=True
    )
  if config is not None and config.is_gradual:
    first_content = next((line for line in lines[1:] if line.strip()), "")
    if not FRONTMATTER_KEY_RE.match(first_content):
      return Frontmatter(
          {}, {}, None, "缺少顶部 YAML frontmatter", 1, absent=True
      )

  closing_index = next(
      (index for index in range(1, len(lines)) if lines[index].strip() == "---"),
      None,
  )
  if closing_index is None:
    return Frontmatter(
        {}, {}, None, "YAML frontmatter 缺少结束分隔符 ---", 1
    )
  closing_line = closing_index + 1
  if yaml is None:
    detail = f"：{YAML_IMPORT_ERROR}" if YAML_IMPORT_ERROR else ""
    return Frontmatter(
        {},
        {},
        closing_line,
        f"缺少 PyYAML 依赖，无法解析 YAML frontmatter{detail}",
        1,
    )

  yaml_text = "\n".join(lines[1:closing_index])
  try:
    root_node = yaml.compose(yaml_text, Loader=yaml.SafeLoader)
  except yaml.YAMLError as error:
    problem = getattr(error, "problem", None) or str(error).splitlines()[0]
    mark = getattr(error, "problem_mark", None)
    error_line = mark.line + 2 if mark is not None else 1
    return Frontmatter(
        {},
        {},
        closing_line,
        f"YAML frontmatter 非法：{problem}",
        error_line,
    )
  if not isinstance(root_node, yaml.nodes.MappingNode):
    error_line = root_node.start_mark.line + 2 if root_node is not None else 2
    return Frontmatter(
        {},
        {},
        closing_line,
        "YAML frontmatter 顶层必须是键值映射",
        error_line,
    )

  fields: dict[str, int] = {}
  for key_node, _ in root_node.value:
    key_line = key_node.start_mark.line + 2
    if (
        not isinstance(key_node, yaml.nodes.ScalarNode)
        or key_node.tag != "tag:yaml.org,2002:str"
    ):
      return Frontmatter(
          fields,
          {},
          closing_line,
          "YAML frontmatter 一级字段名必须是字符串",
          key_line,
      )
    field_name = key_node.value
    if field_name in fields:
      return Frontmatter(
          fields,
          {},
          closing_line,
          f"YAML frontmatter 重复一级字段：{field_name}",
          key_line,
      )
    fields[field_name] = key_line

  try:
    loaded = yaml.safe_load(yaml_text)
  except yaml.YAMLError as error:
    problem = getattr(error, "problem", None) or str(error).splitlines()[0]
    mark = getattr(error, "problem_mark", None)
    error_line = mark.line + 2 if mark is not None else 1
    return Frontmatter(
        fields,
        {},
        closing_line,
        f"YAML frontmatter 非法：{problem}",
        error_line,
    )
  except ValueError as error:
    return Frontmatter(
        fields,
        {},
        closing_line,
        f"YAML frontmatter 构造失败：{error}",
        fields.get("last_reviewed", 1),
    )
  if not isinstance(loaded, dict):
    return Frontmatter(
        fields,
        {},
        closing_line,
        "YAML frontmatter 顶层必须是键值映射",
        2,
    )
  return Frontmatter(fields, loaded, closing_line, None)


def normalized_frontmatter_value(frontmatter: Frontmatter, field_name: str) -> str:
  """把 YAML 字符串归一化；bool、数字和集合值不冒充语义字段。"""
  value = frontmatter.values.get(field_name)
  if not isinstance(value, str):
    return ""
  return value.strip().casefold()


def frontmatter_string_error(
    frontmatter: Frontmatter, field_name: str
) -> str | None:
  """校验必须为非空真实字符串的语义字段。"""
  value = frontmatter.values.get(field_name)
  if not isinstance(value, str):
    return (
        f"{field_name} 必须是非空字符串；"
        f"实际类型：{type(value).__name__}"
    )
  if not value.strip():
    return f"{field_name} 不能为空"
  return None


def last_reviewed_error(frontmatter: Frontmatter) -> str | None:
  """校验 last_reviewed 为有效 YAML date 或 YYYY-MM-DD 字符串。"""
  value = frontmatter.values.get("last_reviewed")
  if type(value) is date:
    return None
  if not isinstance(value, str):
    return (
        "last_reviewed 必须是有效 YYYY-MM-DD 字符串或 YAML date；"
        f"实际类型：{type(value).__name__}"
    )
  normalized = value.strip()
  if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
    return "last_reviewed 必须是有效 YYYY-MM-DD 日期"
  try:
    date.fromisoformat(normalized)
  except ValueError:
    return "last_reviewed 必须是有效 YYYY-MM-DD 日期"
  return None


def frontmatter_collection_has_items(
    _path: Path, frontmatter: Frontmatter, field_name: str
) -> bool:
  """判断 YAML 列表字段是否至少包含一项。"""
  value = frontmatter.values.get(field_name)
  return isinstance(value, list) and bool(value)


def frontmatter_collection_is_list(
    _path: Path, frontmatter: Frontmatter, field_name: str
) -> bool:
  """判断字段经 YAML 解析后是否为真实列表。"""
  return isinstance(frontmatter.values.get(field_name), list)


def frontmatter_collection_item_error(
    frontmatter: Frontmatter, field_name: str
) -> str | None:
  """返回列表项类型错误；文档引用必须是非空字符串。"""
  value = frontmatter.values.get(field_name)
  if not isinstance(value, list):
    return None
  for index, item in enumerate(value, start=1):
    if not isinstance(item, str) or not item.strip():
      return f"{field_name} 列表第 {index} 项必须是非空字符串"
  return None


def authority_matches_status(
    status: str, authority: str, config: GovernanceConfig | None = None
) -> bool:
  """校验文档状态与权威类型不会互相冲突（读 status_authority_matrix）。"""
  return _cfg(config).authority_allowed_for_status(status, authority)


def first_document_h1(text: str) -> str:
  """只读取首个 H1，避免用普通正文里的术语推断技术方案类型。"""
  lines = text.splitlines()
  body_start = 0
  if lines and starts_frontmatter(lines[0]):
    closing_index = next(
        (
            index
            for index in range(1, len(lines))
            if lines[index].strip() == "---"
        ),
        None,
    )
    if closing_index is not None:
      body_start = closing_index + 1

  visible_lines = [
      mask_inline_code(line)
      for _, line in iter_non_fenced_lines("\n".join(lines[body_start:]))
  ]
  for index, line in enumerate(visible_lines):
    match = re.match(r"^ {0,3}#(?:[ \t]+)(.+?)\s*$", line)
    if match:
      return match.group(1).strip().rstrip("#").rstrip()
    if index > 0 and re.fullmatch(r" {0,3}=+[ \t]*", line):
      return visible_lines[index - 1].strip()
  return ""


def technical_plan_expected_authority(
    path: Path, text: str, config: GovernanceConfig | None = None
) -> str | None:
  """按文件名、H1 和 task 目录识别技术方案分片的严格权威类型。"""
  config = _cfg(config)
  h1 = first_document_h1(text)
  identity = f"{path.stem}\n{h1}"
  normalized_stem = path.stem.casefold().replace("-", "_").replace(".", "_")
  if config.evidence_directory_name in {
      part.casefold() for part in path.parts
  }:
    return None
  if config.acceptance_matrix_re.search(normalized_stem):
    return "acceptance-current"
  if config.task_shard_identity_re.search(identity):
    return "task-current"
  if (
      path.parent.name.casefold() == config.tasks_directory_name
      and config.task_file_prefix_re.match(path.stem)
  ):
    return "task-current"
  for authority, pattern in config.compiled_technical_plan_authority_patterns:
    if pattern.search(identity):
      return authority
  return None


def technical_plan_authority_matches_status(
    status: str,
    authority: str,
    current_authority: str,
    config: GovernanceConfig | None = None,
) -> bool:
  """校验技术方案分片的严格状态映射，同时允许背景与历史生命周期。"""
  config = _cfg(config)
  if status == "current":
    return authority == current_authority
  if status == "background":
    return authority == config.technical_plan_background_authority
  if status in {"archive", "superseded"}:
    return authority == config.technical_plan_historical_authority
  return False


def resolve_superseded_target(
    source: Path,
    target_value: str,
    root: Path,
    docs_dir: Path,
    config: GovernanceConfig | None = None,
) -> Path | None:
  """解析替代目标；支持当前文件相对路径和 docs 根仓库根路径。"""
  config = _cfg(config)
  raw_target = Path(target_value.strip())
  if raw_target.is_absolute():
    return None
  candidate = (
      root / raw_target
      if raw_target.parts and raw_target.parts[0] == config.docs_root
      else source.parent / raw_target
  ).resolve()
  if not candidate.is_relative_to(docs_dir.resolve()):
    return None
  return candidate


def suggest_supersession_path(
    source: Path, target_value: str, docs_dir: Path
) -> str:
  """目标写错时给出可直接照抄的写法。

  两种口径都合法（同目录相对 / 以 docs 根开头），报错只说「不存在」等于让人猜。
  按文件名在 docs 下找；唯一命中才建议，多个同名时不猜。
  """
  name = Path(target_value.strip()).name
  if not name:
    return ""
  matches = [item for item in docs_dir.rglob(name) if item.is_file()]
  if len(matches) != 1:
    return ""
  relative = os.path.relpath(matches[0], source.parent)
  return f"；是否想写 {Path(relative).as_posix()}"


def declares_pointer(
    source: Path,
    expected: Path,
    field_name: str,
    root: Path,
    docs_dir: Path,
    config: GovernanceConfig | None = None,
) -> bool:
  """source 的 field_name 列表是否指向 expected（按解析后的真实路径比对）。

  两端可以各用一种路径口径（同目录相对 / 以 docs 根开头），故不能比字面量。
  """
  values = parse_frontmatter(source).values.get(field_name)
  if not isinstance(values, list):
    return False
  target = expected.resolve()
  for value in values:
    if not isinstance(value, str) or not value.strip():
      continue
    resolved = resolve_superseded_target(source, value, root, docs_dir, config)
    if resolved is not None and resolved == target:
      return True
  return False


def superseded_targets(
    source: Path, root: Path, docs_dir: Path, config: GovernanceConfig | None = None
) -> list[Path]:
  """返回可继续遍历的有效替代目标；非法或缺失目标由调用方报告。"""
  config = _cfg(config)
  frontmatter = parse_frontmatter(source)
  values = frontmatter.values.get("superseded_by")
  if frontmatter.error or not isinstance(values, list):
    return []
  targets: list[Path] = []
  for value in values:
    if not isinstance(value, str) or not value.strip():
      continue
    target = resolve_superseded_target(source, value, root, docs_dir, config)
    if target is not None and target.is_file():
      targets.append(target)
  return targets


def superseded_cycle(
    start: Path, root: Path, docs_dir: Path, config: GovernanceConfig | None = None
) -> list[Path] | None:
  """深度优先检查从指定文档出发的替代链，并返回首个环路。"""
  config = _cfg(config)
  visited: set[Path] = set()
  active: list[Path] = []

  def visit(path: Path) -> list[Path] | None:
    if path in active:
      cycle_start = active.index(path)
      return active[cycle_start:] + [path]
    if path in visited:
      return None
    active.append(path)
    for target in superseded_targets(path, root, docs_dir, config):
      cycle = visit(target)
      if cycle is not None:
        return cycle
    active.pop()
    visited.add(path)
    return None

  return visit(start.resolve())


def has_key_document_signal(
    text: str, config: GovernanceConfig | None = None
) -> bool:
  """识别正文前部明确自称权威、契约、路线图或完成定义的文档。"""
  config = _cfg(config)
  visible_lines: list[str] = []
  for _, line in iter_non_fenced_lines(text):
    visible_lines.append(mask_inline_code(line))
    if len(visible_lines) >= 80:
      break
  return bool(config.key_document_signal_re.search("\n".join(visible_lines)))


def normalized_navigation_label(value: str) -> str:
  """归一化目录名和 H1，用于识别纯目录导航标题。"""
  return re.sub(r"[^a-z0-9一-鿿]+", "", value.casefold())


def has_key_document_title(
    path: Path, text: str, config: GovernanceConfig | None = None
) -> bool:
  """识别关键 H1；与父目录同名的纯导航标题不算关键文档。"""
  config = _cfg(config)
  lines = text.splitlines()
  body_start = 0
  if lines and starts_frontmatter(lines[0]):
    closing_index = next(
        (
            index
            for index in range(1, len(lines))
            if lines[index].strip() == "---"
        ),
        None,
    )
    if closing_index is not None:
      body_start = closing_index + 1

  visible_lines = [
      mask_inline_code(line)
      for _, line in iter_non_fenced_lines("\n".join(lines[body_start:]))
  ]

  def title_is_key(title: str) -> bool:
    normalized_title = title.strip().rstrip("#").rstrip()
    if normalized_navigation_label(
        normalized_title
    ) == normalized_navigation_label(path.parent.name):
      return False
    return bool(config.key_document_title_re.search(normalized_title))

  for index, line in enumerate(visible_lines):
    match = re.match(r"^ {0,3}#(?:[ \t]+)(.+?)\s*$", line)
    if match:
      return title_is_key(match.group(1))
    if index > 0 and re.fullmatch(r" {0,3}=+[ \t]*", line):
      title_lines: list[str] = []
      cursor = index - 1
      while cursor >= 0:
        candidate = visible_lines[cursor]
        if not candidate.strip() or re.match(r"^ {4}", candidate):
          break
        title_lines.append(candidate.strip())
        cursor -= 1
      if title_lines:
        return title_is_key(" ".join(reversed(title_lines)))
  return False


def frontmatter_declares_field(text: str, field_name: str) -> bool:
  """仅用于关键文档识别；字段值仍必须由 PyYAML 校验。"""
  lines = text.splitlines()
  if not lines or not starts_frontmatter(lines[0]):
    return False
  field_pattern = re.compile(rf"^{re.escape(field_name)}\s*:")
  for line in lines[1:]:
    if line.strip() == "---":
      return False
    if field_pattern.match(line):
      return True
  return False


def is_template_document(
    path: Path, docs_dir: Path, config: GovernanceConfig | None = None
) -> bool:
  """用明确目录或文件名识别模板，避免把模板正文当成执行契约。"""
  config = _cfg(config)
  relative = path.relative_to(docs_dir)
  parent_names = {part.casefold() for part in relative.parts[:-1]}
  stem = path.stem.casefold()
  return bool(
      parent_names & config.template_directory_names
  ) or stem.endswith(config.template_filename_suffixes)


def has_key_document_name(
    path: Path, docs_dir: Path, config: GovernanceConfig | None = None
) -> bool:
  """按高置信文件名和语义目录识别设计、契约、任务与验收文档。"""
  config = _cfg(config)
  relative = path.relative_to(docs_dir)
  parent_names = {part.casefold() for part in relative.parts[:-1]}
  return bool(
      config.key_document_filename_re.search(path.stem)
      or parent_names & config.key_document_directory_names
  )


def is_key_document(
    path: Path,
    docs_dir: Path,
    frontmatter: Frontmatter,
    text: str,
    config: GovernanceConfig | None = None,
) -> bool:
  """判定 V5 关键文档；普通导航简化，权威 README 不豁免。"""
  config = _cfg(config)
  if is_template_document(path, docs_dir, config):
    return False
  authority_declared = (
      "current_authority" in frontmatter.fields
      or frontmatter_declares_field(text, "current_authority")
  )
  navigation_name = path.name.casefold()
  if navigation_name == config.navigation_readme_filename:
    return authority_declared or has_key_document_title(path, text, config)
  if navigation_name in config.legacy_navigation_filenames:
    status = normalized_frontmatter_value(frontmatter, "status")
    return authority_declared and status not in {"archive", "superseded"}
  if authority_declared:
    return True
  return has_key_document_name(path, docs_dir, config) or has_key_document_signal(
      text, config
  )


def iter_non_fenced_lines(text: str) -> Iterator[tuple[int, str]]:
  """逐行返回非 fenced code block（围栏代码块）内容。"""
  fence_char: str | None = None
  fence_length = 0
  for line_number, line in enumerate(text.splitlines(), start=1):
    match = FENCE_RE.match(line)
    if fence_char is None:
      if match:
        marker = match.group(1)
        fence_char = marker[0]
        fence_length = len(marker)
        continue
      yield line_number, line
      continue

    if match:
      marker = match.group(1)
      if marker[0] == fence_char and len(marker) >= fence_length:
        fence_char = None
        fence_length = 0


def mask_inline_code(line: str) -> str:
  """遮蔽行内代码，保留字符位置以避免把示例识别成 Markdown 链接。"""
  chars = list(line)
  index = 0
  while index < len(line):
    if line[index] != "`":
      index += 1
      continue
    run_end = index
    while run_end < len(line) and line[run_end] == "`":
      run_end += 1
    marker = line[index:run_end]
    closing = line.find(marker, run_end)
    if closing < 0:
      index = run_end
      continue
    for masked_index in range(index, closing + len(marker)):
      chars[masked_index] = " "
    index = closing + len(marker)
  return "".join(chars)


def is_escaped(text: str, index: int) -> bool:
  """判断指定字符前是否有奇数个反斜杠。"""
  backslashes = 0
  cursor = index - 1
  while cursor >= 0 and text[cursor] == "\\":
    backslashes += 1
    cursor -= 1
  return backslashes % 2 == 1


def destination_from_link_body(body: str) -> str | None:
  """从 `(destination "title")` 中提取 destination。"""
  stripped = body.strip()
  if not stripped:
    return None
  if stripped.startswith("<"):
    closing = stripped.find(">")
    return stripped[1:closing] if closing >= 0 else None

  for index, char in enumerate(stripped):
    if char.isspace() and not is_escaped(stripped, index):
      return stripped[:index]
  return stripped


def inline_link_destinations(line: str) -> Iterator[str]:
  """提取一行中的内联链接和图片链接目标。"""
  visible = mask_inline_code(line)
  cursor = 0
  while cursor < len(visible):
    close_label = visible.find("](", cursor)
    if close_label < 0:
      return
    open_label = visible.rfind("[", cursor, close_label)
    if open_label < 0 or is_escaped(visible, close_label):
      cursor = close_label + 2
      continue

    body_start = close_label + 2
    depth = 1
    index = body_start
    angle_wrapped = False
    while index < len(visible):
      char = visible[index]
      if char == "<" and index == body_start:
        angle_wrapped = True
      elif char == ">" and angle_wrapped:
        angle_wrapped = False
      elif not angle_wrapped and not is_escaped(visible, index):
        if char == "(":
          depth += 1
        elif char == ")":
          depth -= 1
          if depth == 0:
            destination = destination_from_link_body(
                line[body_start:index]
            )
            if destination is not None:
              yield destination
            cursor = index + 1
            break
      index += 1
    else:
      return


class HtmlLinkParser(HTMLParser):
  """提取 HTML a[href] 与 img[src]，保留源行号。"""

  def __init__(self) -> None:
    super().__init__(convert_charrefs=True)
    self.destinations: list[tuple[int, str]] = []

  def handle_starttag(
      self, tag: str, attrs: list[tuple[str, str | None]]
  ) -> None:
    normalized_tag = tag.casefold()
    if normalized_tag not in {"a", "img"}:
      return
    target_attribute = "href" if normalized_tag == "a" else "src"
    for name, value in attrs:
      if name.casefold() == target_attribute and value is not None:
        self.destinations.append((self.getpos()[0], value))
        return


def iter_html_links(text: str) -> Iterator[tuple[int, str]]:
  """提取非代码块中的 HTML 链接和图片地址。"""
  lines = text.splitlines()
  visible_lines = [""] * len(lines)
  for line_number, line in iter_non_fenced_lines(text):
    visible_lines[line_number - 1] = mask_inline_code(line)
  parser = HtmlLinkParser()
  parser.feed("\n".join(visible_lines))
  parser.close()
  yield from parser.destinations


def iter_markdown_links(text: str) -> Iterator[tuple[int, str]]:
  """提取非代码块中的内联链接、图片链接和引用式链接定义。"""
  for line_number, line in iter_non_fenced_lines(text):
    for destination in inline_link_destinations(line):
      yield line_number, destination
    definition = REFERENCE_DEFINITION_RE.match(mask_inline_code(line))
    if definition:
      destination = definition.group(1)
      if destination.startswith("<") and destination.endswith(">"):
        destination = destination[1:-1]
      yield line_number, destination


def iter_v10_links(text: str) -> Iterator[tuple[int, str]]:
  """合并 Markdown 与 HTML 中需要 V10 校验的链接。"""
  yield from iter_markdown_links(text)
  yield from iter_html_links(text)


def relative_link_path(destination: str) -> str | None:
  """返回需校验的相对文件路径；外链、锚点和绝对链接返回 None。"""
  parts = relative_link_parts(destination)
  return parts[0] if parts is not None else None


def relative_link_parts(
    destination: str,
) -> tuple[str | None, str | None] | None:
  """解析本地相对链接的路径与 fragment；外链和绝对链接返回 None。"""
  cleaned = html.unescape(destination).strip()
  if not cleaned or cleaned.startswith("/"):
    return None
  parsed = _urlsplit(cleaned)
  if parsed.scheme or parsed.netloc:
    return None
  path = _unquote(parsed.path)
  fragment = _unquote(parsed.fragment) or None
  if not path and fragment is None:
    return None
  relative = re.sub(r"\\([\\ ()\[\]])", r"\1", path) if path else None
  return relative, fragment


def markdown_line_fragment_issue(
    target: Path,
    fragment: str | None,
    line_count_cache: dict[Path, int],
) -> str | None:
  """校验 GitHub 风格 #Ln/#Ln-Lm；普通标题 fragment 不推断 slug。"""
  if fragment is None:
    return None
  match = LINE_FRAGMENT_RE.fullmatch(fragment)
  if match is None:
    return None
  if not target.is_file():
    return "行号 fragment 的目标不是文件"
  start_line = int(match.group(1))
  end_line = int(match.group(2)) if match.group(2) else start_line
  total_lines = count_lines(target, line_count_cache)
  if start_line < 1 or end_line < start_line or end_line > total_lines:
    return f"行号 fragment 越界；目标共 {total_lines} 行"
  return None


def audit_v2(root: Path, config: GovernanceConfig | None = None) -> GateResult:
  """V2：检查活文档目录命名和 archive 一级目录命名。"""
  config = _cfg(config)
  docs_dir = root / config.docs_root
  archive = config.archive_directory_name
  path_exceptions = {Path(item) for item in config.v2_path_exceptions}
  result = GateResult("V2", f"{config.docs_root}:1", "0 个受治理目录")
  checked = 0
  exception_hint = "、".join(
      f"{config.docs_root}/{item}" for item in config.v2_path_exceptions
  )
  # 有白名单时列出「仅 X 和 archive … 豁免」；无白名单时只提 archive。
  if exception_hint:
    exemption_clause = f"仅 {exception_hint} 和 {archive} 一级以下历史路径豁免"
  else:
    exemption_clause = f"仅 {archive} 一级以下历史路径豁免"
  for directory in iter_governed_directories(docs_dir, config=config):
    relative = directory.relative_to(docs_dir)
    parts = relative.parts
    if parts and parts[0] == archive and len(parts) >= 3:
      continue
    checked += 1
    if relative in path_exceptions:
      continue
    if not config.directory_name_re.fullmatch(directory.name):
      # gradual：既有目录名只提示。存量项目的 `API_Reference`、`user_guide`
      # 是既成事实，不是这次治理做错的事；改名要连带改掉所有指向它的链接，
      # 绝不是「装上第一天」能做的。判失败只会让人把整个门禁关掉。
      if config.is_gradual:
        result.notice(
            directory,
            1,
            f"目录名不是 {config.directory_name_label}（{exemption_clause}）。"
            f"下一步：改为 {config.directory_name_label} 目录名，"
            "并同步更新所有指向它的链接",
            root,
        )
      else:
        result.add(
            directory,
            1,
            f"目录名不是 {config.directory_name_label}；{exemption_clause}",
            root,
        )
  result.checked = f"{checked} 个受治理目录"
  return result


def audit_v4(root: Path, config: GovernanceConfig | None = None) -> GateResult:
  """V4：直接含至少两个文件的非纯资产目录必须有 README.md。"""
  config = _cfg(config)
  docs_dir = root / config.docs_root
  result = GateResult("V4", f"{config.docs_root}:1", "0 个候选目录")
  candidates = 0
  for directory in iter_governed_directories(
      docs_dir, include_root=True, config=config
  ):
    direct_files = sorted(path for path in directory.iterdir() if path.is_file())
    if len(direct_files) < 2:
      continue
    # 无 Markdown 的脚本、数据、图片目录视为纯资产目录。
    if not any(path.suffix.lower() == ".md" for path in direct_files):
      continue
    candidates += 1
    if not (directory / "README.md").is_file():
      # gradual：从没建过导航的目录只提示。要求存量项目先重建整个 docs 结构
      # 才肯放行，等于把门槛前置到尚未产生任何价值的时刻。
      message = (
          f"直接含 {len(direct_files)} 个文件且包含 Markdown，缺少 README.md"
      )
      if config.is_gradual:
        result.notice(
            directory,
            1,
            f"{message}。下一步：在该目录新建 README.md，链接目录内各文档",
            root,
        )
      else:
        result.add(directory, 1, message, root)
  result.checked = f"{candidates} 个非纯资产候选目录"
  return result


def explicit_v5_documents(
    docs_dir: Path, config: GovernanceConfig | None = None
) -> tuple[set[Path], set[Path]]:
  """返回 V5 固定关键文档，以及存在时匹配通配的文档。"""
  config = _cfg(config)
  required = {docs_dir / relative for relative in config.required_key_documents}
  matched: set[Path] = set()
  for pattern in config.required_key_document_globs:
    matched.update(docs_dir.glob(pattern))
  return required, matched


def audit_v5(root: Path, config: GovernanceConfig | None = None) -> GateResult:
  """V5：关键文档必须含全部必备字段；其余贴了标签的文档校验标签底线。

  底线 = status 枚举合法 + superseded 指针一致（protocol §5.2 的两条矛盾
  规则）。完全没有 frontmatter 的文档不进底线校验（gradual 的水平线宽松
  判定同样视为未贴标签）。
  """
  config = _cfg(config)
  docs_dir = root / config.docs_root
  required_fields = config.required_frontmatter_fields
  result = GateResult("V5", f"{config.docs_root}:1", "0 篇关键文档")
  if yaml is None:
    detail = f"：{YAML_IMPORT_ERROR}" if YAML_IMPORT_ERROR else ""
    result.add(
        docs_dir,
        1,
        f"缺少 PyYAML 依赖，无法执行 frontmatter 审计{detail}",
        root,
    )
    return result
  all_markdown = markdown_files(docs_dir)
  required, kickoff_documents = explicit_v5_documents(docs_dir, config)
  key_documents = set(required) | kickoff_documents
  malformed_frontmatter_documents: set[Path] = set()
  labeled_documents: set[Path] = set()

  for path in all_markdown:
    if path.is_relative_to(docs_dir / config.archive_directory_name):
      continue
    text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(path, config)
    # absent 已含文档级结论（gradual 下水平线开头也算 absent），不再重看首行。
    if not frontmatter.absent and frontmatter.error is not None:
      malformed_frontmatter_documents.add(path)
    elif not frontmatter.absent:
      labeled_documents.add(path)
    if (
        is_key_document(path, docs_dir, frontmatter, text, config)
        or technical_plan_expected_authority(path, text, config) is not None
    ):
      key_documents.add(path)

  for path in sorted(key_documents | malformed_frontmatter_documents):
    if not path.is_file():
      result.add(path, 1, "固定关键文档不存在", root)
      continue
    frontmatter = parse_frontmatter(path, config)
    if frontmatter.error:
      # gradual：从未贴过标签的文档只提示不判失败——那是「尚未纳入治理」，
      # 不是过错。显式列入 required_key_documents 的除外：那是项目自己声明
      # 「这几篇必须治理」，缺标签就是没兑现声明。
      if config.is_gradual and frontmatter.absent and path not in required:
        result.notice(
            path,
            1,
            "未纳入治理：无 frontmatter，本次跳过。"
            "下一步：在文件顶部贴上 frontmatter 标签"
            "（status/owner/last_reviewed）即开始受治理",
            root,
        )
        continue
      requirement = (
          f"；必需字段：{', '.join(required_fields)}"
          if path in key_documents
          else ""
      )
      result.add(
          path,
          frontmatter.error_line or 1,
          f"{frontmatter.error}{requirement}",
          root,
      )
      continue
    missing = [
        name
        for name in required_fields
        if name not in frontmatter.fields
    ]
    if missing:
      result.add(
          path,
          frontmatter.closing_line or 1,
          f"关键文档 frontmatter 缺字段：{', '.join(missing)}",
          root,
      )
      continue

    string_values: dict[str, str] = {}
    for string_field in (
        "status",
        "applies_when",
        "not_for",
        "current_authority",
        "owner",
    ):
      string_error = frontmatter_string_error(frontmatter, string_field)
      if string_error:
        result.add(
            path,
            frontmatter.fields[string_field],
            string_error,
            root,
        )
        continue
      string_values[string_field] = str(
          frontmatter.values[string_field]
      ).strip()

    status = string_values.get("status", "").casefold()
    authority = string_values.get("current_authority", "").casefold()
    if status and status not in config.allowed_statuses:
      result.add(
          path,
          frontmatter.fields["status"],
          f"status 取值非法：{status or '空'}",
          root,
      )
    if authority and authority not in config.allowed_authorities:
      result.add(
          path,
          frontmatter.fields["current_authority"],
          f"current_authority 取值非法：{authority or '空'}",
          root,
      )
    reviewed_error = last_reviewed_error(frontmatter)
    if reviewed_error:
      result.add(
          path,
          frontmatter.fields["last_reviewed"],
          reviewed_error,
          root,
      )
    for collection_field in ("supersedes", "superseded_by"):
      if not frontmatter_collection_is_list(path, frontmatter, collection_field):
        result.add(
            path,
            frontmatter.fields[collection_field],
            f"{collection_field} 必须是 YAML 列表",
            root,
        )
        continue
      item_error = frontmatter_collection_item_error(
          frontmatter, collection_field
      )
      if item_error:
        result.add(
            path,
            frontmatter.fields[collection_field],
            item_error,
            root,
        )

    # T10 的另一半方向（protocol §2 明文举例的那一半）：本文档声称取代了谁，
    # 对方就必须承认自己已被取代。这一半更危险——漏掉时旧文档会继续自称
    # current，两篇文档同时以现行权威示人，正是本项目要防的核心故障。
    claimed = frontmatter.values.get("supersedes")
    if isinstance(claimed, list):
      for claimed_value in claimed:
        if not isinstance(claimed_value, str) or not claimed_value.strip():
          continue
        old = resolve_superseded_target(
            path, claimed_value, root, docs_dir, config
        )
        if old is None or not old.is_file():
          result.add(
              path,
              frontmatter.fields["supersedes"],
              f"supersedes 目标不存在：{claimed_value}"
              f"{suggest_supersession_path(path, claimed_value, docs_dir)}",
              root,
          )
          continue
        if old.name.casefold() == "readme.md":
          continue
        old_frontmatter = parse_frontmatter(old, config)
        if config.is_gradual and old_frontmatter.absent:
          result.notice(
              path,
              frontmatter.fields["supersedes"],
              f"被取代方尚未纳入治理：{claimed_value}。"
              "下一步：给它贴上标签并写明 superseded_by，替代关系才能被完整校验",
              root,
          )
          continue
        if not declares_pointer(
            old, path, "superseded_by", root, docs_dir, config
        ):
          # 指导必须一步到位：只说改 status，照做会立刻撞上 §4 矩阵
          # （superseded 不允许配 *-current），等于把人骗进第二轮报错。
          allowed = sorted(
              config.status_authority_matrix.get("superseded", ())
          )
          authority_hint = (
              f"、current_authority: {allowed[0]}" if len(allowed) == 1 else ""
          )
          result.add(
              path,
              frontmatter.fields["supersedes"],
              f"替代关系是单边声明：本文档声称取代 {claimed_value}，"
              f"但对方未声明已被本文档取代"
              f"（应在 {display_path(old, root)} 中写 status: superseded"
              f"{authority_hint}，并把"
              f" {os.path.relpath(path, old.parent)} 加入 superseded_by）",
              root,
          )
    if (
        status in config.allowed_statuses
        and authority in config.allowed_authorities
        and not authority_matches_status(status, authority, config)
    ):
      result.add(
          path,
          frontmatter.fields["current_authority"],
          f"status={status} 与 current_authority={authority} 冲突",
          root,
      )
    text = path.read_text(encoding="utf-8", errors="replace")
    expected_authority = technical_plan_expected_authority(path, text, config)
    if expected_authority is not None and not (
        technical_plan_authority_matches_status(
            status, authority, expected_authority, config
        )
    ):
      result.add(
          path,
          frontmatter.fields["current_authority"],
          "technical-plan 分片必须使用严格映射："
          f"current->{expected_authority}, "
          f"background->{config.technical_plan_background_authority}, "
          f"archive/superseded->{config.technical_plan_historical_authority}",
          root,
      )
    if status == "current" and frontmatter_collection_has_items(
        path, frontmatter, "superseded_by"
    ):
      result.add(
          path,
          frontmatter.fields["superseded_by"],
          "status=current 时 superseded_by 必须为空",
          root,
      )
    if status == "superseded" and not frontmatter_collection_has_items(
        path, frontmatter, "superseded_by"
    ):
      result.add(
          path,
          frontmatter.fields["superseded_by"],
          "status=superseded 时 superseded_by 必须指向替代文档",
          root,
      )
    superseded_by = frontmatter.values.get("superseded_by")
    if isinstance(superseded_by, list):
      cycle = superseded_cycle(path, root, docs_dir, config)
      # 对称性检查的前提是这条替代声明本身有效：status=current 时它已被判矛盾，
      # 成环时「让对方认领本文档」会把环越缠越紧。两种情况下都跳过 T10，
      # 由各自的专属报错负责，避免给出会把事情弄得更糟的修复建议。
      symmetry_applicable = status != "current" and cycle is None
      for target_value in superseded_by:
        if not isinstance(target_value, str) or not target_value.strip():
          continue
        target = resolve_superseded_target(
            path, target_value, root, docs_dir, config
        )
        if target is None:
          result.add(
              path,
              frontmatter.fields["superseded_by"],
              f"superseded_by 目标必须位于 {config.docs_root}/ 内：{target_value}",
              root,
          )
        elif not target.is_file():
          result.add(
              path,
              frontmatter.fields["superseded_by"],
              f"superseded_by 目标不存在：{target_value}"
              f"（按同目录解析为 {display_path(target, root)}；"
              f"也可写成以 {config.docs_root}/ 开头的仓库根路径"
              f"{suggest_supersession_path(path, target_value, docs_dir)}）",
              root,
          )
        elif target.name.casefold() != "readme.md":
          target_frontmatter = parse_frontmatter(target, config)
          target_missing = [
              name
              for name in required_fields
              if name not in target_frontmatter.fields
          ]
          if target_frontmatter.error or target_missing:
            detail = (
                target_frontmatter.error
                if target_frontmatter.error
                else f"缺字段：{', '.join(target_missing)}"
            )
            # gradual：目标还没贴标签时只提示。否则「给旧文档贴一张作废标签」——
            # 恰恰是最该做、收益最高的第一步——会强制连锁治理它指向的每一篇文档。
            if config.is_gradual and target_frontmatter.absent:
              result.notice(
                  path,
                  frontmatter.fields["superseded_by"],
                  f"替代目标尚未纳入治理：{target_value}。"
                  "下一步：给它也贴上标签，替代关系才能被完整校验",
                  root,
              )
            else:
              result.add(
                  path,
                  frontmatter.fields["superseded_by"],
                  "superseded_by 非 README 目标无法执行五步门禁："
                  f"{target_value}（{detail}）",
                  root,
              )
          elif symmetry_applicable and not declares_pointer(
              target, path, "supersedes", root, docs_dir, config
          ):
            # T10 反向指针对称：单边声明是最难自查的一类腐烂——旧文档自称退位，
            # 新文档从不知情，读到新文档的人无从判断它是否真的接管了旧职责。
            result.add(
                path,
                frontmatter.fields["superseded_by"],
                f"替代关系是单边声明：本文档声明被 {target_value} 取代，"
                f"但对方的 supersedes 未认领本文档"
                f"（应在 {display_path(target, root)} 的 supersedes 中加入"
                f" {os.path.relpath(path, target.parent)}）",
                root,
            )
      if cycle is not None:
        cycle_text = " -> ".join(
            (Path(config.docs_root) / item.relative_to(docs_dir.resolve())).as_posix()
            for item in cycle
        )
        result.add(
            path,
            frontmatter.fields["superseded_by"],
            f"superseded_by 替代链形成环路：{cycle_text}",
            root,
        )

  # 决策⑨：关键文档之外，任何贴了标签（frontmatter 可解析）的文档也要过
  # 底线校验——status 枚举合法、superseded 指针一致（protocol §5.2 的两条
  # 矛盾规则）。位置不是豁免理由：此前 docs 根下 status: bogus-value 的
  # 三字段文档在两种模式下都静默全 PASS。「没做的事不罚，做错的事才罚」——
  # 它贴了标签且贴错了。刻意不升级为八字段契约：三字段简化形态
  # （status/owner/last_reviewed）仍然合法，缺 status 的也不罚。
  ordinary_labeled_documents = labeled_documents - key_documents
  for path in sorted(ordinary_labeled_documents):
    frontmatter = parse_frontmatter(path, config)
    if "status" not in frontmatter.fields:
      continue
    status_error = frontmatter_string_error(frontmatter, "status")
    if status_error:
      result.add(path, frontmatter.fields["status"], status_error, root)
      continue
    status = normalized_frontmatter_value(frontmatter, "status")
    if status not in config.allowed_statuses:
      result.add(
          path,
          frontmatter.fields["status"],
          f"status 取值非法：{status}",
          root,
      )
    superseded_value = frontmatter.values.get("superseded_by")
    # 「非空」按语义而非形状判：标量字符串 superseded_by: new.md 同样是带
    # 指针（独立复验抓出的 fail-open 形状），空列表与纯空白字符串才算空。
    current_has_pointer = bool(superseded_value) and not (
        isinstance(superseded_value, str) and not superseded_value.strip()
    )
    if status == "current" and current_has_pointer:
      result.add(
          path,
          frontmatter.fields["superseded_by"],
          "status=current 时 superseded_by 必须为空",
          root,
      )
    if status == "superseded" and not frontmatter_collection_has_items(
        path, frontmatter, "superseded_by"
    ):
      result.add(
          path,
          frontmatter.fields.get(
              "superseded_by", frontmatter.fields["status"]
          ),
          "status=superseded 时 superseded_by 必须指向替代文档",
          root,
      )

  # 计数语如实反映检查范围：贴错 YAML 的普通文档也在上面第一个循环里查过。
  ordinary_checked = (
      labeled_documents | malformed_frontmatter_documents
  ) - key_documents
  result.checked = (
      f"{len(key_documents)} 篇关键文档，"
      f"{len(ordinary_checked)} 篇已贴标签普通文档"
  )
  return result


def audit_v9(root: Path, config: GovernanceConfig | None = None) -> GateResult:
  """V9：docs 根 README.md 必须导航全部正式顶层目录。"""
  config = _cfg(config)
  docs_dir = root / config.docs_root
  readme = docs_dir / "README.md"
  result = GateResult(
      "V9", f"{config.docs_root}/README.md:1", "0 个正式顶层目录"
  )
  if not readme.is_file():
    # gradual：没有总导航说明项目还没打算用导航层，不强制它先造一个；
    # 一旦存在，下面照常检查它是否漏链目录（有了就得对）。
    if config.is_gradual:
      result.notice(
          readme,
          1,
          f"总导航不存在。下一步：在 {config.docs_root}/README.md 建立总导航，"
          "链接各正式顶层目录",
          root,
      )
    else:
      result.add(readme, 1, "总导航不存在", root)
    return result

  top_level_directories = sorted(
      path
      for path in docs_dir.iterdir()
      if path.is_dir() and not path.name.startswith(".")
  )
  abnormal = [
      path
      for path in top_level_directories
      if path.name.casefold() in config.abnormal_top_level_names
  ]
  for directory in abnormal:
    result.add(
        directory,
        1,
        "发现平行文档根目录；不得通过加入总导航把 "
        f"{config.docs_root}/{config.docs_root} 类异常合法化",
        root,
    )

  formal = [path for path in top_level_directories if path not in abnormal]
  text = readme.read_text(encoding="utf-8", errors="replace")
  linked_targets: set[Path] = set()
  for _, destination in iter_markdown_links(text):
    relative = relative_link_path(destination)
    if relative is None:
      continue
    linked_targets.add((readme.parent / relative).resolve())

  for directory in formal:
    expected_readme = (directory / "README.md").resolve()
    if expected_readme not in linked_targets and directory.resolve() not in linked_targets:
      # gradual：漏链只提示。否则与 V4 直接打架——V4 刚说「这个目录的
      # README 可以先不建」，V9 却要求总导航必须链接那个还不存在的文件，
      # 结果是「有一个不完整的索引」（存量项目的典型形态）照样被打红。
      if config.is_gradual:
        result.notice(
            readme,
            1,
            f"未导航正式顶层目录 {config.docs_root}/{directory.name}/。"
            f"下一步：在总导航中加入链接 ./{directory.name}/README.md",
            root,
        )
      else:
        result.add(
            readme,
            1,
            f"未导航正式顶层目录 {config.docs_root}/{directory.name}/；"
            f"应链接 ./{directory.name}/README.md",
            root,
        )
  result.checked = f"{len(formal)} 个正式顶层目录"
  return result


def v10_markdown_sources(
    docs_dir: Path, config: GovernanceConfig | None = None
) -> list[Path]:
  """返回 V10 活文档；历史状态正文跳过，archive README 仍审计。"""
  config = _cfg(config)
  sources: list[Path] = []
  for path in markdown_files(docs_dir):
    relative = path.relative_to(docs_dir)
    if relative.parts and relative.parts[0] == config.archive_directory_name:
      if path.name == "README.md":
        sources.append(path)
      continue
    frontmatter = parse_frontmatter(path)
    if normalized_frontmatter_value(frontmatter, "status") in {
        "archive",
        "superseded",
    }:
      continue
    sources.append(path)
  return sources


def count_lines(path: Path, cache: dict[Path, int]) -> int:
  """按需统计文件行数并缓存。"""
  resolved = path.resolve()
  if resolved not in cache:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
      cache[resolved] = sum(1 for _ in handle)
  return cache[resolved]


def audit_relative_links(
    source: Path,
    text: str,
    result: GateResult,
    root: Path,
    line_count_cache: dict[Path, int],
    governed: bool = True,
) -> int:
  """检查 Markdown/HTML 相对链接及行号 fragment，返回链接数量。

  ``governed=False``（未贴标签的文档）时坏链降级为提示：存量坏链不是这次
  治理造成的，而贴过标签的文档必须为自己的链接负责。
  """
  link_count = 0
  report = result.add if governed else result.notice
  for line_number, destination in iter_v10_links(text):
    link_parts = relative_link_parts(destination)
    if link_parts is None:
      continue
    relative, fragment = link_parts
    if relative is None:
      target = source.resolve()
    else:
      link_count += 1
      target = (source.parent / relative).resolve()
    if not target.exists():
      message = (
          f"相对链接目标不存在：{destination} "
          f"(解析为 {display_path(target, root)})"
      )
      if not governed:
        message += "。下一步：改为指向存在的文件，或删除失效链接"
      report(source, line_number, message, root)
      continue
    fragment_issue = markdown_line_fragment_issue(
        target, fragment, line_count_cache
    )
    if fragment_issue:
      message = f"相对链接 {fragment_issue}：{destination}"
      if not governed:
        message += "。下一步：核对目标文件行数后修正行号 fragment"
      report(source, line_number, message, root)
  return link_count


def audit_docs_line_references(
    source: Path,
    text: str,
    result: GateResult,
    root: Path,
    docs_dir: Path,
    line_count_cache: dict[Path, int],
    config: GovernanceConfig | None = None,
) -> int:
  """检查单篇 Markdown 的显式 docs 根路径:line 引用，返回引用数量。"""
  config = _cfg(config)
  reference_count = 0
  for line_number, line in iter_non_fenced_lines(text):
    for match in config.docs_line_reference_re.finditer(line):
      reference_count += 1
      target_text = match.group(1)
      start_line = int(match.group(2))
      end_line = int(match.group(3)) if match.group(3) else start_line
      if "..." in target_text:
        result.add(
            source,
            line_number,
            f"显式 {config.docs_root} 引用含字面 ...，属于无效锚点：{match.group(0)}",
            root,
        )
        continue
      target = (root / target_text).resolve()
      try:
        target.relative_to(docs_dir.resolve())
      except ValueError:
        result.add(
            source,
            line_number,
            f"显式 {config.docs_root} 引用逃逸 {config.docs_root}/：{match.group(0)}",
            root,
        )
        continue
      if not target.is_file():
        result.add(
            source,
            line_number,
            f"显式 {config.docs_root} 引用文件不存在：{match.group(0)}",
            root,
        )
        continue
      total_lines = count_lines(target, line_count_cache)
      if start_line < 1 or end_line < start_line or end_line > total_lines:
        result.add(
            source,
            line_number,
            f"显式 {config.docs_root} 引用行号越界：{match.group(0)}；"
            f"目标共 {total_lines} 行",
            root,
        )
  return reference_count


def audit_v10(root: Path, config: GovernanceConfig | None = None) -> GateResult:
  """V10：检查活文档相对链接和显式 docs 根路径:line 引用。"""
  config = _cfg(config)
  docs_dir = root / config.docs_root
  if yaml is None:
    result = GateResult("V10", f"{config.docs_root}:1", "0 篇 Markdown")
    detail = f"：{YAML_IMPORT_ERROR}" if YAML_IMPORT_ERROR else ""
    result.add(
        docs_dir,
        1,
        f"缺少 PyYAML 依赖，无法判定活文档状态{detail}",
        root,
    )
    return result
  sources = v10_markdown_sources(docs_dir, config)
  result = GateResult("V10", f"{config.docs_root}:1", f"{len(sources)} 篇 Markdown")
  line_count_cache: dict[Path, int] = {}
  link_count = 0
  line_reference_count = 0
  for source in sources:
    text = source.read_text(encoding="utf-8", errors="replace")
    # 与 V5 同一口径：贴过标签的文档要为自己的链接负责，没贴的只提示。
    governed = not config.is_gradual or not parse_frontmatter(source, config).absent
    link_count += audit_relative_links(
        source, text, result, root, line_count_cache, governed
    )
    line_reference_count += audit_docs_line_references(
        source, text, result, root, docs_dir, line_count_cache, config
    )
  result.checked = (
      f"{len(sources)} 篇 Markdown，{link_count} 个相对链接，"
      f"{line_reference_count} 个 {config.docs_root}/...:line 引用"
  )
  return result


def document_status(path: Path) -> str:
  """返回文档自身声明的 status（小写）；无 frontmatter 或未声明时返回空串。"""
  value = parse_frontmatter(path).values.get("status")
  return str(value).strip().casefold() if isinstance(value, str) else ""


def last_reviewed_date(frontmatter: Frontmatter) -> date | None:
  """取出可比较的 last_reviewed；非法或缺失返回 None（由 V5 负责报错）。"""
  value = frontmatter.values.get("last_reviewed")
  if type(value) is date:
    return value
  if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
    try:
      return date.fromisoformat(value.strip())
    except ValueError:
      return None
  return None


def navigation_links(
    docs_dir: Path, config: GovernanceConfig | None = None
) -> Iterator[tuple[Path, int, str, Path]]:
  """遍历各级 README 中指向 docs 内 Markdown 的链接。

  产出 (README 路径, 行号, 原始链接文本, 解析后的目标路径)。
  """
  config = _cfg(config)
  resolved_docs = docs_dir.resolve()
  for readme in markdown_files(docs_dir):
    if readme.name.casefold() != config.navigation_readme_filename:
      continue
    # archive/ 下的索引 README 的本职就是列出已归档文档，不能拿「导航不得
    # 指向作废文档」去打它——那正是它该做的事。
    relative = readme.relative_to(docs_dir)
    if relative.parts and relative.parts[0] == config.archive_directory_name:
      continue
    text = readme.read_text(encoding="utf-8", errors="replace")
    for line_number, destination in iter_v10_links(text):
      parts = relative_link_parts(destination)
      if parts is None or parts[0] is None:
        continue
      target = (readme.parent / parts[0]).resolve()
      if target.suffix.lower() != ".md" or not target.is_file():
        continue
      if not target.is_relative_to(resolved_docs):
        continue
      yield readme, line_number, destination, target


def audit_v11(
    root: Path,
    config: GovernanceConfig | None = None,
    today: date | None = None,
) -> GateResult:
  """V11 防腐烂：导航与标签互检判失败；久未复核与孤儿文档只提示。

  分级的理由见 ``GateResult.notice``：能明确指认「谁和谁打架」的判失败，
  只能表达「这里可能变味了」的一律降级，否则门禁会被整个关掉。
  """
  config = _cfg(config)
  docs_dir = root / config.docs_root
  result = GateResult("V11", f"{config.docs_root}:1", "0 篇受治理文档")
  if not docs_dir.is_dir():
    return result
  if yaml is None:
    detail = f"：{YAML_IMPORT_ERROR}" if YAML_IMPORT_ERROR else ""
    result.add(docs_dir, 1, f"缺少 PyYAML 依赖，无法执行防腐烂检查{detail}", root)
    return result

  today = today or date.today()
  resolved_docs = docs_dir.resolve()
  linked: set[Path] = set()

  # T12：导航与标签互检。README 把一篇文档列为可读入口，而该文档自称已作废，
  # 两者必有一错——正是「导航过期藏不住，标签错误也藏不住」。
  for readme, line_number, destination, target in navigation_links(
      docs_dir, config
  ):
    linked.add(target)
    status = document_status(target)
    if status in config.historical_statuses:
      result.add(
          readme,
          line_number,
          f"导航仍指向已作废文档：{destination}"
          f"（{display_path(target, root)} 自称 status={status}）",
          root,
      )

  governed = 0
  for path in markdown_files(docs_dir):
    relative = path.relative_to(docs_dir)
    if relative.parts and relative.parts[0] == config.archive_directory_name:
      continue
    frontmatter = parse_frontmatter(path)
    # 未纳入治理的文档谈不上「该被导航到」「该被复核」，不在本门范围内。
    if frontmatter.absent or frontmatter.error:
      continue
    governed += 1

    # T11 孤儿：没有任何 README 能走到它。豁免——
    #   README 自身是导航本身；docs 根下文档直接可见；
    #   所在目录压根没有 README 时，「这个目录还没建导航」由 V4 提示一次即可，
    #   在这里对该目录每一篇文档各报一次，只是把同一件事说 N 遍。
    # 已作废文档同样不报：它们本来就不该被导航链接（链接了会触发上面的
    # 互检失败），劝人「加进 README」等于劝人去踩另一个错。
    status = document_status(path)
    is_navigation = path.name.casefold() == config.navigation_readme_filename
    directory_has_navigation = any(
        sibling.name.casefold() == config.navigation_readme_filename
        for sibling in path.parent.iterdir()
        if sibling.is_file()
    )
    if (
        not is_navigation
        and status not in config.historical_statuses
        and directory_has_navigation
        and path.resolve() not in linked
        and path.parent.resolve() != resolved_docs
    ):
      result.notice(
          path,
          1,
          "孤儿文档：所在目录的 README 没有链接到它，"
          "读者只能靠全文检索撞见。下一步：把它加入该目录 README 的导航",
          root,
      )

    # T11 久未复核。
    reviewed = last_reviewed_date(frontmatter)
    if reviewed is not None:
      age = (today - reviewed).days
      if age > config.last_reviewed_max_age_days:
        result.notice(
            path,
            frontmatter.fields.get("last_reviewed", 1),
            f"已 {age} 天未复核（阈值 {config.last_reviewed_max_age_days} 天）。"
            "下一步：复核内容仍然有效后，把 last_reviewed 更新为复核当天日期",
            root,
        )

  result.checked = f"{governed} 篇受治理文档"
  return result


def framework_roots(
    docs_dir: Path, config: GovernanceConfig | None = None
) -> list[Path]:
  """递归寻找任务框架根：包含状态文件（config.status_file_name）的目录。

  evidence 目录整体剪枝：归档的运行产物里即使复制了一份状态文件，
  也不构成一个新的框架根。找不到任何框架根时 V12/V13 不适用。
  """
  config = _cfg(config)
  roots: list[Path] = []
  for current, directory_names, file_names in os.walk(docs_dir):
    directory_names[:] = sorted(
        name
        for name in directory_names
        if not is_ignored_tool_directory(name, config)
        and name.casefold() != config.evidence_directory_name
    )
    if config.status_file_name in file_names:
      roots.append(Path(current))
  return roots


def framework_markdown_files(
    framework_root: Path, config: GovernanceConfig | None = None
) -> list[Path]:
  """框架根及其下全部 Markdown，排除 evidence 目录与工具缓存目录。"""
  config = _cfg(config)
  found: list[Path] = []
  for current, directory_names, file_names in os.walk(framework_root):
    directory_names[:] = sorted(
        name
        for name in directory_names
        if not is_ignored_tool_directory(name, config)
        and name.casefold() != config.evidence_directory_name
    )
    for name in sorted(file_names):
      if name.lower().endswith(".md"):
        found.append(Path(current) / name)
  return found


def framework_evidence_directory(
    framework_root: Path, config: GovernanceConfig | None = None
) -> Path | None:
  """返回框架根的 evidence 直接子目录；不存在返回 None。"""
  config = _cfg(config)
  for child in sorted(framework_root.iterdir()):
    if child.is_dir() and child.name.casefold() == config.evidence_directory_name:
      return child
  return None


def budget_approval_line(status_text: str, check_key: str) -> str | None:
  """在状态文件中寻找对应检查键的 `批准:` 放行行。

  检查键按独立 token 匹配（前后不是字母数字、下划线或连字符），
  避免 `批准: evidence-files ...` 顺带放行 `files`。
  """
  key_re = re.compile(
      rf"(?<![A-Za-z0-9_-]){re.escape(check_key)}(?![A-Za-z0-9_-])"
  )
  for line in status_text.splitlines():
    stripped = line.strip()
    if stripped.startswith("批准:") and key_re.search(stripped):
      return stripped
  return None


def audit_v12(root: Path, config: GovernanceConfig | None = None) -> GateResult:
  """V12 任务框架预算：框架文档与 evidence 体量必须留在预算内。

  软阈值超限只提示；硬阈值超限判失败，除非状态文件中有以 `批准:` 开头
  且含对应检查键（lines / files / evidence-files / evidence-runs）的行——
  预算的目的不是禁止大框架，而是让「变大」成为一次显式决定，
  留下一行可追溯的批准记录。
  """
  config = _cfg(config)
  docs_dir = root / config.docs_root
  result = GateResult("V12", f"{config.docs_root}:1", "0 个任务框架根")
  if not docs_dir.is_dir():
    return result
  roots = framework_roots(docs_dir, config)

  for framework_root in roots:
    status_file = framework_root / config.status_file_name
    status_text = status_file.read_text(encoding="utf-8", errors="replace")

    def check_budget(
        anchor: Path,
        check_key: str,
        label: str,
        measured: int,
        soft: int,
        hard: int,
        unit: str,
        status_text: str = status_text,
    ) -> None:
      """软阈值超限只提示；硬阈值超限按有无批准行分流。"""
      if measured > hard:
        approved = budget_approval_line(status_text, check_key)
        if approved is not None:
          result.notice(
              anchor,
              1,
              f"{label}超硬阈值（实测 {measured} {unit} > {hard}），"
              f"已由状态文件批准放行：{approved}。"
              "下一步：定期复核该批准行，不再成立时删除以恢复预算约束",
              root,
          )
        else:
          result.add(
              anchor,
              1,
              f"{label}超硬阈值（检查键 {check_key}）："
              f"实测 {measured} {unit} > {hard}（软阈值 {soft}）；"
              f"确属必要时在状态文件写一行"
              f" `批准: {check_key} <原因> <日期>` 可放行",
              root,
          )
      elif measured > soft:
        result.notice(
            anchor,
            1,
            f"{label}超软阈值（检查键 {check_key}）："
            f"实测 {measured} {unit} > {soft}（硬阈值 {hard}）。"
            "下一步：精简或归档超预算内容，确需超限时在状态文件写一行"
            f" `批准: {check_key} <原因> <日期>` 为硬阈值预先放行",
            root,
        )

    markdown = framework_markdown_files(framework_root, config)
    total_lines = 0
    for path in markdown:
      with path.open("r", encoding="utf-8", errors="replace") as handle:
        total_lines += sum(1 for _ in handle)
    check_budget(
        status_file,
        "lines",
        "框架 Markdown 总行数",
        total_lines,
        config.framework_lines_soft_limit,
        config.framework_lines_hard_limit,
        "行",
    )
    check_budget(
        status_file,
        "files",
        "框架 Markdown 文件数",
        len(markdown),
        config.framework_files_soft_limit,
        config.framework_files_hard_limit,
        "个",
    )

    evidence_dir = framework_evidence_directory(framework_root, config)
    if evidence_dir is None:
      continue
    evidence_files = sum(
        1 for path in evidence_dir.rglob("*") if path.is_file()
    )
    check_budget(
        evidence_dir,
        "evidence-files",
        f"{config.evidence_directory_name} 文件总数",
        evidence_files,
        config.evidence_files_soft_limit,
        config.evidence_files_hard_limit,
        "个",
    )
    for task_dir in sorted(
        child for child in evidence_dir.iterdir() if child.is_dir()
    ):
      run_count = sum(1 for child in task_dir.iterdir() if child.is_dir())
      check_budget(
          task_dir,
          "evidence-runs",
          f"{config.evidence_directory_name}/{task_dir.name} 的运行子目录数",
          run_count,
          config.evidence_runs_soft_limit,
          config.evidence_runs_hard_limit,
          "个",
      )

  result.checked = f"{len(roots)} 个任务框架根"
  return result


REGISTRY_HEADER_CELLS = ["id", "status", "updated_at"]
REGISTRY_SEPARATOR_CELL_RE = re.compile(r":?-+:?")


def registry_table_cells(line: str) -> list[str]:
  """把 Markdown 表行拆成去空白单元格；容忍两端竖线的有无。"""
  stripped = line.strip()
  if stripped.startswith("|"):
    stripped = stripped[1:]
  if stripped.endswith("|"):
    stripped = stripped[:-1]
  return [cell.strip() for cell in stripped.split("|")]


def strip_code_span(cell: str) -> str:
  """剥掉单元格外层的一对反引号：`PASS` 与 PASS 同义。"""
  if len(cell) >= 2 and cell.startswith("`") and cell.endswith("`"):
    return cell[1:-1].strip()
  return cell


def audit_v13(root: Path, config: GovernanceConfig | None = None) -> GateResult:
  """V13 状态登记表：状态只准记录在状态文件的登记表里。

  三层检查（对每个任务框架根）：
    1. 状态文件必须恰好包含一张表头为 id | status | updated_at 的登记表；
    2. 表行 id 不得重复、status 必须属于 config.status_registry_statuses 枚举；
    3. 绊线：框架根下其他 Markdown（排除状态文件与 evidence 目录）正文中
       出现枚举的独立大写 token 即报错。这是绊线不是语义保证——只能证明
       状态词出现在了登记表之外，不能证明它是一条状态记录；fenced code
       block 视为示例不扫，行内代码照扫。
  """
  config = _cfg(config)
  docs_dir = root / config.docs_root
  result = GateResult("V13", f"{config.docs_root}:1", "0 个任务框架根")
  if not docs_dir.is_dir():
    return result
  roots = framework_roots(docs_dir, config)
  allowed = sorted(config.status_registry_statuses)

  for framework_root in roots:
    status_file = framework_root / config.status_file_name
    status_text = status_file.read_text(encoding="utf-8", errors="replace")
    visible_lines = list(iter_non_fenced_lines(status_text))
    header_lines = [
        line_number
        for line_number, line in visible_lines
        if "|" in line
        and [cell.casefold() for cell in registry_table_cells(line)]
        == REGISTRY_HEADER_CELLS
    ]

    if not header_lines:
      result.add(
          status_file,
          1,
          "状态文件缺少状态登记表：需要恰好一张表头为"
          " id | status | updated_at 的 Markdown 表",
          root,
      )
    elif len(header_lines) > 1:
      result.add(
          status_file,
          header_lines[1],
          f"状态登记表必须恰好一个，实际发现 {len(header_lines)} 个"
          f"（表头行 {', '.join(str(item) for item in header_lines)}）",
          root,
      )
    else:
      seen_ids: dict[str, int] = {}
      for line_number, line in visible_lines:
        if line_number <= header_lines[0]:
          continue
        if "|" not in line:
          break
        cells = registry_table_cells(line)
        if cells and all(
            REGISTRY_SEPARATOR_CELL_RE.fullmatch(cell) for cell in cells
        ):
          continue
        row_id = strip_code_span(cells[0]) if cells else ""
        row_status = strip_code_span(cells[1]) if len(cells) > 1 else ""
        if row_id in seen_ids:
          result.add(
              status_file,
              line_number,
              f"状态登记表 id 重复：{row_id or '空'}"
              f"（首次出现于第 {seen_ids[row_id]} 行）",
              root,
          )
        else:
          seen_ids[row_id] = line_number
        if row_status not in config.status_registry_statuses:
          result.add(
              status_file,
              line_number,
              f"状态登记表 status 取值非法：{row_status or '空'}；"
              f"可选值：{', '.join(allowed)}",
              root,
          )

    # 绊线：登记表之外的状态词。只扫正文——frontmatter 是受治理的元数据，
    # 不在「状态只准记录于登记表」的射程内。
    for path in framework_markdown_files(framework_root, config):
      if path == status_file:
        continue
      text = path.read_text(encoding="utf-8", errors="replace")
      lines = text.splitlines()
      body_start_line = 0
      if lines and starts_frontmatter(lines[0]):
        closing_index = next(
            (
                index
                for index in range(1, len(lines))
                if lines[index].strip() == "---"
            ),
            None,
        )
        if closing_index is not None:
          body_start_line = closing_index + 1
      for line_number, line in iter_non_fenced_lines(text):
        if line_number <= body_start_line:
          continue
        tokens = config.status_registry_token_re.findall(line)
        if tokens:
          result.add(
              path,
              line_number,
              "状态只准记录于状态文件的登记表，此处出现状态词："
              f"{', '.join(dict.fromkeys(tokens))}（绊线检查，不做语义判断）",
              root,
          )

  result.checked = f"{len(roots)} 个任务框架根"
  return result


AUDITORS = {
    "V2": audit_v2,
    "V4": audit_v4,
    "V5": audit_v5,
    "V9": audit_v9,
    "V10": audit_v10,
    "V11": audit_v11,
    "V12": audit_v12,
    "V13": audit_v13,
}


def print_result(result: GateResult) -> None:
  """输出稳定、可被 CI 阅读的 gate 结果。提示不影响 PASS/FAIL 判定。"""
  issues = sorted(set(result.issues))
  notices = sorted(set(result.notices))
  suffix = f"；{len(notices)} 条提示" if notices else ""
  if issues:
    print(
        f"{result.gate} FAIL {result.anchor} - "
        f"{len(issues)} 个问题；已检查 {result.checked}{suffix}"
    )
    for issue in issues:
      print(f"  {issue.path}:{issue.line} - {issue.message}")
  else:
    print(
        f"{result.gate} PASS {result.anchor} - 已检查 {result.checked}{suffix}"
    )
  for note in notices:
    print(f"  提示 {note.path}:{note.line} - {note.message}")
