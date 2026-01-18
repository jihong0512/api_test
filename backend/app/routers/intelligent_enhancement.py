from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import Project, User
from app.routers.auth import get_current_user_optional
from app.services.rag_service import HybridRAGService
from app.services.agent_service import MultiAgentOrchestrator

router = APIRouter()

def get_rag_service():
    """获取RAG服务实例（延迟初始化）"""
    return HybridRAGService()

def get_agent_orchestrator():
    """获取Agent编排器实例（延迟初始化）"""
    return MultiAgentOrchestrator()


class QueryRequest(BaseModel):
    query: str
    mode: str = "hybrid"  # hybrid, graph, graph_rag
    top_k: int = 10


class AgentTaskRequest(BaseModel):
    task: str
    initial_context: Optional[Dict[str, Any]] = None


@router.post("/rag/search")
async def rag_search(
    project_id: int,
    request: QueryRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """混合RAG检索"""
    # 验证项目权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        rag_service = get_rag_service()
        results = await rag_service.query(
            query=request.query,
            project_id=project_id,
            mode=request.mode,
            top_k=request.top_k
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG检索失败: {str(e)}")


@router.post("/graph-rag/search")
async def graph_rag_search(
    project_id: int,
    request: QueryRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """GraphRAG检索（基于知识图谱的检索增强生成）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        rag_service = get_rag_service()
        results = await rag_service.graph_rag_search(
            query=request.query,
            project_id=project_id,
            top_k=request.top_k
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GraphRAG检索失败: {str(e)}")


@router.post("/agent/process")
async def agent_process(
    project_id: int,
    request: AgentTaskRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """多Agent协作处理任务"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        agent_orchestrator = get_agent_orchestrator()
        result = await agent_orchestrator.process(
            task=request.task,
            project_id=project_id,
            initial_context=request.initial_context
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent处理失败: {str(e)}")


@router.post("/agent/parse-interfaces")
async def agent_parse_interfaces(
    project_id: int,
    request: AgentTaskRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """使用接口解析Agent解析接口"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    from app.services.agent_service import InterfaceParserAgent
    
    agent = InterfaceParserAgent()
    state = {
        "messages": [],
        "current_task": request.task,
        "parsed_interfaces": [],
        "dependencies": {},
        "test_cases": [],
        "context": request.initial_context or {},
        "project_id": project_id
    }
    
    try:
        result_state = await agent.parse(state)
        return {
            "interfaces": result_state["parsed_interfaces"],
            "context": result_state["context"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"接口解析失败: {str(e)}")


@router.post("/agent/analyze-dependencies")
async def agent_analyze_dependencies(
    project_id: int,
    interfaces: List[Dict[str, Any]] = Body(...),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """使用依赖分析Agent分析接口依赖"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    from app.services.agent_service import DependencyAnalyzerAgent
    
    agent = DependencyAnalyzerAgent()
    state = {
        "messages": [],
        "current_task": "",
        "parsed_interfaces": interfaces,
        "dependencies": {},
        "test_cases": [],
        "context": {},
        "project_id": project_id
    }
    
    try:
        result_state = await agent.analyze(state)
        return {"dependencies": result_state["dependencies"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"依赖分析失败: {str(e)}")


@router.post("/agent/generate-testcases")
async def agent_generate_testcases(
    project_id: int,
    interfaces: List[Dict[str, Any]] = Body(...),
    dependencies: Optional[Dict[str, Any]] = Body(None),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """使用测试用例生成Agent生成测试用例"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    from app.services.agent_service import TestCaseGeneratorAgent
    
    agent = TestCaseGeneratorAgent()
    state = {
        "messages": [],
        "current_task": "",
        "parsed_interfaces": interfaces,
        "dependencies": dependencies or {},
        "test_cases": [],
        "context": {},
        "project_id": project_id
    }
    
    try:
        result_state = await agent.generate(state)
        return {"test_cases": result_state["test_cases"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试用例生成失败: {str(e)}")






