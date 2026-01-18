from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import json
import httpx
import re
import asyncio
from datetime import datetime

from app.database import get_db
from app.models import DocumentAPIInterface, Project, User, Document
from app.routers.auth import get_current_user_optional

router = APIRouter()


class DocumentInterfaceCreate(BaseModel):
    name: str
    method: str = "GET"
    url: str
    base_url: Optional[str] = None
    path: Optional[str] = None
    service: Optional[str] = None
    headers: Optional[dict] = None
    params: Optional[dict] = None
    request_body: Optional[dict] = None
    response_body: Optional[dict] = None
    response_schema: Optional[dict] = None
    status_code: int = 200
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    deprecated: bool = False


class DocumentInterfaceUpdate(BaseModel):
    name: Optional[str] = None
    method: Optional[str] = None
    url: Optional[str] = None
    base_url: Optional[str] = None
    path: Optional[str] = None
    service: Optional[str] = None
    headers: Optional[dict] = None
    params: Optional[dict] = None
    request_body: Optional[dict] = None
    response_body: Optional[dict] = None
    response_schema: Optional[dict] = None
    status_code: Optional[int] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    deprecated: Optional[bool] = None
    version: Optional[str] = None


class DocumentInterfaceResponse(BaseModel):
    id: int
    document_id: int
    project_id: int
    name: str
    method: str
    url: str
    base_url: Optional[str]
    path: Optional[str]
    service: Optional[str]
    headers: Optional[dict]
    params: Optional[dict]
    request_body: Optional[dict]
    response_body: Optional[dict]
    response_schema: Optional[dict]
    status_code: int
    description: Optional[str]
    tags: Optional[List[str]]
    deprecated: bool
    version: Optional[str]
    created_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class InterfaceDebugRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: Optional[dict] = None
    params: Optional[dict] = None
    body: Optional[dict] = None
    timeout: int = 30
    interface_id: Optional[int] = None  # 接口ID，用于保存响应体到数据库


class InterfaceDebugResponse(BaseModel):
    status_code: int
    headers: dict
    body: Optional[dict] = None
    text: Optional[str] = None
    error: Optional[str] = None
    elapsed_time: float


