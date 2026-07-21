---
status: current
applies_when: 判定某个阶段是否真正完成、检查证据是否齐全、决定能否进入下一阶段
not_for: 阶段规划顺序(见 roadmap.md)、任务执行步骤(见 tasks/)
current_authority: acceptance-current
supersedes: []
superseded_by: []
owner: canonmark
last_reviewed: 2026-07-21
---

# canonmark 验收矩阵

结论:每个阶段都有量化验收项。判定五态:`PASS` / `FAIL` / `BLOCKED` / `INSUFFICIENT_EVIDENCE` / `NOT_APPLICABLE`。实现者不得自评 PASS,须独立 subagent 验收。

## 验收项

| ID | 阶段 | 验收项 | 测试命令 | 通过条件 | 证据路径 | 状态 |
|---|---|---|---|---|---|---|
| A0 | P0 | 文档结构齐全且自合规 | `canon audit docs/`(P3 后可跑) | 无缺 README / frontmatter 完整 | docs/progress.md | INSUFFICIENT_EVIDENCE |
| A1 | P1 | 42 单测迁移后零改动全绿 | `python -m pytest tests/ -q` | 42 passed | tests 运行输出 | PENDING |
| A2 | P1 | 默认配置输出与 agong 原版逐字节一致 | 对同一 docs 树跑新旧审计器 diff | 无差异 | 证据文件 | PENDING |
| A3 | P1 | audit_v5 frontmatter 主体已参数化 | 翻转 `required_fields`/`allowed_statuses` 应改变行为 | 行为随配置变 | tests/test_audit.py | PENDING |
| A4 | P2 | src 无 agong 专属依赖 | `grep -ri "gen_diagrams\|sunyur\|agong\|deep_search6" src/` | 仅出现在默认配置值/注释,无代码依赖 | grep 输出 | PENDING |
| A5 | P2 | 纯标准库 + 可选 PyYAML 可跑 | 干净 venv `pip install -e . && canon --help` | 退出码 0 | 安装日志 | PENDING |
| A6 | P3 | canonmark 自审自身全 PASS | `canon audit docs/ --config canonmark.toml` | 五门全 PASS,exit 0 | CI 日志 | PENDING |
| A7 | P3 | pre-commit + CI 各真跑绿一次 | 本地 hook 触发 + CI pipeline | 两条路均绿 | CI pipeline URL | PENDING |
| A8 | P4 | INVALID fixture 精确报中 6 处埋雷 | `canon audit tests/fixtures/invalid --config ...` | 恰好 6 类问题,exit 1 | fixture 报告 | PENDING |
| A9 | P4 | VALID fixture 修好后 exit 0 | 同上,valid 变体 | 全 PASS,exit 0 | fixture 报告 | PENDING |
| A10 | P4 | 改配置不改代码即换项目 | 同 fixture,两份 config 翻转命名口径 | 结果翻转,.py 零改动 | 两份 config + 报告 | PENDING |
| A11 | P4 | 独立 subagent 验收 ACCEPT | 独立 subagent 复核 A1–A10 证据 | verdict = ACCEPT | subagent 报告 | PENDING |
| A12 | P5 | 发布物完整 | 人工核对 README/pyproject/LICENSE | 齐全,可一条命令推送 | — | PENDING |

## 未验证范围(诚实边界)

- GitHub 远程发布(A12 之后)不由 agent 执行,留用户拍板。
- Windows 首跑(CRLF/BOM/反斜杠路径)第一版不覆盖,列入风险。
- agong_server 侧的实际接入(换用 canonmark + 写 agong 配置)不在本项目范围,是 agong 侧后续。
