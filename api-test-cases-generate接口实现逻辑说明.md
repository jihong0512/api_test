# `/api/test-cases/generate` 接口实现逻辑说明

## 接口定义

**路径**：`POST /api/test-cases/generate`

**代码位置**：`backend/app/routers/test_cases.py` 第59-177行

---

## 请求参数

```python
class TestCaseGenerateRequest(BaseModel):
    api_interface_ids: List[int]  # 要生成测试用例的API接口ID列表
    case_type: str = "pytest"  # 用例类型：pytest 或 jmeter
    module: Optional[str] = None  # 模块名称（可选）
    generate_async: bool = True  # 是否异步生成（默认True）
```

---

## 实现流程

### 第一步：验证项目和接口

**代码**（第67-81行）：
```python
# 验证项目存在
project = db.query(Project).filter(
    Project.id == project_id,
    Project.user_id == current_user.id
).first()
if not project:
    raise HTTPException(status_code=404, detail="Project not found")

# 验证API接口存在
api_interfaces = db.query(APIInterface).filter(
    APIInterface.id.in_(request.api_interface_ids),
    APIInterface.project_id == project_id
).all()

if len(api_interfaces) != len(request.api_interface_ids):
    raise HTTPException(status_code=400, detail="部分API接口不存在")
```

---

### 第二步：选择生成方式（异步 or 同步）

根据 `request.generate_async` 参数选择生成方式：

#### 方式A：异步生成（推荐，默认）

**代码**（第83-119行）：

```python
if request.generate_async:
    # 异步生成：创建测试用例记录，然后提交Celery任务
    test_case_ids = []
    for api_interface in api_interfaces:
        # 1. 创建测试用例记录（状态为"generating"）
        test_case = TestCase(
            project_id=project_id,
            api_interface_id=api_interface.id,
            name=f"{api_interface.name}_测试用例",  # ✅ 名称格式：{接口名}_测试用例
            case_type=request.case_type,  # 'pytest' 或 'jmeter'
            module=request.module,
            status="generating",  # 状态：生成中
            generation_progress=0  # 进度：0%
        )
        db.add(test_case)
        db.commit()
        db.refresh(test_case)
        test_case_ids.append(test_case.id)
        
        # 2. 提交异步Celery任务
        task = generate_test_case_task.delay(
            test_case_id=test_case.id,
            case_type=request.case_type,
            project_id=project_id,
            api_interface_id=api_interface.id,
            module=request.module
        )
        
        # 3. 更新测试用例的任务ID
        test_case.generation_task_id = task.id
        db.commit()
    
    return {
        "message": "测试用例生成任务已提交",
        "test_case_ids": test_case_ids,
        "task_ids": [...],
        "async": True
    }
```

**关键点**：
- ✅ 立即返回响应，不阻塞
- ✅ 在数据库中创建测试用例记录（状态为"generating"）
- ✅ 提交Celery异步任务 `generate_test_case_task`
- ✅ 返回测试用例ID和任务ID列表

---

#### 方式B：同步生成（不推荐，可能超时）

**代码**（第120-177行）：

```python
else:
    # 同步生成（不推荐，可能超时）
    from app.services.test_case_generator import PytestCaseGenerator, JMeterCaseGenerator
    from app.services.smart_test_data_generator import SmartTestDataGenerator
    
    results = []
    generator = SmartTestDataGenerator()
    
    for api_interface in api_interfaces:
        # 1. 构建接口信息字典
        api_data = {
            "id": api_interface.id,
            "name": api_interface.name,
            "method": api_interface.method,
            "url": api_interface.url,
            "params": json.loads(api_interface.params) if api_interface.params else {},
            "headers": json.loads(api_interface.headers) if api_interface.headers else {},
            "body": json.loads(api_interface.body) if api_interface.body else {},
            "response_schema": json.loads(api_interface.response_schema) if api_interface.response_schema else {},
            "description": api_interface.description or ""
        }
        
        # 2. 生成测试数据（不使用真实数据库数据）
        test_data = generator.generate_test_data_for_api(
            api_info=api_data,
            connection_id=None,  # ❌ 不使用数据库连接
            project_id=project_id,
            use_real_data=False,  # ❌ 不使用真实数据
            db_session=db
        )
        
        # 3. 根据用例类型选择生成器并生成测试代码
        if request.case_type == "pytest":
            case_generator = PytestCaseGenerator()
            test_code = case_generator.generate_test_case(api_interface=api_data, test_data=test_data)
        elif request.case_type == "jmeter":
            case_generator = JMeterCaseGenerator()
            test_code = case_generator.generate_test_case(api_interface=api_data, test_data=test_data)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的用例类型: {request.case_type}")
        
        # 4. 创建测试用例记录（状态为"completed"）
        test_case = TestCase(
            project_id=project_id,
            api_interface_id=api_interface.id,
            name=f"{api_interface.name}_测试用例",  # ✅ 名称格式：{接口名}_测试用例
            case_type=request.case_type,
            module=request.module,
            test_code=test_code,  # ✅ 已生成的测试代码
            status="completed",  # 状态：已完成
            generation_progress=100  # 进度：100%
        )
        db.add(test_case)
        results.append(test_case.id)
    
    db.commit()
    
    return {
        "message": "测试用例生成完成",
        "test_case_ids": results,
        "async": False
    }
```

