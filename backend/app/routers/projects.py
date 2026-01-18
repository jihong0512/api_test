from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import Project, User
from app.routers.auth import get_current_user_optional

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    user_id: int
    
    class Config:
        from_attributes = True


@router.post("/", response_model=ProjectResponse)
async def create_project(
    project: ProjectCreate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """创建项目"""
    db_project = Project(name=project.name, description=project.description, user_id=current_user.id)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


@router.get("/", response_model=List[ProjectResponse])
async def list_projects(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取项目列表（无需登录）"""
    # 如果没有用户，返回所有项目
    if not current_user:
        projects = db.query(Project).all()
    else:
        projects = db.query(Project).filter(Project.user_id == current_user.id).all()
    return projects


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取项目详情（无需登录）"""
    if not current_user:
        project = db.query(Project).filter(Project.id == project_id).first()
    else:
        project = db.query(Project).filter(
            Project.id == project_id,
            Project.user_id == current_user.id
        ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# 项目删除功能已禁用
# @router.delete("/{project_id}")
# async def delete_project(
#     project_id: int,
#     current_user: User = Depends(get_current_user_optional),
#     db: Session = Depends(get_db)
# ):
#     """删除项目（无需登录）"""
#     if not current_user:
#         project = db.query(Project).filter(Project.id == project_id).first()
#     else:
#         project = db.query(Project).filter(
#             Project.id == project_id,
#             Project.user_id == current_user.id
#         ).first()
#     
#     if not project:
#         raise HTTPException(status_code=404, detail="Project not found")
#     
#     # 删除项目（由于设置了级联删除，相关的文档、接口等会自动删除）
#     db.delete(project)
#     db.commit()
#     
#     return {"message": "Project deleted successfully"}

