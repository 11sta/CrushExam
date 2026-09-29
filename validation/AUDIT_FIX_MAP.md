# v1.7.0 · 复现问题与回归映射

基于上一轮v1.6.0模拟学习压力测试P01—P13，采用新的反例/正例回归。不是重新运行上一轮540条规则学生测评，也不报告真人效应量。下表的测试位于 `tests/test_learning_contracts_v170.py`。

| 原编号 | 本次改动或保留 | 对应测试后缀/检索词 |
|---|---|---|
| P01 选项正确掩盖理由 | 原始选项信用与方法核验分离；叙述理由或低置信度触发method_check | P01_correct_option; low_confidence; reason_review; valid_original_reason |
| P02 零回应推进 | awaiting_step、step_check；连续next/quiz不越过 | P02_no_step; guided_success |
| P03 不理解仍推进 | uncertain/partial/incorrect进入更小步骤；三轮未确认待巩固 | P03_confusion; three_failed; explicit_skip; waiting_step |
| P04 一问代替整题 | 前置冻结完整要求；原答/题目/答案版本绑定；漏评unassessed；明确局部不足保留 | P04_one_of_three; rubric_; freeform_manual_right; cannot_rename |
| P05 模块强遮蔽错题 | evidence.summarize统一文字/矩阵；最新错误优先，方法待核验独立 | P05_any_unrepaired |
| P06 延迟后失败 | 保留当前证据降级，历史不删除 | P06_later_failure |
| P07 同题记忆泛化 | 同题隔日与未见题分别记录；不生成模块strong结论 | P07_same_item |
| P08 迁移类型混同 | parameter/representation/context/unclassified显式子类 | P08_parameter; representation_and_context |
| P09 未确认迁移 | 继续禁止；普通判分有出口 | P09_unconfirmed; target_exposed; base_last_wrong |
| P10 提示后误算独立 | 明确跳过也不洗掉受助事实 | P10_guided_exposure |
| P11 原答覆盖 | 保留原答不可覆盖；后补解释不能冒充原始理由 | P11_no_grade_overwrite; new_answer_cannot |
| P12 中断恢复 | 保留同一attempt、冻结契约和未结束步骤 | P12_resume; resume_old_guided |
| P13 分项进步 | 完成1项到2项仍保留局部进步，不冒称整题正确 | P13_partial_step |

附加回归：真实原答片段及参考片段核验、步骤id绑定、评分记录attempt绑定、来源变更、题库/契约不向未提交页面泄漏、v7升级备份、未来schema拒绝、旧方法/手工评分保守迁移。新增42项，见完整日志。

`validation/learning-process-commands.json` 是28次独立进程命令实录，直接复验P04失败防线与完整评分正向路径、P02/P03等待和P01方法核对；其他情形由真实临时工作区的CLI/模块回归验证，不把它们都称为独立进程实测。

## 仍需人工或真实环境核实

- 来源覆盖是结构/文字覆盖约束，不是学科语义完备性的自动证明。宿主确认前必须对照题干所有问项与参考，参考不完整时不要强行冻结。
- 选项信用不直接证明方法熟练；没有原始解释时不能凭后来补充解释改写首次独立表现。
- 参数/表示/情境分类由宿主核对，不是算法自动识别的因果迁移证据。未见仅指工作区可观测记录。
- 延迟规则是本地日期变化，测试用受控记录，不等于真实等待24/72小时或真人保持率。
