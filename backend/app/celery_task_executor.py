from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import TestTask, TestCase, TestResult, TestEnvironment, Project
from app.services.test_executor import TestExecutor
import json
from typing import Dict, Any, List
from datetime import datetime


class TaskController:
    """任务控制器：管理任务的暂停、继续、停止"""
    
    _task_states = {}  # {task_id: "running" | "paused" | "stopped"}
    
    @classmethod
    def pause_task(cls, task_id: int):
        """暂停任务"""
        cls._task_states[task_id] = "paused"
    
    @classmethod
    def resume_task(cls, task_id: int):
        """继续任务"""
        cls._task_states[task_id] = "running"
    
    @classmethod
    def stop_task(cls, task_id: int):
        """停止任务"""
        cls._task_states[task_id] = "stopped"
    
    @classmethod
    def get_task_state(cls, task_id: int) -> str:
        """获取任务状态"""
        return cls._task_states.get(task_id, "running")
    
    @classmethod
    def clear_task_state(cls, task_id: int):
        """清除任务状态"""
        if task_id in cls._task_states:
            del cls._task_states[task_id]


@celery_app.task(bind=True)
def execute_test_task(
    self,
    task_id: int
):
    """
    异步执行测试任务
    
    Args:
        task_id: 测试任务ID
    """
    db = SessionLocal()
    task_controller = TaskController()
    
    try:
        # 获取测试任务
        test_task = db.query(TestTask).filter(TestTask.id == task_id).first()
        if not test_task:
            return {"status": "error", "message": "测试任务不存在"}
        
        # 检查任务状态
        control_state = task_controller.get_task_state(task_id)
        if control_state == "stopped":
            test_task.status = "stopped"
            db.commit()
            return {"status": "stopped", "message": "任务已停止"}
        
        # 更新任务状态
        test_task.status = "running"
        test_task.execution_task_id = self.request.id
        test_task.executed_at = datetime.now()
        db.commit()
        
        # 获取测试环境
        environment = None
        if test_task.environment_id:
            environment = db.query(TestEnvironment).filter(
                TestEnvironment.id == test_task.environment_id
            ).first()
        
        if not environment:
            test_task.status = "failed"
            test_task.error_message = "测试环境不存在"
            db.commit()
            return {"status": "error", "message": "测试环境不存在"}
        
        # 解析测试用例ID列表
        test_case_ids = json.loads(test_task.test_case_ids) if test_task.test_case_ids else []
        
        if not test_case_ids:
            test_task.status = "failed"
            test_task.error_message = "没有测试用例"
            db.commit()
            return {"status": "error", "message": "没有测试用例"}
        
        test_task.total_cases = len(test_case_ids)
        db.commit()
        
        # 创建执行器
        executor = TestExecutor(db)
        
        # 存储提取的数据（用于用例间的数据传递）
        extracted_data = {}
        
        # 执行每个测试用例
        passed_count = 0
        failed_count = 0
        skipped_count = 0
        
        for index, case_id in enumerate(test_case_ids):
            # 检查控制状态（暂停、停止）
            control_state = task_controller.get_task_state(task_id)
            
            if control_state == "stopped":
                test_task.status = "stopped"
                db.commit()
                break
            
            if control_state == "paused":
                test_task.status = "paused"
                test_task.paused_at = datetime.now()
                db.commit()
                # 等待继续
                while task_controller.get_task_state(task_id) == "paused":
                    import time
                    time.sleep(1)
                    if task_controller.get_task_state(task_id) == "stopped":
                        test_task.status = "stopped"
                        db.commit()
                        break
                
                if test_task.status == "stopped":
                    break
                
                test_task.status = "running"
                test_task.paused_at = None
                db.commit()
            
            # 获取测试用例
            test_case = db.query(TestCase).filter(TestCase.id == case_id).first()
            if not test_case:
                skipped_count += 1
                continue
            
            # 获取任务配置的测试数据
            task_test_data = None
            if test_task.test_data_config:
                try:
                    test_data_config = json.loads(test_task.test_data_config)
                    task_test_data = test_data_config.get(str(case_id))
                except:
                    pass
            
            # 执行测试用例（同步方法）
            result = executor.execute_test_case(
                test_case=test_case,
                environment=environment,
                extracted_data=extracted_data,
                prepared_test_data=task_test_data
            )
            
            # 计算性能指标
            performance_metrics = {}
            if result.get("execution_time"):
                performance_metrics["execution_time"] = result["execution_time"]
            
            # 保存重试信息到性能指标
            if result.get("retry_info"):
                performance_metrics["retry_info"] = result["retry_info"]
            
            request_size = 0
            if result.get("request_data"):
                request_json = json.dumps(result["request_data"], ensure_ascii=False)
                request_size = len(request_json.encode('utf-8'))
                performance_metrics["request_size"] = request_size
            
            response_size = 0
            status_code = None
            if result.get("response_data"):
                response_json = json.dumps(result["response_data"], ensure_ascii=False)
                response_size = len(response_json.encode('utf-8'))
                performance_metrics["response_size"] = response_size
                
                response_data_obj = result["response_data"]
                if isinstance(response_data_obj, dict):
                    status_code = response_data_obj.get("status_code")
            
            # 保存测试结果（包含性能指标和重试信息）
            # 如果结果中有retry_info，添加到performance_metrics中
            if result.get("retry_info"):
                performance_metrics["retry_info"] = result["retry_info"]
            
            test_result = TestResult(
                task_id=task_id,
                test_case_id=case_id,
                status=result["status"],
                request_data=json.dumps(result.get("request_data"), ensure_ascii=False),
                response_data=json.dumps(result.get("response_data"), ensure_ascii=False),
                assertions_result=json.dumps(result.get("assertions", []), ensure_ascii=False),
                error_message=result.get("error_message"),
                execution_time=result.get("execution_time"),
                request_size=request_size,
                response_size=response_size,
                status_code=status_code,
                performance_metrics=json.dumps(performance_metrics, ensure_ascii=False)
            )
            db.add(test_result)
            
            # 更新统计
            if result["status"] == "passed":
                passed_count += 1
            elif result["status"] == "failed":
                failed_count += 1
            else:
                skipped_count += 1
            
            # 提取数据（用于后续用例）
            if result.get("response_data") and result["status"] == "passed":
                response_data = result["response_data"]
                if isinstance(response_data, dict):
                    body = response_data.get("body", {})
                    
                    # 提取token
                    if isinstance(body, dict):
                        token = body.get("token") or body.get("access_token") or \
                               (body.get("data", {}).get("token") if isinstance(body.get("data"), dict) else None)
                        if token:
                            extracted_data["authToken"] = token
                        
                        # 提取ID
                        for id_field in ["id", "post_id", "device_id", "course_id", "family_id"]:
                            if id_field in body:
                                extracted_data[id_field] = body[id_field]
                            elif isinstance(body.get("data"), dict) and id_field in body["data"]:
                                extracted_data[id_field] = body["data"][id_field]
            
            # 更新进度
            progress = int((index + 1) / len(test_case_ids) * 100)
            test_task.progress = progress
            test_task.passed_cases = passed_count
            test_task.failed_cases = failed_count
            test_task.skipped_cases = skipped_count
            db.commit()
            
            # 更新Celery任务进度
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': index + 1,
                    'total': len(test_case_ids),
                    'progress': progress,
                    'passed': passed_count,
                    'failed': failed_count,
                    'skipped': skipped_count
                }
            )
        
        # 任务完成
        test_task.status = "completed"
        test_task.completed_at = datetime.now()
        test_task.progress = 100
        
        # 生成结果摘要
        summary = {
            "total": test_task.total_cases,
            "passed": passed_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "pass_rate": f"{(passed_count / test_task.total_cases * 100):.2f}%" if test_task.total_cases > 0 else "0%"
        }
        test_task.result_summary = json.dumps(summary, ensure_ascii=False)
        
        db.commit()
        
        # 清除任务状态
        task_controller.clear_task_state(task_id)
        
        return {
            "status": "completed",
            "total": test_task.total_cases,
            "passed": passed_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "summary": summary
        }
    
    except Exception as e:
        db.rollback()
        
        # 更新错误状态
        if test_task:
            test_task.status = "failed"
            test_task.error_message = str(e)
            test_task.progress = 0
            db.commit()
        
        # 清除任务状态
        task_controller.clear_task_state(task_id)
        
        return {"status": "error", "message": str(e)}
    
    finally:
        db.close()


# 导出任务控制器供API使用
task_controller = TaskController()

