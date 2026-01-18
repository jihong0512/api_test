"""
测试编排服务API
提供统一的测试流程编排接口
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import Project, User
from app.routers.auth import get_current_user_optional
from app.services.test_orchestrator import TestOrchestrator

router = APIRouter()


class FullTestFlowRequest(BaseModel):
    """完整测试流程请求"""
    document_id: Optional[int] = None
    document_file_path: Optional[str] = None
    environment_id: Optional[int] = None
    test_suite_id: Optional[int] = None
    auto_execute: bool = False


@router.post("/full-flow")
async def execute_full_test_flow(
    project_id: int,
    request: FullTestFlowRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """执行完整的测试流程"""
    # 验证项目权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 创建编排服务
    orchestrator = TestOrchestrator(db)
    
    # 执行完整流程
    result = await orchestrator.full_test_flow(
        project_id=project_id,
        document_id=request.document_id,
        document_file_path=request.document_file_path,
        environment_id=request.environment_id,
        test_suite_id=request.test_suite_id,
        auto_execute=request.auto_execute
    )
    
    return result


@router.get("/flow-status/{project_id}")
async def get_test_flow_status(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试流程状态"""
    # 验证项目权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    orchestrator = TestOrchestrator(db)
    status = orchestrator.get_test_flow_status(project_id)
    
    return status








































