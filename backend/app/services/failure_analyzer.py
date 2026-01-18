from typing import Dict, Any, List, Optional
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import TestResult, TestTask, TestCase
from app.services.llm_service import LLMService


class FailureAnalyzer:
    """失败分析器：智能分析测试失败原因"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.llm_service = LLMService()
    
    def analyze_failure(
        self,
        test_result: TestResult,
        test_case: Optional[TestCase] = None
    ) -> Dict[str, Any]:
        """
        分析单个测试失败原因
        
        Args:
            test_result: 测试结果
            test_case: 测试用例（可选）
        
        Returns:
            失败分析结果
        """
        if test_result.status != "failed":
            return {
                "status": "not_failed",
                "message": "该测试结果未失败"
            }
        
        # 解析数据
        request_data = json.loads(test_result.request_data) if test_result.request_data else {}
        response_data = json.loads(test_result.response_data) if test_result.response_data else {}
        assertions_result = json.loads(test_result.assertions_result) if test_result.assertions_result else []
        error_message = test_result.error_message or ""
        
        # 构建分析提示
        prompt = f"""
请分析以下API测试失败的原因，并提供详细的失败分析和改进建议。

测试用例信息：
- 用例名称：{test_case.name if test_case else '未知'}
- 用例描述：{test_case.description if test_case else '无'}

请求信息：
- 方法：{request_data.get('method', '')}
- URL：{request_data.get('url', '')}
- 请求头：{json.dumps(request_data.get('headers', {}), ensure_ascii=False)}
- 请求体：{json.dumps(request_data.get('body', {}), ensure_ascii=False)}

响应信息：
- 状态码：{response_data.get('status_code', '')}
- 响应体：{json.dumps(response_data.get('body', {}), ensure_ascii=False)}

断言结果：
{json.dumps(assertions_result, ensure_ascii=False)}

错误信息：
{error_message}

请提供：
1. 失败原因分析（详细说明为什么会失败）
2. 可能的原因分类（如：接口问题、数据问题、环境问题、断言问题等）
3. 修复建议（具体的修复步骤）
4. 预防措施（如何避免类似问题）

