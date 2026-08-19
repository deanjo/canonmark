---
status: current
applies_when: 定义/校验文档权威元数据 8 字段、执行五步权威判定协议、判断 status×current_authority 组合是否合法、处理缺字段或矛盾元数据的 fail-closed 行为、查阅任务框架治理(V12/V13)的检查契约
not_for: 价值主张与竞品边界(见 vision.md)、阶段规划顺序(见 roadmap.md)、验收判定标准(见 acceptance.md)
current_authority: contract-current
supersedes: []
superseded_by: []
owner: canonmark
last_reviewed: 2026-08-19
---

# canonmark 权威元数据契约与判定协议

结论先行:本文件是 canonmark 的核心协议规范,定义两件事——(1)每篇关键文档头部必须携带的 **8 字段权威元数据契约**;(2)agent / 脚本 / 人把任何文档当依据前必须执行的 **五步判定协议**。协议的铁律是 **fail-closed(保守关闭):未证明适用,就不授予权威。** 缺字段或元数据矛盾时,标记 `INSUFFICIENT_METADATA` / `METADATA_CONFLICT`,绝不把旧正文当现行事实。

本文件是 `contract-current`,定义接口 / 行为约束;它本身也遵守自己定义的协议(dogfood)。

## 1. 概念与角色划分

- **关键文档**:会被执行 agent 反复当作权威输入读取的文档(设计文档、契约、任务分片、验收矩阵、Roadmap、规范)。frontmatter 强制完整 8 字段。
- **普通文档**:会议纪要、诊断报告、操作记录、进度日志等。frontmatter 简化(`status` / `owner` / `last_reviewed` 三字段),只能作为记录或线索;一旦要主导设计 / 执行 / 验收,必须先补齐关键文档的完整 8 字段。

本协议的判定逻辑只对关键文档强制。普通文档不参与五步判定的权威授予。

## 2. 8 字段权威元数据契约

关键文档头部必须是可被 YAML 解析的 frontmatter,包含且仅需以下 8 个字段。缺任一字段、类型错误、枚举非法,一律 fail-closed(见 §5)。

```yaml
---
status: current                       # 枚举:current | background | archive | superseded
applies_when: 处理 X 场景的具体任务     # 具体场景,禁泛词
not_for: 不应主导的相邻场景 A、B         # 硬否决场景
current_authority: contract-current   # 枚举:六选一(见下)
supersedes: []                        # 被本文件取代的旧文档路径列表;无则 []
superseded_by: []                     # 取代本文件的新文档路径列表;当前权威写 []
owner: canonmark                      # 责任模块或 @handle
last_reviewed: 2026-07-21             # 最近复核日期 YYYY-MM-DD
---
```

### 2.1 逐字段定义

**`status`**(生命周期状态,枚举四选一)
文档当前处于生死链条的哪一段。这决定「默认是否加载正文」。

| 值 | 语义 | 默认加载行为 |
|---|---|---|
| `current` | 当前仍维护或生效 | 加载;但「能否主导」由 `current_authority` 决定,不等于有权威 |
| `background` | 不再是当前维护入口,仍有背景 / 证据价值 | 仅任务明确需要背景或证据时按需读取 |
| `archive` | 已完成使命的历史记录 | 默认排除,仅追溯历史时读取 |
| `superseded` | 被新文档取代,顶部指向替代者 | 先跟随 `superseded_by`,旧正文默认不读 |

**`applies_when`**(适用场景)
本文件**应该**被读取并当作依据的具体任务场景。
写法硬要求:必须是具体任务场景,**禁写泛词**。反例:`supplier`。正例:`处理供应商导入批次重试`。字段过泛、为空或无法据此判断适用性,判定时一律按「不匹配」处理(见 §3 第 4 步)——不允许靠读全文反推「它也许适用」。

