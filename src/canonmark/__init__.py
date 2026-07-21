"""canonmark：给 docs/ 一个可机检的「权威契约」，裁决 AI 该信哪篇文档。

公开入口：
  - :class:`canonmark.config.GovernanceConfig` / :func:`canonmark.config.load_config`
  - :mod:`canonmark.audit` 五门审计函数
  - :func:`canonmark.cli.main` 命令行入口（``canon``）
"""

from __future__ import annotations

from .config import DEFAULT_CONFIG, GovernanceConfig, load_config

__all__ = ["DEFAULT_CONFIG", "GovernanceConfig", "load_config", "__version__"]

__version__ = "0.1.0"
