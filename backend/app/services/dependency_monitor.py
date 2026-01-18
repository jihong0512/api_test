import asyncio
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging

from app.models import TestEnvironment, TestResult, Project

logger = logging.getLogger(__name__)


class DependencyMonitor:
    """依赖服务监控器"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    async def check_service_health(
        self,
        base_url: str,
        timeout: float = 5.0,
        health_endpoint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        检查服务健康状态
        
        Args:
            base_url: 服务基础URL
            timeout: 超时时间（秒）
            health_endpoint: 健康检查端点（可选）
        
        Returns:
            健康状态信息
        """
        check_url = base_url.rstrip("/")
        if health_endpoint:
            check_url = f"{check_url}/{health_endpoint.lstrip('/')}"
        else:
            check_url = f"{check_url}/health"  # 默认健康检查端点
        
        start_time = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(check_url)
                elapsed = (datetime.now() - start_time).total_seconds()
                
                is_healthy = 200 <= response.status_code < 400
                
                return {
                    "status": "healthy" if is_healthy else "unhealthy",
                    "status_code": response.status_code,
                    "response_time": elapsed,
                    "checked_at": datetime.now().isoformat(),
                    "url": check_url,
                    "error": None
                }
        
        except httpx.TimeoutException:
            elapsed = (datetime.now() - start_time).total_seconds()
            return {
                "status": "timeout",
                "status_code": None,
                "response_time": elapsed,
                "checked_at": datetime.now().isoformat(),
                "url": check_url,
                "error": "连接超时"
            }
        
        except httpx.ConnectError:
            elapsed = (datetime.now() - start_time).total_seconds()
            return {
                "status": "unreachable",
                "status_code": None,
                "response_time": elapsed,
                "checked_at": datetime.now().isoformat(),
                "url": check_url,
                "error": "无法连接到服务"
            }
        
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            return {
                "status": "error",
                "status_code": None,
                "response_time": elapsed,
                "checked_at": datetime.now().isoformat(),
                "url": check_url,
                "error": str(e)
            }
    
    async def monitor_environment(
        self,
        environment: TestEnvironment,
        health_endpoint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        监控测试环境
        
        Args:
            environment: 测试环境
            health_endpoint: 健康检查端点
        
        Returns:
            监控结果
        """
        health_status = await self.check_service_health(
            environment.base_url,
            health_endpoint=health_endpoint
        )
        
        # 获取最近的成功率和错误率
        stats = self._get_recent_statistics(environment.id)
        
        return {
            "environment_id": environment.id,
            "environment_name": environment.name,
            "base_url": environment.base_url,
            "health_status": health_status,
            "recent_stats": stats,
            "monitored_at": datetime.now().isoformat()
        }
    
    def _get_recent_statistics(
        self,
        environment_id: int,
        hours: int = 24
    ) -> Dict[str, Any]:
        """获取最近统计信息"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # 查询最近的结果（通过TestTask关联）
        from app.models import TestTask
        results = self.db.query(TestResult).join(
            TestTask,
            TestResult.task_id == TestTask.id
        ).filter(
            TestTask.environment_id == environment_id,
            TestResult.created_at >= cutoff_time
        ).all()
        
        if not results:
            return {
                "total": 0,
                "success_rate": 0,
                "error_rate": 0,
                "avg_response_time": 0
            }
        
        total = len(results)
        passed = len([r for r in results if r.status == "passed"])
        failed = len([r for r in results if r.status == "failed"])
        
        # 计算平均响应时间
        response_times = [
            float(r.execution_time) for r in results
            if r.execution_time
        ]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # 统计状态码分布
        status_codes = {}
        for result in results:
            if result.status_code:
                status_codes[result.status_code] = status_codes.get(result.status_code, 0) + 1
        
        # 统计错误类型
        error_types = {}
        for result in results:
            if result.status == "failed" and result.error_message:
                error_type = self._classify_error(result.error_message)
                error_types[error_type] = error_types.get(error_type, 0) + 1
        
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "success_rate": (passed / total * 100) if total > 0 else 0,
            "error_rate": (failed / total * 100) if total > 0 else 0,
            "avg_response_time": avg_response_time,
            "status_code_distribution": status_codes,
            "error_type_distribution": error_types
        }
    
    def _classify_error(self, error_message: str) -> str:
        """分类错误类型"""
        error_lower = error_message.lower()
        
        if "429" in error_message or "rate limit" in error_lower:
            return "rate_limit"
        elif "timeout" in error_lower:
            return "timeout"
        elif "connection" in error_lower or "connect" in error_lower:
            return "connection_error"
        elif "500" in error_message or "server error" in error_lower:
            return "server_error"
        elif "404" in error_message:
            return "not_found"
        elif "401" in error_message or "unauthorized" in error_lower:
            return "authentication_error"
        elif "403" in error_message or "forbidden" in error_lower:
            return "authorization_error"
        else:
            return "unknown_error"
    
    async def monitor_multiple_environments(
        self,
        project_id: int,
        health_endpoint: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        监控项目的所有环境
        
        Args:
            project_id: 项目ID
            health_endpoint: 健康检查端点
        
        Returns:
            所有环境的监控结果
        """
        environments = self.db.query(TestEnvironment).filter(
            TestEnvironment.project_id == project_id
        ).all()
        
        results = []
        for env in environments:
            try:
                monitor_result = await self.monitor_environment(env, health_endpoint)
                results.append(monitor_result)
            except Exception as e:
                logger.error(f"监控环境{env.id}失败: {e}")
                results.append({
                    "environment_id": env.id,
                    "environment_name": env.name,
                    "base_url": env.base_url,
                    "health_status": {
                        "status": "error",
                        "error": str(e)
                    },
                    "monitored_at": datetime.now().isoformat()
                })
        
        return results
    
    def get_service_availability(
        self,
        environment_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        获取服务可用性统计
        
        Args:
            environment_id: 环境ID
            days: 统计天数
        
        Returns:
            可用性统计
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        
        # 查询最近的测试结果
        from app.models import TestTask
        results = self.db.query(TestResult).join(
            TestTask,
            TestResult.task_id == TestTask.id
        ).filter(
            TestTask.environment_id == environment_id,
            TestResult.created_at >= cutoff_time
        ).all()
        
        if not results:
            return {
                "availability_rate": 0,
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "avg_response_time": 0
            }
        
        total = len(results)
        successful = len([r for r in results if r.status == "passed"])
        failed = len([r for r in results if r.status == "failed"])
        
        response_times = [
            float(r.execution_time) for r in results
            if r.execution_time
        ]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            "availability_rate": (successful / total * 100) if total > 0 else 0,
            "total_requests": total,
            "successful_requests": successful,
            "failed_requests": failed,
            "avg_response_time": avg_response_time,
            "period_days": days
        }