**`not_for`**(排除场景)
本文件**不应该主导**的相邻场景——即最容易被误当依据、进而导致任务跑偏的邻近任务。
写法硬要求:写会导致跑偏的具体相邻场景。例:一个「身份映射」任务文档的 `not_for` 写 `安全治理全量验收、部署重建、通用运维`。`not_for` 是**硬否决**:当前任务命中排除场景时立即停止,即使 `status: current` 也不能覆盖(见 §3 第 3 步)。

**`current_authority`**(权威角色,枚举六选一)
本文件在被采信后,**能主导什么**。这是五步的最后一关,决定角色分工。

| 值 | 能主导的范围 |
|---|---|
| `roadmap-current` | 加载顺序与阶段边界(哪个阶段做什么、先读谁) |
| `task-current` | 具体执行(当前任务怎么做) |
| `contract-current` | 接口 / 行为约束(字段定义、协议、schema) |
| `acceptance-current` | 验收(某阶段是否达标、证据是否齐全) |
| `background-reference` | **永不主导**——当前维护的背景说明,只作入口或说明 |
| `historical-evidence` | **永不主导**——历史证据,仅供追溯 |

铁律:`background-reference` 与 `historical-evidence` 无论 `status` 是什么,**都不能主导当前实现或验收**。

**`supersedes`**(向后指针,列表)
被本文件取代的旧文档路径列表。没有则写 `[]`。与被取代文档的 `superseded_by` 互为反向指针——两端必须对称:若 A 的 `supersedes` 含 B,则 B 的 `superseded_by` 应含 A。

**`superseded_by`**(向前指针,列表)
取代本文件的新文档路径列表。当前权威写 `[]`。**非空即表示本文件已被取代**,这是五步协议的第一道关卡(见 §3 第 1 步)。

**两个指针字段的路径口径**(两种写法都合法,审计器按解析后的真实路径比对,两端可各用一种):

| 写法 | 解析基准 | 例 |
|---|---|---|
| 不以 docs 根开头 | **当前文件所在目录** | `docs/design/old.md` 里写 `new.md` → `docs/design/new.md` |
| 以 docs 根开头 | 仓库根 | 同一文件里写 `docs/design/new.md` → 同上 |

绝对路径与解析后落在 docs 根之外的路径一律非法。写错时审计器会给出解析结果与可照抄的建议写法,不只报「目标不存在」——第一次贴标签的人不该靠猜。

**`owner`**(责任归属)
文档的责任模块或个人。优先用模块名(取该文档所在顶层目录名);其次 `@handle`。同一模块用一致取值,便于问责与复核路由。

**`last_reviewed`**(最近复核日期)
`YYYY-MM-DD` 格式的最近复核日期。用于新鲜度信号:超期未复核的 `current` 文档应由审计器提示复核,防止「标着 current 实则腐烂」。

## 3. 五步判定协议(顺序不得交换)

任何 agent / 脚本 / 人把一篇关键文档当作设计、执行或验收依据前,**必须先只解析头部 frontmatter**,按下列固定顺序判定。**不能先读正文再反推是否适用。** 通过全部五步,才进入正文的渐进加载(见 §6)。

```
superseded_by ─▶ status ─▶ not_for ─▶ applies_when ─▶ current_authority
   取代?          生死?      否决?        适用?           能主导什么?
```

### 第 1 步:`superseded_by`——是否已被取代

先结合 `status` 校验组合:`status: current` 且 `superseded_by` 非空,判 `METADATA_CONFLICT`(自称现行却又声明被取代,矛盾)。
`superseded_by` 为合法非空列表时,它不是「按顺序挑一个」,而是把**全部目标作为候选**:逐个校验目标路径是否存在、替代链是否成环;对**每个目标重新执行完整五步**;最后按各目标的 `current_authority` 分工。
唯一的导航例外是 `README.md`:它可作为替代入口来**发现**候选,但 README 正文本身不得直接取得任务权威,链接到的权威文档仍须重新过五步。
旧文档只可在追溯证据时按需读取;目标不存在或替代链成环时,**不得回退使用旧正文**——保持 fail-closed。

