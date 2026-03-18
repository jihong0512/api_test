# 知识库Skill改造方案

> 基于当前热门的Function Calling/Tool Calling技术，提供多个无需修改核心代码的改造方案

---

## 一、当前技术趋势分析

### 1.1 热门技术方向

| 技术 | 说明 | 代表厂商 |
|------|------|---------|
| **Function Calling** | LLM直接调用预定义工具 | OpenAI, Anthropic |
| **Structured Outputs** | 使用Pydantic确保输出格式 | OpenAI, DeepSeek |
| **ReAct模式** | Reasoning + Acting，推理+行动 | LangChain, AutoGPT |
| **Tool Use** | 多工具协同调用 | Claude, GPT-4 |
| **Agentic RAG** | 智能路由和工具选择 | LangGraph, CrewAI |

### 1.2 项目现状

✅ **已有基础**:
- LangGraph多Agent架构
- 混合RAG检索系统
- 知识库（ChromaDB + Neo4j）

❌ **待改进**:
- Agent使用传统prompt方式，未使用Function Calling
- 输出格式依赖JSON解析，不够稳定
- 工具调用需要手动编写prompt

---

## 二、改造方案（无需修改核心代码）

### 方案一：Function Calling改造（推荐⭐⭐⭐⭐⭐）

**核心思想**: 将现有的RAG检索、知识图谱查询等能力封装为Function，让LLM直接调用

#### 架构设计

```
┌─────────────────────────────────────────────────────────┐
│               Function Calling架构                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  LLM (DeepSeek/OpenAI)                                  │
│    ↓                                                     │
│  Function Calling Layer (新增)                           │
│    ├── search_knowledge_base()                          │
│    ├── query_knowledge_graph()                         │
│    ├── analyze_dependencies()                          │
│    └── generate_test_case()                            │
│    ↓                                                     │
│  现有服务层（无需修改）                                   │
│    ├── VectorService                                    │
│    ├── HybridRAGService                                 │
│    └── DatabaseService                                  │
└─────────────────────────────────────────────────────────┘
```

#### 实施步骤

**步骤1**: 创建Function定义层（新建文件）

```python
# backend/app/services/function_tools.py (新建)

from typing import List, Dict, Any
from pydantic import BaseModel, Field

class SearchKnowledgeBaseInput(BaseModel):
    """知识库检索工具输入"""
    query: str = Field(description="检索查询内容")
    project_id: int = Field(description="项目ID")
    top_k: int = Field(default=10, description="返回结果数量")

class QueryKnowledgeGraphInput(BaseModel):
    """知识图谱查询工具输入"""
    query: str = Field(description="图谱查询内容")
    project_id: int = Field(description="项目ID")
    relationship_type: str = Field(default="all", description="关系类型")

class AnalyzeDependenciesInput(BaseModel):
    """依赖分析工具输入"""
    interface_names: List[str] = Field(description="接口名称列表")
    project_id: int = Field(description="项目ID")

# Function定义
FUNCTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "从知识库中检索相关文档和接口信息，支持语义检索和关键词检索",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索查询内容，例如：'登录接口的参数有哪些'"
                    },
                    "project_id": {
                        "type": "integer",
                        "description": "项目ID"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认10",
                        "default": 10
                    }
                },
                "required": ["query", "project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_knowledge_graph",
            "description": "从知识图谱中查询接口依赖关系、数据流关系等",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "查询内容，例如：'登录接口依赖哪些接口'"
                    },
                    "project_id": {
                        "type": "integer",
                        "description": "项目ID"
                    },
                    "relationship_type": {
                        "type": "string",
                        "description": "关系类型：call_dependency, data_dependency, business_dependency",
                        "enum": ["all", "call_dependency", "data_dependency", "business_dependency"]
                    }
                },
                "required": ["query", "project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_dependencies",
            "description": "分析接口之间的依赖关系，包括调用依赖、数据依赖等",
            "parameters": {
                "type": "object",
                "properties": {
                    "interface_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "需要分析的接口名称列表"
                    },
                    "project_id": {
                        "type": "integer",
                        "description": "项目ID"
                    }
                },
                "required": ["interface_names", "project_id"]
            }
        }
    }
]
```

