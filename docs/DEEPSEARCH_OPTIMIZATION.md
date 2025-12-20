# DeepSearch 优化方案

## 📊 对比分析

对比了参考项目 `deep_search-dev` 和当前 Weaver 项目的 DeepSearch 实现后，发现以下可优化点：

### ✅ 当前已有的优势

1. **Prompt 已经很好**：使用了结构化的"角色-背景-任务-输出-限制"框架
2. **集成到 LangGraph**：与整体工作流无缝集成
3. **配置化**：从 settings 读取参数（max_epochs, query_num等）
4. **取消机制**：集成到 cancellation_manager
5. **爬虫增强**：`_hydrate_with_crawler` 补充内容

### 🔧 需要优化的点

#### 1. **URL 去重机制** ⭐⭐⭐⭐⭐

**问题**：当前实现可能会重复爬取相同的 URL

**参考项目的方案**：
```python
class SearchCrawl:
    def __init__(self):
        self.all_searched_urls = []   # 所有搜索到的 URL
        self.selected_urls = []        # 已爬取的 URL

    async def select_related_url(self, search_results):
        # 从 all_searched_urls 中排除已爬取的
        available_urls = [
            url for url in self.all_searched_urls
            if url not in self.selected_urls
        ]

        # 选择后更新 selected_urls
        self.selected_urls.extend(related_urls)
```

**优势**：
- 避免重复爬取同一 URL
- 节省网络请求和时间
- 提高信息多样性

---

#### 2. **OOP 封装 - 职责分离** ⭐⭐⭐⭐

**问题**：当前所有逻辑都在函数中，不易维护状态

**参考项目的方案**：
```python
class DeepSearch:
    """主流程控制"""
    def __init__(self, topic, max_epochs):
        self.topic = topic
        self.max_epochs = max_epochs
        self.summary_search = []
        self.have_query = []
        self.crawl_res_lst = []
        self.search_crawl = SearchCrawl(...)

    async def run(self):
        for epoch in range(self.max_epochs):
            rewrite_query = await self.step_formulate_query(epoch)
            crawl_res = await self.step_search_crawl(rewrite_query)
            answer = await self.step_summarize_crawl_res(crawl_res)
            if 'yes' in answer:
                break
        return final_summary

class SearchCrawl:
    """搜索和爬取逻辑"""
    def __init__(self, topic, rewrite_query, summary_search):
        self.origin_query = topic
        self.rewrite_query = rewrite_query
        self.summary_search = summary_search
        self.all_searched_urls = []
        self.selected_urls = []
```

**优势**：
- 职责清晰：DeepSearch 管流程，SearchCrawl 管搜索爬取
- 状态管理：类属性自动维护状态
- 易于扩展和测试

---

#### 3. **取消事件监听优化** ⭐⭐⭐

**问题**：当前只在关键点检查，可能不够及时

**参考项目的方案**：
```python
class DeepSearch:
    def __init__(self, ..., cancel_event=None):
        self.cancel_event = cancel_event

    def watch_cancel_event(self):
        """在每个步骤前调用"""
        if self.cancel_event and self.cancel_event.is_set():
            self.logger.info("收到取消请求，开始任务取消！")
            raise asyncio.CancelledError()

    async def step_formulate_query(self, epoch):
        self.watch_cancel_event()  # 检查取消
        # ... 执行逻辑

    async def step_search_crawl(self, rewrite_query):
        self.watch_cancel_event()  # 检查取消
        # ... 执行逻辑
```

**优势**：
- 更细粒度的取消检查
- 专门的监听方法，代码清晰
- 支持外部 cancel_event

---

#### 4. **详细的性能统计** ⭐⭐⭐

**问题**：当前日志不够详细

**参考项目的方案**：
```python
async def step_formulate_query(self, epoch):
    tmp_start_time = time.time()
    rewrite_query = await formulate_query(...)
    self.logger.info(f'拆解 topic 耗时：{time.time() - tmp_start_time}s')
    return rewrite_query

async def step_search_crawl(self, rewrite_query):
    tmp_start_time = time.time()
    crawl_res = await self.search_crawl.run()
    self.logger.info(f'搜索爬取耗时：{time.time() - tmp_start_time}s')
    return crawl_res
```

