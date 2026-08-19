---
status: current
applies_when: 判定某个阶段是否真正完成、检查证据是否齐全、决定能否进入下一阶段
not_for: 阶段规划顺序(见 roadmap.md)、任务执行步骤(见 tasks/)
current_authority: acceptance-current
supersedes: []
superseded_by: []
owner: canonmark
last_reviewed: 2026-08-19
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
| A5 | P2 | 装上即可跑(依赖口径见证据栏) | `pip install -e . && canon --help` | 退出码 0 | canon/audit --help exit 0。**验收项原文是「纯标准库 + 可选 PyYAML 可跑」,锚定 P2 时点;2026-08-19 起 PyYAML 转为唯一硬依赖**——`pip install canonmark` 一步装齐,「可选」二字不再成立(转正理由:只装本体时读 frontmatter 的门报缺依赖、退出码 1,打脸 A20)。本项 PASS 的范围是「装完 `canon` 能起来」,这一判据两种口径下都成立;真实安装路径的冷装实证见 A26 | PASS |
| A6 | P3 | canonmark 自审自身全 PASS | `canon audit docs/ --config canonmark.toml` | 全部 gate PASS,exit 0 | 全门 PASS,exit 0(门数随阶段增加,以命令输出为准) | PASS |
| A7 | P3 | pre-commit + CI 各真跑绿一次 | `pre-commit run --all-files` + CI pipeline | 两条路均绿 | 2026-07-29 双路收口:本地——`pre-commit install` 已装入本仓与全新 clone,双向实测(坏 frontmatter 提交被钩子拦下 exit 1、干净提交放行);PATH 前提保留(提交环境需把 venv 的 bin 加进 PATH,否则报 `Executable canon not found`)。远端——私有仓 PR#1 首跑 CI,tests 与 self-audit 两 job 均 pass(actions run 30432342592)。此前「钩子未装、CI 从未跑」的诚实披露见 git 历史 | PASS |
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
| A17 | P6 | `canon_read` 对作废文档不返回正文 | `pytest tests/test_read.py tests/test_mcp.py` | 返回替代目标,**正文不出现在输出中** | 哨兵串断言:CLI 层与 MCP 工具调用层双双不泄漏正文;另断言输出长度**不随文档变长而增长**(测试把同一篇作废文档撑长两千行,输出字节数一字不变)。2026-07-29 用户裁决:据复验 ACCEPT 置 PASS | PASS |
| A18 | P6 | `canon index` 紧凑且可过滤 | `pytest tests/test_read.py -k Index` | 输出字节数 < 全文总量的 10%;过滤生效 | 自身 docs 实测远低于门槛(具体比例跑命令栏的命令现取);另加一条更本质的断言——索引大小**不随正文变长而增长**,只与篇数有关(原判据在文档很短时会失真);`--dir` / `--current-only` / `--json` 均有用例。2026-07-29 用户裁决:据复验 ACCEPT 置 PASS | PASS |
| A19 | P6 | 对照实验:消费者被拦并改读替代目标 | 见下「A19 对照实验记录」 | 答案取自现行文档,非作废文档 | **四组实测,结论与预期不同**:标签的价值成立(无标签组只能推理并明确要求人确认),但 `canon_read` 的**增量**价值在本实验规模下未体现——有标签组不用工具也答对了。详见下节,含实验设计缺陷的自陈 | INSUFFICIENT_EVIDENCE |
| A12 | P7 | 发布物完整 | 人工核对 README/pyproject/LICENSE | 齐全,可一条命令推送 | 独立复验两轮(2026-07-29):首轮 FAIL 四条依据(Homepage 修正未提交、公开命令缺 flag、远程门面 main 陈旧且默认分支为 WIP 分支、README 措辞歧义)→ 逐条翻正后重判 **PASS**——LICENSE 完整 MIT;pyproject 与真实仓库一致;README 表述与事实逐点吻合;远程四点同锚(HEAD=origin/main=origin/feat=本地 main),默认分支 main,可见性 PRIVATE;公开=一条命令(见 tasks/README 的 T9 行,含 gh 2.96 所需 flag);main 分支 CI 首跑 success。公开动作本身留用户(红线) | PASS |
| A23 | P7 后 | V12 任务框架预算门(软阈值提示 / 硬阈值失败 / 批准行放行) | `pytest tests/ -k FrameworkBudget -q` | 三档判定与 protocol §9.2 契约一致;无框架根时直接 PASS | 2026-08-19 零上下文独立复验 ACCEPT:软/硬/批准三档与无框架根路径逐条实测吻合(本仓自审 V12 即活证据) | PASS |
| A24 | P7 后 | V13 状态登记表门(唯一登记表 + 登记表外状态词绊线) | `pytest tests/ -k StatusRegistry -q` | 登记表缺失/多张/重复 id/非法 status 判失败;绊线只报告不做语义判断,与 protocol §9.3 契约一致 | 2026-08-19 零上下文独立复验 ACCEPT:四类失败与绊线行为逐条实测吻合 | PASS |
| A25 | P7 后 | `canon hook` 行为契约(PreToolUse 拦截) | `pytest tests/test_hook.py -q` + `echo '<PreToolUse JSON>' \| canon hook` | 退休文档的 Read 输出 deny JSON 且含替代去处;current / 未贴标签 / 非 docs 路径 / 非 Read 工具 / 解析失败一律静默放行 exit 0 | 2026-08-19 零上下文独立复验 ACCEPT:契约实测 + 13 组对抗探针(路径穿越/符号链接/兄弟目录前缀/环境变量冲突/坏输入)无静默放过、无误拦 | PASS |
| A26 | P7 后 | 成品化:陌生人可安装可跑通 | `python -m build`(`dist/` 不入库,本地已构建过可跳过)→ `python -m venv /tmp/cm && /tmp/cm/bin/pip install dist/canonmark-*.whl && /tmp/cm/bin/canon audit 任一零标签项目/docs` | 装完即有可用的 `canon`,依赖自动装齐(不必记得装附加项);对零 frontmatter 老项目**全门 PASS、exit 0**,无缺依赖报错 | 2026-08-19 冷装实测:全新 venv 装 dist 里的 wheel,PyYAML 随之装入;对新建的零 frontmatter 老项目跑审计,全门 PASS、有指路提示、exit 0(门数与提示条数随阶段与项目形态而变,以命令输出为准)。这是 A20 在**真实安装路径**上的复验——A20 当时跑的是开发树,而用户拿到的是 wheel;PyYAML 还是可选附加项时这条正是失败的(读 frontmatter 的门缺依赖退出码 1),转正后才成立 | PASS |

