# CrushExam · 循证备考教练

**把你自己的课件、试卷和笔记，变成一套"先诊断、再补讲、后带练、可复测"的备考流程——先答后查、原答不可覆盖、每个结论有出处。**

CrushExam 是一个 TeleAgent 技能（Skill）。你把课程资料交给 TeleAgent 并说一句"帮我备考"，它就会提取题目与考点、分层摸底、生成能力缺口视图和每日计划，然后逐题带你练到会、按遗忘节奏安排复测。核心脚本离线运行（仅 Python 标准库），不依赖模型 API，不用 AI 编题、不猜教师重点、不编造通过概率。

适合期末考试、等级/认证考试、技能类考试的冲刺复习与错题复盘。

---

## 一分钟看懂它怎么工作

```text
你的资料 → 提取题目与考点 → 分层摸底（一次一题）
        → 能力缺口热图 + 每日计划
        → 补讲 → 带做 → 独立练习 → 反馈
        → 错题跨日复测 → 考前小抄
```

- **诊断**：从你的试卷/作业/课件里提取章节、题目与配图，分层抽题摸底，生成"知识点 × 题型"能力热图——灰色代表未测，不伪造掌握度
- **计划**：结合考试日期、每天可用时间和已确认的分值结构，输出今天该学什么、大约学多久
- **学会**：按"补讲 → 带做 → 独立 → 反馈"闭环教学：教练示范关键步骤，你补上缺的那步，核对通过后才进入独立练习
- **记住**：错题自动排期复测；同题隔日重测、未见过的变式迁移分别留痕，不互相冒充

## 核心理念

| 原则 | 含义 |
|---|---|
| **循证（Evidence-based）** | 只用你资料里的题；每个结论标注出处和样本数；题库数量、印刷分值不冒充卷面权重 |
| **先答后查（Answer-first）** | 必须先提交原答才能看参考解析，这是代码级门禁，不是行为约定 |
| **原答不可覆盖** | 提交后原话冻结；重复提交幂等；重做必须重新呈题建立新记录，不能用"后来才想明白"覆盖当时的真实作答 |
| **诚实边界** | 一次答对不称掌握；未测不是零分；提交数≠判分数；自报成绩必须标注 |
| **统一判分策略** | 内置判分规则（10 分制、通过线 ≥8、多选全对 10/漏选 6/错选 0、不定项按答案形态自动分流、AI 参考显式标注），任何账号判分语义一致，不靠宿主每次现发挥 |
| **可中断恢复** | 阶段、任务、未答题全部持久化；下次对话自动恢复原进度，不重新开始 |

## 功能总览

**诊断与分析**
- 提取资料 → 章节/题目/配图，输出提取状态透明报告（哪些成功、哪些是扫描件、哪些被跳过）
- 分层摸底：按确认范围、题型/章节覆盖、未测优先抽题，一次一题，整轮结束前不揭晓
- 知识点能力表 + 离线 HTML 热图（知识模块 × 题型、六模块概览、来源表）
- 考试蓝图：KC 词典（知识点 + 关键词）自动映射题目，支持分值结构导入与手动修正

**教学闭环（补讲 → 带做 → 独立 → 反馈）**
- 按持久化任务逐步教学：概念题讲含义与适用条件、程序题展示中间状态、计算题讲公式选择
- 带做：教练示范必要步骤 → 你补关键步骤（原话保存）→ 教练核对 → 通过后才进独立
- 独立：同任务中另一道**未被带做**的原题，只给题不提示
- 反馈：先存原答再判分；只给结果、首个关键错误、下一动作

**判分与证据**
- 客观题自动判分（对/错、√/×、T/F、单字母、ABCD 集合归一化），判分结果带分值与通过线
- 主观题评分契约：看到你的答案**之前**冻结完整要点清单，逐项核对（met/partial/missing/uncertain），漏评不判全对
- 选项与方法分离：选对但理由错误 → 选项得分保留、方法单独核验
- 跨日复测与迁移：同题隔日、未见原题、参数/表示/情境变化分别留痕

**辅助能力**
- 离线单题工作台（HTML）：本地作答、冻结、导出 JSON 回后端判分
- 用量报告：区分本地渲染文件数、日志调用次数与平台积分，不虚报
- 考前小抄、自报成绩（始终标注）、环境自检（doctor）

## 支持的资料格式

