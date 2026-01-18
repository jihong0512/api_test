"""
HTML测试报告生成器
仿照Allure样式生成美观的HTML测试报告
"""
import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional


def generate_html_report(
    task_id: int,
    task_name: str,
    execution_logs: List[Dict[str, Any]],
    total_cases: int,
    passed_cases: int,
    failed_cases: int,
    skipped_cases: int,
    report_type: str = "interface"
) -> str:
    """
    生成HTML测试报告
    
    Args:
        task_id: 任务ID
        task_name: 任务名称
        execution_logs: 执行日志列表
        total_cases: 总用例数
        passed_cases: 通过用例数
        failed_cases: 失败用例数
        skipped_cases: 跳过用例数
        report_type: 报告类型 (scenario, interface, performance)
    
    Returns:
        报告文件路径
    """
    # 创建报告目录（使用 /tmp 或当前工作目录，避免 /app 只读权限问题）
    base_report_dir = os.environ.get('REPORT_BASE_DIR', '/tmp/reports')
    try:
        os.makedirs(base_report_dir, exist_ok=True)
        # 测试是否可写
        test_file = os.path.join(base_report_dir, '.test_write')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except (OSError, PermissionError):
            # 如果无法写入，使用当前工作目录
            base_report_dir = os.path.join(os.getcwd(), 'reports')
            os.makedirs(base_report_dir, exist_ok=True)
    except (OSError, PermissionError):
        # 如果无法创建，使用当前工作目录
        base_report_dir = os.path.join(os.getcwd(), 'reports')
        os.makedirs(base_report_dir, exist_ok=True)
    
    report_dir = os.path.join(base_report_dir, f"{report_type}_task_{task_id}")
    os.makedirs(report_dir, exist_ok=True)
    
    # 生成HTML内容
    html_content = _generate_html_content(
        task_id=task_id,
        task_name=task_name,
        execution_logs=execution_logs,
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        skipped_cases=skipped_cases,
        report_type=report_type
    )
    
    # 保存HTML文件
    report_path = os.path.join(report_dir, "index.html")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return report_path


