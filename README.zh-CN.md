# canonmark

*[English](README.md) · 简体中文*

> **告诉你的 AI agent,该信哪篇文档。**

你的 `docs/` 目录现在是 AI 的上下文。AI 编程助手(Claude Code、Cursor、Copilot)
把里面每一篇都当成权威来读——包括你三个月前就作废的那篇、描述着早已删除接口的
那份规范、以及互相矛盾的两套指南。现有的检查工具管格式、管措辞、管断链,
**没有一个会问「这篇文档还算不算数」**。canonmark 就是补这一问的。

canonmark 把「文档权威」变成每篇关键文档头部的一份机器可校验的契约:谁现行、
谁被取代、冲突时谁说了算、这篇文档能拍板什么。然后在文档说谎时,把构建拦下来。

同样重要的一点:让 agent **先读标签,再读正文**。五步判定协议要求先解析
frontmatter(文档头部的元数据块),而 `canon_read` 把这个习惯变成了机制——
读一篇已作废的文档,拿到的是替代文档的指针,永远不是它的正文。

## 前后对比

**之前** —— 没有任何标记说旧文档已死,于是 agent 信了它:

```
docs/
  api-design.md          # (无元数据) —— 描述着已删除的接口 POST /v1/sync
  api-design-v2.md       # (无元数据) —— 真正现行的设计

agent 读到 api-design.md → 自信地写下对 POST /v1/sync 的调用 → 构建挂了。
```

**之后** —— 一个 `superseded_by` 指针,把 agent 引到真正算数的那篇:

```
docs/
  api-design.md          # status: superseded   superseded_by: [api-design-v2.md]
  api-design-v2.md       # status: current      current_authority: contract-current

agent 先解析 frontmatter → 跟随 superseded_by → 改读 api-design-v2.md。
旧正文从未作为现行事实进入上下文。
```

## 它做什么

- 在每篇关键文档的 frontmatter 里定义一份 **8 字段权威契约**
  (`status`、`applies_when`、`not_for`、`current_authority`、`supersedes`、
  `superseded_by`、`owner`、`last_reviewed`)。
- 给 agent 一套**五步判定协议**——`superseded_by → status → not_for →
  applies_when → current_authority`——让它在读正文*之前*先读头部,
  绝不把死文档当成活事实。
- **失败时向严处理。** 字段缺失或元数据自相矛盾会被点名
  (`INSUFFICIENT_METADATA` / `METADATA_CONFLICT`),而不是默默相信那份过期正文。
- 把它变成**门禁**:在 pre-commit 和 CI 里跑 `canon audit docs/`,
  标签就不会悄悄腐烂。
- 也治理**任务框架文档**(V12/V13 两道门):给框架文档和证据目录的体量设预算,
  再加一张唯一的状态登记表——状态词被复制到登记表之外就会绊线报警。
  这是为长期 AI 任务留下的那堆「作战文档」准备的。

## 为什么要做

两件事同时成立:过期和互相矛盾的文档,是大模型上下文里最强的干扰项;
而相当大比例的文档写完之后再也没被更新过。结果就是:一个通过了所有现有
检查工具的 `docs/` 目录,依然能把 agent 直接带进错误的代码——因为从来没有
哪个检查器问过一句*「这篇还算不算数?」*。canonmark 就是这道缺失的检查,
是 AI 上下文工具栈里的**文档生命周期层**。

## 它站在哪一层(是补位,不是替代)

| 工具 | 管什么 |
|---|---|
| `llms.txt` | 你的公开**网站**向大模型暴露什么 |
| `AGENTS.md` | 你给 agent 的**工作指令**(怎么干活) |
| `Vale` / `markdownlint` / `lychee` | **措辞、格式、断链** |
| **canonmark** | **文档权威与生命周期**——该信哪篇,以及信到什么时候 |

一句话:**AGENTS.md 告诉 agent 怎么干活,canonmark 告诉 agent 该信哪篇文档。**

还有一层分工:canonmark 是**检查端**。与它配套的**写作端**是
`technical-plan-sharding` skill,它指导怎么写出那套分片方案文档
(Roadmap 入口、契约分片、任务分片、验收矩阵)——正是这些门要校验的对象。
该 skill 尚未随本仓发布;元数据词汇表与合法矩阵只有一个事实源,即
[protocol §4](docs/design/protocol.md),写作端引用它而非复制。

## 快速开始

```bash
pip install git+https://github.com/deanjo/canonmark
```

需要 Python 3.9 以上(CI 实测覆盖 3.9 到 3.13)。PyYAML 会被自动装上——
它是真正的依赖,不是可选附加项,所以全新环境装完即可用。

