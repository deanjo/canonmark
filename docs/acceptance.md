---
status: current
applies_when: 判定某个阶段是否真正完成、检查证据是否齐全、决定能否进入下一阶段
not_for: 阶段规划顺序(见 roadmap.md)、任务执行步骤(见 tasks/)
current_authority: acceptance-current
supersedes: []
superseded_by: []
owner: canonmark
last_reviewed: 2026-07-28
---

# canonmark 验收矩阵

结论:每个阶段都有量化验收项。判定五态:`PASS` / `FAIL` / `BLOCKED` / `INSUFFICIENT_EVIDENCE` / `NOT_APPLICABLE`。实现者不得自评 PASS,须独立 subagent 验收。

## 验收项

| ID | 阶段 | 验收项 | 测试命令 | 通过条件 | 证据路径 | 状态 |
|---|---|---|---|---|---|---|
| A0 | P0 | 文档结构齐全且自合规 | `canon audit docs/`(自审) | 无缺 README / frontmatter 完整 | A6 自审全 PASS 间接证明 | PASS |
| A1 | P1 | 42 单测迁移后断言零改动全绿 | `python -m pytest tests/ -q` | 全绿,原用例断言文本不变 | 全绿(计数跑命令栏的命令现取,不在此复制)。**断言文本确实一字未改,但须如实记录:P5 的对称性检查是破坏性变更**——`test_v5_superseded_by_accepts_valid_multi_target_paths` 的原场景(多目标 superseded_by 不带反向指针)在新规则下会报错,靠给 fixture 补 `supersedes` 保住断言;迁移用例中另有若干处显式传入 `STRICT` 以继续断言严格口径 | PASS |
| A2 | P1 | 默认配置输出与 agong 原版逐字节一致(P1 时点) | 对同一 docs 树跑新旧审计器 diff | 无差异 | cksum 双方 `749520412 312` IDENTICAL——这是 P1 验收当时(2026-07-21)的历史证据,锚定该时点,今日不再可复现。**须如实记录:自 P5 起默认输出有意不再与原版逐字节一致**——agong 残留默认值已清空,且新增的 T10 对称性检查会报原版从不报的问题(与 A1 注脚及 README Status 同一口径)。本项 PASS 的范围限定为 P1 抽取时点 | PASS |
| A3 | P1 | audit_v5 frontmatter 主体已参数化 | 翻转 `allowed_statuses` 应改变行为 | 行为随配置变,.py md5 不变 | 含/去 draft → V5 PASS↔FAIL | PASS |
| A4 | P2 | src 无 agong 专属依赖 | `grep -ri` src/ | 仅注释/默认配置值,无代码依赖 | 命中全在注释/config 默认值 | PASS |
| A5 | P2 | 纯标准库 + 可选 PyYAML 可跑 | `pip install -e . && canon --help` | 退出码 0 | canon/audit --help exit 0 | PASS |
| A6 | P3 | canonmark 自审自身全 PASS | `canon audit docs/ --config canonmark.toml` | 全部 gate PASS,exit 0 | 全门 PASS,exit 0(门数随阶段增加,以命令输出为准) | PASS |
| A7 | P3 | pre-commit + CI 各真跑绿一次 | `pre-commit run --all-files` + CI pipeline | 两条路均绿 | 本地 `Passed` exit 0，**但有两个未写出的前提**：`.git/hooks/pre-commit` 并未安装（需 `pre-commit install`），且 `canon` 不在系统 PATH 上（需把 venv 的 bin 加进 PATH，否则报 `Executable canon not found`）。**所以「本地提交会自动挡住脏文档」在当前 checkout 上并不成立**——跑得通的是手动触发那条路。远端 CI 无 remote，从未跑过 | PASS(手动触发) |
| A8 | P4 | INVALID fixture 精确报中 6 处埋雷 | `pytest tests/test_fixtures.py` | 恰好 6 类问题 | **P5 曾无声打破此项**(fixture 不被任何测试引用,gradual 把其中 2 处埋雷降级为提示),独立验收查出;修法:fixture 配置声明 `adoption_mode = "strict"`,并新建 `tests/test_fixtures.py` 把双向 oracle 接进 pytest,不再依赖人工跑 CLI | PASS |
| A9 | P4 | VALID fixture 一处不报 | `pytest tests/test_fixtures.py` | 无 issue 亦无 notice | **P5 曾无声打破此项**:valid fixture 里 `old-notes.md` 声称被 `replacement.md` 取代而对方未认领——正是项目文档记载的「自家后院的单边声明」,T10 上线后被抓出。已给 `replacement.md` 补 `supersedes`,该现行犯就此归案 | PASS |
| A10 | P4 | 改配置不改代码即换项目 | 同 fixture,两份 config 翻转口径 | 结果翻转,.py 零改动 | A3 md5 佐证 .py 未改 | PASS |
| A11 | P4 | 独立 subagent 验收 ACCEPT | 独立 subagent 复核 A1–A10 证据 | verdict = ACCEPT | 独立验收 ACCEPT,无 FAIL | PASS |
| A13 | P5 | 反向指针不对称被判失败 | `pytest tests/ -k SupersessionSymmetry` | 报错且 exit 1 | 全绿;单边声明报「替代关系是单边声明」并给出对方应加的路径 | PASS |
| A14 | P5 | 超期**只提示不失败** | `pytest tests/ -k stale_review` | 有提示输出但 **exit 0** | 进 notices 不进 issues;老项目实测 exit 0 | PASS |
| A15 | P5 | 孤儿文档被提示 | `pytest tests/ -k orphan` | 出现在提示中,不判失败 | V11 提示「孤儿文档」;老项目实测命中 payment-design.md 且 exit 0 | PASS |
| A16 | P5 | README 清单与文档标签互检 | `pytest tests/ -k navigation_pointing` | 报错 | README 指向自称 superseded 的文档 → V11 issues 命中 README | PASS |
| A20 | P5 | 存量项目装上不当场变红(渐进采用) | 对零 frontmatter 的老项目跑 `canon audit` | 无任何 gate FAIL,**exit 0**,提示指路 | 零标签老项目实测:全门 PASS、有指路提示、exit 0;提示条数随门数与项目形态而变,不在此复制(当时夹具未入库,复现请对任意零标签项目跑命令栏命令) | PASS |
| A21 | P5 | 贴第一张作废标签不触发连锁强制 | 旧文档声明被未治理的新文档取代 | 不判失败,只提示补标签 | V5 降级为「替代目标尚未纳入治理」提示,exit 0 | PASS |
| A22 | P5 | strict 模式下结构性缺失照旧判失败 | `pytest tests/ -k strict_still_fails` | 缺 frontmatter / 缺导航均 FAIL | 全绿;canonmark 自身 strict 全门 PASS | PASS |
| A17 | P6 | `canon_read` 对作废文档不返回正文 | `pytest tests/test_read.py tests/test_mcp.py` | 返回替代目标,**正文不出现在输出中** | 哨兵串断言:CLI 层与 MCP 工具调用层双双不泄漏正文;另断言输出长度**不随文档变长而增长**(测试把同一篇作废文档撑长两千行,输出字节数一字不变) | INSUFFICIENT_EVIDENCE |
| A18 | P6 | `canon index` 紧凑且可过滤 | `pytest tests/test_read.py -k Index` | 输出字节数 < 全文总量的 10%;过滤生效 | 自身 docs 实测远低于门槛(具体比例跑命令栏的命令现取);另加一条更本质的断言——索引大小**不随正文变长而增长**,只与篇数有关(原判据在文档很短时会失真);`--dir` / `--current-only` / `--json` 均有用例 | INSUFFICIENT_EVIDENCE |
| A19 | P6 | 对照实验:消费者被拦并改读替代目标 | 见下「A19 对照实验记录」 | 答案取自现行文档,非作废文档 | **四组实测,结论与预期不同**:标签的价值成立(无标签组只能推理并明确要求人确认),但 `canon_read` 的**增量**价值在本实验规模下未体现——有标签组不用工具也答对了。详见下节,含实验设计缺陷的自陈 | INSUFFICIENT_EVIDENCE |
| A12 | P7 | 发布物完整 | 人工核对 README/pyproject/LICENSE | 齐全,可一条命令推送 | 待 P7 | PENDING |

