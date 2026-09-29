# 合成学生命令旅程

仅验证脚本流程。以下回答为预设合成输入，不是对真人学习效果的测量。

## 1. setup /mnt/data/crush_validation/unpacked-journey-v170/synthetic_materials --exam synthetic-release --name 数据结构·发布合成测试 --lang zh --goal pass --days 7 --minutes 45

退出码 0；阶段 diagnosing；有效判分 0。

```text
✅ 工作区已建好: /mnt/data/crush_validation/unpacked-journey-v170/synthetic_materials/exam-cram  (0.0s)
文件: homework×3, lecture×3
章节 (3):
   1. 栈  [lecture1.txt; 3 题目]
   2. 队列  [lecture2.txt; 3 题目]
   3. 二叉树  [lecture3.txt; 3 题目]
题目: 9 (9 有参考答案)
配图: 0 + 0 question/answer crops
资料 | 类型(自动归类) | 提取状态 | 用途/待核对
--- | --- | --- | ---
hw1.txt | homework | 可提取 | 基础原题
hw2.txt | homework | 可提取 | 基础原题
hw3.txt | homework | 可提取 | 基础原题
lecture1.txt | lecture | 可提取 | 理解概念/例题
lecture2.txt | lecture | 可提取 | 理解概念/例题
lecture3.txt | lecture | 可提取 | 理解概念/例题
文件 | 内容 | 用途
--- | --- | ---
/mnt/data/crush_validation/unpacked-journey-v170/synthetic_materials/exam-cram/source_manifest.md | 全量资料来源、提取状态及待核对点 | 确认考试重点与遗漏材料
下一步: python coach.py quiz --stratified -n 6  （入口必经：先小规模分层诊断 → gaps → plan，再开始讲课，不要直接 next）
```

## 2. quiz --stratified -n 4

退出码 0；阶段 diagnosing；有效判分 0。

```text
=== 摸底 1/4：先作答，整轮后统一分析 ===
选题依据：确认范围、题型/章节覆盖、未测优先；难度和分值只使用已核对来源，不估个人得分概率。
[q_09c371c02cca10a6] 第3章｜choice｜hw3.txt p.1
共享题干（来自前题原文，不含答案）：hw3.txt p.1
<<<MATERIAL 047236342655b30e
根A、左孩子B、右孩子C，前序是什么？
MATERIAL>>> 047236342655b30e
<<<MATERIAL f56c0db6eed68055
同一棵二叉树的后序遍历是什么？
A. ABC
B. BCA
MATERIAL>>> f56c0db6eed68055
作答编号：1d98b2831fb94022be0b85b615fc947c
📍 摸底 · 有效作答 0 → python coach.py submit q_09c371c02cca10a6 "<你的原答>"
```

## 3. session pause

退出码 0；阶段 paused；有效判分 0。

```text
本次已暂停；未完成任务与原答已保留。
总结已保存：/mnt/data/crush_validation/unpacked-journey-v170/synthetic_materials/exam-cram/session_summary.md
📍 已暂停 · 有效作答 0 → python coach.py session resume
```

## 4. session resume

退出码 0；阶段 diagnosing；有效判分 0。

```text
[q_09c371c02cca10a6] 第3章｜choice｜hw3.txt p.1
共享题干（来自前题原文，不含答案）：hw3.txt p.1
<<<MATERIAL e795ead20a58abcf
根A、左孩子B、右孩子C，前序是什么？
MATERIAL>>> e795ead20a58abcf
<<<MATERIAL 80f8f978442839f0
同一棵二叉树的后序遍历是什么？
A. ABC
B. BCA
MATERIAL>>> 80f8f978442839f0
作答编号：1d98b2831fb94022be0b85b615fc947c
📍 摸底 · 有效作答 0 → python coach.py submit q_09c371c02cca10a6 "<你的原答>"
```

## 5. submit q_09c371c02cca10a6 B

退出码 0；阶段 diagnosing；有效判分 1。

```text
已记录原答。先完成整轮摸底，再统一分析；此处不揭晓解析。
📍 摸底 · 有效作答 1 → python coach.py quiz --stratified
```

## 6. quiz --stratified

退出码 0；阶段 diagnosing；有效判分 1。

```text
=== 摸底 2/4：先作答，整轮后统一分析 ===
选题依据：确认范围、题型/章节覆盖、未测优先；难度和分值只使用已核对来源，不估个人得分概率。
[q_3e39ed19fba8ca23] 第2章｜subjective｜hw2.txt p.1
<<<MATERIAL 8e8b08d505a2a31a
简述循环队列判断空与满的方法，并解释保留空位。
MATERIAL>>> 8e8b08d505a2a31a
作答编号：8c02b0ffee3d4f059e31b0eb133826a0
📍 摸底 · 有效作答 1 → python coach.py submit q_3e39ed19fba8ca23 "<你的原答>"
```

