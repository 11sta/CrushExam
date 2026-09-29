# v1.7 学习与评价契约

面向宿主教练和开发者。普通学生仍通过自然语言使用，不需要记命令。以下命令在技能根目录运行，已知工作区时始终在子命令前传 `-w`。占位符不能当真实题号/评价依据提交。

## 1. 主观题：先冻结完整要求，后提交和判分

```bash
python coach.py -w <工作区> rubric draft <qid> --out <内部草案.json>
# 教练在看到学生原答之前，对照完整题目和参考核对草案：
# 逐项定义id/label/reference_quote，不带status；coverage_confirmed改为true。
python coach.py -w <工作区> rubric freeze <qid> --file <内部草案.json>
python coach.py -w <工作区> quiz --qid <qid>
python coach.py -w <工作区> submit <qid> "学生逐字原答"
python coach.py -w <工作区> rubric ratings <qid> --out <内部评分记录.json>
# 只填写每项status；met/partial须用student_quote引用首次原答。
python coach.py -w <工作区> grade <qid> --rubric <内部评分记录.json>
```

`draft` 包含真实题号、题干版本、答案版本、完整题目、参考来源和初始分段。`freeze` 要求所有参考文字被要点引用覆盖，避免只剩判空却漏判满和用途；覆盖校验忽略常规空白与标点，保留运算符。分段不是学科语义识别。教练必须核对题目是否还包含参考未回答的问项；资料不完整就保持未核验，不能点确认后假称有完整标准答案。

以下为评分记录形状，实际文件由 `rubric ratings` 生成：

```json
{
  "contract_id": "工具返回的冻结契约哈希",
  "attempt_id": "本次作答编号",
  "source": {"file": "真实参考文件", "page": 1},
  "criteria": [
    {"id": "r1", "label": "冻结时的要求名称", "reference_quote": "冻结时的参考片段",
     "status": "met", "student_quote": "首次原答里的实际片段"},
    {"id": "r2", "label": "冻结时的另一要求", "reference_quote": "冻结时的另一片段",
     "status": "missing"}
  ]
}
```

判定：全部必需要点完成且完整契约已预先冻结，才可判整题正确。明确某项 partial/missing 可以确定未全对，并保留局部进步；未评项为 unassessed，不宣称学生没答。全部已评项为 met、但有其他漏评或不确定项时，退出码3，原答保留等待核对。修正评分记录补齐漏评后，可以针对同一已冻结 attempt 再核对；首次有效判分后不能覆盖。

旧未冻结格式仍可保留明确的局部错误，不允许作为整题正确。已经看到/提交原答才创建要求不算盲评：保留旧答，明确暂缓；只将新契约用于下一次呈题。不要为通过门禁改写第一次答案。内部契约和评分模板含参考答案，不给学生、不写进未提交工作台。

## 2. 带做：回应与评价分开

```text
补讲 → 原题带做 → awaiting_step
     → task note → step_check
     → task assess met → independent
     → task assess partial/incorrect/uncertain → remediation → 更小步骤
```

```bash
python coach.py -w <工作区> task note --note "学生刚才补出的步骤"
python coach.py -w <工作区> task assess --step-id <工具返回id> --verdict met \
  --quote "刚才原话的实际片段" --reference-quote "原参考片段" --note "这一步为何符合参考"
```

状态 met 是宿主的语义评价，不是程序对自然语言的自动证明；partial/incorrect/uncertain 不进入独立测试。连续 next、quiz 或 note 不能代替评价；三轮仍未确认收束待巩固。`task skip-check --note "学生明确暂缓/直接挑战的原因"` 提供出口，不制造通过；`task finish --status needs_work` 允许结束当天。

## 3. 正确选项与方法核对分离

带解释的原答、低置信度正确选项会保留 right 和原始选项信用，同时记录方法 pending。程序只识别“需要核对解释”，不自动判断长文本理由真假。无理由的高置信度正确也只说明该题正确，不能报告方法全面掌握。

```bash
python coach.py -w <工作区> verify-reason <qid> --attempt <原作答id> \
  --verdict met --quote "首次原答中的解释片段" \
  --reference-quote "本题参考中的真实解释" --note "逐步核对说明"
```

verdict 可为 met/incorrect/uncertain。只有原答有实际理由、参考有可用解释时才能核对。参考仅有B或学生原答仅B，不能用B证明方法；可在补讲后用另一道未见原题验证。核对可以发生在反馈后，但只能评价提交前已经冻结的文字，绝不能用反馈后补出的解释替换原话。追加核对事件与初次评分分别保留。

## 4. 时间、熟悉性与迁移是不同维度

- `evidence_level` 保留原有键用于兼容；当前标签不再泛称“强”。
- `same_item_retest` 表示不同本地日期的同题复测，不意味着真实24小时或稳定记忆；原题记忆与规则掌握无法仅靠同题区分。
- `novelty` 为 first_unseen/previously_seen；仅指当前工作区可观察记录，不能推断学生在外部是否见过。
- `transfer_kind` 为 parameter/representation/context/unclassified，依教练核对题目后明确声明分类；不自动把参数变化升级为情境迁移。

```bash
python coach.py -w <工作区> verify-transfer <目标qid> <基题qid> --kc <已核对知识点id> \
  --kind parameter --basis "两题规则相同，具体哪些参数发生变化" --confirmed
python coach.py -w <工作区> grade <目标qid> --transfer-from <基题qid>
```

题号和来源必须真实、目标题未有旧作答或提交前解答暴露、基题最近有有效独立成功。题干/答案改变使关系失效。目标此前跨日看过解答、基题最近失败或方法仍待核验，都不升级异题证据。普通判分仍有出口，不必为了迁移标签卡住学习。

## 5. 汇总、恢复与升级

文字报告和HTML均调用 evidence.summarize：任一最近错误或错误理由优先为gap；方法未核验保留待核验；未测不是零分；同题隔日证据不等于模块普遍能力。高历史证据和当前缺口分开，任务结束不意味着所有知识点掌握。

延续主状态v7，新增learning_contract_version=2。首次写入新版前备份study_state.v7.before-v1.7.0.json；旧手工评分要求覆盖未知标legacy_unverified，不改写旧得分。旧迁移类别未知标unclassified，不猜参数还是情境。旧已结束任务是历史记录，新报告不把它当现行的掌握保证。

输入契约、作答和步骤记录都可在attempts与tasks中追溯。新的等待状态有明确暂缓、结束与恢复出口。不要运行两个不同版本并发写同一工作区。无Python/写入能力时只能受限对话，不能假称这些状态已持久化。
