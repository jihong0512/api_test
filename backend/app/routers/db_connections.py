from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import DBConnection, Project, User, TableMetadata, ColumnMetadata, TableRelationship
from app.routers.auth import get_current_user_optional
from app.services.db_service import DatabaseService
from app.services.metadata_service import DatabaseMetadataManager
from app.services.ner_service import KnowledgeGraphEnricher
from app.celery_tasks import analyze_database_metadata_task, extract_knowledge_graph_task
from celery.result import AsyncResult
from app.celery_app import celery_app

router = APIRouter()
db_service = DatabaseService()


class DBConnectionCreate(BaseModel):
    db_type: str
    host: str
    port: int
    database_name: str
    username: str
    password: str


class DBConnectionResponse(BaseModel):
    id: int
    project_id: int
    db_type: str
    host: str
    port: int
    database_name: str
    username: str  # 添加username字段，方便前端回填（但不包含password，出于安全考虑）
    status: str
    
    class Config:
        from_attributes = True


@router.post("/", response_model=DBConnectionResponse)
async def create_db_connection(
    connection: DBConnectionCreate,
    project_id: int = Query(...),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """创建数据库连接"""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 测试连接
    test_result = db_service.test_connection(
        connection.db_type,
        connection.host,
        connection.port,
        connection.database_name,
        connection.username,
        connection.password
    )
    
    if not test_result["success"]:
        error_message = test_result.get("message", "连接失败")
        # 简化错误信息，提取关键部分
        if "Lost connection" in error_message:
            error_message = "无法连接到数据库服务器，请检查网络连接和服务器地址"
        elif "Access denied" in error_message or "1045" in error_message:
            error_message = "数据库认证失败，请检查用户名和密码"
        elif "Unknown database" in error_message or "1049" in error_message:
            error_message = "数据库不存在，请检查数据库名称"
        raise HTTPException(status_code=400, detail=error_message)
    
    # 连接测试成功
    db_connection = DBConnection(
        project_id=project_id,
        db_type=connection.db_type,
        host=connection.host,
        port=connection.port,
        database_name=connection.database_name,
        username=connection.username,
        password=connection.password,
        status="pending"  # 初始状态为pending，等待元数据解析
    )
    db.add(db_connection)
    db.commit()
    db.refresh(db_connection)
    
    # 异步触发元数据解析（知识图谱提取会在元数据解析完成后自动触发）
    task_id = None
    try:
        metadata_task = analyze_database_metadata_task.delay(db_connection.id)
        task_id = metadata_task.id
    except Exception as e:
        # 任务触发失败不影响连接创建
        print(f"异步任务触发失败: {e}")
    
    # 返回连接信息和任务ID
    response_data = {
        "id": db_connection.id,
        "project_id": db_connection.project_id,
        "db_type": db_connection.db_type,
        "host": db_connection.host,
        "port": db_connection.port,
        "database_name": db_connection.database_name,
        "username": db_connection.username,  # 添加username字段，满足DBConnectionResponse模型要求
        "status": db_connection.status,
        "metadata_task_id": task_id  # 返回任务ID
    }
    return response_data


@router.post("/test")
async def test_db_connection(
    connection: DBConnectionCreate,
    current_user: User = Depends(get_current_user_optional)
):
    """测试数据库连接（不创建连接）"""
    try:
        # 测试连接
        test_result = db_service.test_connection(
            connection.db_type,
            connection.host,
            connection.port,
            connection.database_name,
            connection.username,
            connection.password
        )
        
        if not test_result.get("success", False):
            error_message = test_result.get("message", "连接失败")
            # 简化错误信息，提取关键部分
            if "Lost connection" in error_message:
                error_message = "无法连接到数据库服务器，请检查网络连接和服务器地址"
            elif "Access denied" in error_message or "1045" in error_message:
                error_message = "数据库认证失败，请检查用户名和密码"
            elif "Unknown database" in error_message or "1049" in error_message:
                error_message = "数据库不存在，请检查数据库名称"
            elif "timed out" in error_message or "timeout" in error_message.lower():
                error_message = "连接超时，请检查网络连接和数据库服务器是否可访问"
            raise HTTPException(status_code=400, detail=error_message)
        
        return {
            "success": True,
            "message": "连接测试成功",
            "version": test_result.get("version")
        }
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        # 捕获其他异常，返回友好的错误信息
        error_message = str(e)
        if "timed out" in error_message or "timeout" in error_message.lower():
            error_message = "连接超时，请检查网络连接和数据库服务器是否可访问"
        elif "could not translate host name" in error_message.lower():
            error_message = "无法解析主机名，请检查主机地址是否正确"
        raise HTTPException(status_code=500, detail=f"连接测试失败: {error_message}")


@router.post("/{connection_id}/analyze")
async def analyze_database(
    connection_id: int,
    include_data_features: bool = Query(True, description="是否包含数据特征分析"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """分析数据库：解析元数据、采样分析数据特征、构建知识图谱"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    try:
        engine = db_service.connect_database(
            connection.db_type,
            connection.host,
            connection.port,
            connection.database_name,
            connection.username,
            connection.password
        )
        
        # 分析数据库结构
        schema_info = db_service.analyze_database_schema(engine)
        
        # 提取并保存元数据到数据库
        metadata_manager = DatabaseMetadataManager(db)
        save_result = metadata_manager.extract_and_save_metadata(
            connection, engine, schema_info
        )
        
        # 分析并保存表关系
        relationships_result = metadata_manager.analyze_and_save_relationships(
            connection, engine, schema_info
        )
        
        # 分析数据特征（可选）
        data_features = {}
        if include_data_features:
            for table in schema_info["tables"][:10]:  # 限制分析前10个表，避免耗时过长
                try:
                    features = db_service.analyze_data_features(engine, table["name"])
                    data_features[table["name"]] = features
                except Exception as e:
                    print(f"分析表 {table['name']} 失败: {e}")
        
        # 获取业务上下文（从项目描述中）
        from app.models import Project
        project = db.query(Project).filter(Project.id == connection.project_id).first()
        business_context = project.description if project and project.description else None

        # 构建Neo4j知识图谱（包含数据特征）
        neo4j_success = False
        neo4j_error = None
        try:
            db_service.build_knowledge_graph(
                schema_info,
                connection.project_id,
                data_features if include_data_features else None,
                business_context
            )
            neo4j_success = True
        except Exception as e:
            neo4j_error = str(e)
            print(f"⚠️  构建Neo4j知识图谱失败: {neo4j_error}")
            print("💡 数据库元数据已保存到MySQL，但知识图谱功能不可用")

        # 生成Cypher文件
        cypher_content = None
        try:
            cypher_content = metadata_manager.generate_cypher_file(connection)
        except Exception as e:
            print(f"⚠️  生成Cypher文件失败: {e}")
        
        # NER和关系抽取（可选，处理前5个表的数据）
        ner_results = {}
        if include_data_features and neo4j_success:
            try:
                enricher = KnowledgeGraphEnricher(db_service, metadata_manager.metadata_service)
                # 限制处理前5个表，避免耗时过长
                for table in schema_info["tables"][:5]:
                    try:
                        ner_result = enricher.enrich_from_table_data(
                            engine, table["name"], limit=50, project_id=connection.project_id
                        )
                        ner_results[table["name"]] = {
                            "entities_count": len(ner_result.get("entities", [])),
                            "relationships_count": len(ner_result.get("relationships", [])),
                            "total_texts_processed": ner_result.get("total_texts_processed", 0)
                        }

                        # 生成实体关系的Cypher并追加到主文件
                        if cypher_content and (ner_result.get("entities") or ner_result.get("relationships")):
                            entity_cypher = enricher.generate_cypher_for_entities(
                                table["name"],
                                ner_result.get("entities", []),
                                ner_result.get("relationships", []),
                                connection.project_id
                            )
                            cypher_content += "\n\n" + entity_cypher
                    except Exception as e:
                        print(f"NER处理表 {table['name']} 失败: {e}")
            except Exception as e:
                print(f"⚠️  NER处理失败: {e}")

        response_data = {
            "message": "数据库分析完成" + ("（知识图谱功能不可用）" if not neo4j_success else ""),
            "schema": schema_info,
            "metadata_saved": {
                "tables": save_result["saved_tables"],
                "relationships": relationships_result["saved_relationships"]
            },
            "data_features": data_features,
            "tables_analyzed": len(data_features),
            "ner_results": ner_results,
            "cypher_file_content": cypher_content,
            "neo4j_available": neo4j_success
        }

        if neo4j_error:
            response_data["neo4j_error"] = neo4j_error
            response_data["warning"] = "Neo4j服务不可用，知识图谱功能暂时无法使用。数据库元数据已保存到MySQL。"

        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库分析失败: {str(e)}")


@router.post("/{connection_id}/sample-data")
async def sample_table_data(
    connection_id: int,
    table_name: str = Query(..., description="表名"),
    limit: int = Query(100, description="采样数量"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """采样表数据"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    try:
        engine = db_service.connect_database(
            connection.db_type,
            connection.host,
            connection.port,
            connection.database_name,
            connection.username,
            connection.password
        )
        
        sample_data = db_service.sample_data(engine, table_name, limit)
        return {
            "table_name": table_name,
            "sample_size": len(sample_data),
            "data": sample_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据采样失败: {str(e)}")


@router.post("/{connection_id}/analyze-features")
async def analyze_table_features(
    connection_id: int,
    table_name: str = Query(..., description="表名"),
    sample_size: int = Query(1000, description="采样大小"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """分析表的数据特征"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    try:
        engine = db_service.connect_database(
            connection.db_type,
            connection.host,
            connection.port,
            connection.database_name,
            connection.username,
            connection.password
        )
        
        features = db_service.analyze_data_features(engine, table_name, sample_size)
        return features
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"特征分析失败: {str(e)}")


@router.get("/", response_model=List[DBConnectionResponse])
async def list_db_connections(
    project_id: int = Query(...),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取数据库连接列表（无需登录）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    connections = db.query(DBConnection).filter(DBConnection.project_id == project_id).all()
    return connections


@router.get("/{connection_id}/graph-data")
async def get_knowledge_graph_data(
    connection_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取知识图谱数据（用于前端可视化）"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    try:
        # 传递connection_id，只获取该数据库连接的元数据
        graph_data = db_service.get_knowledge_graph_data(connection.project_id, connection_id=connection_id)
        return graph_data
    except Exception as e:
        # Neo4j连接失败时返回空数据，而不是500错误
        import traceback
        error_msg = str(e)
        print(f"获取知识图谱数据失败: {error_msg}")
        print(traceback.format_exc())
        
        # 返回空数据格式，前端可以显示空状态
        return {
            "nodes": [],
            "edges": [],
            "error": error_msg if "Neo4j" not in error_msg else "Neo4j连接失败，请检查配置"
        }


@router.post("/{connection_id}/analyze-metadata")
async def trigger_metadata_analysis(
    connection_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """触发数据库元数据解析任务（无需登录）"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # 检查项目是否存在（无需登录）
    project = db.query(Project).filter(Project.id == connection.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 触发异步任务
    task = analyze_database_metadata_task.delay(connection_id)
    
    return {
        "message": "元数据解析任务已启动",
        "task_id": task.id,
        "connection_id": connection_id
    }


@router.post("/{connection_id}/extract-knowledge-graph")
async def trigger_knowledge_graph_extraction(
    connection_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """触发知识图谱提取任务"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == connection.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # 触发异步任务
    task = extract_knowledge_graph_task.delay(connection_id)
    
    return {
        "message": "知识图谱提取任务已启动",
        "task_id": task.id,
        "connection_id": connection_id
    }


@router.get("/{connection_id}/task")
async def get_connection_task(
    connection_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取连接正在运行的任务ID"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == connection.project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # 从Redis查找正在运行的任务
    # 尝试从Celery的active任务中查找
    try:
        from celery import current_app
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active()
        
        if active_tasks:
            for worker, tasks in active_tasks.items():
                for task in tasks:
                    # 检查任务参数是否包含connection_id
                    task_args = task.get('args', [])
                    if task_args and len(task_args) > 0 and task_args[0] == connection_id:
                        if 'analyze_database_metadata_task' in task.get('name', ''):
                            return {
                                'task_id': task.get('id'),
                                'task_type': 'metadata',
                                'state': 'PROGRESS'
                            }
                        elif 'extract_knowledge_graph_task' in task.get('name', ''):
                            return {
                                'task_id': task.get('id'),
                                'task_type': 'graph',
                                'state': 'PROGRESS'
                            }
    except Exception as e:
        print(f"查找任务失败: {e}")
    
    # 如果没找到，返回null
    return {
        'task_id': None,
        'task_type': None,
        'state': None
    }


@router.get("/task/{task_id}/status")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user_optional)
):
    """获取Celery任务状态"""
    task_result = AsyncResult(task_id, app=celery_app)
    
    if task_result.state == 'PENDING':
        response = {
            'state': task_result.state,
            'status': '等待中',
            'progress': 0,
            'message': '任务等待执行'
        }
    elif task_result.state == 'PROGRESS':
        info = task_result.info or {}
        response = {
            'state': task_result.state,
            'status': '执行中',
            'progress': info.get('progress', 0),
            'message': info.get('message', '处理中...'),
            'meta': {
                'progress': info.get('progress', 0),
                'message': info.get('message', '处理中...'),
                'current_table': info.get('current_table', ''),
                'nodes': info.get('nodes', []),
                'total_tables': info.get('total_tables', 0),
                'processed_tables': info.get('processed_tables', 0)
            }
        }
    elif task_result.state == 'SUCCESS':
        result = task_result.result or {}
        info = task_result.info or {}
        response = {
            'state': task_result.state,
            'status': '完成',
            'progress': 100,
            'message': result.get('message', info.get('message', '任务完成')),
            'result': result,
            'meta': {
                'progress': 100,
                'message': result.get('message', '任务完成'),
                'nodes': result.get('nodes', info.get('nodes', [])),
                'total_tables': result.get('tables_count', info.get('total_tables', 0)),
                'processed_tables': result.get('tables_count', info.get('processed_tables', 0)),
                # 标记已完成，前端可根据 meta.status 或 state 直接显示“完成”
                'status': 'completed'
            }
        }
    else:
        # 失败或其他状态
        response = {
            'state': task_result.state,
            'status': '失败' if task_result.state == 'FAILURE' else task_result.state,
            'progress': 0,
            'message': str(task_result.info) if task_result.info else '任务执行失败'
        }
    
    return response


@router.post("/task/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user_optional)
):
    """取消/终止Celery任务"""
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        
        # 获取任务当前状态
        try:
            current_state = task_result.state
        except Exception as state_error:
            # 如果获取状态失败，尝试直接取消
            print(f"获取任务状态失败: {state_error}")
            current_state = None
        
        # 检查任务状态
        if current_state and current_state in ['SUCCESS', 'FAILURE', 'REVOKED']:
            return {
                "status": "already_finished",
                "message": f"任务已经完成或已终止，当前状态: {current_state}",
                "task_id": task_id,
                "state": current_state
            }
        
        # 尝试终止任务
        try:
            # 对于 PENDING 状态的任务，使用 revoke 但不发送 terminate 信号
            # 对于 PROGRESS 状态的任务，使用 terminate=True
            if current_state == 'PENDING':
                # PENDING 状态的任务还没有开始执行，只需要撤销即可
                celery_app.control.revoke(task_id, terminate=False)
            else:
                # PROGRESS 状态的任务正在执行，需要发送终止信号
                celery_app.control.revoke(task_id, terminate=True, signal='SIGTERM')
            
            # 等待一小段时间确保任务被终止
            import time
            time.sleep(0.5)
            
            # 再次检查状态
            try:
                final_state = task_result.state
            except:
                final_state = 'REVOKED'
            
            return {
                "status": "cancelled",
                "message": "任务已成功终止",
                "task_id": task_id,
                "state": final_state
            }
        except Exception as revoke_error:
            # 如果revoke失败，尝试使用abort
            print(f"revoke失败，尝试abort: {revoke_error}")
            try:
                celery_app.control.abort(task_id)
                return {
                    "status": "cancelled",
                    "message": "任务已终止（使用abort）",
                    "task_id": task_id
                }
            except Exception as abort_error:
                # 如果都失败了，至少返回一个响应
                print(f"abort也失败: {abort_error}")
                return {
                    "status": "partial_cancelled",
                    "message": f"任务终止请求已发送，但确认状态时出错: {str(abort_error)}",
                    "task_id": task_id
                }
        
    except Exception as e:
        import traceback
        error_detail = str(e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"终止任务失败: {error_detail}")