### 第 2 步:`status`——是否默认加载正文

- `archive` / `superseded`:默认不加载正文。
- `background`:仅当任务明确需要背景或证据时才保留读取。
- `current`:表示文档当前仍维护或生效,但**不等于它能主导实现**——角色留到第 5 步定。

### 第 3 步:`not_for`——是否命中硬否决

当前任务命中 `not_for` 里的排除场景时**立即停止**。`not_for` 是硬否决,即使 `status: current` 也不能覆盖。
例:任务是「重建部署」,而某文档 `not_for` 明写「部署重建」,则该文档在本任务中直接出局,无论它多现行。

### 第 4 步:`applies_when`——是否明确命中适用场景

当前任务明确命中 `applies_when` 描述的适用场景时才继续。
字段过泛、为空或无法判断,按**不匹配**处理,不得靠通读全文来「猜它也许适用」。这一步与第 3 步共同构成范围闸门:第 3 步排除误用,第 4 步要求正命中。

### 第 5 步:`current_authority`——能承担什么角色

最后决定可承担的角色:`roadmap-current` 管加载顺序与阶段边界,`task-current` 管具体执行,`contract-current` 管接口 / 行为约束,`acceptance-current` 管验收;`background-reference` 与 `historical-evidence` **永远不能主导**当前实现或验收。

## 4. status × current_authority 合法矩阵

`status` 与 `current_authority` 的组合不是自由搭配,必须落在下表内。**不在表内的组合判 `METADATA_CONFLICT`**(见 §5)。这张表由 `canon audit` 机械校验,是唯一权威口径。

| `status` | 允许的 `current_authority` | 默认加载行为 |
|---|---|---|
| `current` | `roadmap-current` / `task-current` / `contract-current` / `acceptance-current` / `background-reference` | `*-current` 按角色主导;`background-reference` 表示「当前维护的背景说明」,只作入口或说明 |
| `background` | `background-reference` / `historical-evidence` | 仅任务明确需要背景或证据时按需读取 |
| `archive` | `historical-evidence` | 默认排除,仅追溯历史证据时读取 |
| `superseded` | `historical-evidence` | 先跟随 `superseded_by`,旧正文默认不读 |

读表要点:

- **`current` 不允许配 `historical-evidence`**:一篇还现行的文档不该自称「历史证据」。
- **`archive` / `superseded` 只允许 `historical-evidence`**:已归档 / 已取代的文档不能自称任何 `*-current` 或 `background-reference`——它无权主导,也不再是维护中的背景入口。
- **`current + background-reference` 合法**:表示「当前维护但只作说明、不主导」的入口文档(canonmark 自己的 `vision.md` 就是这个组合)。
- 冲突组合举例:`status: archive` + `current_authority: contract-current`(归档文档不能当现行契约)→ `METADATA_CONFLICT`;`status: superseded` + `superseded_by: []`(自称被取代却不指出取代者)→ `METADATA_CONFLICT`。

### 4.1 与写作端 skill 的关系(单一事实源在本节)

canonmark 是**检查端**。与之配套的**写作端**是 `technical-plan-sharding` skill(本机 Codex 全局 skill),它指导如何写出 Roadmap 入口 / 契约分片 / 任务分片 / 验收矩阵——正好对应本协议的四个 `*-current` 角色。两者同源:该 skill §1.5 的 frontmatter 模板是本协议 8 字段中的 6 个(缺 `owner` / `last_reviewed`),§6 的验收五值枚举与 `acceptance.md` 的判定五态一字不差。

**分工**:skill 管「怎么写出合规文档」(靠自觉),canonmark 管「写完了机器验一遍」(靠门禁)。**词汇表与合法矩阵以本节为单一事实源**,写作端引用而非复制——否则加字段、改矩阵要改两处,迟早漂移。

