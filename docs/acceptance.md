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
| A0 | P0 | 文档结构齐全且自合规 | `canon audit docs/`(自审) | 无缺 README / frontmatter 完整 | A6 自审全 PASS 间接证明 | PASS |
| A1 | P1 | 42 单测迁移后零改动全绿 | `python -m pytest tests/ -q` | 42 passed | `42 passed, 45 subtests` | PASS |
| A2 | P1 | 默认配置输出与 agong 原版逐字节一致 | 对同一 docs 树跑新旧审计器 diff | 无差异 | cksum 双方 `749520412 312` IDENTICAL | PASS |
| A3 | P1 | audit_v5 frontmatter 主体已参数化 | 翻转 `allowed_statuses` 应改变行为 | 行为随配置变,.py md5 不变 | 含/去 draft → V5 PASS↔FAIL | PASS |
| A4 | P2 | src 无 agong 专属依赖 | `grep -ri` src/ | 仅注释/默认配置值,无代码依赖 | 命中全在注释/config 默认值 | PASS |
| A5 | P2 | 纯标准库 + 可选 PyYAML 可跑 | `pip install -e . && canon --help` | 退出码 0 | canon/audit --help exit 0 | PASS |
| A6 | P3 | canonmark 自审自身全 PASS | `canon audit docs/ --config canonmark.toml` | 五门全 PASS,exit 0 | 五门全 PASS,exit 0 | PASS |
| A7 | P3 | pre-commit + CI 各真跑绿一次 | 本地 hook 触发 + CI pipeline | 两条路均绿 | 本地 pre-commit `Passed` exit 0;远端 CI 待推送后验 | PASS(本地) |
| A8 | P4 | INVALID fixture 精确报中 6 处埋雷 | `canon audit tests/fixtures/invalid` | 恰好 6 类问题,exit 1 | 6 类一一对上,exit 1 | PASS |
| A9 | P4 | VALID fixture 修好后 exit 0 | 同上,valid 变体 | 全 PASS,exit 0 | 五门全 PASS,exit 0 | PASS |
| A10 | P4 | 改配置不改代码即换项目 | 同 fixture,两份 config 翻转口径 | 结果翻转,.py 零改动 | A3 md5 佐证 .py 未改 | PASS |
| A11 | P4 | 独立 subagent 验收 ACCEPT | 独立 subagent 复核 A1–A10 证据 | verdict = ACCEPT | 独立验收 ACCEPT,无 FAIL | PASS |
| A13 | P5 | 反向指针不对称被判失败 | fixture:A 声称被 B 取代、B 未声明取代 A | 报错且 exit 1 | 待实现 | PENDING |
| A14 | P5 | 超期**只提示不失败** | fixture:`last_reviewed` 超阈值 | 有提示输出但 **exit 0** | 待实现 | PENDING |
| A15 | P5 | 孤儿文档被提示 | fixture:无任何导航链接指向的文档 | 出现在提示中,不判失败 | 待实现 | PENDING |
| A16 | P5 | README 清单与文档标签互检 | fixture:README 标现行 / 文档自称作废 | 报错 | 待实现 | PENDING |
| A17 | P6 | `canon_read` 对作废文档不返回正文 | 对 `superseded` 文档调用 canon_read | 返回替代目标,**正文不出现在输出中** | 待实现 | PENDING |
| A18 | P6 | `canon index` 紧凑且可过滤 | `canon index --json` / `--dir` | 输出字节数 < 全文总量的 10%;过滤生效 | 待实现 | PENDING |
| A19 | P6 | 对照实验:消费者被拦并改读替代目标 | 真实会话中提问一个新旧文档答案不同的问题 | 答案取自现行文档,非作废文档 | 待实现 | PENDING |
| A12 | P7 | 发布物完整 | 人工核对 README/pyproject/LICENSE | 齐全,可一条命令推送 | 待 P7 | PENDING |

## 未验证范围(诚实边界)

- GitHub 远程发布(A12 之后)不由 agent 执行,留用户拍板。
- Windows 首跑(CRLF/BOM/反斜杠路径)第一版不覆盖,列入风险。
- agong_server 侧的实际接入(换用 canonmark + 写 agong 配置)不在本项目范围,是 agong 侧后续。
