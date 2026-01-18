from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import APIInterface, Project, User
from app.routers.auth import get_current_user_optional
from app.services.request_builder import RequestBuilder, ContentType
from app.services.prompt_engineer import PromptEngineer

router = APIRouter()


class RequestBuildRequest(BaseModel):
    """请求构造请求"""
    method: str
    base_url: str
    path: str
    path_params: Optional[Dict[str, Any]] = None
    query_params: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, Any]] = None
    body: Optional[Any] = None
    content_type: Optional[str] = None
    auth_config: Optional[Dict[str, Any]] = None


class CodeGenerationRequest(BaseModel):
    """代码生成请求"""
    api_interface_id: Optional[int] = None
    method: Optional[str] = None
    base_url: Optional[str] = None
    path: Optional[str] = None
    path_params: Optional[Dict[str, Any]] = None
    query_params: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, Any]] = None
    body: Optional[Any] = None
    content_type: Optional[str] = None
    auth_config: Optional[Dict[str, Any]] = None
    language: str = "python"
    framework: str = "httprunner"
    use_llm: bool = False


class SecuritySchemesParseRequest(BaseModel):
    """安全方案解析请求"""
    openapi_doc: Dict[str, Any]


@router.post("/build")
async def build_request(
    request: RequestBuildRequest,
    current_user: User = Depends(get_current_user_optional)
):
    """构造HTTP请求"""
    builder = RequestBuilder()
    
    request_info = builder.build_request(
        method=request.method,
        base_url=request.base_url,
        path=request.path,
        path_params=request.path_params,
        query_params=request.query_params,
        headers=request.headers,
        body=request.body,
        content_type=request.content_type,
        auth_config=request.auth_config
    )
    
    return {
        "status": "success",
        "request": request_info
    }


@router.post("/generate-code")
async def generate_request_code(
    request: CodeGenerationRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成请求代码"""
    builder = RequestBuilder()
    prompt_engineer = PromptEngineer()
    
    # 如果提供了api_interface_id，从数据库获取
    if request.api_interface_id:
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
        
        # 从数据库接口构造请求（统一使用模型字段）
        import json
        method = api_interface.method or request.method or "GET"
        base_url = request.base_url or ""
        path = api_interface.url or request.path or ""
        path_params = request.path_params or {}
        query_params = json.loads(api_interface.params) if api_interface.params else (request.query_params or {})
        headers = json.loads(api_interface.headers) if api_interface.headers else (request.headers or {})
        body = None
        if api_interface.body:
            try:
                body = json.loads(api_interface.body)
            except:
                body = api_interface.body
        content_type = request.content_type
        
        # 构建请求
        request_info = builder.build_request(
            method=method,
            base_url=base_url,
            path=path,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            body=body or request.body,
            content_type=content_type,
            auth_config=request.auth_config
        )
    else:
        # 直接使用请求参数
        if not all([request.method, request.base_url, request.path]):
            raise HTTPException(status_code=400, detail="缺少必要参数")
        
        request_info = builder.build_request(
            method=request.method,
            base_url=request.base_url,
            path=request.path,
            path_params=request.path_params,
            query_params=request.query_params,
            headers=request.headers,
            body=request.body,
            content_type=request.content_type,
            auth_config=request.auth_config
        )
    
    # 生成代码
    code = builder.generate_request_code(
        request=request_info,
        language=request.language,
        framework=request.framework
    )
    
    # 如果使用LLM生成
    if request.use_llm:
        try:
            from app.services.llm_service import LLMService
            llm_service = LLMService()
            
            # 构建Prompt
            api_interface_dict = {
                "name": "API接口",
                "method": request_info["method"],
                "url": request_info["url"],
                "path": request_info["path"],
                "headers": request_info["headers"],
                "params": request_info.get("query_params", {}),
                "body": request_info.get("body"),
                "description": "通过请求构造生成"
            }
            
            prompt = prompt_engineer.build_code_generation_prompt(
                api_interface=api_interface_dict,
                framework=request.framework,
                language=request.language
            )
            
            generated_code = llm_service.chat(
                prompt,
                temperature=0.3,
                max_tokens=2000
            )
            
            # 清理代码
            if generated_code.startswith("```python"):
                generated_code = generated_code.replace("```python", "").replace("```", "").strip()
            elif generated_code.startswith("```"):
                generated_code = generated_code.replace("```", "").strip()
            
            code = generated_code
        except Exception as e:
            # LLM生成失败，使用传统方式
            pass
    
    return {
        "status": "success",
        "code": code,
        "request_info": request_info,
        "language": request.language,
        "framework": request.framework
    }


@router.post("/parse-security-schemes")
async def parse_security_schemes(
    request: SecuritySchemesParseRequest,
    current_user: User = Depends(get_current_user_optional)
):
    """从OpenAPI文档解析securitySchemes"""
    builder = RequestBuilder()
    
    security_schemes = builder.parse_security_schemes(request.openapi_doc)
    
    return {
        "status": "success",
        "security_schemes": security_schemes
    }


@router.post("/apply-security")
async def apply_security_to_request(
    request_build_request: RequestBuildRequest,
    scheme_name: str,
    auth_value: str,
    current_user: User = Depends(get_current_user_optional)
):
    """将认证配置应用到请求"""
    builder = RequestBuilder()
    
    # 构建请求
    request_info = builder.build_request(
        method=request_build_request.method,
        base_url=request_build_request.base_url,
        path=request_build_request.path,
        path_params=request_build_request.path_params,
        query_params=request_build_request.query_params,
        headers=request_build_request.headers,
        body=request_build_request.body,
        content_type=request_build_request.content_type
    )
    
    # 如果提供了auth_config，直接使用
    if request_build_request.auth_config:
        request_info = builder.build_request(
            method=request_build_request.method,
            base_url=request_build_request.base_url,
            path=request_build_request.path,
            path_params=request_build_request.path_params,
            query_params=request_build_request.query_params,
            headers=request_build_request.headers,
            body=request_build_request.body,
            content_type=request_build_request.content_type,
            auth_config=request_build_request.auth_config
        )
    else:
        # 需要从OpenAPI文档解析securitySchemes（这里简化处理）
        # 实际使用中应该传入完整的security_schemes
        pass
    
    return {
        "status": "success",
        "request": request_info
    }


