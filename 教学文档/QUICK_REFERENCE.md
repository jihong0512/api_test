# 快速参考指南

## 🚀 系统核心概念速查表

### 系统的三大核心功能

```
┌──────────────────────────────────────────────────┐
│  输入: API文档                                   │
├──────────────────────────────────────────────────┤
│  1️⃣  文档解析                                   │
│     将各种格式的文档转换为结构化接口信息         │
│     输出: DocumentAPIInterface                   │
├──────────────────────────────────────────────────┤
│  2️⃣  依赖分析                                   │
│     发现接口间的依赖关系，规划执行顺序          │
│     输出: Dependencies, ExecutionPlan            │
├──────────────────────────────────────────────────┤
│  3️⃣  用例生成                                   │
│     基于接口定义和依赖生成可执行的测试代码      │
│     输出: TestCase (Pytest代码)                 │
└──────────────────────────────────────────────────┘
          输出: 可执行的测试代码
```

---

## 📊 数据流转图

```
用户上传 ┌─────────────┐
  文档   │  Document   │
        └──────┬──────┘
               │
        ┌──────▼──────────────┐
        │ DocumentParser      │
        │ (文档解析)          │
        └──────┬──────────────┘
               │
        ┌──────▼────────────────────────┐
        │ DocumentAPIInterface           │
        │ (接口详情)                     │
        └──────┬───────────────┬────────┘
               │               │
          ┌────▼──────┐   ┌────▼──────┐
          │向量化      │   │依赖分析    │
          │(RAG)      │   │(图数据库)  │
          └────┬──────┘   └────┬──────┘
               │               │
          ┌────▼───────┐  ┌────▼──────┐
          │Milvus      │  │Neo4j      │
          │(向量索引)   │  │(依赖图)    │
          └─────────────┘  └───────────┘
               
               用户请求生成用例
                    │
        ┌───────────▼─────────────┐
        │ TestCaseGenerator        │
        │ 1. RAG检索上下文        │
        │ 2. 生成测试数据         │
        │ 3. 构造HTTP请求         │
        │ 4. 用LLM生成代码        │
        └───────────┬─────────────┘
                    │
        ┌───────────▼─────────────┐
        │ TestCase (Pytest)        │
        │ (可直接运行的Python代码) │
        └──────────────────────────┘
```

---

## 🔑 关键数据结构

### DocumentAPIInterface（接口定义）
```python
{
  "name": "登录",                           # 接口名
  "method": "POST",                         # HTTP方法
  "url": "/api/auth/login",                # 接口URL
  
  "request_body": {                         # 请求体
    "username": {"type": "string"},
    "password": {"type": "string"}
  },
  
  "response_schema": {                      # 响应Schema
    "code": {"type": "integer"},
    "data": {
      "token": {"type": "string"},
      "userId": {"type": "integer"}
    }
  },
  
  "description": "用户登录"                  # 描述
}
```

### Dependency（依赖关系）
```python
{
  "source": "登录",                         # 源接口
  "target": "获取用户",                     # 目标接口
  "type": "parameter",                      # 依赖类型
  "fields": ["token", "userId"],           # 相关字段
  "confidence": 0.95                        # 置信度
}
```

### TestCase（测试用例）
```python
{
  "name": "test_user_login",
  "method": "POST",
  "url": "/api/auth/login",
  
  "test_data": {
    "username": "testuser",
    "password": "testpass123"
  },
  
  "assertions": [
    {"type": "status_code", "expected": 200},
    {"type": "json_body", "path": "code", "expected": 0}
  ]
}
```

---

## 🎯 常见任务速查

### 任务1：上传和解析文档

```python
# 1. 上传文件
POST /documents/upload
{
  "project_id": 123,
  "file": <file>,
  "file_type": "openapi"  # 或 json, yaml, pdf, docx等
}

# 2. 查看解析结果
GET /documents/{doc_id}/interfaces
返回: [DocumentAPIInterface, ...]

# 3. 查看提取的所有接口
GET /projects/{project_id}/interfaces
```

### 任务2：分析依赖关系

```python
# 1. 触发依赖分析
POST /projects/{project_id}/analyze-dependencies

# 2. 查看依赖关系
GET /projects/{project_id}/dependencies
返回: [Dependency, ...]

# 3. 查看执行计划
GET /projects/{project_id}/execution-plan
返回: [[接口1], [接口2, 接口3], [接口4]]
```

### 任务3：生成测试用例

```python
# 1. 生成单个接口的用例
POST /test-cases/generate
{
  "project_id": 123,
  "api_interface_ids": [1, 2, 3],
  "case_type": "pytest"
}

# 2. 查看生成的用例
GET /test-cases/{case_id}
返回: {
  "name": "test_xxx",
  "test_code": "import pytest\n...",
  "status": "completed"
}

# 3. 下载用例代码
GET /test-cases/{case_id}/code
返回: Python文件
```

### 任务4：执行测试

```python
# 1. 运行单个用例
POST /test-cases/{case_id}/run
{
  "environment_id": 456  # 测试环境
}

# 2. 查看执行结果
GET /test-cases/{case_id}/results
返回: {
  "status": "success/failed",
  "duration": 1.23,
  "output": "..."
}

# 3. 批量运行
POST /test-tasks/batch-run
{
  "project_id": 123,
  "test_case_ids": [1, 2, 3]
}
```

---

## ⚙️ 核心服务速查