**优势**：
- 每个步骤的耗时清晰可见
- 便于性能分析和优化
- 便于监控和告警

---

#### 5. **最终报告质量要求** ⭐⭐⭐⭐

**问题**：当前 final_summary prompt 没有明确字数和质量要求

**参考项目的要求**：
```python
final_summary_prompt = """
# 任务
需要你根据信息围绕主题进行总结。主题：`{topic}`

# 工作流
1、仔细阅读所有信息，结合主题阅读理解，充分理解上下文。
2、选出跟主题相关的内容，对选出内容进行总结。
3、如果主题是问题类的，需要总结推理出相关答案，否则正常根据主题进行总结即可。
4、在撰写对比内容时，如果缺少某方面信息，必须明确说明"目前暂无XX相关资料"。

# 要求
- 要求字数不能少于 3500 字，必须尽可能多。
- 总结的内容必须是信息里面的内容，不能自己发挥，尤其是时间之类的信息。
- 总结的内容必须要点足够全面。
- 逻辑连贯，语句通顺。
- 直接以 markdown 格式给出最后结果。

# 需要总结的信息
```{summary_search}```
"""
```

**优势**：
- 明确字数要求（3500+）
- 明确工作流步骤
- 处理信息缺失的情况
- 提高报告质量

---

#### 6. **错误处理和容错** ⭐⭐⭐

**参考项目的方案**：
```python
async def run(self):
    try:
        for epoch in range(self.max_epochs):
            try:
                # ... 每轮逻辑
            except asyncio.CancelledError:
                raise  # 继续向上抛出
            except Exception as e:
                self.logger.error(f"第 {epoch+1} 轮搜索出错，开始下一轮迭代！")
                self.logger.error(traceback.format_exc())
                continue  # 继续下一轮，不中断整个流程

        return final_summary
    except asyncio.CancelledError:
        self.logger.warning('接收到取消任务信号，停止任务！')
        llm.cancel_request()  # 取消 LLM 请求
        raise
    finally:
        self.logger.warning('任务结束，搜索爬虫停止！')
```

**优势**：
- 单轮失败不影响整体流程
- 正确处理取消信号
- 完整的 try-except-finally

---

## 🚀 优化实施方案

### 方案 A: 最小改动（推荐）

**只优化关键点，保持现有架构**

1. ✅ 添加 URL 去重机制
2. ✅ 优化取消检查
3. ✅ 增强日志（性能统计）
4. ✅ 改进 final_summary prompt

**优势**：
- 改动小，风险低
- 与 LangGraph 集成不受影响
- 立即可用

**代码位置**：`agent/deepsearch.py`

---

### 方案 B: 重构（可选）

**完全 OOP 重构，参考项目架构**

1. ✅ 创建 DeepSearch 类
2. ✅ 创建 SearchCrawl 类
3. ✅ 添加所有优化点

**优势**：
- 代码结构更清晰
- 易于维护和扩展
- 状态管理更好

**挑战**：
- 需要调整 LangGraph 集成
- 改动较大，需要充分测试

---

## 📝 具体实施步骤（方案 A）

### Step 1: 添加 URL 去重

```python
# agent/deepsearch.py

def run_deepsearch(state, config):
    # 添加 URL 追踪
    all_searched_urls = []
    selected_urls = []

    for epoch in range(max_epochs):
        # ... 搜索

        # 去重逻辑
        for r in combined_results:
            url = r.get("url")
            if url and url not in all_searched_urls:
                all_searched_urls.append(url)

        # 筛选 URL 时排除已选择的
        available_results = [
            r for r in combined_results
            if r.get("url") not in selected_urls
        ]

        chosen_urls = _pick_relevant_urls(..., available_results, ...)
        selected_urls.extend(chosen_urls)
```

### Step 2: 增强性能日志