暂未发布到 PyPI,所以直接从 git 装:一条命令,效果相同。
(从克隆的仓库装:`pip install -e .`)

```bash
canon init                     # 生成 canonmark.toml,并打印 MCP 接线配置
canon audit docs/              # 审计权威元数据;有冲突时退出码非 0
canon read docs/design/x.md    # 按契约读一篇文档(见下文)
canon index --current-only     # 紧凑的标签清单;按需使用,绝不是读文档的前置步骤
canon mcp                      # 以 MCP server 运行,让 agent 的工具面出现 canon_read
canon hook                     # Claude Code PreToolUse 钩子:拦下对作废文档的内置读取
```

### 接进你的门禁

pre-commit —— 加进 `.pre-commit-config.yaml`,然后 `pre-commit install`:

```yaml
repos:
  - repo: https://github.com/deanjo/canonmark
    rev: v0.1.0
    hooks:
      - id: canon-audit
```

GitHub Actions —— 在工作流里加一步:

```yaml
      - uses: deanjo/canonmark@main
        with:
          path: docs/
          config: canonmark.toml
```

或者在任何 CI 里直接调命令行:标签写错时 `canon audit docs/` 会以非 0 退出码收场。

> **如果钩子报 `Executable canon not found`:** pre-commit 在它自己的环境里运行,
> 所以 `canon` 必须在「执行提交的那个进程」的 `PATH` 上。最常见的原因是
> canonmark 装在虚拟环境里,而你在虚拟环境之外提交——先激活虚拟环境,
> 或者给命令加前缀 `PATH="$PWD/.venv/bin:$PATH"`。

### 让 agent 先读标签(Claude Code)

两处接线,都能直接打印出来,粘贴即可:

```bash
canon init --print-mcp     # .mcp.json 片段:把 canon_read 送进 agent 的工具面
canon init --print-hook    # .claude/settings.json 片段:PreToolUse 拦截
```

MCP 那份是*提供*正确的工具,hook 那份是*强制*它。装上 hook 之后,agent 若对
`docs/` 下的作废文档伸手去用内置的文件读取工具,会收到一个拒绝,外加指向现行
文档的去处——作废正文根本不会进入上下文窗口。这个 hook 采取「失败即放行」:
一旦它解析不了事件、配置或文件,就保持沉默、让读取照常进行,所以一个坏掉的
闸机永远不会把你锁在自己的文档库外面。

`canon audit` 只解析每篇关键文档的 frontmatter,拿它对照权威契约,
把每一处 `INSUFFICIENT_METADATA` / `METADATA_CONFLICT` 连同文件路径报出来——
可以直接接进 pre-commit 和 CI。

### 它不会让你的老仓第一天就变红

把 canonmark 指向一个存在多年、还没有任何 frontmatter 的 `docs/`,它的退出码是
**0**。规矩是:**没做的事不罚,做错的事才罚。** 没贴标签的文档、缺失的导航,
都以「提示」的形式报出来并给出下一步动作;只有*已经*贴了标签却写错的文档,
才会判门禁失败。所以你可以一篇一篇地采用——给一篇过期设计文档贴上
「已被 v2 取代」,这本身就是完整且有用的一步,不会逼着你连带去给 v2
和 v2 指向的所有文档都贴标签。

有一处细节要说清楚,免得上面这个承诺不诚实:一篇文档如果首行是 `---`
**水平分割线**,曾被误读为「没有闭合的 frontmatter」,即使在渐进模式下也判失败。
2026-07-29 已修复:渐进模式现在会看 `---` 后面跟的是什么——如果不像 YAML 键,
就把这篇算作单纯没贴标签(提示,退出码 0)。而 `---` 后面确实跟着像 YAML 键的
东西,在任何模式下仍然判失败:真写了标签却忘了闭合,是值得抓出来的错误。
这份宽容的诚实代价,记录在 [docs/acceptance.md](docs/acceptance.md):以 YAML
注释行开头的标签、或者 `status:current` 这种冒号后漏空格的手误,现在在渐进
模式下会被读成「未贴标签」而不再报错。

等一个文档库完成治理,就在 `canonmark.toml` 里改成
`adoption_mode = "strict"` 正式开启严格模式,结构性缺口会重新判失败
(canonmark 就是这样审自己的)。

### 更进一步:`canon_read`,执行层

canonmark 的核心是上面那部分:**标签,加上审计门禁。** 在我们的对照实验里
(见「状态」一节),光是标签就完成了大部分工作——agent 从「大概是这篇吧,
请你确认一下」变成了不用任何工具就给出确定且正确的判断。`canon_read` 是在这个
基础上,补那些导航覆盖不到的场景:一份没人更新的 README,或者 agent 通过搜索
直接落到某篇文档上。标签只有在有东西照它行动时才起作用,`canon_read`
就是那个行动的东西:拿它去读一篇已退休的文档,**正文根本不会返回**——
你拿到的是它的状态,以及该去哪里。

