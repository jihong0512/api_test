"""
接口分组和依赖链API路由
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Project, DocumentAPIInterface
from app.routers.auth import get_current_user_optional
from app.services.interface_grouping_service import InterfaceGroupingService
import json

router = APIRouter(prefix="/api/interface-grouping", tags=["接口分组"])


class GroupingResult(BaseModel):
    """分组结果响应模型"""
    groups: Dict[str, Dict[str, Any]]
    chains_count: int
    total_interfaces: int
    cypher_file: str


class InterfaceGroupResponse(BaseModel):
    """接口分组响应模型"""
    group_id: str
    group_name: str
    interfaces: List[Dict[str, Any]]


class DependencyChainResponse(BaseModel):
    """依赖链响应模型"""
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


@router.post("/process/{project_id}", response_model=GroupingResult)
async def process_interface_grouping(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    处理接口分组和依赖链构建
    
    1. 按照30个分组规则对接口进行分组
    2. 如果没有匹配的分组规则，按照接口名称、接口path的相似度分组
    3. 构建依赖链：登录接口 -> 创建 -> 修改 -> 查询 -> 删除
    4. 生成Cypher文件并存储到Neo4j、ChromaDB和Redis
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 创建服务实例
    service = InterfaceGroupingService(db)
    
    # 处理接口分组和依赖链
    result = await service.process_interfaces(project_id)
    
    return result


@router.get("/groups/{project_id}")
async def get_interface_groups(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    获取接口分组列表（从Redis读取）
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 从Redis读取分组数据
    from app.services.interface_grouping_service import redis_client
    groups_key = f"interface_groups:{project_id}"
    
    try:
        groups_data_str = redis_client.get(groups_key)
        if groups_data_str:
            groups_data = json.loads(groups_data_str)
            return groups_data
        else:
            return {"message": "未找到分组数据，请先执行接口分组处理"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分组数据失败: {str(e)}")


@router.get("/chains/{project_id}")
async def get_dependency_chains(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    获取依赖链数据（从Redis读取）
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 从Redis读取依赖链数据
    from app.services.interface_grouping_service import redis_client
    chains_key = f"interface_chains:{project_id}"
    
    try:
        chains_data_str = redis_client.get(chains_key)
        if chains_data_str:
            chains_data = json.loads(chains_data_str)
            return chains_data
        else:
            return {"message": "未找到依赖链数据，请先执行接口分组处理"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取依赖链数据失败: {str(e)}")


@router.get("/topology/{project_id}")
async def get_topology_graph(
    project_id: int,
    source: str = Query("neo4j", description="数据源：neo4j 或 redis"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    获取拓扑图数据（从Neo4j或Redis读取）
    
    source参数：
    - neo4j: 从Neo4j图数据库读取（实时数据）
    - redis: 从Redis缓存读取（更快）
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if source == "redis":
        # 从Redis读取
        from app.services.interface_grouping_service import redis_client
        
        # 获取分组数据
        groups_key = f"interface_groups:{project_id}"
        groups_data_str = redis_client.get(groups_key)
        
        # 获取依赖链数据
        chains_key = f"interface_chains:{project_id}"
        chains_data_str = redis_client.get(chains_key)
        
        if not groups_data_str or not chains_data_str:
            raise HTTPException(status_code=404, detail="未找到拓扑图数据，请先执行接口分组处理")
        
        groups_data = json.loads(groups_data_str)
        chains_data = json.loads(chains_data_str)
        
        # 构建拓扑图数据格式
        nodes = []
        edges = []
        
        # 添加节点（从依赖链中提取）
        for chain in chains_data:
            for node in chain.get('nodes', []):
                if node not in nodes:
                    nodes.append(node)
            for edge in chain.get('edges', []):
                edges.append(edge)
        
        return {
            "nodes": nodes,
            "edges": edges,
            "groups": groups_data
        }
    
    elif source == "neo4j":
        # 从Neo4j读取
        from app.services.interface_grouping_service import InterfaceGroupingService
        service = InterfaceGroupingService(db)
        
        try:
            # 查询Neo4j获取所有接口节点和关系
            cypher_query = f"""
            MATCH (n)
            WHERE n.project_id = {project_id}
            OPTIONAL MATCH (n)-[r]->(m)
            WHERE m.project_id = {project_id}
            RETURN n, r, m
            LIMIT 1000
            """
            
            results = service.db_service.query_knowledge_graph(cypher_query, project_id)
            
            # 构建节点和边
            nodes = []
            edges = []
            node_ids = set()
            
            for record in results:
                # 处理节点n
                if 'n' in record and record['n']:
                    node_data = record['n']
                    node_id = str(node_data.get('id', ''))
                    if node_id and node_id not in node_ids:
                        nodes.append({
                            'id': node_id,
                            'name': node_data.get('name', ''),
                            'type': node_data.get('type', ''),
                            'method': node_data.get('method', ''),
                            'url': node_data.get('url', '')
                        })
                        node_ids.add(node_id)
                
                # 处理节点m
                if 'm' in record and record['m']:
                    node_data = record['m']
                    node_id = str(node_data.get('id', ''))
                    if node_id and node_id not in node_ids:
                        nodes.append({
                            'id': node_id,
                            'name': node_data.get('name', ''),
                            'type': node_data.get('type', ''),
                            'method': node_data.get('method', ''),
                            'url': node_data.get('url', '')
                        })
                        node_ids.add(node_id)
                
                # 处理关系r
                if 'r' in record and record['r']:
                    rel_data = record['r']
                    source_id = str(record['n'].get('id', '')) if 'n' in record and record['n'] else ''
                    target_id = str(record['m'].get('id', '')) if 'm' in record and record['m'] else ''
                    
                    if source_id and target_id:
                        edges.append({
                            'source': source_id,
                            'target': target_id,
                            'type': rel_data.get('type', 'DEPENDS_ON'),
                            'description': rel_data.get('description', '')
                        })
            
            return {
                "nodes": nodes,
                "edges": edges,
                "source": "neo4j"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"从Neo4j获取拓扑图数据失败: {str(e)}")
    
    else:
        raise HTTPException(status_code=400, detail="source参数必须是 'neo4j' 或 'redis'")


@router.get("/cypher/{project_id}")
async def get_cypher_file(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    获取最新的Cypher文件内容
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    import os
    from datetime import datetime
    
    # 查找最新的Cypher文件
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cypher_dir = os.path.join(backend_dir, "cypher_files")
    
    if not os.path.exists(cypher_dir):
        raise HTTPException(status_code=404, detail="Cypher文件目录不存在")
    
    # 查找匹配的Cypher文件
    cypher_files = [
        f for f in os.listdir(cypher_dir)
        if f.startswith(f"interface_groups_chains_{project_id}_") and f.endswith(".cypher")
    ]
    
    if not cypher_files:
        raise HTTPException(status_code=404, detail="未找到Cypher文件")
    
    # 按时间排序，获取最新的
    cypher_files.sort(reverse=True)
    latest_file = cypher_files[0]
    filepath = os.path.join(cypher_dir, latest_file)
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {
            "filename": latest_file,
            "content": content,
            "filepath": filepath
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取Cypher文件失败: {str(e)}")

