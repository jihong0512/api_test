"""
API文档变更检测和智能更新建议API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import json

from app.database import get_db
from app.models import (
    Document, Project, User, APIInterface, TestCase,
    APIDocumentSnapshot, APIChangeHistory, UpdateSuggestion
)
from app.routers.auth import get_current_user_optional
from app.services.api_change_detector import APIChangeDetector
from app.services.script_update_adviser import ScriptUpdateAdviser

router = APIRouter()

change_detector = APIChangeDetector()
update_adviser = ScriptUpdateAdviser()


@router.post("/snapshot")
async def create_snapshot(
    document_id: int,
    version: Optional[str] = None,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """创建API文档快照"""
    # 验证文档权限
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    project = db.query(Project).filter(
        Project.id == document.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # 获取当前项目下的所有接口
    interfaces = db.query(APIInterface).filter(
        APIInterface.project_id == document.project_id
    ).all()
    
    # 构建快照数据
    snapshot_data = []
    for iface in interfaces:
        snapshot_data.append({
            "id": iface.id,
            "name": iface.name,
            "method": iface.method,
            "url": iface.url,
            "description": iface.description,
            "headers": iface.headers,
            "params": iface.params,
            "body": iface.body,
            "response_schema": iface.response_schema
        })
    
    # 生成版本号
    if not version:
        existing_snapshots = db.query(APIDocumentSnapshot).filter(
            APIDocumentSnapshot.document_id == document_id
        ).count()
        version = f"v{existing_snapshots + 1}"
    
    # 创建快照
    snapshot = APIDocumentSnapshot(
        project_id=document.project_id,
        document_id=document_id,
        snapshot_data=json.dumps(snapshot_data, ensure_ascii=False),
        version=version
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    
    return {
        "message": "快照创建成功",
        "snapshot_id": snapshot.id,
        "version": snapshot.version,
        "total_interfaces": len(snapshot_data)
    }


@router.post("/detect-changes")
async def detect_changes(
    document_id: int,
    old_snapshot_id: Optional[int] = None,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """检测API文档变更"""
    # 验证文档权限
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    project = db.query(Project).filter(
        Project.id == document.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # 获取旧快照数据
    if old_snapshot_id:
        old_snapshot = db.query(APIDocumentSnapshot).filter(
            APIDocumentSnapshot.id == old_snapshot_id
        ).first()
        if not old_snapshot:
            raise HTTPException(status_code=404, detail="Old snapshot not found")
        old_interfaces_data = json.loads(old_snapshot.snapshot_data)
    else:
        # 如果没有指定旧快照，使用最新快照
        old_snapshot = db.query(APIDocumentSnapshot).filter(
            APIDocumentSnapshot.document_id == document_id
        ).order_by(APIDocumentSnapshot.created_at.desc()).first()
        if not old_snapshot:
            raise HTTPException(status_code=404, detail="No previous snapshot found")
        old_interfaces_data = json.loads(old_snapshot.snapshot_data)
    
    # 获取当前接口数据
    current_interfaces = db.query(APIInterface).filter(
        APIInterface.project_id == document.project_id
    ).all()
    new_interfaces_data = []
    for iface in current_interfaces:
        new_interfaces_data.append({
            "id": iface.id,
            "name": iface.name,
            "method": iface.method,
            "url": iface.url,
            "description": iface.description,
            "headers": iface.headers,
            "params": iface.params,
            "body": iface.body,
            "response_schema": iface.response_schema
        })
    
    # 检测变更
    changes = change_detector.detect_changes(old_interfaces_data, new_interfaces_data)
    
    # 创建新的快照
    current_snapshot = db.query(APIDocumentSnapshot).filter(
        APIDocumentSnapshot.document_id == document_id
    ).order_by(APIDocumentSnapshot.created_at.desc()).first()
    
    if not current_snapshot or current_snapshot.id != old_snapshot.id:
        # 创建新快照
        existing_snapshots = db.query(APIDocumentSnapshot).filter(
            APIDocumentSnapshot.document_id == document_id
        ).count()
        version = f"v{existing_snapshots + 1}"
        
        new_snapshot = APIDocumentSnapshot(
            project_id=document.project_id,
            document_id=document_id,
            snapshot_data=json.dumps(new_interfaces_data, ensure_ascii=False),
            version=version
        )
        db.add(new_snapshot)
        db.commit()
        db.refresh(new_snapshot)
    else:
        new_snapshot = current_snapshot
    
    # 保存变更历史
    for change_type in ["added", "deleted", "modified"]:
        if changes.get(change_type):
            affected_ids = []
            if change_type == "modified":
                affected_ids = [item["interface"].get("id") for item in changes[change_type] if item.get("interface", {}).get("id")]
            elif change_type in ["added", "deleted"]:
                affected_ids = [item.get("id") for item in changes[change_type] if item.get("id")]
            
            if affected_ids:
                # 评估变更级别
                change_level = "low"
                if change_type == "deleted":
                    change_level = "breaking"
                elif change_type == "modified":
                    # 检查是否有高风险变更
                    for item in changes[change_type]:
                        if item.get("changes", {}).get("change_level") in ["high", "breaking"]:
                            change_level = "high"
                            break
                        elif item.get("changes", {}).get("change_level") == "medium":
                            change_level = "medium"
                
                change_history = APIChangeHistory(
                    project_id=document.project_id,
                    snapshot_id=new_snapshot.id,
                    old_snapshot_id=old_snapshot.id,
                    change_type=change_type,
                    change_summary=json.dumps(changes.get("summary", {}), ensure_ascii=False),
                    affected_interfaces=json.dumps(affected_ids, ensure_ascii=False),
                    change_level=change_level
                )
                db.add(change_history)
    
    db.commit()
    
    return {
        "message": "变更检测完成",
        "changes": changes,
        "new_snapshot_id": new_snapshot.id,
        "old_snapshot_id": old_snapshot.id
    }


@router.post("/generate-update-suggestions")
async def generate_update_suggestions(
    change_history_id: int,
    update_strategy: str = "auto",
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """为受影响的测试用例生成更新建议"""
    # 验证变更历史
    change_history = db.query(APIChangeHistory).filter(
        APIChangeHistory.id == change_history_id
    ).first()
    if not change_history:
        raise HTTPException(status_code=404, detail="Change history not found")
    
    project = db.query(Project).filter(
        Project.id == change_history.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # 获取受影响的测试用例
    affected_interface_ids = json.loads(change_history.affected_interfaces or "[]")
    affected_test_cases = db.query(TestCase).filter(
        TestCase.api_interface_id.in_(affected_interface_ids),
        TestCase.project_id == change_history.project_id
    ).all()
    
    if not affected_test_cases:
        return {
            "message": "没有受影响的测试用例",
            "suggestions": []
        }
    
    # 获取变更信息
    old_snapshot = db.query(APIDocumentSnapshot).filter(
        APIDocumentSnapshot.id == change_history.old_snapshot_id
    ).first()
    new_snapshot = db.query(APIDocumentSnapshot).filter(
        APIDocumentSnapshot.id == change_history.snapshot_id
    ).first()
    
    old_interfaces = json.loads(old_snapshot.snapshot_data) if old_snapshot else []
    new_interfaces = json.loads(new_snapshot.snapshot_data) if new_snapshot else []
    
    # 重新检测变更以获取详细信息
    changes_result = change_detector.detect_changes(old_interfaces, new_interfaces)
    
    suggestions = []
    for test_case in affected_test_cases:
        # 找到对应的接口变更信息
        api_interface_id = test_case.api_interface_id
        change_info = None
        
        if change_history.change_type == "modified":
            for mod_item in changes_result.get("modified", []):
                if mod_item.get("interface", {}).get("id") == api_interface_id:
                    change_info = mod_item
                    break
        elif change_history.change_type == "added":
            change_info = {
                "interface": next(
                    (iface for iface in new_interfaces if iface.get("id") == api_interface_id),
                    {}
                ),
                "changes": {"change_level": "low"}
            }
        elif change_history.change_type == "deleted":
            change_info = {
                "interface": next(
                    (iface for iface in old_interfaces if iface.get("id") == api_interface_id),
                    {}
                ),
                "changes": {"change_level": "breaking"}
            }
        
        if change_info:
            # 构建测试用例数据
            test_case_data = {
                "id": test_case.id,
                "name": test_case.name,
                "api_interface_id": test_case.api_interface_id,
                "test_data": test_case.test_data,
                "test_code": test_case.test_code,
                "assertions": test_case.assertions
            }
            
            # 生成更新建议
            suggestion = await update_adviser.generate_update_suggestions(
                change_info, test_case_data, update_strategy
            )
            
            # 保存建议到数据库
            update_suggestion = UpdateSuggestion(
                change_history_id=change_history_id,
                test_case_id=test_case.id,
                strategy=suggestion["strategy"],
                reasoning=suggestion.get("reasoning", ""),
                update_plan=json.dumps(suggestion.get("update_plan", {}), ensure_ascii=False),
                manual_interventions=json.dumps(
                    suggestion.get("manual_interventions", []), ensure_ascii=False
                ),
                estimated_effort=suggestion.get("estimated_effort", "medium"),
                automation_rate=suggestion.get("automation_rate", 0.0)
            )
            db.add(update_suggestion)
            suggestions.append({
                "test_case_id": test_case.id,
                "test_case_name": test_case.name,
                **suggestion
            })
    
    db.commit()
    
    return {
        "message": "更新建议生成完成",
        "total_suggestions": len(suggestions),
        "suggestions": suggestions
    }


@router.get("/change-history")
async def get_change_history(
    project_id: int,
    limit: int = 20,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取变更历史列表"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    history_list = db.query(APIChangeHistory).filter(
        APIChangeHistory.project_id == project_id
    ).order_by(APIChangeHistory.detected_at.desc()).limit(limit).all()
    
    result = []
    for history in history_list:
        result.append({
            "id": history.id,
            "change_type": history.change_type,
            "change_level": history.change_level,
            "change_summary": json.loads(history.change_summary or "{}"),
            "affected_interfaces": json.loads(history.affected_interfaces or "[]"),
            "detected_at": history.detected_at.isoformat() if history.detected_at else None,
            "snapshot_id": history.snapshot_id,
            "old_snapshot_id": history.old_snapshot_id
        })
    
    return {
        "total": len(result),
        "history": result
    }


@router.get("/update-suggestions/{change_history_id}")
async def get_update_suggestions(
    change_history_id: int,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取更新建议列表"""
    change_history = db.query(APIChangeHistory).filter(
        APIChangeHistory.id == change_history_id
    ).first()
    if not change_history:
        raise HTTPException(status_code=404, detail="Change history not found")
    
    project = db.query(Project).filter(
        Project.id == change_history.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    query = db.query(UpdateSuggestion).filter(
        UpdateSuggestion.change_history_id == change_history_id
    )
    
    if status:
        query = query.filter(UpdateSuggestion.status == status)
    
    suggestions = query.all()
    
    result = []
    for suggestion in suggestions:
        result.append({
            "id": suggestion.id,
            "test_case_id": suggestion.test_case_id,
            "strategy": suggestion.strategy,
            "reasoning": suggestion.reasoning,
            "update_plan": json.loads(suggestion.update_plan or "{}"),
            "manual_interventions": json.loads(suggestion.manual_interventions or "[]"),
            "estimated_effort": suggestion.estimated_effort,
            "automation_rate": float(suggestion.automation_rate) if suggestion.automation_rate else 0.0,
            "status": suggestion.status,
            "created_at": suggestion.created_at.isoformat() if suggestion.created_at else None,
            "applied_at": suggestion.applied_at.isoformat() if suggestion.applied_at else None
        })
    
    return {
        "total": len(result),
        "suggestions": result
    }


@router.post("/apply-suggestion/{suggestion_id}")
async def apply_suggestion(
    suggestion_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """应用更新建议"""
    suggestion = db.query(UpdateSuggestion).filter(
        UpdateSuggestion.id == suggestion_id
    ).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    change_history = db.query(APIChangeHistory).filter(
        APIChangeHistory.id == suggestion.change_history_id
    ).first()
    if not change_history:
        raise HTTPException(status_code=404, detail="Change history not found")
    
    project = db.query(Project).filter(
        Project.id == change_history.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    test_case = db.query(TestCase).filter(TestCase.id == suggestion.test_case_id).first()
    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")
    
    update_plan = json.loads(suggestion.update_plan or "{}")
    
    # 根据策略应用更新
    if suggestion.strategy == "regenerate":
        # 重新生成测试代码
        new_test_code = update_plan.get("update_plan", {}).get("new_test_code")
        if new_test_code:
            test_case.test_code = new_test_code
            test_case.status = "completed"
    elif suggestion.strategy == "incremental":
        # 增量更新（这里需要更复杂的逻辑，暂时标记为需要人工介入）
        test_case.status = "active"  # 保持活跃状态，等待人工验证
    
    # 更新建议状态
    suggestion.status = "applied"
    from datetime import datetime
    suggestion.applied_at = datetime.now()
    
    db.commit()
    
    return {
        "message": "更新建议已应用",
        "suggestion_id": suggestion_id,
        "test_case_id": test_case.id,
        "status": test_case.status
    }








