**步骤2**: 创建Function执行层（新建文件）

```python
# backend/app/services/function_executor.py (新建)

from typing import Dict, Any, List
from app.services.rag_service import HybridRAGService
from app.services.db_service import DatabaseService
from app.services.vector_service import VectorService

class FunctionExecutor:
    """Function执行器，将Function调用映射到现有服务"""
    
    def __init__(self):
        self.rag_service = HybridRAGService()
        self.db_service = DatabaseService()
        self.vector_service = VectorService()
    
    async def search_knowledge_base(
        self,
        query: str,
        project_id: int,
        top_k: int = 10
    ) -> Dict[str, Any]:
        """执行知识库检索"""
        results = await self.rag_service.hybrid_search(
            query=query,
            project_id=project_id,
            top_k=top_k,
            use_rerank=True
        )
        
        return {
            "results": [
                {
                    "text": r.get("text", ""),
                    "score": r.get("score", 0),
                    "metadata": r.get("metadata", {})
                }
                for r in results
            ],
            "count": len(results)
        }
    
    async def query_knowledge_graph(
        self,
        query: str,
        project_id: int,
        relationship_type: str = "all"
    ) -> Dict[str, Any]:
        """执行知识图谱查询"""
        # 使用现有的GraphRAG能力
        results = await self.rag_service.graph_rag_search(
            query=query,
            project_id=project_id,
            top_k=10
        )
        
        return {
            "graph_context": results.get("graph_context", ""),
            "relationships": results.get("graph_results", [])
        }
    
    async def analyze_dependencies(
        self,
        interface_names: List[str],
        project_id: int
    ) -> Dict[str, Any]:
        """执行依赖分析"""
        # 调用现有的依赖分析服务（通过现有接口）
        # 这里可以调用现有的API或服务
        return {
            "dependencies": [],
            "analysis": "依赖分析结果"
        }
```

**步骤3**: 修改LLMService支持Function Calling（最小改动）

```python
# 在 backend/app/services/llm_service.py 中添加新方法

async def chat_with_tools(
    self,
    prompt: str,
    tools: List[Dict[str, Any]],
    function_executor: Any,  # FunctionExecutor实例
    temperature: float = 0.7
) -> Dict[str, Any]:
    """支持Function Calling的对话"""
    messages = [{"role": "user", "content": prompt}]
    
    # 调用LLM，传入tools定义
    response = self.client.chat.completions.create(
        model=self.model,
        messages=messages,
        tools=tools,  # 传入Function定义
        tool_choice="auto",  # 让LLM自动选择工具
        temperature=temperature
    )
    
    message = response.choices[0].message
    
    # 如果LLM要求调用Function
    if message.tool_calls:
        messages.append(message)
        
        # 执行Function调用
        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            # 调用Function执行器
            if function_name == "search_knowledge_base":
                result = await function_executor.search_knowledge_base(**function_args)
            elif function_name == "query_knowledge_graph":
                result = await function_executor.query_knowledge_graph(**function_args)
            elif function_name == "analyze_dependencies":
                result = await function_executor.analyze_dependencies(**function_args)
            else:
                result = {"error": f"Unknown function: {function_name}"}
            
            # 将Function执行结果返回给LLM
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False)
            })
        
        # 再次调用LLM，让它基于Function结果生成最终答案
        final_response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=temperature
        )
        
        return {
            "content": final_response.choices[0].message.content,
            "tool_calls": [tc.function.name for tc in message.tool_calls],
            "function_results": result
        }
    
    return {"content": message.content}
```

**优势**:
- ✅ 无需修改现有VectorService、RAGService等核心代码
- ✅ LLM可以自主决定何时调用哪个工具
- ✅ 更准确的工具调用，减少prompt工程
- ✅ 支持多轮工具调用

**适用场景**:
- 测试用例生成时自动检索相关文档
- 接口解析时自动查询知识图谱
- 依赖分析时自动调用多个工具

---

### 方案二：Structured Outputs改造（推荐⭐⭐⭐⭐）

**核心思想**: 使用Pydantic模型确保LLM输出格式稳定，减少JSON解析错误

