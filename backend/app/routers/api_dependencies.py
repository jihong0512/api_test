from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json

from app.database import get_db
from app.models import APIInterface, Project, User, DBConnection
from app.routers.auth import get_current_user_optional
from app.services.dependency_analyzer import DependencyAnalyzer
from app.services.api_dependency_analyzer import APIDependencyAnalyzer
from app.services.optimized_dependency_analyzer import OptimizedDependencyAnalyzer
from app.celery_tasks import analyze_api_dependencies_task, analyze_all_interfaces_task
from app.celery_app import celery_app
from celery.result import AsyncResult
from app.models import Document, DocumentAPIInterface

router = APIRouter()


@router.get("/dependency-graph/{project_id}")
async def get_dependency_graph(
    project_id: int,
    connection_id: Optional[int] = Query(None, description="数据库连接ID"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取接口依赖关系图（无需登录）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取所有API接口
    api_interfaces = db.query(APIInterface).filter(
        APIInterface.project_id == project_id
    ).all()
    
    api_list = []
    for api in api_interfaces:
        # 解析URL获取base_url和path
        url = api.url if api.url else ""
        # 尝试从URL中提取base_url和path
        base_url = ""
        path = url
        try:
            if url.startswith("http://") or url.startswith("https://"):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                path = parsed.path
            else:
                # 如果不是完整URL，可能是相对路径，尝试提取域名和路径
                if "/" in url:
                    parts = url.split("/", 1)
                    if len(parts) > 1:
                        base_url = parts[0] if ":" in parts[0] else ""
                        path = "/" + parts[1] if len(parts) > 1 else url
        except:
            pass
        
        api_data = {
            "id": api.id,
            "name": api.name or path or url,
            "method": api.method,
            "url": url,
            "path": path,
            "base_url": base_url,
            "params": json.loads(api.params) if api.params else {},
            "request_body": json.loads(api.body) if api.body else {},
            "response_schema": json.loads(api.response_schema) if api.response_schema else {},
            "headers": json.loads(api.headers) if api.headers else {}
        }
        api_list.append(api_data)
    
    # 获取数据库连接
    if not connection_id:
        connection = db.query(DBConnection).filter(
            DBConnection.project_id == project_id
        ).first()
        if connection:
            connection_id = connection.id
    
    # 构建节点数据，确保包含名称和URL，并添加label字段
    def build_node_with_label(api):
        node_name = api.get("name", "")
        node_url = api.get("url", "")
        label = f"{node_name}\n{node_url}" if node_url else node_name
        return {
            "id": api["id"],
            "name": node_name,
            "url": node_url,
            "method": api.get("method", ""),
            "label": label
        }
    
    # 如果没有数据库连接，返回空图而不是错误
    if not connection_id:
        return {
            "project_id": project_id,
            "connection_id": None,
            "dependency_graph": {
                "nodes": [build_node_with_label(api) for api in api_list],
                "edges": []
            },
            "message": "No database connection found, showing API interfaces only"
        }
    
    # 分析依赖关系
    analyzer = DependencyAnalyzer(db)
    try:
        dependency_graph = analyzer.analyze_api_dependencies(
            api_list, connection_id, project_id
        )
        
        # 确保所有节点都包含URL和label
        if "nodes" in dependency_graph:
            for node in dependency_graph["nodes"]:
                if "label" not in node:
                    node_name = node.get("name", "")
                    node_url = node.get("url", "")
                    if not node_url:
                        # 尝试从api_list中查找对应的URL
                        api_match = next((api for api in api_list if str(api["id"]) == str(node["id"])), None)
                        if api_match:
                            node_url = api_match.get("url", "")
                    label = f"{node_name}\n{node_url}" if node_url else node_name
                    node["label"] = label
                    node["url"] = node_url
    except Exception as e:
        # 如果分析失败，返回空图而不是抛出异常
        return {
            "project_id": project_id,
            "connection_id": connection_id,
            "dependency_graph": {
                "nodes": [build_node_with_label(api) for api in api_list],
                "edges": []
            },
            "message": f"Failed to analyze dependencies: {str(e)}"
        }
    
    return {
        "project_id": project_id,
        "connection_id": connection_id,
        "dependency_graph": dependency_graph
    }


@router.get("/call-chains/{project_id}")
async def get_call_chains(
    project_id: int,
    connection_id: Optional[int] = Query(None, description="数据库连接ID"),
    source_api_id: Optional[int] = Query(None, description="起始接口ID"),
    target_api_id: Optional[int] = Query(None, description="目标接口ID"),
    max_length: int = Query(10, description="最大链长度"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取接口调用链路（从Neo4j或依赖分析结果中获取）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        # 优先从OptimizedDependencyAnalyzer获取依赖关系
        from app.services.optimized_dependency_analyzer import OptimizedDependencyAnalyzer
        analyzer = OptimizedDependencyAnalyzer(db)
        
        # 从Neo4j获取依赖关系
        neo4j_result = analyzer.get_dependencies_from_neo4j(project_id)
        nodes = neo4j_result.get('nodes', [])
        edges = neo4j_result.get('edges', [])
        
        if not nodes or not edges:
            # 如果Neo4j没有数据，尝试从DocumentAPIInterface获取数据并分析
            from app.models import DocumentAPIInterface
            interfaces_db = db.query(DocumentAPIInterface).filter(
                DocumentAPIInterface.project_id == project_id
    ).all()
    
            if not interfaces_db:
                return {
                    "project_id": project_id,
                    "call_chains": [],
                    "total": 0,
                    "message": "没有找到接口数据，请先在接口列表页面进行依赖分析"
                }
            
            # 构建接口列表
            interfaces = []
            for iface_db in interfaces_db:
                interfaces.append({
                    "id": str(iface_db.id),
                    "name": iface_db.name,
                    "method": iface_db.method,
                    "url": iface_db.url,
                    "path": iface_db.path or "",
                    "base_url": iface_db.base_url or "",
                    "description": iface_db.description or ""
                })
            
            # 如果有接口数据但Neo4j没有，提示用户先进行分析
            return {
                "project_id": project_id,
                "call_chains": [],
                "total": 0,
                "message": "请先在接口列表页面选择接口进行依赖分析，分析完成后即可查看调用链路"
            }
        
        # 构建调用链：从依赖关系中查找所有路径
        def build_call_chains(nodes, edges, max_depth=max_length):
            """从依赖关系构建调用链"""
            # 构建邻接表
            graph = {}
            node_map = {node['id']: node for node in nodes}
            
            for edge in edges:
                source = edge['source']
                target = edge['target']
                if source not in graph:
                    graph[source] = []
                graph[source].append(target)
            
            # 查找所有路径
            all_chains = []
            
            def dfs(current_node, path, visited):
                """深度优先搜索查找路径"""
                if len(path) > max_depth:
                    return
                
                # 如果路径长度>=2，保存为一条调用链
                if len(path) >= 2:
                    chain = {
                        "nodes": path.copy(),
                        "length": len(path),
                        "interfaces": [node_map.get(node_id, {}).get('name', node_id) for node_id in path]
                    }
                    all_chains.append(chain)
                
                # 继续搜索
                if current_node in graph:
                    for next_node in graph[current_node]:
                        if next_node not in visited:
                            visited.add(next_node)
                            path.append(next_node)
                            dfs(next_node, path, visited)
                            path.pop()
                            visited.remove(next_node)
            
            # 从每个节点开始搜索
            for start_node in graph.keys():
                dfs(start_node, [start_node], {start_node})
            
            # 去重（相同的路径只保留一次）
            unique_chains = []
            seen = set()
            for chain in all_chains:
                chain_key = tuple(chain['nodes'])
                if chain_key not in seen:
                    seen.add(chain_key)
                    unique_chains.append(chain)
            
            return unique_chains
        
        call_chains = build_call_chains(nodes, edges, max_length)
        
        # 过滤
        if source_api_id:
            call_chains = [c for c in call_chains if c["nodes"][0] == str(source_api_id)]
        
        if target_api_id:
            call_chains = [c for c in call_chains if c["nodes"][-1] == str(target_api_id)]
        
        # 转换为前端需要的格式
        formatted_chains = []
        for chain in call_chains:
            formatted_chain = {
                "nodes": chain["nodes"],
                "length": chain["length"],
                "interfaces": chain["interfaces"]
            }
            formatted_chains.append(formatted_chain)
        
        return {
            "project_id": project_id,
            "call_chains": formatted_chains,
            "total": len(formatted_chains)
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "project_id": project_id,
            "call_chains": [],
            "total": 0,
            "message": f"获取调用链失败: {str(e)}"
    }


@router.get("/api/{api_id}/dependencies")
async def get_api_dependencies(
    api_id: int,
    project_id: int,
    connection_id: Optional[int] = Query(None, description="数据库连接ID"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取单个接口的依赖关系"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取指定接口
    api_interface = db.query(APIInterface).filter(
        APIInterface.id == api_id,
        APIInterface.project_id == project_id
    ).first()
    
    if not api_interface:
        raise HTTPException(status_code=404, detail="API interface not found")
    
    # 获取所有接口
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
    
    # 查找指定接口的节点
    target_node = next(
        (n for n in dependency_graph["nodes"] if n["id"] == api_id),
        None
    )
    
    if not target_node:
        raise HTTPException(status_code=404, detail="API not found in dependency graph")
    
    # 查找所有依赖该接口的接口（反向依赖）
    dependents = []
    for node in dependency_graph["nodes"]:
        all_deps = node.get("data_flow_deps", []) + node.get("business_logic_deps", [])
        if any(dep.get("api_id") == api_id for dep in all_deps):
            dependents.append({
                "api_id": node["id"],
                "api_name": node["name"],
                "url": node["url"],
                "method": node["method"],
                "dependency": next(
                    (d for d in all_deps if d.get("api_id") == api_id),
                    None
                )
            })
    
    return {
        "api_id": api_id,
        "api_name": target_node["name"],
        "url": target_node["url"],
        "method": target_node["method"],
        "dependencies": {
            "data_flow": target_node.get("data_flow_deps", []),
            "business_logic": target_node.get("business_logic_deps", [])
        },
        "dependents": dependents,
        "summary": {
            "total_dependencies": len(target_node.get("data_flow_deps", [])) + len(target_node.get("business_logic_deps", [])),
            "total_dependents": len(dependents)
        }
    }




@router.post("/analyze/{project_id}")
async def analyze_all_interfaces(
    project_id: int,
    connection_id: Optional[int] = None,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    全局分析所有接口的依赖关系
    使用相似度分组、CRUD排序，使用deepseek分析并存储到Neo4j和Redis
    自动为同类型接口建立连接关系
    在分析开始前会清除该项目的Redis、ChromaDB、Neo4j相关数据
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 清除之前的相关数据（Redis、ChromaDB、Neo4j）
    try:
        import redis
        from app.config import settings
        from app.services.vector_service import VectorService
        from app.services.db_service import DatabaseService
        
        print(f"开始清除项目 {project_id} 的Redis、ChromaDB、Neo4j数据...")
        
        # 1. 清除Redis数据
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            encoding='utf-8'
        )
        
        # 清除项目相关的Redis keys
        redis_patterns = [
            f"project:{project_id}:*",
            f"dependency_analysis:project:{project_id}:*",
            f"few_shot:project:{project_id}:*",
            f"scenario_chains:project:{project_id}:*",
            f"dependency_graph:{project_id}",  # 依赖关系图数据
            f"interface_groups:{project_id}",  # 接口分组数据
            f"interface_chains:{project_id}",  # 接口依赖链数据
        ]
        
        for pattern in redis_patterns:
            keys = redis_client.keys(pattern)
            if keys:
                redis_client.delete(*keys)
                print(f"已清除Redis键: {len(keys)} 个 (pattern: {pattern})")
        
        # 2. 清除ChromaDB数据
        try:
            vector_service = VectorService()
            vector_service.delete_documents(document_id=project_id)
            print(f"已清除ChromaDB数据 (document_id: {project_id})")
        except Exception as e:
            print(f"清除ChromaDB数据失败: {e}")
        
        # 3. 清除Neo4j数据
        try:
            db_service = DatabaseService()
            session = db_service._get_neo4j_session()
            with session as neo4j_session:
                # 删除该项目的所有接口节点和依赖关系
                result = neo4j_session.run(
                    "MATCH (n:APIInterface {project_id: $project_id}) DETACH DELETE n RETURN count(n) as deleted",
                    project_id=project_id
                )
                record = result.single()
                deleted_count = record['deleted'] if record else 0
                print(f"已清除Neo4j数据: {deleted_count} 个节点")
        except Exception as e:
            print(f"清除Neo4j数据失败: {e}")
        
        print(f"项目 {project_id} 的旧数据清除完成")
    except Exception as e:
        print(f"清除旧数据时发生错误: {e}")
        import traceback
        traceback.print_exc()
        # 不清除数据不是致命错误，继续执行分析
    
    # 获取所有接口（从DocumentAPIInterface表）
    interfaces_db = db.query(DocumentAPIInterface).filter(
        DocumentAPIInterface.project_id == project_id
    ).all()
    
    if not interfaces_db or len(interfaces_db) == 0:
        raise HTTPException(status_code=404, detail="未找到接口数据，请先上传文档并解析接口")
    
    # 获取数据库连接
    if not connection_id:
        connection = db.query(DBConnection).filter(
            DBConnection.project_id == project_id
        ).first()
        if connection:
            connection_id = connection.id
    
    # 构建接口数据列表
    api_list = []
    for iface_db in interfaces_db:
        try:
            # 安全解析JSON字段
            headers = {}
            if iface_db.headers:
                try:
                    headers = json.loads(iface_db.headers)
                except:
                    headers = {}
            
            params = {}
            if iface_db.params:
                try:
                    params = json.loads(iface_db.params)
                except:
                    params = {}
            
            request_body = {}
            if iface_db.request_body:
                try:
                    request_body = json.loads(iface_db.request_body)
                except:
                    request_body = {}
            
            response_body = {}
            if iface_db.response_body:
                try:
                    body_str = str(iface_db.response_body)
                    # 如果包含HTML标签，尝试提取JSON部分
                    if '<' in body_str and '>' in body_str:
                        import re
                        json_match = re.search(r'\{.*\}', body_str, re.DOTALL)
                        if json_match:
                            body_str = json_match.group(0)
                    response_body = json.loads(body_str)
                    if not isinstance(response_body, dict):
                        response_body = {"raw": str(response_body)}
                except Exception as e:
                    # 解析失败时，尝试保留原始字符串（如果非空）
                    body_str = str(iface_db.response_body).strip()
                    if body_str and body_str not in ['{}', 'null', 'None', '']:
                        # 如果原始字符串有内容，尝试作为字符串存储
                        response_body = {"raw": body_str}
                    else:
                        # 如果为空，保持为空字典，让验证逻辑使用response_schema
                        response_body = {}
            
            response_headers = {}
            if iface_db.response_headers:
                try:
                    response_headers = json.loads(iface_db.response_headers)
                except:
                    response_headers = {}
            
            response_schema = {}
            if iface_db.response_schema:
                try:
                    response_schema = json.loads(iface_db.response_schema)
                except:
                    response_schema = {}
            
            tags = []
            if iface_db.tags:
                try:
                    tags = json.loads(iface_db.tags)
                except:
                    tags = []
            
            api_data = {
                "id": iface_db.id,
                "interface_id": iface_db.id,
                "name": iface_db.name,
                "title": iface_db.name,  # 使用name作为title
                "method": iface_db.method,
                "url": iface_db.url,
                "path": iface_db.path or "",
                "base_url": iface_db.base_url or "",
                "service": iface_db.service or "",
                "headers": headers,
                "params": params,
                "request_body": request_body,
                "response_headers": response_headers,
                "response_body": response_body,
                "response_schema": response_schema,
                "status_code": iface_db.status_code,
                "description": iface_db.description or "",
                "tags": tags,
                "deprecated": iface_db.deprecated,
                "version": iface_db.version or "",
                "document_id": iface_db.document_id
            }
            api_list.append(api_data)
        except Exception as e:
            print(f"解析接口 {iface_db.id} 失败: {e}")
            continue
    
    if len(api_list) == 0:
        raise HTTPException(status_code=400, detail="没有有效的接口数据可分析")
    
    # 使用Celery异步任务进行分析
    try:
        # Celery的delay()方法不支持关键字参数，需要使用位置参数
        # 如果connection_id是None，只传递project_id
        if connection_id is not None:
            task = analyze_all_interfaces_task.delay(project_id, connection_id)
        else:
            task = analyze_all_interfaces_task.delay(project_id)
        
        return {
            "task_id": task.id,
            "project_id": project_id,
            "status": "pending",
            "message": "接口依赖分析任务已启动，正在后台处理..."
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"启动分析任务失败: {str(e)}")


@router.post("/analyze-selected/{project_id}")
async def analyze_selected_interfaces(
    project_id: int,
    interface_ids: List[int] = Body(..., description="要分析的接口ID列表"),
    connection_id: Optional[int] = Body(None, description="数据库连接ID（可选）"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    分析用户选择的接口依赖关系（已废弃，建议使用 /analyze/{project_id}）
    使用相似度分组、CRUD排序，使用deepseek分析并存储到Neo4j和Redis
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if not interface_ids or len(interface_ids) == 0:
        raise HTTPException(status_code=400, detail="请至少选择一个接口进行分析")
    
    # 从DocumentAPIInterface获取接口
    interfaces_db = db.query(DocumentAPIInterface).filter(
        DocumentAPIInterface.id.in_(interface_ids),
        DocumentAPIInterface.project_id == project_id
    ).all()
    
    if len(interfaces_db) != len(interface_ids):
        raise HTTPException(status_code=404, detail="部分接口不存在或不属于该项目")
    
    # 获取数据库连接
    if not connection_id:
        connection = db.query(DBConnection).filter(
            DBConnection.project_id == project_id
        ).first()
        if connection:
            connection_id = connection.id
    
    # 构建接口数据列表（与analyze_all_interfaces相同的逻辑）
    api_list = []
    for iface_db in interfaces_db:
        try:
            headers = {}
            if iface_db.headers:
                try:
                    headers = json.loads(iface_db.headers)
                except:
                    headers = {}
            
            params = {}
            if iface_db.params:
                try:
                    params = json.loads(iface_db.params)
                except:
                    params = {}
            
            request_body = {}
            if iface_db.request_body:
                try:
                    request_body = json.loads(iface_db.request_body)
                except:
                    request_body = {}
            
            response_body = {}
            if iface_db.response_body:
                try:
                    body_str = str(iface_db.response_body)
                    # 如果包含HTML标签，尝试提取JSON部分
                    if '<' in body_str and '>' in body_str:
                        import re
                        json_match = re.search(r'\{.*\}', body_str, re.DOTALL)
                        if json_match:
                            body_str = json_match.group(0)
                    response_body = json.loads(body_str)
                    if not isinstance(response_body, dict):
                        response_body = {"raw": str(response_body)}
                except Exception as e:
                    # 解析失败时，尝试保留原始字符串（如果非空）
                    body_str = str(iface_db.response_body).strip()
                    if body_str and body_str not in ['{}', 'null', 'None', '']:
                        # 如果原始字符串有内容，尝试作为字符串存储
                        response_body = {"raw": body_str}
                    else:
                        # 如果为空，保持为空字典，让验证逻辑使用response_schema
                        response_body = {}
            
            response_headers = {}
            if iface_db.response_headers:
                try:
                    response_headers = json.loads(iface_db.response_headers)
                except:
                    response_headers = {}
            
            response_schema = {}
            if iface_db.response_schema:
                try:
                    response_schema = json.loads(iface_db.response_schema)
                except:
                    response_schema = {}
            
            tags = []
            if iface_db.tags:
                try:
                    tags = json.loads(iface_db.tags)
                except:
                    tags = []
            
            api_data = {
                "id": iface_db.id,
                "interface_id": iface_db.id,
                "name": iface_db.name,
                "title": iface_db.name,
                "method": iface_db.method,
                "url": iface_db.url,
                "path": iface_db.path or "",
                "base_url": iface_db.base_url or "",
                "service": iface_db.service or "",
                "headers": headers,
                "params": params,
                "request_body": request_body,
                "response_headers": response_headers,
                "response_body": response_body,
                "response_schema": response_schema,
                "status_code": iface_db.status_code,
                "description": iface_db.description or "",
                "tags": tags,
                "deprecated": iface_db.deprecated,
                "version": iface_db.version or "",
                "document_id": iface_db.document_id
            }
            api_list.append(api_data)
        except Exception as e:
            print(f"解析接口 {iface_db.id} 失败: {e}")
            continue
    
    # 使用优化分析器进行分析
    try:
        analyzer = OptimizedDependencyAnalyzer(db)
        result = analyzer.analyze_interfaces(api_list, connection_id or 0, project_id)
        
        return {
            "project_id": project_id,
            "interface_ids": interface_ids,
            "connection_id": connection_id,
            "message": f"已成功分析 {len(interface_ids)} 个接口的依赖关系",
            "nodes_count": len(result.get('nodes', [])),
            "edges_count": len(result.get('edges', []))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.get("/task-status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    获取Celery任务状态
    """
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        
        if task_result.state == 'PENDING':
            response = {
                'task_id': task_id,
                'state': task_result.state,
                'status': 'pending',
                'progress': 0,
                'message': '任务等待执行...'
            }
        elif task_result.state == 'PROGRESS':
            # 处理进度信息，确保info是字典格式
            info = task_result.info
            if isinstance(info, dict):
                progress = info.get('progress', 0)
                message = info.get('message', '正在处理...')
            elif isinstance(info, tuple):
                # 如果info是元组格式 (current, total, message)
                progress = info[0] if len(info) > 0 else 0
                message = info[2] if len(info) > 2 else '正在处理...'
            else:
                progress = 0
                message = '正在处理...'
            
            response = {
                'task_id': task_id,
                'state': task_result.state,
                'status': 'processing',
                'progress': progress,
                'message': message
            }
        elif task_result.state == 'SUCCESS':
            result = task_result.result
            response = {
                'task_id': task_id,
                'state': task_result.state,
                'status': 'success',
                'progress': 100,
                'message': result.get('message', '分析完成'),
                'result': result
            }
        elif task_result.state == 'FAILURE':
            response = {
                'task_id': task_id,
                'state': task_result.state,
                'status': 'failure',
                'progress': 0,
                'message': str(task_result.info) if task_result.info else '任务执行失败'
            }
        else:
            response = {
                'task_id': task_id,
                'state': task_result.state,
                'status': 'unknown',
                'progress': 0,
                'message': f'任务状态: {task_result.state}'
            }
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务状态失败: {str(e)}")


@router.delete("/dependency-analysis/all")
async def delete_all_dependency_analysis(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    删除所有项目的接口依赖分析数据
    清除所有项目的Redis、ChromaDB、Neo4j中存储的依赖分析数据
    警告：此操作不可恢复，请谨慎使用
    """
    try:
        import redis
        from app.config import settings
        from app.services.vector_service import VectorService
        from app.services.db_service import DatabaseService
        
        deleted_counts = {
            "redis": 0,
            "chromadb": 0,
            "neo4j": 0,
            "projects": 0,
            "test_case_suites": 0
        }
        
        # 获取所有项目ID
        all_projects = db.query(Project).all()
        project_ids = [p.id for p in all_projects]
        deleted_counts["projects"] = len(project_ids)
        
        # 1. 清除Redis数据（所有项目）
        try:
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                encoding='utf-8'
            )
            
            # 清除所有项目相关的Redis keys
            redis_patterns = [
                "project:*",
                "dependency_analysis:project:*",
                "few_shot:project:*",
                "scenario_chains:project:*",
                "analysis:progress:*",
                "dependency_graph:*",  # 依赖关系图数据
                "interface_groups:*",  # 接口分组数据
                "interface_chains:*",  # 接口依赖链数据
            ]
            
            total_keys = 0
            for pattern in redis_patterns:
                keys = redis_client.keys(pattern)
                if keys:
                    redis_client.delete(*keys)
                    total_keys += len(keys)
            
            deleted_counts["redis"] = total_keys
            print(f"已清除Redis键: {total_keys} 个（所有项目）")
        except Exception as e:
            print(f"清除Redis数据失败: {e}")
        
        # 2. 清除ChromaDB数据（所有项目）
        try:
            vector_service = VectorService()
            # 清除所有项目的向量数据
            vector_service._ensure_chroma_connected()
            if hasattr(vector_service, 'collection') and vector_service.collection:
                # 获取所有文档并删除
                results = vector_service.collection.get()
                if results and results.get("ids"):
                    vector_service.collection.delete(ids=results["ids"])
                    deleted_counts["chromadb"] = len(results["ids"])
                    print(f"已清除ChromaDB数据: {len(results['ids'])} 条（所有项目）")
        except Exception as e:
            print(f"清除ChromaDB数据失败: {e}")
        
        # 3. 清除Neo4j数据（所有项目）
        try:
            db_service = DatabaseService()
            session = db_service._get_neo4j_session()
            with session as neo4j_session:
                # 删除所有接口节点和依赖关系
                result = neo4j_session.run(
                    "MATCH (n:APIInterface) DETACH DELETE n RETURN count(n) as deleted"
                )
                record = result.single()
                deleted_count = record['deleted'] if record else 0
                deleted_counts["neo4j"] = deleted_count
                print(f"已清除Neo4j数据: {deleted_count} 个节点（所有项目）")
        except Exception as e:
            print(f"清除Neo4j数据失败: {e}")
        
        # 4. 清除MySQL数据库中的场景用例集数据（所有项目）
        try:
            from app.models import TestCaseSuite
            deleted_suites = db.query(TestCaseSuite).delete(synchronize_session=False)
            db.commit()
            deleted_counts["test_case_suites"] = deleted_suites
            print(f"已清除MySQL场景用例集数据: {deleted_suites} 条（所有项目）")
        except Exception as e:
            db.rollback()
            print(f"清除MySQL场景用例集数据失败: {e}")
            deleted_counts["test_case_suites"] = 0
        
        return {
            "message": f"所有项目的接口依赖分析数据已删除（共 {len(project_ids)} 个项目）",
            "deleted_counts": deleted_counts,
            "projects_affected": len(project_ids)
        }
        
    except Exception as e:
        print(f"删除所有依赖分析数据时发生错误: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"删除所有依赖分析数据失败: {str(e)}")


@router.delete("/dependency-analysis/{project_id}")
async def delete_dependency_analysis(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    删除指定项目的接口依赖分析数据
    清除Redis、ChromaDB、Neo4j中存储的依赖分析数据
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        import redis
        from app.config import settings
        from app.services.vector_service import VectorService
        from app.services.db_service import DatabaseService
        
        deleted_counts = {
            "redis": 0,
            "chromadb": 0,
            "neo4j": 0,
            "test_case_suites": 0
        }
        
        # 1. 清除Redis数据
        try:
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                encoding='utf-8'
            )
            
            # 清除项目相关的Redis keys
            redis_patterns = [
                f"project:{project_id}:*",
                f"dependency_analysis:project:{project_id}:*",
                f"few_shot:project:{project_id}:*",
                f"scenario_chains:project:{project_id}:*",
                f"analysis:progress:{project_id}",
                f"dependency_graph:{project_id}",  # 依赖关系图数据
                f"interface_groups:{project_id}",  # 接口分组数据
                f"interface_chains:{project_id}",  # 接口依赖链数据
            ]
            
            total_keys = 0
            for pattern in redis_patterns:
                keys = redis_client.keys(pattern)
                if keys:
                    redis_client.delete(*keys)
                    total_keys += len(keys)
            
            deleted_counts["redis"] = total_keys
            print(f"已清除Redis键: {total_keys} 个 (project_id: {project_id})")
        except Exception as e:
            print(f"清除Redis数据失败: {e}")
        
        # 2. 清除ChromaDB数据
        try:
            vector_service = VectorService()
            vector_service.delete_documents(document_id=project_id)
            deleted_counts["chromadb"] = 1  # 标记为已清除
            print(f"已清除ChromaDB数据 (document_id: {project_id})")
        except Exception as e:
            print(f"清除ChromaDB数据失败: {e}")
        
        # 3. 清除Neo4j数据
        try:
            db_service = DatabaseService()
            session = db_service._get_neo4j_session()
            with session as neo4j_session:
                # 删除该项目的所有接口节点和依赖关系
                result = neo4j_session.run(
                    "MATCH (n:APIInterface {project_id: $project_id}) DETACH DELETE n RETURN count(n) as deleted",
                    project_id=project_id
                )
                record = result.single()
                deleted_count = record['deleted'] if record else 0
                deleted_counts["neo4j"] = deleted_count
                print(f"已清除Neo4j数据: {deleted_count} 个节点")
        except Exception as e:
            print(f"清除Neo4j数据失败: {e}")
        
        # 4. 清除MySQL数据库中的场景用例集数据
        try:
            from app.models import TestCaseSuite
            deleted_suites = db.query(TestCaseSuite).filter(
                TestCaseSuite.project_id == project_id
            ).delete(synchronize_session=False)
            db.commit()
            deleted_counts["test_case_suites"] = deleted_suites
            print(f"已清除MySQL场景用例集数据: {deleted_suites} 条")
        except Exception as e:
            db.rollback()
            print(f"清除MySQL场景用例集数据失败: {e}")
            deleted_counts["test_case_suites"] = 0
        
        return {
            "message": f"项目 {project_id} 的接口依赖分析数据已删除",
            "project_id": project_id,
            "deleted_counts": deleted_counts
        }
        
    except Exception as e:
        print(f"删除依赖分析数据时发生错误: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"删除依赖分析数据失败: {str(e)}")


@router.get("/dependencies-from-neo4j/{project_id}")
async def get_dependencies_from_neo4j(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    获取接口依赖关系（优化版本：优先从Redis读取，如果Redis没有再从Neo4j读取）
    分析完成后，数据已保存到Redis、ChromaDB、Neo4j，优先从Redis读取以提高性能
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        analyzer = OptimizedDependencyAnalyzer(db)
        
        # 优先从Redis读取（性能最优）
        redis_backup = analyzer._load_dependency_graph_from_redis(project_id)
        if redis_backup and redis_backup.get('nodes') and len(redis_backup.get('nodes', [])) > 0:
            print(f"从Redis加载依赖关系图：{len(redis_backup.get('nodes', []))} 个节点，{len(redis_backup.get('edges', []))} 条边")
            return {
                "project_id": project_id,
                "dependency_graph": redis_backup,
                "nodes_count": len(redis_backup.get('nodes', [])),
                "edges_count": len(redis_backup.get('edges', [])),
                "source": "redis"
            }
        
        # 如果Redis没有数据，尝试从Neo4j读取
        print("Redis中没有数据，尝试从Neo4j读取...")
        result = analyzer.get_dependencies_from_neo4j(project_id)
        
        # 如果Neo4j返回的数据为空，返回空数据
        if not result.get('nodes') or len(result.get('nodes', [])) == 0:
            print("Neo4j数据也为空，返回空数据")
            return {
                "project_id": project_id,
                "dependency_graph": {"nodes": [], "edges": []},
                "nodes_count": 0,
                "edges_count": 0,
                "source": "empty"
            }
        
        nodes_count = len(result.get('nodes', []))
        edges_count = len(result.get('edges', []))
        print(f"从Neo4j返回：{nodes_count} 个节点，{edges_count} 条边")
        if edges_count == 0 and nodes_count > 0:
            print(f"⚠️  警告：有 {nodes_count} 个节点但没有边，可能依赖关系未正确存储或查询失败")
        
        return {
            "project_id": project_id,
            "dependency_graph": result,
            "nodes_count": nodes_count,
            "edges_count": edges_count,
            "source": "neo4j"
        }
    except Exception as e:
        # 如果Neo4j不可用，尝试从Redis备份中获取
        print(f"Neo4j获取失败: {e}，尝试从Redis备份获取")
        try:
            analyzer = OptimizedDependencyAnalyzer(db)
            redis_backup = analyzer._load_dependency_graph_from_redis(project_id)
            if redis_backup and redis_backup.get('nodes') and len(redis_backup.get('nodes', [])) > 0:
                print(f"从Redis备份加载依赖关系图：{len(redis_backup.get('nodes', []))} 个节点")
                return {
                    "project_id": project_id,
                    "dependency_graph": redis_backup,
                    "nodes_count": len(redis_backup.get('nodes', [])),
                    "edges_count": len(redis_backup.get('edges', [])),
                    "source": "redis_backup",
                    "neo4j_error": str(e)
                }
        except Exception as redis_error:
            print(f"Redis备份获取也失败: {redis_error}")
        
        # 如果Redis也失败，返回空数据
        return {
            "project_id": project_id,
            "dependency_graph": {
                "nodes": [],
                "edges": []
            },
            "error": str(e),
            "source": "none"
        }


@router.get("/dependencies-from-documents/{project_id}")
async def get_dependencies_from_documents_deprecated(
    project_id: int,
    document_id: Optional[int] = Query(None, description="文档ID，不提供则返回所有文档的依赖关系"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    获取从文档中分析出的接口依赖关系（优先从Neo4j获取）
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 优先从Neo4j获取
    try:
        analyzer = OptimizedDependencyAnalyzer(db)
        neo4j_result = analyzer.get_dependencies_from_neo4j(project_id)
        
        if neo4j_result.get('nodes') and len(neo4j_result['nodes']) > 0:
            return {
                "project_id": project_id,
                "dependency_graph": neo4j_result,
                "source": "neo4j",
                "auth_interface": None,
                "token_info": None
            }
    except Exception as e:
        print(f"从Neo4j获取依赖关系失败: {e}")
    
    # 如果Neo4j没有数据，尝试从Redis获取（旧方法）
    analyzer = APIDependencyAnalyzer(db)
    
    if document_id:
        # 获取特定文档的依赖关系
        analysis_result = analyzer.get_dependency_analysis(project_id, str(document_id))
        
        if not analysis_result:
            # 检查文档是否存在
            document = db.query(Document).filter(
                Document.id == document_id,
                Document.project_id == project_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            return {
                "project_id": project_id,
                "document_id": document_id,
                "status": "not_analyzed",
                "message": "该文档的接口依赖关系尚未分析，请先调用 /analyze-from-documents 接口",
                "dependency_graph": {
                    "nodes": [],
                    "edges": []
                }
            }
        
        return {
            "project_id": project_id,
            "document_id": document_id,
            "status": "success",
            "dependency_graph": analysis_result,
            "auth_interface": analysis_result.get("auth_interface"),
            "token_info": analysis_result.get("token_info")
        }
    else:
        # 获取所有文档的依赖关系（合并）
        documents = db.query(Document).filter(Document.project_id == project_id).all()
        
        all_nodes = []
        all_edges = []
        node_map = {}  # 用于去重
        
        for doc in documents:
            analysis_result = analyzer.get_dependency_analysis(project_id, str(doc.id))
            if analysis_result:
                # 合并节点（去重）
                for node in analysis_result.get("nodes", []):
                    node_id = node.get("id")
                    if node_id not in node_map:
                        node_map[node_id] = node
                        all_nodes.append(node)
                
                # 合并边
                all_edges.extend(analysis_result.get("edges", []))
        
        # 合并所有文档的auth_interface和token_info（使用第一个找到的）
        merged_auth_interface = None
        merged_token_info = None
        for doc in documents:
            analysis_result = analyzer.get_dependency_analysis(project_id, str(doc.id))
            if analysis_result and not merged_auth_interface:
                merged_auth_interface = analysis_result.get("auth_interface")
                merged_token_info = analysis_result.get("token_info")
                if merged_auth_interface:
                    break
        
        return {
            "project_id": project_id,
            "documents_count": len(documents),
            "status": "success",
            "dependency_graph": {
                "nodes": all_nodes,
                "edges": all_edges,
                "dependency_chains": [],  # 合并的链需要重新计算
                "topological_order": []   # 合并的顺序需要重新计算
            },
            "auth_interface": merged_auth_interface,
            "token_info": merged_token_info
        }


