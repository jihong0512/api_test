from typing import Dict, Any, List, Optional
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models import TestTask, TestResult


class TrendAnalyzer:
    """趋势分析器：展示测试通过率变化趋势"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def analyze_pass_rate_trend(
        self,
        project_id: int,
        days: int = 30,
        group_by: str = "day"  # day, week, month
    ) -> Dict[str, Any]:
        """
        分析测试通过率趋势
        
        Args:
            project_id: 项目ID
            days: 分析最近N天
            group_by: 分组方式（day/week/month）
        
        Returns:
            趋势数据
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # 查询任务
        tasks = self.db.query(TestTask).filter(
            TestTask.project_id == project_id,
            TestTask.created_at >= cutoff_date,
            TestTask.status == "completed"
        ).order_by(TestTask.created_at).all()
        
        # 按时间分组统计
        trend_data = []
        
        if group_by == "day":
            current_date = cutoff_date.date()
            end_date = datetime.now().date()
            
            while current_date <= end_date:
                day_tasks = [
                    t for t in tasks
                    if t.created_at.date() == current_date
                ]
                
                if day_tasks:
                    stats = self._calculate_day_stats(day_tasks)
                    trend_data.append({
                        "date": current_date.isoformat(),
                        "total_tasks": len(day_tasks),
                        "total_cases": stats["total_cases"],
                        "passed_cases": stats["passed_cases"],
                        "failed_cases": stats["failed_cases"],
                        "pass_rate": stats["pass_rate"],
                        "avg_execution_time": stats["avg_execution_time"]
                    })
                
                current_date += timedelta(days=1)
        
        elif group_by == "week":
            # 按周分组
            week_data = {}
            for task in tasks:
                week_start = (task.created_at - timedelta(days=task.created_at.weekday())).date()
                if week_start not in week_data:
                    week_data[week_start] = []
                week_data[week_start].append(task)
            
            for week_start, week_tasks in sorted(week_data.items()):
                stats = self._calculate_day_stats(week_tasks)
                trend_data.append({
                    "date": week_start.isoformat(),
                    "total_tasks": len(week_tasks),
                    "total_cases": stats["total_cases"],
                    "passed_cases": stats["passed_cases"],
                    "failed_cases": stats["failed_cases"],
                    "pass_rate": stats["pass_rate"],
                    "avg_execution_time": stats["avg_execution_time"]
                })
        
        # 计算总体趋势
        overall_stats = self._calculate_overall_stats(tasks)
        
        # 计算趋势方向
        trend_direction = self._calculate_trend_direction(trend_data)
        
        return {
            "project_id": project_id,
            "analysis_period_days": days,
            "group_by": group_by,
            "trend_data": trend_data,
            "overall_stats": overall_stats,
            "trend_direction": trend_direction,
            "analysis_time": datetime.now().isoformat()
        }
    
    def _calculate_day_stats(self, tasks: List[TestTask]) -> Dict[str, Any]:
        """计算某天的统计信息"""
        total_cases = sum(t.total_cases or 0 for t in tasks)
        passed_cases = sum(t.passed_cases or 0 for t in tasks)
        failed_cases = sum(t.failed_cases or 0 for t in tasks)
        
        pass_rate = (passed_cases / total_cases * 100) if total_cases > 0 else 0
        
        # 计算平均执行时间（简化处理）
        avg_execution_time = 0
        if tasks:
            # 可以从result_summary中提取
            times = []
            for task in tasks:
                if task.result_summary:
                    try:
                        summary = json.loads(task.result_summary)
                        # 假设summary中有执行时间信息
                    except:
                        pass
            
            avg_execution_time = sum(times) / len(times) if times else 0
        
        return {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "pass_rate": pass_rate,
            "avg_execution_time": avg_execution_time
        }
    
    def _calculate_overall_stats(self, tasks: List[TestTask]) -> Dict[str, Any]:
        """计算总体统计"""
        total_tasks = len(tasks)
        total_cases = sum(t.total_cases or 0 for t in tasks)
        total_passed = sum(t.passed_cases or 0 for t in tasks)
        total_failed = sum(t.failed_cases or 0 for t in tasks)
        total_skipped = sum(t.skipped_cases or 0 for t in tasks)
        
        pass_rate = (total_passed / total_cases * 100) if total_cases > 0 else 0
        
        return {
            "total_tasks": total_tasks,
            "total_cases": total_cases,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "total_skipped": total_skipped,
            "overall_pass_rate": pass_rate
        }
    
    def _calculate_trend_direction(self, trend_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算趋势方向"""
        if len(trend_data) < 2:
            return {
                "direction": "insufficient_data",
                "message": "数据不足，无法分析趋势"
            }
        
        # 计算前半段和后半段的平均通过率
        mid_point = len(trend_data) // 2
        first_half = trend_data[:mid_point]
        second_half = trend_data[mid_point:]
        
        first_avg = sum(d["pass_rate"] for d in first_half) / len(first_half) if first_half else 0
        second_avg = sum(d["pass_rate"] for d in second_half) / len(second_half) if second_half else 0
        
        change = second_avg - first_avg
        change_percentage = (change / first_avg * 100) if first_avg > 0 else 0
        
        if change > 5:
            direction = "improving"
            message = f"通过率上升{change_percentage:.2f}%，趋势向好"
        elif change < -5:
            direction = "declining"
            message = f"通过率下降{abs(change_percentage):.2f}%，需要关注"
        else:
            direction = "stable"
            message = "通过率保持稳定"
        
        return {
            "direction": direction,
            "change": change,
            "change_percentage": change_percentage,
            "message": message,
            "first_half_avg": first_avg,
            "second_half_avg": second_avg
        }









































