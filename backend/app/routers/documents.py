from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path
import os
import uuid
import json
import redis
import shutil

from app.database import get_db
from app.models import Document, Project, User, APIInterface
from app.routers.auth import get_current_user_optional
from app.services.enhanced_document_parser import EnhancedDocumentParser
from app.services.vector_service import VectorService
from app.celery_tasks import parse_document_task, delete_document_task
from app.config import settings

# Redis连接
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    encoding='utf-8'
)

router = APIRouter()
document_parser = EnhancedDocumentParser()

def get_vector_service():
    """获取向量服务实例（延迟初始化）"""
    return VectorService()


@router.post("/upload")
async def upload_document(
    file: Optional[UploadFile] = File(None),
    swagger_url: Optional[str] = Query(None, description="在线Swagger文档URL"),
    project_id: int = Query(...),
    is_few_shot: bool = Query(False, description="是否标记为接口测试参考用例"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """上传文档（支持文件上传或在线Swagger URL）"""
    # 验证项目（无需登录时允许所有项目）
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 处理在线Swagger URL
    if swagger_url:
        if not (swagger_url.startswith('http://') or swagger_url.startswith('https://')):
            raise HTTPException(status_code=400, detail="无效的URL格式")
        
        # 创建临时文件路径标记（使用URL作为文件路径，解析器会识别）
        file_id = str(uuid.uuid4())
        file_path = swagger_url  # 直接使用URL作为路径
        file_ext = 'swagger'
        filename = f"swagger_{file_id}.json"
        file_size = 0  # URL文件大小未知
        
        # 创建文档记录
        document = Document(
            project_id=project_id,
            filename=filename,
            file_type=file_ext,
            file_path=str(file_path),  # 存储URL
            file_size=file_size,
            status="uploaded"
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # 使用Celery异步解析文档
        try:
            task = parse_document_task.delay(
                document_id=document.id,
                file_path=str(file_path),  # 传递URL
                file_type=file_ext,
                is_few_shot=is_few_shot  # 传递few-shot标记
            )
            document.status = "parsing"
            document.parse_result = json.dumps({
                "task_id": task.id,
                "is_few_shot_example": is_few_shot
            }, ensure_ascii=False)
            db.commit()
            
            # 清除文档列表缓存（清除所有相关的缓存键）
            try:
                from app.services.cache_service import cache_service
                # 清除所有可能的缓存键
                cache_service.invalidate_cache(f"documents:{project_id}*")
            except Exception as e:
                print(f"清除文档列表缓存失败: {e}")
            
            return {
                "message": "Swagger URL添加成功，正在异步解析中",
                "document_id": document.id,
                "task_id": task.id,
                "status": "parsing"
            }
        except Exception as e:
            document.status = "error"
            db.commit()
            raise HTTPException(status_code=500, detail=f"文档解析任务启动失败: {str(e)}")
    
    # 处理文件上传
    if not file:
        raise HTTPException(status_code=400, detail="请上传文件或提供Swagger URL")
    
    # 检查文件名
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    
    # 获取文件扩展名
    filename = file.filename
    file_path_obj = Path(filename)
    file_ext = file_path_obj.suffix
    
    # 处理没有扩展名的情况
    if not file_ext or len(file_ext) <= 1:
        file_ext = ""
    else:
        file_ext = file_ext[1:].lower()  # 去掉点号并转为小写
    
    # 检查文件名中是否包含特定关键词，用于识别Postman、Apifox和Swagger文件
    filename_lower = filename.lower()
    
    # 根据文件名特征识别文件类型
    if 'postman' in filename_lower or filename_lower.endswith('.postman_collection.json'):
        file_ext = 'postman'
    elif 'apifox' in filename_lower:
        file_ext = 'apifox'
    elif 'swagger' in filename_lower or 'openapi' in filename_lower:
        file_ext = 'swagger'
    elif 'ks_all_interface' in filename_lower or 'all_interface' in filename_lower:
        # 专门识别ks_all_interface.json文件
        file_ext = 'json'
    elif file_ext in ['json', 'yaml', 'yml']:
        # JSON/YAML文件可能是Swagger，先默认识别，解析时会自动判断
        # 如果文件名包含swagger/openapi，则识别为swagger
        if 'swagger' in filename_lower or 'openapi' in filename_lower:
            file_ext = 'swagger'
    elif not file_ext:
        # 如果没有扩展名，尝试根据内容类型判断
        content_type = file.content_type or ""
        if 'json' in content_type:
            file_ext = 'json'
        elif 'yaml' in content_type or 'yml' in content_type:
            file_ext = 'yaml'
        elif 'pdf' in content_type:
            file_ext = 'pdf'
        elif 'word' in content_type or 'document' in content_type:
            file_ext = 'docx'
        elif 'excel' in content_type or 'spreadsheet' in content_type:
            file_ext = 'xlsx'
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"无法识别文件格式。文件名: {filename}, 内容类型: {content_type}. 请确保文件有正确的扩展名。"
            )
    
    if not file_ext or file_ext not in document_parser.supported_formats:
        raise HTTPException(
            status_code=400, 
            detail=f"不支持的文件格式: {file_ext or '未知格式'}. 支持格式: {', '.join(sorted(document_parser.supported_formats))}"
        )
    
    # 创建上传目录
    upload_dir = Path(settings.UPLOAD_DIR) / str(project_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成唯一文件名
    file_id = str(uuid.uuid4())
    file_path = upload_dir / f"{file_id}.{file_ext}"
    
    # 保存文件
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # 创建文档记录
    document = Document(
        project_id=project_id,
        filename=file.filename,
        file_type=file_ext,
        file_path=str(file_path),
        file_size=len(content),
        status="uploaded"
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    
    # 使用Celery异步解析文档
    try:
        # 触发Celery异步任务
        task = parse_document_task.delay(
            document_id=document.id,
            file_path=str(file_path),
            file_type=file_ext,
            is_few_shot=is_few_shot  # 传递few-shot标记
        )
        
        # 更新文档状态为解析中
        document.status = "parsing"
        document.parse_result = json.dumps({
            "task_id": task.id,
            "is_few_shot_example": is_few_shot
        }, ensure_ascii=False)
        db.commit()
        
        # 清除文档列表缓存，确保新上传的文档能立即显示（清除所有相关的缓存键）
        try:
            from app.services.cache_service import cache_service
            # 清除所有可能的缓存键
            cache_service.invalidate_cache(f"documents:{project_id}*")
        except Exception as e:
            print(f"清除文档列表缓存失败: {e}")
        
        return {
            "message": "文档上传成功，正在异步解析中",
            "document_id": document.id,
            "task_id": task.id,
            "status": "parsing"
        }
    except Exception as e:
        document.status = "error"
        db.commit()
        raise HTTPException(status_code=500, detail=f"文档解析任务启动失败: {str(e)}")


@router.get("/")
async def list_documents(
    project_id: int = Query(..., description="项目ID"),
    is_few_shot: Optional[bool] = Query(None, description="是否只查询few-shot文件"),
    page: int = Query(1, ge=1, description="页码（从1开始）"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量（1-100）"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取文档列表（支持分页，优先从Redis读取缓存）"""
    from app.services.cache_service import cache_service
    
    # 定义数据获取函数（当缓存缺失时调用）
    def fetch_all_documents():
        """从数据库获取所有文档"""
        query = db.query(Document).filter(
            Document.project_id == project_id,
            Document.status != "deleted"  # 过滤掉已删除的文档
        )
        
        documents = query.order_by(Document.created_at.desc()).all()
        
        # 转换为字典列表（用于JSON序列化和缓存）
        result = []
        for doc in documents:
            doc_is_few_shot = False
            if doc.parse_result:
                try:
                    parse_result = json.loads(doc.parse_result)
                    doc_is_few_shot = parse_result.get("is_few_shot_example", False)
                except:
                    pass
            
            # 应用few-shot过滤
            if is_few_shot is not None:
                if is_few_shot and not doc_is_few_shot:
                    continue
                if not is_few_shot and doc_is_few_shot:
                    continue
            
            result.append({
                "id": doc.id,
                "filename": doc.filename,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "is_few_shot": doc_is_few_shot
            })
        
        return result
    
    # 使用缓存服务获取分页数据
    # 注意：缓存键需要包含 is_few_shot 参数，确保不同查询使用不同的缓存
    cache_key = f"documents:{project_id}:is_few_shot_{is_few_shot if is_few_shot is not None else 'all'}"
    
    paginated_data, total_count, total_pages, current_page = cache_service.get_paginated_list(
        cache_key=cache_key,
        page=page,
        page_size=page_size,
        fetch_all_func=fetch_all_documents,
        cache_type='documents'
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


@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """删除文档，使用异步任务清理Redis和ChromaDB中的数据，并清除缓存"""
    from app.services.cache_service import cache_service
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.project_id.in_(
            db.query(Project.id).filter(Project.user_id == current_user.id)
        )
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # 记录project_id用于清除缓存
    project_id = document.project_id
    
    # 触发异步删除任务
    try:
        task = delete_document_task.delay(
            document_id=document.id,
            file_path=document.file_path
        )
        
        # 立即从数据库中标记为删除状态
        document.status = "deleted"
        db.commit()
        
        # 清除缓存（异步）
        cache_service.invalidate_cache(f"documents:{project_id}")
        
        return {
            "message": "文档删除中，请等待后台处理完成",
            "document_id": document.id,
            "task_id": task.id,
            "status": "deleting"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除文档失败: {str(e)}")


@router.post("/{document_id}/retry")
async def retry_parse_document(
    document_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """重新解析文档（用于解析失败时重试）"""
    document = db.query(Document).filter(Document.id == document_id).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # 检查文件是否存在（如果是URL，跳过文件存在性检查）
    is_url = document.file_path.startswith("http://") or document.file_path.startswith("https://")
    if not is_url and not os.path.exists(document.file_path):
        raise HTTPException(status_code=404, detail="文件不存在，无法重新解析")
    
    # 如果文档状态是parsing，先检查任务是否还在运行
    if document.status == "parsing":
        try:
            parse_result = json.loads(document.parse_result) if document.parse_result else {}
            if "task_id" in parse_result:
                from celery.result import AsyncResult
                from app.celery_app import celery_app
                task_result = AsyncResult(parse_result["task_id"], app=celery_app)
                if not task_result.ready():
                    # 任务还在运行，先撤销它
                    celery_app.control.revoke(parse_result["task_id"], terminate=True)
                    print(f"[重新解析] 已撤销旧任务: {parse_result['task_id']}")
        except Exception as e:
            print(f"[重新解析] 检查旧任务状态失败: {e}")
    
    # 重新触发解析任务
    try:
        task = parse_document_task.delay(
            document_id=document.id,
            file_path=document.file_path,
            file_type=document.file_type
        )
        document.status = "parsing"
        document.parse_result = json.dumps({"task_id": task.id}, ensure_ascii=False)
        db.commit()
        
        return {
            "message": "已重新启动解析任务",
            "document_id": document.id,
            "task_id": task.id,
            "status": "parsing"
        }
    except Exception as e:
        document.status = "error"
        db.commit()
        raise HTTPException(status_code=500, detail=f"重新解析任务启动失败: {str(e)}")


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取文档解析状态"""
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.project_id.in_(
            db.query(Project.id).filter(Project.user_id == current_user.id)
        )
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    result = {
        "id": document.id,
        "filename": document.filename,
        "status": document.status,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }
    
    # 如果有任务ID，获取任务状态
    if document.parse_result:
        try:
            parse_result = json.loads(document.parse_result)
            if "task_id" in parse_result:
                from celery.result import AsyncResult
                from app.celery_app import celery_app
                
                task_result = AsyncResult(parse_result["task_id"], app=celery_app)
                result["task_status"] = task_result.state
                if task_result.ready():
                    if task_result.successful():
                        result["parse_result"] = task_result.result
                    else:
                        result["error"] = str(task_result.info)
        except:
            pass
    
    return result


@router.get("/{document_id}/parsed")
async def get_parsed_content(
    document_id: int,
    content_type: Optional[str] = Query(None, description="内容类型: text, tables, images, formulas, metadata, full"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """从Redis获取文档解析结果（按分类）"""
    # 验证文档权限
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.project_id.in_(
            db.query(Project.id).filter(Project.user_id == current_user.id)
        )
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # 使用统一的fileid格式：file:{fileid}
    fileid = document_id
    redis_key_prefix = f"file:{fileid}"
    
    try:
        if content_type:
            # 获取特定类型的内容
            key = f"{redis_key_prefix}:{content_type}"
            data = redis_client.get(key)
            
            if data:
                return {
                    "document_id": document_id,
                    "fileid": fileid,
                    "content_type": content_type,
                    "data": json.loads(data)
                }
            else:
                raise HTTPException(status_code=404, detail=f"{content_type}内容不存在")
        else:
            # 获取所有分类的内容
            result = {
                "document_id": document_id,
                "fileid": fileid,
                "filename": document.filename,
                "content_types": {}
            }
            
            # 先获取解析信息
            info_key = f"{redis_key_prefix}:info"
            info_data = redis_client.get(info_key)
            if info_data:
                result["parse_info"] = json.loads(info_data)
            
            # 获取所有分类
            content_types = ["text", "tables", "images", "formulas", "metadata", "interfaces", "full"]
            for ct in content_types:
                key = f"{redis_key_prefix}:{ct}"
                data = redis_client.get(key)
                if data:
                    result["content_types"][ct] = json.loads(data)
            
            return result
            
    except redis.RedisError as e:
        raise HTTPException(status_code=500, detail=f"Redis连接失败: {str(e)}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"数据解析失败: {str(e)}")


@router.post("/import-test-env")
async def import_test_environment_file(
    file_url: str = Query(..., description="测试环境文件URL，例如：http://example.com/1.json"),
    project_id: int = Query(..., description="项目ID"),
    environment_name: str = Query("国内测试环境", description="环境名称"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    导入测试环境JSON文件（如1.json），解析接口信息并存储到数据库、ChromaDB和Redis
    该文件将作为few-shot示例，用于指导deepseek进行依赖分析和测试用例生成
    """
    import requests
    import tempfile
    from datetime import datetime
    
    try:
        # 验证项目
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # 下载文件
        response = requests.get(file_url, timeout=30)
        response.raise_for_status()
        
        # 保存到临时文件
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.json') as tmp_file:
            tmp_file.write(response.content)
            tmp_file_path = tmp_file.name
        
        try:
            # 解析JSON文件
            parsed_data = await document_parser.parse(tmp_file_path, 'json')
            
            # 提取接口信息
            api_interfaces = document_parser.extract_api_interfaces(parsed_data)
            
            if not api_interfaces:
                raise HTTPException(status_code=400, detail="文件中未找到接口信息")
            
            # 创建文档记录
            filename = file_url.split('/')[-1] or "1.json"
            document = Document(
                project_id=project_id,
                filename=filename,
                file_type='json',
                file_path=tmp_file_path,  # 临时使用，稍后移动
                file_size=len(response.content),
                status="parsing",
                parse_result=json.dumps({
                    "environment": environment_name,
                    "source_url": file_url,
                    "is_few_shot_example": True
                }, ensure_ascii=False)
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            
            # 保存文件到uploads目录（而不是临时文件，避免被删除）
            uploads_dir = Path("/app/uploads")
            uploads_dir.mkdir(exist_ok=True)
            final_file_path = uploads_dir / f"{document.id}_{filename}"
            shutil.move(tmp_file_path, str(final_file_path))
            
            # 更新文件路径
            document.file_path = str(final_file_path)
            db.commit()
            
            # 存储接口到数据库
            created_interfaces = []
            for iface_data in api_interfaces:
                # 检查是否已存在
                existing = db.query(APIInterface).filter(
                    APIInterface.project_id == project_id,
                    APIInterface.url == iface_data.get("url", ""),
                    APIInterface.method == iface_data.get("method", "GET")
                ).first()
                
                if not existing:
                    # 截断过长的名称和描述
                    interface_name = iface_data.get("name", "")[:200] if iface_data.get("name") else ""
                    interface_description = iface_data.get("description", "")[:500] if iface_data.get("description") else ""
                    db_interface = APIInterface(
                        project_id=project_id,
                        name=interface_name,
                        method=iface_data.get("method", "GET"),
                        url=iface_data.get("url", ""),
                        description=interface_description,
                        headers=json.dumps(iface_data.get("headers", {}), ensure_ascii=False) if iface_data.get("headers") else None,
                        params=json.dumps(iface_data.get("params", {}), ensure_ascii=False) if iface_data.get("params") else None,
                        body=json.dumps(iface_data.get("request_body", iface_data.get("body", {})), ensure_ascii=False) if iface_data.get("request_body") or iface_data.get("body") else None,
                        response_schema=json.dumps(iface_data.get("response_schema", {}), ensure_ascii=False) if iface_data.get("response_schema") else None
                    )
                    db.add(db_interface)
                    created_interfaces.append(db_interface)
            
            db.commit()
            
            # 存储到Redis（作为few-shot示例）
            fileid = document.id
            redis_key_prefix = f"file:{fileid}"
            
            # 存储完整解析结果
            parse_info = {
                "document_id": document.id,
                "file_type": "json",
                "environment": environment_name,
                "source_url": file_url,
                "parse_time": datetime.now().isoformat(),
                "status": "parsed",
                "is_few_shot_example": True,
                "total_interfaces": len(api_interfaces),
                "interfaces": api_interfaces
            }
            
            redis_client.set(
                f"{redis_key_prefix}:info",
                json.dumps(parse_info, ensure_ascii=False),
                ex=86400 * 365  # 1年过期
            )
            
            # 存储接口信息（用于few-shot）
            redis_client.set(
                f"{redis_key_prefix}:interfaces",
                json.dumps(api_interfaces, ensure_ascii=False),
                ex=86400 * 365
            )
            
            # 存储完整数据
            full_result = {
                **parsed_data,
                "document_id": document.id,
                "fileid": fileid,
                "environment": environment_name,
                "is_few_shot_example": True,
                "parse_time": parse_info["parse_time"]
            }
            redis_client.set(
                f"{redis_key_prefix}:full",
                json.dumps(full_result, ensure_ascii=False),
                ex=86400 * 365
            )
            
            # 标记为few-shot示例
            few_shot_key = f"few_shot:project:{project_id}:environment:{environment_name}"
            redis_client.set(
                few_shot_key,
                json.dumps({
                    "document_id": document.id,
                    "fileid": fileid,
                    "environment": environment_name,
                    "interfaces_count": len(api_interfaces),
                    "created_at": datetime.now().isoformat()
                }, ensure_ascii=False),
                ex=86400 * 365
            )
            
            # 存储到ChromaDB
            try:
                vector_service = get_vector_service()
                await vector_service.add_classified_content(document.id, parsed_data)
            except Exception as e:
                print(f"ChromaDB存储失败（不影响主流程）: {e}")
            
            return {
                "message": f"测试环境文件导入成功，已存储到数据库、ChromaDB和Redis",
                "document_id": document.id,
                "environment": environment_name,
                "total_interfaces": len(api_interfaces),
                "created_interfaces": len(created_interfaces),
                "is_few_shot_example": True,
                "few_shot_key": few_shot_key
            }
            
        finally:
            # 清理临时文件
            if os.path.exists(tmp_file_path):
                try:
                    os.remove(tmp_file_path)
                except:
                    pass
                    
    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=f"文件下载失败: {str(e)}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")

