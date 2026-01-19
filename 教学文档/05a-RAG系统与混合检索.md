# 📚 RAG系统与混合检索详解

> 理解RAG（检索增强生成）及其在API测试系统中的应用

---

## 目录
1. [什么是RAG](#什么是rag)
2. [向量化和存储](#向量化和存储)
3. [混合检索系统](#混合检索系统)
4. [RAG检索流程](#rag检索流程)
5. [实战集成](#实战集成)

---

## 什么是RAG

### RAG的三个阶段

**RAG** = Retrieval-Augmented Generation（检索增强生成）

```
┌─────────────────────────────────────────────────┐
│ Retrieval（检索）                              │
│ 从向量数据库找到相关的文档块                     │
│ 输入：用户查询 → 输出：前k个相关文档             │
└──────────────┬──────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────┐
│ Augmentation（增强）                           │
│ 将检索到的文档加入到LLM的上下文                 │
│ 形成更完整的提示词                              │
└──────────────┬──────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────┐
│ Generation（生成）                             │
│ LLM基于增强的上下文生成答案                     │
│ 输入：查询+检索到的相关文档 → 输出：准确的答案    │
└─────────────────────────────────────────────────┘
```

### 为什么需要RAG？

**问题场景**：

```
场景1：LLM知识过时
┌─────────────────────────────┐
│ 用户问：                      │
│ "请帮我生成登录接口的测试"   │
│                             │
│ LLM的困惑：                  │
│ "我的训练数据来自2024年       │
│ 不知道你项目的具体接口定义"   │
└─────────────────────────────┘

场景2：LLM不了解项目细节
┌─────────────────────────────┐
│ 用户问：                      │
│ "生成订单支付接口的测试"     │
│                             │
│ LLM的问题：                  │
│ "不知道项目中支付接口的       │
│ 具体参数、认证方式、依赖"     │
└─────────────────────────────┘
```

**RAG解决方案**：

```
不是让LLM凭空生成，而是：
1. 先查找你项目中的相关文档
2. 把文档作为背景资料给LLM
3. LLM基于这些资料生成答案

这样答案就准确、相关，充分利用项目历史
```

### 测试系统中的应用

```
用户请求：为登录接口生成测试用例

    ↓

RAG步骤：
  1. 检索：从项目文档中找到登录接口的详细信息
  2. 增强：提示词现在包含：
     - 登录接口的参数说明
     - 成功响应的格式
     - 认证方式（JWT Token）
     - 类似接口的测试风格
  3. 生成：LLM知道上下文后，生成准确的测试代码

    ↓

输出：符合项目风格、参数准确的测试用例
```

---

## 向量化和存储

### 文档分块流程

文档太长无法直接存储，需要分块处理：

```python
原始文档（10000字符）

        ↓ 分块
        
┌─────────────────────────────────────────┐
│ 块1 (512字符)                            │
│ "接口名：POST /api/users/login"          │
│ "参数：username, password"               │
│ "响应：token, userId, username"          │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ 块2 (512字符，与块1有50字符重叠)        │
│ "响应：token, userId, username"          │
│ "错误处理：401登录失败..."              │
│ "认证方式：Bearer Token"                │
└─────────────────────────────────────────┘

...更多块...

        ↓ 向量化

向量1 (768维向量)
向量2 (768维向量)
...

        ↓ 存储到向量数据库
        
向量库中可以快速检索相似内容
```

### 向量化详解

**什么是向量化？**

```
文本 → 数字向量（用768个或更多数字表示）

例如：
"POST /api/users/login" 
  ↓
[0.123, 0.456, ..., 0.789]  # 768个数字

好处：可以计算两个向量的相似度！
```

**相似度计算**：

```python
# 查询向量和候选向量之间的余弦相似度
cos_similarity = dot_product(query_vec, candidate_vec) / 
                 (norm(query_vec) * norm(candidate_vec))

# 相似度范围：-1 到 1
# 1：完全相同
# 0：无关
# -1：完全相反
```

### 常用的Embedding模型

| 模型 | 维度 | 速度 | 质量 | 推荐场景 |
|------|------|------|------|---------|
| **paraphrase-MiniLM-L6-v2** | 384 | ⚡⚡⚡ | ⭐⭐ | 快速原型 |
| **all-MiniLM-L6-v2** | 384 | ⚡⚡ | ⭐⭐⭐ | **推荐** |
| **all-mpnet-base-v2** | 768 | ⚡ | ⭐⭐⭐⭐ | 精准检索 |
| **bge-large-zh-v1.5** | 1024 | ⚡ | ⭐⭐⭐⭐⭐ | 中文优化 |

### 向量数据库对比

| 数据库 | 特点 | 优点 | 缺点 |
|-------|------|------|------|
| **Milvus** | 专业向量DB | 功能完整，性能强 | 需要单独部署 |
| **ChromaDB** | 简洁轻量 | 容易集成，无需部署 | 功能相对简单 |
| **Pinecone** | 云服务 | 无需维护，开箱即用 | 需要付费，网络依赖 |
| **Weaviate** | 云+开源 | 功能丰富 | 配置复杂 |

---

## 混合检索系统

### 单一检索的局限

```
❌ 只用向量检索
  问题：需要理解语义，速度慢
  例：用户搜"status 字段"，向量检索可能找不到
  
❌ 只用BM25关键词匹配  
  问题：无法理解语义
  例：搜"如何认证"，可能找不到"authentication"相关内容
```

### 混合检索方案

```
┌──────────────────────────────────────────┐
│ 用户查询：分页接口的参数有哪些           │
└──────────────┬─────────────────────────────┘
               │
        ┌──────┴──────┐
        │             │
        ▼             ▼
    向量检索      BM25检索
    │             │
    ├─关键字：    ├─关键字：
    │ page,       │ page,
    │ limit,      │ limit,
    │ offset      │ offset
    │             │
    ├─结果A      ├─结果B
    │ {          │ {
    │  "para": "  │  "name": "
    │  page_sz",  │  page",
    │  ...        │  ...
    │ }           │ }
    │             │
    └──────┬──────┘
           │
           ▼
       合并结果
       (去重)
           │
           ▼
       重排序
       (使用Cross-encoder)
           │
           ▼
       最终排序的结果
       [最相关 → 较相关 → ...]
```

### 混合检索的实现逻辑

```python
# 步骤1：并行执行向量检索和BM25
vector_results = await vector_search(query)     # [A, B, C, ...]
bm25_results = await bm25_search(query)         # [D, E, F, ...]

# 步骤2：合并结果（去重）
merged = merge(vector_results, bm25_results)    # [A, B, C, D, E, F, ...]

# 步骤3：重排序（使用Cross-encoder模型）
reranked = rerank(query, merged)                # [A, D, B, E, C, F, ...]

# 步骤4：返回top-k
return reranked[:10]
```

### 何时使用混合检索

**推荐使用混合检索的场景**：

✅ **通用查询**（最常见）
```
"怎样处理登录失败"
"参数校验的规则"
"支付接口的集成示例"
```

✅ **关键词+语义混合**
```
"status 字段的含义" ← 关键词（status）+ 语义（含义）
```

❌ **纯关键词查询**（用BM25足够）
```
"找到 userId 字段"
"查找 200 状态码"
```

---

## RAG检索流程

### 完整的数据流

```
项目启动
    │
    ├─ 上传API文档
    │    │
    │    ├─→ DocumentParser
    │    │   提取接口、参数、格式
    │    │
    │    └─→ 获得结构化接口数据
    │         [接口1, 接口2, ...]
    │
    ├─ 向量化并存储
    │    │
    │    ├─→ Chunking
    │    │   每块512字符，50字符重叠
    │    │
    │    ├─→ Embedding
    │    │   使用MiniLM模型
    │    │   输出384维向量
    │    │
    │    └─→ VectorDB存储
    │         [向量1, 向量2, ...]
    │
    └─ 依赖分析
         │
         └─→ Neo4j存储依赖关系


用户请求"生成登录测试用例"
    │
    ├─ RAG检索
    │    │
    │    ├─→ 向量化查询
    │    │   "生成登录测试用例" → [0.123, 0.456, ...]
    │    │
    │    ├─→ 并行检索
    │    │   ├─ 向量检索：从向量库找相似度>0.7的结果
    │    │   └─ BM25搜索：关键词匹配
    │    │
    │    ├─→ 合并去重
    │    │   结果去掉重复的文档
    │    │
    │    └─→ 重排序
    │        Cross-encoder重新排序
    │
    ├─ LLM生成
    │    │
    │    ├─→ 构造提示词
    │    │   提示词 = 系统提示 + Few-shot + RAG结果 + 用户请求
    │    │
    │    └─→ 调用LLM
    │         gpt-4 / Claude 生成代码
    │
    └─→ 返回：可运行的测试用例
```

### 关键参数调优

```python
# 检索相关性阈值
similarity_threshold = 0.6  # 0.6-0.8推荐
                            # 太低：结果太多噪音
                            # 太高：可能遗漏相关结果

# 返回结果数量
top_k = 5                  # 3-5推荐
                           # 太少：信息不足
                           # 太多：干扰LLM

# 重排序模型
reranker = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
           # 计算成本：O(n * query_len * doc_len)
           # 建议在top_k=10的基础上重排序

# 块的大小
chunk_size = 512           # 字符数
overlap = 50               # 块间重叠
                           # 防止信息在块边界丢失
```

---

## 实战集成

### 完整的检索流程代码

```python
class RAGRetriever:
    """完整的RAG检索系统"""
    
    def __init__(self):
        # 初始化各个组件
        self.vector_db = VectorDatabase()
        self.bm25_service = BM25Service()
        self.reranker = RerankerModel()
        self.llm = LLMService()
    
    async def retrieve_and_augment(
        self,
        query: str,
        project_id: str,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        混合检索流程
        """
        
        # 步骤1：并行执行向量检索和BM25
        vector_results, bm25_results = await asyncio.gather(
            self._vector_search(query, project_id),
            self._bm25_search(query, project_id)
        )
        
        # 步骤2：合并结果
        merged = self._merge_results(vector_results, bm25_results)
        
        # 步骤3：重排序
        reranked = await self.reranker.rerank(query, merged)
        
        # 步骤4：过滤相关性较低的结果
        filtered = [
            r for r in reranked
            if r['rerank_score'] > 0.3
        ][:top_k]
        
        # 步骤5：构造增强的上下文
        context = self._build_context(query, filtered)
        
        return {
            'query': query,
            'retrieved_count': len(filtered),
            'context': context,
            'sources': [r['source'] for r in filtered]
        }
    
    async def generate_with_rag(
        self,
        user_request: str,
        project_id: str
    ) -> str:
        """
        使用RAG增强的生成
        """
        
        # 检索相关文档
        rag_result = await self.retrieve_and_augment(
            user_request,
            project_id
        )
        
        # 构造完整提示词
        system_prompt = """
你是一个资深API测试工程师。
请根据提供的项目文档和用户请求，生成高质量的测试代码。
"""
        
        user_prompt = f"""
用户请求: {user_request}

项目相关文档（参考）:
{rag_result['context']}

请基于上面的文档信息，生成测试代码。
确保测试代码符合文档中接口的定义。
"""
        
        # 调用LLM
        response = await self.llm.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])
        
        return response
    
    def _build_context(self, query: str, retrieved: List[Dict]) -> str:
        """构造增强的上下文文本"""
        
        context = f"""## 相关背景信息\n\n"""
        
        for i, item in enumerate(retrieved, 1):
            context += f"""
### 参考资料 {i}
来源: {item['source']}
相关度: {item['rerank_score']:.1%}

{item['text']}

---
"""
        
        return context
```

### 性能优化建议

**1. 缓存策略**
```python
# 缓存常见查询的检索结果
cache = Redis()

async def retrieve_with_cache(query, project_id):
    cache_key = f"rag:{project_id}:{query_hash}"
    
    # 先查缓存
    cached = await cache.get(cache_key)
    if cached:
        return cached
    
    # 没有缓存则执行检索
    result = await retrieve_and_augment(query, project_id)
    
    # 存入缓存（24小时过期）
    await cache.set(cache_key, result, ex=86400)
    
    return result
```

**2. 批量检索**
```python
# 同时处理多个查询，提高吞吐量
async def batch_retrieve(
    queries: List[str],
    project_id: str
) -> List[Dict]:
    """批量检索"""
    
    tasks = [
        retrieve_and_augment(q, project_id)
        for q in queries
    ]
    
    results = await asyncio.gather(*tasks)
    return results
```

**3. 定期更新索引**
```python
# 当文档变化时，增量更新索引
async def update_index(
    project_id: str,
    updated_documents: List[Dict]
):
    """增量更新向量索引"""
    
    for doc in updated_documents:
        # 重新分块和向量化
        chunks = await chunker.chunk(doc['content'])
        embeddings = await embedder.embed(chunks)
        
        # 更新向量库
        await vector_db.upsert(
            collection=f"project_{project_id}",
            ids=[f"{doc['id']}_{i}" for i in range(len(chunks))],
            vectors=embeddings,
            metadata=[{'doc_id': doc['id']} for _ in chunks]
        )
```

---

## 总结

**RAG系统** 是让LLM能够准确生成项目相关内容的关键技术：

- ✅ **检索**：从文档库找到相关信息
- ✅ **增强**：将信息加入到LLM的上下文
- ✅ **生成**：LLM基于增强的上下文生成准确答案

**混合检索** 结合了向量搜索和关键词匹配的优点，提供最佳的检索效果。

这是**测试系统中实现知识库检索的核心技术**！
