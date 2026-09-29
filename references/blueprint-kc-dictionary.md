---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'c30c23fd-7f9c-449f-9f7e-2135944b70cd'
  PropagateID: 'c30c23fd-7f9c-449f-9f7e-2135944b70cd'
  ReservedCode1: '4c74d06d-9289-4129-9ab6-def50ed597ef'
  ReservedCode2: '4c74d06d-9289-4129-9ab6-def50ed597ef'
---

# 考试蓝图与 KC 词典（blueprint-kc-dictionary.md）

> 支持文档：如何为某门课建立「考试蓝图」，让分层诊断（`quiz --stratified`）和知识点能力表（`gaps`）按知识点工作。
> 与 SKILL.md §1a/§3/§6 配套；本文件描述数据格式与构建流程，命令行为以 `python coach.py blueprint --help` 为准。

## 1. 蓝图是什么

`blueprint.json`（工作区内）由三部分组成：

1. **考试结构 structure**：题型 × 题数 × 分值（来自老师/卷面/学生笔记，标注来源与是否已确认）。
2. **KC 词典 kcs**：知识点列表。每个知识点（knowledge component）有 `id`、`chapter`、`title`、`keywords`、`source`。词典是**课程数据，不是代码**——由你（tutor）根据该课程的资料提取，导入后代码按关键词自动把题库里的题映射到知识点。
3. **题目映射 q_map**：qid → [kc, ...]，由关键词匹配自动生成；可用 `blueprint --qmap qid:kc1+kc2` 手动修正（重建时保留）。可选 `question_meta` 用于记录有出处的题目难度。

## 2. 快速流程

1. 从课程资料（笔记目录/PPT 目录/考纲）列出知识点 → 写成 JSON 文件，建议放资料夹根目录 `kc-dict.json`（re-setup 会自动重新导入，见 §4）。
2. `python coach.py blueprint --file kc-dict.json` → 自动建映射并打印覆盖情况。
3. `python coach.py blueprint --kcs` 查看全部知识点；`blueprint --qmap q_xxx:kc1+kc2` 修正明显误标。
4. `python coach.py gaps` 看知识点能力表；`python coach.py quiz --stratified -n 6` 做分层诊断。

## 3. 文件格式

```json
{
  "structure": {
    "source": "手写笔记 p.2（学生自记，已确认）",
    "confirmed": true,
    "sections": [
      {"type": "单选", "count": 15, "points": 30, "note": "每题2分"},
      {"type": "判断", "count": 5, "points": 10}
    ],
    "note": "可选补充说明"
  },
  "kcs": [
    {"id": "ch6-2", "chapter": 6, "title": "AH与ESP封装模式",
     "keywords": ["AH", "ESP", "传输模式", "隧道模式"], "source": "notes",
     "exam_points": 12, "weight_confirmed": true, "weight_source": "教师公布考核表 p.2"},
    {"id": "misc-web", "chapter": null, "title": "Web/浏览器安全",
     "keywords": ["Web", "Cookie"], "source": "bank"}
  ],
  "question_meta": {
    "q_abc123": {"difficulty": "basic", "difficulty_confirmed": true,
                 "difficulty_source": "老师标注基础题，作业第 2 页"}
  }
}
```

- `structure` 可省略（考试结构未知时留空，先建知识点）。
- `kcs` 也可以是顶层裸列表（只有知识点、没有结构）。
- `source`：`notes`（来自笔记/讲义）或 `bank`（从题目反推的补充知识点，如考试里出现但笔记未覆盖的主题）。`blueprint --kcs` 展示时会标注「题库补充」。
- `chapter`：与工作区 `chapters.json` 的章节号一致；跨章主题可设为 `null`（按知识点聚合时排在最后）。
- `exam_points` 可省略；只有同时给出 `weight_confirmed: true` 和可核查的 `weight_source` 时才参与知识点排序。它表示**考试范围内有来源的分值**，不是练习题上的分数；没证据请删掉这三个字段。
- `structure.confirmed: true` 需要写明 `source` 且各题型有可信的总分 `points`；只有这样的考试结构才用于题型分值排序。仅凭某章题库题数、打印练习题分值或记忆中的印象不能确定卷面权重。

## 4. 关键词匹配规则（决定 q_map 质量）

- 匹配对象：题干 + 全部选项 + 参考答案（含解析）。答案里点名概念也算命中。
- 命中数排序，每题最多取前 3 个知识点。
- **纯 ASCII 且 ≤3 字符**的关键词（`AH`、`SA`、`MAC`、`IV`）做**词边界**匹配，避免误伤（`HASH` 不会命中 `AH`，`DNSSec` 不会命中 `DNS`）。
- 中文关键词按子串匹配。
- 匹配不中的题**不会被打标签**，`blueprint` 的「未映射」清单与 `gaps` 的「chN 其他」行会诚实展示——绝不猜标签。

## 5. 质量建议（真实使用反馈）

- **关键词宁缺毋滥**：别放太泛的词（如「安全」「协议」），会污染多个知识点，把能力表稀释成噪音。宁可用 3–5 个特征词（概念名/协议名/专有名词）。
- **词典以笔记小节为骨架**：先用课程笔记/PPT 的目录生成 `id/title/chapter`，再逐小节补关键词，最后用 `blueprint` 的未映射清单和抽查标签来校准。
- **跨章题很正常**：试卷题被 BM25 归到某章，但考点可能属于另一章的知识点（如「木马安装到被控端」在 ch5，考点是木马）。q_map 允许跨章，能力表按知识点聚合时自动合并。
- **手动修正**：`blueprint --qmap q_xxx:ch2-3+ch2-4` 后重建不丢；误标改为空列表 `--qmap q_xxx:` 即移除。

## 6. 分层抽样怎么用

`quiz --stratified -n 6`：
- 有已确认的考试范围时先限定对应章节；有已确认卷面结构时覆盖题型并参考对应题型总分；有来源的知识点分值也可参与同一轮排序。**不以某章题库题数充当考试分值**。
- 优先未作答题、未覆盖知识点和题型，再用题号稳定消歧。题库只覆盖有限题型时，报告缺失题型，不用无关题冒充摸底。
- 可核实的题目难度可在 `question_meta` 按题号记录 `difficulty`（`basic`/`medium`/`hard` 或 1–5）、`difficulty_confirmed: true` 和 `difficulty_source`，帮助覆盖基础与较难题；自动抽出的题通常没有可信难度，维度标「未知」，不从题长或加粗推断。
- 题目不够时按现有范围提供可用题并明确未测；默认少量诊断，用户要求深入摸底时再增加题量。

## 7. 诚实边界（与 SKILL.md §6 一致）

- 能力表保留「基于 N 题」的去重样本数，并附 `by_type`（知识点 × 题型的已测、未测、最近表现）；一道题可属于两个知识点，按章节汇总时只计一次。
- **历史最好证据与最近表现分别展示**；最近答错必须恢复为缺口，不能沿用曾经正确的强度。未测题不得当作零分；提示后答对不能当作独立掌握。
- 分值结构若来自学生自记，`structure.confirmed` 标 false 并写清来源；输出始终带来源标注。
- 摸底答对率只是小样本记录，不能直接转换为正式考试得分概率、通过率或预计提分。

> AI生成
