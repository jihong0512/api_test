from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import json
import os
import subprocess

from app.database import get_db
from app.models import TestTask, Project, User, TestEnvironment, TestCaseSuite, TestCase
from app.routers.auth import get_current_user_optional
from app.services.task_scheduler import TaskScheduler
from app.services.task_preparation import TaskPreparationService
from app.celery_task_executor import execute_test_task, task_controller
from app.celery_app import celery_app
from app.celery_tasks_execution import execute_test_task_task
from app.utils.redis_helper import get_redis_client

router = APIRouter()
task_scheduler = TaskScheduler()


class TestTaskCreate(BaseModel):
    name: str
    scenario: Optional[str] = None  # 执行场景描述
    task_type: str = "immediate"  # immediate, scheduled
    execution_task_type: str = "interface"  # scenario(接口场景用例执行), interface(接口测试用例执行), performance(性能测试执行), other(其他)
    cron_expression: Optional[str] = None
    test_case_ids: Optional[List[int]] = None  # 直接选择用例
    test_case_suite_id: Optional[int] = None  # 单个用例集合（向后兼容）
    test_case_suite_ids: Optional[List[int]] = None  # 多个用例集合
    environment_id: int
    threads: Optional[int] = 10  # 性能测试线程数（5,10,20,50,100）
    duration: Optional[int] = 5  # 性能测试执行时长（分钟，5,10,15,20,30）
    max_retries: int = 3
    auto_prepare: bool = True  # 是否自动准备（分析依赖、构造数据）


class TestTaskUpdate(BaseModel):
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    test_case_ids: Optional[List[int]] = None
    environment_id: Optional[int] = None
    max_retries: Optional[int] = None


