"""
CI/CD集成与自动化流程API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from app.database import get_db
from app.models import Project, User, TestCase, TestTask, TestCaseSuite
from app.routers.auth import get_current_user_optional
from app.services.test_command_builder import TestCommandBuilder
from app.services.cicd_config_generator import CICDConfigGenerator

router = APIRouter()

command_builder = TestCommandBuilder()
config_generator = CICDConfigGenerator()


class TestCommandRequest(BaseModel):
    """测试命令生成请求"""
    test_case_ids: Optional[List[int]] = None
    test_case_files: Optional[List[str]] = None
    test_suite_id: Optional[int] = None
    test_module: Optional[str] = None
    environment: Optional[str] = None
    framework: str = "httprunner"
    report_format: str = "allure"
    parallel: bool = False
    workers: int = 4
    verbose: bool = False
    max_failures: Optional[int] = None
    markers: Optional[str] = None
    coverage: bool = False


class CICDConfigRequest(BaseModel):
    """CI/CD配置生成请求"""
    platform: str  # jenkins, github_actions, gitlab_ci
    project_name: str
    python_version: str = "3.9"
    node_version: Optional[str] = None
    workflow_name: Optional[str] = None
    trigger_branches: Optional[List[str]] = None
    test_command_config: Optional[Dict[str, Any]] = None
    # 如果test_command_config为空，则使用以下参数构建
    test_case_ids: Optional[List[int]] = None
    test_suite_id: Optional[int] = None
    test_module: Optional[str] = None
    environment: Optional[str] = None
    framework: str = "httprunner"
    report_format: str = "allure"
    parallel: bool = False


@router.post("/test-command")
async def generate_test_command(
    request: TestCommandRequest,
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成测试执行命令"""
    # 验证项目权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 验证测试套件（如果提供）
    if request.test_suite_id:
        suite = db.query(TestCaseSuite).filter(
            TestCaseSuite.id == request.test_suite_id,
            TestCaseSuite.project_id == project_id
        ).first()
        if not suite:
            raise HTTPException(status_code=404, detail="Test case suite not found")
        
        # 解析用例ID列表
        import json
        if suite.test_case_ids:
            case_ids = json.loads(suite.test_case_ids)
            request.test_case_ids = case_ids
    
    # 验证测试用例（如果提供）
    if request.test_case_ids:
        cases = db.query(TestCase).filter(
            TestCase.id.in_(request.test_case_ids),
            TestCase.project_id == project_id
        ).all()
        if len(cases) != len(request.test_case_ids):
            raise HTTPException(status_code=404, detail="Some test cases not found")
    
    # 生成命令
    command_config = command_builder.build_test_command(
        test_case_ids=request.test_case_ids,
        test_case_files=request.test_case_files,
        test_module=request.test_module,
        environment=request.environment,
        framework=request.framework,
        report_format=request.report_format,
        parallel=request.parallel,
        workers=request.workers,
        verbose=request.verbose,
        max_failures=request.max_failures,
        markers=request.markers,
        coverage=request.coverage
    )
    
    # 生成Shell脚本（可选）
    shell_script = command_builder.generate_shell_script(command_config)
    
    return {
        "command_config": command_config,
        "shell_script": shell_script,
        "usage": {
            "direct_command": command_config.get("command_with_env", command_config.get("command")),
            "shell_script": "Save shell_script content to run_tests.sh and execute: bash run_tests.sh"
        }
    }


