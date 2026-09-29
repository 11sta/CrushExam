---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '85940041-a441-40d1-ad2f-54316284df22'
  PropagateID: '85940041-a441-40d1-ad2f-54316284df22'
  ReservedCode1: '7e77183e-c074-4a67-9963-1f58ff3eba86'
  ReservedCode2: '7e77183e-c074-4a67-9963-1f58ff3eba86'
---

# CrushExam 1.7.0 ·

**基于学生真实课程资料的可恢复备考教练：先诊断，再按具体解题步骤训练，用真实作答反馈，原答不可覆盖。**

CrushExam 是一个面向期末、等级、考证等考试的 TeleAgent Skill。它只使用学生自己的课件、作业、试卷和教材——不用 AI 出题、不猜教师重点、不编造通过概率。核心脚本离线运行（Python 标准库），不依赖模型 API 或在线服务。

---

## 核心理念

| 原则 | 含义 |
|---|---|
| **循证（Evidence-based）** | 只用资料里的题；每个结论标注出处和样本数；题库数量、印刷分值不冒充卷面权重 |
| **先答后查（Answer-first）** | 学生必须先提交原答才能看参考解析，代码级门禁（exit 5），不是行为约定 |
| **原答不可覆盖** | `submit` 后原话冻结；`attempt_id` 标识每次尝试；重复提交幂等；重做必须重新呈题建立新 attempt |
| **诚实边界** | 一次答对不称掌握；未测不是零分；提交数≠判分数；工具调用数≠积分；自报成绩必须标注 |
| **可中断恢复** | 阶段、任务、未答题持久化；`session resume` 恢复原状，不重新初始化 |

## 功能总览

**诊断与分析**
- `setup` 提取资料 → 章节/题目/配图，输出提取状态透明报告（哪些成功、哪些是扫描件、哪些被跳过）
- `quiz --stratified` 分层摸底：按确认范围、题型/章节覆盖、未测优先抽题，一次一题，整轮结束前不揭晓
- `gaps` 知识点能力表 + `--html` 离线热图（知识模块×题型、六模块概览、来源表）；灰色=未测，不伪造百分比
- `blueprint` 考试蓝图：KC 词典（知识点+关键词）自动映射题目，支持分值结构导入与手动修正

**教学闭环（补讲 → 带做 → 独立 → 反馈）**
- `next` 按持久化任务逐步教学：概念题讲含义与适用条件、程序题展示中间状态、计算题讲公式选择
- 带做：教练示范必要步骤 → 学生补关键步骤（`task note` 存原话）→ 教练核对（`task assess`）→ 只有 `met` 才进独立
- 独立：同任务中另一道**未被带做**的原题，只给题不提示
- 反馈：先存原答再 `grade`；只给结果、首个关键错误、下一动作

**判分与证据**
- 客观题自动判分（对/错/√/×/T/F、单字母、ABCD 集合归一化）
- 主观题评分契约：看到学生答案**之前**用 `rubric draft/freeze` 冻结完整要点清单，`rubric ratings` 逐项核对（met/partial/missing/uncertain），漏评标 `unassessed` 不判全对
- 选项与方法分离：选对但理由错误 → 选项得分保留、方法进入 `method_check`
- 跨日复测与迁移：同题隔日、未见原题、参数/表示/情境变化分别留痕（`verify-transfer --kind`），不互相冒充

**工程可靠性**
- 阶段状态机（diagnosing → analysis → planning → studying → session_complete）+ 退出码语义（0/2/3/4/5/6）
- 有界 OS 工作区锁（Windows msvcrt / Linux fcntl）、原子写入、v6→v7 状态自动备份迁移
- 资料防注入：`<<<MATERIAL>>>` 包裹的教材文本不被当作指令执行
- 多考试完全隔离：一考试一工作区，互不共享题目、成绩、历史

**辅助能力**
- `workbench` 离线单题工作台（HTML）：学生本地作答、冻结、导出 JSON，`import-answer` 回后端判分（未提交页面不含参考答案）
- `usage` 用量报告：按天/会话统计工具调用，渲染文件数不冒充视觉调用估算
- `cheatsheet` 小抄、`score` 自报成绩（始终标注）、`doctor` 环境自检

## 部署到 TeleAgent

CrushExam 是一个 TeleAgent 技能（Skill），部署后 TeleAgent 会在你说"备考/复习/刷题"等场景自动激活它。有两种安装方式：