**A17/A18 状态说明(2026-07-28 记)**:P6(T13/T14)首轮独立验收判定 REJECT,修复后复验判定 ACCEPT(见 progress.md 2026-07-27 心跳;两项必办已完成并入 commit 6e21f78)。A17/A18 是否据此由 INSUFFICIENT_EVIDENCE 置 PASS,待用户拍板;拍板前维持原状态值。

## A19 对照实验记录

**结论与预期不同,如实记录。** 预期是「不装 canonmark 的 AI 引用作废文档答错,装了的被拦下答对」。实测:**没有任何一组答错**。

### 实验设计

同一个网关项目,同一个问题(限流该用什么算法、阈值多少),四组只差读取条件。旧文档 `rate-limit.md` 写固定窗口 / 100 QPS,新文档 `rate-limit-v2.md` 写滑动窗口+令牌桶 / 300 QPS,二者互斥。刻意模拟最真实的失效场景:**`design/README.md` 只链接旧文档,新文档是孤儿**(人忘了更新导航)。旧文档正文完全正常,只有 frontmatter 标着 `superseded`。

### 结果

| 组 | 条件 | 结果 | 关键表现 |
|---|---|---|---|
| 对照 0-a | **无任何标签**,直接读 | 倾向 v2,**明确说无法确定** | 「一份被否决的 RFC 草稿和一份已生效的继任方案,在缺少状态标记时长得一模一样」,要求人拍板 |
| 对照 0-b | 无任何标签,换弱一档模型 | 倾向 v2,**明确说不是 100% 确证** | 建议「找相关同事确认哪份是线上在用的」 |
| A | **有标签**,直接读文件 | **确定答对** | 自己读到 `status: superseded` 与 `not_for: 当前限流实现依据`,据此排除旧文档 |
| B | 有标签 + `canon_read` | **确定答对** | 旧文档被拦截,拿到重定向后改读 v2 |

