# v1.7.0 命令与兼容说明

新增评分、带做、理由和异题类别的最新契约见 [learning-contracts.md](learning-contracts.md)。该文档优先于下面保留的 v1.6 历史说明。

**行为变更**：`task note` 只保存实际回应，必须 `task assess` 才推进；`answer ... right --note ...` 不能绕过完整评分契约；`grade --rubric` 必须绑定冻结契约才可形成主观题整题正确。`verify-transfer --kind` 指定类别。旧工作区不必重建；恢复命令不变。

---

# 工作流、命令与数据契约 · 1.6.0

所有命令格式为 `python coach.py -w "<工作区>" <子命令>`。`qid` 和 `attempt_id` 必须来自工具输出，不自行猜测。学生只需用自然语言作答。

## 常用操作

| 意图 | 子命令 | 说明 |
|---|---|---|
| 查看进度 | `status [--detail]` | 显示当前任务和待处理原因 |
| 恢复未答题 | `resume` 或 `quiz` | 重显同一attempt，不新增次数 |
| 初次摸底 | `quiz --stratified -n 4` | 默认4，最多8，每次一题 |
| 再次摸底 | `diagnose --restart [-n 4]` | 保存旧批次；活动作答需先处理 |
| 保存原答 | `submit <qid> "原答" [--hinted] [--attempt ID]` | 原答冻结；重复同答幂等 |
| 格式澄清 | `clarify <qid> "明确选项"` | 只适用不可解析状态，原答不覆盖 |
| 不会／跳过 | `skip [qid] --reason unable` | 不记错误分数，保留原因 |
| 缺条件／缺图 | `skip [qid] --reason material_missing --note "缺少内容"` | 挂起该题，不锁全流程 |
| 暂缓 | `defer [qid] --note "原因"` | 当天不再自动安排该题 |
| 看分析 | `gaps [--html] [--detail]` / `evidence` | 只有摸底批次结束后进入分析出口 |
| 安排任务 | `plan [--minutes N] [--date YYYY-MM-DD] [--detail]` | 不会无故替换当前未完成队列 |
| 不做诊断先学 | `plan --skip-diagnosis` | 明确跳过，旧原答仍保留 |
| 下一批任务 | `plan --rebuild` | 当前作答须结束；旧任务归档 |
| 下一教学步 | `next [--repeat|--back]` | 按保存任务补讲、带做、独立 |
| 看当前任务 | `task [show] [--json]` | 包括题号、阶段、完成条件 |
| 保留带做步骤 | `task note --note "学生实际补出的步骤"` | 受助记录，不计独立成功 |
| 收束任务 | `task finish --status needs_work --note "仍缺什么"` | 还支持deferred/material_blocked/completed_unverified；不允许伪造passed |
| 指定原题 | `quiz --qid <qid>` | 未结束时只能重显当前题 |
| 跨章抽题 | `quiz --all` | 仍遵守确认范围；课外显式加 `--outside-scope` |
| 看参考 | `check <qid> [--attempt ID]` | `--force`不绕过先答后查 |
| 客观判分 | `grade <qid> [--attempt ID]` | 使用冻结原答，不接受另一个答案覆盖 |
| 主观核对 | `grade <qid> --rubric "JSON" [--error-type expression]` | 有来源的分点评价 |
| 简化主观核对 | `answer <qid> right\|wrong --note "具体依据"` | 保留对照依据；无答案不判分 |
| 新作答复测 | `quiz --qid <qid>` → `submit` → `review <qid> --result right\|wrong` | 仍核验原答；不能沿用旧记录 |
| 跳章 | `goto N [--restart]` | 同时切任务；原当前任务暂缓，原答保留 |
| 结束章节 | `done [--chapter N] [--unverified]` | 阅读/独立证据/暂缓分开，不保证全章掌握 |
| 暂停／结束 | `session pause` / `session finish` | 原任务和未答题不丢失 |
| 恢复／总结 | `session resume` / `session summary` | 同一会话恢复；下一批用plan --rebuild |
| 异常阶段修复 | `session recover` | 保存历史，不默默清空状态 |
| 查作答原始记录 | `attempts [--qid ID] [--json]` | 不需要直接改JSON |
| 单题工作台 | `workbench [--out 路径]` | 先呈题，导出不等于提交成功 |
| 导入离线原答 | `import-answer "<JSON>"` | 检查考试、attempt、qid、版本和token |

其余原功能保留：`blueprint`、`ask`、`chapter`、`figures`、`figure`、`export`、`note`、`mistakes`、`cheatsheet`、`score`、`usage`、`exams`、`switch`、`doctor`。参数以 `<命令> -h` 为准。

## 主观题评分点JSON

以下只是格式示例。必须将来源、引用和评价替换为学生真实题目和实际作答；不要把示例当成真实评分。

```json
{
  "source": {"file": "hw2.txt", "page": 1},
  "criteria": [
    {"id": "empty", "label": "空队列条件", "status": "met", "reference_quote": "空时front=rear"},
    {"id": "full", "label": "满队列条件", "status": "missing", "reference_quote": "满时(rear+1)%M=front"},
    {"id": "reason", "label": "保留空位的原因", "status": "missing", "reference_quote": "保留空位用于区分空与满"}
  ],
  "note": "学生只写出了空条件，另两个要点缺失。"
}
```

`source.file/page` 必须与本题参考答案来源一致，`reference_quote` 必须在该参考原文中真实存在。状态仅限 `met/partial/missing/uncertain`。全部met才是该分项方案下整体正确；有uncertain则暂不形成确定结论。每项不接受 `score/points/max_points`，避免把教练拆分的要点误标为教师分值。引用存在性可以校验，但评分点是否全面、学生是否真正达到要点仍需宿主审阅。

错误类别：`concept`概念、`method`方法选择、`procedure`过程、`calculation`计算、`reading`读题、`expression`表达、`unknown`待定位。不推断心理或智力，不把缺材料归因于能力。

## 恢复与数据不变量

`study_state.json` 为权威数据；`progress.md/notebook.md/session_summary.md` 是派生视图。v7用 `attempts` 保存不可变原答，`tasks`保存可执行题号和阶段。`pending/open_quiz/last_plan`为兼容视图，不要手改它们推动流程。

阶段和任务状态分别控制。活动作答没有结束时不能静默切题、重排计划或跳章；重显原题则完全允许。整轮诊断后统一分析，查看报告的命令不能绕过阶段门禁。任一材料/格式阻塞都可局部退出，不要求学生所有题全对才能结束本次。

代码内同题每日上限3次、连续错误上限3次；复测默认1/3/7日。每天是宿主机器的本地日，部署时对齐时区；当前没有全套per-exam时区时钟。独立性是可观察提示事件和学生自报的证据，不是反作弊认证。修改JSON或跳过脚本不属于保护边界。

工作区锁和考试注册表锁都为有界OS锁。命令崩溃由OS释放；不要按文件时间随意删除锁文件。状态使用唯一临时文件+fsync+原子替换；多个派生文件并非分布式事务，异常后以权威状态为准重新输出视图。

## 迁移与回滚

升级前备份整个工作区。v6第一次写入v7前自动留一个原状态副本，旧不明确揭晓时间保守处理。旧v5无考试归属的记录保留在隔离区，不自动挂到新考试。正常重扫会比较题目与答案版本，变化题不沿用旧掌握结论。

回滚时使用备份目录的完整工作区副本和相应旧代码，不让旧代码直接读写v7状态。不通过修改版本数字“降级”。本版不自动删除用户资料、备份、原答或历史考试。