### 方式一：通过技能市场安装（推荐普通用户）

如果你拿到的 ZIP 来自作者或技能市场：

1. 打开 TeleAgent Desktop →【技能】→【我的技能】→ 导入/安装
2. 选择 `crushexam-teleagent.zip`（确保解压后 `SKILL.md` 在根目录，不要套多层文件夹）
3. 安装后在技能列表确认「循证备考教练」已启用；若提示技能数量已达上限（100 个），先在列表里停用不常用技能再启用
4. 对话里说「用我的课程资料开始备考」，技能即被触发

### 方式二：手动放置技能目录（推荐开发者/测试者）

从本仓库获取并直接放进 TeleAgent 的技能目录：

```bash
git clone https://github.com/11sta/CrushExam.git
```

1. 找到你的 TeleAgent 技能目录：
   - Windows：`%TELEAGENT_CONFIG_DIR%\skills\`（通常在 `C:\Users\<你>\.config\TeleAgent\users\<用户ID>\skills\`）
   - 可在 PowerShell 运行 `echo $env:TELEAGENT_CONFIG_DIR` 确认
2. 把仓库内容复制为 `skills\crushexam\` 文件夹，保持结构不变：

```text
skills\crushexam\
├── SKILL.md          ← 必须在这里（技能的入口）
├── coach.py
├── coach\
├── references\
├── templates\
└── ...
```

3. 验证安装：

```bash
cd <技能目录>\crushexam
python coach.py doctor
# 预期输出：CrushExam 1.7.0 | python 3.x ...，环境自检全绿
```

4. 重启 TeleAgent Desktop（或新开一个会话）让技能被发现，之后正常对话即可触发

### 安装验证清单

- [ ] `SKILL.md` 位于技能文件夹**根目录**（不是子文件夹里）
- [ ] `python coach.py doctor` 正常运行
- [ ] 技能列表显示「循证备考教练」且已启用
- [ ] 对话说"帮我备考"时技能被激活

### 常见问题

| 现象 | 原因与处理 |
|---|---|
| `python` 不是内部或外部命令 | 未安装 Python 3.8+ 或未加入 PATH；TeleAgent 自带运行时通常可用 |
| doctor 提示 pypdfium2 缺失 | 仅影响 PDF 文字提取与配图，纯文本资料不受影响；需要 PDF 支持时 `pip install pypdfium2` |
| 技能没被触发 | 检查技能是否启用；对话里明确提到"备考/复习/考试/刷题"类关键词 |
| Windows 下教练导入 JSON 报 `Unexpected UTF-8 BOM` | 用 PowerShell 5.1 生成 JSON 时会带 BOM；改为 UTF-8 无 BOM 写入（浏览器导出的 JSON 不受影响） |
| Windows 跑测试有 3 个 ERROR | `test_cli_flow` 的已知隔离缺陷（仅设 HOME 未设 USERPROFILE 时），不影响技能运行 |

### 升级与数据安全

- **升级只替换技能代码目录，绝不删除课程资料和学习工作区**；学习数据（题目、作答、错题、进度）都存在你的资料文件夹的 `exam-cram\` 里，与技能代码完全分离
- 旧版状态（v6）首次由新版保存前会自动备份为 `.backups\`；升级前仍建议自行整份备份工作区
- 绝不在日常升级/恢复场景使用 `setup --fresh`（该参数会主动重置进度）
- 不要让新旧两个版本同时读写同一工作区

## 快速上手

```bash
# 1. 首次：资料 + 考试信息
python coach.py setup "课程资料目录" --exam netsec-final --date 2026-10-04 --lang zh --goal pass --minutes 45

# 2. 分层摸底（逐题提交原答，整轮结束后统一分析）
python coach.py -w "<工作区>" quiz --stratified -n 4
python coach.py -w "<工作区>" submit <qid> "学生真实原答"   # 每题一次

# 3. 分析 → 计划 → 学习
python coach.py -w "<工作区>" gaps --html
python coach.py -w "<工作区>" plan
python coach.py -w "<工作区>" next

