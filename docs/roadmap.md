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

### P5 防腐烂检查组(回应「人会遗忘」)
标签本身会腐烂,而腐烂靠人记性防不住,只能靠机器发现。五类检查:
① **反向指针不对称** → 判失败。A 声称被 B 取代、B 未声明取代 A 即报错。**注意:`docs/design/protocol.md` §2/§8 已承诺此约束,但当前代码未实现(`supersedes` 在 `audit.py` 仅有格式校验)——规范先于实现,必须补齐。**
② `last_reviewed` 超期 → **仅提示,绝不判失败**。时间触发的失败会造成「某天全库突然变红而当天无人改动」,团队的第一反应是关闭整个门禁,与目的相反。
③ 孤儿文档(无任何导航链接指向)→ 提示。
④ 新增文档疑似取代旧文档而旧文档未声明 → 提交时提示。基于 diff 的启发式,无法确定,**只提示不报错**。
⑤ README 文件清单与文档标签互检(见 protocol §7.6)。
出口:每类检查有 fixture 覆盖 + acceptance 对应验收项;独立 subagent 验收 ACCEPT。

### P6 文档发现与读取接线(主角是 `canon_read`)
把「只读头部」从一句请求变成一套机制。依据 protocol §7:
- `canon_read` 行为契约实现(§7.4):作废文档**不返回正文**,只返回状态与替代目标。
- `canon index`(§7.5):紧凑输出 + 过滤能力;**不得**写成「每次先跑」的必经路径。
- MCP server:暴露上述两个能力,使其出现在消费者的工具面而非仅存在于文档约定。
- `canon init` 生成 MCP 配置片段与宿主指令话术(§7.7 的正确版本)。
出口:**对照实验**证明消费者读到作废文档时被拦截并改读替代目标——可复现的实验,不接受「应该会生效」这类判断。

### P7 发布准备(不执行发布)
README / pyproject / LICENSE 完善;准备好 `gh repo create` 命令。**远程公开发布是红线,留用户拍板,agent 不擅自执行。**
出口:一条命令可推送;发布决定权交用户。

## 命名裁决(已定,来自 agent_ 前缀冲突核验)

- 默认规范:kebab-case、禁 `agent_` 前缀、ASCII 文件名——作为 canonmark 默认配置。
- agong 的 `agent_` + 中文命名是「使用者的作用域例外」,留在 agong 自己的配置里,不进 canonmark 默认。
- canonmark 自己的文档遵守默认(禁 `agent_`)——这就是最强的 dogfood 证据。

## 依赖顺序(对抗核验给定,勿按直觉)

P0 → P1(先建 config/loader,含 audit_v5 主体)→ P2(抽取即过滤)→ P3(自审 + CI)→ P4(验收)→ **P5(防腐烂)→ P6(读取接线)** → P7(发布)。

**P5 必须早于 P6,不可颠倒**:P6 让消费者依据标签跳过全文,而这个动作的全部价值建立在标签可信之上。标签仍会腐烂时先做 P6,等于在流沙上盖楼——消费者会据此跳过真正该读的文档,比不做更危险。

铁律:「发布」永远最后,且永不自动执行。