#### 实施步骤

**步骤1**: 定义Pydantic模型（新建文件）

```python
# backend/app/services/structured_models.py (新建)

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class InterfaceInfo(BaseModel):
    """接口信息模型"""
    name: str = Field(description="接口名称")
    method: str = Field(description="HTTP方法")
    url: str = Field(description="接口URL")
    description: Optional[str] = Field(default="", description="接口描述")
    params: Dict[str, Any] = Field(default_factory=dict, description="请求参数")
    headers: Dict[str, Any] = Field(default_factory=dict, description="请求头")
    body: Optional[Dict[str, Any]] = Field(default=None, description="请求体")
    response_schema: Optional[Dict[str, Any]] = Field(default=None, description="响应结构")

class DependencyInfo(BaseModel):
    """依赖信息模型"""
    source: str = Field(description="源接口")
    target: str = Field(description="目标接口")
    dependency_type: str = Field(description="依赖类型")
    data_flow: Optional[str] = Field(default=None, description="数据流")

class TestCaseInfo(BaseModel):
    """测试用例信息模型"""
    name: str = Field(description="测试用例名称")
    type: str = Field(description="测试类型：normal/boundary/exception")
    description: str = Field(description="测试描述")
    test_data: Dict[str, Any] = Field(description="测试数据")
    assertions: List[Dict[str, Any]] = Field(description="断言列表")
    dependencies: List[str] = Field(default_factory=list, description="依赖的接口")
```

**步骤2**: 修改LLMService支持Structured Outputs

```python
# 在 backend/app/services/llm_service.py 中添加

async def chat_with_structure(
    self,
    prompt: str,
    response_model: BaseModel,  # Pydantic模型
    temperature: float = 0.3
) -> BaseModel:
    """使用Structured Outputs调用LLM"""
    
    # 如果LLM支持structured_outputs（如OpenAI）
    if hasattr(self.client.chat.completions, 'create'):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},  # 或使用response_model
            temperature=temperature
        )
        
        result = json.loads(response.choices[0].message.content)
        return response_model(**result)
    
    # 降级方案：使用prompt + JSON解析
    prompt_with_schema = f"""
{prompt}

请严格按照以下JSON Schema格式输出：
{response_model.model_json_schema()}

只输出JSON，不要其他内容：
"""
    result = await self.chat(prompt_with_schema, temperature=temperature)
    parsed = json.loads(result)
    return response_model(**parsed)
```

**优势**:
- ✅ 输出格式稳定，减少解析错误
- ✅ 自动验证数据类型
- ✅ 更好的IDE支持（类型提示）

**适用场景**:
- 接口解析结果结构化
- 测试用例生成结果结构化
- 依赖分析结果结构化

---

### 方案三：ReAct模式改造（推荐⭐⭐⭐）

**核心思想**: 让Agent能够推理（Reasoning）和行动（Acting），自主决定使用哪些工具

#### 架构设计

```
┌─────────────────────────────────────────────────────────┐
│              ReAct模式架构                                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Thought: 我需要检索登录接口的信息                        │
│    ↓                                                     │
│  Action: search_knowledge_base(query="登录接口")         │
│    ↓                                                     │
│  Observation: 检索到3个相关文档                           │
│    ↓                                                     │
│  Thought: 现在我需要分析这些接口的依赖关系                │
│    ↓                                                     │
│  Action: query_knowledge_graph(...)                     │
│    ↓                                                     │
│  Observation: 找到2个依赖关系                             │
│    ↓                                                     │
│  Final Answer: 基于检索结果生成测试用例                  │
└─────────────────────────────────────────────────────────┘
```

#### 实施步骤

**步骤1**: 创建ReAct Agent包装器（新建文件）