# 4. 会话管理
python coach.py -w "<工作区>" session finish   # 结束本次（保留状态）
python coach.py -w "<工作区>" session resume   # 下次恢复
```

学生全程用自然语言（"开始""我的答案是…""不理解这步""今天结束"），命令由宿主代为执行。完整命令协议见 `references/workflow-and-commands.md`，评分契约见 `references/learning-contracts.md`。

## 架构设计

```text
SKILL.md                    宿主教学与交互契约（阶段门禁、呈现规则、诚实边界）
coach.py                    命令入口
coach/runtime.py            工作流控制器（命令分发、阶段校验）
coach/workflow.py           阶段状态机、恢复、会话收束
coach/attempts.py           不可变原答、attempt_id、独立性与时间线
coach/assessment.py         冻结评分契约、完整覆盖校验、原始理由核对
coach/tasks.py              持久化教学任务（补讲/带做/独立/反馈）
coach/planner.py            时间预算与跨日复测调度
coach/evidence.py           证据汇总（文字/矩阵/排序共用，未修复优先）
coach/ability_view.py       能力视图与离线 HTML 热图
coach/blueprint.py          考试蓝图：KC 词典、题→知识点映射、分层抽题
coach/material_safety.py    资料边界、共享题干、可用性检查
coach/workbench.py          离线单题工作台与作答导入契约
coach/workspace_lock.py     有界 OS 锁
coach/ 其他模块             提取、章节、题库、判分、图像、索引等
templates/workbench.html    单题工作台页面
references/                 命令协议、评分点、KC 词典格式、OCR 边界
scripts/                    可重复的发布验证脚本
tests/                      176 项单元与子进程回归
validation/                 实际测试记录与检查证据
```

**数据契约**：`study_state.json`（v7）为权威数据，`attempts` 保存不可变原答，`tasks` 保存可执行任务；`progress.md`/`notebook.md`/`session_summary.md` 是派生视图。状态使用唯一临时文件 + fsync + 原子替换。

## v1.7 更新重点

本版优先修复**学习证据可信度**，而非堆功能：

| 问题 | v1.7 处理 |
|---|---|
| 只评 1/3 问也可能判全对 | 作答前冻结完整评分契约；漏评与未作答分开；不能补写旧要求制造满分 |
| 错题未修复，模块却显示"强" | 文字、矩阵与学习排序共用当前证据汇总；任一未修复题优先 |
| 带做没回应也能继续 | 等待实际步骤 → 核对步骤（`task assess`）→ 通过后才独立；三轮未确认收束为待巩固 |
| 正确选项掩盖错误理由 | 选项信用与方法分开核验；首次原答不可被后来解释替换 |
| 同题记忆与新题能力混同 | 同题隔日、未见原题、参数/表示/情境迁移分别留痕 |
| 用量误报 | 区分本地渲染文件数、日志调用次数与平台积分，不再由 PNG 数推断视觉调用 |

完整变更历史见 `CHANGELOG.md`。

## 升级与数据安全

- **替换 Skill 代码目录，保留课程资料和学习工作区，绝不使用 `--fresh`**（该参数意味着主动重置进度）
- v6 状态首次由新版保存前自动备份为 `.backups/study_state.v6.before-v7.json`；原答与历史迁入 v7，旧手工判分标 `legacy_unverified` 不改写
- 升级前建议自行备份整个工作区；不要让新旧版本并发写同一工作区；回退需恢复升级前的整份备份
- 重扫资料（补材料后）用相同考试 ID、相同工作区再 `setup`：未变化的原答保留，变化题证据隔离待核对

## 测试与验证

```bash
python -m unittest discover -s tests    # 176 项（Windows/Linux 均通过）
python coach.py doctor                  # 环境自检
```

- 单测使用隔离临时目录与考试注册表，不触碰真实学习进度
- `test_cli_flow` 以独立子进程跑完整用户旅程；已在 Windows 上修复 `USERPROFILE` 隔离（v1.7 原版仅设 `HOME`，Windows 下会读到真实注册表）
- 合并保留了纯函数测试（chapters/extract/figures/index/questions/text/usage_log），合计 176 项
- 实际验证记录（合成旅程、浏览器检查）见 `validation/RELEASE_VALIDATION.md`——合成测试不作为真人提分证据

## 边界声明

- 不引入 AI 出题、完整知识 DAG、自动成绩预测或多 Agent 生产流水线
- 章节与知识点自动匹配是启发式，歧义时需人工核对；难度、分值、范围必须有来源
- 主观题与带做步骤的语义核对由宿主教练承担，脚本保证契约完整、引用可追溯、原答不覆盖
- 离线工作台是文件式闭环，不是实时 TeleAgent 前端；浏览器保存不等于工作区已收到
- 无 Python 执行能力时只能受限对话教学，不能声称状态已保存或判分已运行

---