**已知冲突,共两处——2026-07-29 已由用户裁决:采纳本协议立场,skill §1.5 的映射已改为引用本节**(原冲突记录保留如下,作为「先冻结、后裁决」的先例):

1. skill §1.5 规定「`background-reference` 只能配 `status: background`」,而本节允许 `current + background-reference`。两者不能同时成立,且按 skill 的规则,canonmark 自己的 `vision.md` 是非法文档。
2. skill §1.5 规定 `historical-evidence` 只能配 `status: archive` 或 `superseded`,而本节 §4 矩阵的 `background` 行明确允许 `background + historical-evidence`。即同一篇 `background + historical-evidence` 文档,canonmark 审计放行(2026-07-28 实测:strict 模式下全门 PASS、exit 0),按 skill 却是非法组合。

本协议的立场与理由:`status` 表示**生命周期**(还在维护吗),`current_authority` 表示**能主导什么**,这是两个正交维度。强行绑定会丢掉「当前维护但不主导」这种常见形态的表达力——`vision.md` 正是此类:它在维护中(不是背景、更不是过期),但不该主导实现。若按 skill 的规则把它标成 `status: background`,反而与事实不符。

这两处冲突按「裁决前双方冻结」的规矩走到 2026-07-29 由用户收口,期间无单方面改动。冲突本身就是本项目要消灭的形态(两份权威对同一件事给出相反规定),而且**canonmark 检查不到它们**——它只校验自己配置内的一致性,不知道 skill 的存在。这条能力边界不因裁决消失,见 `acceptance.md`「未验证范围」。

## 5. fail-closed 语义:缺字段 / 矛盾时怎么办

协议的默认立场是保守关闭——**未证明适用,就不授予权威**。分两类标记:

### 5.1 `INSUFFICIENT_METADATA`(元数据不足)

关键文档出现以下任一情况:缺 frontmatter、缺 §2 任一必填字段、YAML 无法解析、字段类型错误、枚举值非法。
处置:该正文**不得作为当前权威**;可退回目录 `README.md` 寻找替代入口,但 README 正文同样不能直接取得任务权威。

#### 「未治理」与「漏标签」是两回事

同样是「没有 frontmatter」,含义随库而变:在**已治理的库**里是可疑信号——同侪都有标签,唯独这篇没有,多半是新建时漏了或被人绕过,该拦;在**从未治理过的库**里是正常状态——全库都还没有标签,罚它等于罚这个项目「还没开始」。上面 fail-closed 的立场针对的是前者。

判定语义本身不随库而变:任何模式下,缺字段的文档都不得作为当前权威。变的只是**审计器是否把它算作门禁失败**,由采用模式 `adoption_mode` 决定(见 `src/canonmark/config.py`):

| 模式 | 完全没有 frontmatter | 有 frontmatter 但字段缺/错 |
|---|---|---|
| `gradual`(默认) | 提示「未纳入治理」,不判失败、不影响退出码 | 判失败 |
| `strict` | 判失败 | 判失败 |

一句话原则:**没做的事不罚,做错的事才罚。** 例外是被项目显式列入 `required_key_documents` 的文档——那是项目自己声明「这几篇必须治理」,`gradual` 下缺标签也判失败,因为没兑现自己的声明。

**底线校验对所有贴了标签的文档生效(2026-07-29 起)**:frontmatter 可解析的文档,无论角色与位置,`status` 枚举必须落在配置词汇表内,且 `superseded` 必须带指针、`current` 不得带指针(§5.2 前两条;「非空」按语义判,标量字符串指针同样算)。普通文档的三字段简化形态(§1)仍然合法,缺 `status` 不罚;指针的目标存在性、双向对称与环检测仍是关键文档专属,不在普通文档的底线内。

