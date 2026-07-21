---
status: current
owner: canonmark
last_reviewed: 2026-07-21
---

# canonmark 文档

本目录是 canonmark 项目的文档层。canonmark 用自己的规范治理自己的文档(dogfood),这里每篇关键文档都带完整 frontmatter。

## 导航

| 文件 | 用途 | 权威角色 |
|---|---|---|
| [roadmap.md](./roadmap.md) | 阶段规划与顺序 | roadmap-current |
| [acceptance.md](./acceptance.md) | 验收矩阵 | acceptance-current |
| [kickoff.md](./kickoff.md) | 编排纪律与红线 | contract-current |
| [progress.md](./progress.md) | 进度心跳日志 | 记录 |
| [design/vision.md](./design/vision.md) | 价值与要解决的问题 | background-reference |
| [design/protocol.md](./design/protocol.md) | 权威元数据契约与五步判定协议 | contract-current |
| [tasks/](./tasks/) | 任务分片 | task-current |

## 状态说明

- current:当前生效
- background:背景参考,不主导当前任务
- archive / superseded:历史,不作依据

## 怎么读(frontmatter-first)

把任何文档当依据前,先只看头部 frontmatter,按 `superseded_by → status → not_for → applies_when → current_authority` 五步判定该不该读、能主导什么。详见 [design/protocol.md](./design/protocol.md)。
