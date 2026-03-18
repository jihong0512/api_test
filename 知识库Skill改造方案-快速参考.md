# 知识库Skill改造方案 - 快速参考

> 基于Function Calling/Tool Calling技术的改造方案（无需修改核心代码）

---

## 一、四个改造方案速览

| 方案 | 核心思想 | 实施难度 | 效果 | 推荐度 |
|------|---------|---------|------|--------|
| **方案一：Function Calling** | LLM直接调用知识库工具 | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **方案二：Structured Outputs** | 使用Pydantic确保输出格式 | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **方案三：ReAct模式** | 推理+行动，自主决策 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **方案四：Agentic RAG** | 智能路由选择检索策略 | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## 二、方案一：Function Calling（最推荐）

### 核心架构

```
LLM → Function Calling Layer → 现有服务（无需修改）
```

### 实施步骤

1. **新建文件**: `backend/app/services/function_tools.py`
   - 定义Function工具（search_knowledge_base, query_knowledge_graph等）

2. **新建文件**: `backend/app/services/function_executor.py`
   - 将Function调用映射到现有服务

3. **修改**: `backend/app/services/llm_service.py`
   - 添加`chat_with_tools()`方法支持Function Calling

### 优势
- ✅ LLM自主决定何时调用工具
- ✅ 无需修改VectorService、RAGService等核心代码
- ✅ 支持多轮工具调用

### 代码示例

```python
# Function定义
FUNCTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "从知识库中检索相关文档",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "project_id": {"type": "integer"},
                    "top_k": {"type": "integer", "default": 10}
                }
            }
        }
    }
]

# 使用
response = await llm_service.chat_with_tools(
    prompt="帮我找登录接口的信息",
    tools=FUNCTION_TOOLS,
    function_executor=function_executor
)
```

---

## 三、方案二：Structured Outputs

### 核心思想
使用Pydantic模型确保LLM输出格式稳定

### 实施步骤

1. **新建文件**: `backend/app/services/structured_models.py`
   - 定义Pydantic模型（InterfaceInfo, TestCaseInfo等）

2. **修改**: `backend/app/services/llm_service.py`
   - 添加`chat_with_structure()`方法

### 优势
- ✅ 输出格式稳定，减少JSON解析错误
- ✅ 自动类型验证
- ✅ 更好的IDE支持

### 代码示例

```python
class InterfaceInfo(BaseModel):
    name: str
    method: str
    url: str
    params: Dict[str, Any]

# 使用
result = await llm_service.chat_with_structure(
    prompt="解析这个接口...",
    response_model=InterfaceInfo
)
# result自动是InterfaceInfo类型，无需JSON解析
```

---

## 四、方案三：ReAct模式

### 核心思想
让Agent能够推理（Thought）和行动（Action）

### 流程

```
Thought → Action → Observation → Thought → ... → Final Answer
```

### 实施步骤

1. **新建文件**: `backend/app/services/react_agent.py`
   - 实现ReAct循环逻辑

2. **集成**: 在现有Agent中使用

### 优势
- ✅ 支持复杂多步骤推理
- ✅ 更接近人类思考过程

---

## 五、方案四：Agentic RAG

### 核心思想
智能路由，自动选择最合适的检索策略

### 路由策略

```
简单查询 → 向量检索
关键词查询 → 混合检索
关系查询 → 知识图谱
复杂查询 → ReAct模式
```

### 实施步骤

1. **新建文件**: `backend/app/services/rag_router.py`
   - 实现查询路由逻辑

2. **修改**: `backend/app/services/rag_service.py`
   - 添加`intelligent_search()`方法

### 优势
- ✅ 自动选择最优检索策略
- ✅ 提升检索准确性和效率

---

## 六、推荐实施路径

### 阶段一（1-2周）：快速见效
1. ✅ **方案二：Structured Outputs** - 稳定输出格式
2. ✅ **方案一：Function Calling** - 工具调用能力

### 阶段二（2-4周）：能力增强
3. ✅ **方案四：Agentic RAG** - 智能路由
4. ✅ **方案三：ReAct模式** - 复杂任务处理

---

## 七、关键优势

### 无需修改核心代码
- ✅ 所有方案都是**新增文件**
- ✅ 通过包装器模式接入现有服务
- ✅ 保持向后兼容

### 快速集成
- ✅ 最小改动即可接入
- ✅ 不影响现有功能
- ✅ 可以逐步实施

---

## 八、技术栈对比

| 技术 | 当前项目 | 改造后 |
|------|---------|--------|
| **Agent框架** | LangGraph | LangGraph + Function Calling |
| **输出格式** | JSON解析 | Pydantic结构化输出 |
| **工具调用** | Prompt方式 | Function Calling |
| **检索策略** | 固定策略 | 智能路由（Agentic RAG） |
| **推理能力** | 单步推理 | ReAct多步推理 |

---

## 九、快速开始

### 最小实施（方案一 + 方案二）

1. 创建Function定义文件
2. 创建Function执行器
3. 添加Structured Outputs支持
4. 修改LLMService支持Function Calling

**预计工作量**: 2-3天
**效果**: 显著提升工具调用准确性和输出稳定性

---

## 十、注意事项

### 性能
- Function Calling会增加API调用次数（需要缓存）
- 建议添加Redis缓存层

### 成本
- Function Calling会增加Token消耗
- 建议设置调用次数限制

### 兼容性
- 所有方案保持向后兼容
- 可以逐步迁移

---

**总结**: 优先实施方案一（Function Calling）和方案二（Structured Outputs），这两个方案投入小、见效快，可以快速提升系统能力。
