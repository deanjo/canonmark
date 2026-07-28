---
status: current
applies_when: 查看或更新跨会话的任务状态与阶段归属、判断某个任务当前处于哪一步
not_for: 阶段规划顺序(见 roadmap.md)、验收判定(见 acceptance.md)、协议字段定义(见 design/protocol.md)
current_authority: task-current
supersedes: []
superseded_by: []
owner: canonmark
last_reviewed: 2026-07-28
---

# canonmark 任务台账

结论:这是跨会话的任务状态单一事实源。状态五态:TODO / DOING / DONE / BLOCKED / NEEDS-VERIFY。验收判定见 [acceptance.md](../acceptance.md),阶段顺序见 [roadmap.md](../roadmap.md)。

| 任务 | 阶段 | 负责 | 状态 | 证据 / 备注 |
|---|---|---|---|---|
| T0 项目骨架 + 权威文档 | P0 | 主 agent | DONE | git 5e65863;roadmap/acceptance/kickoff/progress/docs-README 已落盘 |
| T1 命名裁决(禁 agent_ 为默认,agong 走例外) | P0 | 主 agent | DONE | 记录在 roadmap.md「命名裁决」 |
| T2 抽取参数化 docs-audit.py → src/canonmark | P1 | 实现 agent | DONE | 必修全做(audit_v5 主体/L471/词汇表/trigger_paths);独立验收 A1-A3 PASS |
| T3 canonmark.toml 自审配置 | P1 | 实现 agent | DONE | 自审 A6 全门 PASS exit 0(门数会随阶段增加,此处不复制具体数字) |
| T4 迁移 42 单测 + 12 文件 fixture | P1/P4 | 实现 agent | DONE | 迁移范围为 42 个用例(`DocsAuditTest` 至今恰好 42);invalid 精确报 6 类 exit1、valid exit0(A8/A9) |
| T5 排除不可移植件(gen_diagrams/task-packet/java) | P2 | 实现 agent | DONE | grep src/ 无代码依赖(A4 PASS) |
| T6 设计文档(vision/protocol)+ README 门面 | P0 | 文档 agent | DONE | vision(305 文件冲突已实测)/protocol(8字段+五步+矩阵)/README 门面已写;3 取舍认同:宽松矩阵不纳 sharding 严子集、不编造 P1 代码行号、无环检测标为待 P1 验;protocol 自洽性并入 T8 复核 |
| T7 自审反馈链路(pre-commit + Action + CI) | P3 | 主 agent | DONE | 4 文件已写;本地 pre-commit 真跑 `Passed` exit 0(A7 本地);远端 CI 待推送后验 |
| T8 独立 subagent 验收 A1–A11 | P4 | 验收 agent | DONE | 独立复现判定 ACCEPT,A1–A11 全 PASS,无 FAIL;含 protocol 自洽核对 |
| T15 渐进采用(adoption_mode) | P5 | 实现 agent | DONE | `adoption_mode` = `gradual`(默认,结构性缺失降为提示)/ `strict`(照旧判失败),非法值 `__post_init__` 抛 ValueError;`GateResult.notice` 提示通道只打印不影响退出码;`required_key_documents` 内置默认清空(原 agong 现值会让陌生项目一装就报错),`canon init` 模板同步;`superseded_by` 目标不存在的报错补两种路径口径说明 + 可照抄写法;仓库根 `canonmark.toml` 设 strict,自审全门 PASS exit 0(计数以本表「波次 2」段为准,不在此处重复维护) |
| T10 反向指针对称检查 → 判失败 | P5 | 实现 agent | DONE | 并入 V5(与既有替代链环检测同族);`declares_pointer` 按解析后路径比对,两端可各用一种口径;报错含「对方应加哪一行」。**两个方向都做**:`superseded_by`→查对方 `supersedes`,以及 protocol §2 明文举例的 `supersedes`→查对方 `superseded_by`(**首轮只做了前者,被独立验收抓出**;后者更危险——漏掉时旧文档继续自称 current,两篇同时以现行权威示人)。两处跳过:`status: current`(已判矛盾)与替代链成环(让对方认领会把环缠更紧) |
| T11 超期提示 + 孤儿检测 | P5 | 实现 agent | DONE | 新增 V11 门,**一律只进 notices 不影响退出码**;阈值 `last_reviewed_max_age_days` 默认 180 天且可配。孤儿检测四类豁免:README 自身、docs 根下文档、**所在目录还没有 README 时**(否则同一件事对该目录每篇文档各说一遍,V4 已提示过一次)、**已作废文档**(它们本就不该被导航链接,劝人加进 README 等于劝人踩 T12 那个错)——后两类由独立验收发现。**原任务名中的「新增未声明替代提示」不做**,理由见 roadmap P5 第 ④ 项 |
| T12 README 清单与文档标签互检 | P5 | 实现 agent | DONE | 并入 V11;各级 README 指向自称 `superseded`/`archive` 的文档即判失败(protocol §7.6 已标注实现);目标未贴标签时无从判断状态,跳过。**`archive/` 下的索引 README 豁免**——列出归档文档正是它的本职(独立验收发现的误报) |
| T13 `canon_read` 行为契约 + `canon index` 紧凑输出与过滤 | P6 | 实现 agent | DONE | `src/canonmark/read.py` + `index.py`,CLI `canon read` / `canon index --dir/--current-only/--json`。**首轮独立验收判定 REJECT → 修复后复验判定 ACCEPT**(必办已完成并入 commit 6e21f78;A17/A18 是否据此置 PASS 待用户拍板,过程见下「波次 3」段)。作废文档正文不返回(哨兵串断言,不靠人肉检查);正文交付时剥掉 frontmatter(头部摘要已给过,再附一遍等于同样的字节收两次费)。**机器判客观事实,不假装判语义**:按 status/superseded_by 过滤是机器的活,`not_for`/`applies_when` 是否命中当前任务由调用方判断——假装能匹配比不匹配更危险,一次错误的「不适用」会让 agent 跳过真正该读的文档。index 的紧凑性由「大小不随正文变长而增长」守住,比原判据「< 全文 10%」更本质(后者在文档很短时会失真) |
| T14 MCP server + `canon init` 生成接线片段 | P6 | 实现 agent | DONE | `src/canonmark/mcp.py`(stdio JSON-RPC,`canon mcp`)+ `canon init --print-mcp`。**手写而非用官方 SDK**:canonmark 承诺 `pip install` 后纯标准库即可跑,MCP 的 stdio 传输就是逐行 JSON-RPC,自己实现的体量很小,不值得为省它引入额外依赖树;范围限于 initialize/tools/list/tools/call,完整握手有测试。**§7.5/§7.7 的措辞约束已机检,两层守卫**(现版口径;首版关键词黑名单被独立验收的变异测试击穿后改造):①强制原样——工具描述必须以禁令常量 `NOT_A_PREREQUISITE` 原文结尾,且该原文在测试内有独立字面量副本,防同源恒真;②去空格黑名单兜底——去空格后匹配「先…canon index」变体,覆盖描述、接线片段与宿主话术(须为 §7.7 原文)。如实边界:挡得住改写与删除,挡不住在别处增写相反指引,那只能靠人工审阅——把废止过的设计交给人的记性守不住,能交给测试的都交给测试。验收口径同 T13(首轮 REJECT → 复验 ACCEPT) |
| T9 发布准备(README/pyproject 完善)+ 远程发布 | P7 | 主 agent + 用户 | TODO | 远程发布留用户拍板(红线);发布物基本齐 |

