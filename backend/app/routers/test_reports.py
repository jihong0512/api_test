from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import os
import json

from app.database import get_db
from app.models import TestTask, TestResult, TestCase, Project, User
from app.routers.auth import get_current_user_optional
from app.services.report_generator import AllureReportGenerator
from app.services.failure_analyzer import FailureAnalyzer
from app.services.ai_suggestion_service import AISuggestionService
from app.services.trend_analyzer import TrendAnalyzer

router = APIRouter()


@router.post("/{task_id}/generate-allure")
async def generate_allure_report(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成Allure测试报告"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    # 获取测试结果
    test_results = db.query(TestResult).filter(TestResult.task_id == task_id).all()
    
    if not test_results:
        # 如果没有TestResult记录，检查任务是否有执行日志
        if not task.execution_logs:
            raise HTTPException(
                status_code=400, 
                detail="没有测试结果。该任务可能使用了新的执行方式，请等待任务完成后查看报告。"
            )
        # 如果有执行日志但没有TestResult，说明使用了新的执行方式
        # 这种情况下，Allure报告应该已经在任务执行时生成
        if task.allure_report_path:
            return {
                "task_id": task_id,
                "report_dir": task.allure_report_path,
                "report_url": f"/api/jobs/{task_id}/allure-report",
                "status": "success",
                "message": "报告已在任务执行时生成"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="该任务没有生成HTML测试报告。请确保任务类型为scenario或interface，且任务已成功完成。"
            )
    
    # 获取测试用例
    test_case_ids = [r.test_case_id for r in test_results]
    test_cases = db.query(TestCase).filter(TestCase.id.in_(test_case_ids)).all()
    
    # 生成Allure结果
    report_generator = AllureReportGenerator()
    results_info = report_generator.generate_allure_results(task, test_results, test_cases)
    
    # 生成HTML报告
    report_dir = f"/tmp/allure-reports/task_{task_id}"
    report_info = report_generator.generate_allure_report(
        results_info["results_dir"],
        report_dir
    )
    
    if report_info["status"] == "error":
        raise HTTPException(status_code=500, detail=f"生成报告失败: {report_info.get('error')}")
    
    return {
        "task_id": task_id,
        "report_dir": report_dir,
        "report_url": f"/api/test-reports/{task_id}/allure/index.html",
        "status": "success"
    }


@router.get("/{task_id}/allure/index.html")
async def serve_allure_report(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """提供Allure报告文件"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    from fastapi.responses import FileResponse
    
    report_file = f"/tmp/allure-reports/task_{task_id}/index.html"
    if not os.path.exists(report_file):
        raise HTTPException(status_code=404, detail="报告文件不存在，请先生成报告")
    
    return FileResponse(report_file)


@router.post("/{task_id}/analyze-failures")
async def analyze_task_failures(
    task_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """分析任务失败原因"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    analyzer = FailureAnalyzer(db)
    analysis_result = analyzer.analyze_task_failures(task_id)
    
    # 分析每个失败用例
    failed_results = db.query(TestResult).filter(
        TestResult.task_id == task_id,
        TestResult.status == "failed"
    ).all()
    
    detailed_analysis = []
    for result in failed_results:
        test_case = db.query(TestCase).filter(TestCase.id == result.test_case_id).first()
        case_analysis = analyzer.analyze_failure(result, test_case)
        
        # 保存分析结果
        if case_analysis.get("status") == "success":
            result.failure_analysis = json.dumps(case_analysis["analysis"], ensure_ascii=False)
            db.commit()
        
        detailed_analysis.append({
            "test_case_id": result.test_case_id,
            "test_case_name": test_case.name if test_case else "",
            "analysis": case_analysis.get("analysis", {})
        })
    
    analysis_result["detailed_analysis"] = detailed_analysis
    
    return analysis_result


@router.get("/{result_id}/analyze-failure")
async def analyze_single_failure(
    result_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """分析单个测试失败原因"""
    result = db.query(TestResult).filter(TestResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    # 检查权限
    task = db.query(TestTask).filter(TestTask.id == result.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    project = db.query(Project).filter(
        Project.id == task.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    test_case = db.query(TestCase).filter(TestCase.id == result.test_case_id).first()
    analyzer = FailureAnalyzer(db)
    analysis = analyzer.analyze_failure(result, test_case)
    
    # 保存分析结果
    if analysis.get("status") == "success":
        result.failure_analysis = json.dumps(analysis["analysis"], ensure_ascii=False)
        db.commit()
    
    return analysis


@router.get("/{task_id}/ai-suggestions")
async def get_ai_suggestions(
    task_id: int,
    days: int = Query(30, description="分析最近N天的历史数据"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取AI优化建议"""
    task = db.query(TestTask).filter(TestTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == task.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    suggestion_service = AISuggestionService(db)
    suggestions = suggestion_service.generate_suggestions(task_id, days)
    
    # 保存建议到任务
    if suggestions.get("suggestions"):
        task.ai_suggestions = json.dumps(suggestions, ensure_ascii=False)
        db.commit()
    
    return suggestions


@router.get("/trend-analysis/{project_id}")
async def get_trend_analysis(
    project_id: int,
    days: int = Query(30, description="分析最近N天"),
    group_by: str = Query("day", description="分组方式：day/week/month"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试通过率趋势分析"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    trend_analyzer = TrendAnalyzer(db)
    trend_data = trend_analyzer.analyze_pass_rate_trend(project_id, days, group_by)
    
    return trend_data

