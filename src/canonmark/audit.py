"""canonmark 只读文档审计器（五门）。

从 agong ``docs-audit.py`` 抽取而来。所有原来读模块级项目常量的地方，
都改成读传入的 :class:`~canonmark.config.GovernanceConfig`；未显式传 config 时
回退到 :data:`~canonmark.config.DEFAULT_CONFIG`（= agong 现值，零漂移）。

五门：
  V2  目录命名（kebab-case + 白名单 + archive 历史豁免）
  V4  含 ≥2 文件的非纯资产目录必须有 README
  V5  关键文档 frontmatter 契约（本模块最大的一块）
  V9  总导航必须链接全部正式顶层目录
  V10 活文档相对链接与 docs/...:line 引用不得断
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


SUPPORTED_GATES = ("V2", "V4", "V5", "V9", "V10")
# Markdown 结构性正则（与项目无关，保持模块常量）。
REFERENCE_DEFINITION_RE = re.compile(
    r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|[^\s]+)"
)
LINE_FRAGMENT_RE = re.compile(r"^L([0-9]+)(?:-L([0-9]+))?$", re.IGNORECASE)
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


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

  def add(self, path: Path | str, line: int, message: str, root: Path) -> None:
    """加入问题，并统一输出仓库相对路径。"""
    self.issues.append(
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


def parse_frontmatter(path: Path) -> Frontmatter:
  """用 PyYAML 解析顶部 frontmatter，并拒绝重复一级字段。"""
  lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
  if not lines or lines[0].strip() != "---":
    return Frontmatter({}, {}, None, "缺少顶部 YAML frontmatter", 1)

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
  if lines and lines[0].strip() == "---":
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
  if lines and lines[0].strip() == "---":
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
  if not lines or lines[0].strip() != "---":
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
      result.add(
          directory,
          1,
          f"直接含 {len(direct_files)} 个文件且包含 Markdown，缺少 README.md",
          root,
      )
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
  """V5：关键文档必须在顶部 frontmatter 中包含必备字段。"""
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

  for path in all_markdown:
    if path.is_relative_to(docs_dir / config.archive_directory_name):
      continue
    text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(path)
    lines = text.splitlines()
    if (
        lines
        and lines[0].strip() == "---"
        and frontmatter.error is not None
    ):
      malformed_frontmatter_documents.add(path)
    if (
        is_key_document(path, docs_dir, frontmatter, text, config)
        or technical_plan_expected_authority(path, text, config) is not None
    ):
      key_documents.add(path)

  for path in sorted(key_documents | malformed_frontmatter_documents):
    if not path.is_file():
      result.add(path, 1, "固定关键文档不存在", root)
      continue
    frontmatter = parse_frontmatter(path)
    if frontmatter.error:
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
              f"superseded_by 目标不存在：{target_value}",
              root,
          )
        elif target.name.casefold() != "readme.md":
          target_frontmatter = parse_frontmatter(target)
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
            result.add(
                path,
                frontmatter.fields["superseded_by"],
                "superseded_by 非 README 目标无法执行五步门禁："
                f"{target_value}（{detail}）",
                root,
            )
      cycle = superseded_cycle(path, root, docs_dir, config)
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
  result.checked = f"{len(key_documents)} 篇关键文档"
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
) -> int:
  """检查 Markdown/HTML 相对链接及行号 fragment，返回链接数量。"""
  link_count = 0
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
      result.add(
          source,
          line_number,
          f"相对链接目标不存在：{destination} "
          f"(解析为 {display_path(target, root)})",
          root,
      )
      continue
    fragment_issue = markdown_line_fragment_issue(
        target, fragment, line_count_cache
    )
    if fragment_issue:
      result.add(
          source,
          line_number,
          f"相对链接 {fragment_issue}：{destination}",
          root,
      )
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
    link_count += audit_relative_links(
        source, text, result, root, line_count_cache
    )
    line_reference_count += audit_docs_line_references(
        source, text, result, root, docs_dir, line_count_cache, config
    )
  result.checked = (
      f"{len(sources)} 篇 Markdown，{link_count} 个相对链接，"
      f"{line_reference_count} 个 {config.docs_root}/...:line 引用"
  )
  return result


AUDITORS = {
    "V2": audit_v2,
    "V4": audit_v4,
    "V5": audit_v5,
    "V9": audit_v9,
    "V10": audit_v10,
}


def print_result(result: GateResult) -> None:
  """输出稳定、可被 CI 阅读的 gate 结果。"""
  issues = sorted(set(result.issues))
  if not issues:
    print(f"{result.gate} PASS {result.anchor} - 已检查 {result.checked}")
    return
  print(
      f"{result.gate} FAIL {result.anchor} - "
      f"{len(issues)} 个问题；已检查 {result.checked}"
  )
  for issue in issues:
    print(f"  {issue.path}:{issue.line} - {issue.message}")
