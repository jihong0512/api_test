from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import json

from app.database import get_db
from app.models import TestResult, TestTask, Project, User
from app.routers.auth import get_current_user_optional

router = APIRouter()


class TestResultResponse(BaseModel):
    id: int
    task_id: int
    test_case_id: int
    status: str
    execution_time: Optional[float]
    status_code: Optional[int]
    request_size: Optional[int]
    response_size: Optional[int]
    
    class Config:
        from_attributes = True


@router.get("/")
async def list_test_results(
    task_id: int,
    status: Optional[str] = Query(None, description="按状态筛选"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试结果列表（支持筛选）"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    query = db.query(TestResult).filter(TestResult.task_id == task_id)
    
    if status:
        query = query.filter(TestResult.status == status)
    
    results = query.order_by(TestResult.created_at).all()
    
    # 格式化结果数据
    formatted_results = []
    for result in results:
        result_dict = {
            "id": result.id,
            "task_id": result.task_id,
            "test_case_id": result.test_case_id,
            "status": result.status,
            "execution_time": float(result.execution_time) if result.execution_time else None,
            "status_code": result.status_code,
            "request_size": result.request_size,
            "response_size": result.response_size,
            "error_message": result.error_message,
            "created_at": result.created_at
        }
        
        # 解析JSON字段
        if result.request_data:
            try:
                result_dict["request_data"] = json.loads(result.request_data)
            except:
                result_dict["request_data"] = result.request_data
        
        if result.response_data:
            try:
                result_dict["response_data"] = json.loads(result.response_data)
            except:
                result_dict["response_data"] = result.response_data
        
        if result.assertions_result:
            try:
                result_dict["assertions_result"] = json.loads(result.assertions_result)
            except:
                result_dict["assertions_result"] = result.assertions_result
        
        if result.performance_metrics:
            try:
                result_dict["performance_metrics"] = json.loads(result.performance_metrics)
            except:
                result_dict["performance_metrics"] = result.performance_metrics
        
        if result.failure_analysis:
            try:
                result_dict["failure_analysis"] = json.loads(result.failure_analysis)
            except:
                result_dict["failure_analysis"] = result.failure_analysis
        
        formatted_results.append(result_dict)
    
    return formatted_results


@router.get("/{result_id}")
async def get_test_result(
    result_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试结果详情"""
    result = db.query(TestResult).filter(TestResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    # 检查权限
    task = db.query(TestTask).filter(TestTask.id == result.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    project = db.query(Project).filter(
        Project.id == task.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    # 格式化结果
    result_dict = {
        "id": result.id,
        "task_id": result.task_id,
        "test_case_id": result.test_case_id,
        "status": result.status,
        "execution_time": float(result.execution_time) if result.execution_time else None,
        "status_code": result.status_code,
        "request_size": result.request_size,
        "response_size": result.response_size,
        "error_message": result.error_message,
        "created_at": result.created_at
    }
    
    # 解析JSON字段
    try:
        result_dict["request_data"] = json.loads(result.request_data) if result.request_data else None
        result_dict["response_data"] = json.loads(result.response_data) if result.response_data else None
        result_dict["assertions_result"] = json.loads(result.assertions_result) if result.assertions_result else None
        result_dict["performance_metrics"] = json.loads(result.performance_metrics) if result.performance_metrics else None
        result_dict["failure_analysis"] = json.loads(result.failure_analysis) if result.failure_analysis else None
        result_dict["ai_suggestions"] = json.loads(result.ai_suggestions) if result.ai_suggestions else None
    except:
        pass
    
    return result_dict


