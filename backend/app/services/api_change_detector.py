"""
API文档变更检测服务
对比新旧API文档，识别接口的增、删、改
"""
import json
from typing import Dict, List, Any, Optional, Tuple
from deepdiff import DeepDiff
from app.services.llm_service import LLMService


class APIChangeDetector:
    """API文档变更检测器"""
    
    def __init__(self):
        self.llm_service = LLMService()
    
    def detect_changes(
        self,
        old_interfaces: List[Dict[str, Any]],
        new_interfaces: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        检测API接口变更
        
        Args:
            old_interfaces: 旧的接口列表
            new_interfaces: 新的接口列表
            
        Returns:
            变更检测结果，包含：
            - added: 新增的接口列表
            - deleted: 删除的接口列表
            - modified: 修改的接口列表
            - unchanged: 未变更的接口列表
        """
        # 建立接口索引（使用 method + url 作为唯一标识）
        old_map = self._build_interface_map(old_interfaces)
        new_map = self._build_interface_map(new_interfaces)
        
        old_keys = set(old_map.keys())
        new_keys = set(new_map.keys())
        
        # 识别新增、删除、修改、未变更的接口
        added_keys = new_keys - old_keys
        deleted_keys = old_keys - new_keys
        common_keys = old_keys & new_keys
        
        added = [new_map[key] for key in added_keys]
        deleted = [old_map[key] for key in deleted_keys]
        
        modified = []
        unchanged = []
        
        for key in common_keys:
            old_iface = old_map[key]
            new_iface = new_map[key]
            
            # 深度比较接口差异
            changes = self._compare_interface(old_iface, new_iface)
            
            if changes["has_changes"]:
                modified.append({
                    "interface": new_iface,
                    "old_interface": old_iface,
                    "changes": changes
                })
            else:
                unchanged.append(new_iface)
        
        return {
            "added": added,
            "deleted": deleted,
            "modified": modified,
            "unchanged": unchanged,
            "summary": {
                "total_added": len(added),
                "total_deleted": len(deleted),
                "total_modified": len(modified),
                "total_unchanged": len(unchanged)
            }
        }
    
    def _build_interface_map(self, interfaces: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """构建接口映射表"""
        interface_map = {}
        for iface in interfaces:
            method = iface.get("method", "").upper()
            url = iface.get("url", "").strip()
            key = f"{method}:{url}"
            interface_map[key] = iface
        return interface_map
    
    def _compare_interface(
        self,
        old_iface: Dict[str, Any],
        new_iface: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        比较单个接口的变更
        
        Returns:
            变更详情，包括：
            - has_changes: 是否有变更
            - change_types: 变更类型列表
            - detailed_changes: 详细变更信息
        """
        change_types = []
        detailed_changes = {}
        
        # 比较基本信息
        basic_fields = ["name", "method", "url", "description"]
        for field in basic_fields:
            old_val = old_iface.get(field)
            new_val = new_iface.get(field)
            if old_val != new_val:
                change_types.append(f"basic_{field}")
                detailed_changes[field] = {
                    "old": old_val,
                    "new": new_val
                }
        
        # 比较请求参数
        old_params = self._parse_json_field(old_iface.get("params"))
        new_params = self._parse_json_field(new_iface.get("params"))
        param_changes = self._compare_schema(old_params, new_params)
        if param_changes["has_changes"]:
            change_types.append("params")
            detailed_changes["params"] = param_changes
        
        # 比较请求体
        old_body = self._parse_json_field(old_iface.get("body"))
        new_body = self._parse_json_field(new_iface.get("body"))
        body_changes = self._compare_schema(old_body, new_body)
        if body_changes["has_changes"]:
            change_types.append("body")
            detailed_changes["body"] = body_changes
        
        # 比较请求头
        old_headers = self._parse_json_field(old_iface.get("headers"))
        new_headers = self._parse_json_field(new_iface.get("headers"))
        header_changes = self._compare_schema(old_headers, new_headers)
        if header_changes["has_changes"]:
            change_types.append("headers")
            detailed_changes["headers"] = header_changes
        
        # 比较响应Schema
        old_response = self._parse_json_field(old_iface.get("response_schema"))
        new_response = self._parse_json_field(new_iface.get("response_schema"))
        response_changes = self._compare_schema(old_response, new_response)
        if response_changes["has_changes"]:
            change_types.append("response_schema")
            detailed_changes["response_schema"] = response_changes
        
        return {
            "has_changes": len(change_types) > 0,
            "change_types": change_types,
            "detailed_changes": detailed_changes,
            "change_level": self._assess_change_level(change_types, detailed_changes)
        }
    
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
    
    def _compare_schema(
        self,
        old_schema: Any,
        new_schema: Any
    ) -> Dict[str, Any]:
        """
        比较Schema的变更（用于params、body、response_schema等）
        
        Returns:
            包含 has_changes 和 diff 的字典
        """
        if old_schema == new_schema:
            return {"has_changes": False}
        
        # 使用DeepDiff进行深度比较
        try:
            diff = DeepDiff(old_schema, new_schema, ignore_order=False, verbose_level=2)
            diff_dict = diff.to_dict()
            
            # 提取变更类型
            change_types = []
            if "dictionary_item_added" in diff_dict:
                change_types.append("fields_added")
            if "dictionary_item_removed" in diff_dict:
                change_types.append("fields_removed")
            if "values_changed" in diff_dict:
                change_types.append("values_changed")
            if "type_changes" in diff_dict:
                change_types.append("type_changes")
            
            return {
                "has_changes": True,
                "change_types": change_types,
                "diff": diff_dict,
                "summary": self._summarize_diff(diff_dict)
            }
        except Exception as e:
            # 如果DeepDiff失败，使用简单的比较
            return {
                "has_changes": True,
                "change_types": ["unknown"],
                "error": str(e)
            }
    
    def _summarize_diff(self, diff_dict: Dict[str, Any]) -> str:
        """总结差异信息"""
        summary_parts = []
        
        if "dictionary_item_added" in diff_dict:
            added = diff_dict["dictionary_item_added"]
            summary_parts.append(f"新增 {len(added)} 个字段")
        
        if "dictionary_item_removed" in diff_dict:
            removed = diff_dict["dictionary_item_removed"]
            summary_parts.append(f"删除 {len(removed)} 个字段")
        
        if "values_changed" in diff_dict:
            changed = diff_dict["values_changed"]
            summary_parts.append(f"修改 {len(changed)} 个字段值")
        
        if "type_changes" in diff_dict:
            type_changed = diff_dict["type_changes"]
            summary_parts.append(f"类型变更 {len(type_changed)} 个字段")
        
        return "; ".join(summary_parts) if summary_parts else "存在变更"
    
    def _assess_change_level(
        self,
        change_types: List[str],
        detailed_changes: Dict[str, Any]
    ) -> str:
        """
        评估变更级别
        
        Returns:
            - "low": 低风险变更（如描述、可选参数）
            - "medium": 中等风险变更（如参数类型变更、新增必填参数）
            - "high": 高风险变更（如URL变更、删除必填参数、响应结构变更）
            - "breaking": 破坏性变更（如方法变更、接口删除）
        """
        # 检查破坏性变更
        if any("basic_url" in ct or "basic_method" in ct for ct in change_types):
            return "breaking"
        
        # 检查高风险变更
        high_risk_indicators = [
            "params" in change_types and "fields_removed" in str(detailed_changes),
            "response_schema" in change_types and "type_changes" in str(detailed_changes),
            "body" in change_types and "fields_removed" in str(detailed_changes)
        ]
        
        if any(high_risk_indicators):
            return "high"
        
        # 检查中等风险变更
        medium_risk_indicators = [
            "params" in change_types or "body" in change_types,
            "response_schema" in change_types
        ]
        
        if any(medium_risk_indicators):
            return "medium"
        
        # 低风险变更
        return "low"
    
    async def analyze_impact_on_test_cases(
        self,
        changes: Dict[str, Any],
        affected_test_cases: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        分析变更对测试用例的影响
        
        Args:
            changes: 变更检测结果
            affected_test_cases: 受影响的测试用例列表
            
        Returns:
            影响分析结果
        """
        impact_analysis = {
            "affected_cases": [],
            "risk_assessment": {},
            "recommendations": []
        }
        
        # 分析每个受影响的测试用例
        for test_case in affected_test_cases:
            case_analysis = {
                "test_case_id": test_case.get("id"),
                "test_case_name": test_case.get("name"),
                "impact_level": "unknown",
                "required_actions": [],
                "estimated_effort": "unknown"
            }
            
            # 根据变更类型判断影响
            api_interface_id = test_case.get("api_interface_id")
            if api_interface_id:
                # 找到对应的变更
                interface_key = self._find_interface_change(changes, api_interface_id)
                
                if interface_key:
                    if interface_key in changes.get("deleted", []):
                        case_analysis["impact_level"] = "critical"
                        case_analysis["required_actions"] = [
                            "接口已删除，需要删除或重新关联测试用例"
                        ]
                        case_analysis["estimated_effort"] = "high"
                    elif interface_key in [m["interface"].get("id") for m in changes.get("modified", [])]:
                        mod_info = next(
                            m for m in changes["modified"]
                            if m["interface"].get("id") == api_interface_id
                        )
                        change_level = mod_info["changes"].get("change_level", "low")
                        
                        if change_level == "breaking":
                            case_analysis["impact_level"] = "critical"
                            case_analysis["required_actions"] = [
                                "需要重新生成测试用例代码"
                            ]
                        elif change_level == "high":
                            case_analysis["impact_level"] = "high"
                            case_analysis["required_actions"] = [
                                "需要更新测试数据和断言"
                            ]
                        elif change_level == "medium":
                            case_analysis["impact_level"] = "medium"
                            case_analysis["required_actions"] = [
                                "需要验证测试用例是否仍然有效"
                            ]
                        else:
                            case_analysis["impact_level"] = "low"
                            case_analysis["required_actions"] = [
                                "建议重新运行测试验证"
                            ]
            
            impact_analysis["affected_cases"].append(case_analysis)
        
        # 使用LLM生成智能建议
        llm_recommendations = await self._generate_llm_recommendations(changes, impact_analysis)
        impact_analysis["recommendations"].extend(llm_recommendations)
        
        return impact_analysis
    
    def _find_interface_change(self, changes: Dict[str, Any], interface_id: int) -> Optional[str]:
        """查找接口对应的变更"""
        # 这里简化处理，实际应该根据interface_id匹配
        # 由于我们使用的是method+url作为key，这里需要扩展逻辑
        return None
    
    async def _generate_llm_recommendations(
        self,
        changes: Dict[str, Any],
        impact_analysis: Dict[str, Any]
    ) -> List[str]:
        """使用LLM生成智能建议"""
        prompt = f"""
基于以下API变更信息，提供测试脚本维护建议：

变更摘要：
- 新增接口：{changes['summary']['total_added']}个
- 删除接口：{changes['summary']['total_deleted']}个
- 修改接口：{changes['summary']['total_modified']}个
- 未变更接口：{changes['summary']['total_unchanged']}个

受影响测试用例：{len(impact_analysis['affected_cases'])}个

请提供3-5条具体的维护建议，包括：
1. 如何处理新增接口
2. 如何处理删除接口
3. 如何处理修改接口
4. 如何降低维护成本
5. 如何保障测试脚本有效性

请用简洁的中文回答，每条建议不超过50字。
"""
        
        try:
            recommendations = await self.llm_service.chat(prompt)
            # 解析LLM返回的建议（假设返回的是列表或换行分隔的文本）
            if isinstance(recommendations, list):
                return recommendations
            elif isinstance(recommendations, str):
                return [r.strip() for r in recommendations.split("\n") if r.strip()]
            else:
                return []
        except Exception as e:
            return [
                "建议重新生成受影响接口的测试用例",
                "建议运行完整测试套件验证变更影响",
                "建议建立API文档变更监控机制"
            ]

