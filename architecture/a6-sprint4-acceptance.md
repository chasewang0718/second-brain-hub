# Phase A6 · Sprint 4 Acceptance Report

**Sprint**: Relationship Tier + Cadence Alarm
**Status**: ✅ Merged 2026-04-22
**Regression**: 105/105 (S1+S2+S3+S4 combined)
**Smoke target**: production DuckDB `brain-telemetry.duckdb` @ 47.5 MB
**Pre-apply snapshot**: `20260422-201944-a6-sprint4-pre-apply.duckdb` (sha256 `43b513e7…`)

## 1. Design decisions

### 1.1 Why reuse `person_facts` + `person_insights` instead of new tables

The original roadmap hinted at a `tier_suggestions` table. We explicitly rejected it:

- **Authoritative tier** → `person_facts` with `key='relationship_tier'`. This gives us bi-temporal history **for free**: six months from now "was 田果 inner in 2026-Q1?" is just `list_facts(at='2026-03-31', key='relationship_tier')`. It also means tier transitions auto-log without any new plumbing (Sprint 1's `_current_open_fact` closure logic handles it).
- **AI suggestions** → `person_insights` with `insight_type='tier_suggestion'` + `superseded_by` chain (same pattern as `topics_30d` / `weekly_digest` from Sprint 3). We don't need schema migrations; the v5 migration from Sprint 3 already added `superseded_by`.
- **Zero new tables, zero new migrations** was the cleanest possible delivery for a "tier + alarm" sprint.

### 1.2 The single hard rule: AI never overwrites human

`suggest_tier(pid, apply_as_fact=True)` only writes to `person_facts` when `get_tier(pid) is None`. This is tested explicitly (`test_suggest_tier_does_not_overwrite_human_fact`). If a human has ever set the tier — even a month ago — AI will suggest, but never auto-apply. Only a later explicit `brain tier set` can change it.

### 1.3 Heuristic-first suggester (no LLM)

Unlike Sprint 3's topics/weekly (which genuinely benefit from LLM narrative), tier assignment is a **deterministic classification over existing metrics**. We use a conservative ladder over `interactions_30d` + `interactions_90d` + `dormancy_days`:

| Condition                                          | Suggested tier | Confidence |
| -------------------------------------------------- | -------------- | ---------- |
| `dormancy_days > 365`                              | dormant        | 0.70       |
| `i30 ≥ 20` AND `i90 ≥ 50`                          | inner          | 0.70       |
| `i30 ≥ 5` AND `i90 ≥ 15`                           | close          | 0.60       |
| `i30 ≥ 1` OR `i90 ≥ 5`                             | working        | 0.50       |
| `dormancy_days > 180`                              | dormant        | 0.50       |
| else                                               | acquaintance   | 0.40       |

This is easy to tune from a single yaml key later if needed; no prompt-engineering circus to keep LLM happy. Also: 500-person `suggest --all` takes ~7.5 min vs. potentially 2+ hours with Ollama per-person.

### 1.4 Cadence alarm is strictly additive over A5's flat-45d

Existing `brain relationship-alerts` kept its 45d flat threshold as `## Overdue Contacts (>=45d, flat baseline)`. On top we added `## Tiered Cadence Alarm` which reads tier facts + YAML `people_cadence:` and groups overdue people by tier. **People without a tier fact are invisible to the new section** — they continue to be served by the flat baseline. So the migration is backward-compatible: nothing gets quieter after deploy.

### 1.5 `dormant` tier has null cadence on purpose

Setting `dormant:` to `null` in YAML means "no alarm". Semantics: dormant is an **explicit** user decision ("I've accepted I'm not staying in touch"), so silencing alarms is the whole point. `list_overdue_by_tier` skips any tier with `cadence_target_days=None`.

### 1.6 YAML garbage tolerance

`load_cadence_config` treats:
- missing `people_cadence:` section → full defaults,
- unparseable per-tier value (e.g. `"abc"`) → keep default for that tier,
- negative/zero per-tier value → treat as `None` (no alarm).

Rationale: the daily digest must never crash over a typo in a config edit. Test `test_load_cadence_config_rejects_garbage_values` pins this.

## 2. Deliverables

### 2.1 Schema

- **No new tables / columns.** `relationship_tier` lives in existing `person_facts`; `tier_suggestion` lives in existing `person_insights`.
- Backward compat verified: v5 migration from Sprint 3 is sufficient.

### 2.2 New module: `brain_agents.relationship_tier`

Public surface:

```
ALLOWED_TIERS = ('inner','close','working','acquaintance','dormant')
TIER_FACT_KEY = 'relationship_tier'
INSIGHT_TIER_SUGGEST = 'tier_suggestion'

load_cadence_config() -> dict[str, int | None]
set_tier(pid, tier, *, note, source_kind, confidence) -> dict
get_tier(pid) -> str | None
list_tiers(*, tier=None, include_history=False) -> list[dict]
suggest_tier(pid, *, apply_as_fact=False) -> dict
suggest_tier_all(*, min_interactions_all=1, max_persons=2000, apply_as_fact=False) -> dict
list_overdue_by_tier(*, tiers=None, cadence=None) -> dict[str, list[dict]]
get_tier_suggestion(pid) -> dict | None
```

### 2.3 CLI

| Command                                          | Purpose                                                       |
| ------------------------------------------------ | ------------------------------------------------------------- |
| `brain tier set <pid> <tier> [--note X]`         | Authoritative write. Validates tier against allow-list.       |
| `brain tier get <pid>`                           | Returns current tier + latest AI suggestion                   |
| `brain tier list [--tier X] [--history]`         | Roster, optionally filtered, optionally with history          |
| `brain tier suggest --person-id X [--apply]`     | Suggest one; `--apply` writes fact iff no human fact exists   |
| `brain tier suggest --all [--apply] [--max N]`   | Bulk heuristic scan                                           |
| `brain tier overdue [--tier X]`                  | List people whose dormancy > cadence target, grouped by tier  |

### 2.4 `people_render` enhancements

- `frontmatter.relationship_tier` added (string) when a tier fact exists
- `frontmatter.cadence_target_days` added (int) when cadence is non-null
- New `## Relationship Tier` section after Metrics, with:
  - `- **current**: `<tier>``
  - `- **cadence target**: N days` (or `_no alarm_` for `dormant`)
  - `- **status**: ✅ within cadence (<dormancy>/<target>d)` | `⚠️ <N>d overdue` | `— (no dormancy)` | `— (no alarm)`
  - `- **AI suggestion**: `<tier>` (confidence X) — <reason>` when a suggestion row exists
- Section is silently omitted if neither tier fact nor suggestion row exists → backward compatible.

### 2.5 `digest.generate_relationship_alerts` upgrade

New structure:

```markdown
# Relationship Alerts · <date>

## Tiered Cadence Alarm
### `inner (cadence 14d)` · <N> overdue
| name | person_id | dormancy | over target | last seen |
...

### `close (cadence 30d)` · <N> overdue
...

## Overdue Contacts (>=45d, flat baseline)
- <name>: <gap> days
...

## Suggested Action
- Pick top 3 people and send a quick catch-up message.
```

Return payload now includes `tiered_overdue` + `tiered_by_tier`.

### 2.6 E2 scheduled task

`tools/housekeeping/brain-e2-task.ps1 weekly-review` now chains **four** Phase A6 steps, each isolated by try/continue with `hub-alert` fallback:

1. `brain person-metrics recompute --all` (S3)
2. `brain person-digest rebuild --all --weekly-days 7 --topics-days 30` (S3)
3. `brain tier suggest --all` (S4, no `--apply`)
4. (pre-existing) people-eval trend snapshot

A failure in any one step logs a hub-alert but does not abort the others.

### 2.7 Tests (25 new)

- `test_relationship_tier.py` — 22 new cases:
  - round-trip set/get; rejects unknown tier; rejects empty pid
  - `get_tier` returns None when unset
  - bi-temporal history: second `set_tier` closes prior fact
  - `list_tiers(tier=...)` filter
  - `load_cadence_config` defaults / overrides / garbage tolerance (3 cases)
  - heuristic ladder covers inner/close/dormant
  - `suggest_tier` chains `superseded_by`
  - AI never overwrites human; applies when fresh
  - `suggest_tier_all` skips people without metrics
  - overdue flags inner > 14d with correct `days_overdue`
  - overdue within threshold returns nothing
  - overdue excludes people without tier fact (legacy-flat path keeps them)
  - overdue ignores dormant tier (null cadence)
  - overdue sorted by `days_overdue` DESC
  - `tiers=[...]` filter honored
  - `get_tier_suggestion` roundtrip + None case
- `test_people_render.py` — 3 new cases:
  - frontmatter + `## Relationship Tier` section with overdue chip
  - within-cadence shows ✅ chip
  - section omitted when no tier data
- `test_digest.py` — 3 new cases:
  - tiered section renders inner overdue with correct `+Nd` over target
  - tiered empty when nobody exceeds
  - back-compat: no tier data → "none" + flat baseline intact

### 2.8 Config

`config/thresholds.yaml` gained `people_cadence:` block with inline documentation about tier semantics and tuning guidance.

## 3. Smoke test

| Step                                                                 | Result                                                                                                                                                |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `brain ingest-backup-now --label a6-sprint4-pre-apply`               | 47.5 MB snapshot, sha256 `43b513e7…`                                                                                                                  |
| `brain tier suggest --all --max-persons 500`                         | 500 people / 7.5 min, distribution: inner=10 / close=22 / working=311 / acquaintance=150 / dormant=7 — sensible long-tail                             |
| 田果 (`p_8168e6185835`) metrics                                      | i_all=424 / i_30d=147 / i_90d=274 / dormancy=2d                                                                                                       |
| 田果 AI suggestion                                                   | `inner` confidence 0.70 — matches manual tier                                                                                                         |
| 田果 human fact (pre-existing)                                       | `inner`, source_kind=manual                                                                                                                           |
| `brain tier overdue --tier inner`                                    | 0 overdue (田果 within 14d cadence) ✓                                                                                                                 |
| Demo: `brain tier set p_5dfc9fd19a48 close` (陈浩祈, dormancy=103d)  | OK; closed_id=null, inserted_id=7                                                                                                                     |
| `brain tier overdue`                                                 | close bucket: 1 overdue, `days_overdue: 73` (103 − 30) ✓                                                                                              |
| `brain relationship-alerts`                                          | `tiered_overdue: 1`, `tiered_by_tier.close: 1`; md file has `## Tiered Cadence Alarm → close (cadence 30d) → 1 overdue` table row for 陈浩祈 ✓        |
| `brain people-render --person-id p_8168e6185835` (田果)              | frontmatter has `relationship_tier: inner` / `cadence_target_days: 14`; body has `## Relationship Tier` with `✅ within cadence (2/14d)` + AI suggestion ✓ |
| `brain people-render --person-id p_5dfc9fd19a48` (陈浩祈 demo)       | `## Relationship Tier` has `⚠️ 73d overdue` chip + AI suggestion `acquaintance` (human `close` wins) ✓                                                 |
| Full regression (S1+S2+S3+S4)                                        | 105/105 passed                                                                                                                                        |

## 4. Known limitations / follow-ups

1. **`suggest --all` scaling**: 500 people / 7.5 min is fine today; at 10k+ people we'd need to batch the `_insert_suggestion_and_supersede` transaction. Not blocking.
2. **AI suggestion is heuristic-only**: intentional — tier is classification over existing metrics, no LLM needed. If future business rules (e.g. "promote to inner after 3 consecutive weeks of ≥5 interactions") require narrative grounding, we'd add an LLM pass then. Not needed today.
3. **No demotion rule**: heuristic can upgrade a dormant person to working if they reappear, but doesn't auto-demote active inner people. Intentional — dropping someone from inner should be a deliberate human act.
4. **`brain tier unset`**: not implemented. If a user wants to remove a tier, they should `set` to `dormant` (semantically closest to "stop nagging me"). Adding explicit invalidation would need `person_facts.invalidate_fact` exposure in CLI; deferred.
5. **`weekly-review` run time**: now four sub-steps in series. Worth considering parallelization at ~10k people.

## 5. Phase A6 overall status → ✅

All four Sprints done. The exit checklist in `ROADMAP.md → Phase A6 整体退出标志` is 3/4 checked; the remaining item ("连续 7 天 BrainWeeklyReview + BrainRelationshipAlerts 无失败") is a 7-day observational window that starts now. No code work pending for A6.

Phase A6 is marked ✅ with a note that production 7-day stability is tracked separately.
