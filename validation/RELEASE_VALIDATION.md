# CrushExam v1.7.0 发布验证

验证记录日期：2026-09-29。基线是用户上一轮收到的v1.6.0完整包。本轮修改源码、增加回归、执行独立进程学习旅程和浏览器检查；无真人受试者、无模型API调用、无TeleAgent线上联调。

## 结果与证据

| 层次 | 实际结果 | 对应文件 |
|---|---|---|
| 修改前v1.6.0基线 | 90/90通过 | baseline-v160-tests.log |
| 本次完整回归 | 132/132通过（90个原测试函数+42个新增） | unit-tests.log |
| 新增学习契约回归 | 42/42通过 | learning-tests.log |
| 完整独立进程旅程 | 32条命令通过，最终session_complete | synthetic-journey.json / .md / -summary.json |
| 重点反例与正向流程 | 28条独立进程命令、5项断言通过 | learning-process-commands/checks/summary.json |
| Chromium桌面/移动检查 | 16项通过；无JS错误、无远端请求 | browser-results.json / screenshots/ |

**原90个测试函数中，1个教学阶段测试有意加强/更新契约**：`TeachingAndMigrationTests.test_teach_guide_independent_feedback_and_session_finish`增加真实步骤记录及评价后才进入独立阶段，不再期待连续next自动通过。其余89个原测试函数未修改。不能称原测试全部原封不动。新42项见AUDIT_FIX_MAP.md。

发布候选包重新解压后，完整回归实际 **132/132通过（52.295秒）**，日志见 `unpacked-tests.log`；两组独立进程旅程也在解压版本上再次执行通过。最终校验记录在 `results.json`，文件字节清单在根目录MANIFEST.sha256。验证记录加入最终包后，已比较47个非验证文件：运行时代码、模板、Skill指令、说明和测试与候选解压实际验证的文件逐字节一致。只有验证记录及MANIFEST被更新。

## 浏览器边界

实际 Chromium 144.0.7559.96，桌面1365×950、窄屏390×844。容器策略阻断file/HTTP导航（ERR_BLOCKED_BY_ADMINISTRATOR），最终用Playwright `set_content`加载同一生成HTML测试选项输入、冻结原答、重复导出、后端幂等导入/判分与反馈界面；已检查[hidden]元素实际隐藏。该模式下浏览器明确提示不能持久保存，验证了这一降级提示。

**没有验证**原生文件打开、HTTP实际访问、刷新后的localStorage持久化、TeleAgent内嵌页和移动客户端文件回传。不能将本记录解读为这些路径通过。截图为合成题目与合成回答，不是学生个人资料。

## 复现

在技能根目录运行（输出目录必须不存在或为空）：

```bash
python -m unittest discover -s tests -v
python scripts/validate_release.py --out /tmp/crushexam-journey-v170
python scripts/validate_learning_release.py --out /tmp/crushexam-contracts-v170
# 可选浏览器验证；需本机已有Playwright与Chromium，不属于技能强制依赖
python scripts/validate_workbench.py --out /tmp/crushexam-browser-v170 --transport set-content --chromium /usr/bin/chromium
```

常规浏览器允许URL导航时可使用`--transport static-http`，包含重载持久化检查；本轮不宣称这条分支已经通过。核心回归使用隔离临时工作区和考试注册表，不修改真实学习进度。各脚本在包内自带合成资料构造，日志中绝对测试路径只是本次记录，不是用户的安装要求。

## 平台与局限

实际Python 3.13.5 / Linux x86_64。核心标准库运行，不新增网络或模型依赖。没有Windows/macOS实机、其他Python版本、真实扫描件和真实考试课程的全量验收。

这些测试证明所列反例和流程在受控夹具下满足契约，不证明宿主模型会正确识别知识点、评分点语义或每个错误原因。完整评分要求需教练先核对资料；步骤和理由评价仍是带引用的人工/宿主语义判断。用户可跳过或结束但不因此计掌握。未重新测量上一轮规则学生的后测分数，更未测试真人提分、真实24/72小时保持和普遍迁移能力。

## 升级

替换Skill代码，保留材料和工作区，不使用--fresh。v1.6状态首次新版本保存前自动备份到`.backups/study_state.v7.before-v1.7.0.json`；仍建议先自行备份整个工作区。旧得分和原答保留，旧覆盖/理由信息缺失标待核验，旧迁移类别不猜测。不要让两个版本并发写同一工作区，回退需恢复整份旧备份。