## 7. submit q_3e39ed19fba8ca23 空时front=rear；满条件和空位原因还不清楚。

退出码 0；阶段 diagnosing；有效判分 1。

```text
已记录原答。先完成整轮摸底，再统一分析；此处不揭晓解析。
📍 摸底 · 有效作答 1 → python coach.py quiz --stratified
```

## 8. quiz --stratified

退出码 0；阶段 diagnosing；有效判分 1。

```text
=== 摸底 3/4：先作答，整轮后统一分析 ===
选题依据：确认范围、题型/章节覆盖、未测优先；难度和分值只使用已核对来源，不估个人得分概率。
[q_14b5b6859b1fc62d] 第1章｜choice｜hw1.txt p.1
<<<MATERIAL 6235fb5be022091a
栈的基本规则是什么？
A. 先进先出
B. 后进先出
MATERIAL>>> 6235fb5be022091a
作答编号：e97bf56cbb8b414ab1282e24ff11046d
📍 摸底 · 有效作答 1 → python coach.py submit q_14b5b6859b1fc62d "<你的原答>"
```

## 9. submit q_14b5b6859b1fc62d B

退出码 0；阶段 diagnosing；有效判分 2。

```text
已记录原答。先完成整轮摸底，再统一分析；此处不揭晓解析。
📍 摸底 · 有效作答 2 → python coach.py quiz --stratified
```

## 10. quiz --stratified

退出码 0；阶段 diagnosing；有效判分 2。

```text
=== 摸底 4/4：先作答，整轮后统一分析 ===
选题依据：确认范围、题型/章节覆盖、未测优先；难度和分值只使用已核对来源，不估个人得分概率。
[q_183e57ae5ca81816] 第2章｜choice｜hw2.txt p.1
<<<MATERIAL 313b6ad3d06cbeda
队列入队1、2后出队得到什么？
A. 1
B. 2
MATERIAL>>> 313b6ad3d06cbeda
作答编号：1ecc6646742c499a936f200854fa47d8
📍 摸底 · 有效作答 2 → python coach.py submit q_183e57ae5ca81816 "<你的原答>"
```

## 11. submit q_183e57ae5ca81816 A

退出码 0；阶段 analysis；有效判分 3。

```text
已记录原答。先完成整轮摸底，再统一分析；此处不揭晓解析。
📍 汇总分析 · 有效作答 3 → python coach.py gaps
```

## 12. gaps --html

退出码 0；阶段 planning；有效判分 3。

```text
=== 知识点能力表｜按章暂代 ===
已测 3 道；未测不是零分，单题答对也不能推算考试得分概率。
没有 KC 词典，按章聚合（导入蓝图后可按知识点查看）
模块 | 最近证据 | 已测/题库 | 说明
--- | --- | --- | ---
栈 | 独立作答样本（仍需补测） | 1/3 | 错/跳 0、独立对 1、未测 2
队列 | 独立作答样本（仍需补测） | 1/3 | 错/跳 0、独立对 1、未测 2
二叉树 | 独立作答样本（仍需补测） | 1/3 | 错/跳 0、独立对 1、未测 2
1 道主观题待依据参考答案核对；暂不纳入已测能力。
文件 | 内容 | 用途
--- | --- | ---
/mnt/data/crush_validation/unpacked-journey-v170/synthetic_materials/exam-cram/capability.html | 离线知识模块×题型热图、六模块概览及来源表 | 核对误标并确定先补模块（浏览器打开）
📍 安排首轮任务 · 有效作答 3 → python coach.py plan
非判分记录：主观题待核对 1
这些记录不等于答错，不纳入正确率；首次原答与原因均可追溯。
📍 安排首轮任务 · 有效作答 3 → python coach.py plan
```

## 13. plan

退出码 0；阶段 planned；有效判分 3。

```text
=== 今日计划｜先补关键缺口 ===
考试日期：未填写；只使用确认范围与分值，不估计个人通过概率。
当前任务：栈
步骤：定位并补讲｜预算 25 分钟
完成依据：完成一次未见原题独立验证；选项与方法证据分别记录
原因：尚未摸底；考试对应分值未知；基于本章 1 道已测题
依据：尚未摸底；考试对应分值未知；基于本章 1 道已测题
安排说明：ch1
📍 今日任务 · 栈 · 有效作答 3 → python coach.py next
```

## 14. task