```python
def run_deepsearch(state, config):
    for epoch in range(max_epochs):
        epoch_start = time.time()

        # 生成查询
        query_start = time.time()
        queries = _generate_queries(...)
        logger.info(f"[Epoch {epoch+1}] 查询生成耗时: {time.time()-query_start:.2f}s")

        # 搜索
        search_start = time.time()
        results = ...
        logger.info(f"[Epoch {epoch+1}] 搜索耗时: {time.time()-search_start:.2f}s")

        # 爬取
        crawl_start = time.time()
        ...
        logger.info(f"[Epoch {epoch+1}] 爬取耗时: {time.time()-crawl_start:.2f}s")

        logger.info(f"[Epoch {epoch+1}] 总耗时: {time.time()-epoch_start:.2f}s")
```

### Step 3: 改进 final_summary prompt

```python
# prompts/templates/deepsearch/final_summary.py

final_summary_prompt = """
# 任务
需要你根据信息围绕主题进行深度总结。主题：`{topic}`

# 工作流
1. 仔细阅读所有信息，结合主题阅读理解，充分理解上下文
2. 选出跟主题相关的内容，对选出内容进行总结
3. 如果主题是问题类的，需要总结推理出相关答案
4. 对比类主题：如果缺少某方面信息，必须明确说明"目前暂无XX相关资料"

# 要求
- **字数要求**：不少于 3500 字，尽可能详细全面
- **内容准确**：总结内容必须基于提供的信息，不得自己发挥或创造事实
- **要点全面**：必须涵盖主题的所有关键方面
- **逻辑清晰**：结构合理，层次分明，逻辑连贯
- **格式规范**：使用 Markdown 格式，包含标题、列表、引用等
- **引用来源**：在文末列出"参考来源"部分

# 需要总结的信息
```{summary_search}```
"""
```

### Step 4: 优化错误处理

```python
def run_deepsearch(state, config):
    try:
        for epoch in range(max_epochs):
            try:
                _check_cancel(state)

                # ... 执行逻辑

            except asyncio.CancelledError:
                raise  # 继续向上抛出
            except Exception as e:
                logger.error(f"Epoch {epoch+1} 失败: {e}", exc_info=True)
                continue  # 继续下一轮

        return {
            "final_report": final_report,
            # ...
        }
    except asyncio.CancelledError as e:
        logger.warning("DeepSearch 被取消")
        return handle_cancellation(state, e)
```

---

## 📈 预期效果

实施优化后，预期达到：

1. **性能提升**：
   - 避免重复爬取，节省 20-30% 时间
   - 更详细的性能日志，便于优化瓶颈

2. **质量提升**：
   - 更严格的报告要求，字数增加 50%+
   - 信息多样性提高（URL 去重）

3. **稳定性提升**：
   - 单轮失败不影响整体流程
   - 更好的取消机制

4. **可维护性提升**：
   - 详细的日志便于调试
   - 清晰的错误处理

---

## 🔍 对比总结

| 维度 | 当前实现 | 参考项目 | 优化后 |
|------|---------|---------|--------|
| **Prompt 质量** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **URL 去重** | ❌ | ✅ | ✅ |
| **OOP 封装** | ❌ | ✅ | ⚠️（可选） |
| **取消机制** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **性能日志** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **报告质量** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **错误处理** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **LangGraph 集成** | ⭐⭐⭐⭐⭐ | ❌ | ⭐⭐⭐⭐⭐ |

---

## 💾 实施建议

1. **优先级排序**：
   - P0: URL 去重（效果最明显）
   - P1: 性能日志（立即可用）
   - P1: Final Summary Prompt（提高质量）
   - P2: 错误处理优化
   - P3: OOP 重构（可选）

2. **测试验证**：
   - 在测试环境先验证 URL 去重效果
   - 对比优化前后的报告质量
   - 监控性能变化

3. **灰度发布**：
   - 先在部分场景使用优化版本
   - 收集反馈后全量上线

---

是否需要我直接实现优化版本的代码？