@router.get("/project/{project_id}", response_model=List[DocumentInterfaceResponse])
async def list_document_interfaces(
    project_id: int,
    document_id: Optional[int] = None,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取文档接口列表（无需登录）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    query = db.query(DocumentAPIInterface).filter(
        DocumentAPIInterface.project_id == project_id
    )
    
    if document_id:
        query = query.filter(DocumentAPIInterface.document_id == document_id)
    
    interfaces = query.order_by(DocumentAPIInterface.created_at.desc()).all()
    
    # 解析JSON字段
    result = []
    for iface in interfaces:
        try:
            # 安全解析JSON字段
            headers = None
            if iface.headers:
                try:
                    headers = json.loads(iface.headers)
                except:
                    headers = {}
            
            params = None
            if iface.params:
                try:
                    params = json.loads(iface.params)
                except:
                    params = {}
            
            request_body = None
            if iface.request_body:
                try:
                    request_body = json.loads(iface.request_body)
                except:
                    request_body = {}
            
            response_body = None
            if iface.response_body:
                try:
                    body_str = str(iface.response_body)
                    # 如果包含HTML标签，尝试提取JSON部分
                    if '<' in body_str and '>' in body_str:
                        # 查找最后一个{...}JSON部分（通常在HTML之后）
                        import re
                        json_match = re.search(r'\{.*\}', body_str, re.DOTALL)
                        if json_match:
                            body_str = json_match.group(0)
                    
                    # 尝试解析JSON
                    response_body = json.loads(body_str)
                    # 确保是字典类型
                    if not isinstance(response_body, dict):
                        response_body = {"raw": str(response_body)}
                except:
                    # 如果解析失败，可能是HTML或其他非JSON格式，存储为空字典
                    # 但为了满足Pydantic模型要求（dict类型），我们使用空字典
                    response_body = {}
            
            response_schema = None
            if iface.response_schema:
                try:
                    response_schema = json.loads(iface.response_schema)
                except:
                    response_schema = {}
            
            tags = None
            if iface.tags:
                try:
                    tags = json.loads(iface.tags)
                except:
                    tags = []
            
            iface_dict = {
                "id": iface.id,
                "document_id": iface.document_id,
                "project_id": iface.project_id,
                "name": iface.name,
                "method": iface.method,
                "url": iface.url,
                "base_url": iface.base_url,
                "path": iface.path,
                "service": iface.service,
                "headers": headers,
                "params": params,
                "request_body": request_body,
                "response_body": response_body,
                "response_schema": response_schema,
                "status_code": iface.status_code,
                "description": iface.description,
                "tags": tags,
                "deprecated": iface.deprecated,
                "version": iface.version,
                "created_at": iface.created_at.isoformat() if iface.created_at else None
            }
            result.append(iface_dict)
        except Exception as e:
            print(f"解析接口 {iface.id} 失败: {e}")
            continue
    
    return result


@router.get("/{interface_id}", response_model=DocumentInterfaceResponse)
async def get_document_interface(
    interface_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取单个文档接口详情（无需登录）"""
    interface = db.query(DocumentAPIInterface).filter(
        DocumentAPIInterface.id == interface_id
    ).first()
    
    if not interface:
        raise HTTPException(status_code=404, detail="Interface not found")
    
    # 安全解析JSON字段
    try:
        headers = None
        if interface.headers:
            try:
                headers = json.loads(interface.headers)
            except:
                headers = {}
        
        params = None
        if interface.params:
            try:
                params = json.loads(interface.params)
            except:
                params = {}
        
        request_body = None
        if interface.request_body:
            try:
                request_body = json.loads(interface.request_body)
            except:
                request_body = {}
        
        response_body = None
        if interface.response_body:
            try:
                body_str = str(interface.response_body)
                # 如果包含HTML标签，尝试提取JSON部分
                if '<' in body_str and '>' in body_str:
                    import re
                    json_match = re.search(r'\{.*\}', body_str, re.DOTALL)
                    if json_match:
                        body_str = json_match.group(0)
                
                response_body = json.loads(body_str)
                if not isinstance(response_body, dict):
                    response_body = {"raw": str(response_body)}
            except:
                response_body = {}
        
        response_headers = None
        if interface.response_headers:
            try:
                response_headers = json.loads(interface.response_headers)
            except:
                response_headers = {}
        
        response_schema = None
        if interface.response_schema:
            try:
                response_schema = json.loads(interface.response_schema)
            except:
                response_schema = {}
        
        tags = None
        if interface.tags:
            try:
                tags = json.loads(interface.tags)
            except:
                tags = []
    except Exception as e:
        print(f"解析接口 {interface.id} 失败: {e}")
        # 使用默认值
        headers = {}
        params = {}
        request_body = {}
        response_body = {}
        response_headers = {}
        response_schema = {}
        tags = []
    
    return {
        "id": interface.id,
        "document_id": interface.document_id,
        "project_id": interface.project_id,
        "name": interface.name,
        "method": interface.method,
        "url": interface.url,
        "base_url": interface.base_url,
        "path": interface.path,
        "service": interface.service,
        "headers": headers,
        "params": params,
        "request_body": request_body,
        "response_headers": response_headers,
        "response_body": response_body,
        "response_schema": response_schema,
        "status_code": interface.status_code,
        "description": interface.description,
        "tags": tags,
        "deprecated": interface.deprecated,
        "version": interface.version or "",
        "created_at": interface.created_at.isoformat() if interface.created_at else None
    }


@router.put("/{interface_id}", response_model=DocumentInterfaceResponse)
async def update_document_interface(
    interface_id: int,
    update_data: DocumentInterfaceUpdate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """更新文档接口（无需登录）"""
    interface = db.query(DocumentAPIInterface).filter(
        DocumentAPIInterface.id == interface_id
    ).first()
    
    if not interface:
        raise HTTPException(status_code=404, detail="Interface not found")
    
    # 更新字段
    update_dict = update_data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        if key in ["headers", "params", "request_body", "response_body", "response_headers", "response_schema", "tags"]:
            if value is not None:
                setattr(interface, key, json.dumps(value, ensure_ascii=False))
        else:
            setattr(interface, key, value)
    
    db.commit()
    db.refresh(interface)
    
    # 安全解析JSON字段
    try:
        headers = None
        if interface.headers:
            try:
                headers = json.loads(interface.headers)
            except:
                headers = {}
        
        params = None
        if interface.params:
            try:
                params = json.loads(interface.params)
            except:
                params = {}
        
        request_body = None
        if interface.request_body:
            try:
                request_body = json.loads(interface.request_body)
            except:
                request_body = {}
        
        response_body = None
        if interface.response_body:
            try:
                body_str = str(interface.response_body)
                # 如果包含HTML标签，尝试提取JSON部分
                if '<' in body_str and '>' in body_str:
                    import re
                    json_match = re.search(r'\{.*\}', body_str, re.DOTALL)
                    if json_match:
                        body_str = json_match.group(0)
                
                response_body = json.loads(body_str)
                if not isinstance(response_body, dict):
                    response_body = {"raw": str(response_body)}
            except:
                response_body = {}
        
        response_headers = None
        if interface.response_headers:
            try:
                response_headers = json.loads(interface.response_headers)
            except:
                response_headers = {}
        
        response_schema = None
        if interface.response_schema:
            try:
                response_schema = json.loads(interface.response_schema)
            except:
                response_schema = {}
        
        tags = None
        if interface.tags:
            try:
                tags = json.loads(interface.tags)
            except:
                tags = []
    except Exception as e:
        print(f"解析接口 {interface.id} 失败: {e}")
        # 使用默认值
        headers = {}
        params = {}
        request_body = {}
        response_body = {}
        response_headers = {}
        response_schema = {}
        tags = []
    
    return {
        "id": interface.id,
        "document_id": interface.document_id,
        "project_id": interface.project_id,
        "name": interface.name,
        "method": interface.method,
        "url": interface.url,
        "base_url": interface.base_url,
        "path": interface.path,
        "service": interface.service,
        "headers": headers,
        "params": params,
        "request_body": request_body,
        "response_headers": response_headers,
        "response_body": response_body,
        "response_schema": response_schema,
        "status_code": interface.status_code,
        "description": interface.description,
        "tags": tags,
        "deprecated": interface.deprecated,
        "version": interface.version or "",
        "created_at": interface.created_at.isoformat() if interface.created_at else None
    }


@router.delete("/{interface_id}")
async def delete_document_interface(
    interface_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """删除文档接口（无需登录），并同步删除Neo4j、Redis、ChromaDB中的相关数据"""
    interface = db.query(DocumentAPIInterface).filter(
        DocumentAPIInterface.id == interface_id
    ).first()
    
    if not interface:
        raise HTTPException(status_code=404, detail="Interface not found")
    
    project_id = interface.project_id
    
    # 删除MySQL中的数据
    db.delete(interface)
    db.commit()
    
    # 同步删除Neo4j中的接口节点和依赖关系
    try:
        from app.services.db_service import DatabaseService
        db_service = DatabaseService()
        session = db_service._get_neo4j_session()
        if session:
            with session as neo4j_session:
                # 删除该接口的节点及其所有依赖关系
                result = neo4j_session.run(
                    "MATCH (n:APIInterface {id: $interface_id, project_id: $project_id}) DETACH DELETE n RETURN count(n) as deleted",
                    interface_id=str(interface_id),
                    project_id=project_id
                )
                record = result.single()
                deleted_count = record['deleted'] if record else 0
                if deleted_count > 0:
                    print(f"已从Neo4j删除接口 {interface_id} 的节点和依赖关系（共{deleted_count}个节点）")
                else:
                    print(f"Neo4j中未找到接口 {interface_id} 的节点")
    except Exception as e:
        print(f"删除Neo4j数据失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 同步删除Redis中的依赖分析数据（由于Redis数据是按项目存储的，删除整个项目的缓存）
    try:
        import redis
        from app.config import settings
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            encoding='utf-8'
        )
        
        # 清除项目相关的Redis keys
        redis_patterns = [
            f"dependency_graph:{project_id}",
            f"interface_groups:{project_id}",
            f"interface_chains:{project_id}",
            f"project:{project_id}:*",
            f"dependency_analysis:project:{project_id}:*",
            f"few_shot:project:{project_id}:*",
            f"scenario_chains:project:{project_id}:*",
        ]
        
        total_keys = 0
        for pattern in redis_patterns:
            keys = redis_client.keys(pattern)
            if keys:
                redis_client.delete(*keys)
                total_keys += len(keys)
        
        if total_keys > 0:
            print(f"已清除Redis键: {total_keys} 个 (project_id: {project_id})")
    except Exception as e:
        print(f"清除Redis数据失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 同步删除ChromaDB中的向量数据
    try:
        from app.services.vector_service import VectorService
        vector_service = VectorService()
        deleted_count = vector_service.delete_interface_from_chromadb(project_id, str(interface_id))
        if deleted_count > 0:
            print(f"已从ChromaDB删除接口 {interface_id} 的向量数据（共{deleted_count}条）")
    except Exception as e:
        print(f"删除ChromaDB数据失败: {e}")
        import traceback
        traceback.print_exc()
    
    return {"message": "Interface deleted successfully"}


class BatchDeleteRequest(BaseModel):
    interface_ids: List[int]


@router.post("/batch-delete")
async def batch_delete_document_interfaces(
    request: BatchDeleteRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """批量删除文档接口（无需登录），并同步删除Neo4j、Redis、ChromaDB中的相关数据"""
    if not request.interface_ids:
        raise HTTPException(status_code=400, detail="interface_ids cannot be empty")
    
    # 查询所有要删除的接口
    interfaces = db.query(DocumentAPIInterface).filter(
        DocumentAPIInterface.id.in_(request.interface_ids)
    ).all()
    
    if not interfaces:
        raise HTTPException(status_code=404, detail="No interfaces found")
    
    # 获取项目ID（假设所有接口都属于同一个项目）
    project_ids = set(interface.project_id for interface in interfaces)
    if len(project_ids) > 1:
        print(f"警告：批量删除的接口属于多个项目: {project_ids}")
    
    interface_ids = [interface.id for interface in interfaces]
    
    # 删除MySQL中的数据
    deleted_count = 0
    for interface in interfaces:
        db.delete(interface)
        deleted_count += 1
    
    db.commit()
    
    # 同步删除Neo4j中的接口节点和依赖关系
    try:
        from app.services.db_service import DatabaseService
        db_service = DatabaseService()
        session = db_service._get_neo4j_session()
        if session:
            with session as neo4j_session:
                total_deleted = 0
                for interface in interfaces:
                    result = neo4j_session.run(
                        "MATCH (n:APIInterface {id: $interface_id, project_id: $project_id}) DETACH DELETE n RETURN count(n) as deleted",
                        interface_id=str(interface.id),
                        project_id=interface.project_id
                    )
                    record = result.single()
                    deleted_count_neo4j = record['deleted'] if record else 0
                    total_deleted += deleted_count_neo4j
                
                if total_deleted > 0:
                    print(f"已从Neo4j删除 {total_deleted} 个接口节点和依赖关系")
    except Exception as e:
        print(f"删除Neo4j数据失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 同步删除Redis中的依赖分析数据（清除所有相关项目的缓存）
    try:
        import redis
        from app.config import settings
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            encoding='utf-8'
        )
        
        total_keys = 0
        for project_id in project_ids:
            # 清除项目相关的Redis keys
            redis_patterns = [
                f"dependency_graph:{project_id}",
                f"interface_groups:{project_id}",
                f"interface_chains:{project_id}",
                f"project:{project_id}:*",
                f"dependency_analysis:project:{project_id}:*",
                f"few_shot:project:{project_id}:*",
                f"scenario_chains:project:{project_id}:*",
            ]
            
            for pattern in redis_patterns:
                keys = redis_client.keys(pattern)
                if keys:
                    redis_client.delete(*keys)
                    total_keys += len(keys)
        
        if total_keys > 0:
            print(f"已清除Redis键: {total_keys} 个")
    except Exception as e:
        print(f"清除Redis数据失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 同步删除ChromaDB中的向量数据
    try:
        from app.services.vector_service import VectorService
        vector_service = VectorService()
        total_deleted_chromadb = 0
        for interface in interfaces:
            deleted_count = vector_service.delete_interface_from_chromadb(interface.project_id, str(interface.id))
            total_deleted_chromadb += deleted_count
        
        if total_deleted_chromadb > 0:
            print(f"已从ChromaDB删除 {total_deleted_chromadb} 条向量数据")
    except Exception as e:
        print(f"删除ChromaDB数据失败: {e}")
        import traceback
        traceback.print_exc()
    
    return {
        "message": f"Successfully deleted {deleted_count} interface(s)",
        "deleted_count": deleted_count
    }


@router.post("/debug", response_model=InterfaceDebugResponse)
async def debug_interface(
    debug_request: InterfaceDebugRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """调试接口：发送HTTP请求并返回响应，如果提供了interface_id则保存响应体到数据库"""
    import time
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=debug_request.timeout) as client:
            method = debug_request.method.upper()
            headers = debug_request.headers or {}
            
            # 根据方法发送请求
            if method == "GET":
                response = await client.get(
                    debug_request.url,
                    headers=headers,
                    params=debug_request.params
                )
            elif method == "POST":
                response = await client.post(
                    debug_request.url,
                    headers=headers,
                    params=debug_request.params,
                    json=debug_request.body
                )
            elif method == "PUT":
                response = await client.put(
                    debug_request.url,
                    headers=headers,
                    params=debug_request.params,
                    json=debug_request.body
                )
            elif method == "DELETE":
                response = await client.delete(
                    debug_request.url,
                    headers=headers,
                    params=debug_request.params
                )
            elif method == "PATCH":
                response = await client.patch(
                    debug_request.url,
                    headers=headers,
                    params=debug_request.params,
                    json=debug_request.body
                )
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported method: {method}")
            
            elapsed_time = time.time() - start_time
            
            # 提取响应体中的JSON数据
            def extract_json_from_response(response_text: str) -> dict:
                """从响应体中提取JSON数据，如果没有JSON则返回{}"""
                if not response_text or not isinstance(response_text, str):
                    return {}
                
                # 去除首尾空白
                response_text = response_text.strip()
                
                # 尝试直接解析为JSON
                try:
                    parsed = json.loads(response_text)
                    if isinstance(parsed, dict):
                        return parsed
                    elif isinstance(parsed, list):
                        return {"data": parsed} if len(parsed) > 0 else {}
                    else:
                        return {"value": str(parsed)}
                except:
                    pass
                
                # 尝试从文本中提取JSON（使用更强大的正则表达式）
                # 方法1: 查找最外层的JSON对象 { ... }（支持嵌套）
                json_obj_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
                matches = re.finditer(json_obj_pattern, response_text, re.DOTALL)
                
                # 按长度降序排序，优先提取最长的JSON对象
                json_matches = []
                for match in matches:
                    try:
                        parsed = json.loads(match.group())
                        if isinstance(parsed, dict) and len(parsed) > 0:
                            json_matches.append((len(match.group()), parsed))
                    except:
                        continue
                
                if json_matches:
                    # 返回最长的有效JSON对象
                    json_matches.sort(reverse=True, key=lambda x: x[0])
                    return json_matches[0][1]
                
                # 方法2: 查找JSON数组 [ ... ]
                json_array_pattern = r'\[(?:[^\[\]]|(?:\[[^\[\]]*\]))*\]'
                matches = re.finditer(json_array_pattern, response_text, re.DOTALL)
                
                array_matches = []
                for match in matches:
                    try:
                        parsed = json.loads(match.group())
                        if isinstance(parsed, list) and len(parsed) > 0:
                            array_matches.append((len(match.group()), parsed))
                    except:
                        continue
                
                if array_matches:
                    array_matches.sort(reverse=True, key=lambda x: x[0])
                    return {"data": array_matches[0][1]}
                
                # 方法3: 尝试提取JSON字符串（可能在引号内）
                json_str_pattern = r'["\'](\{[^"\']*\})["\']'
                matches = re.finditer(json_str_pattern, response_text)
                for match in matches:
                    try:
                        parsed = json.loads(match.group(1))
                        if isinstance(parsed, dict) and len(parsed) > 0:
                            return parsed
                    except:
                        continue
                
                # 如果没有找到JSON，返回空字典
                return {}
            
            # 尝试解析JSON响应
            body = None
            text = None
            extracted_json = {}
            
            try:
                body = response.json()
                extracted_json = body if isinstance(body, dict) else {"data": body}
            except:
                text = response.text
                # 从响应文本中提取JSON
                extracted_json = extract_json_from_response(text)
            
            # 如果提供了interface_id且响应成功，保存响应体到数据库、Redis、ChromaDB
            if debug_request.interface_id and response.status_code >= 200 and response.status_code < 300:
                try:
                    interface = db.query(DocumentAPIInterface).filter(
                        DocumentAPIInterface.id == debug_request.interface_id
                    ).first()
                    
                    if interface:
                        # 保存提取的JSON数据到响应体（如果没有JSON数据则保存{}）
                        response_body_to_save = extracted_json if extracted_json else {}
                        interface.response_body = json.dumps(response_body_to_save, ensure_ascii=False)
                        interface.response_headers = json.dumps(dict(response.headers), ensure_ascii=False)
                        interface.status_code = response.status_code
                        db.commit()
                        
                        # 更新Redis缓存
                        try:
                            from app.config import settings
                            import redis
                            redis_client = redis.Redis(
                                host=settings.REDIS_HOST,
                                port=settings.REDIS_PORT,
                                password=settings.REDIS_PASSWORD,
                                db=0,
                                decode_responses=True,
                                encoding='utf-8'
                            )
                            
                            # 更新接口列表缓存
                            redis_key = f"file:{interface.document_id}:api_interfaces"
                            cached_data = redis_client.get(redis_key)
                            if cached_data:
                                interfaces_list = json.loads(cached_data)
                                for iface in interfaces_list:
                                    if iface.get('id') == interface.id:
                                        iface['response_body'] = json.dumps(response_body_to_save, ensure_ascii=False)
                                        iface['response_headers'] = json.dumps(dict(response.headers), ensure_ascii=False)
                                        iface['status_code'] = response.status_code
                                        break
                                redis_client.set(redis_key, json.dumps(interfaces_list, ensure_ascii=False), ex=86400 * 30)
                        except Exception as e:
                            print(f"更新Redis缓存失败: {e}")
                        
                        # 更新ChromaDB（如果有向量存储）
                        try:
                            from app.services.vector_service import VectorService
                            # 注意：ChromaDB主要用于文档向量存储，接口数据通常不存储在ChromaDB中
                            # 如果需要更新ChromaDB，可以在这里添加逻辑
                        except Exception as e:
                            print(f"更新ChromaDB失败（可能不需要）: {e}")
                        
                        # 触发接口依赖分析和场景用例集更新（异步任务）
                        try:
                            from app.celery_tasks import analyze_all_interfaces_task
                            # 异步触发接口依赖分析（analyze_all_interfaces_task接受project_id和可选的connection_id）
                            analyze_all_interfaces_task.delay(interface.project_id, None)
                            print(f"已触发项目 {interface.project_id} 的接口依赖分析任务")
                        except Exception as e:
                            print(f"触发接口依赖分析失败: {e}")
                            # 如果Celery任务调用失败，尝试直接调用API（异步方式）
                            try:
                                async def trigger_analysis():
                                    async with httpx.AsyncClient() as client:
                                        await client.post(
                                            f"http://localhost:8004/api/relations/analyze/{interface.project_id}",
                                            json={},
                                            timeout=5.0
                                        )
                                asyncio.create_task(trigger_analysis())
                            except Exception as trigger_error:
                                print(f"触发分析API调用失败: {trigger_error}")
                                pass
                            
                except Exception as e:
                    print(f"保存响应体到数据库失败: {e}")
                    import traceback
                    traceback.print_exc()
                    # 不抛出异常，继续返回响应
            
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": extracted_json if extracted_json else (body if body is not None else None),
                "text": text,
                "error": None,
                "elapsed_time": elapsed_time
            }
    except httpx.TimeoutException:
        elapsed_time = time.time() - start_time
        return {
            "status_code": 0,
            "headers": {},
            "body": None,
            "text": None,
            "error": "请求超时",
            "elapsed_time": elapsed_time
        }
    except Exception as e:
        elapsed_time = time.time() - start_time
        return {
            "status_code": 0,
            "headers": {},
            "body": None,
            "text": None,
            "error": str(e),
            "elapsed_time": elapsed_time
        }

