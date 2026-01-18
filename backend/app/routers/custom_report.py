from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json
from datetime import datetime
from io import BytesIO

from app.database import get_db
from app.models import TestResult, TestTask, Project, User, TestCase
from app.routers.auth import get_current_user_optional
from fastapi.responses import StreamingResponse

router = APIRouter()


class CustomReportConfig(BaseModel):
    report_title: str = "测试报告"
    include_passed: bool = True
    include_failed: bool = True
    include_skipped: bool = False
    include_request_data: bool = True
    include_response_data: bool = True
    include_performance_metrics: bool = True
    include_failure_analysis: bool = True
    include_trends: bool = False
    date_range: Optional[Dict[str, str]] = None  # {start: "2024-01-01", end: "2024-01-31"}
    format: str = "html"  # html, pdf, excel, json


@router.post("/generate/{task_id}")
async def generate_custom_report(
    task_id: int,
    config: CustomReportConfig,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    生成自定义测试报告
    """
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
    query = db.query(TestResult).filter(TestResult.task_id == task_id)
    
    # 按状态筛选
    status_filter = []
    if config.include_passed:
        status_filter.append("passed")
    if config.include_failed:
        status_filter.append("failed")
    if config.include_skipped:
        status_filter.append("skipped")
    
    if status_filter:
        query = query.filter(TestResult.status.in_(status_filter))
    
    results = query.order_by(TestResult.created_at).all()
    
    # 获取用例信息
    test_cases = {}
    case_ids = list(set([r.test_case_id for r in results]))
    if case_ids:
        cases = db.query(TestCase).filter(TestCase.id.in_(case_ids)).all()
        test_cases = {case.id: case for case in cases}
    
    # 构建报告数据
    report_data = {
        "title": config.report_title,
        "task_name": task.name,
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total": len(results),
            "passed": len([r for r in results if r.status == "passed"]),
            "failed": len([r for r in results if r.status == "failed"]),
            "skipped": len([r for r in results if r.status == "skipped"])
        },
        "results": []
    }
    
    for result in results:
        result_item = {
            "test_case_id": result.test_case_id,
            "test_case_name": test_cases.get(result.test_case_id, {}).name if result.test_case_id in test_cases else "未知用例",
            "status": result.status,
            "status_code": result.status_code,
            "execution_time": float(result.execution_time) if result.execution_time else None,
            "error_message": result.error_message
        }
        
        if config.include_request_data and result.request_data:
            try:
                result_item["request_data"] = json.loads(result.request_data)
            except:
                result_item["request_data"] = result.request_data
        
        if config.include_response_data and result.response_data:
            try:
                result_item["response_data"] = json.loads(result.response_data)
            except:
                result_item["response_data"] = result.response_data
        
        if config.include_performance_metrics and result.performance_metrics:
            try:
                result_item["performance_metrics"] = json.loads(result.performance_metrics)
            except:
                pass
        
        if config.include_failure_analysis and result.failure_analysis:
            try:
                result_item["failure_analysis"] = json.loads(result.failure_analysis)
            except:
                pass
        
        report_data["results"].append(result_item)
    
    # 根据格式生成报告
    if config.format == "json":
        return report_data
    
    elif config.format == "html":
        html_content = generate_html_report(report_data, config)
        return StreamingResponse(
            BytesIO(html_content.encode('utf-8')),
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename=test_report_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            }
        )
    
    elif config.format == "pdf":
        # PDF生成需要额外库，这里先返回提示
        raise HTTPException(status_code=501, detail="PDF格式暂未实现，请使用HTML或JSON格式")
    
    elif config.format == "excel":
        # Excel生成需要额外库，这里先返回提示
        raise HTTPException(status_code=501, detail="Excel格式暂未实现，请使用HTML或JSON格式")
    
    else:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {config.format}")


def generate_html_report(report_data: Dict[str, Any], config: CustomReportConfig) -> str:
    """生成HTML格式的报告"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{report_data['title']}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                background-color: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #1890ff;
                border-bottom: 2px solid #1890ff;
                padding-bottom: 10px;
            }}
            .summary {{
                display: flex;
                gap: 20px;
                margin: 20px 0;
            }}
            .summary-card {{
                flex: 1;
                padding: 15px;
                border-radius: 4px;
                text-align: center;
            }}
            .summary-card.total {{
                background-color: #e6f7ff;
                border: 1px solid #91d5ff;
            }}
            .summary-card.passed {{
                background-color: #f6ffed;
                border: 1px solid #b7eb8f;
            }}
            .summary-card.failed {{
                background-color: #fff2f0;
                border: 1px solid #ffccc7;
            }}
            .summary-card.skipped {{
                background-color: #fffbe6;
                border: 1px solid #ffe58f;
            }}
            .summary-card h3 {{
                margin: 0;
                font-size: 24px;
                color: #333;
            }}
            .summary-card p {{
                margin: 5px 0 0 0;
                color: #666;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }}
            th, td {{
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #e8e8e8;
            }}
            th {{
                background-color: #fafafa;
                font-weight: bold;
            }}
            tr:hover {{
                background-color: #fafafa;
            }}
            .status-passed {{
                color: #52c41a;
                font-weight: bold;
            }}
            .status-failed {{
                color: #ff4d4f;
                font-weight: bold;
            }}
            .status-skipped {{
                color: #faad14;
                font-weight: bold;
            }}
            .detail-section {{
                margin-top: 20px;
                padding: 15px;
                background-color: #fafafa;
                border-radius: 4px;
            }}
            .detail-section h4 {{
                margin-top: 0;
                color: #1890ff;
            }}
            pre {{
                background-color: #f5f5f5;
                padding: 10px;
                border-radius: 4px;
                overflow-x: auto;
            }}
            .metadata {{
                color: #999;
                font-size: 12px;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{report_data['title']}</h1>
            <div class="metadata">
                <p>任务名称: {report_data['task_name']}</p>
                <p>生成时间: {report_data['generated_at']}</p>
            </div>
            
            <div class="summary">
                <div class="summary-card total">
                    <h3>{report_data['summary']['total']}</h3>
                    <p>总计</p>
                </div>
                <div class="summary-card passed">
                    <h3>{report_data['summary']['passed']}</h3>
                    <p>通过</p>
                </div>
                <div class="summary-card failed">
                    <h3>{report_data['summary']['failed']}</h3>
                    <p>失败</p>
                </div>
                <div class="summary-card skipped">
                    <h3>{report_data['summary']['skipped']}</h3>
                    <p>跳过</p>
                </div>
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>用例名称</th>
                        <th>状态</th>
                        <th>状态码</th>
                        <th>执行时间</th>
                        <th>错误信息</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for result in report_data['results']:
        status_class = f"status-{result['status']}"
        html += f"""
                    <tr>
                        <td>{result['test_case_name']}</td>
                        <td class="{status_class}">{result['status']}</td>
                        <td>{result.get('status_code', '-')}</td>
                        <td>{result.get('execution_time', '-')}</td>
                        <td>{result.get('error_message', '-')}</td>
                    </tr>
        """
        
        # 添加详细信息
        if config.include_request_data or config.include_response_data:
            html += f"""
                    <tr>
                        <td colspan="5">
                            <div class="detail-section">
            """
            
            if config.include_request_data and result.get('request_data'):
                html += f"""
                                <h4>请求数据</h4>
                                <pre>{json.dumps(result['request_data'], indent=2, ensure_ascii=False)}</pre>
                """
            
            if config.include_response_data and result.get('response_data'):
                html += f"""
                                <h4>响应数据</h4>
                                <pre>{json.dumps(result['response_data'], indent=2, ensure_ascii=False)}</pre>
                """
            
            if config.include_failure_analysis and result.get('failure_analysis'):
                html += f"""
                                <h4>失败分析</h4>
                                <pre>{json.dumps(result['failure_analysis'], indent=2, ensure_ascii=False)}</pre>
                """
            
            html += """
                            </div>
                        </td>
                    </tr>
            """
    
    html += """
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    
    return html


@router.get("/formats")
async def get_report_formats():
    """获取支持的报告格式列表"""
    return {
        "formats": [
            {"value": "html", "label": "HTML", "description": "美观的网页格式，可直接在浏览器中查看"},
            {"value": "json", "label": "JSON", "description": "结构化数据格式，便于程序处理"},
            {"value": "pdf", "label": "PDF", "description": "PDF文档格式（暂未实现）"},
            {"value": "excel", "label": "Excel", "description": "Excel表格格式（暂未实现）"}
        ]
    }









































