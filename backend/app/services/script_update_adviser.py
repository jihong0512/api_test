"""
智能测试脚本更新建议服务
提供两种策略：重新生成 和 差异更新
"""
import json
from typing import Dict, List, Any, Optional
from app.services.api_change_detector import APIChangeDetector
from app.services.test_case_generator import PytestCaseGenerator
from app.services.llm_service import LLMService
from app.services.request_builder import RequestBuilder


class ScriptUpdateAdviser:
    """智能测试脚本更新建议器"""
    
    def __init__(self):
        self.change_detector = APIChangeDetector()
        self.case_generator = PytestCaseGenerator()
        self.llm_service = LLMService()
        self.request_builder = RequestBuilder()
    
    async def generate_update_suggestions(
        self,
        change_info: Dict[str, Any],
        test_case: Dict[str, Any],
        update_strategy: str = "auto"
    ) -> Dict[str, Any]:
        """
        生成更新建议
        
        Args:
            change_info: 变更信息（来自APIChangeDetector）
            test_case: 测试用例信息
            update_strategy: 更新策略
                - "auto": 自动选择策略
                - "regenerate": 重新生成
                - "incremental": 差异更新
        
        Returns:
            更新建议，包含：
            - strategy: 建议的策略
            - reasoning: 策略选择理由
            - update_plan: 更新计划
            - manual_interventions: 需要人工介入的部分
            - estimated_effort: 预估工作量
        """
        if update_strategy == "auto":
            strategy = await self._recommend_strategy(change_info, test_case)
        elif update_strategy == "regenerate":
            strategy = "regenerate"
        else:
            strategy = "incremental"
        
        if strategy == "regenerate":
            return await self._generate_regenerate_plan(change_info, test_case)
        else:
            return await self._generate_incremental_plan(change_info, test_case)
    
    async def _recommend_strategy(
        self,
        change_info: Dict[str, Any],
        test_case: Dict[str, Any]
    ) -> str:
        """
        智能推荐更新策略
        
        策略选择规则：
        - 如果变更级别为 breaking 或 high，推荐重新生成
        - 如果变更涉及核心业务逻辑，推荐重新生成
        - 如果是简单的参数变更，推荐差异更新
        """
        changes = change_info.get("changes", {})
        change_level = changes.get("change_level", "low")
        
        # 检查变更类型
        change_types = changes.get("change_types", [])
        
        # 破坏性或高风险变更 -> 重新生成
        if change_level in ["breaking", "high"]:
            return "regenerate"
        
        # URL或方法变更 -> 重新生成
        if any("basic_url" in ct or "basic_method" in ct for ct in change_types):
            return "regenerate"
        
        # 响应Schema结构变更 -> 重新生成
        if "response_schema" in change_types:
            response_changes = changes.get("detailed_changes", {}).get("response_schema", {})
            if response_changes.get("change_types"):
                change_type_list = response_changes["change_types"]
                if "type_changes" in change_type_list or "fields_removed" in change_type_list:
                    return "regenerate"
        
        # 其他情况 -> 差异更新
        return "incremental"
    
    async def _generate_regenerate_plan(
        self,
        change_info: Dict[str, Any],
        test_case: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成重新生成策略的更新计划
        """
        new_interface = change_info.get("interface", {})
        old_interface = change_info.get("old_interface", {})
        
        # 提取新接口信息
        method = new_interface.get("method", "GET")
        url = new_interface.get("url", "")
        params = self._parse_json_field(new_interface.get("params"))
        body = self._parse_json_field(new_interface.get("body"))
        headers = self._parse_json_field(new_interface.get("headers"))
        response_schema = self._parse_json_field(new_interface.get("response_schema"))
        
        # 生成新的测试代码
        try:
            # 获取测试数据和断言
            test_data = self._parse_json_field(test_case.get("test_data")) or {}
            assertions = self._parse_json_field(test_case.get("assertions")) or []
            
            new_test_code = self.case_generator.generate_test_case(
                api_interface={
                    "method": method,
                    "url": url,
                    "params": params,
                    "body": body,
                    "headers": headers,
                    "response_schema": response_schema,
                    "description": new_interface.get("description", "")
                },
                test_data=test_data,
                assertions=assertions
            )
            
            # 对比新旧代码差异
            old_test_code = test_case.get("test_code", "")
            code_diff = self._compare_code(old_test_code, new_test_code)
            
            return {
                "strategy": "regenerate",
                "reasoning": "接口发生重大变更，建议重新生成测试脚本以确保完整性和正确性",
                "update_plan": {
                    "steps": [
                        "备份现有测试用例",
                        "使用新接口定义重新生成测试代码",
                        "迁移自定义测试数据和断言逻辑",
                        "验证新生成的测试代码",
                        "更新测试用例记录"
                    ],
                    "new_test_code": new_test_code,
                    "code_changes": code_diff
                },
                "manual_interventions": [
                    {
                        "type": "custom_logic",
                        "description": "检查并迁移测试用例中的自定义逻辑",
                        "location": "test_case.custom_code",
                        "priority": "high"
                    },
                    {
                        "type": "test_data",
                        "description": "验证测试数据是否适配新接口参数",
                        "location": "test_case.test_data",
                        "priority": "medium"
                    },
                    {
                        "type": "assertions",
                        "description": "验证断言是否适配新的响应结构",
                        "location": "test_case.assertions",
                        "priority": "high"
                    }
                ],
                "estimated_effort": "medium",
                "automation_rate": 0.8  # 80%可自动化
            }
        except Exception as e:
            return {
                "strategy": "regenerate",
                "reasoning": "接口发生重大变更，建议重新生成测试脚本",
                "error": str(e),
                "manual_interventions": [
                    {
                        "type": "error_handling",
                        "description": f"代码生成失败: {str(e)}，需要人工介入",
                        "priority": "critical"
                    }
                ],
                "estimated_effort": "high",
                "automation_rate": 0.0
            }
    
    async def _generate_incremental_plan(
        self,
        change_info: Dict[str, Any],
        test_case: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成差异更新策略的更新计划
        """
        changes = change_info.get("changes", {})
        detailed_changes = changes.get("detailed_changes", {})
        change_types = changes.get("change_types", [])
        
        update_steps = []
        code_modifications = []
        manual_checks = []
        
        # 分析各类变更并生成更新步骤
        if "params" in change_types:
            param_changes = detailed_changes.get("params", {})
            param_update = self._analyze_param_changes(param_changes, test_case)
            update_steps.extend(param_update["steps"])
            code_modifications.extend(param_update["code_modifications"])
            manual_checks.extend(param_update["manual_checks"])
        
        if "body" in change_types:
            body_changes = detailed_changes.get("body", {})
            body_update = self._analyze_body_changes(body_changes, test_case)
            update_steps.extend(body_update["steps"])
            code_modifications.extend(body_update["code_modifications"])
            manual_checks.extend(body_update["manual_checks"])
        
        if "response_schema" in change_types:
            response_changes = detailed_changes.get("response_schema", {})
            response_update = self._analyze_response_changes(response_changes, test_case)
            update_steps.extend(response_update["steps"])
            code_modifications.extend(response_update["code_modifications"])
            manual_checks.extend(response_update["manual_checks"])
        
        if "headers" in change_types:
            header_changes = detailed_changes.get("headers", {})
            header_update = self._analyze_header_changes(header_changes, test_case)
            update_steps.extend(header_update["steps"])
            code_modifications.extend(header_update["code_modifications"])
        
        # 使用LLM生成智能代码修改建议
        llm_suggestions = await self._generate_llm_code_suggestions(
            change_info, test_case, code_modifications
        )
        
        return {
            "strategy": "incremental",
            "reasoning": "接口变更较小，可以通过差异更新方式智能修改现有脚本",
            "update_plan": {
                "steps": update_steps,
                "code_modifications": code_modifications,
                "llm_suggestions": llm_suggestions
            },
            "manual_interventions": manual_checks,
            "estimated_effort": "low",
            "automation_rate": 0.6  # 60%可自动化
        }
    
    def _analyze_param_changes(
        self,
        param_changes: Dict[str, Any],
        test_case: Dict[str, Any]
    ) -> Dict[str, Any]:
        """分析参数变更"""
        steps = []
        code_modifications = []
        manual_checks = []
        
        diff = param_changes.get("diff", {})
        
        # 处理新增参数
        if "dictionary_item_added" in diff:
            added_params = diff["dictionary_item_added"]
            steps.append(f"新增 {len(added_params)} 个请求参数")
            code_modifications.append({
                "type": "add_params",
                "params": added_params,
                "suggestion": "在请求参数中添加新增的参数字段"
            })
            manual_checks.append({
                "type": "param_validation",
                "description": "验证新增参数是否为必填，如是则需要在测试数据中添加",
                "priority": "medium"
            })
        
        # 处理删除参数
        if "dictionary_item_removed" in diff:
            removed_params = diff["dictionary_item_removed"]
            steps.append(f"删除 {len(removed_params)} 个请求参数")
            code_modifications.append({
                "type": "remove_params",
                "params": removed_params,
                "suggestion": "从请求参数中移除已删除的参数字段"
            })
        
        # 处理参数值变更
        if "values_changed" in diff:
            changed_params = diff["values_changed"]
            steps.append(f"修改 {len(changed_params)} 个参数定义")
            manual_checks.append({
                "type": "param_type_check",
                "description": "检查参数类型变更是否影响现有测试数据",
                "priority": "high"
            })
        
        return {
            "steps": steps,
            "code_modifications": code_modifications,
            "manual_checks": manual_checks
        }
    
    def _analyze_body_changes(
        self,
        body_changes: Dict[str, Any],
        test_case: Dict[str, Any]
    ) -> Dict[str, Any]:
        """分析请求体变更"""
        steps = []
        code_modifications = []
        manual_checks = []
        
        diff = body_changes.get("diff", {})
        
        # 处理新增字段
        if "dictionary_item_added" in diff:
            added_fields = diff["dictionary_item_added"]
            steps.append(f"请求体新增 {len(added_fields)} 个字段")
            code_modifications.append({
                "type": "update_body",
                "action": "add_fields",
                "fields": added_fields,
                "suggestion": "在请求体中添加新增字段，需要生成对应的测试数据"
            })
            manual_checks.append({
                "type": "required_field_check",
                "description": "检查新增字段是否为必填，如是则需要更新测试数据",
                "priority": "high"
            })
        
        # 处理删除字段
        if "dictionary_item_removed" in diff:
            removed_fields = diff["dictionary_item_removed"]
            steps.append(f"请求体删除 {len(removed_fields)} 个字段")
            code_modifications.append({
                "type": "update_body",
                "action": "remove_fields",
                "fields": removed_fields,
                "suggestion": "从请求体中移除已删除的字段"
            })
        
        # 处理类型变更
        if "type_changes" in diff:
            type_changes = diff["type_changes"]
            steps.append(f"请求体 {len(type_changes)} 个字段类型变更")
            manual_checks.append({
                "type": "data_compatibility",
                "description": "检查字段类型变更是否导致测试数据不兼容，需要更新测试数据",
                "priority": "critical"
            })
        
        return {
            "steps": steps,
            "code_modifications": code_modifications,
            "manual_checks": manual_checks
        }
    
    def _analyze_response_changes(
        self,
        response_changes: Dict[str, Any],
        test_case: Dict[str, Any]
    ) -> Dict[str, Any]:
        """分析响应Schema变更"""
        steps = []
        code_modifications = []
        manual_checks = []
        
        diff = response_changes.get("diff", {})
        
        # 处理新增字段
        if "dictionary_item_added" in diff:
            added_fields = diff["dictionary_item_added"]
            steps.append(f"响应新增 {len(added_fields)} 个字段")
            code_modifications.append({
                "type": "update_assertions",
                "action": "add_assertions",
                "fields": added_fields,
                "suggestion": "可以添加对新字段的断言校验"
            })
        
        # 处理删除字段
        if "dictionary_item_removed" in diff:
            removed_fields = diff["dictionary_item_removed"]
            steps.append(f"响应删除 {len(removed_fields)} 个字段")
            code_modifications.append({
                "type": "update_assertions",
                "action": "remove_assertions",
                "fields": removed_fields,
                "suggestion": "移除对已删除字段的断言，避免测试失败"
            })
            manual_checks.append({
                "type": "assertion_update",
                "description": "需要从断言中移除对已删除字段的检查",
                "priority": "high"
            })
        
        # 处理类型变更
        if "type_changes" in diff:
            type_changes = diff["type_changes"]
            steps.append(f"响应 {len(type_changes)} 个字段类型变更")
            manual_checks.append({
                "type": "assertion_type_check",
                "description": "检查断言中的类型判断是否需要更新",
                "priority": "critical"
            })
        
        return {
            "steps": steps,
            "code_modifications": code_modifications,
            "manual_checks": manual_checks
        }
    
    def _analyze_header_changes(
        self,
        header_changes: Dict[str, Any],
        test_case: Dict[str, Any]
    ) -> Dict[str, Any]:
        """分析请求头变更"""
        steps = []
        code_modifications = []
        
        diff = header_changes.get("diff", {})
        
        if "dictionary_item_added" in diff:
            added_headers = diff["dictionary_item_added"]
            steps.append(f"新增 {len(added_headers)} 个请求头")
            code_modifications.append({
                "type": "update_headers",
                "action": "add_headers",
                "headers": added_headers
            })
        
        if "dictionary_item_removed" in diff:
            removed_headers = diff["dictionary_item_removed"]
            steps.append(f"删除 {len(removed_headers)} 个请求头")
            code_modifications.append({
                "type": "update_headers",
                "action": "remove_headers",
                "headers": removed_headers
            })
        
        return {
            "steps": steps,
            "code_modifications": code_modifications,
            "manual_checks": []
        }
    
    def _compare_code(self, old_code: str, new_code: str) -> Dict[str, Any]:
        """对比新旧代码差异"""
        # 简单的代码对比，实际可以使用更专业的diff工具
        old_lines = old_code.split("\n")
        new_lines = new_code.split("\n")
        
        added_lines = [line for line in new_lines if line not in old_lines]
        removed_lines = [line for line in old_lines if line not in new_lines]
        
        return {
            "added_lines_count": len(added_lines),
            "removed_lines_count": len(removed_lines),
            "added_lines": added_lines[:10],  # 只显示前10行
            "removed_lines": removed_lines[:10]
        }
    
    async def _generate_llm_code_suggestions(
        self,
        change_info: Dict[str, Any],
        test_case: Dict[str, Any],
        code_modifications: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """使用LLM生成智能代码修改建议"""
        prompt = f"""
基于以下接口变更信息和代码修改建议，生成具体的代码修改指导：

接口变更信息：
{json.dumps(change_info, ensure_ascii=False, indent=2)}

测试用例代码片段：
```python
{test_case.get("test_code", "")[:500]}
```

需要执行的代码修改：
{json.dumps(code_modifications, ensure_ascii=False, indent=2)}

请为每个代码修改项提供：
1. 具体的代码位置（行号或函数名）
2. 修改前后的代码对比
3. 修改原因说明
4. 需要注意的事项

请用中文回答，格式清晰。
"""
        
        try:
            suggestions = await self.llm_service.chat(prompt)
            return [
                {
                    "type": "llm_suggestion",
                    "content": suggestions,
                    "source": "llm"
                }
            ]
        except Exception as e:
            return [
                {
                    "type": "error",
                    "content": f"LLM建议生成失败: {str(e)}",
                    "source": "system"
                }
            ]
    
    def _parse_json_field(self, field_value: Optional[str]) -> Any:
        """解析JSON字段"""
        if field_value is None:
            return None
        if isinstance(field_value, str):
            try:
                return json.loads(field_value)
            except:
                return field_value
        return field_value

