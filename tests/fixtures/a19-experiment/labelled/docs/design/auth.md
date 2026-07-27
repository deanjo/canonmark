---
status: current
applies_when: 实现或修改网关鉴权逻辑
not_for: 限流、路由
current_authority: contract-current
supersedes: []
superseded_by: []
owner: platform
last_reviewed: 2026-06-01
---

# 网关鉴权设计

JWT 校验放在网关层，密钥从 KMS 拉取并缓存 5 分钟。