**关键点**：
- ⚠️ 同步执行，可能超时
- ✅ 立即生成测试代码并保存
- ❌ 不使用真实数据库数据（`use_real_data=False`）
- ✅ 测试用例状态直接为"completed"

---

## 异步生成任务详情（Celery Task）

**任务名称**：`generate_test_case_task`

**代码位置**：`backend/app/celery_tasks.py` 第2105-2229行

### 任务流程

#### 1. 获取测试用例和API接口信息

**代码**（第2128-2139行）：
```python
# 获取测试用例记录
test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
if not test_case:
    raise Exception(f"测试用例不存在: {test_case_id}")

# 获取API接口信息（优先从APIInterface表，如果不存在则从DocumentAPIInterface表）
api_interface = db.query(APIInterface).filter(APIInterface.id == api_interface_id).first()
if not api_interface:
    api_interface = db.query(DocumentAPIInterface).filter(DocumentAPIInterface.id == api_interface_id).first()
    if not api_interface:
        raise Exception(f"API接口不存在: {api_interface_id}")
```

#### 2. 构建接口信息字典

**代码**（第2146-2174行）：
```python
interface_info = {
    'id': api_interface.id,
    'name': api_interface.name or 'test_api',
    'method': getattr(api_interface, 'method', 'GET') or 'GET',
    'url': getattr(api_interface, 'url', '') or '',
    'path': getattr(api_interface, 'path', '') or '',
    'headers': getattr(api_interface, 'headers', '{}') or '{}',
    'params': getattr(api_interface, 'params', '{}') or '{}',
    'body': getattr(api_interface, 'body', '{}') or getattr(api_interface, 'request_body', '{}') or '{}',
    'description': getattr(api_interface, 'description', '') or ''
}

# 解析JSON字符串
if isinstance(interface_info['headers'], str):
    try:
        interface_info['headers'] = json.loads(interface_info['headers'])
    except:
        interface_info['headers'] = {}
# ... 类似地处理 params 和 body
```

#### 3. 选择生成器并生成测试代码

**代码**（第2181-2185行）：
```python
# 根据用例类型选择生成器
if case_type == 'jmeter':
    generator = JMeterCaseGenerator()
else:
    generator = PytestCaseGenerator()  # 默认使用pytest生成器

# 生成测试代码
test_code = generator.generate_test_case(
    api_interface=interface_info,
    project_id=project_id
)
```

**生成器说明**：
- `PytestCaseGenerator`：生成pytest格式的测试用例代码
- `JMeterCaseGenerator`：生成JMeter格式的性能测试脚本

#### 4. 更新测试用例记录

**代码**（第2187-2200行）：
```python
# 更新测试用例
test_case.test_code = test_code  # 保存生成的测试代码
test_case.status = "active"  # 状态改为"active"（活跃）
test_case.generation_progress = 100  # 进度改为100%
db.commit()
```

#### 5. 更新任务状态并返回

**代码**（第2202-2210行）：
```python
self.update_state(
    state='PROGRESS',
    meta={'progress': 100, 'message': '测试用例生成完成'}
)

return {
    "status": "success",
    "test_case_id": test_case_id,
    "message": "测试用例生成完成"
}
```

---

## 关键特性总结

### ✅ 生成的测试用例特征

1. **名称格式**：`{api_interface.name}_测试用例`
   - ✅ 名称不包含"场景"
   - ✅ 会显示在"接口测试用例"标签页（`is_scenario=false`）

2. **用例类型**：根据 `case_type` 参数确定
   - `"pytest"`：接口测试用例
   - `"jmeter"`：性能测试用例

3. **状态流转**：
   - 异步生成：`generating` → `active`
   - 同步生成：直接 `completed`

### ⚠️ 注意事项

1. **不使用真实数据库数据**：
   - 同步生成：`use_real_data=False`，`connection_id=None`
   - 异步生成：不调用 `SmartTestDataGenerator`，直接使用生成器

2. **异步生成是默认方式**：
   - `generate_async=True`（默认值）
   - 推荐使用异步方式，避免超时

3. **前端没有调用入口**：
   - 后端接口已实现，但前端没有对应的UI
   - 需要通过API直接调用或添加前端按钮

---

## 调用示例

### 请求示例

```json
POST /api/test-cases/generate?project_id=1
Content-Type: application/json

{
  "api_interface_ids": [1, 2, 3],
  "case_type": "pytest",
  "module": "用户模块",
  "generate_async": true
}
```

### 响应示例（异步）

```json
{
  "message": "测试用例生成任务已提交",
  "test_case_ids": [10, 11, 12],
  "task_ids": ["abc-123", "def-456", "ghi-789"],
  "async": true
}
```

### 响应示例（同步）

```json
{
  "message": "测试用例生成完成",
  "test_case_ids": [10, 11, 12],
  "async": false
}
```

