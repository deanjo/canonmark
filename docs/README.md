---
status: current
owner: canonmark
last_reviewed: 2026-09-20
---

# canonmark 文档

本目录是 canonmark 项目的文档层。canonmark 用自己的规范治理自己的文档(dogfood),这里每篇关键文档都带完整 frontmatter。

## 导航

| 文件 | 用途 | 权威角色 |
|---|---|---|
| [design/protocol.md](./design/protocol.md) | 权威元数据契约与五步判定协议 | contract-current |
| [design/vision.md](./design/vision.md) | 价值与要解决的问题 | background-reference |
| [acceptance.md](./acceptance.md) | 验收矩阵与诚实边界(已知绕过、未证明的收益) | acceptance-current |
| [design/](./design/README.md) | 设计文档索引 | — |

## 状态说明

- current:当前生效
- background:背景参考,不主导当前任务
- archive / superseded:历史,不作依据

## 怎么读(frontmatter-first)

把任何文档当依据前,先只看头部 frontmatter,按 `superseded_by → status → not_for → applies_when → current_authority` 五步判定该不该读、能主导什么。详见 [design/protocol.md](./design/protocol.md)。
