from typing import Dict, Any, List, Optional
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from app.models import TestTask, TestResult, TestCase


class AllureReportGenerator:
    """Allure报告生成器"""
    
    def __init__(self, report_base_dir: str = "/tmp/allure-results"):
        self.report_base_dir = report_base_dir
        os.makedirs(report_base_dir, exist_ok=True)
    
    def generate_allure_results(
        self,
        task: TestTask,
        test_results: List[TestResult],
        test_cases: List[TestCase]
    ) -> Dict[str, Any]:
        """
        生成Allure测试结果文件
        
        Args:
            task: 测试任务
            test_results: 测试结果列表
            test_cases: 测试用例列表
        
        Returns:
            生成的结果文件路径
        """
        task_results_dir = os.path.join(self.report_base_dir, f"task_{task.id}")
        os.makedirs(task_results_dir, exist_ok=True)
        
        # 生成测试用例结果文件
        for result in test_results:
            test_case = next((tc for tc in test_cases if tc.id == result.test_case_id), None)
            if not test_case:
                continue
            
            # 生成Allure结果JSON
            allure_result = self._create_allure_result(result, test_case, task)
            
            # 保存为JSON文件（Allure格式）
            result_file = os.path.join(
                task_results_dir,
                f"test-result-{result.id}.json"
            )
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(allure_result, f, ensure_ascii=False, indent=2)
        
        # 生成executor信息
        executor_info = {
            "buildName": f"Task-{task.id}",
            "name": task.name,
            "type": "local",
            "buildOrder": task.id,
            "reportName": task.name
        }
        
        executor_file = os.path.join(task_results_dir, "executor.json")
        with open(executor_file, 'w', encoding='utf-8') as f:
            json.dump(executor_info, f, ensure_ascii=False)
        
        return {
            "results_dir": task_results_dir,
            "total_results": len(test_results)
        }
    
    def _create_allure_result(
        self,
        result: TestResult,
        test_case: TestCase,
        task: TestTask
    ) -> Dict[str, Any]:
        """创建Allure格式的测试结果"""
        # 解析数据
        request_data = json.loads(result.request_data) if result.request_data else {}
        response_data = json.loads(result.response_data) if result.response_data else {}
        assertions_result = json.loads(result.assertions_result) if result.assertions_result else []
        
        # 构建Allure结果
        allure_result = {
            "uuid": f"test-{result.id}",
            "historyId": f"test-{test_case.id}",
            "fullName": f"{test_case.name}",
            "labels": [
                {"name": "suite", "value": task.name},
                {"name": "testClass", "value": test_case.module or "default"},
                {"name": "testMethod", "value": test_case.name},
                {"name": "package", "value": f"project.{task.project_id}"}
            ],
            "name": test_case.name,
            "status": self._map_status(result.status),
            "statusDetails": {
                "message": result.error_message or "",
                "trace": result.error_message or ""
            } if result.status == "failed" else None,
            "stage": "finished",
            "description": test_case.description or "",
            "steps": self._create_allure_steps(result, request_data, response_data, assertions_result),
            "attachments": [],
            "parameters": [],
            "start": int(result.created_at.timestamp() * 1000) if result.created_at else None,
            "stop": int((result.created_at.timestamp() + result.execution_time) * 1000) if result.created_at and result.execution_time else None
        }
        
        # 添加性能指标作为附件
        if result.performance_metrics:
            try:
                perf_metrics = json.loads(result.performance_metrics)
                allure_result["attachments"].append({
                    "name": "Performance Metrics",
                    "source": "performance.json",
                    "type": "application/json"
                })
            except:
                pass
        
        return allure_result
    
    def _create_allure_steps(
        self,
        result: TestResult,
        request_data: Dict[str, Any],
        response_data: Dict[str, Any],
        assertions_result: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """创建Allure步骤"""
        steps = []
        
        # 请求步骤
        request_step = {
            "name": f"{request_data.get('method', 'REQUEST')} {request_data.get('url', '')}",
            "status": self._map_status(result.status),
            "stage": "finished",
            "steps": [],
            "attachments": [
                {
                    "name": "Request",
                    "source": "request.json",
                    "type": "application/json"
                }
            ],
            "start": int(result.created_at.timestamp() * 1000) if result.created_at else None,
            "stop": int((result.created_at.timestamp() + result.execution_time) * 1000) if result.created_at and result.execution_time else None
        }
        steps.append(request_step)
        
        # 断言步骤
        if assertions_result:
            for assertion in assertions_result:
                assertion_step = {
                    "name": f"Assertion: {assertion.get('type', '')} - {assertion.get('field', '')}",
                    "status": "passed" if assertion.get("passed") else "failed",
                    "stage": "finished",
                    "statusDetails": {
                        "message": f"Expected: {assertion.get('expected')}, Actual: {assertion.get('actual')}"
                    } if not assertion.get("passed") else None
                }
                steps.append(assertion_step)
        
        return steps
    
    def _map_status(self, status: str) -> str:
        """映射状态到Allure状态"""
        status_map = {
            "passed": "passed",
            "failed": "failed",
            "skipped": "skipped",
            "error": "broken"
        }
        return status_map.get(status, "unknown")
    
    def generate_allure_report(self, results_dir: str, report_dir: str) -> Dict[str, Any]:
        """
        生成Allure HTML报告
        
        Args:
            results_dir: Allure结果目录
            report_dir: 报告输出目录
        
        Returns:
            报告信息
        """
        os.makedirs(report_dir, exist_ok=True)
        
        try:
            # 执行allure generate命令
            cmd = [
                "allure", "generate",
                results_dir,
                "-o", report_dir,
                "--clean"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return {
                    "status": "success",
                    "report_dir": report_dir,
                    "index_path": os.path.join(report_dir, "index.html")
                }
            else:
                return {
                    "status": "error",
                    "error": result.stderr
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "error": "生成报告超时"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def serve_allure_report(self, report_dir: str, port: int = 5050) -> Dict[str, Any]:
        """
        启动Allure报告服务器（可选）
        
        Args:
            report_dir: 报告目录
            port: 端口号
        
        Returns:
            服务信息
        """
        try:
            # 在后台启动allure serve
            cmd = [
                "allure", "serve",
                report_dir,
                "-p", str(port)
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            return {
                "status": "started",
                "port": port,
                "url": f"http://localhost:{port}",
                "pid": process.pid
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }









