| 类型 | 格式 | 说明 |
|---|---|---|
| 纯文本 | txt / md / markdown / text / rst | 自动识别 UTF-8 / GB18030 编码 |
| 网页 | html / htm | 提取正文文本 |
| 文档 | docx | 含表格 |
| 幻灯片 | pptx | 逐页提取，含演讲者备注 |
| PDF | pdf | 需可选依赖 `pypdfium2`（doctor 会检测）；纯图片扫描件走受控 OCR 流程 |
| 图片 | png / jpg / jpeg / gif / bmp / webp | 仅作题目配图展示，不参与文本提取 |

旧版 .ppt/.xls、epub、音视频暂不支持。扫描件（无文字层 PDF）在提取时会被明确标记，按受控流程处理：先核对、再局部识读、成本可控、出处可溯，不会擅自全量 OCR。

## 快速上手

**日常使用：全程自然语言，不需要记任何命令。**

部署后对 TeleAgent 说：

> 我有一堆课程资料，帮我备考。

它会引导你提供最小资料包（一份带可靠答案的试卷或作业 + 老师划的重点 + 课件任选其一），自动完成提取、摸底和计划。之后直接说"开始""我的答案是……""这步不理解""今天到此为止"即可；中断后下次自动恢复原进度。

**进阶：直接驱动命令**（通常由宿主代为执行，适合开发与测试）

```bash
# 1. 首次：资料 + 考试信息
python scripts/coach.py setup "课程资料目录" --exam final --date 2026-12-18 --lang zh --goal pass --minutes 45

# 2. 分层摸底（逐题提交原答，整轮结束后统一分析）
python scripts/coach.py -w "<工作区>" quiz --stratified -n 4
python scripts/coach.py -w "<工作区>" submit <qid> "学生真实原答"   # 每题一次

# 3. 分析 → 计划 → 学习
python scripts/coach.py -w "<工作区>" gaps --html
python scripts/coach.py -w "<工作区>" plan
python scripts/coach.py -w "<工作区>" next

# 4. 会话管理
python scripts/coach.py -w "<工作区>" session finish   # 结束本次（保留状态）
python scripts/coach.py -w "<工作区>" session resume   # 下次恢复
```

完整命令协议见 `references/workflow-and-commands.md`，评分契约见 `references/learning-contracts.md`，判分规则见 `references/grading-policy.md`。

## 部署到 TeleAgent

CrushExam 部署后，TeleAgent 会在你说"备考/复习/刷题"等场景自动激活它。有两种安装方式：

### 方式一：导入 ZIP（推荐普通用户）

如果你拿到的 ZIP 来自作者或技能市场：

1. 打开 TeleAgent Desktop →【技能】→【我的技能】→ 导入/安装
2. 选择 `crushexam-teleagent-v1.9.0.zip`（确保解压后 `SKILL.md` 在根目录，不要套多层文件夹）
3. 安装后在技能列表确认「循证备考教练」已启用；若提示技能数量已达上限，先停用不常用技能再启用
4. 对话里说「用我的课程资料开始备考」即可触发；全新账号只需准备资料，其余引导由技能自动完成

