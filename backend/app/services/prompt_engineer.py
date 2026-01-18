from typing import Dict, Any, List, Optional
import json


class PromptEngineer:
    """Prompt工程：设计有效的Prompt指导LLM生成测试代码"""
    
    def __init__(self):
        pass
    
    def build_code_generation_prompt(
        self,
        api_interface: Dict[str, Any],
        test_data: Optional[Dict[str, Any]] = None,
        framework: str = "httprunner",
        language: str = "python",
        custom_requirements: Optional[List[str]] = None
    ) -> str:
        """
        构建代码生成的Prompt
        
        Args:
            api_interface: API接口信息
            test_data: 测试数据
            framework: 测试框架
            language: 编程语言
            custom_requirements: 自定义要求
        
        Returns:
            完整的Prompt
        """
        prompt_parts = []
        
        # 1. 角色定义
        prompt_parts.append(self._get_role_definition())
        
        # 2. 任务描述
        prompt_parts.append(self._get_task_description(api_interface, framework, language))
        
        # 3. API接口信息
        prompt_parts.append(self._format_api_interface(api_interface))
        
        # 4. 测试数据
        if test_data:
            prompt_parts.append(self._format_test_data(test_data))
        
        # 5. 代码结构要求
        prompt_parts.append(self._get_code_structure_requirements(framework, language))
        
        # 6. 代码规范
        prompt_parts.append(self._get_code_standards(framework, language))
        
        # 7. 特殊逻辑要求
        if custom_requirements:
            prompt_parts.append(self._format_custom_requirements(custom_requirements))
        
        # 8. 输出格式要求
        prompt_parts.append(self._get_output_requirements())
        
        return "\n\n".join(prompt_parts)
    
    def _get_role_definition(self) -> str:
        """角色定义"""
        return """你是一位专业的自动化测试工程师，擅长使用各种测试框架编写高质量的API测试代码。你的代码应该：
1. 结构清晰，易于维护
2. 包含完整的错误处理
3. 使用最佳实践
4. 具有良好的可读性"""
    
    def _get_task_description(
        self,
        api_interface: Dict[str, Any],
        framework: str,
        language: str
    ) -> str:
        """任务描述"""
        api_name = api_interface.get("name", "API接口")
        method = api_interface.get("method", "GET")
        
        return f"""## 任务
请为以下API接口生成{framework}框架的{language}测试代码：

**接口信息：**
- 名称：{api_name}
- 方法：{method}
- 描述：{api_interface.get('description', '无')}

**要求：**
1. 生成完整的、可直接运行的测试代码
2. 包含请求构造（方法、URL、参数、请求头、请求体）
3. 包含断言验证
4. 包含数据提取（如果需要）
5. 处理认证机制
6. 处理错误情况"""
    
    def _format_api_interface(self, api_interface: Dict[str, Any]) -> str:
        """格式化API接口信息"""
        parts = ["## API接口详情\n"]
        
        method = api_interface.get("method", "GET")
        url = api_interface.get("url") or api_interface.get("path", "")
        base_url = api_interface.get("base_url", "")
        
        parts.append(f"- **HTTP方法**: {method.upper()}")
        parts.append(f"- **路径**: {url}")
        if base_url:
            parts.append(f"- **基础URL**: {base_url}")
        
        # 解析参数
        params = {}
        if api_interface.get("params"):
            try:
                params = json.loads(api_interface["params"]) if isinstance(api_interface["params"], str) else api_interface["params"]
            except:
                pass
        
        if params:
            parts.append(f"- **查询参数**: {json.dumps(params, ensure_ascii=False, indent=2)}")
        
        # 解析请求头
        headers = {}
        if api_interface.get("headers"):
            try:
                headers = json.loads(api_interface["headers"]) if isinstance(api_interface["headers"], str) else api_interface["headers"]
            except:
                pass
        
        if headers:
            parts.append(f"- **请求头**: {json.dumps(headers, ensure_ascii=False, indent=2)}")
        
        # 请求体
        body = api_interface.get("body") or api_interface.get("request_body")
        if body:
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except:
                    pass
            parts.append(f"- **请求体**: {json.dumps(body, ensure_ascii=False, indent=2)}")
        
        # 响应Schema
        response_schema = api_interface.get("response_schema")
        if response_schema:
            parts.append(f"- **响应Schema**: 已定义")
        
        return "\n".join(parts)
    
    def _format_test_data(self, test_data: Dict[str, Any]) -> str:
        """格式化测试数据"""
        parts = ["## 测试数据\n"]
        parts.append("以下测试数据需要在请求中使用：")
        parts.append(f"```json\n{json.dumps(test_data, ensure_ascii=False, indent=2)}\n```")
        return "\n".join(parts)
    
    def _get_code_structure_requirements(self, framework: str, language: str) -> str:
        """代码结构要求"""
        if framework == "httprunner":
            return """## 代码结构要求（HttpRunner）

代码应该遵循HttpRunner的结构：

```python
class TestAPI(HttpRunner):
    config = Config("测试名称")
    
    teststeps = [
        Step(
            RunRequest("步骤名称")
            .get/post/put/delete/patch("URL")
            .with_params(**params)  # 查询参数
            .with_headers(**headers)  # 请求头
            .with_json(data)  # JSON请求体
            .extract()
            .with_jmespath("json_path", "变量名")  # 提取数据
            .validate()
            .assert_equal("status_code", 200)  # 断言
        )
    ]
```

**要求：**
1. 使用正确的HTTP方法（.get/.post/.put/.delete/.patch）
2. 使用.with_params()添加查询参数
3. 使用.with_headers()添加请求头
4. 使用.with_json()添加JSON请求体（POST/PUT/PATCH）
5. 使用.extract().with_jmespath()提取响应数据
6. 使用.validate().assert_*()进行断言"""
        
        elif framework == "requests":
            return """## 代码结构要求（requests）

代码应该使用requests库：

```python
import requests

url = "完整URL"
headers = {...}
params = {...}
json_data = {...}

response = requests.get/post/put/delete(url, headers=headers, params=params, json=json_data)

assert response.status_code == 200
```

**要求：**
1. 导入requests库
2. 构造完整的URL（包含base_url和path）
3. 设置请求头和参数
4. 根据Content-Type选择json/data/files参数
5. 包含断言验证"""
        
        else:
            return """## 代码结构要求

代码应该结构清晰，包含：
1. 导入必要的库
2. 构造请求URL和参数
3. 发送HTTP请求
4. 验证响应
5. 处理错误情况"""
    
    def _get_code_standards(self, framework: str, language: str) -> str:
        """代码规范"""
        return """## 代码规范

1. **命名规范**：
   - 使用有意义的变量名
   - 类名使用大驼峰（PascalCase）
   - 函数和变量使用下划线命名（snake_case）

2. **代码风格**：
   - 遵循PEP 8（Python）或ESLint（JavaScript）
   - 适当的缩进和空格
   - 添加必要的注释

3. **语法正确性（必须严格遵守）**：
   - **Python语法正确**：确保所有括号匹配、引号匹配、冒号正确使用
   - **缩进正确**：使用4个空格（不使用Tab），确保所有缩进一致
   - **导入语句正确**：确保所有导入的包存在且正确（如pytest, allure, requests, httprunner等）
   - **变量和函数命名**：符合Python命名规范，不使用关键字
   - **无语法错误**：确保代码没有任何语法错误、缩进错误或导入错误

4. **错误处理**：
   - 包含异常处理
   - 检查响应状态码
   - 处理网络错误

5. **数据提取**：
   - 如果接口返回token、ID等，需要提取并保存
   - 使用合适的提取方法（JMESPath、JSONPath等）

6. **断言验证**：
   - 验证状态码
   - 验证响应体结构
   - 验证关键字段值

**重要：在生成代码后，必须自行检查代码的语法正确性，修复任何语法问题、缩进问题和包导入问题。生成的代码必须是语法完全正确的，可以直接执行。**"""
    
    def _format_custom_requirements(self, requirements: List[str]) -> str:
        """格式化自定义要求"""
        parts = ["## 特殊要求\n"]
        for i, req in enumerate(requirements, 1):
            parts.append(f"{i}. {req}")
        return "\n".join(parts)
    
    def _get_output_requirements(self) -> str:
        """输出格式要求"""
        return """## 输出要求

请只输出代码，不需要额外的说明文字。代码应该：
1. 完整且可运行
2. 包含所有必要的导入
3. 使用提供的测试数据
4. 包含完整的断言逻辑
5. 如果有认证要求，正确处理认证
6. **必须确保生成的代码语法完全正确，包括：**
   - Python语法正确（缩进、括号匹配、引号匹配等）
   - 所有导入语句正确且包存在
   - 缩进使用4个空格（不使用Tab），确保缩进一致
   - 变量名和函数名符合Python命名规范
   - 没有语法错误、缩进错误或导入错误
7. **在生成代码后，必须自行检查代码的语法正确性，修复任何语法问题、缩进问题和包导入问题**

**输出格式：**
直接输出代码，不要包含markdown代码块标记（```python）"""
    
    def build_advanced_prompt(
        self,
        api_interface: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        test_scenario: Optional[str] = None,
        dependencies: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        构建高级Prompt（包含上下文和场景）
        
        Args:
            api_interface: API接口信息
            context: 上下文信息（依赖数据、前置步骤等）
            test_scenario: 测试场景描述
            dependencies: 依赖的接口列表
        
        Returns:
            高级Prompt
        """
        prompt_parts = []
        
        # 基础Prompt
        prompt_parts.append(self.build_code_generation_prompt(api_interface))
        
        # 测试场景
        if test_scenario:
            prompt_parts.append(f"## 测试场景\n{test_scenario}")
        
        # 依赖信息
        if dependencies:
            prompt_parts.append(self._format_dependencies(dependencies))
        
        # 上下文信息
        if context:
            prompt_parts.append(self._format_context(context))
        
        return "\n\n".join(prompt_parts)
    
    def _format_dependencies(self, dependencies: List[Dict[str, Any]]) -> str:
        """格式化依赖信息"""
        parts = ["## 接口依赖\n"]
        parts.append("此接口依赖以下前置接口，可能需要在请求中使用它们返回的数据：")
        
        for i, dep in enumerate(dependencies, 1):
            parts.append(f"\n{i}. {dep.get('name', '未知接口')}")
            parts.append(f"   - 方法: {dep.get('method', 'GET')}")
            parts.append(f"   - 路径: {dep.get('path', '')}")
            if dep.get("extracted_data"):
                parts.append(f"   - 提取的数据: {json.dumps(dep['extracted_data'], ensure_ascii=False)}")
        
        parts.append("\n请在测试代码中正确使用这些依赖数据。")
        
        return "\n".join(parts)
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """格式化上下文信息"""
        parts = ["## 上下文信息\n"]
        
        if context.get("extracted_data"):
            parts.append("**已提取的数据（可在当前请求中使用）：**")
            parts.append(f"```json\n{json.dumps(context['extracted_data'], ensure_ascii=False, indent=2)}\n```")
        
        if context.get("environment"):
            parts.append(f"**测试环境**: {context['environment']}")
        
        if context.get("base_url"):
            parts.append(f"**基础URL**: {context['base_url']}")
        
        return "\n".join(parts)




