## 当前波次

- 波次 1(DONE):实现 + 文档两 agent 并行交付,独立验收 ACCEPT,P3 反馈链路本地跑通。已完成 P0–P4 全部验收项(A0–A11 PASS)。
- **波次 2(DONE,独立验收 ACCEPT):T15 渐进采用 + T10–T12 防腐烂检查组**。T15 必须打头,不是先后随意:T10 是把要求提得**更严**,而实测证明存量项目连当前这一档都过不去——给旧文档贴一张「我作废了,去看 v2」的标签(收益最高、最该做的第一步)就会因为 v2 还没贴标签而判 FAIL。先做 T10 再补渐进采用,T10 的判定逻辑要按新语义重写一遍。
  **第一轮独立验收判定 REJECT**,查出 7 个问题,已全部修复:①**最严重——P5 打破了已 PASS 的 A8/A9**(`tests/fixtures/` 不被任何测试引用,只有人工跑 CLI 才碰得到,于是无声破坏,而 acceptance.md 里两项仍标着 PASS)。修法不只是补 fixture,而是**新建 `tests/test_fixtures.py` 把双向 oracle 接进 pytest**,让同一件事不会再发生第二次;②T10 只做了一半(见上行);③gradual 内部自相矛盾——V4 说「这个目录的 README 可以先不建」,V9 却硬性要求总导航链接那个还不存在的文件,于是「有一个不完整的索引」这种存量项目的典型形态照样被打红;④V2/V10 完全不参与渐进采用(非 kebab 目录名、历史坏链仍硬判失败);⑤T12 误伤 archive 索引;⑥孤儿提示给作废文档出的主意照做就会 FAIL;⑦文档内计数自相矛盾。
  **第二轮独立验收:代码侧 6 项(#1–#6)全部复现通过**——含「破坏 fixture 后新测试确实会失败」的反证、V10 边界(贴过标签的文档坏链仍 FAIL)、孤儿检测没被做废(README 存在但漏链时仍提示)。对抗性检查确认 **gradual 下仍有 16 类判失败**(替代关系全部一致性、标签本身全部正确性、导航与标签互检一条没放),T15 没把工具做废。
  **但第二轮仍判 REJECT,卡在文档口径**:roadmap 留着「66 passed」和「独立验收尚未进行」,acceptance.md 这一轮**新写进去** A13「6 用例」、A22「3 用例」「五门」三处错数——复核命令就印在同一行里。**教训已写进 roadmap P5:在防文档腐烂的项目里手抄会变的数字就是在制造腐烂,数字要么由命令现场产出,要么只在单一位置维护。** 已按此改掉全部计数陈述,并顺带修掉验收附带发现的 N2(孤儿检测硬编码 README.md,不随 `navigation_readme_filename` 变)、N3(`v2_path_exceptions` 默认值仍带 agong 目录名,会印进陌生项目的报错文案)、N4(T10 修复指导不完整,照抄后还会因 `current_authority` 再失败一轮)、N5(fixture 测试用 mutate + 手调 `__post_init__`,改为与 CLI 一致的 `dataclasses.replace`)。N6(以 `---` 水平线开头的存量文档被误判为已治理)未修,记入 [acceptance.md](../acceptance.md) 的「未验证范围」。
  **第四轮复验判定 ACCEPT。** 通过的理由不是「问题变少了」,而是问题的性质变了:前三轮每次都是「改掉被点名的几处,再在相邻位置以同样方式错一次」,直到修法从「改数字」升级为「不写数字 + 让机器守」。验收用 11 组独立变异攻击新守卫(重排版、全角冒号、改写措辞、语序翻转、谎报、把注释挪出注释行、新增一道 V12 幽灵门…),确认**没有任何一条路径是「解析不出来就当通过」**——静默放过才是真问题,不存在。A13–A16 / A20–A22 已置 PASS,A8/A9 恢复 PASS。
  遗留非阻塞项:V11 孤儿检测在单目录数千文件时为 O(n²)(实测 2000 篇同目录约 7.8s,iterdir 占八成,一行 dict 缓存可解);T10 一步收敛的承诺仅在 `status_authority_matrix` 对 `superseded` 恰好允许一个 authority 时成立(默认配置如此,多值时降级为不提示 authority,降级本身正确)。
- **波次 3(DONE,复验判定 ACCEPT):T13–T14 读取接线**。顺序不可与波次 2 颠倒——理由见 roadmap「依赖顺序」。
  **首轮独立验收判定 REJECT**,3 个阻塞 + 6 个非阻塞,已全部处理:①MCP server 被一行**合法**JSON(批量数组/裸标量)打死,而覆盖它的测试只测了「不可解析的文本」——虚假信心;②`cli.py` 的 docstring 只声明 5 个子命令里的 2 个,**正是 P5 建 `test_contract.py` 专门要防的那类错,守卫没随新模块扩容于是在隔壁文件原样复发**,现已把守卫扩到「docstring 声明的子命令 = parser 实际注册的」;③无 PyYAML 时 `canon index` 静默把全库标成「无标签」、`--current-only` 安静回答「没有现行文档」,现改为明确报错并加实测守卫;④接线话术守卫被 5 组变异骗过 4 组(关键词黑名单挡不住语义改写),改为把禁令固定成常量强制原样出现,并**如实标注这道守卫挡不住什么**;⑤`canon_read` 曾是无限制任意文件读取器,现按调用方分层——MCP 层钉在 docs 树内(给 agent 的受限接口),CLI 层放行(人手动跑时知道自己在读什么);⑥BOM 开头的作废文档会泄漏全文(与已知的 `---` 水平线边界同根),已在 frontmatter 识别处剥掉 BOM;⑦`--dir ..` 静默返回整棵树、⑧索引可被 frontmatter 换行注入伪造行(违反「一篇一行」硬约束)、⑨三处手抄数字(**第五次栽在同一个坑**)。
  A19 的证据可复现性也是验收点名的:原先夹具只活在临时目录、提示词与原始输出都没保存——「只能被相信,不能被验证,而 P6 的出口恰恰是不接受相信」。现已落进 `tests/fixtures/a19-experiment/`(两份正文逐字相同、仅差标签的夹具 + 提示词 + 四组结果摘录 + 复现命令)。
  **修复后复验判定 ACCEPT**(附两项必办,已完成并入 commit 6e21f78)。acceptance 的 A17/A18 是否据此由 INSUFFICIENT_EVIDENCE 置 PASS,待用户拍板,拍板前维持原状态;当前推进的是审读修复(可信度收尾),波次 4 之前的最后一道门。
- 波次 4:T9 发布决策(红线,需用户拍板)。
- 设计依据:三层分工(README 导航 / `canon_read` 兜底 / `canon index` 按需)见 `docs/design/protocol.md` §7,**该节是 2026-07-21 对早期设计的更正**:早期方案曾把「每次先跑全库索引」作为默认路径,会污染上下文,已废止。