退出码 0；阶段 planned；有效判分 3。

```text
当前任务：栈
步骤：定位并补讲｜预算 25 分钟
完成依据：完成一次未见原题独立验证；选项与方法证据分别记录
原因：尚未摸底；考试对应分值未知；基于本章 1 道已测题
📍 今日任务 · 栈 · 有效作答 3 → python coach.py next
```

## 15. goto 1 --restart

退出码 0；阶段 studying；有效判分 3。

```text
已切换到第1章：栈；后续 next/quiz 将执行同一任务。
📍 学习与练习 · 栈 · 有效作答 3 → python coach.py next
```

## 16. next

退出码 0；阶段 studying；有效判分 3。

```text
当前任务：栈
步骤：定位并补讲｜预算 25 分钟
完成依据：完成一次未见原题独立验证；选项与方法证据分别记录
原因：尚未摸底；考试对应分值未知；基于本章 1 道已测题
<<<MATERIAL e1766c3603c4bb4b
[lecture1.txt p.1]
第1章 栈
栈遵循后进先出。入栈在栈顶添加元素，出栈删除栈顶元素。
例：入栈1，入栈2，再出栈得到2，剩下1。
MATERIAL>>> e1766c3603c4bb4b
教练只解释当前规则及其适用条件，先确认学生卡在哪一步；下一步用资料例题补步骤。
📍 学习与练习 · 栈 · 有效作答 3 · 等待你的下一步选择
```

## 17. next

退出码 0；阶段 studying；有效判分 3。

```text
带做例题：只检查一个关键步骤，不能算作独立测试。
[q_d972d360694ce746] 第1章｜choice｜hw1.txt p.1
<<<MATERIAL 13d2734160dff074
入栈1、2后出栈得到什么？
A. 1
B. 2
MATERIAL>>> 13d2734160dff074
--- 参考答案 ---
🟢 (hw1.txt p.1)
<<<MATERIAL ca89fc3d6490a815
B
MATERIAL>>> ca89fc3d6490a815
教练先示范第一步，再让学生补下一步；等待学生回答。随后选另一道原题独立验证。
📍 学习与练习 · 栈 · 有效作答 3 · 等待你的下一步选择
```

## 18. next

退出码 0；阶段 studying；有效判分 3。

```text
当前任务：栈
步骤：等待你补一个步骤｜预算 25 分钟
完成依据：完成一次未见原题独立验证；选项与方法证据分别记录
原因：尚未摸底；考试对应分值未知；基于本章 1 道已测题
等你补一个关键步骤；重复 next 不会跳过回应。实际回应由 task note 保存。
📍 学习与练习 · 栈 · 有效作答 3 → python coach.py task note --note "<学生实际补出的步骤>"
```

## 19. task note --note 合成学生：先标记栈顶，再删除最后入栈的元素。

退出码 0；阶段 studying；有效判分 3。

```text
实际步骤已保存：6713c2409fdf43169610a5d3416f0ab3；待核对，不计独立成功。
当前任务：栈
步骤：核对刚才的步骤｜预算 25 分钟
完成依据：完成一次未见原题独立验证；选项与方法证据分别记录
原因：尚未摸底；考试对应分值未知；基于本章 1 道已测题
📍 学习与练习 · 栈 · 有效作答 3 → python coach.py task assess --step-id 6713c2409fdf43169610a5d3416f0ab3 --verdict <met|partial|incorrect|uncertain> --quote "<原话>" --reference-quote "<参考片段>" --note "<核对说明>"
```

## 20. task assess --step-id 6713c2409fdf43169610a5d3416f0ab3 --verdict met --quote 先标记栈顶，再删除最后入栈的元素 --reference-quote B --note 合成输入核对：参考选项对应弹出栈顶，实际学生步骤已保存。

退出码 0；阶段 studying；有效判分 3。

```text
步骤核对已保存。通过才进入独立练习；部分/错误/不确定先补小步骤。
当前任务：栈
步骤：独立做资料原题｜预算 25 分钟
完成依据：完成一次未见原题独立验证；选项与方法证据分别记录
原因：换另一道未见资料原题验证。
📍 学习与练习 · 栈 · 有效作答 3 → python coach.py next
```

## 21. next

退出码 0；阶段 studying；有效判分 3。

```text
=== 资料原题练习｜只做当前这一题 ===
[q_ab631da48e04cc88] 第1章｜choice｜hw1.txt p.1
<<<MATERIAL a872c482a899eb57
入栈1、2，出栈，入栈3再出栈，顺序是什么？
A. 1、3
B. 2、3
MATERIAL>>> a872c482a899eb57
作答编号：e56d96d9d76f4bfe8b381e5498316f86
📍 学习与练习 · 栈 · 有效作答 3 → python coach.py submit q_ab631da48e04cc88 "<你的原答>"
```