同一原则同样适用于标签之外的结构约定,`gradual` 下一并降级为提示:目录缺 README、总导航不存在或漏链某个目录、目录名不符合命名规范、未贴标签文档中的坏链。判断依据都是「这是既成事实还是这次做错的事」——存量项目的 `API_Reference` 目录名与历史坏链属前者,改动它们的成本(连带改掉所有指向的链接)远超装上工具的第一天。唯一保留的边界:**贴过标签的文档要为自己的链接负责**,其坏链照旧判失败。

这不是把标准放松,而是把「尚未纳入治理」与「已纳入但写错」分开处置:前者是待办,后者是缺陷。混为一谈的代价是实测过的——一个零 frontmatter 的存量项目装上后,当时的 5 个门里 3 个 FAIL、退出码 1,接上 pre-commit 直接卡死提交,团队的第一反应是关掉整个门禁,与目的相反。

### 5.2 `METADATA_CONFLICT`(元数据矛盾)

出现以下任一情况:

- `status` 与 `current_authority` 不落在 §4 合法矩阵内;
- `status: current` 但 `superseded_by` 非空;
- 同一任务同时命中该文档的 `applies_when` 与 `not_for`;
- `supersedes` / `superseded_by` 反向指针不对称,或替代链成环。

处置:**停止使用该文档,先修元数据**,再重新判定。不允许「先按正文干着、回头再修标签」。

### 5.3 多篇文档同时通过五步:先分工,别误判成冲突

多篇文档都通过五步是**正常协作**,不是冲突。先按 `current_authority` 分工:Roadmap 管加载顺序与阶段,Task 管执行,Contract 管接口 / 行为,Acceptance 管验收,Background 只作说明。
只有**同一范围、同一 authority** 的多篇文档仍给出互斥结论时,才算真冲突:由明确的上级 Roadmap / README 路由或用户指定来收口;在裁决前标记「权威冲突,证据不足」,不擅自选一篇采信。

### 5.4 文档与运行时事实冲突:事实优先

当前代码、配置、日志或测试与文档冲突时,**先报告事实冲突**。元数据只决定「该读谁」,**不能把旧正文变成运行时事实**。文档说接口存在、代码里已删除——以代码为准,文档标记须随之修正。

## 6. 通过五步 ≠ 加载全文:渐进加载

判定通过只是拿到「可以读」的资格,不等于一次性吞下整篇。读取正文必须继续遵守渐进加载,控制上下文开销:

- 先看 H1、目录,或用标题关键词定位章节。
- 只读取回答当前问题所需的章节,以及该章节明确依赖的前置定义或验收条款。
- 遇到链接到另一篇文档时,对新文档**重新执行五步**,不沿链接递归加载全文。
- 需要多个章节时逐段追加;**禁止以「全面理解」为由**一次性读取整篇长文或整个目录。

## 7. 文档发现与读取路径(三层分工)

结论:**默认路径是目录 README 逐层导航,不是全库索引。真正的执行主角是 `canon_read`,它零额外上下文开销。`canon index` 是按需的全局工具,不得写成"每次先跑"的必经路径。**

### 7.1 三层分工

| 层 | 机制 | 何时用 | 上下文成本 |
|---|---|---|---|
| 导航层 | 目录 `README.md` 逐层下钻 | **默认**,找文档的常规路径 | 每层一个小文件 |
| 读取层 | `canon_read(path)` | **读任何 docs 文档时**,替代直接读文件 | **零额外**(这篇本来就要读) |
| 全局层 | `canon index` | 按需:跨目录检索、体检、CI 报告 | 高,**不得默认调用** |

### 7.2 为什么默认是 README 而不是全库索引

逐层导航读的是若干个小文件(每层一个),而全库索引一次返回整库标签。对中大型文档库,后者显著更贵,且 README 由人撰写、带业务语义,定位能力强于机器生成的扁平清单。**把全库索引设为必经路径会污染上下文,与本协议"按需加载"的初衷直接冲突。**

### 7.3 那为什么仍然需要 `canon_read`

两个 README 无法覆盖的失效场景:

1. **README 的状态信息是二手的、靠人手工同步。** 文档作废后,需要有人回头修改上级 README 的文件清单——这与"人会遗忘"是同一个失效模式。`canon_read` 读取的是文档自身头部的声明,不依赖导航被及时更新。
2. **消费者可能绕过导航。** 通过全文检索、外部链接、历史引用直接命中某篇文档时,整个导航层被跳过。

`canon_read` 是导航失效时的安全网,而非导航的替代品。

### 7.4 `canon_read` 的行为契约(核心)

| 目标文档状态 | 返回 |
|---|---|
| `current` 且未命中 `not_for` | 正文 |
| `superseded` / `archive` | **不返回正文**;返回状态与 `superseded_by` 指向的替代目标 |
| 命中 `not_for` | 正文 + 明确的适用性警告 |
| 未纳入治理(无 frontmatter,且 `adoption_mode` 为 `gradual`) | **正文** + 一行说明「此文档未纳入治理,无法验证时效性」 |
| `INSUFFICIENT_METADATA` / `METADATA_CONFLICT` | 诊断信息;正文不得作为权威依据返回 |

设计意图:把协议从**"写给消费者遵守的规矩"**转变为**"消费者获得的数据已经过协议过滤"**。前者依赖自觉,后者是机制。

未纳入治理的文档为什么反而放行正文(见 §5.1 的两种采用模式):拒绝返回的收益是「防止 AI 信一篇过时文档」,代价是「AI 完全无法工作」。在存量项目里代价远大于收益——全库都还没贴标签,逐篇拒绝等于整个 docs 不可读。更现实的后果是工具直接被绕过:`canon_read` 给不出正文,消费者会退回用内置文件读取工具打开文件,那时连一句警告都收不到,比放行更糟。放行至少还附着「无法验证时效性」这句话。`strict` 模式不适用本行——那种库里缺标签是缺陷,按 `INSUFFICIENT_METADATA` 处置。

**实现状态:已实现**(`src/canonmark/read.py`,CLI `canon read`,MCP 工具 `canon_read`)。上表五行逐行有测试守住,其中最要紧的一条是「作废文档的正文一个字都不出现在输出里」——用哨兵串断言,不是靠人肉检查。

**路径边界按调用方分层**(同名能力两层行为不同,必须写进契约):MCP 层**拒绝 docs 树外的路径**——那是给 agent 的接口,不设边界时它就是一个不受限的任意文件读取器,当 agent 被配置成只给 canonmark 工具时那是条现成的绕过路径;CLI 层**不设这条边界**——人手动跑 `canon read` 时知道自己在读什么,强行限制会让它没法用于仓库外的文档。判定在 `resolve()` 之后进行,符号链接逃逸无效。

**能判什么、不能判什么**:上表按 `status` / `superseded_by` 过滤,这些是客观事实,机器可判。但第 3/4 步(`not_for` / `applies_when` 是否命中「当前任务」)是语义判断,`canon_read` **不假装能做**——它不知道调用方在干什么。改为把这两个字段随正文一并交出,由调用方自己比对。假装能匹配比不匹配更危险:一次错误的「不适用」会让 agent 跳过真正该读的文档。

正文交付时会剥掉 frontmatter:那些字段已在头部摘要里给过,再随正文附一遍等于把同样的字节收两次费,与「零额外上下文开销」的主张相悖。

### 7.5 `canon index` 的约束

- 默认输出紧凑(一篇一行),不含长描述。
- 必须支持过滤:按目录、仅列现行、机器可读格式。
- **不得**出现在"每次读文档前先执行"这类接线指引中。

**实现状态:已实现**(`src/canonmark/index.py`,CLI `canon index --dir/--current-only/--json`,MCP 工具 `canon_index`)。紧凑性由两条断言守住:一条是本节的原始判据(真实体量下索引 < 全文的 10%),另一条更本质——**索引大小不随正文变长而增长**,只与篇数有关;后者在任何规模下都成立,前者在文档很短时会失真。