### 方式二：手动放置技能目录（推荐开发者/测试者）

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
├── scripts\          ← coach.py 入口与 coach\ 包
├── references\       ← 使用说明、判分策略等文档
├── assets\           ← workbench.html、grading-policy.json
└── tests\
```

3. 验证安装：

```bash
cd <技能目录>\crushexam
python scripts/coach.py doctor
# 预期输出：CrushExam 1.9.0 | python 3.x ...，环境自检全绿
```

4. 重启 TeleAgent Desktop（或新开一个会话）让技能被发现

### 安装验证清单

- [ ] `SKILL.md` 位于技能文件夹**根目录**（不是子文件夹里）
- [ ] `python scripts/coach.py doctor` 正常运行
- [ ] 技能列表显示「循证备考教练」且已启用
- [ ] 对话说"帮我备考"时技能被激活

### 常见问题

| 现象 | 原因与处理 |
|---|---|
| `python` 不是内部或外部命令 | 未安装 Python 3.8+ 或未加入 PATH；TeleAgent 自带运行时通常可用 |
| doctor 提示 pypdfium2 缺失 | 仅影响 PDF 文字提取与配图，纯文本资料不受影响；需要 PDF 支持时 `pip install pypdfium2` |
| 技能没被触发 | 检查技能是否启用；对话里明确提到"备考/复习/考试/刷题"类关键词 |
| Windows 下导入 JSON 报 `Unexpected UTF-8 BOM` | 用 PowerShell 5.1 生成 JSON 时会带 BOM；改为 UTF-8 无 BOM 写入（浏览器导出的 JSON 不受影响） |

## 数据与隐私

- **学习数据只存本地**：题目、作答、错题、进度全部保存在你资料目录下自动生成的 `exam-cram\` 里，与技能代码完全分离；升级只替换技能代码目录，不动你的学习进度
- **资料目录只读**：脚本不修改、不移动、不删除任何原始资料文件，全部产物只写入 `exam-cram\` 子目录
- **个人信息最小化**：材料入库与导出（能力视图、小抄）双层自动掩码手机号、身份证、邮箱等格式类信息；`python scripts/mask_check.py <文件>` 可独立预览掩码效果。中文人名无法与题干用名可靠区分，不做自动掩码；图片中的信息无法掩码
- **升级安全**：旧版状态首次由新版保存前自动备份到 `.backups\`；日常升级/恢复绝不使用 `setup --fresh`（该参数会主动重置进度）；回退需恢复升级前整份备份
- 不要让新旧两个版本同时读写同一工作区；补材料后重扫用相同考试 ID 与工作区再 `setup`，未变化的原答保留

## 架构设计

```text
SKILL.md                    宿主教学与交互契约（阶段门禁、呈现规则、诚实边界）
scripts/coach.py            命令入口
scripts/coach/runtime.py    工作流控制器（命令分发、阶段校验）
scripts/coach/workflow.py   阶段状态机、恢复、会话收束
scripts/coach/attempts.py   不可变原答、attempt_id、独立性与时间线
scripts/coach/assessment.py 冻结评分契约、完整覆盖校验、原始理由核对
scripts/coach/tasks.py      持久化教学任务（补讲/带做/独立/反馈）
scripts/coach/planner.py    时间预算与跨日复测调度
scripts/coach/evidence.py   证据汇总（文字/矩阵/排序共用，未修复优先）
scripts/coach/ability_view.py 能力视图与离线 HTML 热图（导出侧二次掩码）
scripts/coach/blueprint.py 考试蓝图：KC 词典、题→知识点映射、分层抽题
scripts/coach/policy.py     判分策略唯一机器源（通过线、多选10/6/0、rubric落分）
scripts/coach/pii.py        入库+导出双层格式类个人信息掩码
scripts/coach/material_safety.py 资料边界、共享题干、可用性检查
scripts/coach/workbench.py  离线单题工作台与作答导入契约
scripts/coach/workspace_lock.py 有界 OS 锁
scripts/coach/ 其他模块     提取、章节、题库、判分、图像、索引等
assets/workbench.html       单题工作台页面
assets/grading-policy.json  判分策略默认配置（机器可读，可审计/覆盖）
references/                 命令协议、评分契约、判分策略与样例、OCR 边界、版本历史
tests/                      单元与子进程回归（含导出掩码回归）
```

**数据契约**：`study_state.json` 为权威数据，作答账本保存不可变原答，`tasks` 保存可执行任务；`progress.md`/`notebook.md`/`session_summary.md` 是派生视图。状态写入使用唯一临时文件 + fsync + 原子替换。

## 测试与验证

```bash
python -m unittest discover -s tests -t .    # 在技能根目录运行（Windows/Linux 均通过）
python scripts/coach.py doctor                  # 环境自检
```

- 204 项单元与子进程测试全部通过；测试使用隔离临时目录与考试注册表，不触碰真实学习进度
- 端到端合成旅程复现：`python scripts/validate_release.py --out <空目录>`（独立 HOME、零网络、合成材料）——合成测试不作为真人提分证据

## 边界声明

- 不引入 AI 出题、完整知识 DAG、自动成绩预测或多 Agent 生产流水线
- 章节与知识点自动匹配是启发式，歧义时需人工核对；难度、分值、范围必须有来源
- 主观题与带做步骤的语义核对由宿主教练承担，脚本保证契约完整、引用可追溯、原答不覆盖
- 离线工作台是文件式闭环，不是实时前端；浏览器保存不等于工作区已收到
- 无 Python 执行能力时只能受限对话教学，不能声称状态已保存或判分已运行

## License
MIT