| 服务 | 职责 | 关键方法 |
|------|------|--------|
| **DocumentParser** | 解析各种格式文档 | `parse()` |
| **TestCaseGenerator** | 生成测试用例代码 | `generate()` |
| **DependencyAnalyzer** | 分析接口依赖 | `analyze()` |
| **RAGService** | 混合检索 | `hybrid_search()` |
| **VectorService** | 向量化和存储 | `add_documents()`, `search()` |
| **LLMService** | 调用大模型 | `chat()`, `complete()` |

---

## 💻 代码示例速查

### 示例1：解析文档
```python
from app.services.document_parser import DocumentParser

parser = DocumentParser()
interfaces = await parser.parse(
    file_path="/path/to/api.json",
    file_type="json"
)
print(interfaces)  # [接口1, 接口2, ...]
```

### 示例2：分析依赖
```python
from app.services.dependency_analyzer import DependencyAnalyzer

analyzer = DependencyAnalyzer()
result = await analyzer.analyze(interfaces, project_id=123)
print(result["dependencies"])      # 依赖关系
print(result["execution_plan"])    # 执行顺序
```

### 示例3：生成用例
```python
from app.services.test_case_generator import TestCaseGenerator

generator = TestCaseGenerator()
code = await generator.generate(
    api_interface=interface,
    dependencies=dependencies,
    use_llm=True
)
print(code)  # Python测试代码
```

### 示例4：RAG检索
```python
from app.services.rag_service import HybridRAGService

rag = HybridRAGService()
results = await rag.hybrid_search(
    query="如何登录系统",
    project_id=123,
    top_k=5
)
for result in results:
    print(result["text"], result["score"])
```

---

## 🔍 故障排查

### 问题1：文档解析失败
```
症状：解析后没有接口信息
排查：
1. 检查文件格式是否支持
2. 检查文件内容是否有效
3. 查看logs获取详细错误
4. 尝试用LLM增强模式
```

### 问题2：依赖关系不完整
```
症状：某些接口的依赖没有被识别
排查：
1. 参数名是否匹配（LoginResponse.token vs LoginRequest.token）
2. 是否存在业务流程依赖（需要LLM识别）
3. 检查接口文档描述是否清晰
```

### 问题3：生成的用例无法运行
```
症状：生成的测试代码执行失败
排查：
1. 测试数据是否合理（邮箱格式、密码强度等）
2. 依赖关系是否正确处理
3. URL是否正确（需要正确的base_url）
4. 认证信息是否完整
```

### 问题4：RAG搜索结果不准确
```
症状：搜索得不到相关文档
排查：
1. 向量化是否成功（检查Milvus)
2. 查询词是否与文档相关
3. 尝试使用更具体的查询词
4. 检查文档分块的大小
```

---

## 📈 性能优化建议

### 优化1：加速文档解析
```python
# ❌ 同步处理（慢）
for doc in documents:
    parse(doc)

# ✅ 异步并行处理（快）
results = await asyncio.gather(*[
    parse(doc) for doc in documents
])
```

### 优化2：缓存向量
```python
# 避免重复向量化同一文本
cache = {}
for text in texts:
    if text not in cache:
        cache[text] = embedding_model.encode(text)
```

### 优化3：批量生成用例
```python
# ❌ 逐个生成（慢）
for interface in interfaces:
    generate_case(interface)

# ✅ 批量生成（快）
results = await batch_generate_test_cases(interfaces)
```

---

## 📝 最常用的端点

```
POST   /documents/upload                    上传文档
GET    /projects/{id}/interfaces            查看接口
POST   /projects/{id}/analyze-dependencies  分析依赖
GET    /projects/{id}/dependencies          查看依赖
POST   /test-cases/generate                 生成用例
GET    /test-cases/{id}                     查看用例
POST   /test-cases/{id}/run                 运行用例
GET    /test-results/{id}                   查看结果
POST   /search                              RAG搜索
```

---

## 🎓 重点知识

### 必须理解的概念
- ✅ 文档格式的识别和标准化
- ✅ 接口依赖的三种类型（参数、流程、认证）
- ✅ 拓扑排序确定执行顺序
- ✅ 向量化和混合检索
- ✅ Pytest测试用例的结构

### 必须会操作的任务
- ✅ 上传和解析API文档
- ✅ 分析接口间的依赖
- ✅ 生成和执行测试用例
- ✅ 查看测试结果和报告
- ✅ 使用RAG搜索文档

### 必须掌握的技能
- ✅ 理解JSON/YAML格式
- ✅ 理解HTTP请求和响应
- ✅ 理解Python和Pytest
- ✅ 理解AI和向量化基础
- ✅ 理解系统架构和数据流

---

## 💾 常用配置

### 文件格式配置
```python
SUPPORTED_FORMATS = {
    'txt', 'json', 'yaml', 'yml',
    'pdf', 'docx', 'md',
    'csv', 'xlsx', 'xls',
    'jmx', 'apifox'
}

EMBEDDING_MODEL = 'paraphrase-MiniLM-L6-v2'  # 768维
VECTOR_DB = 'Milvus'                         # 向量数据库
GRAPH_DB = 'Neo4j'                           # 关系图数据库
```

### 性能参数配置
```python
CHUNK_SIZE = 512          # 文档分块大小
CHUNK_OVERLAP = 50        # 分块重叠
TOP_K = 5                 # 检索结果数
BATCH_SIZE = 10           # 批量处理大小
TIMEOUT = 30              # 请求超时
```

---

记住这个快速参考，你就能快速定位问题和找到解决方案！