第三条约束(不得写成必经路径)现在也是**机检**的,分两层:

1. **强制原样**:MCP 工具描述必须以常量 `NOT_A_PREREQUISITE` 的原文结尾。之所以要求原样而非「含某几个关键词」——独立验收用 5 组变异测过关键词黑名单,4 组静默放过(「工作流的第一步就执行 canon index」「建议先跑canon index」去掉一个空格即可绕开)。自然语言的等价改写挡不住,统一措辞是可机检的前提。
2. **黑名单兜底**:去空格后匹配若干「先…canon index」变体,覆盖描述、接线片段与宿主话术。

**这道守卫挡得住什么、挡不住什么(如实记录)**:它保证禁令不被改写或删除(禁令期望原文在测试内有独立字面量副本,不与实现共享常量,防同源恒真),**不保证描述别处不出现相反指引**——验收实测,在禁令原样保留的前提下,前面增写「开始任何任务前请务必先调用本工具」仍会静默放过。增写这条路只能靠人工审阅。

### 7.6 README 与文档标签互检

README 文件清单标注为现行、而该文档自身声明已作废时,判为不一致并报错。二者互为校验:导航过期藏不住,标签错误也藏不住。

**已实现**(V11 门):各级 README 中指向 docs 内 Markdown 的链接,若目标文档自称 `superseded` / `archive` 即报错。同门下另有两项**只提示不判失败**的检查——久未复核、孤儿文档(无任何 README 链接指向)。分级的理由是:能明确指认「谁和谁打架」的判失败,只能表达「这里可能变味了」的一律降级,否则整个门禁会被关掉。目标文档尚未纳入治理(无 frontmatter)时无从判断状态,不在本门范围内。

### 7.7 接线话术(写入宿主指令文件的原文)

- 错误:"读 docs 前先执行 `canon index`"
- 正确:**"按目录 README 导航定位文档;读取 docs 下任何文档时使用 `canon_read`,不要直接读取文件。"**

**实现状态:已实现**。`canon init` 生成 `.mcp.json` 片段与上面这句话术(`canon init --print-mcp` 可单独查看);`canon mcp` 以 stdio JSON-RPC 提供 MCP server,把 `canon_read` / `canon_index` 送进 agent 的工具面。

两处设计决定值得记录:

1. **为什么必须有 MCP 这一层**:写在文档里的约定,agent 得先读到那篇文档才知道(先有鸡先有蛋);注册进工具面的能力,它睁眼就看见。这就是 T14 说的「让能力出现在消费者工具面,而非仅存在于文档约定」。
2. **为什么手写 MCP server 而不用官方 SDK**:canonmark 承诺 `pip install` 后纯标准库即可跑。MCP 的 stdio 传输就是逐行 JSON-RPC 2.0,自己实现的体量很小,不值得为省它把一棵额外依赖树压给每个使用者。实现范围限于 `initialize` / `tools/list` / `tools/call` 三个方法,够跑通工具调用;完整握手有测试覆盖。

**诚实边界(2026-08-19 更新:宿主侧钩子已交付)**:话术仍是话术——工具进了列表、描述里写死了「替代直接读文件」,agent 理论上仍可能顺手用内置读取工具绕过去。此前的结论是「拦死需要宿主侧钩子,超出本工具范围」;该钩子现已随仓提供:`canon hook` 实现 Claude Code 的 PreToolUse 拦截协议,内置 Read 命中 docs 根下退休文档(`superseded` / `archive`)时**直接拒绝并给出替代去处**(状态判定与文案和 `canon read` 同一逻辑源);`canon init --print-hook` 打印接线用的 settings.json 片段。这把「先读标签」从三重提示升级为宿主侧强制。已知边界如实保留:**hook 只拦截 Read 工具,Bash `cat` 等其他读取路径不在拦截范围**;current / 未贴标签 / 非 docs 路径 / 解析失败一律静默放行(哲学同 V11 的分级:闸机故障不得锁死全库)。

