---
status: current
applies_when: 实现或修改网关限流逻辑、确定限流算法与阈值
not_for: 鉴权、路由、灰度发布
current_authority: contract-current
supersedes: [rate-limit.md]
superseded_by: []
owner: platform
last_reviewed: 2026-07-20
---

# 网关限流设计 v2

## 算法选型

改用**滑动窗口日志 + 令牌桶**（sliding window log + token bucket）双层结构。
固定窗口在窗口边界会放过两倍突发流量，线上已出过一次事故，故废弃。

## 阈值

单实例阈值提高到 **300 QPS**，令牌桶容量 450，允许短时突发。

## 实现要点

计数状态放 Redis 做跨实例同步，本地只保留令牌桶。
