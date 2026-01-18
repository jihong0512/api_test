from typing import Dict, Any, List, Optional
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models import TestResult, TestTask, TestCase
from app.services.llm_service import LLMService


class AISuggestionService:
    """AI优化建议服务：基于历史数据和模式识别提供优化建议"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.llm_service = LLMService()
    
    def generate_suggestions(
        self,
        task_id: int,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        基于历史数据生成优化建议
        
        Args:
            task_id: 任务ID
            days: 分析最近N天的历史数据
        
        Returns:
            优化建议
        """
        task = self.db.query(TestTask).filter(TestTask.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}
        
        # 获取历史任务数据
        cutoff_date = datetime.now() - timedelta(days=days)
        
        historical_tasks = self.db.query(TestTask).filter(
            TestTask.project_id == task.project_id,
            TestTask.created_at >= cutoff_date
        ).all()
        
        # 统计历史数据
        stats = self._calculate_statistics(historical_tasks)
        
        # 获取当前任务的详细结果
        current_results = self.db.query(TestResult).filter(
            TestResult.task_id == task_id
        ).all()
        
        # 生成建议
        suggestions = []
        
        # 1. 通过率建议
        if stats["total_tasks"] > 0:
            pass_rate = stats["avg_pass_rate"]
            if pass_rate < 80:
                suggestions.append({
                    "type": "pass_rate",
                    "priority": "high",
                    "title": "测试通过率偏低",
                    "description": f"最近{days}天的平均通过率为{pass_rate:.2f}%，建议重点关注",
                    "recommendations": [
                        "检查失败用例的失败模式",
                        "优化测试数据构造逻辑",
                        "加强环境稳定性检查",
                        "完善异常处理机制"
                    ]
                })
        
        # 2. 性能建议
        if stats["avg_execution_time"] > 30:
            suggestions.append({
                "type": "performance",
                "priority": "medium",
                "title": "执行时间较长",
                "description": f"平均执行时间为{stats['avg_execution_time']:.2f}秒，建议优化",
                "recommendations": [
                    "检查是否有慢查询接口",
                    "优化测试数据准备时间",
                    "考虑并行执行独立用例",
                    "减少不必要的等待时间"
                ]
            })
        
        # 3. 失败模式建议
        if stats["common_failures"]:
            top_failure = max(stats["common_failures"].items(), key=lambda x: x[1])
            suggestions.append({
                "type": "failure_pattern",
                "priority": "high",
                "title": f"常见失败模式：{top_failure[0]}",
                "description": f"此失败模式出现{top_failure[1]}次，占失败总数的{top_failure[1]/stats['total_failures']*100:.2f}%",
                "recommendations": self._get_failure_recommendations(top_failure[0])
            })
        
        # 4. 数据质量建议
        if current_results:
            data_quality_issues = self._analyze_data_quality(current_results)
            if data_quality_issues:
                suggestions.append({
                    "type": "data_quality",
                    "priority": "medium",
                    "title": "数据质量问题",
                    "description": "检测到测试数据质量问题",
                    "recommendations": data_quality_issues
                })
        
        # 5. 使用LLM生成综合建议
        llm_suggestions = self._generate_llm_suggestions(task, current_results, stats)
        if llm_suggestions:
            suggestions.append({
                "type": "ai_analysis",
                "priority": "medium",
                "title": "AI综合分析建议",
                "description": "基于测试历史和当前结果的综合分析",
                "recommendations": llm_suggestions
            })
        
        return {
            "task_id": task_id,
            "analysis_period_days": days,
            "statistics": stats,
            "suggestions": suggestions,
            "generated_at": datetime.now().isoformat()
        }
    
    def _calculate_statistics(self, tasks: List[TestTask]) -> Dict[str, Any]:
        """计算统计数据"""
        total_tasks = len(tasks)
        total_cases = 0
        total_passed = 0
        total_failed = 0
        total_time = 0.0
        failure_patterns = {}
        total_failures = 0
        
        for task in tasks:
            if task.total_cases:
                total_cases += task.total_cases
                total_passed += task.passed_cases or 0
                total_failed += task.failed_cases or 0
                total_failures += task.failed_cases or 0
            
            if task.result_summary:
                try:
                    summary = json.loads(task.result_summary)
                    # 可以提取更多统计信息
                except:
                    pass
            
            # 统计失败模式（从测试结果中统计）
            failed_results = self.db.query(TestResult).filter(
                TestResult.task_id == task.id,
                TestResult.status == "failed"
            ).all()
            
            for result in failed_results:
                if result.error_message:
                    pattern = self._extract_failure_pattern(result.error_message)
                    failure_patterns[pattern] = failure_patterns.get(pattern, 0) + 1
        
        avg_pass_rate = (total_passed / total_cases * 100) if total_cases > 0 else 0
        
        return {
            "total_tasks": total_tasks,
            "total_cases": total_cases,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "total_failures": total_failures,
            "avg_pass_rate": avg_pass_rate,
            "avg_execution_time": total_time / total_tasks if total_tasks > 0 else 0,
            "common_failures": failure_patterns
        }
    
    def _analyze_data_quality(self, results: List[TestResult]) -> List[str]:
        """分析数据质量问题"""
        issues = []
        
        # 检查是否有大量空响应
        empty_responses = sum(
            1 for r in results 
            if r.response_data and (r.response_data == "{}" or r.response_data == "null")
        )
        
        if empty_responses > len(results) * 0.3:
            issues.append("超过30%的响应为空，建议检查数据生成逻辑")
        
        # 检查状态码分布
        status_codes = {}
        for result in results:
            if result.status_code:
                status_codes[result.status_code] = status_codes.get(result.status_code, 0) + 1
        
        if status_codes.get(500, 0) > len(results) * 0.2:
            issues.append("服务器错误比例较高，建议检查环境稳定性")
        
        return issues
    
    def _get_failure_recommendations(self, failure_pattern: str) -> List[str]:
        """根据失败模式获取建议"""
        recommendations_map = {
            "timeout": [
                "增加接口超时时间",
                "优化接口性能",
                "检查网络连接质量"
            ],
            "authentication_error": [
                "实现Token自动刷新",
                "添加Token有效性检查",
                "优化认证流程"
            ],
            "server_error": [
                "添加服务器健康检查",
                "实现自动重试机制",
                "优化错误处理"
            ],
            "assertion_error": [
                "完善断言规则",
                "更新测试数据",
                "验证业务逻辑"
            ]
        }
        
        return recommendations_map.get(failure_pattern, [
            "分析具体失败原因",
            "检查测试环境",
            "验证测试数据"
        ])
    
    def _extract_failure_pattern(self, error_message: str) -> str:
        """提取失败模式"""
        error_lower = error_message.lower()
        
        if "timeout" in error_lower:
            return "timeout"
        elif "401" in error_message or "unauthorized" in error_lower:
            return "authentication_error"
        elif "403" in error_message or "forbidden" in error_lower:
            return "authorization_error"
        elif "500" in error_message:
            return "server_error"
        elif "assertion" in error_lower:
            return "assertion_error"
        else:
            return "other_error"
    
    def _generate_llm_suggestions(
        self,
        task: TestTask,
        results: List[TestResult],
        stats: Dict[str, Any]
    ) -> List[str]:
        """使用LLM生成优化建议"""
        try:
            prompt = f"""
基于以下测试任务和历史数据，提供优化建议：

当前任务：
- 任务名称：{task.name}
- 总用例数：{task.total_cases}
- 通过数：{task.passed_cases}
- 失败数：{task.failed_cases}
- 通过率：{(task.passed_cases/task.total_cases*100) if task.total_cases > 0 else 0:.2f}%

历史统计（最近30天）：
- 平均通过率：{stats.get('avg_pass_rate', 0):.2f}%
- 总任务数：{stats.get('total_tasks', 0)}
- 常见失败模式：{stats.get('common_failures', {})}

请提供3-5条具体的优化建议，每条建议应该：
1. 针对性强
2. 可执行
3. 有明确的改进方向

请以JSON数组格式返回，例如：
["建议1", "建议2", "建议3"]
"""
            
            response = self.llm_service.chat(prompt, temperature=0.5, max_tokens=500)
            
            # 提取JSON数组
            import re
            json_match = re.search(r'\[.*?\]', response, re.DOTALL)
            if json_match:
                suggestions = json.loads(json_match.group())
                return suggestions if isinstance(suggestions, list) else []
        
        except Exception as e:
            print(f"LLM生成建议失败: {e}")
        
        return []

