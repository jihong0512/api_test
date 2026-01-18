from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import json

from app.database import get_db
from app.models import APIInterface, Project, User
from app.routers.auth import get_current_user_optional
from app.services.cache_service import cache_service

router = APIRouter()


class APIInterfaceCreate(BaseModel):
    name: str
    method: str
    url: str
    description: Optional[str] = None
    headers: Optional[str] = None
    params: Optional[str] = None
    body: Optional[str] = None
    response_schema: Optional[str] = None


class APIInterfaceResponse(BaseModel):
    id: int
    project_id: int
    name: str
    method: str
    url: str
    description: Optional[str]
    
    class Config:
        from_attributes = True


@router.post("/", response_model=APIInterfaceResponse)
async def create_api_interface(
    project_id: int,
    api_interface: APIInterfaceCreate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """创建接口"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    db_interface = APIInterface(
        project_id=project_id,
        name=api_interface.name,
        method=api_interface.method,
        url=api_interface.url,
        description=api_interface.description,
        headers=api_interface.headers,
        params=api_interface.params,
        body=api_interface.body,
        response_schema=api_interface.response_schema
    )
    db.add(db_interface)
    db.commit()
    db.refresh(db_interface)
    
    # 清除缓存
    cache_service.invalidate_cache(f"api_interfaces:{project_id}*")
    
    return db_interface


@router.get("/")
async def list_api_interfaces(
    project_id: int,
    page: int = Query(1, ge=1, description="页码（从1开始）"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量（1-100）"),
    method: Optional[str] = Query(None, description="按HTTP方法筛选"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取接口列表（支持分页，优先从Redis读取缓存）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 定义数据获取函数（当缓存缺失时调用）
    def fetch_all_interfaces():
        """从数据库获取所有接口"""
        query = db.query(APIInterface).filter(APIInterface.project_id == project_id)
        
        # 应用SQL层过滤
        if method:
            query = query.filter(APIInterface.method == method.upper())
        
        interfaces = query.order_by(APIInterface.created_at.desc()).all()
        
        # 转换为字典列表（用于JSON序列化和缓存）
        result = []
        for iface in interfaces:
            result.append({
                "id": iface.id,
                "project_id": iface.project_id,
                "name": iface.name,
                "method": iface.method,
                "url": iface.url,
                "description": iface.description,
                "headers": iface.headers,
                "params": iface.params,
                "body": iface.body,
                "response_schema": iface.response_schema,
                "created_at": iface.created_at.isoformat() if iface.created_at else None,
                "updated_at": iface.updated_at.isoformat() if iface.updated_at else None
            })
        
        return result
    
    # 构建缓存键（包含所有过滤条件）
    cache_key = f"api_interfaces:{project_id}:{method or 'all'}"
    
    # 使用缓存服务获取分页数据
    paginated_data, total_count, total_pages, current_page = cache_service.get_paginated_list(
        cache_key=cache_key,
        page=page,
        page_size=page_size,
        fetch_all_func=fetch_all_interfaces,
        cache_type='api_interfaces'
    )
    
    return {
        "data": paginated_data,
        "pagination": {
            "page": current_page,
            "page_size": page_size,
            "total": total_count,
            "total_pages": total_pages
        }
    }


@router.get("/{interface_id}")
async def get_api_interface(
    interface_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取单个接口详情"""
    interface = db.query(APIInterface).filter(APIInterface.id == interface_id).first()
    if not interface:
        raise HTTPException(status_code=404, detail="Interface not found")
    
    return {
        "id": interface.id,
        "project_id": interface.project_id,
        "name": interface.name,
        "method": interface.method,
        "url": interface.url,
        "description": interface.description,
        "headers": interface.headers,
        "params": interface.params,
        "body": interface.body,
        "response_schema": interface.response_schema,
        "created_at": interface.created_at.isoformat() if interface.created_at else None,
        "updated_at": interface.updated_at.isoformat() if interface.updated_at else None
    }


@router.put("/{interface_id}")
async def update_api_interface(
    interface_id: int,
    api_interface: APIInterfaceCreate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """更新接口"""
    db_interface = db.query(APIInterface).filter(APIInterface.id == interface_id).first()
    if not db_interface:
        raise HTTPException(status_code=404, detail="Interface not found")
    
    db_interface.name = api_interface.name
    db_interface.method = api_interface.method
    db_interface.url = api_interface.url
    db_interface.description = api_interface.description
    db_interface.headers = api_interface.headers
    db_interface.params = api_interface.params
    db_interface.body = api_interface.body
    db_interface.response_schema = api_interface.response_schema
    
    db.commit()
    db.refresh(db_interface)
    
    # 清除缓存
    cache_service.invalidate_cache(f"api_interfaces:{db_interface.project_id}*")
    
    return {
        "id": db_interface.id,
        "project_id": db_interface.project_id,
        "name": db_interface.name,
        "method": db_interface.method,
        "url": db_interface.url,
        "description": db_interface.description,
        "headers": db_interface.headers,
        "params": db_interface.params,
        "body": db_interface.body,
        "response_schema": db_interface.response_schema,
        "created_at": db_interface.created_at.isoformat() if db_interface.created_at else None,
        "updated_at": db_interface.updated_at.isoformat() if db_interface.updated_at else None
    }


@router.delete("/{interface_id}")
async def delete_api_interface(
    interface_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """删除接口"""
    db_interface = db.query(APIInterface).filter(APIInterface.id == interface_id).first()
    if not db_interface:
        raise HTTPException(status_code=404, detail="Interface not found")
    
    project_id = db_interface.project_id
    
    db.delete(db_interface)
    db.commit()
    
    # 清除缓存
    cache_service.invalidate_cache(f"api_interfaces:{project_id}*")
    
    return {"message": "接口删除成功"}