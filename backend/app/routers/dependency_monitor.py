from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from app.database import get_db
from app.models import TestEnvironment, Project, User
from app.routers.auth import get_current_user_optional
from app.services.dependency_monitor import DependencyMonitor

router = APIRouter()


@router.get("/health/{environment_id}")
async def check_environment_health(
    environment_id: int,
    health_endpoint: Optional[str] = Query(None, description="健康检查端点"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """检查测试环境健康状态"""
    environment = db.query(TestEnvironment).filter(TestEnvironment.id == environment_id).first()
    if not environment:
        raise HTTPException(status_code=404, detail="Test environment not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == environment.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    monitor = DependencyMonitor(db)
    health_status = await monitor.check_service_health(
        environment.base_url,
        health_endpoint=health_endpoint
    )
    
    return health_status


@router.get("/monitor/{environment_id}")
async def monitor_environment(
    environment_id: int,
    health_endpoint: Optional[str] = Query(None, description="健康检查端点"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """监控测试环境（包含健康状态和统计信息）"""
    environment = db.query(TestEnvironment).filter(TestEnvironment.id == environment_id).first()
    if not environment:
        raise HTTPException(status_code=404, detail="Test environment not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == environment.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    monitor = DependencyMonitor(db)
    monitor_result = await monitor.monitor_environment(environment, health_endpoint)
    
    return monitor_result


@router.get("/monitor-all/{project_id}")
async def monitor_all_environments(
    project_id: int,
    health_endpoint: Optional[str] = Query(None, description="健康检查端点"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """监控项目的所有测试环境"""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    monitor = DependencyMonitor(db)
    results = await monitor.monitor_multiple_environments(project_id, health_endpoint)
    
    return {
        "project_id": project_id,
        "environments": results,
        "monitored_at": results[0]["monitored_at"] if results else None
    }


@router.get("/availability/{environment_id}")
async def get_service_availability(
    environment_id: int,
    days: int = Query(7, description="统计天数"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取服务可用性统计"""
    environment = db.query(TestEnvironment).filter(TestEnvironment.id == environment_id).first()
    if not environment:
        raise HTTPException(status_code=404, detail="Test environment not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == environment.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    monitor = DependencyMonitor(db)
    availability = monitor.get_service_availability(environment_id, days)
    
    return {
        "environment_id": environment_id,
        "environment_name": environment.name,
        **availability
    }


@router.get("/status")
async def get_dependency_status(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取依赖服务状态概览"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 如果提供了用户，检查权限（可选）
    if current_user:
        user_project = db.query(Project).filter(
            Project.id == project_id,
            Project.user_id == current_user.id
        ).first()
        if not user_project:
            # 如果用户没有权限，仍然返回所有项目的数据（因为系统已配置为无需登录）
            pass
    
    monitor = DependencyMonitor(db)
    
    # 获取所有环境
    environments = db.query(TestEnvironment).filter(
        TestEnvironment.project_id == project_id
    ).all()
    
    status_list = []
    for env in environments:
        # 快速健康检查
        health = await monitor.check_service_health(env.base_url)
        
        # 获取可用性统计
        availability = monitor.get_service_availability(env.id, days=1)
        
        status_list.append({
            "environment_id": env.id,
            "environment_name": env.name,
            "base_url": env.base_url,
            "health_status": health["status"],
            "availability_rate": availability.get("availability_rate", 0),
            "recent_requests": availability.get("total_requests", 0),
            "last_check": health.get("checked_at")
        })
    
    return {
        "project_id": project_id,
        "environments": status_list,
        "total_environments": len(status_list),
        "healthy_count": len([s for s in status_list if s["health_status"] == "healthy"]),
        "checked_at": status_list[0]["last_check"] if status_list else None
    }












