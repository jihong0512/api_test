from typing import Dict, Any, List, Optional
import json
import yaml
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import redis

from app.services.smart_test_data_generator import SmartTestDataGenerator
from app.services.dependency_analyzer import DependencyAnalyzer
from app.services.response_extractor import ResponseExtractor
from app.services.request_builder import RequestBuilder
from app.services.prompt_engineer import PromptEngineer
from app.services.llm_service import LLMService
from app.config import settings

# Redis连接（用于获取few-shot示例）
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    encoding='utf-8'
)


class PytestCaseGenerator:
    """Pytest测试用例生成器（HttpRunner风格）"""
    
    def __init__(self, use_llm: bool = False):
        self.data_generator = SmartTestDataGenerator()
        self.response_extractor = ResponseExtractor()
        self.request_builder = RequestBuilder()
        self.prompt_engineer = PromptEngineer()
        self.use_llm = use_llm
        if use_llm:
            self.llm_service = LLMService()
    
    def generate_test_case(
        self,
        api_interface: Dict[str, Any],
        test_data: Optional[Dict[str, Any]] = None,
        extracted_data: Optional[Dict[str, Any]] = None,
        assertions: Optional[List[Dict[str, Any]]] = None,
        auth_config: Optional[Dict[str, Any]] = None,
        security_schemes: Optional[Dict[str, Any]] = None,
        use_llm: Optional[bool] = None,
        project_id: Optional[int] = None
    ) -> str:
        """
        生成Pytest测试用例（HttpRunner格式）
        
        Args:
            api_interface: API接口信息
            test_data: 测试数据
            extracted_data: 从前置步骤提取的数据（token等）
            assertions: 断言规则
            auth_config: 认证配置
            security_schemes: 安全方案（从OpenAPI解析）
            use_llm: 是否使用LLM生成
        
        Returns:
            Python测试用例代码
        """
        # 决定是否使用LLM生成
        use_llm_generation = use_llm if use_llm is not None else self.use_llm
        
        # 如果使用LLM生成
        if use_llm_generation:
            return self._generate_with_llm(api_interface, test_data, extracted_data, assertions, auth_config, security_schemes, project_id)
        
        # 传统方式生成（统一使用url字段）
        api_name = api_interface.get("name", "test_api")
        method = api_interface.get("method", "GET").upper()
        url = api_interface.get("url", "")  # 统一使用url字段
        # base_url从测试环境中获取，不在此处设置
        base_url = ""  # 实际执行时会从TestEnvironment.base_url获取
        
        # 使用RequestBuilder构造请求
        path_params = {}
        if extracted_data:
            # 从extracted_data中提取路径参数
            for key, value in extracted_data.items():
                if key.endswith("Id") or key.endswith("ID"):
                    path_params[key] = value
        
        # 解析参数（统一格式）
        params = json.loads(api_interface.get("params", "{}")) if isinstance(api_interface.get("params"), str) else (api_interface.get("params") or {})
        headers = json.loads(api_interface.get("headers", "{}")) if isinstance(api_interface.get("headers"), str) else (api_interface.get("headers") or {})
        body = json.loads(api_interface.get("body", "{}")) if isinstance(api_interface.get("body"), str) else (api_interface.get("body") or {})
        
        # 处理认证
        if auth_config:
            auth_headers = self.request_builder._build_auth_headers(auth_config)
            headers.update(auth_headers)
        elif security_schemes and extracted_data:
            # 从security_schemes应用认证
            # 假设使用第一个认证方案
            scheme_name = list(security_schemes.keys())[0] if security_schemes else None
            if scheme_name and extracted_data.get("authToken"):
                auth_config = {
                    "type": security_schemes[scheme_name].get("type", "bearer"),
                    "value": extracted_data.get("authToken")
                }
                auth_headers = self.request_builder._build_auth_headers(auth_config)
                headers.update(auth_headers)
        
        # 构造请求
        request_info = self.request_builder.build_request(
            method=method,
            base_url=base_url,
            path=url,
            path_params=path_params,
            query_params=params,
            headers=headers,
            body=body,
            auth_config=auth_config
        )
        
        full_url = request_info["url"]
        headers = request_info["headers"]
        body = request_info["body"]
        content_type = request_info.get("content_type", "application/json")
        
        # 在生成代码前，先提取schema结构中的实际数据
        if isinstance(body, dict) and "schema" in body:
            body = self._extract_request_body_from_schema(body)
        
        # 如果有测试数据，使用测试数据覆盖
        if test_data:
            if test_data.get("params"):
                params.update(test_data["params"])
            if test_data.get("headers"):
                headers.update(test_data["headers"])
            if test_data.get("body"):
                if isinstance(body, dict):
                    body.update(test_data["body"])
                else:
                    body = test_data["body"]
        
        # 生成测试用例代码（使用 requests 库，不依赖 httprunner）
        # 构建URL：如果url是完整URL，直接使用；否则拼接base_url
        original_url = api_interface.get("url", "") or api_interface.get("path", "")
        if original_url.startswith('http://') or original_url.startswith('https://'):
            # 如果原始URL是完整URL，直接使用，不拼接base_url
            url_str = f'"{original_url}"'
        elif original_url.startswith('/'):
            # 如果原始URL是路径（以/开头），拼接base_url
            url_str = f'f"{{base_url}}{original_url}"'
        elif original_url:
            # 如果原始URL是相对路径，拼接base_url和/
            url_str = f'f"{{base_url}}/{original_url}"'
        else:
            # 如果原始URL为空，使用base_url
            url_str = 'f"{base_url}"'
        
        test_code = f'''import pytest
import requests
import json


def test_{api_name.replace(" ", "_").replace("/", "_").replace("-", "_")}(base_url, xjid):
    """{api_interface.get('description', api_name)}"""
    url = {url_str}
'''
        
        # 添加参数
        if params:
            test_code += f"    params = {self._format_python_dict(params)}\n"
        else:
            test_code += "    params = None\n"
        
        # 添加请求头
        if headers:
            test_code += f"    headers = {self._format_python_dict(headers)}\n"
        else:
            test_code += "    headers = {{}}\n"
        
        # 添加 xjid 到 headers（如果需要）
        test_code += "    if xjid:\n"
        test_code += "        headers['XJID'] = xjid\n"
        
        # 发送请求（根据方法）
        if method == "GET":
            test_code += "    response = requests.get(url, params=params, headers=headers)\n"
        elif method == "POST":
            if body and content_type == "application/json":
                if isinstance(body, dict):
                    # 检查是否是schema结构，如果是则提取properties生成实际数据
                    body_data = self._extract_request_body_from_schema(body)
                    test_code += f"    json_data = {self._format_python_dict(body_data)}\n"
                    test_code += "    response = requests.post(url, json=json_data, params=params, headers=headers)\n"
                else:
                    test_code += f"    data = {repr(body)}\n"
                    test_code += "    response = requests.post(url, data=data, params=params, headers=headers)\n"
            elif body and content_type == "application/x-www-form-urlencoded":
                test_code += f"    data = {self._format_python_dict(body) if isinstance(body, dict) else repr(body)}\n"
                test_code += "    response = requests.post(url, data=data, params=params, headers=headers)\n"
            else:
                test_code += f"    data = {repr(body) if body else 'None'}\n"
                test_code += "    response = requests.post(url, data=data, params=params, headers=headers)\n"
        elif method == "PUT":
            if body and content_type == "application/json":
                if isinstance(body, dict):
                    # 检查是否是schema结构，如果是则提取properties生成实际数据
                    body_data = self._extract_request_body_from_schema(body)
                    test_code += f"    json_data = {self._format_python_dict(body_data)}\n"
                    test_code += "    response = requests.put(url, json=json_data, params=params, headers=headers)\n"
                else:
                    test_code += f"    data = {repr(body)}\n"
                    test_code += "    response = requests.put(url, data=data, params=params, headers=headers)\n"
            else:
                test_code += f"    data = {repr(body) if body else 'None'}\n"
                test_code += "    response = requests.put(url, data=data, params=params, headers=headers)\n"
        elif method == "PATCH":
            if body and content_type == "application/json":
                if isinstance(body, dict):
                    # 检查是否是schema结构，如果是则提取properties生成实际数据
                    body_data = self._extract_request_body_from_schema(body)
                    test_code += f"    json_data = {self._format_python_dict(body_data)}\n"
                    test_code += "    response = requests.patch(url, json=json_data, params=params, headers=headers)\n"
                else:
                    test_code += f"    data = {repr(body)}\n"
                    test_code += "    response = requests.patch(url, data=data, params=params, headers=headers)\n"
            else:
                test_code += f"    data = {repr(body) if body else 'None'}\n"
                test_code += "    response = requests.patch(url, data=data, params=params, headers=headers)\n"
        elif method == "DELETE":
            test_code += "    response = requests.delete(url, params=params, headers=headers)\n"
        else:
            test_code += f"    # 不支持的HTTP方法: {method}\n"
            test_code += "    response = None\n"
        
        # 添加提取规则（使用 jmespath 或简单的 JSON 路径）
        extract_rules = self._get_extract_rules(api_interface, extracted_data)
        if extract_rules:
            test_code += "\n    # 提取响应数据\n"
            test_code += "    try:\n"
            test_code += "        response_data = response.json()\n"
            test_code += "    except:\n"
            test_code += "        response_data = response.text\n"
            for var_name, extract_path in extract_rules.items():
                # 简单的 JSON 路径提取（不使用 jmespath，避免额外依赖）
                test_code += f"    # 提取 {var_name} 从 {extract_path}\n"
                test_code += f"    # TODO: 实现提取逻辑\n"
        
        # 添加断言
        test_code += "\n    # 断言\n"
        assertions_code = self._generate_assertions_for_requests(api_interface, assertions)
        if assertions_code:
            test_code += assertions_code
        else:
            # 默认断言：状态码为 200
            test_code += "    assert response.status_code == 200, f\"Expected status code 200, got {response.status_code}. Response: {response.text}\"\n"
        
        return test_code
    
    def _get_few_shot_example(self, project_id: int) -> Optional[Dict[str, Any]]:
        """从Redis获取few-shot示例用于测试用例生成"""
        try:
            # 查找few-shot示例
            pattern = f"few_shot:project:{project_id}:document:*"
            keys = redis_client.keys(pattern)
            if keys:
                data = redis_client.get(keys[0])
                if data:
                    few_shot_info = json.loads(data)
                    interfaces = few_shot_info.get('interfaces', [])
                    if interfaces:
                        # 返回前3个接口作为示例
                        return {
                            'interfaces': interfaces[:3],
                            'environment': few_shot_info.get('environment', '')
                        }
        except Exception as e:
            print(f"获取few-shot示例失败: {e}")
        return None
    
    def _generate_with_llm(
        self,
        api_interface: Dict[str, Any],
        test_data: Optional[Dict[str, Any]] = None,
        extracted_data: Optional[Dict[str, Any]] = None,
        assertions: Optional[List[Dict[str, Any]]] = None,
        auth_config: Optional[Dict[str, Any]] = None,
        security_schemes: Optional[Dict[str, Any]] = None,
        project_id: Optional[int] = None
    ) -> str:
        """使用LLM生成测试代码（支持few-shot学习）"""
        # 获取few-shot示例
        few_shot_prompt = ""
        if project_id:
            few_shot_example = self._get_few_shot_example(project_id)
            if few_shot_example and few_shot_example.get('interfaces'):
                few_shot_interfaces = few_shot_example['interfaces']
                few_shot_prompt = f"""
## Few-Shot示例（来自{few_shot_example.get('environment', '国内测试环境')}）：
以下是参考示例，展示了如何生成测试用例：

{json.dumps(few_shot_interfaces, ensure_ascii=False, indent=2)}

请参考以上示例的格式和风格，为下面的接口生成测试用例。

"""
        
        # 构建Prompt
        base_prompt = self.prompt_engineer.build_code_generation_prompt(
            api_interface=api_interface,
            test_data=test_data,
            framework="requests",  # 使用requests库，不使用httprunner
            language="python",
            custom_requirements=self._get_custom_requirements_from_context(
                auth_config, security_schemes, extracted_data
            )
        )
        
        # 添加语法检查要求
        syntax_check_requirement = """
        
## 重要：语法检查要求

**在生成代码后，必须确保代码语法完全正确：**
1. 检查Python语法（括号匹配、引号匹配、冒号正确等）
2. 检查缩进（使用4个空格，不使用Tab，确保缩进一致）
3. 检查导入语句（确保所有导入的包存在且正确）
4. 检查变量和函数命名（符合Python命名规范）
5. 修复任何语法错误、缩进错误或导入错误

生成的代码必须是语法完全正确的Python代码，可以直接执行。
"""
        
        prompt = few_shot_prompt + base_prompt + syntax_check_requirement
        
        # 调用LLM生成代码
        try:
            generated_code = self.llm_service.chat(
                prompt,
                temperature=0.3,
                max_tokens=2000
            )
            
            # 清理代码（移除markdown标记等）
            cleaned_code = self._clean_generated_code(generated_code)
            
            return cleaned_code
        except Exception as e:
            # LLM生成失败，回退到传统方式
            return self.generate_test_case(
                api_interface=api_interface,
                test_data=test_data,
                extracted_data=extracted_data,
                assertions=assertions,
                auth_config=auth_config,
                security_schemes=security_schemes,
                use_llm=False
            )
    
    def _get_custom_requirements_from_context(
        self,
        auth_config: Optional[Dict[str, Any]],
        security_schemes: Optional[Dict[str, Any]],
        extracted_data: Optional[Dict[str, Any]]
    ) -> List[str]:
        """从上下文提取自定义要求"""
        requirements = []
        
        if auth_config:
            auth_type = auth_config.get("type", "")
            requirements.append(f"需要处理{auth_type}认证，认证值从上下文变量中获取")
        
        if security_schemes:
            for scheme_name, scheme_config in security_schemes.items():
                scheme_type = scheme_config.get("type", "")
                requirements.append(f"需要处理{scheme_type}认证方案：{scheme_name}")
        
        if extracted_data:
            if extracted_data.get("authToken"):
                requirements.append("需要从前置步骤提取的authToken设置Authorization头")
            if any(key.endswith("Id") or key.endswith("ID") for key in extracted_data.keys()):
                requirements.append("需要将前置步骤提取的ID填入路径参数或请求体中")
        
        return requirements
    
    def _clean_generated_code(self, code: str) -> str:
        """清理LLM生成的代码"""
        # 移除markdown代码块标记
        if code.startswith("```python"):
            code = code.replace("```python", "").replace("```", "").strip()
        elif code.startswith("```"):
            code = code.replace("```", "").strip()
        
        # 移除多余的空行
        lines = [line for line in code.split("\n") if line.strip() or not lines or lines[-1].strip()]
        return "\n".join(lines)
    
    def _get_method_call(self, method: str) -> str:
        """获取HttpRunner的方法调用"""
        method_map = {
            "GET": "get",
            "POST": "post",
            "PUT": "put",
            "DELETE": "delete",
            "PATCH": "patch"
        }
        return method_map.get(method.upper(), "get")
    
    def _format_python_dict(self, data: Dict[str, Any]) -> str:
        """格式化Python字典"""
        return json.dumps(data, ensure_ascii=False, indent=12)
    
    def _extract_request_body_from_schema(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        从schema结构中提取实际的请求体数据
        
        如果body是schema结构（包含schema键），则从schema.properties中提取字段生成实际数据
        否则直接返回body
        
        Args:
            body: 请求体，可能是schema结构或实际数据
            
        Returns:
            实际的请求体数据字典
        """
        # 检查是否是schema结构（包含content_type和schema键）
        if isinstance(body, dict) and "schema" in body:
            schema_obj = body.get("schema", {})
            if isinstance(schema_obj, dict) and "properties" in schema_obj:
                # 从schema.properties中提取字段
                properties = schema_obj.get("properties", {})
                required_fields = schema_obj.get("required", [])
                result = {}
                
                # 提取所有字段的值（优先使用example，其次使用默认值）
                for field_name, field_schema in properties.items():
                    if isinstance(field_schema, dict):
                        # 优先使用example值
                        if "example" in field_schema:
                            result[field_name] = field_schema["example"]
                        # 其次使用default值
                        elif "default" in field_schema:
                            result[field_name] = field_schema["default"]
                        # 如果是enum类型，使用第一个值
                        elif "enum" in field_schema and field_schema["enum"]:
                            result[field_name] = field_schema["enum"][0]
                        # 根据type生成默认值
                        else:
                            field_type = field_schema.get("type", "string")
                            if field_type == "string":
                                result[field_name] = ""
                            elif field_type == "integer":
                                result[field_name] = 0
                            elif field_type == "number":
                                result[field_name] = 0.0
                            elif field_type == "boolean":
                                result[field_name] = False
                            elif field_type == "array":
                                result[field_name] = []
                            elif field_type == "object":
                                result[field_name] = {}
                            else:
                                result[field_name] = None
                    else:
                        result[field_name] = field_schema
                
                # 确保所有required字段都有值
                for required_field in required_fields:
                    if required_field not in result:
                        # 如果required字段没有值，使用空字符串作为默认值
                        result[required_field] = ""
                
                return result
        
        # 如果不是schema结构，直接返回
        return body
    
    def _get_extract_rules(self, api_interface: Dict[str, Any], extracted_data: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """获取提取规则"""
        rules = {}
        
        response_schema = api_interface.get("response_schema", "")
        
        # 如果是登录接口，提取token
        if "登录" in api_interface.get("name", "") or "login" in api_interface.get("path", "").lower():
            rules["authToken"] = "token"
        
        # 如果是创建接口，提取ID
        api_name = api_interface.get("name", "").lower()
        if "创建" in api_name or "create" in api_name or "add" in api_name:
            if "文章" in api_name or "post" in api_name:
                rules["newPostId"] = "data.id"
            elif "评论" in api_name or "comment" in api_name:
                rules["newCommentId"] = "data.id"
        
        return rules
    
    def _generate_assertions(self, api_interface: Dict[str, Any], assertions: Optional[List[Dict[str, Any]]]) -> str:
        """生成断言代码（HttpRunner格式，已废弃）"""
        code = ""
        
        method = api_interface.get("method", "").upper()
        
        # 默认断言
        if method == "GET":
            code += "            .assert_equal(\"status_code\", 200)\n"
        elif method == "POST":
            code += "            .assert_equal(\"status_code\", 201)\n"
        elif method in ["PUT", "PATCH"]:
            code += "            .assert_equal(\"status_code\", 200)\n"
        elif method == "DELETE":
            code += "            .assert_equal(\"status_code\", 204)\n"
        
        code += "            .assert_not_equal(\"body.code\", None)\n"
        
        # 自定义断言
        if assertions:
            for assertion in assertions:
                assert_type = assertion.get("type", "equal")
                field = assertion.get("field", "")
                expected = assertion.get("expected", "")
                
                if assert_type == "equal":
                    code += f"            .assert_equal(\"{field}\", {repr(expected)})\n"
                elif assert_type == "not_equal":
                    code += f"            .assert_not_equal(\"{field}\", {repr(expected)})\n"
                elif assert_type == "contains":
                    code += f"            .assert_contains(\"{field}\", {repr(expected)})\n"
        
        return code
    
    def _generate_assertions_for_requests(self, api_interface: Dict[str, Any], assertions: Optional[List[Dict[str, Any]]]) -> str:
        """生成断言代码（requests库格式）"""
        code = ""
        
        method = api_interface.get("method", "").upper()
        
        # 默认断言：状态码
        if method == "GET":
            code += "    assert response.status_code == 200, f\"Expected status code 200, got {response.status_code}. Response: {response.text}\"\n"
        elif method == "POST":
            code += "    assert response.status_code in [200, 201], f\"Expected status code 200 or 201, got {response.status_code}. Response: {response.text}\"\n"
        elif method in ["PUT", "PATCH"]:
            code += "    assert response.status_code == 200, f\"Expected status code 200, got {response.status_code}. Response: {response.text}\"\n"
        elif method == "DELETE":
            code += "    assert response.status_code in [200, 204], f\"Expected status code 200 or 204, got {response.status_code}. Response: {response.text}\"\n"
        else:
            code += "    assert response.status_code < 400, f\"Expected status code < 400, got {response.status_code}. Response: {response.text}\"\n"
        
        # 解析响应数据
        code += "    try:\n"
        code += "        response_json = response.json()\n"
        code += "    except:\n"
        code += "        response_json = None\n"
        code += "        response_text = response.text\n"
        
        # 自定义断言
        if assertions:
            for assertion in assertions:
                assert_type = assertion.get("type", "equal")
                field = assertion.get("field", "")
                expected = assertion.get("expected", "")
                
                if assert_type == "equal":
                    if field == "status_code":
                        code += f"    assert response.status_code == {expected}, f\"Expected status code {expected}, got {{response.status_code}}\"\n"
                    elif field.startswith("body.") or field.startswith("json."):
                        # 提取 JSON 路径
                        json_path = field.replace("body.", "").replace("json.", "")
                        code += f"    assert response_json is not None, \"Response is not JSON\"\n"
                        code += f"    # TODO: 实现 JSON 路径提取和断言: {json_path} == {repr(expected)}\n"
                    else:
                        code += f"    # TODO: 实现断言: {field} == {repr(expected)}\n"
                elif assert_type == "not_equal":
                    if field == "status_code":
                        code += f"    assert response.status_code != {expected}, f\"Expected status code != {expected}, got {{response.status_code}}\"\n"
                    else:
                        code += f"    # TODO: 实现断言: {field} != {repr(expected)}\n"
                elif assert_type == "contains":
                    code += f"    assert {repr(expected)} in response.text, f\"Expected response to contain {repr(expected)}\"\n"
        
        return code
        
        return code


class JMeterCaseGenerator:
    """JMeter测试用例生成器（JMX格式）"""
    
    def generate_test_case(
        self,
        api_interface: Dict[str, Any],
        test_data: Optional[Dict[str, Any]] = None,
        extracted_data: Optional[Dict[str, Any]] = None,
        assertions: Optional[List[Dict[str, Any]]] = None,
        project_id: Optional[int] = None
    ) -> str:
        """
        生成JMeter测试用例（JMX格式，支持few-shot学习）
        
        Args:
            api_interface: API接口信息
            test_data: 测试数据
            extracted_data: 从前置步骤提取的数据
            assertions: 断言规则
        
        Returns:
            JMX XML字符串
        """
        api_name = api_interface.get("name", "test_api")
        method = api_interface.get("method", "GET").upper()
        url = api_interface.get("url", "")  # 统一使用url字段
        # base_url从测试环境中获取，不在接口模型中
        # full_url会在执行时由TestEnvironment.base_url + url组合
        full_url = url  # 实际执行时会从TestEnvironment.base_url获取并组合
        
        # 解析参数（统一格式）
        params = json.loads(api_interface.get("params", "{}")) if isinstance(api_interface.get("params"), str) else (api_interface.get("params") or {})
        headers = json.loads(api_interface.get("headers", "{}")) if isinstance(api_interface.get("headers"), str) else (api_interface.get("headers") or {})
        body = json.loads(api_interface.get("body", "{}")) if isinstance(api_interface.get("body"), str) else (api_interface.get("body") or {})
        
        # 使用提取的数据填充
        if extracted_data:
            if extracted_data.get("authToken"):
                headers["Authorization"] = f"Bearer {extracted_data['authToken']}"
        
        if test_data:
            params.update(test_data.get("params", {}))
            headers.update(test_data.get("headers", {}))
            if test_data.get("body"):
                if isinstance(body, dict):
                    body.update(test_data["body"])
                else:
                    body = test_data["body"]
        
        # 创建JMX根元素
        root = Element("jmeterTestPlan", version="1.2", properties="5.0", jmeter="5.6")
        
        # HashTree
        hash_tree = SubElement(root, "hashTree")
        
        # TestPlan
        test_plan = SubElement(hash_tree, "TestPlan", guiclass="TestPlanGui", testclass="TestPlan", testname=api_name, enabled="true")
        SubElement(test_plan, "stringProp", name="TestPlan.comments").text = api_interface.get("description", "")
        SubElement(test_plan, "boolProp", name="TestPlan.functional_mode").text = "false"
        SubElement(test_plan, "boolProp", name="TestPlan.serialize_threadgroups").text = "false"
        
        # ThreadGroup
        thread_group_tree = SubElement(hash_tree, "hashTree")
        thread_group = SubElement(thread_group_tree, "ThreadGroup", guiclass="ThreadGroupGui", testclass="ThreadGroup", testname="Thread Group", enabled="true")
        SubElement(thread_group, "stringProp", name="ThreadGroup.on_sample_error").text = "continue"
        SubElement(thread_group, "elementProp", name="ThreadGroup.main_controller", elementType="LoopController", guiclass="LoopControllerGui", testclass="LoopController", testname="Loop Controller", enabled="true")
        SubElement(thread_group, "stringProp", name="ThreadGroup.num_threads").text = "1"
        SubElement(thread_group, "stringProp", name="ThreadGroup.ramp_time").text = "1"
        SubElement(thread_group, "boolProp", name="ThreadGroup.scheduler").text = "false"
        SubElement(thread_group, "stringProp", name="ThreadGroup.duration").text = ""
        SubElement(thread_group, "stringProp", name="ThreadGroup.delay").text = ""
        
        # HTTP Request Sampler
        request_tree = SubElement(thread_group_tree, "hashTree")
        http_request = SubElement(request_tree, "HTTPSamplerProxy", guiclass="HttpTestSampleGui", testclass="HTTPSamplerProxy", testname=api_name, enabled="true")
        SubElement(http_request, "boolProp", name="HTTPSampler.postBodyRaw").text = "true" if body else "false"
        SubElement(http_request, "elementProp", name="HTTPsampler.Arguments", elementType="Arguments", guiclass="HTTPArgumentsPanel", testclass="Arguments", testname="User Defined Variables", enabled="true")
        
        # URL和Method
        SubElement(http_request, "stringProp", name="HTTPSampler.domain").text = ""
        SubElement(http_request, "stringProp", name="HTTPSampler.path").text = url
        SubElement(http_request, "stringProp", name="HTTPSampler.method").text = method
        
        # 请求头
        if headers:
            header_tree = SubElement(request_tree, "hashTree")
            header_manager = SubElement(header_tree, "HeaderManager", guiclass="HeaderPanel", testclass="HeaderManager", testname="HTTP Header Manager", enabled="true")
            collection_prop = SubElement(header_manager, "collectionProp", name="HeaderManager.headers")
            
            for key, value in headers.items():
                element_prop = SubElement(collection_prop, "elementProp", name=key, elementType="Header")
                SubElement(element_prop, "stringProp", name="Header.name").text = key
                SubElement(element_prop, "stringProp", name="Header.value").text = str(value)
        
        # 请求参数或Body
        if method in ["POST", "PUT", "PATCH"]:
            if body:
                if isinstance(body, dict):
                    body_str = json.dumps(body, ensure_ascii=False)
                else:
                    body_str = str(body)
                
                args_tree = SubElement(request_tree, "hashTree")
                element_prop = SubElement(args_tree, "elementProp", name="HTTPsampler.Arguments", elementType="Arguments")
                collection_prop = SubElement(element_prop, "collectionProp", name="Arguments.arguments")
                
                arg_prop = SubElement(collection_prop, "elementProp", name="", elementType="HTTPArgument")
                SubElement(arg_prop, "boolProp", name="HTTPArgument.always_encode").text = "false"
                SubElement(arg_prop, "stringProp", name="Argument.value").text = body_str
                SubElement(arg_prop, "stringProp", name="Argument.metadata").text = "="
            elif params:
                # 添加参数
                args_tree = SubElement(request_tree, "hashTree")
                element_prop = SubElement(args_tree, "elementProp", name="HTTPsampler.Arguments", elementType="Arguments")
                collection_prop = SubElement(element_prop, "collectionProp", name="Arguments.arguments")
                
                for key, value in params.items():
                    arg_prop = SubElement(collection_prop, "elementProp", name=key, elementType="HTTPArgument")
                    SubElement(arg_prop, "boolProp", name="HTTPArgument.always_encode").text = "false"
                    SubElement(arg_prop, "stringProp", name="Argument.value").text = str(value)
                    SubElement(arg_prop, "stringProp", name="Argument.metadata").text = "="
        
        # 断言
        if assertions:
            assertion_tree = SubElement(request_tree, "hashTree")
            response_assertion = SubElement(assertion_tree, "ResponseAssertion", guiclass="AssertionGui", testclass="ResponseAssertion", testname="Response Assertion", enabled="true")
            SubElement(response_assertion, "collectionProp", name="Asserion.test_strings")
            
            for assertion in assertions:
                assert_type = assertion.get("type", "equal")
                field = assertion.get("field", "")
                expected = assertion.get("expected", "")
                
                if assert_type == "equal":
                    string_prop = SubElement(response_assertion, "stringProp", name="")
                    string_prop.text = f"{field}={expected}"
        
        # 格式化XML
        xml_str = tostring(root, encoding='unicode')
        dom = minidom.parseString(xml_str)
        return dom.toprettyxml(indent="  ")
    
    def _format_jmx_value(self, value: Any) -> str:
        """格式化JMX值"""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

