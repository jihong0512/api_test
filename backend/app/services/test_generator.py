"""
[已废弃] 此文件已废弃，请使用 test_case_generator.py 中的 PytestCaseGenerator 和 JMeterCaseGenerator

保留此文件仅用于向后兼容，新代码请使用：
- PytestCaseGenerator: 生成HttpRunner格式的Pytest测试用例
- JMeterCaseGenerator: 生成JMeter测试脚本
"""

from typing import List, Dict, Any, Optional
from faker import Faker
import json

from app.services.llm_service import LLMService
from app.services.vector_service import VectorService
from app.services.db_service import DatabaseService


class TestGenerator:
    """
    [已废弃] 请使用 PytestCaseGenerator 或 JMeterCaseGenerator
    
    Deprecated: Use PytestCaseGenerator or JMeterCaseGenerator instead
    """
    """测试用例生成器"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.vector_service = VectorService()
        self.db_service = DatabaseService()
        self.faker = Faker('zh_CN')
    
    async def generate_test_data(
        self,
        api_info: Dict[str, Any],
        db_schema: Optional[Dict[str, Any]] = None,
        knowledge_graph: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """生成测试数据"""
        test_data = {
            "params": {},
            "headers": {},
            "body": {}
        }
        
        # 根据API信息生成基础测试数据
        if api_info.get("params"):
            for param, param_info in api_info["params"].items():
                test_data["params"][param] = self._generate_field_data(param_info, db_schema)
        
        if api_info.get("body"):
            if isinstance(api_info["body"], dict):
                for field, field_info in api_info["body"].items():
                    test_data["body"][field] = self._generate_field_data(field_info, db_schema)
        
        # 结合知识图谱生成符合业务逻辑的数据
        if knowledge_graph:
            test_data = await self._enhance_with_knowledge_graph(test_data, api_info, knowledge_graph)
        
        return test_data
    
    def _generate_field_data(self, field_info: Any, db_schema: Optional[Dict[str, Any]] = None) -> Any:
        """根据字段信息生成测试数据"""
        if isinstance(field_info, dict):
            field_type = field_info.get("type", "string")
        else:
            field_type = str(field_info)
        
        type_map = {
            "string": self.faker.word(),
            "integer": self.faker.random_int(),
            "number": self.faker.pyfloat(),
            "boolean": self.faker.boolean(),
            "email": self.faker.email(),
            "phone": self.faker.phone_number(),
            "date": self.faker.date().isoformat(),
            "datetime": self.faker.iso8601(),
            "url": self.faker.url(),
        }
        
        return type_map.get(field_type.lower(), self.faker.word())
    
    async def _enhance_with_knowledge_graph(
        self,
        test_data: Dict[str, Any],
        api_info: Dict[str, Any],
        knowledge_graph: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用知识图谱增强测试数据"""
        # 识别需要关联数据库字段的参数
        prompt = f"""
基于知识图谱，为以下API生成符合业务逻辑的测试数据：

API信息：{json.dumps(api_info, ensure_ascii=False, indent=2)}
当前测试数据：{json.dumps(test_data, ensure_ascii=False, indent=2)}
知识图谱信息：{json.dumps(knowledge_graph, ensure_ascii=False, indent=2)}

请确保生成的测试数据：
1. 符合数据库约束（如外键关联）
2. 符合业务规则（如用户ID必须存在于用户表）
3. 数据关系正确（如订单ID必须关联到存在的订单）

输出增强后的测试数据（JSON格式）：
"""
        result = await self.llm_service.chat(prompt)
        try:
            enhanced_data = json.loads(result)
            return enhanced_data
        except:
            return test_data
    
    async def generate_pytest_case(
        self,
        api_info: Dict[str, Any],
        test_data: Dict[str, Any],
        assertions: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """生成Pytest测试用例（HttpRunner格式）"""
        case_template = f"""
import pytest
from httprunner import HttpRunner, Config, Step, RunRequest

class Test{api_info['name'].replace(' ', '_')}:
    
    config = Config("测试配置").base_url("{api_info.get('base_url', '')}")
    
    teststeps = [
        Step(
            RunRequest("{api_info['name']}")
            .{api_info['method'].lower()}("{api_info['url']}")
            {self._format_headers(api_info.get('headers', {}))}
            {self._format_params(test_data.get('params', {}))}
            {self._format_body(test_data.get('body', {}))}
            {self._format_assertions(assertions or [])}
        )
    ]
"""
        return case_template
    
    def _format_headers(self, headers: Dict[str, Any]) -> str:
        if not headers:
            return ""
        lines = [f".headers({json.dumps(headers, ensure_ascii=False)})"]
        return "\n            ".join(lines)
    
    def _format_params(self, params: Dict[str, Any]) -> str:
        if not params:
            return ""
        return f".params({json.dumps(params, ensure_ascii=False)})"
    
    def _format_body(self, body: Dict[str, Any]) -> str:
        if not body:
            return ""
        return f".json({json.dumps(body, ensure_ascii=False)})"
    
    def _format_assertions(self, assertions: List[Dict[str, Any]]) -> str:
        if not assertions:
            return ".validate().assert_equal('status_code', 200)"
        
        lines = [".validate()"]
        for assertion in assertions:
            assertion_type = assertion.get("type", "equal")
            if assertion_type == "status_code":
                lines.append(f".assert_equal('status_code', {assertion.get('expected', 200)})")
            elif assertion_type == "contains":
                field = assertion.get("field", "")
                value = assertion.get("value", "")
                lines.append(f".assert_contains('body.{field}', '{value}')")
        
        return "\n            ".join(lines)
    
    async def generate_jmeter_case(
        self,
        api_info: Dict[str, Any],
        test_data: Dict[str, Any]
    ) -> str:
        """生成JMeter测试用例"""
        # JMeter XML格式较复杂，这里简化处理
        jmx_template = f"""<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="{api_info['name']}">
    </TestPlan>
    <hashTree>
      <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="{api_info['name']}">
        <stringProp name="HTTPSampler.domain">{api_info.get('domain', '')}</stringProp>
        <stringProp name="HTTPSampler.path">{api_info['url']}</stringProp>
        <stringProp name="HTTPSampler.method">{api_info['method']}</stringProp>
      </HTTPSamplerProxy>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""
        return jmx_template
    
    async def analyze_dependencies(
        self,
        api_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析接口依赖关系"""
        dependency_graph = {
            "nodes": [],
            "edges": []
        }
        
        # 提取所有接口作为节点
        for api in api_list:
            dependency_graph["nodes"].append({
                "id": api.get("id", api.get("name")),
                "name": api.get("name"),
                "method": api.get("method"),
                "url": api.get("url")
            })
        
        # 分析依赖关系（通过参数、响应等）
        for i, api1 in enumerate(api_list):
            for j, api2 in enumerate(api_list):
                if i != j:
                    # 简化的依赖检测：如果api2的响应字段在api1的请求中使用
                    if self._has_dependency(api1, api2):
                        dependency_graph["edges"].append({
                            "source": api1.get("id", api1.get("name")),
                            "target": api2.get("id", api2.get("name")),
                            "type": "data_dependency"
                        })
        
        return dependency_graph
    
    def _has_dependency(self, api1: Dict[str, Any], api2: Dict[str, Any]) -> bool:
        """检测两个接口是否有依赖关系"""
        # 简化实现：检查api2的响应字段是否在api1的请求中出现
        api1_params = str(api1.get("params", "")) + str(api1.get("body", ""))
        api2_response = str(api2.get("response_schema", ""))
        
        # 这里应该更智能地分析，简化处理
        return False



