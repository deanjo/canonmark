---
status: current
applies_when: 定义/校验文档权威元数据 8 字段、执行五步权威判定协议、判断 status×current_authority 组合是否合法、处理缺字段或矛盾元数据的 fail-closed 行为
not_for: 价值主张与竞品边界(见 vision.md)、阶段规划顺序(见 roadmap.md)、验收判定标准(见 acceptance.md)
current_authority: contract-current
supersedes: []
superseded_by: []
owner: canonmark
last_reviewed: 2026-07-21
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

## 5. fail-closed 语义:缺字段 / 矛盾时怎么办

协议的默认立场是保守关闭——**未证明适用,就不授予权威**。分两类标记:

### 5.1 `INSUFFICIENT_METADATA`(元数据不足)

关键文档出现以下任一情况:缺 frontmatter、缺 §2 任一必填字段、YAML 无法解析、字段类型错误、枚举值非法。
处置:该正文**不得作为当前权威**;可退回目录 `README.md` 寻找替代入口,但 README 正文同样不能直接取得任务权威。

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

## 7. 与协议交互的清单(自查)

新建或大改关键文档前自查:

- [ ] 8 字段是否齐全,YAML 可解析,枚举合法(否则 `INSUFFICIENT_METADATA`)
- [ ] `applies_when` / `not_for` 是否具体(不写泛词)
- [ ] `status` × `current_authority` 是否落在 §4 矩阵内
- [ ] `superseded_by` 是否与 `status` 一致(`current` 必须为 `[]`)
- [ ] `supersedes` / `superseded_by` 反向指针是否对称、替代链是否无环
- [ ] 首段是否结论先行,非平凡论断是否带锚点(`file:line` / 数字 / 命令输出)
