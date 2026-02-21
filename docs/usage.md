# 使用指南

本页聚焦“怎么用”：模式选择、Deep Research、代码执行、浏览器自动化等。

---

## 基本对话

1. 打开 Web 界面
2. 在输入框输入问题，例如：“介绍一下 LangGraph”
3. 选择模式：
   - **直接模式**：LLM 直接回答
   - **搜索模式**：联网搜索后回答
   - **工具模式**：调用工具辅助回答
   - **深度模式**：多轮深度研究

---

## 深度研究示例

```
用户：深入研究一下 2024 年人工智能的最新进展

系统：[启动深度研究模式]
  → 第 1 轮：生成 5 个子查询
    - "2024 年 AI 重大突破"
    - "大语言模型最新进展"
    - "AI 应用落地案例"
    - "AI 安全与伦理"
    - "AI 产业发展趋势"
  → 并行搜索 15 个结果
  → 内容摘要与分析
  → 第 2 轮：针对关键点深挖
  → 生成综合报告
```

### 深度研究的引用与证据（强引用）

- 报告正文中的引用采用编号格式：`[1] [2] ...`，编号与文末的“参考来源（自动生成）”一致。
- 在 Web UI 中点击正文里的 `[n]`，会高亮并定位到对应来源（Source Inspector），便于快速核对证据。
- 可通过 `.env` 调整引用来源数量：`DEEPSEARCH_REPORT_SOURCES_LIMIT=20`（默认 20）。
- 如果你希望“证据段落 / passages”更丰富（更慢、更耗 token），可开启抓取正文：
  - `DEEPSEARCH_ENABLE_RESEARCH_FETCHER=true`

---

## 代码执行示例

```python
用户：画一个 2024 年中国 GDP 增长趋势图

系统：[调用 execute_python_code 工具]
```

```python
import matplotlib.pyplot as plt

quarters = ["Q1", "Q2", "Q3", "Q4"]
gdp = [5.3, 4.7, 4.6, 5.4]

plt.figure(figsize=(10, 6))
plt.plot(quarters, gdp, marker="o", linewidth=2, markersize=8)
plt.title("2024年中国GDP季度增长率", fontsize=16)
plt.ylabel("增长率 (%)", fontsize=12)
plt.grid(True, alpha=0.3)
plt.show()
```

---

## 浏览器自动化示例

```
用户：帮我打开百度，搜索"LangGraph 教程"，并截图

系统：[调用沙箱浏览器工具]
  1. sb_browser_navigate: 访问 https://www.baidu.com
  2. sb_browser_type: 在搜索框输入"LangGraph 教程"
  3. sb_browser_click: 点击"百度一下"按钮
  4. sb_browser_screenshot: 截取搜索结果页面

[返回截图]
```
