# evals/

**金标数据集 + prompt 回归测试**.

每次改 prompt / config / 换模型 -> 跑 eval -> 对比分数 -> 决定是否合并.

## 结构

```
pdf-classify/
  golden-set/           手工标注的 "正确答案" 数据集
    001-invoice.json      {source_pdf, expected_output}
    ...
  run-eval.ps1          跑 worker -> 比对 -> 输出分数
  results/              历次跑分结果 (.gitignore 或保留?)
  README.md

inbox-route/            (未来)
capsd-action/           (未来)
```

## 指标

- **Accuracy**: 类别是否正确
- **Path match**: Tier A/B 目录是否正确
- **Confidence correlation**: 高置信时准确率是否真的高 (calibration)
- **Tag overlap**: Jaccard(predicted_tags, expected_tags)
- **Cost**: 平均每份花的 token + 时间

## 使用

```powershell
# 跑当前配置
.\evals\pdf-classify\run-eval.ps1

# 对比两个 config 版本
.\evals\pdf-classify\run-eval.ps1 -CompareCommit HEAD~1
```