```python
# backend/app/services/react_agent.py (新建)

from typing import Dict, Any, List
from app.services.llm_service import LLMService
from app.services.function_executor import FunctionExecutor
from app.services.function_tools import FUNCTION_TOOLS

class ReActAgent:
    """ReAct模式Agent"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.function_executor = FunctionExecutor()
        self.max_iterations = 5
    
    async def run(
        self,
        task: str,
        project_id: int
    ) -> Dict[str, Any]:
        """执行ReAct循环"""
        history = []
        
        for i in range(self.max_iterations):
            # 构建当前状态
            state_prompt = self._build_state_prompt(task, history)
            
            # 调用LLM，让它决定下一步行动
            response = await self.llm_service.chat_with_tools(
                prompt=state_prompt,
                tools=FUNCTION_TOOLS,
                function_executor=self.function_executor
            )
            
            # 解析LLM的响应（Thought + Action）
            thought, action = self._parse_response(response)
            history.append({"thought": thought, "action": action})
            
            # 如果LLM决定结束，返回最终答案
            if action.get("type") == "final_answer":
                return {
                    "answer": action.get("content"),
                    "reasoning_steps": history
                }
            
            # 执行Action
            observation = await self._execute_action(action, project_id)
            history.append({"observation": observation})
        
        return {
            "answer": "达到最大迭代次数",
            "reasoning_steps": history
        }
    
    def _build_state_prompt(self, task: str, history: List[Dict]) -> str:
        """构建状态提示词"""
        prompt = f"""
任务：{task}

历史记录：
"""
        for step in history:
            if "thought" in step:
                prompt += f"Thought: {step['thought']}\n"
            if "action" in step:
                prompt += f"Action: {step['action']}\n"
            if "observation" in step:
                prompt += f"Observation: {step['observation']}\n"
        
        prompt += """
请按照ReAct模式思考：
1. Thought: 分析当前情况，决定下一步行动
2. Action: 选择要调用的工具（search_knowledge_base, query_knowledge_graph等）
3. Observation: 观察工具执行结果
4. 重复直到可以给出最终答案

可用工具：
- search_knowledge_base: 检索知识库
- query_knowledge_graph: 查询知识图谱
- analyze_dependencies: 分析依赖关系

请开始思考：
"""
        return prompt
```

**优势**:
- ✅ Agent可以自主推理和行动
- ✅ 支持多步骤问题解决
- ✅ 更接近人类思考过程

**适用场景**:
- 复杂的测试用例生成任务
- 需要多步骤推理的接口分析
- 跨多个知识源的查询

---

### 方案四：Agentic RAG改造（推荐⭐⭐⭐⭐⭐）

**核心思想**: 让RAG系统能够智能路由，自动选择最合适的检索策略

#### 架构设计

```
┌─────────────────────────────────────────────────────────┐
│            Agentic RAG架构                               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  用户查询                                                │
│    ↓                                                     │
│  查询分类Agent (新增)                                     │
│    ├── 简单查询 → 直接向量检索                           │
│    ├── 复杂查询 → 混合检索                               │
│    ├── 关系查询 → 知识图谱                               │
│    └── 多步骤查询 → ReAct模式                            │
│    ↓                                                     │
│  现有检索服务（无需修改）                                 │
└─────────────────────────────────────────────────────────┘
```

#### 实施步骤

**步骤1**: 创建查询路由Agent（新建文件）

```python
# backend/app/services/rag_router.py (新建)

from typing import Dict, Any, Literal
from app.services.llm_service import LLMService

class RAGRouter:
    """RAG智能路由"""
    
    def __init__(self):
        self.llm_service = LLMService()
    
    async def route(
        self,
        query: str,
        project_id: int
    ) -> Dict[str, Any]:
        """路由查询到最合适的检索策略"""
        
        routing_prompt = f"""
分析以下查询，决定最合适的检索策略：

查询：{query}

可选策略：
1. vector_only: 简单语义查询，直接使用向量检索
2. hybrid: 需要关键词匹配的查询，使用混合检索
3. graph: 需要查询关系的查询，使用知识图谱
4. react: 复杂多步骤查询，使用ReAct模式

请返回JSON格式：
{{
    "strategy": "vector_only|hybrid|graph|react",
    "reason": "选择该策略的原因",
    "refined_query": "优化后的查询（如果需要）"
}}
"""
        
        result = await self.llm_service.chat_with_structure(
            prompt=routing_prompt,
            response_model=RoutingDecision  # Pydantic模型
        )
        
        return {
            "strategy": result.strategy,
            "reason": result.reason,
            "refined_query": result.refined_query
        }
```

