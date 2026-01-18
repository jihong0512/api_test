from fastapi import APIRouter, Depends, HTTPException, Body, Request, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel
import json
from celery.result import AsyncResult

from app.database import get_db
from app.models import TestCase, TestEnvironment, Project, User, TestDebugRecord
from app.routers.auth import get_current_user_optional
from app.services.test_executor import TestExecutor
from app.celery_app import celery_app
from typing import List
from sqlalchemy import desc

router = APIRouter()


class DebugTestCaseRequest(BaseModel):
    test_case_id: int
    environment_id: int
    test_data_override: Optional[Dict[str, Any]] = None
    headers_override: Optional[Dict[str, Any]] = None
    params_override: Optional[Dict[str, Any]] = None
    body_override: Optional[Dict[str, Any]] = None


class ExecuteTestCaseCodeRequest(BaseModel):
    test_case_id: int
    environment_id: int


class FixTestCaseWithDeepSeekRequest(BaseModel):
    test_case_id: int
    error_output: str
    user_suggestion: str = ""  # 用户修复建议


@router.post("/debug")
async def debug_test_case(
    project_id: int,
    request: DebugTestCaseRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    调试单个测试用例（立即执行并返回结果）
    
    用于在线调试测试用例，不保存结果到数据库
    """
    # 检查权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取测试用例
    test_case = db.query(TestCase).filter(
        TestCase.id == request.test_case_id,
        TestCase.project_id == project_id
    ).first()
    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")
    
    # 获取测试环境
    environment = db.query(TestEnvironment).filter(
        TestEnvironment.id == request.environment_id,
        TestEnvironment.project_id == project_id
    ).first()
    if not environment:
        raise HTTPException(status_code=404, detail="Test environment not found")
    
    # 检查用例类型：JMeter用例不能使用TestExecutor执行
    case_type = test_case.case_type or 'pytest'
    print(f"[debug_test_case] 用例ID: {request.test_case_id}, 用例类型: {case_type}, 用例名称: {test_case.name}")
    
    if case_type == 'jmeter':
        raise HTTPException(
            status_code=400, 
            detail=f"JMeter性能测试用例不能使用/debug接口执行，请使用/execute-code接口。用例ID: {request.test_case_id}, 用例名称: {test_case.name}"
        )
    
    # 创建执行器
    executor = TestExecutor(db)
    
    # 准备测试数据（使用覆盖数据）
    extracted_data = {}
    
    # 如果提供了覆盖数据，临时修改用例数据
    original_test_data = test_case.test_data
    if request.test_data_override:
        test_case.test_data = json.dumps(request.test_data_override, ensure_ascii=False)
    
    try:
        # 执行用例（同步方法，在异步函数中调用）
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: executor.execute_test_case(
                test_case=test_case,
                environment=environment,
                extracted_data=extracted_data,
                prepared_test_data=request.test_data_override
            )
        )
        
        # 如果提供了覆盖的请求参数，应用它们
        if request.headers_override or request.params_override or request.body_override:
            if isinstance(result.get("request_data"), dict):
                if request.headers_override:
                    result["request_data"]["headers"] = {
                        **result["request_data"].get("headers", {}),
                        **request.headers_override
                    }
                if request.params_override:
                    result["request_data"]["params"] = {
                        **result["request_data"].get("params", {}),
                        **request.params_override
                    }
                if request.body_override:
                    if isinstance(result["request_data"].get("body"), dict):
                        result["request_data"]["body"] = {
                            **result["request_data"]["body"],
                            **request.body_override
                        }
                    else:
                        result["request_data"]["body"] = request.body_override
        
        return {
            "status": "success",
            "result": result,
            "message": "调试执行完成"
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "调试执行失败"
        }
    
    finally:
        # 恢复原始测试数据
        test_case.test_data = original_test_data


@router.get("/preview")
async def preview_test_case_get(
    project_id: int = Query(..., description="项目ID"),
    test_case_id: int = Query(..., description="测试用例ID"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """预览测试用例的请求数据（GET方法）"""
    return await _preview_test_case_impl(project_id, test_case_id, None, db)

@router.post("/preview")
async def preview_test_case_post(
    project_id: int = Query(..., description="项目ID"),
    test_case_id: int = Query(..., description="测试用例ID"),
    test_data_override: Optional[Dict[str, Any]] = Body(None),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """预览测试用例的请求数据（POST方法）"""
    return await _preview_test_case_impl(project_id, test_case_id, test_data_override, db)

async def _preview_test_case_impl(
    project_id: int,
    test_case_id: int,
    test_data_override: Optional[Dict[str, Any]],
    db: Session
):
    """
    预览测试用例的请求数据（不执行）
    
    用于在调试前预览将要发送的请求
    """
    # 检查权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取测试用例
    test_case = db.query(TestCase).filter(
        TestCase.id == test_case_id,
        TestCase.project_id == project_id
    ).first()
    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")
    
    # 获取API接口
    api_interface = None
    if test_case.api_interface_id:
        from app.models import APIInterface
        api_interface = db.query(APIInterface).filter(
            APIInterface.id == test_case.api_interface_id
        ).first()
    
    if not api_interface:
        raise HTTPException(status_code=404, detail="API interface not found")
    
    # 构建请求数据（统一使用模型字段）
    method = api_interface.method.upper()
    url = api_interface.url or ""
    headers = json.loads(api_interface.headers) if api_interface.headers else {}
    params = json.loads(api_interface.params) if api_interface.params else {}
    body = json.loads(api_interface.body) if api_interface.body else None
    
    # 应用测试数据覆盖
    if test_case.test_data or test_data_override:
        test_data = test_data_override or json.loads(test_case.test_data) if test_case.test_data else {}
        if isinstance(test_data, dict):
            if test_data.get("headers"):
                headers.update(test_data["headers"])
            if test_data.get("params"):
                params.update(test_data["params"])
            if test_data.get("body"):
                if isinstance(body, dict) and isinstance(test_data["body"], dict):
                    body = {**body, **test_data["body"]}
                else:
                    body = test_data["body"]
    
    return {
        "method": method,
        "url": url,
        "headers": headers,
        "params": params,
        "body": body,
        "full_url": url  # 实际URL需要环境base_url，这里返回相对路径
    }


@router.post("/execute-code")
async def execute_test_case_code(
    project_id: int,
    request: ExecuteTestCaseCodeRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    执行测试用例的测试代码（不自动修复）
    
    1. 执行测试代码
    2. 返回执行结果
    3. 如果失败，需要用户手动触发DeepSeek修复
    """
    from app.celery_tasks import execute_test_case_task, execute_jmeter_performance_test_task
    
    # 检查权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取测试用例
    test_case = db.query(TestCase).filter(
        TestCase.id == request.test_case_id,
        TestCase.project_id == project_id
    ).first()
    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")
    
    if not test_case.test_code:
        raise HTTPException(status_code=400, detail="测试用例没有测试代码")
    
    # 获取测试环境
    environment = db.query(TestEnvironment).filter(
        TestEnvironment.id == request.environment_id,
        TestEnvironment.project_id == project_id
    ).first()
    if not environment:
        raise HTTPException(status_code=404, detail="Test environment not found")
    
    # 根据用例类型选择不同的执行任务
    # 严格检查：如果是jmeter类型，必须使用JMeter执行
    case_type = test_case.case_type or 'pytest'  # 默认为pytest
    
    print(f"[执行测试用例] 用例ID: {request.test_case_id}, 用例类型: {case_type}, 用例名称: {test_case.name}")
    
    if case_type == 'jmeter':
        # JMeter性能测试用例：必须使用JMeter执行，使用2个线程进行调试
        print(f"[执行测试用例] 检测到JMeter性能测试用例，使用execute_jmeter_performance_test_task执行")
        task = execute_jmeter_performance_test_task.delay(
            test_case_id=request.test_case_id,
            environment_id=request.environment_id,
            threads=2  # 调试时使用2个线程
        )
        return {
            "status": "submitted",
            "task_id": task.id,
            "message": "JMeter性能测试执行任务已提交（使用2个线程）"
        }
    else:
        # 普通测试用例：使用pytest执行
        print(f"[执行测试用例] 检测到普通测试用例（类型: {case_type}），使用execute_test_case_task执行")
        task = execute_test_case_task.delay(
            test_case_id=request.test_case_id,
            environment_id=request.environment_id
        )
        return {
            "status": "submitted",
            "task_id": task.id,
            "message": "测试代码执行任务已提交"
        }


@router.get("/task-status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取Celery任务状态"""
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        
        result = {
            "task_id": task_id,
            "state": task_result.state,
        }
        
        if task_result.state == "PROGRESS":
            result["meta"] = task_result.info
        elif task_result.state == "SUCCESS":
            result["result"] = task_result.result
        elif task_result.state == "FAILURE":
            result["error"] = str(task_result.info)
            result["traceback"] = task_result.traceback
        elif task_result.state == "REVOKED":
            result["error"] = "任务已被用户中断"
            result["message"] = "任务已中断"
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务状态失败: {str(e)}")


@router.post("/task-cancel/{task_id}")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """取消/终止Celery任务"""
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        
        # 获取任务当前状态
        try:
            current_state = task_result.state
        except Exception as state_error:
            # 如果获取状态失败，尝试直接取消
            print(f"获取任务状态失败: {state_error}")
            current_state = None
        
        # 检查任务状态
        if current_state and current_state in ['SUCCESS', 'FAILURE', 'REVOKED']:
            return {
                "status": "already_finished",
                "message": f"任务已经完成或已终止，当前状态: {current_state}",
                "task_id": task_id,
                "state": current_state
            }
        
        # 尝试终止任务
        try:
            # 使用control.revoke终止任务
            celery_app.control.revoke(task_id, terminate=True, signal='SIGTERM')
            
            # 等待一小段时间确保任务被终止
            import time
            time.sleep(0.5)
            
            # 再次检查状态
            try:
                final_state = task_result.state
            except:
                final_state = 'REVOKED'
            
            return {
                "status": "cancelled",
                "message": "任务已成功终止",
                "task_id": task_id,
                "state": final_state
            }
        except Exception as revoke_error:
            # 如果revoke失败，尝试使用abort
            print(f"revoke失败，尝试abort: {revoke_error}")
            try:
                celery_app.control.abort(task_id)
                return {
                    "status": "cancelled",
                    "message": "任务已终止（使用abort）",
                    "task_id": task_id
                }
            except Exception as abort_error:
                # 如果都失败了，至少返回一个响应
                print(f"abort也失败: {abort_error}")
                return {
                    "status": "partial_cancelled",
                    "message": f"任务终止请求已发送，但确认状态时出错: {str(abort_error)}",
                    "task_id": task_id
                }
        
    except Exception as e:
        import traceback
        error_detail = str(e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"终止任务失败: {error_detail}")


@router.post("/fix-with-deepseek")
async def fix_test_case_with_deepseek(
    project_id: int,
    request: FixTestCaseWithDeepSeekRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    使用DeepSeek修复测试用例代码
    
    用户手动触发，每次点击修复一次
    """
    from app.celery_tasks import fix_test_case_with_deepseek_task
    
    # 检查权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取测试用例
    test_case = db.query(TestCase).filter(
        TestCase.id == request.test_case_id,
        TestCase.project_id == project_id
    ).first()
    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")
    
    if not test_case.test_code:
        raise HTTPException(status_code=400, detail="测试用例没有测试代码")
    
    # 提交异步任务
    task = fix_test_case_with_deepseek_task.delay(
        test_case_id=request.test_case_id,
        error_output=request.error_output,
        user_suggestion=request.user_suggestion
    )
    
    return {
        "status": "submitted",
        "task_id": task.id,
        "message": "DeepSeek修复任务已提交"
    }


@router.get("/debug-records/{test_case_id}")
async def get_debug_records(
    test_case_id: int,
    project_id: int = Query(..., description="项目ID"),
    limit: int = Query(50, description="返回记录数限制"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试用例的调试记录列表"""
    # 检查权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 检查测试用例是否存在且属于该项目
    test_case = db.query(TestCase).filter(
        TestCase.id == test_case_id,
        TestCase.project_id == project_id
    ).first()
    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")
    
    # 获取调试记录列表（按执行时间倒序）
    records = db.query(TestDebugRecord).filter(
        TestDebugRecord.test_case_id == test_case_id
    ).order_by(desc(TestDebugRecord.execution_time)).limit(limit).all()
    
    # 格式化返回数据
    result = []
    for record in records:
        result.append({
            "id": record.id,
            "test_case_id": record.test_case_id,
            "environment_id": record.environment_id,
            "task_id": record.task_id,
            "execution_status": record.execution_status,
            "execution_result": record.execution_result,
            "error_message": record.error_message,
            "execution_time": record.execution_time.isoformat() if record.execution_time else None,
            "duration": record.duration,
            "debug_logs": record.debug_logs,
            "created_at": record.created_at.isoformat() if record.created_at else None
        })
    
    return {
        "status": "success",
        "records": result,
        "total": len(result)
    }

