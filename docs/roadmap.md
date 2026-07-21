---
status: current
applies_when: 规划 canonmark 各阶段顺序、判断当前处于哪个阶段、决定下一步做什么
not_for: 具体任务执行步骤(见 tasks/)、验收判定(见 acceptance.md)、协议字段定义(见 design/protocol.md)
current_authority: roadmap-current
supersedes: []
superseded_by: []
owner: canonmark
last_reviewed: 2026-07-21
---

# canonmark 路线图

结论:canonmark 分 6 个阶段(P0–P5)。核心地基是 P1(抽取参数化)+ P3(自审反馈链路)。当前处于 **P0**。

## 这个项目是什么(一句话)

把 agong_server 内部已验证的文档治理能力,抽取为一个独立、可配置的开源工具:审计文档头部的「权威标签」,裁决 AI agent 该信哪篇文档,并用 CI 门禁保证标签不腐烂。

## 为什么做成独立仓(不在 agong 内部改)

独立仓自动绕开了 agong 内部两笔最麻烦的债:「合并到 master」和「agong CLAUDE.md 与规范打架」都不再阻塞第一版。agong_server 未来作为 canonmark 的第一个使用者接入即可。第一版只需证明:一个从 agong 抽取、去公司化的工具,能在任意项目上按配置运行。

## 阶段

### P0 奠基(进行中)
产物:项目骨架、权威文档结构、协议规范初稿。出口:文档结构齐全,且能被 canonmark 自己的规范识别。

### P1 抽取参数化(地基核心)
把 agong `docs-audit.py`(1441 行)抽取到 `src/canonmark/`,项目特有硬编码抽到 `canonmark.toml`,加 `--config`;**默认值 = agong 现值**,迁移的 42 个单测零改动全绿。
必修(对抗核验坐实,不做就是半拉子):① 必须参数化最大的 `audit_v5` frontmatter 主体(L909–1139);② `status`/`authority` 词汇表定性为「治理模型固定词汇」而非项目品牌,不当可换配置暴露;③ 补 `trigger_paths`/`auditor_home` 等跨模块字段;④ 补 L471 的 docs 根字面量。
出口:`canon audit` 能在带自定义配置的项目上正确运行;42 单测全绿。

### P2 只抽通用件(擦干净)
抽取时就排除不可移植件:`gen_diagrams`(macOS 字体依赖)、task-packet lint(绑内部共识)、java hook(死代码)。新仓从第一天就干净。
出口:`src/` 无 agong 专属依赖;`pip install` 后纯标准库 + 可选 PyYAML 即可跑。

### P3 自审反馈链路(dogfood,《系统之美》核心)
canonmark 用自己的 `canon audit` 审自己的 `docs/`;接 pre-commit + GitHub Action;42 单测建独立 CI job(与文档提交解耦)。形成「文档变脏 → 自动检测 → 挡住」的负反馈回路——用最少机制,让系统自己审自己。
出口:本地提交和 CI 两条路各真跑绿一次;`canon audit docs/` 对自身全 PASS。

### P4 验收(用证据证明)
12 文件 fixture 双向 oracle(该报的精确报中 / 修好后 exit 0);同一 fixture 两份配置翻转命名口径,证明「改配置不改代码就能换项目」;独立 subagent 验收,实现者不得自评 PASS。
出口:acceptance.md 全绿,证据齐全。

### P5 发布准备(不执行发布)
README / pyproject / LICENSE 完善;准备好 `gh repo create` 命令。**远程公开发布是红线,留用户拍板,agent 不擅自执行。**
出口:一条命令可推送;发布决定权交用户。

## 命名裁决(已定,来自 agent_ 前缀冲突核验)

- 默认规范:kebab-case、禁 `agent_` 前缀、ASCII 文件名——作为 canonmark 默认配置。
- agong 的 `agent_` + 中文命名是「使用者的作用域例外」,留在 agong 自己的配置里,不进 canonmark 默认。
- canonmark 自己的文档遵守默认(禁 `agent_`)——这就是最强的 dogfood 证据。

## 依赖顺序(对抗核验给定,勿按直觉)

P0 → P1(先建 config/loader,含 audit_v5 主体)→ P2(抽取即过滤)→ P3(自审 + CI)→ P4(验收)→ P5。
铁律:「发布」永远最后,且永不自动执行。
