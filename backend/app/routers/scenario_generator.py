from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from app.database import get_db
from app.models import APIInterface, Project, User, DBConnection
from app.routers.auth import get_current_user_optional
from app.services.scenario_generator import ScenarioGenerator

router = APIRouter()


class GenerateScenarioRequest(BaseModel):
    user_story: str
    connection_id: Optional[int] = None
    api_ids: Optional[List[int]] = None  # 可选：指定要包含的接口ID


@router.post("/generate/{project_id}")
async def generate_scenario(
    project_id: int,
    request: GenerateScenarioRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    基于用户故事生成测试场景
    
    示例请求体：
    {
        "user_story": "用户成功发布一篇文章并为自己评论",
        "connection_id": 1,
        "api_ids": [1, 3, 5]  // 可选，指定要包含的接口
    }
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取API接口
    query = db.query(APIInterface).filter(APIInterface.project_id == project_id)
    if request.api_ids:
        query = query.filter(APIInterface.id.in_(request.api_ids))
    
    api_interfaces = query.all()
    
    if not api_interfaces:
        raise HTTPException(status_code=400, detail="No API interfaces found")
    
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
    
    # 生成测试场景
    generator = ScenarioGenerator(db)
    scenario = generator.generate_scenario_from_user_story(
        request.user_story,
        api_list,
        connection_id,
        project_id
    )
    
    return {
        "project_id": project_id,
        "connection_id": connection_id,
        "user_story": request.user_story,
        "scenario": scenario
    }


@router.post("/generate-from-dependency/{project_id}")
async def generate_scenario_from_dependency(
    project_id: int,
    user_story: str = Body(..., embed=True),
    connection_id: Optional[int] = Body(None),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """基于依赖关系自动识别接口并生成场景"""
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
            "response_schema": api.response_schema,
            "headers": api.headers
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
    
    # 生成测试场景
    generator = ScenarioGenerator(db)
    scenario = generator.generate_scenario_from_user_story(
        user_story,
        api_list,
        connection_id,
        project_id
    )
    
    return {
        "project_id": project_id,
        "connection_id": connection_id,
        "user_story": user_story,
        "scenario": scenario
    }









