## 22. workbench --out /mnt/data/crush_validation/unpacked-journey-v170/student_question.html

退出码 0；阶段 studying；有效判分 3。

```text
学习工作台：/mnt/data/crush_validation/unpacked-journey-v170/student_question.html
页面一次显示一题，可填写、冻结并导出原答。将JSON交回教练，用 import-answer 导入后才更新进度。
未提交题目的参考答案不写入页面；这是离线文件，不是已接通TeleAgent的实时前端。
```

## 23. submit q_ab631da48e04cc88 B

退出码 0；阶段 studying；有效判分 3。

```text
原答已冻结保存。下一步核对；修改不会覆盖这次提交。
📍 学习与练习 · 栈 · 有效作答 3 → python coach.py grade q_ab631da48e04cc88
```

## 24. check q_ab631da48e04cc88

退出码 0；阶段 studying；有效判分 3。

```text
[q_ab631da48e04cc88] 第1章｜choice｜hw1.txt p.1
<<<MATERIAL 6aa6b1b017508e25
入栈1、2，出栈，入栈3再出栈，顺序是什么？
A. 1、3
B. 2、3
MATERIAL>>> 6aa6b1b017508e25
--- 参考答案 ---
🟢 (hw1.txt p.1)
<<<MATERIAL 06a182590acee284
B
MATERIAL>>> 06a182590acee284
提交后的解析不会改变这次原答的独立性；今天再次做同题会标记为受助。
📍 学习与练习 · 栈 · 有效作答 3 → python coach.py grade q_ab631da48e04cc88
```

## 25. grade q_ab631da48e04cc88 --error-type procedure

退出码 0；阶段 studying；有效判分 4。

```text
正确｜即时独立
原答：B
参考依据：hw1.txt p.1
参考答案：B
本题已收束。等待你决定继续、查看任务或结束本次，不自动开启下一题。
📍 学习与练习 · 有效作答 4 · 等待你的下一步选择
```

## 26. workbench --out /mnt/data/crush_validation/unpacked-journey-v170/student_feedback.html

退出码 0；阶段 studying；有效判分 4。

```text
学习工作台：/mnt/data/crush_validation/unpacked-journey-v170/student_feedback.html
页面一次显示一题，可填写、冻结并导出原答。将JSON交回教练，用 import-answer 导入后才更新进度。
未提交题目的参考答案不写入页面；这是离线文件，不是已接通TeleAgent的实时前端。
```

## 27. done --chapter 1

退出码 0；阶段 studying；有效判分 4。

```text
第1章已结束。
本章有2道当前独立正确证据；不代表全章或所有题型掌握。
📍 学习与练习 · 有效作答 4 → python coach.py session finish
```

## 28. session finish

退出码 0；阶段 session_complete；有效判分 4。

```text
本次已结束；未完成任务与原答已保留。
总结已保存：/mnt/data/crush_validation/unpacked-journey-v170/synthetic_materials/exam-cram/session_summary.md
📍 本次已结束 · 有效作答 4 → python coach.py session resume
```

## 29. next

退出码 4；阶段 session_complete；有效判分 4。

```text
本次学习已暂停或结束。先用 session resume 恢复；不会自动跳过未完成作答。
📍 本次已结束 · 有效作答 4 → python coach.py session resume
```

## 30. session resume

退出码 0；阶段 studying；有效判分 4。

```text
已恢复保存的阶段和任务；不会重新初始化课程或清空历史。
总结已保存：/mnt/data/crush_validation/unpacked-journey-v170/synthetic_materials/exam-cram/session_summary.md
📍 学习与练习 · 有效作答 4 → python coach.py session finish
```

## 31. status

退出码 0；阶段 studying；有效判分 4。

```text
数据结构·发布合成测试｜考试 synthetic-release｜学习与练习
目标：pass｜考试日期：未填写
本次暂无待执行任务。已结束不代表全部掌握，可查看总结或安排下一次。
待澄清 0｜待人工核对 1｜资料阻塞 0｜无可靠答案 0
📍 学习与练习 · 有效作答 4 → python coach.py session finish
```

## 32. session finish

退出码 0；阶段 session_complete；有效判分 4。

```text
本次已结束；未完成任务与原答已保留。
总结已保存：/mnt/data/crush_validation/unpacked-journey-v170/synthetic_materials/exam-cram/session_summary.md
📍 本次已结束 · 有效作答 4 → python coach.py session resume
```