```
$ canon read docs/design/rate-limit.md
docs/design/rate-limit.md — 已作废（status: superseded）
本文档不再有效，正文按权威契约不予返回。
请改读以下现行文档：
  - docs/design/rate-limit-v2.md
```

跑 `canon init` 会打印一段 `.mcp.json` 配置,外加一句给你
`CLAUDE.md`/`AGENTS.md` 的话术。之后每次启动,`canon_read` 都会出现在 agent 的
工具列表里——这个能力活在工具面上,而不是躺在一句「需要 agent 自己去读文档才能
发现」的约定里。

那曾经是诚实的能力上限:**过滤,而非强制**——工具在列表里,描述也写着「用这个
而不要直接读文件」,但 agent 依然可以伸手去够它内置的文件读取器。现在宿主侧的
钩子已经随仓提供:`canon hook` 实现了 Claude Code 的 PreToolUse 协议,拒绝对
`docs/` 下作废文档的内置 `Read`,并给出与 `canon read` 相同的替代指针;
`canon init --print-hook` 会打印接线用的 `settings.json` 片段。在支持钩子的
宿主上,读取路径从「过滤」升级成了「强制」。仍然存在的边界,如实写在这里:
这个钩子只拦截 `Read` 工具——通过 `Bash`(`cat`、`head` 等)读文件是已知的
绕过路径,有意不封;而解析失败一律静默放行,因为一个坏掉的闸机绝不能把
整座图书馆锁上。

它在机制上真正给你的东西是:一篇作废文档的正文永远不会进入上下文窗口,
所以它不可能成为 agent 后来拿去模式匹配的那个东西。

## 中文文档是一等公民

CJK(中日韩)文档在这里是一等公民,不是事后补丁。字段值、`applies_when` /
`not_for` 里的场景描述、审计输出,全都原生支持中文(以及其它非 ASCII)内容——
所以一个中文文档库,得到的权威保证和英文库完全一样。这是刻意的差异化:
canonmark 被抽取出来的那个来源项目,运行着一个大型中文文档库。

## 文档

- [Roadmap](docs/roadmap.md) —— 八个阶段(P0–P7)以及各阶段交付什么。
- [愿景](docs/design/vision.md) —— 问题、价值,以及 canonmark 与相邻项目的差异。
- [协议](docs/design/protocol.md) —— 8 字段契约与五步判定协议的完整规范。

## 状态

**早期开发阶段——P0–P7 全部完成(2026-07-29 起公开);P0–P5 经独立验收,
P6 首轮 REJECT、修复后复验 ACCEPT。** 审计器已从来源项目中抽取并完全参数化。
抽取时(P1)其默认输出经核验与原版逐字节一致——这是一个带日期的事实,不是长期
承诺:自 P5 起默认输出有意与原版分岔,因为来源项目遗留的默认值被清空,
且新增的取代关系对称性检查会报出原版从不报的问题
(见 [docs/acceptance.md](docs/acceptance.md) 的 A1/A2 注记)。
invalid / valid 两套夹具构成双向 oracle(既验证「该报的报中」也验证
「修好后放行」),canonmark 通过 pre-commit 和 CI 审计自己的文档。
P5 加入了防腐烂检查——取代指针必须双向对称、导航不得列出已退休文档——
以及上文描述的渐进采用模式。

P6 加入了读取路径:`canon read`(按契约过滤的投递)、`canon index`(紧凑清单)、
`canon mcp`(一个 MCP server,手写 stdio JSON-RPC,因此不引入任何 MCP SDK;
PyYAML 自 2026-08-19 起成为硬依赖,好让全新的 `pip install` 开箱即用)。
P6 经过两轮独立验收:首轮 REJECT(九个问题),修复后复验 ACCEPT。
关于「贴标签有没有用」的对照实验记录在
[docs/acceptance.md](docs/acceptance.md)——**包括它没能证明的部分**:
在实验规模下,`canon_read` 相对「只贴标签」的增量收益仍未被证明。

2026-08-19 加入宿主侧拦截(`canon hook`)、任务框架治理(V12/V13),
并完成成品化:PyYAML 转正、CI 覆盖 3.9–3.13、装用文档补齐。
尚未发布到 PyPI,目前从 git 安装。验收矩阵见
[docs/acceptance.md](docs/acceptance.md),当前状态见
[docs/progress.md](docs/progress.md)。

## 许可

MIT —— 见 [LICENSE](LICENSE)。