def _generate_html_content(
    task_id: int,
    task_name: str,
    execution_logs: List[Dict[str, Any]],
    total_cases: int,
    passed_cases: int,
    failed_cases: int,
    skipped_cases: int,
    report_type: str
) -> str:
    """生成HTML内容"""
    
    # 计算通过率
    pass_rate = (passed_cases / total_cases * 100) if total_cases > 0 else 0
    
    # 生成测试用例详情HTML
    test_cases_html = ""
    for idx, log in enumerate(execution_logs, 1):
        status = log.get('status', 'unknown')
        status_class = {
            'passed': 'success',
            'failed': 'danger',
            'error': 'danger',
            'skipped': 'warning'
        }.get(status, 'secondary')
        
        test_name = log.get('test_case_name') or log.get('module') or f"测试用例 {idx}"
        output = log.get('output', '')
        error = log.get('error', '')
        
        test_cases_html += f"""
        <div class="test-case-card mb-3">
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <div>
                        <span class="badge bg-{status_class} me-2">{status.upper()}</span>
                        <strong>{test_name}</strong>
                    </div>
                    <small class="text-muted">#{idx}</small>
                </div>
                <div class="card-body">
                    {f'<div class="alert alert-danger"><strong>错误:</strong><pre class="mb-0">{error}</pre></div>' if error else ''}
                    {f'<div class="output-section"><strong>输出:</strong><pre class="output-content">{_escape_html(output)}</pre></div>' if output else ''}
                </div>
            </div>
        </div>
        """
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>测试报告 - {task_name}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        body {{
            background-color: #f5f5f5;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        }}
        .report-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem 0;
            margin-bottom: 2rem;
        }}
        .stats-card {{
            border: none;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }}
        .stats-card:hover {{
            transform: translateY(-5px);
        }}
        .stats-card.success {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        .stats-card.danger {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
        }}
        .stats-card.warning {{
            background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%);
            color: #333;
        }}
        .stats-card.info {{
            background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
            color: #333;
        }}
        .test-case-card .card {{
            border: none;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-radius: 8px;
        }}
        .test-case-card .card-header {{
            background-color: #f8f9fa;
            border-bottom: 2px solid #dee2e6;
        }}
        .output-content {{
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 1rem;
            max-height: 400px;
            overflow-y: auto;
            font-size: 0.875rem;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .progress-ring {{
            transform: rotate(-90deg);
        }}
        .progress-ring-circle {{
            transition: stroke-dashoffset 0.35s;
            transform: rotate(-90deg);
            transform-origin: 50% 50%;
        }}
        .summary-section {{
            background: white;
            border-radius: 10px;
            padding: 2rem;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }}
    </style>
</head>
<body>
    <div class="report-header">
        <div class="container">
            <h1 class="mb-2"><i class="bi bi-clipboard-check"></i> 测试执行报告</h1>
            <p class="mb-0 opacity-75">{task_name}</p>
        </div>
    </div>
    
    <div class="container">
        <!-- 统计卡片 -->
        <div class="row g-4 mb-4">
            <div class="col-md-3">
                <div class="card stats-card success h-100">
                    <div class="card-body text-center">
                        <i class="bi bi-check-circle-fill" style="font-size: 2.5rem;"></i>
                        <h2 class="mt-3 mb-0">{passed_cases}</h2>
                        <p class="mb-0">通过</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card danger h-100">
                    <div class="card-body text-center">
                        <i class="bi bi-x-circle-fill" style="font-size: 2.5rem;"></i>
                        <h2 class="mt-3 mb-0">{failed_cases}</h2>
                        <p class="mb-0">失败</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card warning h-100">
                    <div class="card-body text-center">
                        <i class="bi bi-skip-forward-circle-fill" style="font-size: 2.5rem;"></i>
                        <h2 class="mt-3 mb-0">{skipped_cases}</h2>
                        <p class="mb-0">跳过</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card info h-100">
                    <div class="card-body text-center">
                        <i class="bi bi-list-check" style="font-size: 2.5rem;"></i>
                        <h2 class="mt-3 mb-0">{total_cases}</h2>
                        <p class="mb-0">总计</p>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 摘要信息 -->
        <div class="summary-section">
            <h3 class="mb-4"><i class="bi bi-info-circle"></i> 执行摘要</h3>
            <div class="row">
                <div class="col-md-6">
                    <table class="table table-borderless">
                        <tr>
                            <td><strong>任务ID:</strong></td>
                            <td>#{task_id}</td>
                        </tr>
                        <tr>
                            <td><strong>任务名称:</strong></td>
                            <td>{task_name}</td>
                        </tr>
                        <tr>
                            <td><strong>报告类型:</strong></td>
                            <td>{report_type}</td>
                        </tr>
                        <tr>
                            <td><strong>生成时间:</strong></td>
                            <td>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td>
                        </tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <div class="text-center">
                        <h4>通过率</h4>
                        <div class="d-flex justify-content-center align-items-center">
                            <div style="width: 150px; height: 150px; position: relative;">
                                <svg class="progress-ring" width="150" height="150">
                                    <circle class="progress-ring-circle" 
                                            stroke="#667eea" 
                                            stroke-width="10" 
                                            fill="transparent" 
                                            r="60" 
                                            cx="75" 
                                            cy="75"
                                            stroke-dasharray="{2 * 3.14159 * 60}"
                                            stroke-dashoffset="{2 * 3.14159 * 60 * (1 - pass_rate / 100)}"/>
                                </svg>
                                <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);">
                                    <h2 class="mb-0">{pass_rate:.1f}%</h2>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 测试用例详情 -->
        <div class="summary-section">
            <h3 class="mb-4"><i class="bi bi-list-ul"></i> 测试用例详情</h3>
            {test_cases_html if test_cases_html else '<p class="text-muted">暂无测试用例详情</p>'}
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
    return html


def _escape_html(text: str) -> str:
    """转义HTML特殊字符"""
    if not text:
        return ""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#x27;'))