请以JSON格式返回，格式如下：
{{
    "failure_reason": "失败原因详细说明",
    "category": "失败类别（interface_error/data_error/environment_error/assertion_error等）",
    "root_cause": "根本原因",
    "fix_suggestions": ["建议1", "建议2", "建议3"],
    "prevention_measures": ["措施1", "措施2"]
}}
"""
        
        try:
            # 使用LLM分析
            analysis_text = self.llm_service.chat(
                prompt,
                temperature=0.3,
                max_tokens=1000
            )
            
            # 尝试提取JSON
            analysis_result = self._extract_json_from_response(analysis_text)
            
            # 如果LLM分析失败，使用规则分析
            if not analysis_result:
                analysis_result = self._rule_based_analysis(
                    request_data, response_data, assertions_result, error_message
                )
            
            return {
                "status": "success",
                "analysis": analysis_result,
                "analyzed_at": datetime.now().isoformat()
            }
        
        except Exception as e:
            # 回退到规则分析
            analysis_result = self._rule_based_analysis(
                request_data, response_data, assertions_result, error_message
            )
            return {
                "status": "partial",
                "analysis": analysis_result,
                "error": str(e),
                "analyzed_at": datetime.now().isoformat()
            }
    
    def _extract_json_from_response(self, text: str) -> Optional[Dict[str, Any]]:
        """从LLM响应中提取JSON"""
        import re
        
        # 尝试提取JSON块
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        
        return None
    
    def _rule_based_analysis(
        self,
        request_data: Dict[str, Any],
        response_data: Dict[str, Any],
        assertions_result: List[Dict[str, Any]],
        error_message: str
    ) -> Dict[str, Any]:
        """基于规则的分析"""
        status_code = response_data.get("status_code", 0)
        body = response_data.get("body", {})
        
        failure_reason = ""
        category = "unknown"
        root_cause = ""
        fix_suggestions = []
        prevention_measures = []
        
        # 分析状态码
        if status_code == 0:
            category = "network_error"
            failure_reason = "网络连接失败或超时"
            root_cause = "无法连接到服务器"
            fix_suggestions = [
                "检查网络连接",
                "验证服务器地址和端口",
                "检查防火墙设置"
            ]
            prevention_measures = [
                "添加重试机制",
                "设置合理的超时时间",
                "添加网络连接检测"
            ]
        
        elif status_code == 404:
            category = "interface_error"
            failure_reason = "接口不存在（404 Not Found）"
            root_cause = "URL路径错误或接口已删除"
            fix_suggestions = [
                "检查URL路径是否正确",
                "验证接口是否已更新",
                "确认接口是否已部署"
            ]
            prevention_measures = [
                "定期检查接口文档",
                "添加接口健康检查",
                "使用接口版本管理"
            ]
        
        elif status_code == 401:
            category = "authentication_error"
            failure_reason = "认证失败（401 Unauthorized）"
            root_cause = "Token无效或过期"
            fix_suggestions = [
                "检查Token是否正确",
                "验证Token是否过期",
                "重新获取Token"
            ]
            prevention_measures = [
                "自动刷新Token",
                "添加Token有效性检查",
                "实现Token自动获取"
            ]
        
        elif status_code == 403:
            category = "authorization_error"
            failure_reason = "权限不足（403 Forbidden）"
            root_cause = "用户没有访问权限"
            fix_suggestions = [
                "检查用户权限",
                "验证请求参数",
                "联系管理员添加权限"
            ]
            prevention_measures = [
                "提前验证权限",
                "添加权限检查",
                "使用正确的测试账号"
            ]
        
        elif status_code == 500:
            category = "server_error"
            failure_reason = "服务器内部错误（500 Internal Server Error）"
            root_cause = "服务器端问题"
            fix_suggestions = [
                "检查服务器日志",
                "验证服务器状态",
                "联系开发人员排查"
            ]
            prevention_measures = [
                "添加错误监控",
                "实现异常告警",
                "定期检查服务器健康"
            ]
        
        elif status_code >= 200 and status_code < 300:
            # 状态码正常，检查断言
            failed_assertions = [a for a in assertions_result if not a.get("passed", False)]
            if failed_assertions:
                category = "assertion_error"
                failure_reason = f"断言失败：{len(failed_assertions)}个断言未通过"
                root_cause = "响应数据不符合预期"
                fix_suggestions = [
                    "检查断言条件是否正确",
                    "验证响应数据结构",
                    "确认业务逻辑是否正确"
                ]
                prevention_measures = [
                    "完善断言规则",
                    "添加数据验证",
                    "定期更新测试数据"
                ]
        
        # 检查错误信息
        if error_message:
            if "timeout" in error_message.lower():
                category = "timeout_error"
                failure_reason = "请求超时"
                root_cause = "响应时间过长"
                fix_suggestions = [
                    "增加超时时间",
                    "优化接口性能",
                    "检查网络状况"
                ]
                prevention_measures = [
                    "设置合理的超时时间",
                    "添加性能监控",
                    "优化接口调用"
                ]
        
        return {
            "failure_reason": failure_reason or "未知错误",
            "category": category,
            "root_cause": root_cause or "需要进一步调查",
            "fix_suggestions": fix_suggestions or ["检查日志", "联系技术支持"],
            "prevention_measures": prevention_measures or ["添加监控", "完善测试"]
        }
    
    def analyze_task_failures(self, task_id: int) -> Dict[str, Any]:
        """分析任务中所有失败用例的模式"""
        task = self.db.query(TestTask).filter(TestTask.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}
        
        failed_results = self.db.query(TestResult).filter(
            TestResult.task_id == task_id,
            TestResult.status == "failed"
        ).all()
        
        if not failed_results:
            return {
                "total_failures": 0,
                "message": "没有失败的用例"
            }
        
        # 统计失败模式
        failure_categories = {}
        status_codes = {}
        error_patterns = {}
        
        for result in failed_results:
            response_data = json.loads(result.response_data) if result.response_data else {}
            status_code = response_data.get("status_code", 0)
            
            # 分析失败原因
            analysis = self.analyze_failure(result)
            if analysis.get("status") == "success":
                category = analysis["analysis"].get("category", "unknown")
                failure_categories[category] = failure_categories.get(category, 0) + 1
            
            status_codes[status_code] = status_codes.get(status_code, 0) + 1
            
            # 分析错误模式
            if result.error_message:
                error_key = self._extract_error_pattern(result.error_message)
                error_patterns[error_key] = error_patterns.get(error_key, 0) + 1
        
        return {
            "total_failures": len(failed_results),
            "failure_categories": failure_categories,
            "status_codes": status_codes,
            "error_patterns": error_patterns,
            "top_failure_category": max(failure_categories.items(), key=lambda x: x[1])[0] if failure_categories else None,
            "analysis_time": datetime.now().isoformat()
        }
    
    def _extract_error_pattern(self, error_message: str) -> str:
        """提取错误模式"""
        error_lower = error_message.lower()
        
        if "timeout" in error_lower:
            return "timeout"
        elif "connection" in error_lower:
            return "connection_error"
        elif "404" in error_message:
            return "not_found"
        elif "401" in error_message or "unauthorized" in error_lower:
            return "authentication_error"
        elif "403" in error_message or "forbidden" in error_lower:
            return "authorization_error"
        elif "500" in error_message:
            return "server_error"
        else:
            return "other_error"









































