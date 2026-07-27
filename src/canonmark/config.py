"""canonmark 治理配置。

这里把审计器里所有「项目特有」的常量收敛成一个可配置的 ``GovernanceConfig``。

设计约束（来自 agong 抽取）：所有字段的**默认值逐字等于 agong 原审计器的现值**，
从而保证「不给配置」时行为与原 ``docs-audit.py`` 零漂移，42 个迁移单测无需改断言。

治理词汇表（status / current_authority 的取值集合与合法矩阵）默认取通用治理模型，
不是某个公司的品牌，正常项目直接沿用默认即可；但仍作为字段暴露，翻转配置能改变行为、
不静默失效。项目差异化的部分只有：docs 根名、目录白名单、固定关键文档清单、命名正则族。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping


ADOPTION_MODES = frozenset({"gradual", "strict"})


def _default_status_authority_matrix() -> dict[str, frozenset[str]]:
  """status -> 合法 current_authority 集合（治理模型词汇表）。

  等价于原审计器 ``authority_matches_status`` 的判定：
  current 允许除 historical-evidence 外的一切；background 允许背景/历史；
  archive / superseded 只允许 historical-evidence。
  """
  return {
      "current": frozenset(
          {
              "roadmap-current",
              "task-current",
              "contract-current",
              "acceptance-current",
              "background-reference",
          }
      ),
      "background": frozenset(
          {"background-reference", "historical-evidence"}
      ),
      "archive": frozenset({"historical-evidence"}),
      "superseded": frozenset({"historical-evidence"}),
  }


@dataclass
class GovernanceConfig:
  """一次审计运行的全部可配置项。

  正则类字段存**源字符串**，在 ``__post_init__`` 中编译为私有的已编译对象，
  这样配置既能被 YAML / TOML 序列化，又不必在每次匹配时重复编译。
  """

  # ---- 采用模式 ----------------------------------------------------------
  # 决定「尚未治理」的部分怎么处理。一句话原则：**没做的事不罚，做错的事才罚。**
  #   gradual（默认）：只治理已经表达了治理意图的部分——写了 frontmatter 的文档、
  #     已经存在的 README。缺 frontmatter、缺导航一律降级为提示，不判失败。
  #     这样任何存量项目装上都不会当场变红，可以从一篇文档开始逐步纳入。
  #   strict：结构性缺失同样判失败，适合已完成治理的库（canonmark 自身、agong）。
  # 无论哪种模式，「已经贴了标签却写错」始终判失败——那是做错，不是没做。
  adoption_mode: str = "gradual"

  # ---- V11 防腐烂检查 ----------------------------------------------------
  # last_reviewed 超过多少天算「久未复核」。**只提示，永远不判失败**：
  # 时间触发的失败会让全库在某天突然变红而当天无人改动，团队的第一反应是
  # 关掉整个门禁，与目的正相反。
  last_reviewed_max_age_days: int = 180

  # ---- docs 根与目录命名 -------------------------------------------------
  docs_root: str = "docs"
  archive_directory_name: str = "archive"
  evidence_directory_name: str = "evidence"
  tasks_directory_name: str = "tasks"
  ignored_directory_names: frozenset[str] = frozenset(
      {"__pycache__", ".git", ".tox", ".nox"}
  )
  abnormal_top_level_names: frozenset[str] = frozenset(
      {"doc", "docs", "documentation"}
  )
  # V2 目录命名白名单（产品代号 / 元目录例外）。默认留空，与
  # required_key_documents 同理：白名单天生项目特有，给具体默认值只会把某个
  # 项目的目录名印进所有陌生项目的报错文案里。使用方在自己的配置里声明。
  v2_path_exceptions: tuple[str, ...] = ()
  # 目录命名规则：默认 kebab-case。
  directory_name_regex: str = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
  # 命名规则的人类可读标签，仅用于 V2 报错文案。
  directory_name_label: str = "kebab-case"

  # ---- V5 frontmatter 契约主体 ------------------------------------------
  required_frontmatter_fields: tuple[str, ...] = (
      "status",
      "applies_when",
      "not_for",
      "current_authority",
      "supersedes",
      "superseded_by",
      "owner",
      "last_reviewed",
  )
  allowed_statuses: frozenset[str] = frozenset(
      {"current", "background", "archive", "superseded"}
  )
  # 「不再算数」的状态：默认不加载正文，导航也不该把它们列为可读入口（V11/T12）。
  historical_statuses: frozenset[str] = frozenset({"archive", "superseded"})
  allowed_authorities: frozenset[str] = frozenset(
      {
          "roadmap-current",
          "task-current",
          "contract-current",
          "acceptance-current",
          "background-reference",
          "historical-evidence",
      }
  )
  # status -> 合法 current_authority 集合。翻转此矩阵即改变冲突判定，不静默失效。
  status_authority_matrix: dict[str, frozenset[str]] = field(
      default_factory=_default_status_authority_matrix
  )
  # technical-plan 分片严格映射里 background / 历史两态的目标 authority。
  technical_plan_background_authority: str = "background-reference"
  technical_plan_historical_authority: str = "historical-evidence"

  # ---- 关键文档识别正则族（中英） ---------------------------------------
  key_document_signal_regex: str = (
      r"(唯一权威|权威入口|当前权威|实时状态|执行入口|主真相源|"
      r"本文件.{0,24}(?:验收标准|执行契约|任务账本|路线图)|"
      r"冲突时以.{0,40}为准|必须按本文|Definition of Done|完成定义)"
  )
  key_document_title_regex: str = (
      r"(执行计划|\bimplementation\s+plan\b|设计方案|\bdesign\b|"
      r"roadmap|路线图|\bcontract\b|契约|\btask\b|任务|"
      r"\bacceptance\b|验收|\bstandard\b|规范|\bsecurity\b|"
      r"\brca\b|\brollout\b)"
  )
  key_document_filename_regex: str = (
      r"(设计(?:文档|方案|入口)?|契约|任务分片|执行计划|"
      r"验收(?:矩阵|标准|门禁)|路线图|规范|执行总账|任务账本|"
      r"(?:^|[-_.])(?:design|contract|roadmap|task[-_.]?shard|"
      r"acceptance[-_.]?(?:matrix|criteria)|security|rca|"
      r"rollout[-_.]?status|standard|execution[-_.]?ledger)"
      r"(?:[-_.]|$))"
  )
  key_document_directory_names: frozenset[str] = frozenset(
      {"design", "tasks", "gates"}
  )
  # (authority, 源正则) 列表：命中即判定技术方案分片的期望 authority。
  technical_plan_authority_patterns: tuple[tuple[str, str], ...] = (
      ("roadmap-current", r"(roadmap|路线图)"),
      ("contract-current", r"(\bcontract\b|契约)"),
      ("task-current", r"\btask\s+shard\b"),
      ("acceptance-current", r"(acceptance\s+matrix|验收矩阵)"),
  )
  acceptance_matrix_stem_regex: str = r"(?:^|_)acceptance_matrix(?:_|$)"
  task_shard_identity_regex: str = (
      r"(task\s+shard|任务分片|implementation\s+plan|"
      r"实现计划|实施计划|执行计划)"
  )
  # tasks/ 目录内任务文件名前缀（agong 现值容忍历史 agent_ 前缀）。
  task_file_prefix_regex: str = r"^(?:agent[-_.]?)?t\d+(?:[-_.]|$)"

  # ---- 导航文件名 -------------------------------------------------------
  navigation_readme_filename: str = "readme.md"
  legacy_navigation_filenames: frozenset[str] = frozenset({"readmap.md"})

  # ---- 模板识别 ---------------------------------------------------------
  template_directory_names: frozenset[str] = frozenset({"templates"})
  template_filename_suffixes: tuple[str, ...] = (
      ".template",
      "-template",
      "_template",
      "模板",
  )

  # ---- 固定关键文档（V5 显式必备清单） ----------------------------------
  # 「哪些文档必须存在」天生是项目特有的，没有通用默认值可言：给出任何具体清单，
  # 都会让陌生项目一装上就报「固定关键文档不存在」。默认留空 = 不强制任何文档存在，
  # 项目在自己的配置里声明（canonmark 见仓库根 canonmark.toml，agong 见其自有配置）。
  required_key_documents: tuple[str, ...] = ()
  required_key_document_globs: tuple[str, ...] = ()

  # ---- 前瞻字段（供后续 hook 使用，当前审计逻辑不消费） -----------------
  # 触发治理的路径前缀：改动落在这些前缀下才需要跑门禁。
  trigger_paths: tuple[str, ...] = ("docs/",)
  # 审计器自身安家的位置（相对仓库根），供 hook 定位脚本。
  auditor_home: str = "."

  def __post_init__(self) -> None:
    """把源正则字符串编译为已编译对象，并派生依赖 docs_root 的正则。"""
    if self.adoption_mode not in ADOPTION_MODES:
      allowed = ", ".join(sorted(ADOPTION_MODES))
      raise ValueError(
          f"adoption_mode 取值非法：{self.adoption_mode!r}；可选值：{allowed}"
      )
    self._directory_name_re = re.compile(self.directory_name_regex)
    self._key_document_signal_re = re.compile(
        self.key_document_signal_regex, re.IGNORECASE
    )
    self._key_document_title_re = re.compile(
        self.key_document_title_regex, re.IGNORECASE
    )
    self._key_document_filename_re = re.compile(
        self.key_document_filename_regex, re.IGNORECASE
    )
    self._acceptance_matrix_re = re.compile(self.acceptance_matrix_stem_regex)
    self._task_shard_identity_re = re.compile(
        self.task_shard_identity_regex, re.IGNORECASE
    )
    self._task_file_prefix_re = re.compile(
        self.task_file_prefix_regex, re.IGNORECASE
    )
    self._technical_plan_authority_patterns = tuple(
        (authority, re.compile(source, re.IGNORECASE))
        for authority, source in self.technical_plan_authority_patterns
    )
    # docs/...:line 显式引用正则，随 docs_root 变化而重建。
    root = re.escape(self.docs_root)
    self._docs_line_reference_re = re.compile(
        r"(?<![A-Za-z0-9_./-])"
        rf"({root}/[^\s`'\"<>|:()\[\]{{}}]+)"
        r":([0-9]+)(?:-([0-9]+))?"
    )

  # ---- 只读访问器（审计逻辑通过这些拿已编译正则） -----------------------
  @property
  def is_gradual(self) -> bool:
    """是否处于渐进采用模式：结构性缺失降级为提示。"""
    return self.adoption_mode == "gradual"

  @property
  def directory_name_re(self) -> re.Pattern[str]:
    return self._directory_name_re

  @property
  def key_document_signal_re(self) -> re.Pattern[str]:
    return self._key_document_signal_re

  @property
  def key_document_title_re(self) -> re.Pattern[str]:
    return self._key_document_title_re

  @property
  def key_document_filename_re(self) -> re.Pattern[str]:
    return self._key_document_filename_re

  @property
  def acceptance_matrix_re(self) -> re.Pattern[str]:
    return self._acceptance_matrix_re

  @property
  def task_shard_identity_re(self) -> re.Pattern[str]:
    return self._task_shard_identity_re

  @property
  def task_file_prefix_re(self) -> re.Pattern[str]:
    return self._task_file_prefix_re

  @property
  def compiled_technical_plan_authority_patterns(
      self,
  ) -> tuple[tuple[str, re.Pattern[str]], ...]:
    return self._technical_plan_authority_patterns

  @property
  def docs_line_reference_re(self) -> re.Pattern[str]:
    return self._docs_line_reference_re

  def authority_allowed_for_status(self, status: str, authority: str) -> bool:
    """status 与 current_authority 是否相容（读 status_authority_matrix）。"""
    return authority in self.status_authority_matrix.get(status, frozenset())


def _coerce(default_value: Any, value: Any) -> Any:
  """按默认字段的容器类型，把 YAML / TOML 读来的值归一化。"""
  if isinstance(default_value, tuple):
    # 可能是 (str, ...) 或 ((authority, regex), ...) 这样的嵌套。
    return tuple(
        tuple(item) if isinstance(item, (list, tuple)) else item
        for item in value
    )
  if isinstance(default_value, frozenset):
    return frozenset(value)
  if isinstance(default_value, dict):
    return {
        key: frozenset(inner)
        if isinstance(inner, (list, tuple, set))
        else inner
        for key, inner in value.items()
    }
  return value


def _load_mapping(path: Path) -> Mapping[str, Any]:
  """按扩展名读取 YAML / TOML 配置文件为字典。"""
  suffix = path.suffix.lower()
  text = path.read_text(encoding="utf-8")
  if suffix in {".yaml", ".yml"}:
    return _load_yaml(text, path)
  if suffix == ".toml":
    return _load_toml(text, path)
  # 未知扩展名：优先 YAML，再退回 TOML。
  try:
    return _load_yaml(text, path)
  except Exception:
    return _load_toml(text, path)


def _load_yaml(text: str, path: Path) -> Mapping[str, Any]:
  try:
    import yaml
  except ImportError as error:  # pragma: no cover - 环境缺依赖时的清晰报错
    raise RuntimeError(
        f"读取 YAML 配置 {path} 需要 PyYAML，请先安装：pip install PyYAML"
    ) from error
  loaded = yaml.safe_load(text) or {}
  if not isinstance(loaded, dict):
    raise ValueError(f"配置文件顶层必须是键值映射：{path}")
  return loaded


def _load_toml(text: str, path: Path) -> Mapping[str, Any]:
  try:
    import tomllib  # Python 3.11+
  except ImportError:  # pragma: no cover - 老 Python 回退
    try:
      import tomli as tomllib  # type: ignore
    except ImportError as error:
      raise RuntimeError(
          f"读取 TOML 配置 {path} 需要 Python 3.11+ 或 tomli 包"
      ) from error
  loaded = tomllib.loads(text)
  if not isinstance(loaded, dict):
    raise ValueError(f"配置文件顶层必须是键值映射：{path}")
  return loaded


def load_config(path: str | Path | None = None) -> GovernanceConfig:
  """加载配置：path 为空返回默认；否则读 YAML / TOML 覆盖字段。

  未知字段直接忽略（宽容前向兼容）；已知字段按其默认容器类型归一化。
  """
  if path is None:
    return GovernanceConfig()
  config_path = Path(path).expanduser()
  if not config_path.is_file():
    raise FileNotFoundError(f"配置文件不存在：{config_path}")

  overrides = _load_mapping(config_path)
  reference = GovernanceConfig()
  known = {f.name for f in fields(GovernanceConfig)}
  kwargs: dict[str, Any] = {}
  for key, value in overrides.items():
    if key not in known:
      continue
    kwargs[key] = _coerce(getattr(reference, key), value)
  return GovernanceConfig(**kwargs)


# 默认配置单例：审计函数在未显式传 config 时回退到它（= agong 现值，零漂移）。
DEFAULT_CONFIG = GovernanceConfig()
