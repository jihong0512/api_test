from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.database import get_db
from app.models import Project, User
from app.routers.auth import get_current_user_optional
from app.services.db_service import DatabaseService

router = APIRouter()
db_service = DatabaseService()


@router.get("/")
async def get_knowledge_graph(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取知识图谱（从Neo4j）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        # 从Neo4j获取完整的知识图谱数据
        graph_data = db_service.get_knowledge_graph_data(project_id)

        # 添加Neo4j可用性标志
        if not graph_data.get("nodes") and not graph_data.get("edges"):
            graph_data["neo4j_available"] = False
            graph_data["message"] = "Neo4j服务不可用或未连接数据库，知识图谱功能暂时无法使用"
        else:
            graph_data["neo4j_available"] = True

        return graph_data
    except Exception as e:
        # 如果Neo4j不可用，返回空数据和错误信息
        print(f"⚠️  获取知识图谱失败: {e}")
        return {
            "nodes": [],
            "edges": [],
            "neo4j_available": False,
            "error": str(e),
            "message": "Neo4j服务不可用，知识图谱功能暂时无法使用。请检查Neo4j配置或稍后重试。"
        }


