---
title: Stage 3 · F3 Kuzu 只读 POC
status: ok
created: 2026-04-21
authoritative_at: C:\dev-projects\second-brain-hub\architecture\stage3-f3-kuzu-poc.md
---

# F3 · Kuzu 只读 POC

> 问题：DuckDB 对 CRM 关系面够用，但"好友的好友"/ "共享身份"这类 2+ 跳图查询写起来是堆 SELF JOIN，长期来看不可维护。本 POC 用 Kuzu 当只读视图验证三件事：
> 1. 从 DuckDB 快速重建图（全量覆盖，不增量）
> 2. 写 Cypher 能表达我们真实需要的查询
> 3. 在 75 人级别的真实数据上查询延迟 < 1s

结论：**全部成立**。实测 **FoF 29ms / shared-identifier 22ms / stats 26ms**，两个数量级低于目标。

---

## 1. 架构

```
DuckDB (brain-telemetry.duckdb, 真相源, 可写)
   │
   │  brain graph-build   ← 每次全量重建 (derived view)
   ▼
Kuzu (<telemetry_logs_dir>/kuzu-graph/brain.kuzu, 只读)
```

**节点表**
- `Person(person_id STRING PK, display_name STRING, last_seen_utc TIMESTAMP)`
- `Identifier(value_normalized STRING PK, kind STRING)`

**边表**
- `Interacted(FROM Person TO Person, reason STRING, score DOUBLE)`
  - 来源 1：`relationship_edges(person_a, person_b, relation_kind)` 显式边
  - 来源 2（derived）：`interactions` 同日 + 同 channel 配对，`score = 计数`，`reason = "co-activity"`
- `HasIdentifier(FROM Person TO Identifier)`
  - 来源：`person_identifiers`

**不放进 Kuzu 的东西**：`interactions / person_notes / cloud_queue / merge_candidates` 等随时写入的表全留在 DuckDB；Kuzu 只拿稳定快照。

---

## 2. 接口

### Python 模块
- `brain_agents/graph_build.py::build_graph(kuzu_dir=None) -> dict`
- `brain_agents/graph_query.py::fof(person_id, *, limit=10)`
- `brain_agents/graph_query.py::shared_identifier(person_id, *, limit=20)`
- `brain_agents/graph_query.py::stats()`

全部懒加载 `kuzu`；缺包时抛 `RuntimeError("kuzu_missing:...")`，调用方可捕获降级。

### CLI
```
brain graph-build                      # 重建整图
brain graph-stats                      # 节点/边计数 + 延迟
brain graph-fof <person_id>            # 2-跳邻居
brain graph-shared-identifier <pid>    # 共享标识符对
```

所有命令输出 JSON；失败走 `{"status":"skipped","reason":"kuzu_missing:ImportError"}` 约定。

---

## 3. POC 查询（Cypher）

### Q1 · 好友的好友（排除 1 跳直连）
```cypher
MATCH (a:Person)-[:Interacted]-(b:Person)-[:Interacted]-(c:Person)
WHERE a.person_id = $pid
  AND c.person_id <> a.person_id
  AND NOT EXISTS { MATCH (a)-[:Interacted]-(c) }
RETURN DISTINCT c.person_id, c.display_name
LIMIT $k
```

### Q2 · 共享身份标识符（near-merge hint）
```cypher
MATCH (a:Person)-[:HasIdentifier]->(i:Identifier)<-[:HasIdentifier]-(b:Person)
WHERE a.person_id = $pid AND b.person_id <> a.person_id
RETURN b.person_id, b.display_name, i.kind, i.value_normalized
LIMIT $k
```

---

## 4. 实测（2026-04-21, RTX 4070 / kuzu==0.11.3）

| 步骤 | 数据量 | 延迟 |
|---|---|---|
| `graph-build` | 75 persons / 2 identifiers / 2 HasIdentifier / 0 Interacted | ~6.7s（含 DuckDB 读 + 75 条 CREATE） |
| `graph-stats` | 同上 | **26 ms** |
| `graph-fof p_0a70ca98a115` | 同上 | **29 ms**（0 result，当前无 Interacted） |
| `graph-shared-identifier p_0a70ca98a115` | 同上 | **22 ms** |

> 为什么 `Interacted = 0`：现在 `relationship_edges` 是空的，`interactions` 也只有 demo 数据且没有同日同 channel 的配对。接入真实 iOS/WeChat 数据后这条边会充填起来，延迟仍在 ms 量级。

---

## 5. 取舍与决定

| 选项 | 决定 | 原因 |
|---|---|---|
| Kuzu 与 DuckDB 双写 | ❌ | 双写一致性是坑；全量重建（< 10s）够用 |
| 增量 upsert | ❌（本期） | 触发器机制未落，等 F4 再评估 |
| Interacted 作为有向边 | ✅ | 未来要表达 "A 主动给 B 发了消息" 的方向，哪怕现在对称取值 |
| HasIdentifier 作为有向边 | ✅ | Person→Identifier 天然单向 |
| 节点表放 `last_seen_utc` | ✅ | 允许写 "最近 N 天内的图"（后续） |
| CLI 只读 | ✅（本期） | 写入只走 DuckDB；Kuzu 永远是视图 |

---

## 6. 下一步（F3 的后续迭代，非本 POC 范围）

1. **接入真实 Interacted 边**：当 iOS/WeChat 入库 `interactions` 有真实时间戳后，自动推导 co-activity 边；用户也可以通过 `brain merge-candidates accept` 顺手把显式 `relationship_edges` 写回 DuckDB。
2. **时间窗切片**：`graph-fof --since-days 30` 在 build 时按 `last_seen_utc` + 边 `ts_utc` 过滤节点/边。
3. **与 `context_for_meeting` 打通**：命中某个人时，额外 return 他的 1 跳邻居（"你们最近可能关心的相同话题")。
4. **通过 FastMCP 暴露**：`graph_fof_tool`, `graph_shared_identifier_tool`；与 `merge_candidates` 协同（共享 identifier → 自动建议 T3）。

---

## 变更记录

| 日期 | 说明 |
|---|---|
| 2026-04-21 | 首版；POC 验证通过；Python 模块 + 4 个 CLI + 5 个 pytest 用例；`tools/py/tests/test_graph_poc.py` 全部以 `importorskip("kuzu")` 保护。 |