**A17/A18 状态说明(2026-07-28 记,2026-07-29 更新)**:P6(T13/T14)首轮独立验收判定 REJECT,修复后复验判定 ACCEPT(见 progress.md 2026-07-27 心跳;两项必办已完成并入 commit 6e21f78)。2026-07-29 用户裁决:据复验 ACCEPT 将 A17/A18 由 INSUFFICIENT_EVIDENCE 置 PASS。A19 维持 INSUFFICIENT_EVIDENCE——那是实验自身的局限(增量价值未证),不随本裁决改变。

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

- GitHub 远程公开发布已于 2026-07-29 执行:用户明示「公开」拍板后由 agent 代执行,仓库现为 public——「发布永不自动执行」的铁律全程被遵守(从未由 agent 擅动)。**PyPI 发布(2026-08-19 更新,原记「未立项」已过期)**:`v0.1.0` 已打 tag 并推送、发布物已构建,**上传 PyPI 仍未执行——扳机在用户手里,同一条铁律照旧**。因此 A26 的证据取自本地 wheel 冷装,不是从 PyPI 下载;「`pip install canonmark` 能从公网装到」这一条在上传前不成立。
- **本地 pre-commit 钩子已收口(2026-07-29)**:本仓与全新 clone 均已 `pre-commit install`,双向实测——docs/design/ 下无 frontmatter 文档的提交被钩子拦下(exit 1),干净提交放行;全新 clone 从零走通(clone → venv → `pip install -e .` + `pip install pre-commit` → install → 提交)。PATH 前提仍在:提交环境需把 venv 的 bin 加进 PATH(如 `PATH="$PWD/.venv/bin:$PATH"`),否则钩子报 `Executable canon not found`。
- **Python 版本(2026-08-19 更新)**:`pyproject.toml` 声明 `>=3.9`,CI 的 tests job 已扩为 3.9–3.13 矩阵(`fail-fast: false`),声称支持的每个版本都真跑一遍单测——原记载「CI 只跑 3.11、3.9/3.10 从未实测」到此为止,理由是声称支持却不测,等于让下游用户替我们发现跑不起来。剩余边界如实保留:self-audit job 仍只在 3.11 跑;本地开发机是 3.14,高于矩阵上限,该版本只有本地实跑、CI 无覆盖。
- **写作端 skill 与本协议的权威映射冲突(两处)已于 2026-07-29 由用户裁决**:采纳协议立场,skill §1.5 映射已改为引用 `design/protocol.md` §4.1。能力边界不因裁决消失:canonmark 检查不到这类跨工具的规则冲突——它只校验自己配置内的一致性。
- **宿主侧读取拦截已交付(2026-08-19)**:此前 README 与 protocol §7.7 的诚实边界写的是「硬拦截需要宿主侧钩子,超出本工具范围」——该表述已过时:`canon hook`(Claude Code PreToolUse 协议)已随仓提供,行为契约与复验命令见 A25。已知边界不因交付消失:**hook 只拦截内置 Read 工具,Bash `cat` 等读取路径仍是既有绕过**,本次有意不封,如实记档。
- Windows 首跑(CRLF/BOM/反斜杠路径)第一版不覆盖,列入风险。
- agong_server 侧的实际接入(换用 canonmark + 写 agong 配置)不在本项目范围,是 agong 侧后续。
- **已修(2026-07-29,决策项⑨,用户拍板)**:审计范围盲区——V5 曾只强制关键文档(key 目录 / 文件名正则 / 权威信号 / 自带 `current_authority`),其余位置的已贴标签文档零校验,`status: bogus-value` 在任何模式下静默全 PASS。现对**任何 frontmatter 可解析的文档**加底线校验:status 枚举须落在配置词汇表内(复验实测读配置、非硬编码);§5.2 前两条矛盾规则(`superseded` 须带指针、`current` 不得带指针——「非空」按语义判,**标量字符串指针同样算**,这个 fail-open 形状是复验刁钻探针抓出后补罚的);坏 YAML 本就判失败,已补锁定测试。边界如实记录:缺 `status` 字段不罚;三字段简化形态(progress.md 形)仍合法;普通文档指针**不查**目标存在性/双向对称/成环(§5.2 第 4 条仍是关键文档专属);「未纳入治理」提示仍仅发给关键文档(既有行为)。V5 计数语同步如实(「N 篇关键文档,M 篇已贴标签普通文档」)。回退变异:短路底线循环 10 红、回退形状判定 2 红(且该 2 红对形状变异是唯一且精确的守卫,复验实证);独立复验 ACCEPT(修前修后 A/B 对照、刁钻探针含配置词汇表翻转)。边缘口径(复验记档):current 方向按真值判空,`superseded_by: 0`/`false` 等假值标量按空放行(非字符串亦非指针);superseded 方向仍列表判定,标量指针照旧 fail-closed——两方向不对称但无放行缝隙。
- **已修(2026-07-29,用户拍板)**:水平线边界——首行为 `---` 水平线的存量文档曾被当作「已贴标签」,在 `gradual` 下误判失败(P5 独立验收发现)。实际采用的修法与早前记载的候选(「按找不到闭合判」)不同:gradual 下看 `---` 后**首个非空行像不像 YAML 键值对**,不像即视为未纳入治理(提示,exit 0);strict 维持旧行为;`---` 后跟键值对但缺闭合的,任何模式照旧报错——「真写了标签却忘了闭合」不放过。判定收敛于 `parse_frontmatter` 单一入口,`canon read` 同步;回退变异 3 条测试红;独立复验 ACCEPT(10 组边界探针)。**本修法的已知代价(复验探针发现,如实记录)**:① 合法标签若以 YAML 注释行开头,gradual 下整篇被静默视为未治理,真实标签失效;② `status:current` 这类冒号后无空格的手误,旧行为报「顶层必须是键值映射」,新行为在 gradual 下静默视为未贴标签。两者都是「误判方向一律朝提示」这一拍板取向的直接代价,记录在此防遗忘。
- **正文语义矛盾不在 canonmark 能力范围内**:本工具检查的是标签层(取代关系、状态合法性、导航与标签互检)。两篇文档正文里对同一件事给出相反说法(P6 期间的实例:`kickoff.md` 的「本次不做」清单含 MCP server,而 roadmap P6 / T14 要做——已按 protocol §5.4「事实优先」更正 kickoff,但这个矛盾**当初是人发现的,不是机器**),标签层完全合规,机器抓不到。这类冲突仍需人或 AI 判断。
