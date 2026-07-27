"""canonmark：给 docs/ 一个可机检的「权威契约」，裁决 AI 该信哪篇文档。

公开入口：
  - :class:`canonmark.config.GovernanceConfig` / :func:`canonmark.config.load_config`
  - :mod:`canonmark.audit` 各门审计函数（门的清单见 ``audit.SUPPORTED_GATES``）
  - :func:`canonmark.read.read_document` 按权威契约交付（或扣下）正文
  - :func:`canonmark.index.build_index` 紧凑的标签清单
  - :func:`canonmark.mcp.serve` MCP server（stdio）
  - :func:`canonmark.cli.main` 命令行入口（``canon``）
"""

from __future__ import annotations

from .config import DEFAULT_CONFIG, GovernanceConfig, load_config

__all__ = ["DEFAULT_CONFIG", "GovernanceConfig", "load_config", "__version__"]

__version__ = "0.1.0"
