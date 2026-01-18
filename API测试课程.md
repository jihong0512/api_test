# API接口智能测试系统 - 课程体系

## 📖 目录

一、[API测试系统核心定位](#一api测试系统核心定位)
二、[大模型服务（LLM Service）](#二大模型服务llm-service)
三、[文档解析模块](#三文档解析模块)
四、[测试用例生成模块](#四测试用例生成模块)
五、[接口依赖分析模块](#五接口依赖分析模块)
六、[知识图谱与向量检索](#六知识图谱与向量检索)
七、[异步任务处理（Celery）](#七异步任务处理celery)
八、[测试执行与报告生成](#八测试执行与报告生成)
九、[数据流转与系统架构](#九数据流转与系统架构)
十、[提示词工程](#十提示词工程)
十一、[Few-shot学习与场景化生成](#十一few-shot学习与场景化生成)
十二、[系统在本项目中的实际应用总结](#十二系统在本项目中的实际应用总结)

---

## 一、API测试系统核心定位

### 1. 概念

API接口智能测试系统是一套**基于大模型的智能API测试平台**，核心价值是解决传统API测试的"效率瓶颈"和"质量难题"——通过AI技术实现从"手工编写测试用例"到"智能自动生成"的升级，让测试工程师从重复劳动中解放出来，专注于测试策略和业务逻辑验证。

### 2. 核心思想

**传统API测试**如同"手工制作"，每个测试用例都需要人工编写，效率低、易遗漏、维护成本高。

**智能API测试系统**提供了"自动化生产线"：
- **无智能系统**：测试工程师需要手工分析接口文档、编写测试代码、设计测试数据、维护测试用例；
- **有智能系统**：系统自动解析文档、生成测试用例、分析依赖关系、执行测试并生成报告。

### 3. 系统核心能力体系

| 能力模块 | 作用 | 核心价值 |
|---------|------|---------|
| **文档解析** | 自动解析OpenAPI/Swagger、PDF、Word等格式的接口文档 | 无需手工录入接口信息，支持多种文档格式 |
| **智能用例生成** | 基于大模型自动生成pytest和JMeter测试用例 | 生成高质量测试代码，覆盖正常、异常、边界场景 |
| **依赖分析** | 自动分析接口间的依赖关系和业务逻辑流程 | 识别调用链，确保测试用例按正确顺序执行 |
| **知识图谱** | 使用Neo4j构建接口关系网络，可视化依赖关系 | 直观展示接口关系，支持复杂查询和分析 |
| **向量检索** | 使用Milvus进行语义搜索和相似度匹配 | 快速找到相似接口，支持RAG增强生成 |
| **异步任务** | 使用Celery处理耗时任务（解析、生成、执行） | 不阻塞用户操作，支持长时间任务 |
| **测试执行** | 执行pytest和JMeter测试，生成Allure报告 | 自动化测试执行，生成详细测试报告 |
| **智能分析** | 使用LLM分析测试结果，提供修复建议 | 自动定位问题，提供解决方案 |

### 4. 白话解释

想象一下：
- **传统测试方式**：测试工程师拿到接口文档后，需要手工阅读、理解、编写测试代码、设计测试数据、执行测试、分析结果。这个过程耗时且容易出错。
- **智能测试系统**：就像有一个"AI测试助手"，你只需要上传接口文档，系统就会：
  1. 自动"读懂"文档，提取接口信息
  2. 自动"思考"如何测试，生成测试用例
  3. 自动"分析"接口关系，确保测试顺序正确
  4. 自动"执行"测试，生成详细报告
  5. 自动"诊断"问题，提供修复建议

### 5. 技术架构概览

```
用户浏览器（React前端）
    ↓ HTTP请求
FastAPI后端服务
    ├── 文档解析服务
    ├── 测试用例生成服务
    ├── 接口依赖分析服务
    ├── 测试执行服务
    └── 报告生成服务
    ↓ 异步任务
Celery Worker（后台任务处理）
    ├── 调用大模型（DeepSeek/通义千问）
    ├── 执行pytest测试
    └── 执行JMeter性能测试
    ↓ 数据存储
MySQL（主数据库） + Redis（缓存） + Neo4j（知识图谱） + Milvus（向量检索）
```

---

## 二、大模型服务（LLM Service）

### 1. 核心定位

大模型服务是系统的"大脑"，负责理解接口文档、生成测试用例、分析依赖关系、诊断测试问题。系统使用DeepSeek和通义千问两个大模型，分别处理文本生成和多模态理解任务。

### 2. LLMService类详解

#### 2.1 核心功能

```python
class LLMService:
    """大模型服务，封装DeepSeek API调用"""
    
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL
        )
        self.model = settings.DEEPSEEK_MODEL  # "deepseek-chat"
```

**核心思想**：
- 使用OpenAI兼容的API接口，可以灵活切换不同的大模型服务商
- 统一封装API调用，屏蔽不同模型的差异
- 支持同步和异步调用

#### 2.2 主要方法

| 方法 | 作用 | 使用场景 |
|------|------|---------|
| `chat()` | 基础对话接口 | 通用文本生成任务 |
| `extract_structured_data()` | 从文本中提取结构化数据 | 解析接口文档，提取接口信息 |
| `generate_test_case()` | 生成测试用例 | 基于接口信息生成测试代码 |
| `analyze_error()` | 分析测试失败原因 | 测试失败后自动诊断问题 |
| `vision_parse()` | 多模态解析（图片+文本） | 解析PDF、Word等视觉文档 |
| `parse_visual_document()` | 解析视觉文档 | 从PDF/Word中提取接口信息 |

### 3. 实际应用示例

#### 示例1：生成测试用例

```python
# 场景：为登录接口生成测试用例
llm_service = LLMService()

api_info = {
    "name": "用户登录",
    "method": "POST",
    "url": "/api/login",
    "body": {
        "username": "string",
        "password": "string"
    },
    "response_schema": {
        "code": 200,
        "data": {
            "token": "string"
        }
    }
}

# 调用LLM生成测试用例
test_case = await llm_service.generate_test_case(api_info)

# 输出：
# {
#     "name": "用户登录成功",
#     "description": "验证用户使用正确的用户名和密码能够成功登录",
#     "test_data": {
#         "body": {
#             "username": "testuser",
#             "password": "Test123456"
#         }
#     },
#     "assertions": [
#         {"type": "status_code", "expected": 200},
#         {"type": "contains", "field": "data.token", "value": ""}
#     ]
# }
```

#### 示例2：分析测试失败原因

```python
# 场景：测试执行失败，需要分析原因
error_message = "AssertionError: Expected status code 200, got 401"
request_data = {
    "method": "POST",
    "url": "/api/login",
    "body": {"username": "testuser", "password": "wrong"}
}

# 调用LLM分析错误
analysis = await llm_service.analyze_error(error_message, request_data)

# 输出：
# {
#     "error_type": "认证失败",
#     "root_cause": "密码错误导致认证失败，返回401状态码",
#     "suggestions": [
#         "检查密码是否正确",
#         "确认用户账号是否被锁定",
#         "验证认证逻辑是否正确"
#     ],
#     "fix_method": "使用正确的密码重新测试"
# }
```

#### 示例3：解析视觉文档

```python
# 场景：从PDF文档中提取接口信息
image_paths = ["page1.png", "page2.png"]  # PDF转换的图片

# 调用多模态模型解析
interfaces = await llm_service.parse_visual_document(
    image_paths, 
    document_type="pdf"
)

# 输出：
# {
#     "interfaces": [
#         {
#             "name": "用户登录",
#             "method": "POST",
#             "url": "/api/login",
#             "headers": {},
#             "params": {},
#             "body": {"username": "string", "password": "string"},
#             "description": "用户登录接口",
#             "response_schema": {}
#         }
#     ]
# }
```

### 4. 为什么需要LLM Service？

1. **统一接口**：无论使用哪个大模型，调用方式都一样
2. **灵活切换**：可以轻松切换不同的模型和服务商
3. **错误处理**：统一处理API调用失败、超时等异常情况
4. **易于扩展**：可以轻松添加新功能（如流式输出、函数调用等）

---

## 三、文档解析模块

### 1. 核心定位

文档解析模块是系统的"入口"，负责将各种格式的接口文档（OpenAPI/Swagger、PDF、Word、Excel等）转换为系统可识别的结构化数据。

### 2. 支持的文档格式

| 格式 | 解析方式 | 使用场景 |
|------|---------|---------|
| **OpenAPI/Swagger** | JSON/YAML解析 | 标准化的API文档格式 |
| **Postman Collection** | JSON解析 | Postman导出的接口集合 |
| **PDF文档** | 多模态LLM解析 | 扫描版或图片格式的文档 |
| **Word文档** | 文本提取 + LLM理解 | Word格式的需求文档 |
| **Excel表格** | 表格解析 | Excel格式的接口清单 |
| **Markdown** | 文本解析 | Markdown格式的文档 |

### 3. 解析流程

```
用户上传文档
    ↓
DocumentParser识别文档类型
    ↓
根据类型选择解析器
    ├── JSON/YAML → 直接解析
    ├── PDF/Word → 转换为图片 → 多模态LLM解析
    └── Excel → 表格解析 → LLM标准化
    ↓
提取接口信息
    ├── 接口名称
    ├── HTTP方法
    ├── URL路径
    ├── 请求参数
    ├── 请求体
    ├── 响应格式
    └── 接口描述
    ↓
存储到数据库（document_api_interfaces表）
```

### 4. 核心实现

#### 4.1 标准格式解析（OpenAPI/Swagger）

```python
# 场景：解析OpenAPI文档
def parse_openapi(self, content: str) -> List[Dict]:
    """解析OpenAPI/Swagger文档"""
    if content.startswith('{'):
        data = json.loads(content)
    else:
        data = yaml.safe_load(content)
    
    interfaces = []
    paths = data.get("paths", {})
    
    for path, methods in paths.items():
        for method, details in methods.items():
            interface = {
                "name": details.get("summary", path),
                "method": method.upper(),
                "url": path,
                "description": details.get("description", ""),
                "parameters": details.get("parameters", []),
                "requestBody": details.get("requestBody", {}),
                "responses": details.get("responses", {})
            }
            interfaces.append(interface)
    
    return interfaces
```

#### 4.2 多模态文档解析（PDF/Word）

```python
# 场景：解析PDF文档
async def parse_pdf(self, file_path: str) -> List[Dict]:
    """解析PDF文档（使用多模态LLM）"""
    # 1. 将PDF转换为图片
    images = self.pdf_to_images(file_path)
    
    # 2. 使用多模态LLM解析
    llm_service = LLMService()
    interfaces = await llm_service.parse_visual_document(
        images, 
        document_type="pdf"
    )
    
    # 3. 标准化接口格式
    standardized_interfaces = self.standardize_interfaces(
        interfaces.get("interfaces", [])
    )
    
    return standardized_interfaces
```

### 5. 实际应用场景

#### 场景1：解析Swagger文档

```python
# 输入：Swagger JSON文档
swagger_doc = {
    "paths": {
        "/api/users": {
            "get": {
                "summary": "获取用户列表",
                "parameters": [
                    {"name": "page", "in": "query", "type": "integer"}
                ],
                "responses": {
                    "200": {
                        "description": "成功",
                        "schema": {"type": "array", "items": {"$ref": "#/definitions/User"}}
                    }
                }
            }
        }
    }
}

# 解析结果
interfaces = [
    {
        "name": "获取用户列表",
        "method": "GET",
        "url": "/api/users",
        "params": {"page": "integer"},
        "response_schema": {"type": "array"}
    }
]
```

#### 场景2：解析PDF需求文档

```python
# 输入：PDF文档（包含接口描述）
# PDF内容可能是：
# "用户登录接口
#  POST /api/login
#  请求参数：username, password
#  响应：{code: 200, data: {token: "xxx"}}"

# 解析流程：
# 1. PDF → 图片（page1.png, page2.png）
# 2. 多模态LLM识别图片中的接口信息
# 3. 提取结构化数据

# 输出：
interfaces = [
    {
        "name": "用户登录",
        "method": "POST",
        "url": "/api/login",
        "body": {"username": "string", "password": "string"},
        "response_schema": {"code": 200, "data": {"token": "string"}}
    }
]
```

### 6. 为什么需要文档解析？

1. **自动化**：无需手工录入接口信息
2. **多格式支持**：支持各种常见的文档格式
3. **智能理解**：使用LLM理解非结构化文档
4. **标准化**：将不同格式转换为统一的数据结构

---

## 四、测试用例生成模块

### 1. 核心定位

测试用例生成模块是系统的"核心引擎"，负责将接口信息转换为可执行的测试代码。系统支持生成pytest和JMeter两种格式的测试用例。

### 2. 生成器类型

| 生成器 | 输出格式 | 适用场景 |
|--------|---------|---------|
| **PytestCaseGenerator** | Python pytest代码 | 功能测试、接口测试 |
| **JMeterCaseGenerator** | JMeter脚本（JMX） | 性能测试、压力测试 |

### 3. 生成流程

```
接口信息
    ↓
分析接口特征
    ├── HTTP方法（GET/POST/PUT/DELETE）
    ├── 请求参数（路径参数、查询参数、请求体）
    ├── 响应格式（状态码、响应体结构）
    └── 依赖关系（前置接口、数据提取）
    ↓
构建提示词
    ├── 系统提示词（定义AI角色）
    ├── 用户提示词（接口信息 + 生成要求）
    └── Few-shot示例（参考高质量用例）
    ↓
调用大模型生成
    ├── 正常场景用例
    ├── 异常场景用例
    ├── 边界值用例
    └── 依赖场景用例
    ↓
代码后处理
    ├── 格式检查
    ├── 语法验证
    └── 依赖注入
    ↓
生成最终测试代码
```

### 4. PytestCaseGenerator详解

#### 4.1 核心功能

```python
class PytestCaseGenerator:
    """Pytest测试用例生成器"""
    
    def generate_test_case(
        self,
        api_interface: Dict[str, Any],
        test_data: Optional[Dict[str, Any]] = None,
        extracted_data: Optional[Dict[str, Any]] = None,
        assertions: Optional[List[Dict[str, Any]]] = None,
        use_llm: bool = True
    ) -> str:
        """生成pytest测试用例代码"""
```

**核心思想**：
- 支持LLM生成和模板生成两种方式
- LLM生成：使用大模型生成高质量测试代码
- 模板生成：基于模板快速生成标准测试用例

#### 4.2 生成示例

**输入：接口信息**
```python
api_interface = {
    "name": "用户登录",
    "method": "POST",
    "url": "/api/login",
    "body": {
        "username": "string",
        "password": "string"
    },
    "response_schema": {
        "code": 200,
        "data": {"token": "string"}
    }
}
```

**输出：pytest测试代码**
```python
import pytest
import requests
import allure

@allure.feature("用户登录")
class TestLogin:
    """用户登录接口测试"""
    
    @allure.story("正常登录")
    def test_login_success(self):
        """测试正常登录场景"""
        url = "http://api.example.com/api/login"
        headers = {"Content-Type": "application/json"}
        body = {
            "username": "testuser",
            "password": "Test123456"
        }
        
        response = requests.post(url, json=body, headers=headers)
        
        # 断言
        assert response.status_code == 200
        assert response.json()["code"] == 200
        assert "token" in response.json()["data"]
    
    @allure.story("密码错误")
    def test_login_wrong_password(self):
        """测试密码错误场景"""
        url = "http://api.example.com/api/login"
        headers = {"Content-Type": "application/json"}
        body = {
            "username": "testuser",
            "password": "wrongpassword"
        }
        
        response = requests.post(url, json=body, headers=headers)
        
        # 断言
        assert response.status_code == 401
        assert response.json()["code"] == 401
```

### 5. JMeterCaseGenerator详解

#### 5.1 核心功能

```python
# 场景：生成JMeter性能测试脚本
def generate_jmeter_script(
    self,
    interfaces: List[Dict[str, Any]],
    threads: int = 10,
    ramp_up: int = 1
) -> str:
    """生成JMeter测试脚本（JMX格式）"""
```

**核心思想**：
- 生成完整的JMX XML文件
- 包含Setup Thread Group（登录获取token）
- 包含Thread Group（性能测试）
- 包含断言和监听器

#### 5.2 生成示例

**输入：接口列表**
```python
interfaces = [
    {
        "name": "用户登录",
        "method": "POST",
        "url": "/api/login",
        "body": {"username": "testuser", "password": "Test123456"}
    },
    {
        "name": "获取用户信息",
        "method": "GET",
        "url": "/api/user/info",
        "headers": {"Authorization": "Bearer ${token}"}
    }
]
```

**输出：JMeter脚本（JMX）**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2">
    <!-- Setup Thread Group: 登录获取token -->
    <SetupThreadGroup>
        <HTTPSamplerProxy>
            <stringProp name="HTTPSampler.path">/api/login</stringProp>
            <stringProp name="HTTPSampler.method">POST</stringProp>
            <stringProp name="HTTPSampler.postBodyRaw">{"username":"testuser","password":"Test123456"}</stringProp>
        </HTTPSamplerProxy>
        <JSONPathExtractor>
            <stringProp name="JSON_PATH">$.data.token</stringProp>
            <stringProp name="VAR_NAME">token</stringProp>
        </JSONPathExtractor>
    </SetupThreadGroup>
    
    <!-- Thread Group: 性能测试 -->
    <ThreadGroup>
        <stringProp name="ThreadGroup.num_threads">10</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
        <HTTPSamplerProxy>
            <stringProp name="HTTPSampler.path">/api/user/info</stringProp>
            <stringProp name="HTTPSampler.method">GET</stringProp>
            <HeaderManager>
                <stringProp name="Header.name">Authorization</stringProp>
                <stringProp name="Header.value">Bearer ${token}</stringProp>
            </HeaderManager>
        </HTTPSamplerProxy>
        <ResponseAssertion>
            <stringProp name="Assertion.response_code">200</stringProp>
        </ResponseAssertion>
    </ThreadGroup>
</jmeterTestPlan>
```

### 6. Few-shot学习机制

#### 6.1 核心思想

Few-shot学习是指给大模型提供少量高质量示例，让模型学习如何生成类似的测试用例。

```python
# 场景：生成测试用例时提供Few-shot示例
few_shot_examples = [
    {
        "interface": {
            "name": "创建订单",
            "method": "POST",
            "url": "/api/orders"
        },
        "test_case": """
        def test_create_order_success(self):
            response = requests.post("/api/orders", json={...})
            assert response.status_code == 200
            assert response.json()["code"] == 200
        """
    }
]

# 构建提示词时包含示例
prompt = f"""
请为以下接口生成测试用例。

参考示例：
{few_shot_examples}

目标接口：
{api_interface}

请生成类似格式的测试用例。
"""
```

#### 6.2 为什么需要Few-shot？

1. **提高质量**：示例展示了高质量的测试用例格式
2. **保持一致性**：确保生成的用例风格统一
3. **减少错误**：模型可以参考示例避免常见错误

### 7. 为什么需要测试用例生成？

1. **自动化**：无需手工编写测试代码
2. **高质量**：LLM生成的用例覆盖全面
3. **可维护**：生成的代码结构清晰，易于维护
4. **多格式**：支持pytest和JMeter两种格式

---

## 五、接口依赖分析模块

### 1. 核心定位

接口依赖分析模块是系统的"关系网络分析器"，负责分析接口之间的依赖关系、调用顺序、数据流转，确保测试用例按正确顺序执行。

### 2. 依赖类型

| 依赖类型 | 描述 | 示例 |
|---------|------|------|
| **调用依赖** | 接口A的响应数据被接口B使用 | 登录接口返回token，其他接口需要token |
| **数据流依赖** | 接口A的输出作为接口B的输入 | 创建订单返回order_id，查询订单需要order_id |
| **业务逻辑依赖** | 接口的执行顺序有业务要求 | 必须先注册才能登录，必须先创建才能删除 |
| **状态依赖** | 接口的执行需要特定状态 | 支付接口需要订单状态为"待支付" |

### 3. 分析流程

```
接口列表
    ↓
提取接口特征
    ├── 请求参数（路径参数、查询参数、请求体）
    ├── 响应字段（状态码、响应体结构）
    ├── 接口描述（业务含义）
    └── URL模式（路径模式匹配）
    ↓
分析依赖关系
    ├── 参数匹配（A的响应字段 → B的请求参数）
    ├── URL模式匹配（路径参数依赖）
    ├── 业务逻辑分析（使用LLM分析）
    └── 数据库关系分析（表字段关联）
    ↓
构建依赖图
    ├── 节点（接口）
    ├── 边（依赖关系）
    └── 依赖链（调用链）
    ↓
拓扑排序
    ↓
生成执行顺序
```

### 4. APIDependencyAnalyzer详解

#### 4.1 核心方法

```python
class APIDependencyAnalyzer:
    """接口依赖分析器"""
    
    def analyze_dependencies(
        self, 
        interfaces: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析接口依赖关系"""
```

**核心思想**：
- 预处理接口字段，避免重复计算
- 使用多种策略分析依赖（参数匹配、LLM分析、数据库关系）
- 构建依赖图，进行拓扑排序

#### 4.2 分析示例

**输入：接口列表**
```python
interfaces = [
    {
        "id": 1,
        "name": "用户注册",
        "method": "POST",
        "url": "/api/register",
        "body": {"username": "string", "password": "string"},
        "response_schema": {"code": 200, "data": {"user_id": "integer"}}
    },
    {
        "id": 2,
        "name": "用户登录",
        "method": "POST",
        "url": "/api/login",
        "body": {"username": "string", "password": "string"},
        "response_schema": {"code": 200, "data": {"token": "string"}}
    },
    {
        "id": 3,
        "name": "获取用户信息",
        "method": "GET",
        "url": "/api/user/{user_id}",
        "headers": {"Authorization": "Bearer {token}"}
    }
]
```

**分析过程**：
1. **参数匹配**：接口3的路径参数`{user_id}`可能来自接口1的响应`user_id`
2. **Header依赖**：接口3需要`Authorization` header，可能来自接口2的响应`token`
3. **业务逻辑**：使用LLM分析，接口3需要先登录（接口2）才能获取用户信息

**输出：依赖关系**
```python
{
    "nodes": [
        {"id": 1, "name": "用户注册"},
        {"id": 2, "name": "用户登录"},
        {"id": 3, "name": "获取用户信息"}
    ],
    "edges": [
        {
            "source": 1,
            "target": 3,
            "type": "data_dependency",
            "data_flow": "user_id: response.data.user_id -> path.user_id"
        },
        {
            "source": 2,
            "target": 3,
            "type": "auth_dependency",
            "data_flow": "token: response.data.token -> header.Authorization"
        }
    ],
    "topological_order": [1, 2, 3]  # 执行顺序
}
```

### 5. LLM辅助分析

#### 5.1 核心思想

对于复杂的业务逻辑依赖，使用LLM分析接口之间的业务关系。

```python
async def _analyze_with_llm(
    self, 
    source_interface: Dict[str, Any], 
    target_interface: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """使用LLM分析接口依赖关系"""
    
    prompt = f"""
    请分析以下两个接口之间是否存在依赖关系。
    
    接口A：
    {json.dumps(source_interface, ensure_ascii=False)}
    
    接口B：
    {json.dumps(target_interface, ensure_ascii=False)}
    
    请分析：
    1. 接口B是否需要先调用接口A？
    2. 接口A的响应数据是否被接口B使用？
    3. 是否存在业务逻辑依赖？
    
    请以JSON格式输出分析结果。
    """
    
    result = await self.llm_service.chat(prompt)
    return json.loads(result)
```

#### 5.2 为什么需要LLM分析？

1. **业务理解**：LLM能理解接口的业务含义
2. **复杂关系**：能识别隐式的业务逻辑依赖
3. **上下文理解**：能结合接口描述和参数理解依赖关系

### 6. 拓扑排序

#### 6.1 核心思想

拓扑排序确保依赖的接口先执行，被依赖的接口后执行。

```python
def topological_sort(
    self, 
    dependency_graph: Dict[str, Any]
) -> List[int]:
    """拓扑排序：确定接口执行顺序"""
    
    # 构建入度表
    in_degree = {node["id"]: 0 for node in dependency_graph["nodes"]}
    for edge in dependency_graph["edges"]:
        in_degree[edge["target"]] += 1
    
    # 拓扑排序
    queue = [node["id"] for node in dependency_graph["nodes"] if in_degree[node["id"]] == 0]
    result = []
    
    while queue:
        node_id = queue.pop(0)
        result.append(node_id)
        
        # 更新依赖节点的入度
        for edge in dependency_graph["edges"]:
            if edge["source"] == node_id:
                in_degree[edge["target"]] -= 1
                if in_degree[edge["target"]] == 0:
                    queue.append(edge["target"])
    
    return result
```

#### 6.2 实际应用

```python
# 场景：确定测试用例执行顺序
interfaces = [接口1, 接口2, 接口3]
dependency_graph = analyze_dependencies(interfaces)
execution_order = topological_sort(dependency_graph)

# 输出：execution_order = [1, 2, 3]
# 含义：先执行接口1，再执行接口2，最后执行接口3
```

### 7. 为什么需要依赖分析？

1. **正确执行**：确保测试用例按正确顺序执行
2. **数据传递**：自动处理接口间的数据传递
3. **业务理解**：理解接口间的业务关系
4. **测试优化**：优化测试用例的组织和执行

---

## 六、知识图谱与向量检索

### 1. 核心定位

知识图谱和向量检索是系统的"记忆系统"，负责存储和检索接口关系、相似接口、历史测试数据，支持RAG（检索增强生成）提升测试用例生成质量。

### 2. 知识图谱（Neo4j）

#### 2.1 核心概念

知识图谱使用Neo4j图数据库存储接口关系网络，支持复杂的关系查询和可视化。

**节点类型**：
- `Interface` - API接口节点
- `Database` - 数据库节点
- `Table` - 数据表节点
- `Field` - 字段节点

**关系类型**：
- `DEPENDS_ON` - 接口依赖关系
- `CALLS` - 接口调用关系
- `USES` - 接口使用数据库表
- `CONTAINS` - 数据库包含表，表包含字段

#### 2.2 构建流程

```
接口依赖分析结果
    ↓
RelationshipAnalyzer分析关系
    ├── 接口依赖关系
    ├── 接口与数据库关系
    └── 数据库表关系
    ↓
存储到Neo4j
    ├── 创建Interface节点
    ├── 创建DEPENDS_ON关系
    └── 创建USES关系
    ↓
支持复杂查询
    ├── 查找接口的所有依赖
    ├── 查找接口调用的所有接口
    └── 查找使用相同数据库表的接口
```

#### 2.3 实际应用

```cypher
// 场景1：查找接口的所有依赖
MATCH (source:Interface {name: "获取用户信息"})-[r:DEPENDS_ON]->(target:Interface)
RETURN target.name, r.type

// 场景2：查找接口调用链
MATCH path = (start:Interface {name: "用户注册"})-[r:CALLS*]->(end:Interface)
RETURN path

// 场景3：查找使用相同数据库表的接口
MATCH (i1:Interface)-[:USES]->(t:Table)<-[:USES]-(i2:Interface)
WHERE i1 <> i2
RETURN i1.name, i2.name, t.name
```

### 3. 向量检索（Milvus）

#### 3.1 核心概念

向量检索使用Milvus向量数据库存储接口的向量表示，支持语义搜索和相似度匹配。

**核心流程**：
1. **向量化**：使用embedding模型将接口信息转换为向量
2. **存储**：将向量存储到Milvus
3. **检索**：根据查询向量找到相似的接口

#### 3.2 向量化流程

```python
# 场景：将接口信息向量化
from app.services.vector_service import VectorService

vector_service = VectorService()

interface = {
    "name": "用户登录",
    "method": "POST",
    "url": "/api/login",
    "description": "用户使用用户名和密码登录系统"
}

# 1. 构建文本（用于向量化）
text = f"{interface['name']} {interface['description']} {interface['url']}"

# 2. 向量化
embedding = await vector_service.embed_text(text)

# 3. 存储到Milvus
vector_service.insert(
    collection_name="api_interfaces",
    data=[{
        "id": interface["id"],
        "vector": embedding,
        "metadata": interface
    }]
)
```

#### 3.3 相似接口检索

```python
# 场景：查找与"用户登录"相似的接口
query_interface = {
    "name": "管理员登录",
    "description": "管理员使用账号和密码登录"
}

# 1. 向量化查询接口
query_text = f"{query_interface['name']} {query_interface['description']}"
query_embedding = await vector_service.embed_text(query_text)

# 2. 在Milvus中搜索相似向量
similar_interfaces = vector_service.search(
    collection_name="api_interfaces",
    query_vector=query_embedding,
    top_k=5
)

# 输出：找到5个相似的接口
# [
#     {"id": 1, "name": "用户登录", "similarity": 0.95},
#     {"id": 2, "name": "手机号登录", "similarity": 0.88},
#     ...
# ]
```

### 4. RAG（检索增强生成）

#### 4.1 核心思想

RAG是指在生成测试用例时，先从知识图谱和向量库中检索相关信息，然后将这些信息作为上下文传递给LLM，提升生成质量。

```python
# 场景：使用RAG生成测试用例
async def generate_with_rag(
    self,
    target_interface: Dict[str, Any]
) -> str:
    """使用RAG生成测试用例"""
    
    # 1. 从知识图谱检索相关接口
    related_interfaces = knowledge_graph_service.find_related_interfaces(
        target_interface["id"]
    )
    
    # 2. 从向量库检索相似接口
    similar_interfaces = vector_service.search_similar(
        target_interface,
        top_k=3
    )
    
    # 3. 构建上下文
    context = f"""
    相关接口：
    {json.dumps(related_interfaces, ensure_ascii=False)}
    
    相似接口的测试用例：
    {json.dumps(similar_interfaces, ensure_ascii=False)}
    """
    
    # 4. 使用上下文生成测试用例
    test_case = await llm_service.generate_test_case(
        target_interface,
        context=context
    )
    
    return test_case
```

#### 4.2 为什么需要RAG？

1. **提升质量**：参考相似接口的测试用例，生成更准确的用例
2. **保持一致性**：生成的用例风格与历史用例一致
3. **减少错误**：参考成功的用例，避免常见错误

### 5. 为什么需要知识图谱和向量检索？

1. **关系存储**：持久化存储接口关系，支持复杂查询
2. **相似匹配**：快速找到相似的接口和测试用例
3. **RAG增强**：提升测试用例生成质量
4. **可视化**：直观展示接口关系网络

---

## 七、异步任务处理（Celery）

### 1. 核心定位

异步任务处理是系统的"后台工作引擎"，负责处理耗时的任务（文档解析、测试用例生成、测试执行），不阻塞用户操作。

### 2. Celery架构

```
用户请求（FastAPI）
    ↓ 发送任务
Celery Broker（Redis）
    ↓ 任务队列
Celery Worker
    ├── 文档解析任务
    ├── 测试用例生成任务
    ├── 测试执行任务
    └── 报告生成任务
    ↓ 结果存储
Celery Backend（Redis）
    ↓ 返回结果
用户查询结果
```

### 3. 核心任务类型

| 任务类型 | 功能 | 超时时间 |
|---------|------|---------|
| `parse_document_task` | 解析文档 | 30分钟 |
| `generate_test_case_task` | 生成测试用例 | 30分钟 |
| `generate_scenario_test_case_task` | 生成场景测试用例 | 40分钟 |
| `generate_jmeter_performance_test_task` | 生成JMeter性能测试脚本 | 40分钟 |
| `execute_test_task` | 执行测试 | 60分钟 |
| `execute_performance_test_task` | 执行性能测试 | 60分钟 |
| `fix_test_case_with_deepseek_task` | 修复测试用例 | 10分钟 |

### 4. 任务实现示例

#### 4.1 文档解析任务

```python
@celery_app.task(bind=True, time_limit=1800, soft_time_limit=1500)
def parse_document_task(
    self,
    document_id: int,
    file_path: str,
    file_type: str
):
    """解析文档任务"""
    
    try:
        # 更新任务状态
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': '开始解析文档...'}
        )
        
        # 解析文档
        parser = DocumentParser()
        interfaces = await parser.parse(file_path, file_type)
        
        # 更新任务状态
        self.update_state(
            state='PROGRESS',
            meta={'progress': 80, 'message': '保存接口信息...'}
        )
        
        # 保存到数据库
        save_interfaces_to_db(document_id, interfaces)
        
        # 更新任务状态
        self.update_state(
            state='SUCCESS',
            meta={'progress': 100, 'message': '解析完成', 'interfaces_count': len(interfaces)}
        )
        
        return {
            'status': 'success',
            'interfaces_count': len(interfaces)
        }
    except Exception as e:
        self.update_state(
            state='FAILURE',
            meta={'error': str(e)}
        )
        raise
```

#### 4.2 测试用例生成任务

```python
@celery_app.task(bind=True, time_limit=1800, soft_time_limit=1500)
def generate_test_case_task(
    self,
    test_case_id: int,
    interface_id: int,
    use_llm: bool = True
):
    """生成测试用例任务"""
    
    try:
        # 更新任务状态
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': '准备生成测试用例...'}
        )
        
        # 获取接口信息
        interface = get_interface_by_id(interface_id)
        
        # 生成测试用例
        generator = PytestCaseGenerator(use_llm=use_llm)
        test_code = generator.generate_test_case(interface)
        
        # 更新任务状态
        self.update_state(
            state='PROGRESS',
            meta={'progress': 90, 'message': '保存测试用例...'}
        )
        
        # 保存测试用例
        save_test_case(test_case_id, test_code)
        
        # 更新任务状态
        self.update_state(
            state='SUCCESS',
            meta={'progress': 100, 'message': '生成完成'}
        )
        
        return {'status': 'success'}
    except Exception as e:
        self.update_state(
            state='FAILURE',
            meta={'error': str(e)}
        )
        raise
```

### 5. 任务状态管理

#### 5.1 状态类型

| 状态 | 描述 | 用户操作 |
|------|------|---------|
| **PENDING** | 任务等待执行 | 可以取消 |
| **PROGRESS** | 任务执行中 | 可以查看进度 |
| **SUCCESS** | 任务成功完成 | 可以查看结果 |
| **FAILURE** | 任务执行失败 | 可以查看错误信息，可以重试 |

#### 5.2 进度更新

```python
# 场景：更新任务进度
@celery_app.task(bind=True)
def long_running_task(self, data):
    """长时间运行的任务"""
    
    total_steps = 100
    
    for i in range(total_steps):
        # 执行任务步骤
        process_step(i)
        
        # 更新进度
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': int((i + 1) / total_steps * 100),
                'message': f'处理第 {i + 1} 步...',
                'current': i + 1,
                'total': total_steps
            }
        )
    
    return {'status': 'success', 'total': total_steps}
```

### 6. 断点续传机制

#### 6.1 核心思想

对于长时间运行的任务，支持断点续传，任务中断后可以从checkpoint恢复。

```python
@celery_app.task(bind=True, time_limit=2400)
def generate_scenario_test_case_task(
    self,
    test_case_id: int,
    interfaces_info: List[Dict[str, Any]]
):
    """生成场景测试用例（支持断点续传）"""
    
    # 1. 检查是否有checkpoint
    checkpoint = get_checkpoint(test_case_id)
    
    if checkpoint:
        # 从checkpoint恢复
        processed_interfaces = checkpoint.get("processed_interfaces", [])
        remaining_interfaces = [
            iface for iface in interfaces_info 
            if iface["id"] not in processed_interfaces
        ]
        print(f"[断点续传] 从checkpoint恢复，剩余 {len(remaining_interfaces)} 个接口")
    else:
        # 从头开始
        remaining_interfaces = interfaces_info
        processed_interfaces = []
    
    # 2. 处理剩余接口
    for interface in remaining_interfaces:
        # 生成测试用例
        test_code = generate_test_case(interface)
        
        # 保存checkpoint
        save_checkpoint(test_case_id, {
            "processed_interfaces": processed_interfaces + [interface["id"]],
            "test_code": test_code
        })
        
        processed_interfaces.append(interface["id"])
    
    return {'status': 'success'}
```

#### 6.2 为什么需要断点续传？

1. **可靠性**：任务中断后可以恢复，不需要重新开始
2. **效率**：避免重复处理已完成的部分
3. **用户体验**：长时间任务不会因为中断而丢失进度

### 7. 为什么需要异步任务处理？

1. **不阻塞**：耗时任务在后台执行，不阻塞用户操作
2. **可扩展**：可以启动多个Worker并行处理任务
3. **可靠性**：任务失败可以重试，支持断点续传
4. **进度可见**：用户可以实时查看任务进度

---

## 八、测试执行与报告生成

### 1. 核心定位

测试执行与报告生成模块是系统的"执行引擎"，负责执行pytest和JMeter测试，收集测试结果，生成详细的测试报告。

### 2. 测试执行流程

```
用户创建测试任务
    ↓
分析接口依赖关系
    ↓
排序测试用例（按依赖关系）
    ↓
准备测试数据
    ├── 生成测试数据
    ├── 注入依赖数据（token、ID等）
    └── 配置测试环境
    ↓
执行测试
    ├── pytest执行（功能测试）
    └── JMeter执行（性能测试）
    ↓
收集测试结果
    ├── 测试通过/失败
    ├── 执行时间
    ├── 错误信息
    └── 响应数据
    ↓
生成测试报告
    ├── Allure报告
    ├── HTML报告
    └── LLM分析报告（性能测试）
```

### 3. Pytest测试执行

#### 3.1 核心实现

```python
class TestExecutor:
    """测试执行器"""
    
    def execute_pytest(
        self,
        test_case_ids: List[int],
        environment_id: int
    ) -> Dict[str, Any]:
        """执行pytest测试"""
        
        # 1. 获取测试用例代码
        test_cases = get_test_cases(test_case_ids)
        
        # 2. 获取测试环境配置
        environment = get_test_environment(environment_id)
        
        # 3. 准备测试文件
        test_file = self._prepare_test_file(test_cases, environment)
        
        # 4. 执行pytest
        result = subprocess.run(
            ["pytest", test_file, "--alluredir", "allure-results"],
            capture_output=True,
            text=True
        )
        
        # 5. 解析测试结果
        test_results = self._parse_pytest_results(result)
        
        # 6. 生成Allure报告
        allure_report = self._generate_allure_report()
        
        return {
            'status': 'success',
            'results': test_results,
            'report_path': allure_report
        }
```

#### 3.2 测试结果解析

```python
# 场景：解析pytest测试结果
def _parse_pytest_results(self, result: subprocess.CompletedProcess) -> List[Dict]:
    """解析pytest测试结果"""
    
    # pytest输出示例：
    # test_login.py::TestLogin::test_login_success PASSED
    # test_login.py::TestLogin::test_login_wrong_password FAILED
    
    test_results = []
    lines = result.stdout.split('\n')
    
    for line in lines:
        if '::' in line and ('PASSED' in line or 'FAILED' in line):
            parts = line.split('::')
            test_file = parts[0]
            test_class = parts[1] if len(parts) > 2 else None
            test_method = parts[-1].split()[0]
            status = 'PASSED' if 'PASSED' in line else 'FAILED'
            
            test_results.append({
                'test_file': test_file,
                'test_class': test_class,
                'test_method': test_method,
                'status': status
            })
    
    return test_results
```

### 4. JMeter性能测试执行

#### 4.1 核心实现

```python
def execute_jmeter(
    self,
    jmx_file: str,
    threads: int = 10,
    ramp_up: int = 1,
    duration: int = 60
) -> Dict[str, Any]:
    """执行JMeter性能测试"""
    
    # 1. 执行JMeter
    result = subprocess.run(
        [
            "jmeter", "-n", "-t", jmx_file,
            "-l", "result.jtl",
            "-e", "-o", "html-report",
            "-Jthreads", str(threads),
            "-Jrampup", str(ramp_up),
            "-Jduration", str(duration)
        ],
        capture_output=True,
        text=True
    )
    
    # 2. 解析JMeter结果
    performance_data = self._parse_jmeter_results("result.jtl")
    
    # 3. 使用LLM分析性能瓶颈
    analysis = await self._analyze_performance_with_llm(performance_data)
    
    return {
        'status': 'success',
        'performance_data': performance_data,
        'analysis': analysis,
        'report_path': 'html-report/index.html'
    }
```

#### 4.2 LLM性能分析

```python
async def _analyze_performance_with_llm(
    self,
    performance_data: Dict[str, Any]
) -> Dict[str, Any]:
    """使用LLM分析性能测试结果"""
    
    llm_service = LLMService()
    
    prompt = f"""
    请分析以下性能测试结果，识别性能瓶颈并提供优化建议。
    
    性能数据：
    {json.dumps(performance_data, ensure_ascii=False, indent=2)}
    
    请分析：
    1. 响应时间是否满足要求
    2. 吞吐量是否达到预期
    3. 错误率是否在可接受范围
    4. 识别性能瓶颈
    5. 提供优化建议
    
    请以JSON格式输出分析结果。
    """
    
    analysis = await llm_service.chat(prompt, temperature=0.3)
    return json.loads(analysis)
```

### 5. 报告生成

#### 5.1 Allure报告

```python
def generate_allure_report(self, results_dir: str) -> str:
    """生成Allure测试报告"""
    
    # 1. 生成Allure报告
    subprocess.run(
        ["allure", "generate", results_dir, "-o", "allure-report", "--clean"],
        check=True
    )
    
    # 2. 返回报告路径
    return "allure-report/index.html"
```

#### 5.2 自定义HTML报告

```python
def generate_html_report(
    self,
    test_results: List[Dict[str, Any]]
) -> str:
    """生成自定义HTML报告"""
    
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>测试报告</title>
    </head>
    <body>
        <h1>测试执行报告</h1>
        <table>
            <tr>
                <th>测试用例</th>
                <th>状态</th>
                <th>执行时间</th>
            </tr>
            {% for result in test_results %}
            <tr>
                <td>{{ result.test_case }}</td>
                <td>{{ result.status }}</td>
                <td>{{ result.duration }}ms</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    
    # 渲染模板
    html_content = render_template(html_template, test_results=test_results)
    
    # 保存HTML文件
    report_path = "reports/test_report.html"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return report_path
```

### 6. 为什么需要测试执行与报告生成？

1. **自动化**：自动执行测试，无需手工操作
2. **详细报告**：生成详细的测试报告，便于分析问题
3. **性能分析**：使用LLM分析性能瓶颈，提供优化建议
4. **可追溯**：记录每次测试的执行结果，支持历史追溯

---

## 九、数据流转与系统架构

### 1. 核心定位

数据流转是指数据在系统各个模块之间传递和转换的过程，从文档上传到测试报告生成的完整流程。

### 2. 完整数据流

```
用户上传文档（PDF/Word/OpenAPI）
    ↓
【文档解析模块】
    ├── 解析文档格式
    ├── 提取接口信息
    └── 使用LLM智能理解
    ↓
DocumentAPIInterface（结构化接口数据）
    ↓
【接口依赖分析模块】
    ├── 分析接口依赖关系
    ├── 构建依赖图
    └── 存储到Neo4j知识图谱
    ↓
DependencyGraph（依赖关系图）
    ↓
【测试用例生成模块】
    ├── 使用LLM生成测试用例
    ├── 参考Few-shot示例
    └── 使用RAG增强生成
    ↓
TestCase（测试用例代码）
    ↓
【测试执行模块】
    ├── 分析依赖关系
    ├── 排序测试用例
    ├── 准备测试数据
    └── 执行pytest/JMeter
    ↓
TestResult（测试结果）
    ↓
【报告生成模块】
    ├── 生成Allure报告
    ├── 生成HTML报告
    └── 使用LLM分析结果
    ↓
TestReport（测试报告）
```

### 3. 数据转换过程

#### 阶段1：非结构化 → 结构化

```python
# 输入：PDF文档（非结构化）
pdf_content = """
用户登录接口
POST /api/login
请求参数：username, password
响应：{code: 200, data: {token: "xxx"}}
"""

# 输出：结构化JSON
{
    "name": "用户登录",
    "method": "POST",
    "url": "/api/login",
    "body": {
        "username": "string",
        "password": "string"
    },
    "response_schema": {
        "code": 200,
        "data": {"token": "string"}
    }
}
```

#### 阶段2：接口 → 依赖关系图

```python
# 输入：接口列表
interfaces = [
    {"id": 1, "name": "用户注册", "method": "POST", "url": "/api/register"},
    {"id": 2, "name": "用户登录", "method": "POST", "url": "/api/login"},
    {"id": 3, "name": "获取用户信息", "method": "GET", "url": "/api/user/{user_id}"}
]

# 输出：依赖关系图
{
    "nodes": [接口1, 接口2, 接口3],
    "edges": [
        {"source": 2, "target": 3, "type": "auth_dependency"},
        {"source": 1, "target": 3, "type": "data_dependency"}
    ],
    "topological_order": [1, 2, 3]  # 执行顺序
}
```

#### 阶段3：接口信息 → 测试用例代码

```python
# 输入：接口信息 + 依赖关系
interface = {
    "name": "获取用户信息",
    "method": "GET",
    "url": "/api/user/{user_id}",
    "dependencies": [
        {"type": "auth", "source": "登录接口", "extract": "token"}
    ]
}

# 输出：pytest测试代码
test_code = """
import pytest
import requests

def test_get_user_info():
    # 先登录获取token
    login_response = requests.post("/api/login", json={...})
    token = login_response.json()["data"]["token"]
    
    # 使用token获取用户信息
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get("/api/user/123", headers=headers)
    
    assert response.status_code == 200
    assert "user_id" in response.json()
"""
```

### 4. 为什么需要数据流转？

1. **流程化**：每个阶段的输出是下一阶段的输入，形成完整的测试流程
2. **可追溯**：可以追溯到每个测试用例的来源（从哪个文档、哪个接口生成）
3. **自动化**：整个流程自动化，无需手工干预
4. **可扩展**：可以轻松添加新的处理阶段

---

## 十、提示词工程

### 1. 核心定位

提示词工程是通过精心设计的提示词，引导大模型生成高质量测试用例的技术。就像"教学大纲"一样，告诉AI"要做什么"和"怎么做"。

### 2. 提示词组成

提示词通常由三部分组成：

| 组成部分 | 作用 | 示例 |
|---------|------|------|
| **系统提示词（System Prompt）** | 定义AI的角色和能力 | "你是一个专业的测试工程师，擅长编写高质量的pytest测试用例" |
| **用户提示词（User Prompt）** | 定义具体任务和输入数据 | "请为以下接口生成测试用例：[接口信息]" |
| **Few-shot示例** | 提供高质量示例供AI参考 | "参考以下示例：[示例代码]" |

### 3. 实际应用示例

#### 示例1：测试用例生成提示词

```python
# 系统提示词
system_prompt = """
你是一个专业的测试工程师，擅长编写高质量的pytest测试用例。

你的专业能力包括：
1. 理解API接口的功能和业务逻辑
2. 设计全面的测试场景（正常、异常、边界）
3. 编写清晰、可维护的测试代码
4. 使用合适的断言验证测试结果

请确保生成的测试用例：
- 代码结构清晰，符合pytest规范
- 包含必要的注释和说明
- 使用Allure注解生成详细报告
- 考虑各种测试场景
"""

# 用户提示词
user_prompt = """
请为以下API接口生成pytest测试用例。

接口信息：
{
    "name": "用户登录",
    "method": "POST",
    "url": "/api/login",
    "body": {
        "username": "string",
        "password": "string"
    },
    "response_schema": {
        "code": 200,
        "data": {"token": "string"}
    }
}

要求：
1. 生成正常登录场景的测试用例
2. 生成密码错误场景的测试用例
3. 生成用户名不存在场景的测试用例
4. 使用Allure注解
5. 包含详细的断言

请输出完整的pytest测试代码。
"""
```

#### 示例2：接口依赖分析提示词

```python
prompt = """
请分析以下两个接口之间是否存在依赖关系。

接口A：用户登录
- URL: POST /api/login
- 请求: {"username": "string", "password": "string"}
- 响应: {"code": 200, "data": {"token": "xxx"}}

接口B：获取用户信息
- URL: GET /api/user/{user_id}
- 请求头: {"Authorization": "Bearer {token}"}

请分析：
1. 接口B是否需要先调用接口A？
2. 接口A的响应数据是否被接口B使用？
3. 如果存在依赖，依赖关系是什么类型（认证依赖、数据依赖等）？

请以JSON格式输出分析结果。
"""
```

### 4. 提示词技巧

#### 技巧1：明确角色定位

```python
# 好的提示词：明确角色
"你是一个专业的测试工程师，有10年测试经验，擅长API测试"

# 不好的提示词：角色不明确
"请生成测试用例"
```

#### 技巧2：提供结构化输出格式

```python
# 好的提示词：明确输出格式
"""
请以JSON格式输出，格式如下：
{
    "test_cases": [
        {
            "name": "测试用例名称",
            "test_data": {...},
            "assertions": [...]
        }
    ]
}
"""

# 不好的提示词：格式不明确
"请生成测试用例"
```

#### 技巧3：提供Few-shot示例

```python
# 好的提示词：包含示例
"""
参考以下示例：

接口：创建订单
测试用例：
def test_create_order_success():
    response = requests.post("/api/orders", json={...})
    assert response.status_code == 200

请为以下接口生成类似的测试用例：
[目标接口信息]
"""

# 不好的提示词：没有示例
"请生成测试用例"
```

### 5. 为什么需要提示词工程？

1. **提高质量**：好的提示词能让AI生成更准确的测试用例
2. **保持一致性**：统一的提示词确保生成的用例风格一致
3. **可维护性**：提示词独立存储，便于修改和优化
4. **可复用性**：同一套提示词可以用于不同的项目和接口

---

## 十一、Few-shot学习与场景化生成

### 1. 核心定位

Few-shot学习是指给大模型提供少量高质量示例，让模型学习如何生成类似的测试用例。就像"模仿学习"一样，AI看到好的例子后，能生成类似质量的输出。

### 2. Few-shot学习机制

#### 2.1 核心思想

```python
# 场景：生成测试用例时提供Few-shot示例

# 步骤1：准备高质量示例
few_shot_examples = [
    {
        "interface": {
            "name": "创建订单",
            "method": "POST",
            "url": "/api/orders"
        },
        "test_case": """
        @allure.feature("订单管理")
        class TestCreateOrder:
            @allure.story("创建订单成功")
            def test_create_order_success(self):
                url = "http://api.example.com/api/orders"
                headers = {"Content-Type": "application/json"}
                body = {
                    "product_id": 123,
                    "quantity": 2
                }
                response = requests.post(url, json=body, headers=headers)
                assert response.status_code == 200
                assert response.json()["code"] == 200
                assert "order_id" in response.json()["data"]
        """
    }
]

# 步骤2：构建提示词（包含示例）
prompt = f"""
请为以下接口生成测试用例。

参考示例：
{few_shot_examples}

目标接口：
{target_interface}

请生成类似格式的测试用例。
"""

# 步骤3：调用LLM生成
test_case = await llm_service.chat(prompt)
```

#### 2.2 示例来源

Few-shot示例可以从以下来源获取：

1. **历史测试用例**：从数据库中获取之前生成的高质量测试用例
2. **手动编写**：测试工程师手动编写的标准测试用例
3. **开源项目**：从GitHub等开源项目中获取的优秀测试用例

### 3. 场景化生成

#### 3.1 核心思想

场景化生成是指基于接口依赖关系，生成完整的业务场景测试用例，而不是单独测试每个接口。

```python
# 场景：生成"用户下单"场景的测试用例

# 步骤1：分析场景依赖
scenario_dependencies = [
    {
        "step": 1,
        "interface": "用户登录",
        "purpose": "获取token",
        "extract": "token"
    },
    {
        "step": 2,
        "interface": "查看商品列表",
        "purpose": "获取商品ID",
        "extract": "product_id"
    },
    {
        "step": 3,
        "interface": "创建订单",
        "purpose": "创建订单",
        "extract": "order_id",
        "dependencies": ["token", "product_id"]
    },
    {
        "step": 4,
        "interface": "查询订单",
        "purpose": "验证订单创建成功",
        "dependencies": ["token", "order_id"]
    }
]

# 步骤2：生成场景测试用例
scenario_test_case = """
@allure.feature("用户下单场景")
class TestUserOrderScenario:
    def test_user_order_flow(self):
        # 步骤1：用户登录
        login_response = requests.post("/api/login", json={...})
        token = login_response.json()["data"]["token"]
        
        # 步骤2：查看商品列表
        headers = {"Authorization": f"Bearer {token}"}
        products_response = requests.get("/api/products", headers=headers)
        product_id = products_response.json()["data"][0]["id"]
        
        # 步骤3：创建订单
        order_body = {"product_id": product_id, "quantity": 1}
        order_response = requests.post("/api/orders", json=order_body, headers=headers)
        order_id = order_response.json()["data"]["order_id"]
        
        # 步骤4：查询订单验证
        order_detail_response = requests.get(f"/api/orders/{order_id}", headers=headers)
        assert order_detail_response.status_code == 200
        assert order_detail_response.json()["data"]["order_id"] == order_id
"""
```

#### 3.2 为什么需要场景化生成？

1. **业务完整性**：测试完整的业务流程，而不只是单个接口
2. **真实场景**：更接近用户实际使用场景
3. **依赖验证**：验证接口之间的依赖关系是否正确
4. **效率提升**：一次性测试多个接口，提高测试效率

### 4. 实际应用

在我们的系统中，Few-shot学习和场景化生成被广泛应用于：

1. **测试用例生成**：提供历史高质量用例作为示例
2. **场景测试用例生成**：基于接口依赖关系生成完整场景
3. **性能测试脚本生成**：参考已有的JMeter脚本生成新的脚本

---

## 十二、系统在本项目中的实际应用总结

### 1. 项目架构概览

我们的API接口智能测试系统完全基于现代化技术栈构建，以下是系统在项目中的具体应用：

```
用户浏览器（React前端）
    ↓ HTTP请求
FastAPI后端服务
    ├── 文档解析服务（DocumentParser）
    ├── 测试用例生成服务（TestCaseGenerator）
    ├── 接口依赖分析服务（APIDependencyAnalyzer）
    ├── 测试执行服务（TestExecutor）
    └── 报告生成服务（ReportGenerator）
    ↓ 异步任务
Celery Worker（后台任务处理）
    ├── 调用大模型（DeepSeek/通义千问）
    ├── 执行pytest测试
    └── 执行JMeter性能测试
    ↓ 数据存储
MySQL（主数据库） + Redis（缓存） + Neo4j（知识图谱） + Milvus（向量检索）
```

### 2. 核心技术应用点

#### 2.1 大模型服务（LLMService）

**位置**：`backend/app/services/llm_service.py`

```python
class LLMService:
    """大模型服务，封装DeepSeek API调用"""
    
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL
        )
        self.model = settings.DEEPSEEK_MODEL
```

**应用场景**：
- 文档解析：使用多模态模型解析PDF/Word文档
- 测试用例生成：生成pytest和JMeter测试用例
- 错误分析：分析测试失败原因，提供修复建议
- 性能分析：分析性能测试结果，识别瓶颈

#### 2.2 文档解析模块（DocumentParser）

**位置**：`backend/app/services/document_parser.py`

**支持格式**：
- OpenAPI/Swagger（JSON/YAML）
- Postman Collection
- PDF/Word（使用多模态LLM）
- Excel/Markdown
- JMeter脚本（JMX）

**工作流程**：
1. 识别文档类型
2. 选择合适的解析器
3. 提取接口信息
4. 使用LLM标准化数据
5. 存储到数据库

#### 2.3 测试用例生成模块（TestCaseGenerator）

**位置**：`backend/app/services/test_case_generator.py`

**生成器类型**：
- `PytestCaseGenerator`：生成pytest格式测试用例
- `JMeterCaseGenerator`：生成JMeter性能测试脚本

**生成流程**：
1. 分析接口特征
2. 构建提示词（包含Few-shot示例）
3. 调用大模型生成
4. 代码后处理（格式检查、依赖注入）
5. 保存测试用例

#### 2.4 接口依赖分析模块（APIDependencyAnalyzer）

**位置**：`backend/app/services/api_dependency_analyzer.py`

**分析策略**：
1. **参数匹配**：分析请求参数和响应字段的匹配关系
2. **URL模式匹配**：识别路径参数依赖
3. **LLM分析**：使用大模型分析业务逻辑依赖
4. **数据库关系分析**：结合数据库表关系分析依赖

**输出**：
- 依赖关系图（节点+边）
- 拓扑排序结果（执行顺序）
- 依赖链（调用链）

#### 2.5 知识图谱与向量检索

**知识图谱（Neo4j）**：
- 存储接口节点和依赖关系
- 支持复杂查询（查找依赖链、查找使用相同表的接口）
- 可视化展示接口关系网络

**向量检索（Milvus）**：
- 存储接口的向量表示
- 支持语义搜索（查找相似接口）
- 支持RAG增强生成（参考相似接口生成测试用例）

#### 2.6 异步任务处理（Celery）

**位置**：`backend/app/celery_tasks.py`

**主要任务**：
- `parse_document_task`：解析文档
- `generate_test_case_task`：生成测试用例
- `generate_scenario_test_case_task`：生成场景测试用例
- `execute_test_task`：执行测试
- `fix_test_case_with_deepseek_task`：修复测试用例

**特性**：
- 支持任务状态管理（PENDING/PROGRESS/SUCCESS/FAILURE）
- 支持进度更新
- 支持断点续传
- 支持任务重试

### 3. 完整业务流程

#### 流程1：从文档到测试用例

```
1. 用户上传接口文档（PDF/OpenAPI/Word等）
   ↓
2. 文档解析任务（Celery）
   - DocumentParser解析文档
   - 提取接口信息
   - 存储到document_api_interfaces表
   ↓
3. 用户选择接口生成测试用例
   ↓
4. 测试用例生成任务（Celery）
   - TestCaseGenerator生成测试代码
   - 使用LLM生成
   - 参考Few-shot示例
   - 存储到test_cases表
   ↓
5. 用户查看生成的测试用例
```

#### 流程2：从接口到场景测试

```
1. 用户选择多个接口创建测试用例集
   ↓
2. 接口依赖分析
   - APIDependencyAnalyzer分析依赖关系
   - 构建依赖图
   - 存储到Neo4j
   ↓
3. 生成场景测试用例
   - 基于依赖关系生成完整场景
   - 考虑接口执行顺序
   - 处理数据传递（token、ID等）
   ↓
4. 执行场景测试
   - 按依赖顺序执行
   - 自动处理数据传递
   - 收集测试结果
   ↓
5. 生成测试报告
   - Allure报告
   - HTML报告
   - LLM分析报告
```

### 4. 技术亮点总结

1. **AI驱动的测试用例生成**：使用大模型自动生成高质量测试用例
2. **智能依赖分析**：结合规则引擎和LLM分析接口依赖关系
3. **知识图谱存储**：使用Neo4j存储接口关系，支持复杂查询
4. **向量检索增强**：使用Milvus进行语义搜索，支持RAG增强生成
5. **异步任务处理**：使用Celery处理耗时任务，支持断点续传
6. **Few-shot学习**：提供高质量示例，提升生成质量
7. **场景化生成**：基于依赖关系生成完整业务场景测试用例
8. **多模态文档解析**：支持PDF/Word等视觉文档解析

### 5. 系统优势

1. **自动化程度高**：从文档解析到测试报告生成全流程自动化
2. **智能化水平高**：使用AI技术提升测试用例质量和分析能力
3. **可扩展性强**：模块化设计，易于扩展新功能
4. **用户体验好**：异步任务处理，不阻塞用户操作
5. **数据完整性**：完整的数据流转和追溯机制

---

## 总结

API接口智能测试系统是一个集成了AI技术、知识图谱、向量检索等先进技术的智能测试平台。通过本课程的学习，你应该能够：

1. **理解系统核心定位**：系统如何解决传统API测试的痛点
2. **掌握核心技术**：大模型服务、文档解析、用例生成、依赖分析等
3. **理解数据流转**：从文档到测试报告的完整流程
4. **掌握最佳实践**：提示词工程、Few-shot学习、场景化生成等
5. **了解系统架构**：前后端分离、异步任务、数据存储等

希望这个课程体系能帮助你更好地理解和使用API接口智能测试系统！