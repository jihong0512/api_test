from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import TestEnvironment, Project, User
from app.routers.auth import get_current_user_optional

router = APIRouter()


class TestEnvironmentCreate(BaseModel):
    name: str
    env_type: str  # test_cn, test_overseas, gray_cn, gray_overseas
    base_url: str  # IP:port 或域名
    login_username: Optional[str] = None
    login_password: Optional[str] = None
    xjid: Optional[str] = "30110"  # xjid字段，默认值为30110
    description: Optional[str] = None
    is_default: bool = False


class TestEnvironmentUpdate(BaseModel):
    name: Optional[str] = None
    env_type: Optional[str] = None
    base_url: Optional[str] = None
    login_username: Optional[str] = None
    login_password: Optional[str] = None
    xjid: Optional[str] = None  # xjid字段
    description: Optional[str] = None
    is_default: Optional[bool] = None


@router.post("/")
async def create_environment(
    project_id: int,
    env: TestEnvironmentCreate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """创建测试环境"""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 如果设置为默认，取消其他默认环境
    if env.is_default:
        db.query(TestEnvironment).filter(
            TestEnvironment.project_id == project_id,
            TestEnvironment.is_default == True
        ).update({"is_default": False})
    
    db_env = TestEnvironment(
        project_id=project_id,
        name=env.name,
        env_type=env.env_type,
        base_url=env.base_url,
        login_username=env.login_username,
        login_password=env.login_password,
        xjid=env.xjid or "30110",  # 默认值为30110
        description=env.description,
        is_default=env.is_default
    )
    db.add(db_env)
    db.commit()
    db.refresh(db_env)
    return db_env


@router.get("/")
async def list_environments(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试环境列表（无需登录）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    environments = db.query(TestEnvironment).filter(
        TestEnvironment.project_id == project_id
    ).order_by(TestEnvironment.is_default.desc(), TestEnvironment.created_at.desc()).all()
    
    return environments


@router.get("/{env_id}")
async def get_environment(
    env_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试环境详情"""
    env = db.query(TestEnvironment).filter(TestEnvironment.id == env_id).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == env.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    return env


@router.put("/{env_id}")
async def update_environment(
    env_id: int,
    env_update: TestEnvironmentUpdate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """更新测试环境"""
    env = db.query(TestEnvironment).filter(TestEnvironment.id == env_id).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == env.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    # 如果设置为默认，取消其他默认环境
    if env_update.is_default is True:
        db.query(TestEnvironment).filter(
            TestEnvironment.project_id == env.project_id,
            TestEnvironment.is_default == True,
            TestEnvironment.id != env_id
        ).update({"is_default": False})
    
    # 更新字段
    if env_update.name is not None:
        env.name = env_update.name
    if env_update.env_type is not None:
        env.env_type = env_update.env_type
    if env_update.base_url is not None:
        env.base_url = env_update.base_url
    if env_update.login_username is not None:
        env.login_username = env_update.login_username
    if env_update.login_password is not None:
        env.login_password = env_update.login_password
    if env_update.xjid is not None:
        env.xjid = env_update.xjid
    if env_update.description is not None:
        env.description = env_update.description
    if env_update.is_default is not None:
        env.is_default = env_update.is_default
    
    db.commit()
    db.refresh(env)
    return env


@router.delete("/{env_id}")
async def delete_environment(
    env_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """删除测试环境"""
    env = db.query(TestEnvironment).filter(TestEnvironment.id == env_id).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == env.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    db.delete(env)
    db.commit()
    return {"message": "测试环境已删除"}


@router.post("/{env_id}/set-current")
async def set_current_environment(
    env_id: int,
    project_id: int = Query(...),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """设置当前使用的测试环境（快捷切换）"""
    # 验证项目权限
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 验证环境属于该项目
    env = db.query(TestEnvironment).filter(
        TestEnvironment.id == env_id,
        TestEnvironment.project_id == project_id
    ).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    
    # 设置为默认环境（这样就会成为当前使用的环境）
    db.query(TestEnvironment).filter(
        TestEnvironment.project_id == project_id,
        TestEnvironment.is_default == True,
        TestEnvironment.id != env_id
    ).update({"is_default": False})
    
    env.is_default = True
    db.commit()
    db.refresh(env)
    
    return {
        "message": f"已切换到环境: {env.name}",
        "environment": env
    }




