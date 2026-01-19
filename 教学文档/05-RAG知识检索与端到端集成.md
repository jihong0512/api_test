# RAG知识检索与端到端集成

## 📖 目录
1. [RAG系统概述](#rag系统概述)
2. [向量化和存储](#向量化和存储)
3. [混合检索](#混合检索)
4. [端到端流程集成](#端到端流程集成)
5. [最佳实践](#最佳实践)

---

## RAG系统概述

### 什么是RAG？

RAG 是 **Retrieval-Augmented Generation** 的缩写

```
┌──────────────────────────────────────────┐
│  用户查询                               │
│  (How to login with OAuth?)             │
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│  检索 (Retrieval)                       │
│  从向量数据库查找相关文档                 │
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│  增强 (Augmentation)                    │
│  将检索结果加入到LLM的上下文             │
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│  生成 (Generation)                      │
│  LLM基于上下文生成更准确的答案            │
└──────────────────────────────────────────┘
```

### 为什么使用RAG？

**问题场景**：
```
LLM训练数据可能过时，或者不了解特定项目的API文档细节
```

**解决方案**：
```
RAG允许LLM基于实时的项目文档来生成答案
确保答案的准确性和相关性
```

### 在接口测试中的应用

```
┌─────────────────────────────────────────┐
│  用户要求："生成登录接口的测试用例"     │
└──────────────┬──────────────────────────┘
               │
               ▼
        ┌──────────────────────────┐
        │ RAG检索                  │
        │ 找到登录接口的文档       │
        │ 相关的认证说明           │
        └──────────────┬───────────┘
                       │
                       ▼
    ┌──────────────────────────────────┐
    │ LLM生成                          │
    │ 基于检索到的接口文档              │
    │ 生成准确的测试用例代码             │
    └──────────────────────────────────┘
```

---

## 向量化和存储

### 向量化流程

```
文档内容
  │
  ├─→ 按块分割 (Chunking)
  │   (每个块~512字符)
  │
  ├─→ 向量化 (Embedding)
  │   (使用embedding模型)
  │   (输出向量: 768/1536维)
  │
  └─→ 存储到向量数据库
      (Milvus/ChromaDB)
```

### 示例代码

```python
from typing import List, Dict, Any
import numpy as np

class VectorService:
    """向量化和存储服务"""
    
    def __init__(self):
        # 初始化embedding模型
        from sentence_transformers import SentenceTransformer
        self.embedding_model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
        
        # 初始化向量数据库
        self.vector_db = MilvusDB()
    
    async def chunk_document(self, 
                            content: str, 
                            chunk_size: int = 512,
                            overlap: int = 50) -> List[str]:
        """
        将文档分块
        
        Args:
            content: 文档内容
            chunk_size: 每块大小（字符数）
            overlap: 块之间的重叠（避免信息丢失）
        """
        chunks = []
        start = 0
        
        while start < len(content):
            end = start + chunk_size
            chunk = content[start:end]
            chunks.append(chunk.strip())
            
            # 移动起始位置，保留重叠部分
            start = end - overlap
        
        return chunks
    
    async def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        文本向量化
        """
        # 使用embedding模型将文本转换为向量
        embeddings = self.embedding_model.encode(texts)
        return embeddings
    
    async def add_documents(self, 
                           project_id: int,
                           documents: List[Dict[str, Any]]):
        """
        添加文档到向量数据库
        """
        all_chunks = []
        all_embeddings = []
        all_metadata = []
        
        for doc in documents:
            content = doc.get("content", "")
            
            # 分块
            chunks = await self.chunk_document(content)
            
            # 向量化
            embeddings = await self.embed_texts(chunks)
            
            # 准备metadata
            for i, chunk in enumerate(chunks):
                metadata = {
                    "project_id": project_id,
                    "document_id": doc.get("id"),
                    "document_name": doc.get("name"),
                    "chunk_index": i,
                    "document_type": doc.get("type", "text")
                }
                
                all_chunks.append(chunk)
                all_embeddings.append(embeddings[i])
                all_metadata.append(metadata)
        
        # 批量存储到向量数据库
        await self.vector_db.insert(
            collection_name=f"project_{project_id}",
            documents=all_chunks,
            embeddings=all_embeddings,
            metadata=all_metadata
        )
    
    async def search(self, 
                    query: str, 
                    project_id: int,
                    top_k: int = 5) -> List[Dict[str, Any]]:
        """
        向量相似度搜索
        """
        # 对查询进行向量化
        query_embedding = self.embedding_model.encode([query])[0]
        
        # 在向量数据库中搜索
        results = await self.vector_db.search(
            collection_name=f"project_{project_id}",
            query_vector=query_embedding,
            top_k=top_k
        )
        
        # 格式化结果
        formatted_results = []
        for result in results:
            formatted_results.append({
                "text": result.get("document"),
                "score": float(result.get("score", 0)),
                "metadata": result.get("metadata", {})
            })
        
        return formatted_results
```

---

## 混合检索

### 检索方法对比

| 方法 | 优点 | 缺点 | 应用场景 |
|------|------|------|---------|
| **向量检索** | 语义理解强，支持语义搜索 | 参数配置复杂，速度较慢 | "如何实现登录" |
| **BM25** | 快速，关键词匹配准确 | 无法理解语义 | "找到status字段" |
| **混合** | 结合两种优点 | 需要重排序 | 综合场景（推荐） |

### 混合检索实现

```python
class HybridSearchService:
    """混合检索服务"""
    
    def __init__(self):
        self.vector_service = VectorService()
        self.bm25_service = BM25Service()
        self.reranker = RerankerService()
    
    async def hybrid_search(self, 
                           query: str,
                           project_id: int,
                           top_k: int = 10) -> List[Dict[str, Any]]:
        """
        混合检索：向量检索 + BM25 + 重排序
        """
        
        # 步骤1：并行执行向量检索和BM25
        vector_results, bm25_results = await asyncio.gather(
            self.vector_service.search(query, project_id, top_k=top_k),
            self.bm25_service.search(query, project_id, top_k=top_k)
        )
        
        # 步骤2：合并结果（去重）
        merged = self._merge_results(vector_results, bm25_results)
        
        # 步骤3：重排序
        reranked = await self.reranker.rerank(query, merged, top_k=top_k)
        
        return reranked
    
    def _merge_results(self, 
                      vector_results: List[Dict],
                      bm25_results: List[Dict]) -> List[Dict]:
        """
        合并向量检索和BM25的结果
        """
        merged = {}
        
        # 添加向量检索结果
        for result in vector_results:
            key = result["metadata"]["document_id"]
            if key not in merged:
                merged[key] = {
                    **result,
                    "vector_score": result["score"],
                    "bm25_score": 0
                }
        
        # 添加BM25结果
        for result in bm25_results:
            key = result["metadata"]["document_id"]
            if key in merged:
                merged[key]["bm25_score"] = result["score"]
            else:
                merged[key] = {
                    **result,
                    "vector_score": 0,
                    "bm25_score": result["score"]
                }
        
        # 转换为列表并返回
        return list(merged.values())


class RerankerService:
    """结果重排序服务"""
    
    async def rerank(self, 
                    query: str,
                    candidates: List[Dict],
                    top_k: int = 10) -> List[Dict]:
        """
        使用重排序模型对候选结果重新排序
        """
        from sentence_transformers import CrossEncoder
        
        # 初始化cross-encoder模型
        reranker = CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')
        
        # 计算查询和每个候选的相关性得分
        queries = [query] * len(candidates)
        passages = [c["text"] for c in candidates]
        
        scores = reranker.predict(list(zip(queries, passages)))
        
        # 添加重排序分数
        for i, candidate in enumerate(candidates):
            candidate["rerank_score"] = float(scores[i])
        
        # 按重排序分数排序
        reranked = sorted(
            candidates,
            key=lambda x: x["rerank_score"],
            reverse=True
        )
        
        return reranked[:top_k]
```

---

## 端到端流程集成

### 完整的工作流程

```python
class IntegrationService:
    """端到端流程集成"""
    
    def __init__(self):
        self.document_parser = DocumentParser()
        self.vector_service = VectorService()
        self.dependency_analyzer = DependencyAnalyzer()
        self.test_case_generator = TestCaseGenerator()
        self.rag_service = HybridRAGService()
    
    async def process_project(self, 
                             project_id: int,
                             documents: List[Dict]) -> Dict[str, Any]:
        """
        完整的项目处理流程
        """
        
        # 步骤1: 文档解析
        print("步骤1: 解析文档...")
        parsed_interfaces = []
        
        for doc in documents:
            interfaces = await self.document_parser.parse(
                doc["path"],
                doc["type"]
            )
            parsed_interfaces.extend(interfaces)
        
        # 步骤2: 向量化和存储
        print("步骤2: 向量化文档...")
        await self.vector_service.add_documents(
            project_id,
            [{"content": json.dumps(iface, ensure_ascii=False)} 
             for iface in parsed_interfaces]
        )
        
        # 步骤3: 依赖分析
        print("步骤3: 分析接口依赖...")
        dependencies = await self.dependency_analyzer.analyze(
            parsed_interfaces,
            project_id
        )
        
        # 步骤4: 生成测试用例
        print("步骤4: 生成测试用例...")
        test_cases = []
        
        for interface in parsed_interfaces:
            # 使用RAG检索相关上下文
            context = await self.rag_service.hybrid_search(
                f"测试{interface['name']}",
                project_id
            )
            
            # 生成用例
            test_case = await self.test_case_generator.generate(
                interface,
                dependencies=dependencies,
                rag_context=context
            )
            
            test_cases.append(test_case)
        
        return {
            "project_id": project_id,
            "interfaces_count": len(parsed_interfaces),
            "dependencies_count": len(dependencies),
            "test_cases": test_cases,
            "status": "completed"
        }
```

### 交互流程示例

```
用户上传API文档
    │
    ▼
DocumentParser.parse()
    ├─→ 识别文件格式
    ├─→ 提取内容
    └─→ LLM标准化
    │
    ▼ 得到: [接口1, 接口2, ...]
    │
    ├────────────────────────────┐
    │                            │
    ▼                            ▼
VectorService                DependencyAnalyzer
.add_documents()             .analyze()
    │                            │
    └───────────────┬────────────┘
                    │
                    ▼ 完成向量化和依赖分析
                    │
                    ├──────────────────────┐
                    │                      │
                    ▼                      ▼
            用户生成用例             RAGService
            触发生成               .hybrid_search()
                    │
                    ▼ 查询相关文档
                    │
            TestCaseGenerator
            .generate()
                    │
                    ├─→ 分析接口
                    ├─→ 检索RAG上下文
                    ├─→ 生成测试数据
                    ├─→ 用LLM生成代码
                    │
                    ▼
            返回可执行的测试代码
```

---

## 最佳实践

### ✅ RAG优化建议

1. **合理的文档分块**
   ```python
   # ❌ 太大：256字符
   # ❌ 太小：50字符
   # ✅ 合适：512字符，重叠50字符
   ```

2. **多粒度向量化**
   ```python
   # 不仅向量化文档块，也向量化：
   - 每个接口的完整信息
   - 接口描述+参数说明
   - 业务流程链
   ```

3. **结合多种检索方式**
   ```python
   # ✅ 使用混合检索而非单一方式
   - 向量检索（语义）
   - BM25（关键词）
   - 结构化查询（字段匹配）
   ```

4. **及时更新向量索引**
   ```python
   # 当文档更新时，重新向量化和存储
   if document_modified:
       await vector_service.update_document(doc_id, new_content)
   ```

### ⚠️ 常见陷阱

1. ❌ 忽视向量维度和检索速度的权衡
2. ❌ 文档分块过大导致语义混乱
3. ❌ 只使用向量检索，忽视关键词匹配
4. ❌ 重排序模型选择不当
5. ❌ 未定期更新向量索引

---

## 多Agent编排系统

### 系统架构概览

系统采用 **基于LangGraph的多Agent协调架构**，实现文档解析→依赖分析→用例生成的完整工作流：

```
┌──────────────────────────────────┐
│    用户输入                      │
│  (生成/补全/验证测试用例)       │
└────────────┬─────────────────────┘
             │
    ┌────────▼─────────┐
    │  MultiAgentOrchestrator
    │  (使用LangGraph编排)
    └────────┬─────────┘
             │
    ┌────────┴──────────────────┬───────────┬──────────┐
    │                           │           │          │
    ▼                           ▼           ▼          ▼
┌────────────┐         ┌────────────┐  ┌──────┐  ┌────┐
│Interface   │ Step 1  │Dependency  │  │Test  │  │END │
│ParserAgent │────────>│Analyzer    │→ │Case  │→ │    │
│            │         │Agent       │  │Gen   │  │    │
└────────────┘         └────────────┘  │Agent │  └────┘
                                       └──────┘
    全部由StateGraph管理工作流顺序和数据传递
```

### 核心Agent类

#### 1. InterfaceParserAgent - 接口解析Agent

```python
class InterfaceParserAgent:
    """接口解析Agent - 从用户任务中提取API接口信息"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.rag_service = HybridRAGService()
    
    async def parse(self, state: AgentState) -> AgentState:
        """
        解析用户请求中的接口信息
        
        流程：
        1. 从用户任务中理解需求
        2. 使用RAG检索相关接口文档
        3. 使用LLM提取和结构化接口信息
        """
        messages = state["messages"]
        current_task = state.get("current_task", "")
        project_id = state.get("project_id", 0)
        
        # Step 1: RAG检索相关文档
        rag_results = await self.rag_service.hybrid_search(
            current_task,
            project_id,
            top_k=5
        )
        
        context = "\n".join([r.get("text", "") for r in rag_results])
        
        # Step 2: 使用LLM提取接口信息
        prompt = f"""
        从以下上下文中提取API接口信息。
        
        任务：{current_task}
        相关文档：{context}
        
        请提取：接口名称、HTTP方法、URL、请求参数、响应格式
        """
        
        result = await self.llm_service.chat(prompt, temperature=0.3)
        
        try:
            parsed_data = json.loads(result)
            interfaces = parsed_data.get("interfaces", [])
        except:
            interfaces = []
        
        state["parsed_interfaces"] = interfaces
        state["context"]["parser_context"] = context
        
        return state
```

#### 2. DependencyAnalyzerAgent - 依赖分析Agent

```python
class DependencyAnalyzerAgent:
    """依赖分析Agent - 分析接口之间的调用依赖"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.db_service = DatabaseService()
    
    async def analyze(self, state: AgentState) -> AgentState:
        """
        分析接口之间的依赖关系
        
        分析维度：
        1. 调用依赖 - 哪些接口依赖其他接口
        2. 数据依赖 - 数据如何在接口间流动
        3. 业务依赖 - 接口的执行顺序约束
        4. 数据库依赖 - 接口与数据库表的关系
        """
        interfaces = state.get("parsed_interfaces", [])
        project_id = state.get("project_id", 0)
        
        if not interfaces:
            state["dependencies"] = {}
            return state
        
        # 获取数据库关系
        relationships = self.db_service.get_table_relationships(project_id)
        
        # 构建分析提示
        interfaces_json = json.dumps(interfaces, ensure_ascii=False, indent=2)
        relationships_json = json.dumps(relationships, ensure_ascii=False, indent=2)
        
        prompt = f"""
        分析以下接口的依赖关系。
        
        接口列表：{interfaces_json}
        数据库关系：{relationships_json}
        
        请分析：
        1. 接口调用依赖
        2. 数据流依赖
        3. 执行顺序
        4. 必需的前置步骤
        """
        
        result = await self.llm_service.chat(prompt, temperature=0.3)
        
        try:
            dependencies = json.loads(result)
        except:
            dependencies = {}
        
        state["dependencies"] = dependencies
        
        return state
```

#### 3. TestCaseGeneratorAgent - 用例生成Agent

```python
class TestCaseGeneratorAgent:
    """测试用例生成Agent - 为接口自动生成测试用例"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.rag_service = HybridRAGService()
    
    async def generate(self, state: AgentState) -> AgentState:
        """
        根据接口和依赖关系生成测试用例
        
        生成类型：
        1. 正常场景用例 - 成功路径
        2. 边界值用例 - 边界条件
        3. 异常场景用例 - 错误处理
        4. 依赖场景用例 - 需要前置步骤
        """
        interfaces = state.get("parsed_interfaces", [])
        dependencies = state.get("dependencies", {})
        project_id = state.get("project_id", 0)
        
        test_cases = []
        
        for interface in interfaces:
            # 为每个接口生成多个用例
            interface_json = json.dumps(interface, ensure_ascii=False, indent=2)
            
            prompt = f"""
            为以下API接口生成测试用例。
            
            接口信息：{interface_json}
            
            请生成：
            1. 正常场景用例（成功请求）
            2. 边界值用例（边界条件）
            3. 异常用例（错误处理）
            
            每个用例包含：测试名称、测试数据、期望结果、断言
            """
            
            result = await self.llm_service.chat(prompt, temperature=0.5)
            
            try:
                case_data = json.loads(result)
                test_cases.extend(case_data.get("test_cases", []))
            except:
                pass
        
        state["test_cases"] = test_cases
        
        return state
```

### MultiAgentOrchestrator - 工作流编排器

```python
class AgentState(TypedDict):
    """Agent工作流的状态定义"""
    messages: List[BaseMessage]          # 消息历史
    current_task: str                    # 当前任务
    parsed_interfaces: List[Dict]        # 解析后的接口
    dependencies: Dict[str, Any]         # 接口依赖
    test_cases: List[Dict[str, Any]]    # 生成的用例
    context: Dict[str, Any]              # 上下文信息
    project_id: int                      # 项目ID


class MultiAgentOrchestrator:
    """多Agent协调器 - 使用LangGraph管理工作流"""
    
    def __init__(self):
        self.parser_agent = InterfaceParserAgent()
        self.dependency_agent = DependencyAnalyzerAgent()
        self.testcase_agent = TestCaseGeneratorAgent()
        self.workflow = self._build_workflow()
    
    def _build_workflow(self) -> StateGraph:
        """构建LangGraph工作流"""
        workflow = StateGraph(AgentState)
        
        # 添加节点（Agent）
        workflow.add_node("parser", self._parser_node)
        workflow.add_node("dependency_analyzer", self._dependency_node)
        workflow.add_node("testcase_generator", self._testcase_node)
        
        # 定义流程边（数据流向）
        workflow.set_entry_point("parser")
        workflow.add_edge("parser", "dependency_analyzer")
        workflow.add_edge("dependency_analyzer", "testcase_generator")
        workflow.add_edge("testcase_generator", END)
        
        return workflow.compile()
    
    async def _parser_node(self, state: AgentState) -> AgentState:
        """解析节点"""
        return await self.parser_agent.parse(state)
    
    async def _dependency_node(self, state: AgentState) -> AgentState:
        """依赖分析节点"""
        return await self.dependency_agent.analyze(state)
    
    async def _testcase_node(self, state: AgentState) -> AgentState:
        """用例生成节点"""
        return await self.testcase_agent.generate(state)
    
    async def process(
        self,
        task: str,
        project_id: int,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        处理用户任务 - 完整的Agent工作流
        
        Args:
            task: 用户任务描述（如"生成登录接口的测试用例"）
            project_id: 项目ID
            initial_context: 初始上下文
        
        Returns:
            {
                "interfaces": [...],     # 解析的接口
                "dependencies": {...},   # 依赖关系
                "test_cases": [...]      # 生成的用例
            }
        """
        initial_state: AgentState = {
            "messages": [HumanMessage(content=task)],
            "current_task": task,
            "parsed_interfaces": [],
            "dependencies": {},
            "test_cases": [],
            "context": initial_context or {},
            "project_id": project_id
        }
        
        # 执行工作流（顺序：Parser → DependencyAnalyzer → TestCaseGenerator）
        final_state = await self.workflow.ainvoke(initial_state)
        
        return {
            "interfaces": final_state["parsed_interfaces"],
            "dependencies": final_state["dependencies"],
            "test_cases": final_state["test_cases"],
            "context": final_state["context"]
        }
```

### 使用示例

```python
# 初始化编排器
orchestrator = MultiAgentOrchestrator()

# 处理用户请求
result = await orchestrator.process(
    task="生成用户登录和获取用户信息接口的测试用例",
    project_id=1,
    initial_context={"test_level": "integration"}
)

# 结果
print("✅ 解析的接口：", len(result["interfaces"]))
print("✅ 接口依赖关系：", result["dependencies"])
print("✅ 生成的测试用例：", len(result["test_cases"]))

# 后续可将测试用例生成为可执行的Pytest代码
for case in result["test_cases"]:
    print(f"用例: {case['name']}")
    print(f"类型: {case['type']}")
    print(f"数据: {case['test_data']}")
```

---

## 完整数据流转：从数据准备到测试执行

### 数据准备阶段

**智能体4的职责**：确保测试能够正确执行，数据能够正确传递

#### 完整的Python实现代码

```python
import requests
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class TestCase:
    """测试用例数据类"""
    id: int
    name: str
    interface_id: int
    request_config: Dict[str, Any]
    extract_fields: List[str]  # 需要提取的响应字段

class TestExecutor:
    """测试执行引擎 - 处理拓扑排序和数据流转"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.extracted_data = {}  # 全局数据字典，用于存储跨用例的数据
    
    def replace_placeholders(self, config: Dict, extracted_data: Dict) -> Dict:
        """
        替换配置中的占位符
        {token} → 从extracted_data中取值
        """
        import re
        
        config_str = json.dumps(config)
        
        # 查找所有 {key} 模式的占位符
        placeholders = re.findall(r'\{([^}]+)\}', config_str)
        
        for placeholder in placeholders:
            if placeholder in extracted_data:
                value = extracted_data[placeholder]
                # 替换占位符
                config_str = config_str.replace(
                    f"{{{placeholder}}}",
                    json.dumps(value) if not isinstance(value, str) else value
                )
        
        return json.loads(config_str)
    
    def extract_response_fields(self, response: requests.Response, fields: List[str]) -> Dict:
        """
        从响应中提取指定字段
        """
        extracted = {}
        
        try:
            data = response.json()
        except:
            return extracted
        
        for field in fields:
            # 支持嵌套字段: "data.token" → 从 data['token']
            if "." in field:
                parts = field.split(".")
                value = data
                for part in parts:
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        value = None
                        break
                extracted[field] = value
            else:
                # 简单字段
                extracted[field] = data.get(field)
        
        return extracted
    
    def execute_test_case(self, 
                         case: TestCase,
                         test_data_config: Dict) -> Dict:
        """
        执行单个测试用例
        """
        print(f"\n▶️  执行用例: {case.name}")
        
        # 1️⃣ 准备请求配置（替换占位符）
        request = self.replace_placeholders(test_data_config, self.extracted_data)
        
        print(f"   请求: {request['method']} {request.get('url', request.get('path'))}")
        
        # 2️⃣ 发送请求
        try:
            if request["method"].upper() == "GET":
                response = self.session.get(request["url"])
            elif request["method"].upper() == "POST":
                response = self.session.post(
                    request["url"],
                    json=request.get("json"),
                    headers=request.get("headers", {})
                )
            elif request["method"].upper() == "PUT":
                response = self.session.put(
                    request["url"],
                    json=request.get("json"),
                    headers=request.get("headers", {})
                )
            else:
                response = None
            
            status_code = response.status_code if response else None
            print(f"   响应: {status_code}")
            
        except Exception as e:
            print(f"   ❌ 请求失败: {str(e)}")
            return {
                "case_id": case.id,
                "name": case.name,
                "success": False,
                "error": str(e)
            }
        
        # 3️⃣ 验证响应
        try:
            assert response.status_code == 200, f"HTTP {response.status_code}"
            data = response.json()
            assert data.get("code") == 0, f"API返回错误: {data.get('message')}"
            print(f"   ✅ 验证通过")
        except AssertionError as e:
            print(f"   ❌ 验证失败: {str(e)}")
            return {
                "case_id": case.id,
                "name": case.name,
                "success": False,
                "error": str(e)
            }
        
        # 4️⃣ 提取响应数据供后续用例使用
        extracted = self.extract_response_fields(response, case.extract_fields)
        
        for key, value in extracted.items():
            self.extracted_data[key] = value
            print(f"   💾 提取: {key} = {value}")
        
        return {
            "case_id": case.id,
            "name": case.name,
            "success": True,
            "extracted": extracted,
            "response": response.json()
        }
    
    def execute_all_test_cases(self, 
                               sorted_case_ids: List[int],
                               test_cases: Dict[int, TestCase],
                               test_data_config: Dict[int, Dict]) -> List[Dict]:
        """
        按顺序执行所有测试用例
        """
        print("=" * 60)
        print("🚀 开始执行测试用例")
        print("=" * 60)
        
        results = []
        
        for case_id in sorted_case_ids:
            case = test_cases[case_id]
            config = test_data_config[case_id]
            
            result = self.execute_test_case(case, config)
            results.append(result)
            
            # 如果用例失败且是关键用例，停止执行
            if not result["success"]:
                print(f"\n⚠️  关键用例失败，停止执行后续用例")
                break
        
        # 打印最终统计
        print("\n" + "=" * 60)
        print("📊 执行统计")
        print("=" * 60)
        success_count = sum(1 for r in results if r["success"])
        print(f"成功: {success_count}/{len(results)}")
        
        if success_count == len(results):
            print("✅ 所有用例执行成功！")
        else:
            print("❌ 有用例执行失败")
        
        return results


# ===== 使用示例 =====
if __name__ == "__main__":
    # 定义测试用例
    test_cases = {
        1: TestCase(
            id=1,
            name="登录",
            interface_id=101,
            request_config={
                "method": "POST",
                "url": "http://api.example.com/api/login",
                "json": {"username": "testuser", "password": "testpass123"}
            },
            extract_fields=["token", "userId"]
        ),
        2: TestCase(
            id=2,
            name="创建订单",
            interface_id=102,
            request_config={
                "method": "POST",
                "url": "http://api.example.com/api/order",
                "headers": {"Authorization": "Bearer {token}"},
                "json": {
                    "product_id": "P001",
                    "quantity": 1,
                    "userId": "{userId}"
                }
            },
            extract_fields=["orderId"]
        ),
        3: TestCase(
            id=3,
            name="查询订单",
            interface_id=103,
            request_config={
                "method": "GET",
                "url": "http://api.example.com/api/order/{orderId}",
                "headers": {"Authorization": "Bearer {token}"}
            },
            extract_fields=[]
        )
    }
    
    # 定义测试数据
    test_data_config = {
        1: test_cases[1].request_config,
        2: test_cases[2].request_config,
        3: test_cases[3].request_config
    }
    
    # 执行顺序（已通过拓扑排序确定）
    sorted_case_ids = [1, 2, 3]
    
    # 创建执行器并运行
    executor = TestExecutor(base_url="http://api.example.com")
    results = executor.execute_all_test_cases(sorted_case_ids, test_cases, test_data_config)
    
    # 打印详细结果
    print("\n" + "=" * 60)
    print("📋 详细结果")
    print("=" * 60)
    for result in results:
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"{status} - {result['name']}")
        if not result["success"]:
            print(f"    错误: {result['error']}")
        elif "extracted" in result:
            print(f"    提取数据: {result['extracted']}")
```

**运行结果示例**：
```
============================================================
🚀 开始执行测试用例
============================================================

▶️  执行用例: 登录
   请求: POST http://api.example.com/api/login
   响应: 200
   ✅ 验证通过
   💾 提取: token = abc123xyz
   💾 提取: userId = 42

▶️  执行用例: 创建订单
   请求: POST http://api.example.com/api/order
   响应: 201
   ✅ 验证通过
   💾 提取: orderId = order_456

▶️  执行用例: 查询订单
   请求: GET http://api.example.com/api/order/order_456
   响应: 200
   ✅ 验证通过

============================================================
📊 执行统计
============================================================
成功: 3/3
✅ 所有用例执行成功！

============================================================
📋 详细结果
============================================================
✅ PASS - 登录
    提取数据: {'token': 'abc123xyz', 'userId': 42}
✅ PASS - 创建订单
    提取数据: {'orderId': 'order_456'}
✅ PASS - 查询订单
```

**关键设计特点解析**：

```python
# 1️⃣ 占位符替换机制
extracted_data = {"token": "abc123", "userId": 42}
config = {
    "headers": {"Authorization": "Bearer {token}"},
    "json": {"userId": "{userId}"}
}
# 替换后：
# config = {
#     "headers": {"Authorization": "Bearer abc123"},
#     "json": {"userId": 42}
# }

# 2️⃣ 数据提取机制
response_data = {
    "code": 0,
    "data": {
        "token": "new_token",
        "userId": 99,
        "orderId": "order_789"
    }
}
extract_fields = ["token", "userId"]
# 提取结果：
# {"token": "new_token", "userId": 99}

# 3️⃣ 全局状态维护
self.extracted_data = {}
# Step 1 执行后: {"token": "abc123", "userId": 42}
# Step 2 执行后: {"token": "abc123", "userId": 42, "orderId": "order_456"}
# Step 3 执行: 使用所有这些数据
```

---

## 完整数据流转：从数据准备到测试执行

### 数据准备阶段

**智能体4的职责**：确保测试能够正确执行，数据能够正确传递

#### 阶段1：拓扑排序 + 执行顺序规划

```python
# 输入
test_cases = [
    TestCase(id=1, interface_id=101, name="登录"),
    TestCase(id=2, interface_id=102, name="创建订单"),
    TestCase(id=3, interface_id=103, name="查询订单")
]

dependency_graph = get_from_neo4j()  # 从Neo4j获取依赖图

# 执行拓扑排序
sorted_case_ids = topological_sort(test_cases, dependency_graph)
# 结果: [1, 2, 3]

# 输出
execution_order = [1, 2, 3]  # 确保这个顺序执行
```

#### 阶段2：测试数据方案规划

```python
# 规划每个用例的测试数据

test_data_config = {
    1: {  # 登录接口
        "headers": {"Content-Type": "application/json"},
        "body": {"username": "test_user", "password": "test123"},
        "extract_fields": ["token", "userId"]  # 需要提取这些字段供后续使用
    },
    
    2: {  # 创建订单接口
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer {token}"  # 占位符，运行时会被替换
        },
        "body": {
            "product_id": "123",
            "quantity": 1,
            "userId": "{userId}"  # 占位符，从登录接口的响应提取
        },
        "extract_fields": ["order_id"]
    },
    
    3: {  # 查询订单接口
        "headers": {
            "Authorization": "Bearer {token}"  # 使用login提取的token
        },
        "path_params": {
            "orderId": "{order_id}"  # 使用创建订单提取的order_id
        },
        "extract_fields": []
    }
}

# 占位符规则
# {token}    →   从步骤1的响应中提取
# {userId}   →   从步骤1的响应中提取
# {order_id} →   从步骤2的响应中提取
```

### 测试执行阶段

**流程**：
```
初始化 extracted_data = {}
  ↓
for 每个排序后的用例:
  ↓
  1️⃣ 从 extracted_data 中填充占位符
  ↓
  2️⃣ 构造完整的请求
  ↓
  3️⃣ 执行HTTP请求
  ↓
  4️⃣ 提取响应中的关键字段
  ↓
  5️⃣ 更新 extracted_data
  ↓
  6️⃣ 执行断言验证
  ↓
  继续下一个用例
```

#### 详细执行演示

```python
extracted_data = {}

# ===== 步骤1：执行登录用例 =====
print("执行用例1：登录")

# 1. 准备请求
request_1 = {
    "url": "http://api.example.com/api/login",
    "method": "POST",
    "headers": {"Content-Type": "application/json"},
    "json": {"username": "test_user", "password": "test123"}
}

# 2. 发送请求
response_1 = requests.post(**request_1)

# 3. 验证响应
assert response_1.status_code == 200
data_1 = response_1.json()
assert data_1["code"] == 0

# 4. 提取关键数据
extracted_data["token"] = data_1["data"]["token"]  # "abc123xyz"
extracted_data["userId"] = data_1["data"]["userId"]  # 123

print(f"✓ 登录成功，提取: token={extracted_data['token']}, userId={extracted_data['userId']}")


# ===== 步骤2：执行创建订单用例 =====
print("\n执行用例2：创建订单")

# 1. 从 extracted_data 中填充占位符
request_2 = {
    "url": "http://api.example.com/api/order",
    "method": "POST",
    "headers": {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {extracted_data['token']}"  # ← 使用step1的token
    },
    "json": {
        "product_id": "123",
        "quantity": 1,
        "userId": extracted_data['userId']  # ← 使用step1的userId
    }
}

# 2. 发送请求
response_2 = requests.post(**request_2)

# 3. 验证响应
assert response_2.status_code == 201
data_2 = response_2.json()
assert data_2["code"] == 0

# 4. 提取关键数据
extracted_data["order_id"] = data_2["data"]["id"]  # "order_456"

print(f"✓ 订单创建成功，提取: order_id={extracted_data['order_id']}")


# ===== 步骤3：执行查询订单用例 =====
print("\n执行用例3：查询订单")

# 1. 从 extracted_data 中填充占位符
request_3 = {
    "url": f"http://api.example.com/api/order/{extracted_data['order_id']}",  # ← 使用step2的order_id
    "method": "GET",
    "headers": {
        "Authorization": f"Bearer {extracted_data['token']}"  # ← 使用step1的token
    }
}

# 2. 发送请求
response_3 = requests.get(**request_3)

# 3. 验证响应
assert response_3.status_code == 200
data_3 = response_3.json()
assert data_3["code"] == 0
assert data_3["data"]["id"] == extracted_data['order_id']

print(f"✓ 订单查询成功")


# ===== 最后 =====
print("\n✅ 所有用例执行完成！")
print(f"完整数据流转链: {extracted_data}")
```

### 关键设计特点

#### 1️⃣ 数据自动流转

```
Step1 响应  → 提取 → extracted_data
            ↓
Step2 请求  ← 填充 ← extracted_data  
Step2 响应  → 提取 → extracted_data
            ↓
Step3 请求  ← 填充 ← extracted_data
```

**好处**：
- ✅ 无需手动管理复杂的变量传递
- ✅ 每个用例都能自动获得前置用例的结果
- ✅ 支持链式依赖（A→B→C→D）

#### 2️⃣ 占位符机制

```python
# 占位符规则
{field_name}  →  从前面用例的提取数据中查找

例子：
{token}      →  extracted_data["token"]
{order_id}   →  extracted_data["order_id"]
{user.name}  →  extracted_data["user"]["name"]  (支持嵌套)
```

#### 3️⃣ 错误处理与恢复

```python
def execute_with_recovery(sorted_cases, test_data_config):
    extracted_data = {}
    results = []
    
    for case_id in sorted_cases:
        try:
            # 执行用例
            result = execute_single_case(
                case_id,
                test_data_config[case_id],
                extracted_data
            )
            
            # 提取数据
            if result.is_success:
                extracted_data.update(result.extracted_fields)
            
            results.append(result)
            
        except AssertionError as e:
            # 断言失败：该用例失败，但继续下一个
            results.append({
                "case_id": case_id,
                "status": "FAILED",
                "error": str(e)
            })
            
        except DependencyError as e:
            # 依赖错误：跳过后续依赖于此的用例
            print(f"⚠️ 用例{case_id}失败，跳过它的所有依赖用例")
            break
    
    return results
```

#### 4️⃣ 报告生成

```python
def generate_report(results):
    """
    基于执行结果生成Allure报告
    """
    allure_results = []
    
    for result in results:
        allure_test = {
            "name": result["case_name"],
            "status": "PASSED" if result["success"] else "FAILED",
            "duration": result["duration"],
            "request": result["request"],
            "response": result["response"],
            "extracted_data": result["extracted_fields"]
        }
        allure_results.append(allure_test)
    
    # 生成HTML报告
    generate_allure_html(allure_results)
```

---

## 总结：从文档到用例的完整链路

```
┌─────────────────┐
│   API文档上传    │  (支持多种格式)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   文档解析       │  (提取结构化接口信息)
└────────┬────────┘
         │
    ┌────┴─────┐
    │           │
    ▼           ▼
向量化      依赖分析  (规划执行顺序)
存储到向量  存储到
数据库      Neo4j
    │           │
    └────┬──────┘
         │
         ▼
    ┌──────────────────────┐
    │  User Request        │
    │  (生成/验证/补全)    │
    └──────┬───────────────┘
           │
    ┌──────┴──────┬──────────┬──────────┐
    │             │          │          │
    ▼             ▼          ▼          ▼
Parser        Dependency   TestCase    END
Agent         Analyzer     Generator
              Agent        Agent
    │             │          │
    └──────┬──────┴──────────┘
           │
    ┌──────▼───────────────┐
    │ LangGraph工作流      │
    │ 自动编排和执行      │
    └──────┬───────────────┘
           │
    ┌──────▼───────────────┐
    │ 返回完整结果        │
    │ - 接口信息          │
    │ - 依赖关系          │
    │ - 测试用例          │
    └────────────────────┘

核心优势：
✅ 结构化流程：清晰的Agent协作流程
✅ 自动编排：LangGraph管理状态和流转
✅ RAG增强：每个Agent都可使用RAG检索上下文
✅ 可扩展：轻松添加新的Agent节点
✅ 可维护：用户请求自动重新生成用例
```

