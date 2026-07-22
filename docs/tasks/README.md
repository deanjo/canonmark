---
status: current
applies_when: 查看或更新跨会话的任务状态与阶段归属、判断某个任务当前处于哪一步
not_for: 阶段规划顺序(见 roadmap.md)、验收判定(见 acceptance.md)、协议字段定义(见 design/protocol.md)
current_authority: task-current
supersedes: []
superseded_by: []
owner: canonmark
last_reviewed: 2026-07-21
---

# canonmark 任务台账

结论:这是跨会话的任务状态单一事实源。状态五态:TODO / DOING / DONE / BLOCKED / NEEDS-VERIFY。验收判定见 [acceptance.md](../acceptance.md),阶段顺序见 [roadmap.md](../roadmap.md)。

| 任务 | 阶段 | 负责 | 状态 | 证据 / 备注 |
|---|---|---|---|---|
| T0 项目骨架 + 权威文档 | P0 | 主 agent | DONE | git 5e65863;roadmap/acceptance/kickoff/progress/docs-README 已落盘 |
| T1 命名裁决(禁 agent_ 为默认,agong 走例外) | P0 | 主 agent | DONE | 记录在 roadmap.md「命名裁决」 |
| T2 抽取参数化 docs-audit.py → src/canonmark | P1 | 实现 agent | DONE | 1916 行,31 字段;必修全做(audit_v5 主体/L471/词汇表/trigger_paths);独立验收 A1-A3 PASS |
| T3 canonmark.toml 自审配置 | P1 | 实现 agent | DONE | 自审 A6 五门全 PASS exit 0 |
| T4 迁移 42 单测 + 12 文件 fixture | P1/P4 | 实现 agent | DONE | 42 passed;invalid 精确报 6 类 exit1、valid exit0(A8/A9) |
| T5 排除不可移植件(gen_diagrams/task-packet/java) | P2 | 实现 agent | DONE | grep src/ 无代码依赖(A4 PASS) |
| T6 设计文档(vision/protocol)+ README 门面 | P0 | 文档 agent | DONE | vision(305 文件冲突已实测)/protocol(8字段+五步+矩阵)/README 门面已写;3 取舍认同:宽松矩阵不纳 sharding 严子集、不编造 P1 代码行号、无环检测标为待 P1 验;protocol 自洽性并入 T8 复核 |
| T7 自审反馈链路(pre-commit + Action + CI) | P3 | 主 agent | DONE | 4 文件已写;本地 pre-commit 真跑 `Passed` exit 0(A7 本地);远端 CI 待推送后验 |
| T8 独立 subagent 验收 A1–A11 | P4 | 验收 agent | DONE | 独立复现判定 ACCEPT,A1–A11 全 PASS,无 FAIL;含 protocol 自洽核对 |
| T10 反向指针对称检查 → 判失败 | P5 | 待分配 | TODO | **protocol §2/§8 已承诺但代码未实现**(`supersedes` 仅格式校验);须同步补 acceptance 验收项(上轮 ACCEPT 未覆盖此条) |
| T11 超期提示 + 孤儿检测 + 新增未声明替代提示 | P5 | 待分配 | TODO | 三者**一律只提示不判失败**;超期若做成失败会引发「全库某天突然变红」→ 门禁被关 |
| T12 README 清单与文档标签互检 | P5 | 待分配 | TODO | protocol §7.6;导航过期与标签错误互为校验 |
| T13 `canon_read` 行为契约 + `canon index` 紧凑输出与过滤 | P6 | 待分配 | TODO | protocol §7.4 / §7.5;**主角是 canon_read**,index 不得写成必经路径 |
| T14 MCP server + `canon init` 生成接线片段 | P6 | 待分配 | TODO | protocol §7.7 话术;让能力出现在消费者工具面,而非仅存在于文档约定 |
| T9 发布准备(README/pyproject 完善)+ 远程发布 | P7 | 主 agent + 用户 | TODO | 远程发布留用户拍板(红线);发布物基本齐 |

## 当前波次

- 波次 1(DONE):实现 + 文档两 agent 并行交付,独立验收 ACCEPT,P3 反馈链路本地跑通。已完成 P0–P4 全部验收项(A0–A11 PASS)。
- **波次 2(NEXT):T10–T12 防腐烂检查组**。做完派独立 subagent 验收,再进波次 3。
- **波次 3:T13–T14 读取接线**。顺序不可与波次 2 颠倒——理由见 roadmap「依赖顺序」。
- 波次 4:T9 发布决策(红线,需用户拍板)。
- 设计依据:三层分工(README 导航 / `canon_read` 兜底 / `canon index` 按需)见 `docs/design/protocol.md` §7,**该节是 2026-07-21 对早期设计的更正**:早期方案曾把「每次先跑全库索引」作为默认路径,会污染上下文,已废止。
