# 🤖 LLM标准化与接口识别

> 理解如何用DeepSeek LLM智能理解文档内容并标准化接口定义

---

## 目录
1. [为什么需要LLM标准化](#为什么需要llm标准化)
2. [LLM理解的工作原理](#llm理解的工作原理)
3. [提示词设计](#提示词设计)
4. [接口信息提取](#接口信息提取)
5. [数据标准化](#数据标准化)
6. [处理非结构化文档](#处理非结构化文档)

---

## 为什么需要LLM标准化

### 现实问题

**情景1：PDF文档**
```
原始内容（混乱的格式）：
"
用户登录功能

使用POST方式，调用 /login

需要传入username和password
成功时返回token

失败时返回错误信息
"

问题：
  ❌ 字段定义不清楚
  ❌ 参数类型不明确
  ❌ 响应格式无法确定
  ❌ 错误码信息缺失
```

**情景2：混合格式的Word文档**
```
问题：
  ❌ 表格和文字混合
  ❌ 排版混乱
  ❌ 特殊符号乱码
  ❌ 难以自动解析
```

**情景3：自然语言描述**
```
原始内容：
"
用户需要先注册后才能登录。
注册时需要提供邮箱地址。
注册完成后会发送确认邮件。
用户点击邮件中的链接才能激活账户。
激活后就可以登录了。
"

问题：
  ❌ 隐含的依赖关系（注册→登录→激活）
  ❌ 必需字段不明确
  ❌ 响应格式完全缺失
  ❌ 需要人工理解和编写
```

### LLM的解决方案

```
LLM + 好的提示词 = 智能理解
  ↓
✅ 理解自然语言
✅ 推断缺失信息
✅ 识别隐含的业务逻辑
✅ 补充必要的字段
✅ 输出结构化数据
```

**LLM的优势**：

| 传统规则匹配 | LLM方法 |
|-------------|--------|
| ❌ 只能识别特定格式 | ✅ 支持任意格式 |
| ❌ 对格式混乱敏感 | ✅ 鲁棒性强 |
| ❌ 无法推理关系 | ✅ 能理解业务逻辑 |
| ❌ 缺失字段无法补充 | ✅ 自动补充缺失信息 |
| ❌ 需要维护多套规则 | ✅ 一套提示词适用所有格式 |

---

## LLM理解的工作原理

### 三步工作流

```
┌──────────────────────┐
│ 步骤1: 输入原始文档   │ ◀── 用户上传的任意格式文件
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 步骤2: 提示词引导     │ ◀── 系统提示词（系统角色）
│        LLM理解        │     用户提示词（任务说明）
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 步骤3: 返回结果       │ ──▶ 标准化的JSON结果
└──────────────────────┘
```

### 内部原理

**LLM理解过程**：
```
输入：非结构化的API文档片段
  │
  ├─ Token化：分解为字符和单词
  │
  ├─ 上下文理解：
  │   - 识别关键词（POST、GET、URL等）
  │   - 理解词间关系（参数、响应、状态码）
  │   - 推断隐含信息（认证需求、业务流程）
  │
  ├─ 信息抽取：
  │   - 识别接口基本信息
  │   - 识别请求参数
  │   - 识别响应格式
  │   - 识别业务约束
  │
  └─ 生成结果：
      - 按照提示词要求的格式
      - 补充缺失的字段
      - 确保逻辑一致性
```

**温度参数的作用**：
```
temperature = 0.2（低温，默认）
  → 输出更确定、更"严谨"
  → 适合结构化任务（如提取接口定义）
  
temperature = 0.7（正常）
  → 输出更多样化
  → 适合创意任务（如写文案）
  
temperature = 1.5（高温）
  → 输出更随意
  → 不适合结构化任务
```

我们**故意使用低温度（0.2）**来确保接口定义的准确性。

---

## 提示词设计

### 提示词的两个部分

```
提示词 = 系统提示词 + 用户提示词
```

#### 1. 系统提示词 (System Prompt)

**目的**：定义LLM的角色和行为规范

**最佳实践**：

```python
system_prompt = """
你是一个资深的API文档分析专家，拥有15年的API设计和文档编写经验。

你的专长：
1. 理解各种格式的API文档（结构化、非结构化、混合格式）
2. 识别和补充缺失的API定义信息
3. 按照行业最佳实践标准化API定义
4. 处理多种语言的文档

你的工作方式：
1. 仔细阅读用户提供的文档
2. 识别所有接口定义
3. 补充任何缺失的必要字段
4. 按照标准JSON格式返回结果
5. 如果信息不足，使用合理的默认值或标记为"待确认"

重要规则：
1. 必须返回有效的JSON格式
2. 参数类型使用标准的JSON Schema类型（string, integer, boolean, object, array）
3. 标注哪些字段是必需的（required: true）
4. 包含字段的含义说明（description）
5. 如果有多个可能的解释，选择最合理的
6. 不要编造不存在的接口或字段
7. 保持原文档中的接口名称和URL

输出格式：只返回有效的JSON，不要包含其他说明文字。
"""
```

#### 2. 用户提示词 (User Prompt)

**目的**：说明具体的任务和期望

**最佳实践**：

```python
user_prompt = """
请分析以下API文档，提取所有接口信息并转换为标准的JSON格式。

【原始文档内容】
{原始文档内容}

【输出要求】
请以JSON格式返回结果，包含以下结构：

{{
  "interfaces": [
    {{
      "name": "接口名称",
      "method": "HTTP方法(GET/POST/PUT/DELETE/PATCH)",
      "url": "接口路径，如 /api/users 或 /api/users/{{id}}",
      "description": "接口的功能说明",
      
      "request": {{
        "headers": {{
          "header_name": {{
            "type": "string/integer/boolean",
            "required": true/false,
            "description": "说明",
            "example": "示例值"
          }}
        }},
        "params": {{
          "param_name": {{
            "type": "string/integer/boolean/array/object",
            "required": true/false,
            "description": "说明",
            "example": "示例值"
          }}
        }},
        "body": {{
          "type": "object/array",
          "required": true/false,
          "properties": {{
            "field_name": {{
              "type": "string/integer/boolean/array/object",
              "required": true/false,
              "description": "字段说明",
              "example": "示例值"
            }}
          }}
        }}
      }},
      
      "response": {{
        "status_code": 200,
        "body": {{
          "type": "object",
          "properties": {{
            "code": {{"type": "integer", "description": "状态码"}},
            "message": {{"type": "string", "description": "提示信息"}},
            "data": {{"type": "object", "description": "返回数据"}}
          }}
        }},
        "example": {{
          "code": 0,
          "message": "成功",
          "data": {{}}
        }}
      }},
      
      "error_responses": {{
        "400": {{"description": "参数错误"}},
        "401": {{"description": "未授权"}},
        "500": {{"description": "服务器错误"}}
      }},
      
      "tags": ["分类标签"],
      "authentication": "是否需要认证(true/false)",
      "notes": "其他说明"
    }}
  ]
}}

【特殊说明】
1. 如果文档中没有某些信息，请使用合理的推断：
   - 标准的 CRUD 接口通常遵循 POST (创建) → GET (读) → PUT (更新) → DELETE (删除)
   - 创建接口通常返回 201，其他操作返回 200
   - 大多数接口需要认证，除非特别说明是公开的

2. 对于参数，请明确标注：
   - 必需参数 (required: true)
   - 可选参数 (required: false)
   - 参数的数据类型
   - 参数的含义

3. 对于响应，请包含：
   - 成功响应 (200/201)
   - 常见的错误响应 (400, 401, 403, 404, 500)
   - 响应体的完整结构

4. 如果有多个接口，请按照逻辑顺序排列（通常是创建→读→更新→删除）

请现在开始分析，只返回JSON结果，不要添加其他说明。
"""
```

### 提示词的优化技巧

**1. 使用角色扮演**

```python
# ❌ 不好的写法
prompt = "请提取接口信息"

# ✅ 好的写法
prompt = """
你是一个资深的API文档分析专家。
请从以下文档中提取接口信息...
"""
```

**2. 明确输出格式**

```python
# ❌ 不好的写法
prompt = "请提取接口并返回"

# ✅ 好的写法
prompt = """
请按以下JSON格式返回：
{
  "interfaces": [
    {
      "name": "...",
      "method": "...",
      "url": "..."
    }
  ]
}

只返回JSON，不要其他说明。
"""
```

**3. 给出例子（Few-shot）**

```python
prompt = """
【示例1】
输入: "用户登录接口，POST方法，URL为/login，需要username和password"
输出: {
  "interfaces": [{
    "name": "用户登录",
    "method": "POST",
    "url": "/login",
    "request": {
      "body": {
        "properties": {
          "username": {"type": "string", "required": true},
          "password": {"type": "string", "required": true}
        }
      }
    }
  }]
}

【示例2】
...

现在请按照上述格式处理以下文档：
{原始文档}
"""
```

**4. 设置约束条件**

```python
prompt = """
【重要限制】
1. 不要编造不存在的接口
2. 参数类型只能是：string, integer, boolean, object, array
3. HTTP方法只能是：GET, POST, PUT, DELETE, PATCH
4. 如果信息不足，标记为 "待确认"
5. 必须返回有效的JSON

现在处理文档...
"""
```

---

## 接口信息提取

### 什么是接口识别？

**接口识别 = 从文档中自动找出所有API接口**

```
输入：一份API文档（可能很乱）
输出：清晰的接口列表
  ├─ 接口1：用户登录
  ├─ 接口2：获取用户列表
  ├─ 接口3：创建用户
  └─ ...
```

### LLM接口识别的步骤

```
┌────────────────────────┐
│ 1. 识别接口位置        │ ◀── 在文档中找出接口的边界
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────┐
│ 2. 提取基本信息        │ ◀── name, method, url, description
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────┐
│ 3. 提取请求信息        │ ◀── 参数、请求头、请求体
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────┐
│ 4. 提取响应信息        │ ◀── 状态码、响应体、错误说明
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────┐
│ 5. 补充缺失信息        │ ◀── 合理推断字段
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────┐
│ 返回结构化结果         │ ──▶ 标准JSON格式
└────────────────────────┘
```

### 实际例子

**原始文档**：
```
用户服务 API 说明

1. 登录接口
   Method: POST
   URL: /api/users/login
   Parameters:
     - username (string, required): 用户名
     - password (string, required): 密码，至少6个字符
   
   Success Response (200):
   {
     "code": 0,
     "token": "JWT token字符串",
     "userId": 123
   }
   
   Error Response (400):
   {
     "code": 400,
     "message": "用户名或密码错误"
   }

2. 登出接口
   Method: POST
   URL: /api/users/logout
   Need Auth: Yes
   
   Response:
   {
     "code": 0,
     "message": "logout success"
   }
```

**LLM识别结果**：

```json
{
  "interfaces": [
    {
      "name": "用户登录",
      "method": "POST",
      "url": "/api/users/login",
      "description": "用户通过用户名和密码登录",
      "request": {
        "body": {
          "type": "object",
          "required": ["username", "password"],
          "properties": {
            "username": {
              "type": "string",
              "required": true,
              "description": "用户名"
            },
            "password": {
              "type": "string",
              "required": true,
              "description": "密码，至少6个字符",
              "minLength": 6
            }
          }
        }
      },
      "response": {
        "status_code": 200,
        "body": {
          "type": "object",
          "properties": {
            "code": {
              "type": "integer",
              "description": "状态码"
            },
            "token": {
              "type": "string",
              "description": "JWT token字符串"
            },
            "userId": {
              "type": "integer",
              "description": "用户ID"
            }
          }
        },
        "example": {
          "code": 0,
          "token": "eyJhbGciOiJIUzI1NiIs...",
          "userId": 123
        }
      },
      "error_responses": {
        "400": {
          "description": "用户名或密码错误",
          "example": {
            "code": 400,
            "message": "用户名或密码错误"
          }
        }
      },
      "tags": ["用户管理", "认证"],
      "authentication": false
    },
    {
      "name": "用户登出",
      "method": "POST",
      "url": "/api/users/logout",
      "description": "登出当前用户",
      "request": {
        "body": {
          "type": "object",
          "required": [],
          "properties": {}
        }
      },
      "response": {
        "status_code": 200,
        "body": {
          "type": "object",
          "properties": {
            "code": {
              "type": "integer"
            },
            "message": {
              "type": "string"
            }
          }
        },
        "example": {
          "code": 0,
          "message": "logout success"
        }
      },
      "tags": ["用户管理"],
      "authentication": true
    }
  ]
}
```

**注意LLM的自动补充**：
- ✅ 为password字段推断了`minLength: 6`（从描述中）
- ✅ 为登出接口补充了`authentication: true`（通常需要认证）
- ✅ 为两个接口都补充了`tags`（便于分类）
- ✅ 为response补充了`example`字段（使结果更完整）

---

## 数据标准化

### 什么是数据标准化？

**目标**：将各种不同的接口定义格式转换为**统一的结构**。

```
多种输入格式
  ├─ Swagger定义 {swagger: 2.0, paths: {...}}
  ├─ 自定义JSON {apis: [{name, url, ...}]}
  ├─ PDF文本 "接口：POST /api/users..."
  ├─ Word表格 | 接口名 | 方法 | URL |
  └─ ...其他格式
  
        ↓ LLM理解 + 标准化
        
        ▼
  
统一的输出格式
  {
    "name": "接口名称",
    "method": "POST",
    "url": "/api/users",
    "request": {...},
    "response": {...},
    ...
  }
```

### 标准化的JSON Schema

系统采用以下统一的Schema：

```python
{
  # 基本信息（必需）
  "name": "string",           # 接口名称
  "method": "GET|POST|PUT|DELETE|PATCH",
  "url": "string",            # 接口路径
  
  # 描述（推荐）
  "description": "string",
  "tags": ["string"],
  
  # 请求信息（按需）
  "request": {
    "headers": {
      "header_name": {
        "type": "string|integer|boolean",
        "required": "boolean",
        "description": "string",
        "example": "any"
      }
    },
    "params": {  # 查询参数
      "param_name": {
        "type": "string|integer|boolean|array|object",
        "required": "boolean",
        "description": "string",
        "example": "any"
      }
    },
    "body": {    # 请求体
      "type": "object|array",
      "required": "boolean",
      "properties": {
        "field_name": {
          "type": "string|integer|boolean|array|object",
          "required": "boolean",
          "description": "string",
          "example": "any"
        }
      }
    }
  },
  
  # 响应信息（必需）
  "response": {
    "status_code": "integer",  # 200, 201等
    "body": {
      "type": "object|array",
      "properties": {
        "field_name": {
          "type": "string|integer|boolean|array|object",
          "description": "string"
        }
      }
    },
    "example": {}  # 完整的响应示例
  },
  
  # 错误响应（推荐）
  "error_responses": {
    "400": {"description": "..."},
    "401": {"description": "..."},
    "500": {"description": "..."}
  },
  
  # 其他信息
  "authentication": "boolean",
  "rate_limit": "string",  # 如："100 requests/hour"
  "version": "string"      # API版本
}
```

### 标准化的优势

| 优势 | 说明 |
|------|------|
| **一致性** | 所有接口格式相同，便于后续处理 |
| **可预测性** | 已知的字段和结构，便于编程 |
| **数据库友好** | 易于存储和查询 |
| **工具兼容** | 可以与任何下游工具集成 |
| **易于维护** | 集中式的数据格式定义 |
| **支持转换** | 可以轻松转换为其他格式（如Swagger） |

---

## 处理非结构化文档

### 常见的非结构化内容

```
场景1：自然语言描述
"用户可以通过POST请求 /api/users/login 登录，
需要提供用户名和密码。登录成功后会返回一个token。"

场景2：混合格式
"【用户登录接口】
POST /users/login
参数：
  username  string
  password  string
响应：成功返回 {token: xxx, userId: xxx}"

场景3：表格+文本混合
[表格形式接口列表] + [文字说明]

场景4：代码注释
// POST /api/users - 创建用户
// params: {name: string, email: email}
// response: {userId: int, ...}
```

### LLM处理非结构化的能力

**例子1：从自然语言推断**

```
自然语言输入：
"用户需要通过邮箱和密码才能登录。
登录后会获得一个有效期为24小时的token。
如果登录失败会返回错误信息。
token需要在后续请求的Authorization头中携带。"

LLM推断的信息：
{
  "name": "用户登录",
  "method": "POST",  // 推断：登录通常用POST
  "url": "/login",    // 推断：常见的登录路径
  "request": {
    "body": {
      "properties": {
        "email": {"type": "string", "required": true},
        "password": {"type": "string", "required": true}
      }
    }
  },
  "response": {
    "body": {
      "properties": {
        "token": {"type": "string"},
        "expiresIn": {"type": "integer"}
      }
    }
  },
  "error_responses": {
    "401": {"description": "邮箱或密码错误"}
  },
  "headers_required": ["Authorization"]
}
```

**例子2：从代码注释推断**

```
代码注释输入：
"""
def create_user():
    # POST /api/v1/users
    # 创建新用户
    # body: {name: string, email: string, password: string}
    # response: {id: int, name: string, email: string, created_at: datetime}
    pass
"""

LLM识别的接口：
{
  "name": "创建用户",
  "method": "POST",
  "url": "/api/v1/users",
  "version": "1.0",
  "request": {
    "body": {
      "properties": {
        "name": {"type": "string", "required": true},
        "email": {"type": "string", "required": true},
        "password": {"type": "string", "required": true}
      }
    }
  },
  "response": {
    "body": {
      "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
        "email": {"type": "string"},
        "created_at": {"type": "string", "format": "datetime"}
      }
    }
  }
}
```

### LLM推断的原理

LLM使用以下规则进行智能推断：

```
【HTTP方法推断】
"创建/新建" → POST
"查询/获取" → GET
"更新/修改" → PUT/PATCH
"删除/移除" → DELETE

【URL推断】
常见模式：
  /api/resource           (获取列表)
  /api/resource/{id}      (获取单个)
  /api/resource/{id}/action (执行操作)

【参数推断】
"用户名/邮箱/密码" → string, required
"用户ID/数量/页码" → integer, required
"可选的过滤条件" → string, required=false

【响应推断】
创建 → 返回 201 + 新创建的对象ID
查询 → 返回 200 + 对象数据
更新 → 返回 200 + 成功消息
删除 → 返回 200/204 + 成功消息

【认证推断】
包含"token/登录/认证" → 需要认证
包含"公开/所有人可见" → 不需认证
```

---

## 实现要点

### 1. 错误处理

```python
async def standardize_with_fallback(content, file_type):
    """有回退的标准化"""
    
    try:
        # 尝试LLM标准化
        result = await llm_standardize(content, file_type)
        return result
    except Exception as e:
        # LLM调用失败或返回格式错误
        
        # 回退方案1：尝试使用规则解析
        try:
            result = rule_based_parse(content)
            if result:
                return result
        except:
            pass
        
        # 回退方案2：返回半结构化结果，标记为需要人工审核
        return {
            "interfaces": [],
            "parsing_failed": True,
            "error": str(e),
            "raw_content": content[:1000],  # 前1000字符
            "needs_review": True
        }
```

### 2. 响应校验

```python
def validate_llm_response(response):
    """校验LLM返回的格式"""
    
    # 1. 检查是否是有效的JSON
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        raise ValueError("LLM返回非JSON格式")
    
    # 2. 检查必需字段
    if 'interfaces' not in data:
        raise ValueError("缺少'interfaces'字段")
    
    # 3. 检查每个接口的必需字段
    for interface in data['interfaces']:
        required_fields = ['name', 'method', 'url']
        for field in required_fields:
            if field not in interface:
                raise ValueError(f"接口缺少'{field}'字段: {interface}")
        
        # 验证HTTP方法
        if interface['method'] not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
            raise ValueError(f"无效的HTTP方法: {interface['method']}")
    
    return data
```

### 3. 重试机制

```python
async def standardize_with_retry(content, file_type, max_retries=3):
    """有重试机制的标准化"""
    
    for attempt in range(max_retries):
        try:
            result = await llm_standardize(content, file_type)
            validated = validate_llm_response(result)
            return validated
        except Exception as e:
            if attempt < max_retries - 1:
                # 等待后重试
                await asyncio.sleep(2 ** attempt)  # 指数退避
                continue
            else:
                raise
```

---

## 总结

**LLM标准化的核心价值**：

✅ **支持任意格式**：PDF、Word、自然语言等都可以处理
✅ **智能推断**：补充缺失信息，理解隐含业务逻辑
✅ **高质量输出**：返回结构清晰的标准JSON
✅ **鲁棒性强**：对格式混乱、排版不规范的文档有很好的处理能力
✅ **易于维护**：一套提示词适用所有格式，无需维护多套规则

**关键参数**：
- 使用 **low temperature (0.2)** 确保输出稳定
- 使用清晰的 **系统提示词 + 用户提示词**
- 提供 **明确的输出格式** 和 **示例**
- 添加 **约束条件** 避免错误

这就是 **DocumentParser 智能体处理非结构化文档的核心能力**！
