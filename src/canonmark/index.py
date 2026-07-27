"""`canon index`：按需的全局清单，**不是**读文档的必经路径。

protocol §7.5 给了三条硬约束，都是为了不让它变成上下文污染源：
默认一篇一行、不含长描述；必须能过滤；**不得**写进「每次读文档前先执行」这类
接线指引。早期设计曾把全库索引当默认路径，已废止——对中大型文档库，一次返回
整库标签比逐层 README 导航贵得多，与「按需加载」的初衷直接冲突。

它的正当用途是跨目录检索、体检和 CI 报告，即那些确实需要全局视野的场合。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import audit as _audit
from .audit import display_path, markdown_files, parse_frontmatter
from .config import GovernanceConfig, DEFAULT_CONFIG


class IndexUnavailable(RuntimeError):
  """无法读取标签时抛出，而不是安静地把整库标成「无标签」。

  没有 PyYAML 时每一篇都解析不出 status，若照常输出就会得到一份「全库都没
  治理」的清单——`--current-only` 更会安静地回答「没有现行文档」。在这个
  项目里，「解析不出来就当没有」正是最不该犯的错。
  """


@dataclass(frozen=True)
class IndexEntry:
  """索引里的一行。字段刻意少——长描述属于正文，不属于清单。"""

  path: str
  status: str
  authority: str

  def to_line(self) -> str:
    return f"{self.path}\t{self.status}\t{self.authority}"


def _field(values: dict, name: str) -> str:
  """取字段并压成单行。

  字段值来自被审计的文档，是不可信输入：`status` 写成含换行或制表符的 YAML
  块标量时，原样拼进 TSV 会凭空多出几行，且伪造行与真条目长得一模一样——
  下游 agent 无从分辨。「一篇一行」是 protocol §7.5 的硬约束，这里守住它。
  """
  value = values.get(name)
  if not isinstance(value, str):
    return ""
  return " ".join(value.split()).strip()


def build_index(
    root: Path,
    config: GovernanceConfig | None = None,
    directory: str | None = None,
    current_only: bool = False,
) -> list[IndexEntry]:
  """扫描 docs 下的 Markdown，产出紧凑清单。

  ``directory`` 按 docs 根下的相对路径前缀过滤；``current_only`` 只留现行文档。
  """
  config = config if config is not None else DEFAULT_CONFIG
  docs_dir = root / config.docs_root
  if not docs_dir.is_dir():
    return []
  # 通过模块属性读取而非 from-import：后者在导入时就把值绑死，
  # 测试替换 audit.yaml 时这里看不见，守卫会静默失效。
  if _audit.yaml is None:
    detail = f"：{_audit.YAML_IMPORT_ERROR}" if _audit.YAML_IMPORT_ERROR else ""
    raise IndexUnavailable(
        f"缺少 PyYAML 依赖，无法读取文档标签{detail}；"
        "装上 `pip install canonmark[yaml]` 后重试"
    )

  scope = docs_dir if directory is None else (docs_dir / directory)
  resolved_scope = scope.resolve()
  # --dir 越界（`..`、绝对路径）必须报错而不是静默返回整棵树：后者看起来
  # 像「这个目录下就是这些」，读者无从察觉过滤根本没生效。
  if not resolved_scope.is_relative_to(docs_dir.resolve()):
    raise IndexUnavailable(
        f"--dir 越界：{directory} 解析后落在 {config.docs_root}/ 之外"
    )
  if not resolved_scope.is_dir():
    raise IndexUnavailable(f"--dir 指向的目录不存在：{directory}")
  entries: list[IndexEntry] = []
  for path in markdown_files(docs_dir):
    if not path.resolve().is_relative_to(resolved_scope):
      continue
    frontmatter = parse_frontmatter(path)
    if frontmatter.absent or frontmatter.error:
      status, authority = "-", "-"
    else:
      status = _field(frontmatter.values, "status") or "-"
      authority = _field(frontmatter.values, "current_authority") or "-"
    if current_only and status.casefold() != "current":
      continue
    entries.append(IndexEntry(display_path(path, root), status, authority))
  return sorted(entries, key=lambda entry: entry.path)


def render_index(entries: list[IndexEntry], as_json: bool = False) -> str:
  """渲染索引。默认制表符分隔，一篇一行。"""
  if as_json:
    return json.dumps(
        [
            {"path": e.path, "status": e.status, "current_authority": e.authority}
            for e in entries
        ],
        ensure_ascii=False,
        indent=None,
        separators=(",", ":"),
    )
  return "\n".join(entry.to_line() for entry in entries)