### 结论一:标签的价值成立,但表现方式和预期不同

**差别不在答案对错,在置信度和是否需要人介入。** 无标签的两组都靠内容线索推理(「v2 提到废弃了 v1」「文件名带 v2」),都倾向了正确答案,但都明确标注低置信度并把决定权交回给人。有标签的两组直接给出确定判断。

这比「答错」更能说明成本:真实成本不是 AI 答错,而是**每一次都要人来拍板**。而这个项目的前提正是没人有空拍板。

### 结论二:`canon_read` 的增量价值在本实验规模下未体现

A 组不用工具也答对了。诚实地说,**本实验没能证明 `canon_read` 相对「只贴标签」的增量收益**。

原因是我的实验夹具太小:只有 7 篇文档,A 组把全部读了一遍,旧文档不过几百字节,读进去几乎不要钱。真实项目里 AI 不会通读 docs,而设计文档动辄几十 KB。

可量化的那部分增量是上下文开销:直接读一篇作废文档,进上下文的是它的**全长**;`canon_read` 给出的是固定几行,且**输出长度不随文档变长而增长**——测试把同一篇撑长两千行,输出字节数一字不变(`test_superseded_output_does_not_grow_with_document_length`)。真实设计文档动辄几十 KB,差距是两个数量级。

这里刻意不写具体字节数:此前写过一组「17,484 → 189」,但那个 17,484 字节的输入是临时撑出来的、没进仓库,读者复现不了——**一个复现不了的数字,和一个错数字，对读者是一回事**。要看实际比例,跑上面那条测试或对自己的文档跑 `canon read`。

这一条是确定的;至于「省下的上下文是否换来更好的答案」,本实验没有验证。

### 实验设计的缺陷(自陈)

1. **最初漏了真正的对照组。** 第一版只跑了 A/B 两组,两组都答对时我一度以为工具生效了——其实 A 组根本不是「没有 canonmark」,它是「有标签但没用工具」。补跑无标签组之后才看清:第一件事(标签)贡献了绝大部分价值。
2. **样本量为 1。** 每种条件只跑一次,不能排除偶然。
3. **实验路径里含 `canonmark` 字样**,对照组 0-a 在报告末尾提到了 canonmark,说明它可能从路径推断出了上下文。其结论基于文档内容,但这个污染应当记录。
4. **未验证长文档下的行为差异**——那正是 `canon_read` 增量价值最可能显现的地方,需要重做实验才能回答。

## 未验证范围(诚实边界)

- GitHub 远程发布(A12 之后)不由 agent 执行,留用户拍板。
- **本地 pre-commit 钩子未安装**:`.pre-commit-config.yaml` 写好了、手动 `pre-commit run` 也绿,但 `.git/hooks/pre-commit` 不存在,且 `canon` 不在系统 PATH 上。即「自动挡住脏文档」这条负反馈回路在当前 checkout 上是断的,需要 `pre-commit install` 加把 venv 的 bin 放进 PATH 才闭合。
- **Python 版本**:`pyproject.toml` 声明 `>=3.9`,但 CI 只跑 3.11、本地是 3.14,3.9/3.10 从未实测。
- **写作端 skill 与本协议的权威映射冲突(两处)未裁决**,见 `design/protocol.md` §4.1。canonmark 检查不到这类跨工具的规则冲突——它只校验自己配置内的一致性。
- Windows 首跑(CRLF/BOM/反斜杠路径)第一版不覆盖,列入风险。
- agong_server 侧的实际接入(换用 canonmark + 写 agong 配置)不在本项目范围,是 agong 侧后续。
- **已知边界(P5 独立验收发现,未修)**:`Frontmatter.absent` 按「首行是不是 `---`」判定,因此一篇以 Markdown 水平线 `---` 开头的存量文档会被当作「已贴标签」,在 `gradual` 下照旧判失败,与渐进采用的承诺相悖。场景窄但真实。修法需权衡——若改成「找不到闭合 `---` 就视为没有 frontmatter」,则「真写了标签却忘了闭合」会被降级为提示,可能放过真错误。留待拍板。
- **正文语义矛盾不在 canonmark 能力范围内**:本工具检查的是标签层(取代关系、状态合法性、导航与标签互检)。两篇文档正文里对同一件事给出相反说法(P6 期间的实例:`kickoff.md` 的「本次不做」清单含 MCP server,而 roadmap P6 / T14 要做——已按 protocol §5.4「事实优先」更正 kickoff,但这个矛盾**当初是人发现的,不是机器**),标签层完全合规,机器抓不到。这类冲突仍需人或 AI 判断。
