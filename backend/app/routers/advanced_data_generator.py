from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import APIInterface, Project, User, TestEnvironment
from app.routers.auth import get_current_user_optional
from app.services.advanced_data_generator import AdvancedDataGenerator, TestDataCaseType
from app.services.context_passing import ContextPassing
from app.services.environment_manager import EnvironmentManager

router = APIRouter()


class SchemaGenerateRequest(BaseModel):
    """Schema生成请求"""
    schema: Dict[str, Any]
    constraints: Optional[Dict[str, Any]] = None
    case_type: str = "positive"  # positive, negative, boundary, invalid


class ParametrizeRequest(BaseModel):
    """参数化生成请求"""
    api_interface_id: int
    variable_params: List[str]
    case_types: Optional[List[str]] = None


class DependencyAnalysisRequest(BaseModel):
    """依赖分析请求"""
    api_interface_ids: List[int]
    project_id: int


class ContextPassingCodeRequest(BaseModel):
    """上下文传递代码生成请求"""
    api_sequence: List[Dict[str, Any]]
    project_id: int
    environment_id: Optional[int] = None


@router.post("/generate-by-schema")
async def generate_by_schema(
    request: SchemaGenerateRequest,
    current_user: User = Depends(get_current_user_optional)
):
    """根据JSON Schema生成数据"""
    generator = AdvancedDataGenerator()
    
    case_type_map = {
        "positive": TestDataCaseType.POSITIVE,
        "negative": TestDataCaseType.NEGATIVE,
        "boundary": TestDataCaseType.BOUNDARY,
        "invalid": TestDataCaseType.INVALID
    }
    
    case_type = case_type_map.get(request.case_type, TestDataCaseType.POSITIVE)
    
    data = generator.generate_by_schema(
        schema=request.schema,
        constraints=request.constraints,
        case_type=case_type
    )
    
    return {
        "status": "success",
        "data": data,
        "case_type": request.case_type
    }


@router.post("/generate-parametrized")
async def generate_parametrized_cases(
    request: ParametrizeRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成参数化测试用例"""
    # 获取API接口
    api_interface = db.query(APIInterface).filter(
        APIInterface.id == request.api_interface_id
    ).first()
    
    if not api_interface:
        raise HTTPException(status_code=404, detail="API接口不存在")
    
    # 检查权限
    project = db.query(Project).filter(
        Project.id == api_interface.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    generator = AdvancedDataGenerator()
    
    # 构建API Schema（简化处理）
    api_schema = {
        "properties": {}
    }
    
    # 解析请求体schema
    if api_interface.body:
        import json
        try:
            body = json.loads(api_interface.body) if isinstance(api_interface.body, str) else api_interface.body
            if isinstance(body, dict):
                for param in request.variable_params:
                    if param in body:
                        # 简化处理：假设是string类型
                        api_schema["properties"][param] = {"type": "string"}
        except:
            pass
    
    # 转换case_types
    case_types = None
    if request.case_types:
        case_type_map = {
            "positive": TestDataCaseType.POSITIVE,
            "negative": TestDataCaseType.NEGATIVE,
            "boundary": TestDataCaseType.BOUNDARY,
            "invalid": TestDataCaseType.INVALID
        }
        case_types = [case_type_map.get(ct, TestDataCaseType.POSITIVE) for ct in request.case_types]
    
    # 生成测试用例
    test_cases = generator.generate_parametrized_cases(
        api_schema=api_schema,
        variable_params=request.variable_params,
        case_types=case_types
    )
    
    # 生成pytest代码
    code = generator.generate_pytest_parametrize_code(
        variable_params=request.variable_params,
        test_cases=test_cases,
        test_function_name=f"test_{api_interface.name.replace(' ', '_')}"
    )
    
    return {
        "status": "success",
        "test_cases": test_cases,
        "code": code
    }


@router.post("/analyze-dependencies")
async def analyze_dependencies(
    request: DependencyAnalysisRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """分析API接口间的依赖关系"""
    # 验证项目权限
    project = db.query(Project).filter(
        Project.id == request.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    # 获取API接口列表
    api_interfaces = db.query(APIInterface).filter(
        APIInterface.id.in_(request.api_interface_ids),
        APIInterface.project_id == request.project_id
    ).all()
    
    if not api_interfaces:
        raise HTTPException(status_code=404, detail="未找到API接口")
    
    # 转换为字典格式
    api_dicts = []
    for api in api_interfaces:
        import json
        api_dict = {
            "id": api.id,
            "name": api.name,
            "method": api.method,
            "path": api.url or api.path,
            "headers": json.loads(api.headers) if api.headers else {},
            "params": json.loads(api.params) if api.params else {},
            "body": json.loads(api.body) if api.body else (api.body if api.body else {}),
            "response_schema": json.loads(api.response_schema) if api.response_schema else {}
        }
        api_dicts.append(api_dict)
    
    # 分析依赖
    context_passing = ContextPassing()
    dependencies = context_passing.identify_dependencies(api_dicts)
    
    return {
        "status": "success",
        "dependencies": dependencies
    }


@router.post("/generate-context-passing-code")
async def generate_context_passing_code(
    request: ContextPassingCodeRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成上下文传递代码"""
    # 验证项目权限
    project = db.query(Project).filter(
        Project.id == request.project_id,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="无权访问")
    
    # 分析依赖
    context_passing = ContextPassing()
    dependencies = context_passing.identify_dependencies(request.api_sequence)
    
    # 生成代码
    code = context_passing.generate_context_passing_code(
        api_sequence=request.api_sequence,
        dependencies=dependencies
    )
    
    # 如果有环境配置，添加环境信息
    env_info = ""
    if request.environment_id:
        env_manager = EnvironmentManager(db)
        environment = env_manager.get_environment(request.environment_id, current_user.id)
        if environment:
            env_info = f"""
# 环境配置
ENVIRONMENT = "{environment.name}"
BASE_URL = "{environment.base_url}"
"""
            code = env_info + "\n" + code
    
    return {
        "status": "success",
        "code": code,
        "dependencies": dependencies
    }


@router.get("/environment-config/{environment_id}")
async def get_environment_config(
    environment_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取环境配置"""
    env_manager = EnvironmentManager(db)
    config = env_manager.get_environment_config(environment_id, current_user.id)
    
    if not config:
        raise HTTPException(status_code=404, detail="环境不存在")
    
    return {
        "status": "success",
        "config": config
    }









