@router.post("/")
async def create_test_task(
    project_id: int,
    task: TestTaskCreate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """创建测试任务（自动分析依赖、构造测试数据）"""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 验证环境存在
    environment = db.query(TestEnvironment).filter(
        TestEnvironment.id == task.environment_id,
        TestEnvironment.project_id == project_id
    ).first()
    if not environment:
        raise HTTPException(status_code=404, detail="测试环境不存在")
    
    # 获取用例ID列表
    test_case_ids = []
    test_case_suite_id = None
    
    # 支持多个用例集
    suite_ids = []
    if task.test_case_suite_ids:
        suite_ids = task.test_case_suite_ids
    elif task.test_case_suite_id:
        # 向后兼容：单个用例集
        suite_ids = [task.test_case_suite_id]
    
    if suite_ids:
        # 从多个用例集合获取用例
        all_case_ids = set()  # 使用set去重
        
        for suite_id in suite_ids:
            suite = db.query(TestCaseSuite).filter(
                TestCaseSuite.id == suite_id,
                TestCaseSuite.project_id == project_id
            ).first()
            if not suite:
                raise HTTPException(status_code=404, detail=f"用例集合不存在: {suite_id}")
            
            if suite.test_case_ids:
                case_ids = json.loads(suite.test_case_ids)
                all_case_ids.update(case_ids)
        
        test_case_ids = list(all_case_ids)
        test_case_suite_id = suite_ids[0]  # 保存第一个用例集ID（向后兼容）
    
    elif task.test_case_ids:
        # 直接使用提供的用例ID
        test_case_ids = task.test_case_ids
    
    else:
        raise HTTPException(status_code=400, detail="必须提供test_case_ids、test_case_suite_id或test_case_suite_ids")
    
    # 推断执行类型：如果选择了用例集但未显式指定类型，强制视为场景执行
    if suite_ids and (task.execution_task_type is None or task.execution_task_type == "interface"):
        task.execution_task_type = "scenario"
    elif not suite_ids and not task.execution_task_type:
        task.execution_task_type = "interface"
    
    if not test_case_ids:
        raise HTTPException(status_code=400, detail="用例列表为空")
    
    # 验证任务类型和用例类型的匹配
    if task.execution_task_type == "performance":
        # 性能测试只能选择jmeter类型的用例
        valid_cases = db.query(TestCase).filter(
            TestCase.id.in_(test_case_ids),
            TestCase.project_id == project_id,
            TestCase.case_type == "jmeter"
        ).all()
        if len(valid_cases) != len(test_case_ids):
            raise HTTPException(status_code=400, detail="性能测试执行任务只能选择性能测试用例（jmeter类型）")
        # 验证线程数
        if task.threads not in [5, 10, 20, 50, 100]:
            raise HTTPException(status_code=400, detail="性能测试线程数必须是5, 10, 20, 50, 100之一")
        # 验证执行时长
        if task.duration not in [5, 10, 15, 20, 30]:
            raise HTTPException(status_code=400, detail="性能测试执行时长必须是5, 10, 15, 20, 30分钟之一")
    elif task.execution_task_type == "scenario":
        # 接口场景用例执行任务只能选择场景用例（从test_case_suites中选择）
        if not suite_ids:
            raise HTTPException(status_code=400, detail="接口场景用例执行任务必须选择测试用例组（test_case_suite_id或test_case_suite_ids）")
    elif task.execution_task_type == "interface":
        # 接口测试用例执行任务只能选择pytest类型的用例
        valid_cases = db.query(TestCase).filter(
            TestCase.id.in_(test_case_ids),
            TestCase.project_id == project_id,
            TestCase.case_type == "pytest"
        ).all()
        if len(valid_cases) != len(test_case_ids):
            raise HTTPException(status_code=400, detail="接口测试用例执行任务只能选择接口测试用例（pytest类型）")
    else:
        # 其他类型，验证用例存在即可
        valid_cases = db.query(TestCase).filter(
            TestCase.id.in_(test_case_ids),
            TestCase.project_id == project_id
        ).all()
        if len(valid_cases) != len(test_case_ids):
            raise HTTPException(status_code=400, detail="部分测试用例不存在")
    
    # 自动准备任务：分析依赖关系、构造测试数据
    preparation_result = None
    sorted_case_ids = test_case_ids
    dependency_analysis = None
    test_data_config = None
    
    if task.auto_prepare:
        try:
            # 获取数据库连接ID
            from app.models import DBConnection
            db_connection = db.query(DBConnection).filter(
                DBConnection.project_id == project_id
            ).first()
            connection_id = db_connection.id if db_connection else None
            
            # 准备任务
            preparation_service = TaskPreparationService(db)
            preparation_result = preparation_service.prepare_task(
                test_case_ids=test_case_ids,
                project_id=project_id,
                connection_id=connection_id
            )
            
            # 使用排序后的用例ID
            sorted_case_ids = preparation_result["sorted_case_ids"]
            dependency_analysis = json.dumps(preparation_result["dependency_analysis"], ensure_ascii=False)
            test_data_config = json.dumps(preparation_result["test_data_config"], ensure_ascii=False)
        
        except Exception as e:
            print(f"任务准备失败: {e}")
            # 如果准备失败，使用原始用例顺序
            dependency_analysis = json.dumps({"error": str(e)}, ensure_ascii=False)
    
    # 创建任务
    db_task = TestTask(
        project_id=project_id,
        name=task.name,
        scenario=task.scenario,
        task_type=task.task_type,
        execution_task_type=task.execution_task_type,
        cron_expression=task.cron_expression,
        test_case_ids=json.dumps(sorted_case_ids),  # 使用排序后的用例ID
        test_case_suite_id=test_case_suite_id,
        environment_id=task.environment_id,
        threads=task.threads if task.execution_task_type == "performance" else 10,
        duration=task.duration if task.execution_task_type == "performance" else 5,
        max_retries=task.max_retries,
        dependency_analysis=dependency_analysis,
        test_data_config=test_data_config,
        status="pending"
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    
    # 如果立即执行，启动任务
    if task.task_type == "immediate":
        task_scheduler.execute_task(db_task.id)
    elif task.task_type == "scheduled" and task.cron_expression:
        task_scheduler.schedule_task(db_task.id, task.cron_expression)
    
    # 返回任务信息，包含准备结果
    response = {
        **{
            "id": db_task.id,
            "name": db_task.name,
            "scenario": db_task.scenario,
            "task_type": db_task.task_type,
            "status": db_task.status,
            "test_case_ids": sorted_case_ids,
            "total_cases": len(sorted_case_ids),
            "environment_id": db_task.environment_id
        }
    }
    
    if preparation_result:
        response["preparation"] = {
            "dependency_count": preparation_result["dependency_analysis"].get("dependency_count", 0),
            "sorted": True,
            "test_data_generated": True
        }
    
    return response


@router.post("/{task_id}/execute")
async def execute_task(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """立即执行测试任务"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    # 检查任务状态
    if task.status == "running":
        raise HTTPException(status_code=400, detail="任务正在执行中")
    
    # 执行任务
    task_scheduler.execute_task(task_id)
    
    return {"message": "任务已启动", "task_id": task_id}


@router.post("/{task_id}/pause")
async def pause_task(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """暂停任务"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    if task.status != "running":
        raise HTTPException(status_code=400, detail="只能暂停运行中的任务")
    
    task_controller.pause_task(task_id)
    task.status = "paused"
    task.paused_at = datetime.now()
    db.commit()
    
    return {"message": "任务已暂停", "task_id": task_id}


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """继续任务"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    if task.status != "paused":
        raise HTTPException(status_code=400, detail="只能继续暂停的任务")
    
    task_controller.resume_task(task_id)
    task.status = "running"
    task.paused_at = None
    db.commit()
    
    return {"message": "任务已继续", "task_id": task_id}


@router.post("/{task_id}/stop")
async def stop_task(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """停止任务"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    if task.status not in ["running", "paused"]:
        raise HTTPException(status_code=400, detail="只能停止运行中或暂停的任务")
    
    task_controller.stop_task(task_id)
    task.status = "stopped"
    db.commit()
    
    return {"message": "任务已停止", "task_id": task_id}


@router.post("/{task_id}/retry")
async def retry_task(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """重试失败的任务"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    # 只能重试失败、停止或已完成的任务
    if task.status not in ["failed", "stopped", "completed"]:
        raise HTTPException(
            status_code=400, 
            detail=f"只能重试失败、停止或已完成的任务，当前状态: {task.status}"
        )
    
    if task.status == "failed" and task.retry_count >= task.max_retries:
        raise HTTPException(status_code=400, detail=f"已达到最大重试次数: {task.max_retries}")
    
    # 重置任务状态和进度
    was_failed = task.status == "failed"
    task.status = "pending"
    if was_failed:
        task.retry_count += 1
    task.progress = 0
    task.total_cases = 0
    task.passed_cases = 0
    task.failed_cases = 0
    task.skipped_cases = 0
    task.error_message = None
    task.executed_at = None
    task.completed_at = None
    task.paused_at = None
    task.execution_task_id = None
    task.result_summary = None
    db.commit()
    
    # 重新执行
    task_scheduler.execute_task(task_id)
    
    return {
        "message": "任务已重新提交执行",
        "task_id": task_id,
        "retry_count": task.retry_count,
        "status": task.status
    }


@router.post("/{task_id}/restart")
async def restart_task(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """重新执行任务（无论当前状态）"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    # 如果任务正在运行，先停止
    if task.status == "running":
        task_controller.stop_task(task_id)
        task.status = "stopped"
        db.commit()
    
    # 重置任务状态和进度
    task.status = "pending"
    task.progress = 0
    task.total_cases = 0
    task.passed_cases = 0
    task.failed_cases = 0
    task.skipped_cases = 0
    task.error_message = None
    task.executed_at = None
    task.completed_at = None
    task.paused_at = None
    task.execution_task_id = None
    task.result_summary = None
    # 不增加retry_count，因为是重新执行而不是重试
    db.commit()
    
    # 清除旧的任务结果
    from app.models import TestResult
    db.query(TestResult).filter(TestResult.task_id == task_id).delete()
    db.commit()
    
    # 重新执行
    task_scheduler.execute_task(task_id)
    
    return {
        "message": "任务已重新启动执行",
        "task_id": task_id,
        "status": task.status
    }


@router.get("/")
async def list_test_tasks(
    project_id: int,
    status: Optional[str] = Query(None, description="按状态筛选"),
    environment_id: Optional[int] = Query(None, description="按环境筛选"),
    execution_task_type: Optional[str] = Query(None, description="按执行任务类型筛选: scenario, interface, performance, other"),
    grouped: bool = Query(False, description="是否按类型分组返回"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试任务列表（分类型展示）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    query = db.query(TestTask).filter(TestTask.project_id == project_id)
    
    if status:
        query = query.filter(TestTask.status == status)
    if environment_id:
        query = query.filter(TestTask.environment_id == environment_id)
    if execution_task_type:
        query = query.filter(TestTask.execution_task_type == execution_task_type)
    
    tasks = query.order_by(TestTask.created_at.desc()).all()
    
    # 如果是运行中的任务，获取实时进度
    for task in tasks:
        # 兼容旧数据：如果有用例集但类型标记为interface，视为scenario
        suite_ids = []
        # 有些旧字段名不存在，使用getattr静默处理
        suite_ids_attr = getattr(task, "test_case_suite_ids", None)
        if suite_ids_attr:
            suite_ids = suite_ids_attr
        if getattr(task, "test_case_suite_id", None):
            suite_ids = suite_ids or []
            suite_ids.append(task.test_case_suite_id)
        if task.execution_task_type == "interface" and suite_ids:
            task.execution_task_type = "scenario"
        if task.status == "running" and task.execution_task_id:
            try:
                celery_task = celery_app.AsyncResult(task.execution_task_id)
                if celery_task.state == "PROGRESS":
                    task.progress = celery_task.info.get("progress", task.progress)
            except:
                pass
    
    # 如果请求分组，按execution_task_type分组返回
    if grouped:
        grouped_tasks = {
            "scenario": [],
            "interface": [],
            "performance": [],
            "other": []
        }
        
        for task in tasks:
            task_type = task.execution_task_type or "other"
            if task_type not in grouped_tasks:
                task_type = "other"
            
            # 转换为字典格式
            task_dict = {
                "id": task.id,
                "name": task.name,
                "scenario": task.scenario,
                "task_type": task.task_type,
                "execution_task_type": task.execution_task_type,
                "status": task.status,
                "progress": task.progress,
                "total_cases": task.total_cases,
                "passed_cases": task.passed_cases,
                "failed_cases": task.failed_cases,
                "skipped_cases": task.skipped_cases,
                "executed_at": task.executed_at.isoformat() if task.executed_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "allure_report_path": task.allure_report_path,
                "jtl_report_path": task.jtl_report_path,
                "performance_report_html": task.performance_report_html is not None
            }
            grouped_tasks[task_type].append(task_dict)
        
        return grouped_tasks
    
    # 否则返回平铺列表
    return tasks


@router.get("/{task_id}")
async def get_test_task(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试任务详情"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    # 获取实时状态
    task_status = None
    if task.execution_task_id:
        try:
            celery_task = celery_app.AsyncResult(task.execution_task_id)
            task_status = {
                "task_id": task.execution_task_id,
                "state": celery_task.state,
                "progress": celery_task.info.get("progress", task.progress) if celery_task.state == "PROGRESS" else task.progress,
                "current": celery_task.info.get("current", 0) if celery_task.state == "PROGRESS" else 0,
                "total": celery_task.info.get("total", task.total_cases) if celery_task.state == "PROGRESS" else task.total_cases,
                "passed": celery_task.info.get("passed", task.passed_cases) if celery_task.state == "PROGRESS" else task.passed_cases,
                "failed": celery_task.info.get("failed", task.failed_cases) if celery_task.state == "PROGRESS" else task.failed_cases
            }
        except:
            pass
    
    # 安全解析JSON字段
    test_case_ids = []
    if task.test_case_ids:
        try:
            test_case_ids = json.loads(task.test_case_ids)
        except (json.JSONDecodeError, TypeError):
            test_case_ids = []
    
    result_summary = None
    if task.result_summary:
        try:
            result_summary = json.loads(task.result_summary)
        except (json.JSONDecodeError, TypeError):
            result_summary = None
    
    # 兼容旧数据：如果有用例集但类型标记为interface，视为scenario
    suite_ids = []
    suite_ids_attr = getattr(task, "test_case_suite_ids", None)
    if suite_ids_attr:
        suite_ids = suite_ids_attr
    if getattr(task, "test_case_suite_id", None):
        suite_ids = suite_ids or []
        suite_ids.append(task.test_case_suite_id)
    if task.execution_task_type == "interface" and suite_ids:
        task.execution_task_type = "scenario"
    
    result = {
        "id": task.id,
        "project_id": task.project_id,
        "name": task.name,
        "task_type": task.task_type,
        "execution_task_type": task.execution_task_type,
        "cron_expression": task.cron_expression,
        "test_case_ids": test_case_ids,
        "environment_id": task.environment_id,
        "threads": task.threads,
        "duration": task.duration,
        "status": task.status,
        "progress": task.progress,
        "total_cases": task.total_cases,
        "passed_cases": task.passed_cases,
        "failed_cases": task.failed_cases,
        "skipped_cases": task.skipped_cases,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "executed_at": task.executed_at,
        "completed_at": task.completed_at,
        "paused_at": task.paused_at,
        "error_message": task.error_message,
        "result_summary": result_summary,
        "allure_report_path": task.allure_report_path,
        "jtl_report_path": task.jtl_report_path,
        "performance_report_html": task.performance_report_html,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "task_status": task_status
    }
    
    if task.environment:
        result["environment"] = {
            "id": task.environment.id,
            "name": task.environment.name,
            "env_type": task.environment.env_type,
            "base_url": task.environment.base_url
        }
    
    return result


@router.put("/{task_id}")
async def update_test_task(
    task_id: int,
    task_update: TestTaskUpdate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """更新测试任务"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    if task.status == "running":
        raise HTTPException(status_code=400, detail="不能修改运行中的任务")
    
    # 更新字段
    if task_update.name is not None:
        task.name = task_update.name
    if task_update.cron_expression is not None:
        task.cron_expression = task_update.cron_expression
    if task_update.test_case_ids is not None:
        task.test_case_ids = json.dumps(task_update.test_case_ids)
    if task_update.environment_id is not None:
        task.environment_id = task_update.environment_id
    if task_update.max_retries is not None:
        task.max_retries = task_update.max_retries
    
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}")
async def delete_test_task(
    task_id: int,
    force: bool = Query(False, description="是否强制删除运行中的任务"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """删除测试任务"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    # 如果任务正在运行或暂停，需要先停止
    if task.status in ["running", "paused"]:
        if not force:
            raise HTTPException(
                status_code=400,
                detail=f"任务正在{task.status}，无法删除。如需强制删除，请设置force=true"
            )
        else:
            # 强制停止任务
            task_controller.stop_task(task_id)
            task.status = "stopped"
            db.commit()
    
    # 取消定时任务
    if task.task_type == "scheduled":
        try:
            task_scheduler.cancel_task(task_id)
        except:
            pass
    
    # 删除任务相关的测试结果
    from app.models import TestResult
    db.query(TestResult).filter(TestResult.task_id == task_id).delete()
    
    # 删除任务
    db.delete(task)
    db.commit()
    
    return {"message": "测试任务已删除", "task_id": task_id}


@router.get("/{task_id}/report")
async def get_task_report(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取任务报告（Allure或JTL）"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    if task.execution_task_type in ["scenario", "interface"]:
        # Allure报告
        if not task.allure_report_path:
            raise HTTPException(status_code=404, detail="Allure报告尚未生成")
        return {
            "report_type": "allure",
            "report_path": task.allure_report_path,
            "report_url": f"/api/jobs/{task_id}/allure-report"
        }
    elif task.execution_task_type == "performance":
        # JTL报告
        if not task.jtl_report_path:
            raise HTTPException(status_code=404, detail="JTL报告尚未生成")
        return {
            "report_type": "jtl",
            "report_path": task.jtl_report_path,
            "report_url": f"/api/jobs/{task_id}/jtl-report",
            "performance_analysis": json.loads(task.performance_analysis) if task.performance_analysis else None,
            "performance_report_html_url": f"/api/jobs/{task_id}/performance-report"
        }
    else:
        raise HTTPException(status_code=400, detail="该任务类型不支持报告")


@router.get("/{task_id}/logs")
async def get_task_logs(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取任务执行日志"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    return {
        "task_id": task_id,
        "execution_logs": task.execution_logs,
        "error_message": task.error_message
    }


@router.get("/{task_id}/allure-report")
async def serve_allure_report(
    task_id: int,
    path: str = "",
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """提供HTML测试报告静态文件服务"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    def render_message(message: str, status_code: int = 202):
        html = f"""
        <html>
          <head>
            <meta charset='utf-8'/>
            <title>HTML测试报告生成中</title>
            <style>
              body {{ font-family: Arial, Helvetica, sans-serif; background-color: #f7f7f7; }}
              .container {{ max-width: 560px; margin: 80px auto; padding: 24px 28px; background: #fff; border-radius: 8px; box-shadow: 0 6px 18px rgba(0,0,0,0.08); }}
              h1 {{ font-size: 20px; margin-bottom: 16px; color: #333; }}
              p {{ font-size: 15px; color: #555; line-height: 1.6; }}
            </style>
          </head>
          <body>
            <div class='container'>
              <h1>HTML 测试报告</h1>
              <p>{message}</p>
              <p>请稍后刷新当前页面以查看最新结果。</p>
            </div>
          </body>
        </html>
        """
        return HTMLResponse(content=html, status_code=status_code)

    report_path = task.allure_report_path
    if not report_path:
        return render_message('HTML测试报告尚未生成，请等待任务完成。', status_code=404)
    
    # 检查报告路径是文件还是目录
    if os.path.isfile(report_path):
        # 如果是文件，直接返回
        if report_path.endswith('.html'):
            with open(report_path, 'r', encoding='utf-8') as f:
                return HTMLResponse(content=f.read())
        return FileResponse(report_path)
    elif os.path.isdir(report_path):
        # 如果是目录，查找index.html
        target_path = path or "index.html"
        file_path = os.path.join(report_path, target_path)
        if os.path.exists(file_path):
            if file_path.endswith('.html'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return HTMLResponse(content=f.read())
            return FileResponse(file_path)
        else:
            # 尝试查找目录中的index.html
            index_file = os.path.join(report_path, "index.html")
            if os.path.exists(index_file):
                with open(index_file, 'r', encoding='utf-8') as f:
                    return HTMLResponse(content=f.read())
            return render_message(f'HTML测试报告文件不存在: {file_path}', status_code=404)
    else:
        # 路径不存在
        return render_message(f'HTML测试报告路径不存在: {report_path}', status_code=404)


@router.get("/{task_id}/jtl-report")
async def serve_jtl_report(
    task_id: int,
    path: str = "",
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """提供JTL报告静态文件服务"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    if not task.jtl_report_path:
        raise HTTPException(status_code=404, detail="JTL报告尚未生成")
    
    # JTL报告路径在JMeter容器内，但通过共享卷挂载到了backend容器
    # report_dir是容器内路径，例如：/app/jmeter-results/task_15/html-report
    # 在backend容器中，对应的路径是：/app/jmeter-results/task_15/html-report
    report_dir = task.jtl_report_path  # 例如：/app/jmeter-results/task_15/html-report
    
    # 如果没有指定路径，默认访问index.html
    if not path:
        # 先检查report_dir是否是目录
        if os.path.isdir(report_dir):
            # 是目录，查找index.html
            file_path = os.path.join(report_dir, "index.html")
        else:
            # 不是目录，可能report_dir本身就是文件路径
            file_path = report_dir
    else:
        file_path = os.path.join(report_dir, path)
    
    # 检查文件是否存在（现在可以直接访问，因为已经通过卷挂载）
    if os.path.exists(file_path):
        if os.path.isdir(file_path):
            # 如果是目录，查找index.html
            index_path = os.path.join(file_path, "index.html")
            if os.path.exists(index_path):
                if index_path.endswith('.html'):
                    with open(index_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # 修复静态资源路径，使其相对于API路径
                        # 将相对路径转换为绝对路径
                        content = content.replace('href="content/', f'href="/api/jobs/{task_id}/jtl-report/content/')
                        content = content.replace('src="content/', f'src="/api/jobs/{task_id}/jtl-report/content/')
                        content = content.replace('href="sbadmin2-1.0.7/', f'href="/api/jobs/{task_id}/jtl-report/sbadmin2-1.0.7/')
                        content = content.replace('src="sbadmin2-1.0.7/', f'src="/api/jobs/{task_id}/jtl-report/sbadmin2-1.0.7/')
                        return HTMLResponse(content=content)
                else:
                    return FileResponse(index_path)
            else:
                raise HTTPException(status_code=404, detail=f"目录中没有index.html: {file_path}")
        else:
            # 是文件，直接返回
            if file_path.endswith('.html'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 修复静态资源路径
                    content = content.replace('href="content/', f'href="/api/jobs/{task_id}/jtl-report/content/')
                    content = content.replace('src="content/', f'src="/api/jobs/{task_id}/jtl-report/content/')
                    content = content.replace('href="sbadmin2-1.0.7/', f'href="/api/jobs/{task_id}/jtl-report/sbadmin2-1.0.7/')
                    content = content.replace('src="sbadmin2-1.0.7/', f'src="/api/jobs/{task_id}/jtl-report/sbadmin2-1.0.7/')
                    return HTMLResponse(content=content)
            else:
                return FileResponse(file_path)
    else:
        raise HTTPException(
            status_code=404, 
            detail=f"JTL报告文件不存在: {file_path} (report_dir: {report_dir}, path: {path})"
        )


@router.get("/{task_id}/performance-report")
async def get_performance_report(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取性能分析报告HTML（包含图表）"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    if task.execution_task_type != "performance":
        raise HTTPException(status_code=400, detail="该任务不是性能测试任务")
    
    if not task.performance_report_html:
        raise HTTPException(status_code=404, detail="性能分析报告尚未生成")
    
    return HTMLResponse(content=task.performance_report_html)


@router.post("/{task_id}/generate-performance-analysis")
async def generate_performance_analysis(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成性能瓶颈分析报告（调用DeepSeek分析）"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    if task.execution_task_type != "performance":
        raise HTTPException(status_code=400, detail="该任务不是性能测试任务")
    
    if not task.jtl_report_path:
        raise HTTPException(status_code=404, detail="JTL报告尚未生成，无法进行分析")
    
    # 获取JTL文件路径
    report_dir = task.jtl_report_path
    jtl_file_path = os.path.join(os.path.dirname(report_dir), "result.jtl")
    
    # 检查JTL文件是否存在
    if not os.path.exists(jtl_file_path):
        raise HTTPException(status_code=404, detail="JTL文件不存在，无法进行分析")
    
    # 调用DeepSeek分析
    from app.celery_tasks_execution import analyze_performance_with_deepseek
    
    try:
        analysis_result = analyze_performance_with_deepseek(
            jtl_file_path=jtl_file_path,
            task_id=task_id,
            task_name=task.name or f"任务{task_id}",
            threads=task.threads or 10,
            duration=task.duration or 5
        )
        
        # 保存分析结果
        task.performance_analysis = json.dumps(analysis_result, ensure_ascii=False)
        
        # 检查是否有html_report，如果没有则生成一个HTML报告
        if 'html_report' in analysis_result and analysis_result.get('html_report'):
            task.performance_report_html = analysis_result['html_report']
        else:
            # 如果没有html_report，生成一个HTML报告
            # 检查是否有错误
            has_error = 'error' in analysis_result
            
            try:
                # 尝试生成完整的HTML报告
                from app.services.performance_report_generator import generate_performance_report_html
                html_report = generate_performance_report_html(
                    jtl_file_path=jtl_file_path,
                    task_id=task_id,
                    task_name=task.name or f"任务{task_id}",
                    threads=task.threads or 10,
                    duration=task.duration or 5,
                    deepseek_analysis=analysis_result if not has_error else None
                )
                task.performance_report_html = html_report
            except Exception as gen_error:
                print(f"[generate_performance_analysis] 生成HTML报告失败: {gen_error}")
                import traceback
                traceback.print_exc()
                # 生成一个简单的HTML报告
                error_info = ""
                if has_error:
                    error_info = f'<div class="error"><h2>分析错误</h2><p>{analysis_result.get("error", "未知错误")}</p></div>'
                
                html_content = f"""
                <html>
                <head>
                    <title>性能瓶颈分析报告 - {task.name or f'任务{task_id}'}</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 20px; }}
                        h1 {{ color: #333; }}
                        .error {{ color: red; background: #ffe6e6; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                        .success {{ color: green; }}
                        .info {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                        pre {{ background: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; }}
                    </style>
                </head>
                <body>
                    <h1>性能瓶颈分析报告</h1>
                    <div class="info">
                        <h2>任务信息</h2>
                        <p><strong>任务名称:</strong> {task.name or f'任务{task_id}'}</p>
                        <p><strong>线程数:</strong> {task.threads or 10}</p>
                        <p><strong>执行时长:</strong> {task.duration or 5} 分钟</p>
                    </div>
                    {error_info}
                    <h2>分析结果</h2>
                    <pre>{json.dumps(analysis_result, ensure_ascii=False, indent=2)}</pre>
                </body>
                </html>
                """
                task.performance_report_html = html_content
        
        db.commit()
        
        return {
            "status": "success",
            "message": "性能瓶颈分析报告生成成功",
            "report_url": f"/api/jobs/{task_id}/performance-report"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成性能分析报告失败: {str(e)}")