## 8. 与协议交互的清单(自查)

新建或大改关键文档前自查:

- [ ] 8 字段是否齐全,YAML 可解析,枚举合法(否则 `INSUFFICIENT_METADATA`)
- [ ] `applies_when` / `not_for` 是否具体(不写泛词)
- [ ] `status` × `current_authority` 是否落在 §4 矩阵内
- [ ] `superseded_by` 是否与 `status` 一致(`current` 必须为 `[]`)
- [ ] `supersedes` / `superseded_by` 反向指针是否对称、替代链是否无环
- [ ] 首段是否结论先行,非平凡论断是否带锚点(`file:line` / 数字 / 命令输出)

## 9. 任务框架治理契约(V12/V13)

§1–§8 治理的是单篇文档的权威与生命周期;本节治理的是另一个层面——**AI 长任务的任务框架文档集**(执行总台、任务卡、evidence 目录)作为整体的失控。为什么需要、真实案例见 [vision.md](./vision.md);本节只写机器契约。

### 9.1 任务框架根的判定(两门共同的激活条件)

docs 根下(含任意深度子目录)**包含状态文件的目录即一个任务框架根**。状态文件名由配置 `status_file_name` 指定(默认 `01_EXECUTION_CONTROL.md`,见 `src/canonmark/config.py`)。两条边界:

- evidence 目录整体剪枝:归档的运行产物里即使复制了一份状态文件,也不构成新的框架根;
- 找不到任何框架根时,V12/V13 均不适用,直接 PASS——没有任务框架的项目不为这两门付任何代价。

### 9.2 V12 任务框架预算

对每个框架根,按四个**检查键**测量并对照软 / 硬两级阈值(默认值见 `src/canonmark/config.py` 的 `framework_*` / `evidence_*` 字段,不在本文复制):

| 检查键 | 测量对象 |
|---|---|
| `lines` | 框架根下全部 Markdown 的总行数(排除 evidence 目录) |
| `files` | 框架根下 Markdown 文件数(排除 evidence 目录) |
| `evidence-files` | evidence 目录内文件总数 |
| `evidence-runs` | evidence 下每个任务子目录的运行子目录数 |

判定分三档:

- 超**软阈值**:只提示,不判失败;
- 超**硬阈值**:判失败——除非状态文件里存在对应检查键的批准行;
- **批准行显式放行**:状态文件中一行 `批准: <检查键> <原因> <日期>`,该检查键的硬阈值超限降级为提示并回显批准行。检查键按独立 token 匹配,`批准: evidence-files …` 不会顺带放行 `files`。

预算的目的不是禁止大框架,而是让「变大」成为一次留痕的显式决定——谁批的、为什么、哪天,一行可追溯。

### 9.3 V13 状态登记表

状态只准记录在状态文件的**唯一登记表**里。三层检查:

1. 状态文件必须**恰好包含一张**表头为 `id`、`status`、`updated_at` 的 Markdown 表(零张、多张均判失败);
2. 表行 `id` 不得重复;`status` 必须落在配置枚举 `status_registry_statuses` 内(默认:`PASS` / `FAIL` / `BLOCKED` / `READY` / `EVIDENCE_READY` / `ACTIVE` / `INSUFFICIENT_EVIDENCE` / `NOT_APPLICABLE`);
3. **绊线**:框架根下其他 Markdown(排除状态文件与 evidence 目录)正文中出现枚举内的独立大写 token 即报告。这是绊线不是语义保证——只能证明状态词出现在了登记表之外,不判断它是不是一条状态记录;fenced code block 视为示例不扫,frontmatter 是受治理的元数据、不在射程内。

与其余各门一致,两门是**纯快照检查**:只读工作区文件,零 git、零 subprocess。