@router.post("/cicd-config")
async def generate_cicd_config(
    request: CICDConfigRequest,
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成CI/CD配置文件"""
    # 验证项目权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 如果没有提供test_command_config，则构建一个
    if not request.test_command_config:
        # 验证测试套件（如果提供）
        if request.test_suite_id:
            suite = db.query(TestCaseSuite).filter(
                TestCaseSuite.id == request.test_suite_id,
                TestCaseSuite.project_id == project_id
            ).first()
            if not suite:
                raise HTTPException(status_code=404, detail="Test case suite not found")
            
            import json
            if suite.test_case_ids:
                request.test_case_ids = json.loads(suite.test_case_ids)
        
        # 构建测试命令配置
        test_command_config = command_builder.build_test_command(
            test_case_ids=request.test_case_ids,
            test_suite_id=request.test_suite_id,
            test_module=request.test_module,
            environment=request.environment,
            framework=request.framework,
            report_format=request.report_format,
            parallel=request.parallel
        )
    else:
        test_command_config = request.test_command_config
    
    # 生成CI/CD配置
    config = config_generator.generate_config(
        platform=request.platform,
        project_name=request.project_name or project.name,
        test_command_config=test_command_config,
        python_version=request.python_version,
        node_version=request.node_version,
        workflow_name=request.workflow_name,
        trigger_branches=request.trigger_branches or ["main", "develop"]
    )
    
    return {
        "config": config,
        "usage": {
            "filename": config["filename"],
            "save_path": config["filename"],
            "instructions": _get_platform_instructions(request.platform)
        }
    }


@router.post("/cicd-configs")
async def generate_multiple_cicd_configs(
    platforms: List[str],
    project_id: int,
    project_name: Optional[str] = None,
    python_version: str = "3.9",
    test_case_ids: Optional[List[int]] = None,
    test_suite_id: Optional[int] = None,
    test_module: Optional[str] = None,
    environment: Optional[str] = None,
    framework: str = "httprunner",
    report_format: str = "allure",
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成多个平台的CI/CD配置"""
    # 验证项目权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 构建测试命令配置
    test_command_config = command_builder.build_test_command(
        test_case_ids=test_case_ids,
        test_suite_id=test_suite_id,
        test_module=test_module,
        environment=environment,
        framework=framework,
        report_format=report_format
    )
    
    # 生成所有平台的配置
    configs = config_generator.generate_multiple_configs(
        project_name=project_name or project.name,
        test_command_config=test_command_config,
        platforms=platforms,
        python_version=python_version
    )
    
    return {
        "configs": configs,
        "usage": "Save each config['content'] to the corresponding config['filename']"
    }


@router.post("/shell-script")
async def generate_shell_script(
    request: TestCommandRequest,
    project_id: int,
    script_name: str = "run_tests.sh",
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成测试执行Shell脚本"""
    # 验证项目权限
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 生成命令配置
    command_config = command_builder.build_test_command(
        test_case_ids=request.test_case_ids,
        test_case_files=request.test_case_files,
        test_suite_id=request.test_suite_id,
        test_module=request.test_module,
        environment=request.environment,
        framework=request.framework,
        report_format=request.report_format,
        parallel=request.parallel,
        workers=request.workers,
        verbose=request.verbose,
        max_failures=request.max_failures,
        markers=request.markers,
        coverage=request.coverage
    )
    
    # 生成Shell脚本
    shell_script = command_builder.generate_shell_script(command_config, script_name)
    
    return {
        "script_name": script_name,
        "script_content": shell_script,
        "usage": f"Save this content to {script_name} and make it executable: chmod +x {script_name} && ./{script_name}"
    }


@router.get("/report-config")
async def get_report_config(
    report_format: str = "allure",
    current_user: User = Depends(get_current_user_optional)
):
    """获取报告配置说明"""
    configs = {
        "allure": {
            "description": "Allure测试报告",
            "installation": "pip install allure-pytest",
            "generation_command": "allure generate reports/allure-results -o reports/allure-report --clean",
            "view_command": "allure open reports/allure-report",
            "ci_integration": {
                "jenkins": "使用Allure插件",
                "github_actions": "使用simple-elf/allure-report-action",
                "gitlab_ci": "使用allure-docker-service"
            }
        },
        "junit": {
            "description": "JUnit XML格式报告",
            "installation": "pip install pytest (内置支持)",
            "generation_command": "pytest --junit-xml=reports/junit.xml tests/",
            "view_command": "在CI/CD平台查看",
            "ci_integration": {
                "jenkins": "使用JUnit插件",
                "github_actions": "使用EnricoMi/publish-unit-test-result-action",
                "gitlab_ci": "在artifacts.reports中配置"
            }
        },
        "html": {
            "description": "HTML格式报告",
            "installation": "pip install pytest-html",
            "generation_command": "pytest --html=reports/report.html --self-contained-html tests/",
            "view_command": "在浏览器中打开reports/report.html",
            "ci_integration": {
                "jenkins": "发布HTML报告",
                "github_actions": "上传为artifact",
                "gitlab_ci": "在artifacts.paths中配置"
            }
        }
    }
    
    if report_format not in configs:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的报告格式: {report_format}. 支持的格式: {', '.join(configs.keys())}"
        )
    
    return {
        "format": report_format,
        "config": configs[report_format]
    }


def _get_platform_instructions(platform: str) -> str:
    """获取平台特定的使用说明"""
    instructions = {
        "jenkins": """
1. 将生成的Jenkinsfile保存到项目根目录
2. 在Jenkins中创建Pipeline项目
3. 配置SCM为Git，指向项目仓库
4. Jenkins会自动识别Jenkinsfile并执行
        """,
        "github_actions": """
1. 将生成的YAML文件保存到 .github/workflows/ 目录
2. 文件名可以是任意.yml或.yaml文件
3. 推送到GitHub后会自动触发工作流
4. 也可以手动在Actions标签页触发
        """,
        "gitlab_ci": """
1. 将生成的.gitlab-ci.yml保存到项目根目录
2. GitLab会自动检测并执行CI/CD流程
3. 可以在GitLab项目的CI/CD设置中配置Runner
4. 查看Pipeline结果和报告
        """
    }
    return instructions.get(platform, "请参考相应平台的文档")