**步骤2**: 在现有RAGService中添加路由层（最小改动）

```python
# 在 backend/app/services/rag_service.py 中添加

from app.services.rag_router import RAGRouter

class HybridRAGService:
    def __init__(self):
        # ... 现有代码 ...
        self.router = RAGRouter()  # 新增
    
    async def intelligent_search(
        self,
        query: str,
        project_id: int,
        top_k: int = 10
    ) -> Dict[str, Any]:
        """智能检索：自动选择检索策略"""
        
        # 1. 路由决策
        routing = await self.router.route(query, project_id)
        strategy = routing["strategy"]
        
        # 2. 根据策略执行检索
        if strategy == "vector_only":
            results = await self.vector_service.search(
                query=routing["refined_query"],
                top_k=top_k,
                use_rerank=False
            )
        elif strategy == "hybrid":
            results = await self.hybrid_search(
                query=routing["refined_query"],
                project_id=project_id,
                top_k=top_k
            )
        elif strategy == "graph":
            results = await self.graph_rag_search(
                query=routing["refined_query"],
                project_id=project_id,
                top_k=top_k
            )
        elif strategy == "react":
            # 使用ReAct Agent
            from app.services.react_agent import ReActAgent
            agent = ReActAgent()
            results = await agent.run(query, project_id)
        
        return {
            "strategy": strategy,
            "reason": routing["reason"],
            "results": results
        }
```

**优势**:
- ✅ 自动选择最优检索策略
- ✅ 提高检索准确性和效率
- ✅ 无需修改现有检索服务

**适用场景**:
- 用户查询自动路由
- 不同查询类型自动优化
- 提升整体检索性能

---

## 三、方案对比

| 方案 | 复杂度 | 效果 | 实施难度 | 推荐度 |
|------|--------|------|----------|--------|
| **方案一：Function Calling** | 中 | ⭐⭐⭐⭐⭐ | 低 | ⭐⭐⭐⭐⭐ |
| **方案二：Structured Outputs** | 低 | ⭐⭐⭐⭐ | 低 | ⭐⭐⭐⭐ |
| **方案三：ReAct模式** | 高 | ⭐⭐⭐⭐⭐ | 中 | ⭐⭐⭐ |
| **方案四：Agentic RAG** | 中 | ⭐⭐⭐⭐⭐ | 低 | ⭐⭐⭐⭐⭐ |

---

## 四、推荐实施路径

### 阶段一：快速见效（1-2周）
1. ✅ **方案二：Structured Outputs** - 先稳定输出格式
2. ✅ **方案一：Function Calling** - 让LLM能够调用工具

### 阶段二：能力增强（2-4周）
3. ✅ **方案四：Agentic RAG** - 智能路由提升检索
4. ✅ **方案三：ReAct模式** - 复杂任务处理

### 阶段三：优化完善（持续）
5. ✅ 性能优化
6. ✅ 错误处理增强
7. ✅ 监控和日志

---

## 五、实施注意事项

### 5.1 兼容性
- ✅ 所有方案都是**新增文件**，不修改现有核心代码
- ✅ 通过包装器模式接入现有服务
- ✅ 保持向后兼容

### 5.2 性能考虑
- ✅ Function Calling会增加API调用次数（需要缓存）
- ✅ ReAct模式可能增加延迟（需要设置最大迭代次数）
- ✅ 建议添加Redis缓存层

### 5.3 成本控制
- ✅ Function Calling会增加Token消耗
- ✅ 建议设置调用次数限制
- ✅ 使用缓存减少重复调用

---

## 六、总结

以上四个方案都是基于当前热门的Skill/Tool Calling技术，**无需修改现有核心代码**，通过新增服务层实现能力增强：

1. **Function Calling**: 让LLM直接调用知识库工具
2. **Structured Outputs**: 确保输出格式稳定
3. **ReAct模式**: 支持复杂推理任务
4. **Agentic RAG**: 智能路由提升检索效率

**建议优先实施方案一和方案二**，这两个方案投入小、见效快，可以快速提升系统能力。
