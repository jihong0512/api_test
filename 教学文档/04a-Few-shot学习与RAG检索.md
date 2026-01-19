# 🎓 Few-shot学习与RAG检索详解

> 理解如何用Few-shot学习和RAG检索增强测试用例生成的质量

---

## 目录
1. [Few-shot学习原理](#few-shot学习原理)
2. [RAG检索增强](#rag检索增强)
3. [两种技术的协作](#两种技术的协作)
4. [实现细节](#实现细节)
5. [最佳实践](#最佳实践)

---

## Few-shot学习原理

### 什么是Few-shot？

**定义**：从几个示例中学习规律，然后应用到新任务

**对比三种学习方式**：

```
0-shot（零样本）：
  提示词：请为API生成测试用例
  LLM理解：很模糊...自己随便生成吧
  质量：⭐ 很差
  
  输出：
    def test_api():
        response = requests.get(url)
        assert response is not None

1-shot（单样本）：
  提示词：请参考这个例子生成测试用例
  [展示1个好例子]
  
  质量：⭐⭐ 一般
  
few-shot（多样本）：
  提示词：请参考这些例子生成测试用例
  [展示3-5个好例子]
  
  质量：⭐⭐⭐⭐ 很好！
  
  输出：
    @pytest.fixture
    def auth_token():
        ...
    
    def test_user_login():
        ...assert response.status_code == 200...
        ...assert data["token"] in response...
        ...assert data["userId"] is not None...
```

### Few-shot在apitest中的应用

**关键思想**：
```
与其写复杂的规则告诉LLM"怎么生成"，
不如给它看几个"好的用例"，然后说"按这个风格生成"
```

#### 提示词的三部分结构

```python
# 第1部分：系统提示词（定义角色）
system_prompt = """
你是一个资深的API测试工程师。
你的工作是为给定的API接口生成高质量的Pytest测试用例。
"""

# 第2部分：Few-shot示例（教如何做）
few_shot_examples = """
【示例1：正常登录测试】
接口: POST /api/users/login
请求: {username: "test@example.com", password: "password123"}
响应: {code: 0, data: {token: "eyJ...", userId: 123, username: "test"}}

生成的测试代码:
def test_login_success():
    response = requests.post(
        f"{BASE_URL}/api/users/login",
        json={"username": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "token" in data["data"]
    assert "userId" in data["data"]
    assert data["data"]["username"] == "test"

【示例2：登录失败测试】
同一个接口的错误场景：

def test_login_failure():
    response = requests.post(
        f"{BASE_URL}/api/users/login",
        json={"username": "test@example.com", "password": "wrong_password"}
    )
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == 401
    assert "error" in data or "message" in data

【示例3：需要认证的接口】
接口: GET /api/users/{userId}
需要: Authorization: Bearer {token}
响应: {code: 0, data: {id: 123, username: "test", email: "test@example.com"}}

生成的测试代码:
@pytest.fixture(scope="module")
def auth_token():
    response = requests.post(
        f"{BASE_URL}/api/users/login",
        json={"username": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    return response.json()["data"]["token"]

def test_get_user_info(auth_token):
    response = requests.get(
        f"{BASE_URL}/api/users/123",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["id"] == 123
    assert "username" in data["data"]

【示例4：POST创建资源】
接口: POST /api/articles
需要: Authorization, 请求体包含 {title, content, category}
响应: {code: 0, data: {id: 1, title, content, category, createdAt, createdBy}}

生成的代码:
def test_create_article(auth_token):
    payload = {
        "title": "How to test APIs",
        "content": "Testing APIs is important...",
        "category": "Tech"
    }
    response = requests.post(
        f"{BASE_URL}/api/articles",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["title"] == payload["title"]
    assert "id" in data["data"]
    assert "createdAt" in data["data"]
"""

# 第3部分：实际任务（做这个）
user_prompt = f"""
现在根据上面的示例，为以下接口生成类似质量的测试用例：

接口名称: {interface_name}
HTTP方法: {method}
URL: {url}
描述: {description}
请求参数: {request_params}
响应格式: {response_schema}
依赖的前置接口: {dependencies}

请生成的测试用例应该包括：
1. 正常情况的测试
2. 错误情况的测试（如果适用）
3. 正确的断言
4. 前置条件的处理（如需要认证或依赖其他接口）

只返回Python代码，不要其他说明。
"""
```

### Few-shot的高级技巧

#### 1. 选择最相关的示例

```python
def select_best_few_shot_examples(new_interface, example_pool, num_examples=3):
    """
    从示例池中选择最相关的示例
    """
    
    best_examples = []
    
    # 优先级1：同样的HTTP方法和类似的URL
    for example in example_pool:
        if example['method'] == new_interface['method']:
            if similarity(example['url'], new_interface['url']) > 0.7:
                best_examples.append(example)
    
    # 优先级2：同样的认证需求
    if best_examples:
        return best_examples[:num_examples]
    
    for example in example_pool:
        if example.get('requires_auth') == new_interface.get('requires_auth'):
            best_examples.append(example)
    
    # 优先级3：有相似的响应结构
    if best_examples:
        return best_examples[:num_examples]
    
    # 降级：返回任意示例
    return example_pool[:num_examples]
```

#### 2. 动态构造提示词

```python
async def build_dynamic_few_shot_prompt(interface_info, project_history):
    """
    根据项目历史动态构造Few-shot提示词
    """
    
    # 从项目历史中查找相关的成功用例
    similar_cases = find_similar_test_cases(interface_info, project_history, top_k=3)
    
    # 构造提示词
    few_shot_text = "【参考示例】\n\n"
    
    for i, case in enumerate(similar_cases, 1):
        few_shot_text += f"""
【示例{i}】
接口: {case['interface_info']}

生成的代码:
{case['test_code']}

---
"""
    
    return few_shot_text
```

---

## RAG检索增强

### 什么是RAG？

**RAG** = Retrieval-Augmented Generation
**含义** = 检索增强生成

**工作流**：
```
用户问题
  ↓
检索相关信息
  ↓
用相关信息 + 问题 → 生成答案
```

### RAG在测试用例生成中的应用

**场景**：为新接口生成测试用例

```
步骤1：接收新接口定义
  输入：{name: "订单支付", method: "POST", url: "/orders/{id}/pay"}

步骤2：检索相似的接口和用例
  查询：支付相关的接口
  结果：
    - 订单创建接口的测试用例
    - 其他支付接口的测试用例
    - 类似业务逻辑的用例

步骤3：用LLM生成
  输入：新接口 + 检索到的相似用例
  输出：针对新接口的测试用例

好处：
  ✅ 新用例继承了相似接口的最佳实践
  ✅ 保证测试风格一致
  ✅ 充分利用项目历史
```

### RAG的技术实现

#### 1. 向量化存储

```python
from sentence_transformers import SentenceTransformer

class TestCaseVectorStore:
    """测试用例向量存储"""
    
    def __init__(self):
        # 使用预训练的embedding模型
        self.model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
        self.vectors = {}  # id → vector映射
        self.metadata = {}  # id → 元数据映射
    
    def add_test_case(self, case_id: str, interface_info: dict, test_code: str):
        """添加测试用例到向量库"""
        
        # 构造文本（包含接口信息和测试代码）
        text = f"""
        接口名称: {interface_info['name']}
        HTTP方法: {interface_info['method']}
        URL: {interface_info['url']}
        描述: {interface_info.get('description', '')}
        
        测试代码:
        {test_code[:200]}  # 取前200个字符
        """
        
        # 向量化
        vector = self.model.encode(text)
        
        # 存储
        self.vectors[case_id] = vector
        self.metadata[case_id] = {
            'interface_name': interface_info['name'],
            'method': interface_info['method'],
            'test_code': test_code
        }
    
    def retrieve_similar_cases(self, query_interface: dict, top_k: int = 3):
        """检索相似的测试用例"""
        
        # 1. 构造查询文本
        query_text = f"""
        接口名称: {query_interface['name']}
        HTTP方法: {query_interface['method']}
        URL: {query_interface['url']}
        描述: {query_interface.get('description', '')}
        """
        
        # 2. 向量化查询
        query_vector = self.model.encode(query_text)
        
        # 3. 计算相似度
        import numpy as np
        similarities = {}
        
        for case_id, vector in self.vectors.items():
            # 余弦相似度
            sim = np.dot(query_vector, vector) / (
                np.linalg.norm(query_vector) * np.linalg.norm(vector)
            )
            similarities[case_id] = sim
        
        # 4. 返回top-k
        sorted_cases = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        
        results = []
        for case_id, score in sorted_cases[:top_k]:
            results.append({
                'score': score,
                'metadata': self.metadata[case_id]
            })
        
        return results
```

#### 2. 构造RAG提示词

```python
def build_rag_enhanced_prompt(new_interface, retrieved_cases):
    """
    构造RAG增强的提示词
    """
    
    rag_context = "【从项目历史检索到的相似测试用例】\n\n"
    
    for i, case in enumerate(retrieved_cases, 1):
        rag_context += f"""
【参考用例{i}】
接口: {case['metadata']['interface_name']}

测试代码:
{case['metadata']['test_code']}

相似度: {case['score']:.2%}

---
"""
    
    return rag_context
```

### RAG vs Few-shot的对比

| 特性 | Few-shot | RAG |
|------|----------|-----|
| **来源** | 手工编写的固定示例 | 从项目历史动态检索 |
| **适应性** | 通用但不够个性化 | 高度个性化 |
| **更新** | 需要手工更新 | 自动更新（每生成新用例） |
| **准确性** | 中等 | 高（因为是实际项目的例子） |
| **实现复杂度** | 低 | 中等（需要embedding和相似度计算） |

---

## 两种技术的协作

### 协作方式

```
  新接口定义
       ↓
┌──────┴──────┐
│ 步骤1        │ 步骤2
│ Few-shot提示 │ RAG检索
│ 词（基础）   │ （增强）
└──────┬──────┘
       ↓
  合并提示词
       ↓
  调用LLM生成
       ↓
  高质量的测试用例
```

### 完整的融合代码

```python
class EnhancedTestCaseGenerator:
    """融合Few-shot + RAG的增强型生成器"""
    
    def __init__(self, llm_service, vector_store):
        self.llm_service = llm_service
        self.vector_store = vector_store
        self.few_shot_examples = self._load_few_shot_examples()
    
    async def generate_test_case(self, interface_info):
        """
        生成测试用例：Few-shot + RAG
        """
        
        # 步骤1：构造基础Few-shot提示词
        few_shot_prompt = self._build_few_shot_prompt()
        
        # 步骤2：RAG检索相似用例
        similar_cases = self.vector_store.retrieve_similar_cases(
            interface_info, 
            top_k=3
        )
        rag_context = self._build_rag_context(similar_cases)
        
        # 步骤3：合并提示词
        combined_prompt = f"""
{few_shot_prompt}

【项目相似用例（参考）】
{rag_context}

【要生成的新接口】
名称: {interface_info['name']}
方法: {interface_info['method']}
URL: {interface_info['url']}
...
"""
        
        # 步骤4：调用LLM
        test_code = await self.llm_service.generate(combined_prompt)
        
        # 步骤5：存储用例到向量库（用于后续的RAG检索）
        self.vector_store.add_test_case(
            case_id=f"test_{interface_info['name']}",
            interface_info=interface_info,
            test_code=test_code
        )
        
        return test_code
```

---

## 实现细节

### 1. 选择合适的embedding模型

```python
# 不同的embedding模型
models = {
    # 轻量级（速度快，性能略低）
    'paraphrase-MiniLM-L6-v2': {
        'size': 50,  # MB
        'latency': 5,  # ms
        'quality': 'good'
    },
    
    # 标准（速度-质量平衡）
    'all-MiniLM-L6-v2': {
        'size': 70,
        'latency': 10,
        'quality': 'excellent'
    },
    
    # 高质量（速度慢，性能最好）
    'all-mpnet-base-v2': {
        'size': 400,
        'latency': 30,
        'quality': 'state-of-art'
    }
}

# 推荐：使用 all-MiniLM-L6-v2
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
```

### 2. 相似度阈值

```python
def retrieve_with_threshold(vector_store, query, threshold=0.5):
    """只返回相似度高于阈值的结果"""
    
    results = vector_store.retrieve_similar_cases(query, top_k=10)
    
    # 过滤
    filtered = [r for r in results if r['score'] > threshold]
    
    if not filtered:
        # 如果没有高相似度的用例，返回最相似的那个
        return results[:1]
    
    return filtered[:3]
```

---

## 最佳实践

### ✅ 推荐做法

1. **同时使用Few-shot和RAG**
   ```python
   # 推荐：两者都用
   test_code = await generator.generate_with_few_shot_and_rag(interface)
   ```

2. **定期更新Few-shot示例**
   ```python
   # 季度更新一次Few-shot示例
   # 选择最新、最好的用例作为示例
   ```

3. **监控用例质量**
   ```python
   # 跟踪：用例是否通过、覆盖率等
   # 低质量的用例不要加入RAG库
   ```

### ❌ 避免的做法

1. ❌ 只用Few-shot不用RAG
   ```python
   # 不够个性化
   ```

2. ❌ 过多的Few-shot示例（超过5个）
   ```python
   # 会让提示词过长，反而降低效果
   ```

3. ❌ 不清理RAG库中的低质量用例
   ```python
   # 会污染检索结果
   ```

---

## 总结

**Few-shot + RAG** 是生成高质量测试用例的最强组合：

- **Few-shot**：提供基础的"风格规范"
- **RAG**：提供项目的"最佳实践"
- **结合**：充分发挥LLM的潜力

这就是**测试用例生成智能体（智能体3）的核心技术**！
