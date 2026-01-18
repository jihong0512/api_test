from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from app.database import get_db
from app.models import APIInterface, Project, User, DBConnection
from app.routers.auth import get_current_user_optional
from app.services.dependency_analyzer import DependencyAnalyzer, TestFlowGenerator

router = APIRouter()


class GenerateFlowRequest(BaseModel):
    connection_id: Optional[int] = None
    flow_type: str = "auto"  # auto, 查看公开内容, 登录后操作, 运动训练流程
    api_ids: Optional[List[int]] = None  # 可选：指定要包含的接口ID


@router.post("/analyze-dependencies/{project_id}")
async def analyze_dependencies(
    project_id: int,
    connection_id: Optional[int] = Query(None, description="数据库连接ID"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """分析接口依赖关系"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取所有API接口
    api_interfaces = db.query(APIInterface).filter(
        APIInterface.project_id == project_id
    ).all()
    
    api_list = [
        {
            "id": api.id,
            "name": api.name or api.path,
            "method": api.method,
            "path": api.path,
            "base_url": api.base_url,
            "params": api.params,
            "request_body": api.request_body,
            "response_schema": api.response_schema
        }
        for api in api_interfaces
    ]
    
    # 获取数据库连接
    if not connection_id:
        connection = db.query(DBConnection).filter(
            DBConnection.project_id == project_id
        ).first()
        if connection:
            connection_id = connection.id
    
    if not connection_id:
        raise HTTPException(status_code=400, detail="No database connection found")
    
    # 分析依赖关系
    analyzer = DependencyAnalyzer(db)
    dependency_graph = analyzer.analyze_api_dependencies(
        api_list, connection_id, project_id
    )
    
    return {
        "project_id": project_id,
        "connection_id": connection_id,
        "dependency_graph": dependency_graph
    }


@router.post("/generate-flow/{project_id}")
async def generate_test_flow(
    project_id: int,
    request: GenerateFlowRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成测试流程"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取API接口
    query = db.query(APIInterface).filter(APIInterface.project_id == project_id)
    if request.api_ids:
        query = query.filter(APIInterface.id.in_(request.api_ids))
    
    api_interfaces = query.all()
    
    api_list = [
        {
            "id": api.id,
            "name": api.name or api.path,
            "method": api.method,
            "path": api.path,
            "base_url": api.base_url,
            "params": api.params,
            "request_body": api.request_body,
            "response_schema": api.response_schema,
            "headers": api.headers
        }
        for api in api_interfaces
    ]
    
    # 获取数据库连接
    connection_id = request.connection_id
    if not connection_id:
        connection = db.query(DBConnection).filter(
            DBConnection.project_id == project_id
        ).first()
        if connection:
            connection_id = connection.id
    
    if not connection_id:
        raise HTTPException(status_code=400, detail="No database connection found")
    
    # 生成测试流程
    flow_generator = TestFlowGenerator(db)
    test_flow = flow_generator.generate_test_flow(
        api_list, connection_id, project_id, request.flow_type
    )
    
    return {
        "project_id": project_id,
        "connection_id": connection_id,
        "flow_type": request.flow_type,
        "test_flow": test_flow
    }


@router.get("/business-rules/{project_id}")
async def get_business_rules(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取业务规则定义"""
    analyzer = DependencyAnalyzer(db)
    
    return {
        "business_rules": analyzer.business_rules,
        "description": {
            "未登录用户": "只能查看运动课程、运动计划",
            "已登录用户": "可以创建家庭活动、领取积分、打卡",
            "运动功能": "需要先绑定运动设备",
            "训练计划": "需要登录 → 绑定设备 → 在课程中点击开始"
        }
    }









































