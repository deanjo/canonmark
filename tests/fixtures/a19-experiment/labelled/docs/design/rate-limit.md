---
status: superseded
applies_when: 追溯限流方案的历史演进
not_for: 当前限流实现依据
current_authority: historical-evidence
supersedes: []
superseded_by: [rate-limit-v2.md]
owner: platform
last_reviewed: 2026-02-14
---

# 网关限流设计

## 算法选型

采用**固定窗口计数**（fixed window counter）。每个窗口起始时把计数清零，
窗口内累计请求数超过阈值即拒绝。实现简单，内存开销小。

## 阈值

单实例阈值定为 **100 QPS**。超过后返回 429，`Retry-After: 1`。

## 实现要点

计数器放在本地内存，不做跨实例同步——窗口边界的突发流量可以接受。
