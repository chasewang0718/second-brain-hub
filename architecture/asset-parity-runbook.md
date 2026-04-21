# asset-migrate 对拍运行手册 (E2)

**背景**: B3/B4 把 `tools/asset/brain-asset-migrate.ps1` 和
`brain-asset-source-cleanup.ps1` 迁成了 Python。按
`asset-migration-plan.md` 的并跑约定，PS 版保留 **3 周**做对拍，
期间每跑一次真实源目录就要比一次 Python 结果。

本手册告诉你如何用 `brain asset-parity-diff` 做这件事。

---

## 前置条件

- Python 侧的 `brain asset-scan` 已可用（B3, commit `ad4c2fd`）。
- PowerShell 侧的 `tools/asset/brain-asset-migrate.ps1` 仍在仓里。
- 你准备好一个源目录（`D:\BaiduSyncdisk` 或你想扫的任何目录）。
- **Pillow 已装**。Python 靠 Pillow 读照片的 `DateTimeOriginal`；没装的话
  所有照片都会回退到 mtime，对拍会出现大量 `target_dir` 月份不一致的伪
  差异。验证一下：
  ```powershell
  python -c "from PIL import Image; print('PIL', Image.__version__)"
  ```
  装法：`pip install "pillow>=10.4.0"`（已写进 `tools/py/pyproject.toml`）。

---

## 操作步骤

### 1. 跑 PS 版（-DryRun）

```powershell
cd C:\dev-projects\second-brain-hub
pwsh tools\asset\brain-asset-migrate.ps1 `
    -Source D:\BaiduSyncdisk `
    -JobName parity-ps-2026-04-21 `
    -DryRun
```

输出路径：`D:\second-brain-assets\_migration\parity-ps-2026-04-21-manifest.tsv`

### 2. 跑 Python 版（默认就是 dry-run/scan 模式）

```powershell
python -m brain_cli.main asset-scan `
    --source D:\BaiduSyncdisk `
    --job parity-py-2026-04-21
```

输出路径：`D:\second-brain-assets\_migration\parity-py-2026-04-21-manifest.tsv`

> ⚠️ 两次扫要在**同一天同一源目录状态下**跑，避免期间文件变动
> 造成虚假差异。

### 3. 对拍

```powershell
python -m brain_cli.main asset-parity-diff `
    --a D:\second-brain-assets\_migration\parity-ps-2026-04-21-manifest.tsv `
    --b D:\second-brain-assets\_migration\parity-py-2026-04-21-manifest.tsv `
    --output D:\second-brain-assets\_migration\parity-2026-04-21.md
```

会同时输出：

- 终端：JSON 汇总（`match` / `a_count` / `b_count` /
  `common_count` / `identical_count` / `only_in_a_count` /
  `only_in_b_count` / `mismatches_count` + 每类计数）
- Markdown 报告：三张表（整体汇总 / 每类计数 / 差异明细
  前 20 条）

---

## 如何判读结果

### ✅ 对拍通过

终端里看到 `"match": true`，Markdown 头部是 **✅ 对拍通过**。

即：
- 两侧 `source_path` 集合完全相同
- 所有共同 `source_path` 的 `rule` / `action` / `target_dir`
  都一致（`target_dir` 的斜杠/反斜杠已被归一化，不算差异）

### ⚠️ 有差异 · 预期可接受的

| 差异 | 预期原因 | 处理 |
|---|---|---|
| **只在 B（Python）中** 有 `.tiff` / `.webp` 文件 | B3 显式扩充了分类表 | OK，不算问题 |
| **只在 A（PS）中** 有被 Python exclude 规则拦下来的文件 | Python 的 exclude 是 substring + startswith（PS 只 startswith）；Python 更保守 | 看 `~/.brain-exclude.txt` 第几条命中了，确认是有意排除的 |
| **同 `source_path`，`target_dir` 只差年月** | PS 读 System.Drawing 拿到 EXIF；Python 用 Pillow（或未装 Pillow 就 fallback mtime） | 影响**照片分月归档的精度**；要不要改见下 |

### ❌ 有差异 · 不应该出现的

| 差异 | 含义 | 必须停下的原因 |
|---|---|---|
| **同 `source_path`，`rule` 不同** | 两边分类规则不对齐 | 说明 `classify_file` 的扩展名表有漏洞，**B6 删除 PS 版之前必须修** |
| **同 `source_path`，`action` 不同** | 两边执行路径不对齐 | 可能造成真删时落错位置，**B6 之前必须修** |
| **大量 only_in_a**（不是 exclude 拦的） | Python 的 walker 漏扫了 | 可能是 symlink / 权限问题，查 `os.walk` 行为 |

---

## 进入 B6（删除 PS 脚本）的出口条件

`asset-migration-plan.md` 定义的退出条件：

- [ ] 至少跑 **3 次对拍**（间隔 ≥ 1 周），全部 `match: true` 或
      只有"预期可接受"的差异。
- [ ] 3 次对拍覆盖 ≥ 2 个不同源目录（避免只对拍某一种结构）。
- [ ] 每次对拍的 Markdown 报告都存档到
      `D:\second-brain-assets\_migration\parity-YYYY-MM-DD.md`。

全部满足后，再做 B5（改 `.reference` profile 的 `gasset-*`
函数调 Python CLI）和 B6（删 `tools/asset/*.ps1`）。

---

## 故障排查

### "missing_a" / "missing_b"

路径写错了。检查 `_migration/` 目录实际文件名（PS 版在文件名
里会保留 `-manifest.tsv` 后缀）。

### "`match: false` 但所有字段都相同"

大概率是 `source_path` 的大小写/斜杠差异。工具已经做了
case-insensitive + slash-normalize，如果还是匹配不上，
用 Python 打开两个 TSV 看第一列的 bytes。

### 报告文件里 source_path 里有 `|` 导致表格乱了

E2 已经处理（`|` → `\|`），如果仍然有问题直接看 JSON 输出
（`--output` 省略即可）。

---

## 变更记录

| 日期 | 说明 |
|---|---|
| 2026-04-21 | 首版；配合 E2 工具（`brain asset-parity-diff`）落地。 |
