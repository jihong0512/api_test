# 在文件末尾添加新的Celery任务
@celery_app.task(bind=True, time_limit=1800, soft_time_limit=1700)
def generate_jmeter_performance_test_task(
    self,
    test_case_id: int,
    suite_id: int,
    project_id: int,
    interfaces_info: List[Dict[str, Any]],
    login_token: str,
    few_shot_interfaces: List[Dict[str, Any]],
    environment_info: Dict[str, Any],
    login_interface_info: Optional[Dict[str, Any]] = None,
    threads: int = 10
):
    """
    异步生成JMeter性能测试脚本任务（使用DeepSeek + RAG）
    
    Args:
        test_case_id: 测试用例ID
        suite_id: 测试用例集ID
        project_id: 项目ID
        interfaces_info: 场景接口信息列表（不包括登录接口）
        login_token: 登录token（可能是占位符{{TOKEN}}）
        few_shot_interfaces: Few-shot示例接口信息
        environment_info: 环境信息（base_url, xjid, username等）
        login_interface_info: 登录接口信息
        threads: 并发线程数（默认10）
    """
    db = SessionLocal()
    test_case = None
    
    try:
        from app.models import TestCase, TestCaseSuite
        
        # 获取测试用例记录
        test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
        if not test_case:
            raise Exception(f"测试用例不存在: {test_case_id}")
        
        # 获取测试用例集
        suite = db.query(TestCaseSuite).filter(TestCaseSuite.id == suite_id).first()
        if not suite:
            raise Exception(f"测试用例集不存在: {suite_id}")
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': '开始构建RAG上下文...'}
        )
        
        # 构建JMeter提示词
        prompt_parts = []
        
        # 1. 测试用例集信息
        prompt_parts.append(f"## 测试用例集信息\n")
        prompt_parts.append(f"- 用例集名称: {suite.name}\n")
        prompt_parts.append(f"- 用例集描述: {suite.description or '无'}\n")
        prompt_parts.append(f"\n")
        
        # 2. 环境信息
        prompt_parts.append(f"## 测试环境信息\n")
        prompt_parts.append(f"- 基础URL: {environment_info.get('base_url', '')}\n")
        prompt_parts.append(f"- 用户ID: {environment_info.get('xjid', '')}\n")
        prompt_parts.append(f"- 用户名: {environment_info.get('username', '')}\n")
        prompt_parts.append(f"- 并发线程数: {threads}\n")
        prompt_parts.append(f"\n")
        
        # 3. 登录接口信息（需要在Setup Thread Group中执行）
        prompt_parts.append(f"## 登录接口信息（必须在Setup Thread Group中执行）\n")
        if login_interface_info:
            login_path = login_interface_info.get('path', '/V0.1/index.php')
            # 移除URL中的debug参数
            if '?' in login_path:
                login_path = login_path.split('?')[0]
            login_url_full = f"{login_interface_info.get('base_url', environment_info.get('base_url', ''))}{login_path}"
            
            prompt_parts.append(f"### 登录接口详情:\n")
            prompt_parts.append(f"- 接口名称: {login_interface_info.get('name', '用户登录')}\n")
            prompt_parts.append(f"- 请求方法: {login_interface_info.get('method', 'POST')}\n")
            prompt_parts.append(f"- 请求URL: {login_url_full}\n")
            prompt_parts.append(f"- 请求头: {json.dumps(login_interface_info.get('headers', {}), ensure_ascii=False, indent=2)}\n")
            prompt_parts.append(f"- 请求体: {json.dumps(login_interface_info.get('request_body', {}), ensure_ascii=False, indent=2)}\n")
            
            if login_interface_info.get('response_body'):
                response_body = login_interface_info.get('response_body')
                if isinstance(response_body, str):
                    try:
                        response_body = json.loads(response_body)
                    except:
                        response_body = {}
                prompt_parts.append(f"- 响应体示例: {json.dumps(response_body, ensure_ascii=False, indent=2)}\n")
        
        prompt_parts.append(f"\n")
        prompt_parts.append(f"**重要要求：**\n")
        prompt_parts.append(f"1. 登录接口必须在Setup Thread Group中执行\n")
        prompt_parts.append(f"2. 使用JSON Extractor或Regular Expression Extractor提取token\n")
        prompt_parts.append(f"3. token提取路径：`$.data.info.token` 或使用正则表达式 `\"token\":\"(.+?)\"`\n")
        prompt_parts.append(f"4. 将提取的token保存为JMeter变量 `${token}`\n")
        prompt_parts.append(f"5. 后续所有接口的请求头中使用 `Authorization: Bearer ${token}` 或请求体中使用token变量\n")
        prompt_parts.append(f"\n")
        
        # 4. Few-shot示例接口
        if few_shot_interfaces and len(few_shot_interfaces) > 0:
            prompt_parts.append(f"## Few-shot示例接口（参考这些接口的请求参数）\n")
            for idx, fs_interface in enumerate(few_shot_interfaces[:5], 1):  # 最多5个示例
                prompt_parts.append(f"\n### 示例 {idx}: {fs_interface.get('name', '')}\n")
                prompt_parts.append(f"- 方法: {fs_interface.get('method', '')}\n")
                prompt_parts.append(f"- 路径: {fs_interface.get('path', '')}\n")
                prompt_parts.append(f"- 请求体: {json.dumps(fs_interface.get('request_body', {}), ensure_ascii=False, indent=2)}\n")
            prompt_parts.append(f"\n")
        
        # 5. 场景接口列表（按调用顺序）
        prompt_parts.append(f"## 场景接口列表（按调用顺序）\n")
        prompt_parts.append(f"以下接口需要按顺序生成JMeter测试脚本，每个接口都需要:\n")
        prompt_parts.append(f"1. 使用从Setup Thread Group中提取的token变量 `${token}`\n")
        prompt_parts.append(f"2. 使用正确的请求参数（参考few-shot示例）\n")
        prompt_parts.append(f"3. 添加响应断言（验证HTTP状态码、响应体关键字段）\n")
        prompt_parts.append(f"4. 使用JSON Path断言验证响应体结构\n")
        prompt_parts.append(f"\n")
        
        for idx, interface in enumerate(interfaces_info, 1):
            interface_url = interface.get('url', '') or interface.get('path', '')
            if '?' in interface_url:
                interface_url = interface_url.split('?')[0]
            interface_url_full = f"{interface.get('base_url', environment_info.get('base_url', ''))}{interface_url}"
            
            prompt_parts.append(f"\n### 接口 {idx}: {interface.get('name', '')}\n")
            prompt_parts.append(f"- 请求方法: {interface.get('method', 'GET')}\n")
            prompt_parts.append(f"- 请求URL: {interface_url_full}\n")
            if interface.get('headers'):
                prompt_parts.append(f"- 请求头: {json.dumps(interface.get('headers', {}), ensure_ascii=False, indent=2)}\n")
            if interface.get('request_body'):
                prompt_parts.append(f"- 请求体: {json.dumps(interface.get('request_body', {}), ensure_ascii=False, indent=2)}\n")
            if interface.get('response_body'):
                response_body = interface.get('response_body')
                if isinstance(response_body, str):
                    try:
                        response_body = json.loads(response_body)
                    except:
                        response_body = {}
                prompt_parts.append(f"- 响应体示例: {json.dumps(response_body, ensure_ascii=False, indent=2)}\n")
        
        prompt_parts.append(f"\n")
        prompt_parts.append(f"## JMeter脚本要求\n")
        prompt_parts.append(f"请生成完整的JMX文件内容，包含以下组件：\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 1. Test Plan配置\n")
        prompt_parts.append(f"- 测试计划名称：{suite.name}_性能测试\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 2. Setup Thread Group（登录）\n")
        prompt_parts.append(f"- 线程数：1\n")
        prompt_parts.append(f"- 执行一次登录接口\n")
        prompt_parts.append(f"- 提取token并保存为变量\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 3. Thread Group（性能测试）\n")
        prompt_parts.append(f"- 线程数：{threads}\n")
        prompt_parts.append(f"- Ramp-up时间：10秒\n")
        prompt_parts.append(f"- 循环次数：1\n")
        prompt_parts.append(f"- 持续时间：300秒（5分钟）\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 4. HTTP Request Defaults\n")
        prompt_parts.append(f"- 设置服务器名称和端口\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 5. HTTP Header Manager\n")
        prompt_parts.append(f"- 添加Authorization头：`Bearer ${{token}}`\n")
        prompt_parts.append(f"- 添加Content-Type：`application/json`\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 6. 每个接口的HTTP Request\n")
        prompt_parts.append(f"- 使用正确的HTTP方法（GET/POST/PUT/DELETE）\n")
        prompt_parts.append(f"- 设置正确的路径\n")
        prompt_parts.append(f"- 添加请求体（如果是POST/PUT）\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 7. 断言配置\n")
        prompt_parts.append(f"- Response Assertion：验证HTTP状态码为200\n")
        prompt_parts.append(f"- JSON Path Assertion：验证响应体关键字段（如code、ret等）\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 8. 监听器配置\n")
        prompt_parts.append(f"- View Results Tree（用于调试）\n")
        prompt_parts.append(f"- Summary Report（聚合报告）\n")
        prompt_parts.append(f"- Aggregate Graph（聚合图形）\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"**重要规则：**\n")
        prompt_parts.append(f"1. **URL规则（严格禁止）：绝对不要在URL中添加任何debug或sql参数**，如 `?__debug__=1&__sql__=true` 等后缀\n")
        prompt_parts.append(f"2. 必须使用JMeter变量 `${token}` 传递token，不能硬编码\n")
        prompt_parts.append(f"3. 所有接口必须按顺序执行\n")
        prompt_parts.append(f"4. 必须包含完整的断言检查\n")
        prompt_parts.append(f"5. 生成的JMX文件必须是有效的XML格式\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"请生成完整的JMX XML文件内容，只返回XML代码，不要包含其他解释性文字。\n")
        
        full_prompt = "".join(prompt_parts)
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 30, 'message': '正在调用DeepSeek API生成JMeter脚本...'}
        )
        
        # 调用DeepSeek API
        import requests
        deepseek_api_key = "sk-da6cff2aa0ba4c95b2b62f6693a677b8"
        deepseek_url = "https://api.deepseek.com/v1/chat/completions"
        
        messages = [
            {
                "role": "system",
                "content": """你是一个专业的性能测试工程师，擅长编写高质量的JMeter性能测试脚本。
请根据提供的接口信息，严格按照以下要求生成JMeter测试脚本：

**JMeter脚本要求：**
1. 生成完整的JMX XML文件内容
2. 必须包含Setup Thread Group用于登录和提取token
3. 必须包含Thread Group用于性能测试（默认10个并发线程）
4. 使用HTTP Header Manager传递token：`Authorization: Bearer ${token}`
5. 每个接口必须包含响应断言和JSON Path断言
6. 必须包含监听器（View Results Tree、Summary Report、Aggregate Graph）
7. 所有URL必须使用原始URL，不能添加任何debug或sql参数

**重要规则：**
1. **URL规则（严格禁止）：绝对不要在URL中添加任何debug或sql参数**，如 `?__debug__=1&__sql__=true` 等后缀
2. 必须使用JMeter变量 `${token}` 传递token，不能硬编码
3. 生成的JMX文件必须是有效的XML格式
4. 所有接口必须按顺序执行
5. 必须包含完整的断言检查

请严格按照提供的接口信息生成完整的JMX XML文件内容，只返回XML代码，不要包含其他解释性文字。"""
            },
            {
                "role": "user",
                "content": full_prompt
            }
        ]
        
        response = requests.post(
            deepseek_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {deepseek_api_key}"
            },
            json={
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 8000
            },
            timeout=180
        )
        
        if response.status_code != 200:
            raise Exception(f"DeepSeek API请求失败: {response.status_code} - {response.text}")
        
        result = response.json()
        generated_jmx = result["choices"][0]["message"]["content"]
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 80, 'message': '正在清理生成的JMX脚本...'}
        )
        
        # 检查生成的JMX是否为空
        if not generated_jmx or not generated_jmx.strip():
            raise Exception("DeepSeek API返回的JMX脚本为空，请检查API响应")
        
        # 清理生成的JMX（移除markdown代码块标记）
        import re
        # 移除 ```xml 和 ``` 标记
        generated_jmx = re.sub(r'```xml\s*\n?', '', generated_jmx)
        generated_jmx = re.sub(r'```\s*\n?', '', generated_jmx)
        # 移除开头的空行
        generated_jmx = generated_jmx.strip()
        
        # 再次检查清理后的JMX是否为空
        if not generated_jmx:
            raise Exception("清理后的JMX脚本为空，可能是格式不正确")
        
        # 验证JMX是否为有效的XML
        try:
            import xml.etree.ElementTree as ET
            ET.fromstring(generated_jmx)
        except Exception as e:
            raise Exception(f"生成的JMX脚本不是有效的XML格式: {str(e)}")
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 90, 'message': '正在保存JMX脚本...'}
        )
        
        # 保存JMX脚本到测试用例
        test_case.test_code = generated_jmx
        test_case.status = 'completed'
        test_case.generation_progress = 100
        test_case.error_message = None
        db.commit()
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 100, 'message': 'JMeter性能测试脚本生成成功'}
        )
        
        return {
            "status": "success",
                    "test_case_id": test_case_id,
            "message": "JMeter性能测试脚本生成成功",
            "jmx_length": len(generated_jmx)
        }
        
        except Exception as e:
            import traceback
        error_msg = f"生成JMeter性能测试脚本失败: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        
        if test_case:
            test_case.status = 'failed'
            test_case.error_message = error_msg
            db.commit()
        
        self.update_state(
            state='FAILURE',
            meta={'progress': 0, 'message': error_msg}
        )
        
        raise Exception(error_msg)
    finally:
        db.close()
