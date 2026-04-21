# D3 · 联系人 CLI 最小抽样 — 2026-04-21

> 目的：记录 **`brain who` / `brain overdue`** 对当前内容仓（含 demo + WeChat 指针）的可重复输出，作为 **D3 初样**，供验收清单引用。  
> 说明：**非**「真实联系人全量评测」；WeChat `wxid_*` 在 `who` 上若未配置显示名可能返回空列表，属预期对比项。

## 命令与结果摘要

### `brain overdue`（默认 `--days` 使用 Typer 默认 30）

输出示例（节选）：

```json
[
  {
    "id": "p_alice",
    "name": "Alice Zhang",
    "last_seen_utc": "2026-03-12 14:36:13.569668",
    "days_since_contact": 40
  }
]
```

- **结论**：demo 联系人 **Alice Zhang** 出现在逾期列表（40 天），与 digest 中「Overdue」叙事一致。

### `brain who "Alice Zhang"`

返回 1 条 person 记录（`p_alice`），含 `aliases_json` / `tags_json` / `last_seen_utc`。

### `brain who wxid_0jvw4ueqlvz322`

当前返回 **`[]`**（空数组）。

- **解读**：demo 种子与 **WeChat 档案卡** 的解析键可能不一致；**Stage 2** 将「真实姓名 / 别名」写入 `_aliases.md` 与卡内字段后，应复测并记入本文件 **§ 回归表**。

## 后续

- 替换 5–10 个 **真实联系人** 后：对每个实体跑 `who` / `context-for-meeting`，记录 **漏匹配 / 别名错误** 条数。
