from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json
import redis
from datetime import datetime

from app.database import get_db
from app.models import TestCaseSuite, Project, User, TestCase, DocumentAPIInterface, TestEnvironment
from app.routers.auth import get_current_user_optional
from app.config import settings
from app.services.optimized_dependency_analyzer import OptimizedDependencyAnalyzer
from app.services.db_service import DatabaseService
from fastapi import Body

# Redis连接
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    db=0,
    decode_responses=True,
    encoding='utf-8'
)

router = APIRouter()


class TestCaseSuiteCreate(BaseModel):
    name: str
    description: Optional[str] = None
    test_case_ids: List[int]
    tags: Optional[str] = None  # 逗号分隔的标签


class TestCaseSuiteUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    test_case_ids: Optional[List[Any]] = None  # 支持字符串和整数ID
    tags: Optional[str] = None


class BatchDeleteSuitesRequest(BaseModel):
    suite_ids: List[int]


@router.post("/")
async def create_test_case_suite(
    project_id: int,
    suite: TestCaseSuiteCreate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """创建测试用例集合"""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 验证用例存在
    if suite.test_case_ids:
        valid_cases = db.query(TestCase).filter(
            TestCase.id.in_(suite.test_case_ids),
            TestCase.project_id == project_id
        ).all()
        
        if len(valid_cases) != len(suite.test_case_ids):
            raise HTTPException(status_code=400, detail="部分测试用例不存在")
    
    db_suite = TestCaseSuite(
        project_id=project_id,
        name=suite.name,
        description=suite.description,
        test_case_ids=json.dumps(suite.test_case_ids) if suite.test_case_ids else "[]",
        tags=suite.tags
    )
    db.add(db_suite)
    db.commit()
    db.refresh(db_suite)
    
    return db_suite


@router.get("/")
async def list_test_case_suites(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    获取测试用例集合列表（优化版本：优先从Redis读取）
    分析完成后，场景用例集已保存到Redis、ChromaDB、Neo4j，优先从Redis读取以提高性能
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 直接从数据库读取，确保返回的ID为真实数据库ID，避免后续操作404
    suites = db.query(TestCaseSuite).filter(
        TestCaseSuite.project_id == project_id
    ).order_by(TestCaseSuite.created_at.desc()).all()
    
    result = []
    for suite in suites:
        case_ids = json.loads(suite.test_case_ids) if suite.test_case_ids else []
        result.append({
            "id": suite.id,
            "name": suite.name,
            "description": suite.description,
            "test_case_ids": case_ids,
            "test_case_count": len(case_ids),
            "tags": suite.tags,
            "created_at": suite.created_at.isoformat() if suite.created_at else None,
            "updated_at": suite.updated_at.isoformat() if suite.updated_at else None
        })
    
    return result


def _is_response_body_valid(response_body: Any) -> bool:
    """检查响应体是否有效（不为空且不是空JSON）"""
    if not response_body:
        return False
    
    if isinstance(response_body, str):
        try:
            parsed = json.loads(response_body)
            if isinstance(parsed, dict):
                return len(parsed) > 0
            elif isinstance(parsed, str):
                return len(parsed.strip()) > 0
            else:
                return parsed is not None
        except:
            return len(response_body.strip()) > 0
    
    if isinstance(response_body, dict):
        return len(response_body) > 0
    
    return True


def _fill_request_parameters(
    interface: Dict[str, Any],
    dependency_chain: List[Dict[str, Any]],
    few_shot_example: Optional[Dict[str, Any]],
    default_env: Optional[TestEnvironment],
    analyzer: OptimizedDependencyAnalyzer
) -> Dict[str, Any]:
    """填充接口的请求参数
    1. 优先从few-shot示例中查找相似接口的请求参数
    2. 不再从环境变量读取xjid、用户名、密码
    3. 如果few-shot没有，根据CRUD顺序填充（CREATE→READ→UPDATE→DELETE）
    """
    interface_copy = interface.copy()
    
    # 获取请求体和参数
    request_body = interface_copy.get('request_body', {})
    if isinstance(request_body, str):
        try:
            request_body = json.loads(request_body)
        except:
            request_body = {}
    if not isinstance(request_body, dict):
        request_body = {}
    
    params = interface_copy.get('params', {})
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except:
            params = {}
    if not isinstance(params, dict):
        params = {}
    
    # 不再从环境变量获取xjid、用户名、密码
    xjid_value = None
    username_value = None
    password_value = None
    
    # 1. 优先从few-shot示例中查找相似接口
    similar_interface = None
    if few_shot_example and few_shot_example.get('interfaces'):
        few_shot_interfaces = few_shot_example.get('interfaces', [])
        
        # 计算相似度，找到最相似的接口
        max_similarity = 0.0
        for fs_interface in few_shot_interfaces:
            similarity = analyzer._calculate_interface_similarity(interface, fs_interface)
            if similarity > max_similarity:
                max_similarity = similarity
                similar_interface = fs_interface
        
        # 如果找到相似接口（相似度>0.3），使用其请求参数作为参考
        if similar_interface and max_similarity > 0.3:
            print(f"从few-shot中找到相似接口（相似度: {max_similarity:.2f}）: {similar_interface.get('name', 'N/A')}")
            fs_request_body = similar_interface.get('request_body', {})
            if isinstance(fs_request_body, str):
                try:
                    fs_request_body = json.loads(fs_request_body)
                except:
                    fs_request_body = {}
            if isinstance(fs_request_body, dict):
                # 复制请求参数（但排除xjid、用户名、密码，这些从环境变量读取）
                for key, value in fs_request_body.items():
                    if key not in ['xjid', 'phone', 'username', 'pwd', 'password'] and key not in request_body:
                        request_body[key] = value
    
    # 2. 如果没有few-shot或相似度不高，根据CRUD顺序填充
    if not similar_interface or max_similarity <= 0.3:
        crud_type = analyzer._extract_crud_type(interface)
        
        # 根据CRUD类型填充基础参数
        if crud_type == 'CREATE':
            # 创建操作：通常需要基础数据字段
            if 'name' not in request_body:
                request_body['name'] = "测试数据"
            if 'title' not in request_body:
                request_body['title'] = "测试标题"
        elif crud_type == 'UPDATE':
            # 更新操作：需要ID和要更新的字段
            # 查找前面CREATE操作创建的ID
            for prev_interface in dependency_chain:
                if prev_interface.get('is_login'):
                    continue
                prev_crud = analyzer._extract_crud_type(prev_interface)
                if prev_crud == 'CREATE':
                    # 尝试从前一个接口的响应中提取ID
                    prev_response = prev_interface.get('response_body', {})
                    if isinstance(prev_response, dict):
                        # 常见的ID字段
                        for id_field in ['id', 'data_id', 'record_id', 'item_id']:
                            if id_field in prev_response:
                                request_body['id'] = prev_response[id_field]
                                break
                            elif 'data' in prev_response and isinstance(prev_response['data'], dict):
                                if id_field in prev_response['data']:
                                    request_body['id'] = prev_response['data'][id_field]
                                    break
        elif crud_type == 'READ':
            # 查询操作：通常需要ID或查询条件
            # 查找前面CREATE操作创建的ID
            for prev_interface in dependency_chain:
                if prev_interface.get('is_login'):
                    continue
                prev_crud = analyzer._extract_crud_type(prev_interface)
                if prev_crud == 'CREATE':
                    prev_response = prev_interface.get('response_body', {})
                    if isinstance(prev_response, dict):
                        for id_field in ['id', 'data_id', 'record_id', 'item_id']:
                            if id_field in prev_response:
                                request_body['id'] = prev_response[id_field]
                                break
                            elif 'data' in prev_response and isinstance(prev_response['data'], dict):
                                if id_field in prev_response['data']:
                                    request_body['id'] = prev_response['data'][id_field]
                                    break
        elif crud_type == 'DELETE':
            # 删除操作：需要ID
            for prev_interface in dependency_chain:
                if prev_interface.get('is_login'):
                    continue
                prev_crud = analyzer._extract_crud_type(prev_interface)
                if prev_crud == 'CREATE':
                    prev_response = prev_interface.get('response_body', {})
                    if isinstance(prev_response, dict):
                        for id_field in ['id', 'data_id', 'record_id', 'item_id']:
                            if id_field in prev_response:
                                request_body['id'] = prev_response[id_field]
                                break
                            elif 'data' in prev_response and isinstance(prev_response['data'], dict):
                                if id_field in prev_response['data']:
                                    request_body['id'] = prev_response['data'][id_field]
                                    break
    
    # 3. 填充xjid、用户名、密码（从环境变量，必须覆盖任何其他值）
    if xjid_value:
        # 如果请求体中有xjid字段，用环境变量的值覆盖
        if 'xjid' in request_body:
            request_body['xjid'] = xjid_value
        # 如果请求体中没有xjid字段，但接口可能需要，检查params中是否有
        elif 'xjid' in params:
            params['xjid'] = xjid_value
    
    if username_value:
        # 支持多种用户名字段名，必须覆盖任何其他值
        for username_field in ['phone', 'username', 'user_name', 'account']:
            if username_field in request_body:
                request_body[username_field] = username_value
                break
            elif username_field in params:
                params[username_field] = username_value
                break
    
    if password_value:
        # 支持多种密码字段名，必须覆盖任何其他值
        for password_field in ['pwd', 'password', 'passwd']:
            if password_field in request_body:
                request_body[password_field] = password_value
                break
            elif password_field in params:
                params[password_field] = password_value
                break
    
    # 更新接口的请求体
    interface_copy['request_body'] = request_body
    interface_copy['params'] = params
    
    return interface_copy


def _get_interface_from_redis_or_db(interface_id: str, project_id: int, db: Session) -> Optional[Dict[str, Any]]:
    """从Redis或数据库获取接口信息（优先Redis）
    
    interface_id 可能是：
    1. 接口ID（数字，如 123）
    2. 接口ID字符串（如 "api_123"）
    3. 接口名称（如 "接口1-手机注册"）- 兼容旧数据
    """
    # 尝试从Redis获取（从document_api_interfaces表的Redis缓存中）
    try:
        doc_interface = None
        doc_interface_id = None
        
        # 优先处理接口ID格式
        if isinstance(interface_id, str) and interface_id.startswith('api_'):
            # 格式：api_123 -> 提取数字ID
            try:
                doc_interface_id = int(interface_id.replace('api_', ''))
            except ValueError:
                pass
        elif isinstance(interface_id, (int, str)):
            try:
                # 尝试作为数字ID
                doc_interface_id = int(interface_id)
            except (ValueError, TypeError):
                # 不是数字，可能是接口名称（兼容旧数据）
                interface_name = str(interface_id)
                
                # 处理"接口XX-接口名称"格式，提取实际的接口名称
                # 例如："接口1-手机注册" -> "手机注册"
                import re
                name_match = re.match(r'接口\d+[-]?(.*)', interface_name)
                if name_match:
                    actual_name = name_match.group(1).strip()
                else:
                    actual_name = interface_name
                
                # 首先尝试精确匹配（使用提取的名称）
                doc_interface = db.query(DocumentAPIInterface).filter(
                    DocumentAPIInterface.name == actual_name,
                    DocumentAPIInterface.project_id == project_id
                ).first()
                
                # 如果精确匹配失败，尝试匹配原始名称
                if not doc_interface:
                    doc_interface = db.query(DocumentAPIInterface).filter(
                        DocumentAPIInterface.name == interface_name,
                        DocumentAPIInterface.project_id == project_id
                    ).first()
                
                # 如果还是找不到，尝试模糊匹配（包含该名称）
                if not doc_interface:
                    doc_interface = db.query(DocumentAPIInterface).filter(
                        DocumentAPIInterface.name.like(f'%{actual_name}%'),
                        DocumentAPIInterface.project_id == project_id
                    ).first()
        
        # 如果通过接口ID找到了doc_interface_id，通过ID查询
        if doc_interface_id and not doc_interface:
            doc_interface = db.query(DocumentAPIInterface).filter(
                DocumentAPIInterface.id == doc_interface_id,
                DocumentAPIInterface.project_id == project_id
            ).first()
        
        if not doc_interface:
            print(f"未找到接口: {interface_id} (project_id: {project_id}, 尝试的ID: {doc_interface_id})")
            return None
        
        # 使用找到的接口的ID（这是数据库中的实际ID）
        actual_interface_id = doc_interface.id
        
        # 尝试从Redis获取（更快）
        redis_key = f"file:{doc_interface.document_id}:api_interfaces"
        redis_data = redis_client.get(redis_key)
        if redis_data:
            try:
                interfaces_list = json.loads(redis_data)
                # 在Redis中查找对应的接口（使用实际的接口ID）
                for iface in interfaces_list:
                    if str(iface.get('id')) == str(actual_interface_id):
                        # 不再检查响应体是否有效，允许响应体为空的接口
                        # 确保所有字段都存在，如果Redis中没有，使用数据库的值
                        # 解析headers
                        redis_headers = iface.get('headers', {})
                        if isinstance(redis_headers, str):
                            try:
                                redis_headers = json.loads(redis_headers)
                            except:
                                redis_headers = {}
                        if not redis_headers or (isinstance(redis_headers, dict) and len(redis_headers) == 0):
                            # 从数据库获取
                            if doc_interface.headers:
                                try:
                                    redis_headers = json.loads(doc_interface.headers) if isinstance(doc_interface.headers, str) else doc_interface.headers
                                except:
                                    redis_headers = {}
                            if not redis_headers or (isinstance(redis_headers, dict) and len(redis_headers) == 0):
                                redis_headers = {"Content-Type": "application/json", "Accept": "application/json"}
                        iface['headers'] = redis_headers
                        
                        # 解析request_body
                        redis_request_body = iface.get('request_body', {})
                        if isinstance(redis_request_body, str):
                            try:
                                redis_request_body = json.loads(redis_request_body)
                            except:
                                redis_request_body = {}
                        if not redis_request_body or (isinstance(redis_request_body, dict) and len(redis_request_body) == 0):
                            # 从数据库获取
                            if doc_interface.request_body:
                                try:
                                    redis_request_body = json.loads(doc_interface.request_body) if isinstance(doc_interface.request_body, str) else doc_interface.request_body
                                except:
                                    redis_request_body = {}
                        iface['request_body'] = redis_request_body
                        
                        # 解析response_headers
                        redis_response_headers = iface.get('response_headers', {})
                        if isinstance(redis_response_headers, str):
                            try:
                                redis_response_headers = json.loads(redis_response_headers)
                            except:
                                redis_response_headers = {}
                        if not redis_response_headers or (isinstance(redis_response_headers, dict) and len(redis_response_headers) == 0):
                            # 从数据库获取
                            if doc_interface.response_headers:
                                try:
                                    redis_response_headers = json.loads(doc_interface.response_headers) if isinstance(doc_interface.response_headers, str) else doc_interface.response_headers
                                except:
                                    redis_response_headers = {}
                            if not redis_response_headers or (isinstance(redis_response_headers, dict) and len(redis_response_headers) == 0):
                                redis_response_headers = {"Content-Type": "application/json"}
                        iface['response_headers'] = redis_response_headers
                        
                        # 确保base_url有值
                        if not iface.get('base_url'):
                            iface['base_url'] = doc_interface.base_url or ""
                            if not iface['base_url'] and doc_interface.url:
                                try:
                                    from urllib.parse import urlparse
                                    parsed = urlparse(doc_interface.url)
                                    iface['base_url'] = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
                                except:
                                    pass
                        
                        # 确保path有值
                        if not iface.get('path'):
                            iface['path'] = doc_interface.path or ""
                            if not iface['path'] and doc_interface.url:
                                try:
                                    from urllib.parse import urlparse
                                    parsed = urlparse(doc_interface.url)
                                    iface['path'] = parsed.path
                                    if parsed.query:
                                        iface['path'] = f"{iface['path']}?{parsed.query}"
                                except:
                                    pass
                        
                        return iface
            except Exception as e:
                print(f"从Redis获取接口失败: {e}")
                pass
        
        # 检查响应体（从数据库）
        # 注意：不再因为响应体为空就过滤接口，允许响应体为空的接口用于生成测试用例
        # 响应体为空时，后续会使用默认值 {"status": "success", "message": "请求成功"}
        response_body = None
        if doc_interface.response_body:
            try:
                body_str = str(doc_interface.response_body)
                if '<' in body_str and '>' in body_str:
                    import re
                    json_match = re.search(r'\{.*\}', body_str, re.DOTALL)
                    if json_match:
                        body_str = json_match.group(0)
                response_body = json.loads(body_str)
                if not isinstance(response_body, dict):
                    response_body = {"raw": str(response_body)}
            except:
                response_body = {}
        
        # 不再过滤响应体为空的接口，允许它们用于生成测试用例
        # 如果响应体为空，后续处理会使用默认值
        
        # 如果Redis中没有，从数据库构建完整的接口信息
        # 安全解析JSON字段
        headers = {}
        if doc_interface.headers:
            try:
                headers = json.loads(doc_interface.headers) if isinstance(doc_interface.headers, str) else doc_interface.headers
            except:
                try:
                    headers = json.loads(doc_interface.headers) if doc_interface.headers else {}
                except:
                    headers = {}
        
        params = {}
        if doc_interface.params:
            try:
                params = json.loads(doc_interface.params) if isinstance(doc_interface.params, str) else doc_interface.params
            except:
                try:
                    params = json.loads(doc_interface.params) if doc_interface.params else {}
                except:
                    params = {}
        
        request_body = {}
        if doc_interface.request_body:
            try:
                if isinstance(doc_interface.request_body, str):
                    request_body = json.loads(doc_interface.request_body)
                else:
                    request_body = doc_interface.request_body
            except:
                try:
                    # 尝试解析字符串
                    body_str = str(doc_interface.request_body)
                    request_body = json.loads(body_str)
                except:
                    request_body = {}
        
        response_headers = {}
        if doc_interface.response_headers:
            try:
                if isinstance(doc_interface.response_headers, str):
                    response_headers = json.loads(doc_interface.response_headers)
                else:
                    response_headers = doc_interface.response_headers
            except:
                try:
                    response_headers = json.loads(doc_interface.response_headers) if doc_interface.response_headers else {}
                except:
                    response_headers = {}
        
        response_schema = {}
        if doc_interface.response_schema:
            try:
                response_schema = json.loads(doc_interface.response_schema) if isinstance(doc_interface.response_schema, str) else doc_interface.response_schema
            except:
                try:
                    response_schema = json.loads(doc_interface.response_schema) if doc_interface.response_schema else {}
                except:
                    response_schema = {}
        
        tags = []
        if doc_interface.tags:
            try:
                tags = json.loads(doc_interface.tags) if isinstance(doc_interface.tags, str) else doc_interface.tags
            except:
                try:
                    tags = json.loads(doc_interface.tags) if doc_interface.tags else []
                except:
                    tags = []
        
        # 确保base_url有值
        base_url = doc_interface.base_url or ""
        if not base_url and doc_interface.url:
            # 如果没有base_url，尝试从url中提取
            try:
                from urllib.parse import urlparse
                parsed = urlparse(doc_interface.url)
                base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
            except:
                pass
        
        # 确保path有值（从url中提取）
        path = doc_interface.path or ""
        if not path and doc_interface.url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(doc_interface.url)
                path = parsed.path
                if parsed.query:
                    path = f"{path}?{parsed.query}"
            except:
                pass
        
        # 确保headers不为空（至少有一个默认值）
        if not headers or (isinstance(headers, dict) and len(headers) == 0):
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        
        # 确保request_body不为空（至少有一个默认值）
        if not request_body or (isinstance(request_body, dict) and len(request_body) == 0):
            request_body = {}
        
        # 确保response_headers不为空（至少有一个默认值）
        if not response_headers or (isinstance(response_headers, dict) and len(response_headers) == 0):
            response_headers = {
                "Content-Type": "application/json"
            }
        
        # 确保response_body不为空（至少有一个默认值）
        if not response_body or (isinstance(response_body, dict) and len(response_body) == 0):
            response_body = {
                "status": "success",
                "message": "请求成功"
            }
        
        return {
            "id": actual_interface_id,
            "interface_id": str(actual_interface_id),
            "name": doc_interface.name or "",
            "title": doc_interface.name or "",
            "method": doc_interface.method or "GET",
            "url": doc_interface.url or "",
            "path": path,  # 确保path有值
            "base_url": base_url or (doc_interface.url or ""),  # 确保base_url有值
            "service": doc_interface.service or "",
            "headers": headers,  # 确保请求头有值
            "params": params,
            "request_body": request_body,  # 确保请求体有值
            "response_headers": response_headers,  # 确保响应头有值
            "response_body": response_body,  # 确保响应体有值
            "response_schema": response_schema,
            "status_code": doc_interface.status_code or 200,
            "description": doc_interface.description or "",
            "tags": tags,
            "deprecated": doc_interface.deprecated,
            "version": doc_interface.version or "",
            "document_id": doc_interface.document_id
        }
    except Exception as e:
        print(f"从Redis/DB获取接口 {interface_id} 失败: {e}")
        return None


@router.post("/generate/{project_id}")
async def generate_scenario_suites_from_dependencies(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    从Redis中的接口依赖分析结果生成小场景用例集
    根据分组信息和组内接口信息构建依赖链拓扑图
    每条链的第一个节点都是登录接口，后面的接口按照CRUD顺序：创建 -> 修改 -> 查询 -> 删除
    在生成前会清除该项目的Redis、ChromaDB、Neo4j中的场景用例集相关数据
    """
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # 清除之前的相关数据（Redis、ChromaDB、Neo4j中的场景用例集数据）
        try:
            print(f"开始清除项目 {project_id} 的场景用例集相关数据（Redis、ChromaDB、Neo4j）...")
            
            # 1. 清除Redis中的场景用例集数据
            import redis
            from app.config import settings
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                encoding='utf-8'
            )
            redis_key = f"project:{project_id}:scenarios"
            redis_client.delete(redis_key)
            print(f"已清除Redis中的场景用例集数据 (key: {redis_key})")
            
            # 2. 清除ChromaDB中的场景用例集数据（如果有的话）
            try:
                from app.services.vector_service import VectorService
                vector_service = VectorService()
                # 清除项目相关的场景用例集向量数据
                # ChromaDB支持按metadata过滤删除
                vector_service._ensure_chroma_connected()
                results = vector_service.collection.get(
                    where={"project_id": str(project_id), "type": "scenario"}
                )
                if results and results.get("ids"):
                    vector_service.collection.delete(ids=results["ids"])
                    print(f"已清除ChromaDB中的场景用例集数据 (project_id: {project_id}, type: scenario, 共{len(results['ids'])}条)")
            except Exception as e:
                print(f"清除ChromaDB场景用例集数据失败: {e}")
            
            # 3. 清除Neo4j中的场景用例集数据（如果有的话）
            try:
                from neo4j import GraphDatabase
                from app.config import settings
                neo4j_driver = GraphDatabase.driver(
                    settings.NEO4J_URI,
                    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
                )
                with neo4j_driver.session() as session:
                    # 删除项目相关的场景用例集节点和关系
                    result = session.run(
                        """
                        MATCH (n)
                        WHERE n.project_id = $project_id AND (n.type = 'Scenario' OR n.type = 'scenario')
                        DETACH DELETE n
                        RETURN count(n) as deleted_count
                        """,
                        project_id=project_id
                    )
                    record = result.single()
                    deleted_count = record['deleted_count'] if record else 0
                    print(f"已清除Neo4j中的场景用例集数据: {deleted_count} 个节点")
                neo4j_driver.close()
            except Exception as e:
                print(f"清除Neo4j场景用例集数据失败: {e}")
            
        except Exception as e:
            print(f"清除场景用例集相关数据时出错: {e}")
            import traceback
            traceback.print_exc()
        
        # 删除数据库中的现有小场景用例集数据
        existing_suites = db.query(TestCaseSuite).filter(
            TestCaseSuite.project_id == project_id
        ).all()
        for suite in existing_suites:
            db.delete(suite)
        db.commit()
        print(f"已删除数据库中的 {len(existing_suites)} 个现有场景用例集")
        
        analyzer = OptimizedDependencyAnalyzer(db)
        
        # 1. 尝试从多个数据源获取依赖关系图
        dependency_graph = None
        
        # 首先尝试从Redis读取
        dependency_graph = analyzer._load_dependency_graph_from_redis(project_id)
        
        # 如果Redis中没有，尝试从Neo4j获取
        if not dependency_graph or not dependency_graph.get('nodes') or len(dependency_graph.get('nodes', [])) == 0:
            print("Redis中没有依赖分析结果，尝试从Neo4j获取...")
            try:
                neo4j_result = analyzer.get_dependencies_from_neo4j(project_id)
                if neo4j_result and neo4j_result.get('nodes') and len(neo4j_result.get('nodes', [])) > 0:
                    print(f"从Neo4j获取到 {len(neo4j_result.get('nodes', []))} 个节点")
                    dependency_graph = neo4j_result
            except Exception as e:
                print(f"从Neo4j获取失败: {e}")
        
        # 如果Neo4j也没有，尝试从数据库元数据生成
        if not dependency_graph or not dependency_graph.get('nodes') or len(dependency_graph.get('nodes', [])) == 0:
            print("Neo4j数据为空，尝试从元数据获取...")
            # 从数据库获取所有接口，基于相似度分组生成依赖关系
            interfaces_db = db.query(DocumentAPIInterface).filter(
                DocumentAPIInterface.project_id == project_id
            ).all()
            
            if not interfaces_db or len(interfaces_db) == 0:
                raise HTTPException(status_code=404, detail="项目中没有接口数据，请先导入接口文档")
            
            # 构建接口列表
            all_interfaces = []
            for iface_db in interfaces_db:
                interface_dict = {
                    'id': iface_db.id,
                    'interface_id': iface_db.id,
                    'name': iface_db.name,
                    'title': iface_db.name,
                    'method': iface_db.method,
                    'url': iface_db.url,
                    'path': iface_db.path or '',
                    'base_url': iface_db.base_url or '',
                    'service': iface_db.service or '',
                    'version': iface_db.version or '',
                    'description': iface_db.description or '',
                    'response_body': json.loads(iface_db.response_body) if iface_db.response_body else {}
                }
                all_interfaces.append(interface_dict)
            
            # 基于相似度分组
            groups = analyzer._group_interfaces_by_similarity(all_interfaces, threshold=0.3)
            print(f"从元数据分组完成，共 {len(groups)} 个组")
            
            # 构建简单的依赖图（每个组内的接口按顺序连接）
            nodes = []
            edges = []
            for group in groups:
                for i, interface in enumerate(group):
                    interface_id = analyzer._get_interface_id(interface)
                    nodes.append({
                        'id': str(interface_id),
                        'name': interface.get('name', ''),
                        'data': interface
                    })
                    # 组内接口按顺序连接
                    if i > 0:
                        prev_interface_id = analyzer._get_interface_id(group[i-1])
                        edges.append({
                            'source': str(prev_interface_id),
                            'target': str(interface_id),
                            'type': 'similarity_group'
                        })
            
            dependency_graph = {
                'nodes': nodes,
                'edges': edges,
                'source': 'metadata'
            }
            print(f"从元数据生成依赖图：{len(nodes)} 个节点，{len(edges)} 条边")
        
        if not dependency_graph or not dependency_graph.get('nodes') or len(dependency_graph.get('nodes', [])) == 0:
            raise HTTPException(status_code=404, detail="无法获取依赖分析结果，请先运行接口依赖分析或导入接口文档")
        
        nodes = dependency_graph.get('nodes', [])
        edges = dependency_graph.get('edges', [])
        
        print(f"获取到 {len(nodes)} 个节点，{len(edges)} 条边")
        
        # 2. 获取所有接口数据（从数据库）
        interfaces_db = db.query(DocumentAPIInterface).filter(
            DocumentAPIInterface.project_id == project_id
        ).all()
        
        # 构建接口列表（用于重新分组）
        all_interfaces = []
        interface_id_to_db_id = {}  # 接口ID到数据库ID的映射
        
        for iface_db in interfaces_db:
            interface_dict = {
                'id': iface_db.id,
                'interface_id': iface_db.id,
                'name': iface_db.name,
                'title': iface_db.name,
                'method': iface_db.method,
                'url': iface_db.url,
                'path': iface_db.path or '',
                'base_url': iface_db.base_url or '',
                'service': iface_db.service or '',
                'version': iface_db.version or '',
                'description': iface_db.description or '',
                'response_body': json.loads(iface_db.response_body) if iface_db.response_body else {}
            }
            all_interfaces.append(interface_dict)
            
            # 记录ID映射
            interface_id = analyzer._get_interface_id(interface_dict)
            interface_id_to_db_id[str(interface_id)] = iface_db.id
            interface_id_to_db_id[str(iface_db.id)] = iface_db.id
        
        # 3. 重新分组接口（基于相似度）
        # 如果依赖图是从元数据生成的，需要从依赖图中提取分组信息
        # 否则重新分组接口（基于相似度）
        if dependency_graph.get('source') == 'metadata':
            # 如果是从元数据生成的，需要从依赖图中提取分组信息
            # 根据边的连接关系重建分组
            groups = []
            visited = set()
            node_map = {node.get('id'): node for node in nodes}
            
            for node in nodes:
                node_id = node.get('id')
                if node_id and node_id not in visited:
                    # 找到这个节点所在的分组（通过边的连接关系）
                    group = []
                    # 使用BFS找到所有相连的节点
                    queue = [node_id]
                    visited.add(node_id)
                    while queue:
                        current_id = queue.pop(0)
                        current_node = node_map.get(current_id)
                        if current_node:
                            node_data = current_node.get('data', {})
                            if not node_data:
                                # 如果没有data字段，从all_interfaces中查找
                                for iface in all_interfaces:
                                    iface_id = str(analyzer._get_interface_id(iface))
                                    if iface_id == current_id:
                                        node_data = iface
                                        break
                            if node_data:
                                group.append(node_data)
                            
                            # 查找与这个节点相连的其他节点
                            for edge in edges:
                                if edge.get('source') == current_id:
                                    target_id = edge.get('target')
                                    if target_id and target_id not in visited:
                                        visited.add(target_id)
                                        queue.append(target_id)
                                elif edge.get('target') == current_id:
                                    source_id = edge.get('source')
                                    if source_id and source_id not in visited:
                                        visited.add(source_id)
                                        queue.append(source_id)
                    
                    if group:
                        groups.append(group)
            print(f"从依赖图提取到 {len(groups)} 个组")
        else:
            print(f"开始对 {len(all_interfaces)} 个接口进行分组...")
            groups = analyzer._group_interfaces_by_similarity(all_interfaces, threshold=0.3)
            print(f"分组完成，共 {len(groups)} 个组")
        
        # 4. 获取登录接口（优先使用数据库中的真实登录接口）
        login_interface = None
        login_id = None
        login_db_id = None
        
        # 首先尝试从数据库中查找真实的"手机用户名密码登录"接口
        # 查找条件：POST方法，路径包含 /V0.1/index.php，service为user.login
        real_login_interface = db.query(DocumentAPIInterface).filter(
            DocumentAPIInterface.project_id == project_id,
            DocumentAPIInterface.method == 'POST',
            DocumentAPIInterface.path.like('%V0.1/index.php%'),
            DocumentAPIInterface.service == 'user.login'
        ).first()
        
        # 如果没找到，尝试查找名称包含"手机"和"密码"和"登录"的接口
        if not real_login_interface:
            real_login_interface = db.query(DocumentAPIInterface).filter(
                DocumentAPIInterface.project_id == project_id,
                DocumentAPIInterface.method == 'POST',
                DocumentAPIInterface.path.like('%V0.1/index.php%')
            ).filter(
                DocumentAPIInterface.name.like('%手机%'),
                DocumentAPIInterface.name.like('%密码%'),
                DocumentAPIInterface.name.like('%登录%')
            ).first()
        
        # 如果找到了真实的登录接口，使用它
        if real_login_interface:
            login_dict = {
                'id': real_login_interface.id,
                'interface_id': real_login_interface.id,
                'name': real_login_interface.name,
                'title': real_login_interface.name,
                'method': real_login_interface.method,
                'url': real_login_interface.url,
                'path': real_login_interface.path or '/V0.1/index.php',
                'base_url': real_login_interface.base_url or '',
                'service': real_login_interface.service or 'user.login',
                'version': real_login_interface.version or 'V0.1',
                'description': real_login_interface.description or '',
                'headers': json.loads(real_login_interface.headers) if real_login_interface.headers else {},
                'request_body': json.loads(real_login_interface.request_body) if real_login_interface.request_body else {},
                'response_body': json.loads(real_login_interface.response_body) if real_login_interface.response_body else {},
                'response_headers': json.loads(real_login_interface.response_headers) if real_login_interface.response_headers else {}
            }
            login_interface = login_dict
            login_id = str(real_login_interface.id)
            login_db_id = real_login_interface.id
            print(f"找到真实的登录接口: {real_login_interface.name} (ID: {real_login_interface.id})")
        else:
            # 如果没找到，使用虚拟的登录接口
            login_interface = analyzer._get_login_interface(project_id)
            login_id = str(analyzer._get_interface_id(login_interface))
            login_db_id = interface_id_to_db_id.get(login_id, '__LOGIN_INTERFACE__')
            print(f"使用虚拟登录接口: {login_id}")
        
        # 5. 为每个组构建场景用例集
        scenarios = []
        all_scenario_chains = []  # 用于存储到Neo4j和Redis
        
        # 类别名称映射（用于生成更友好的场景名称，使用中文分组名）
        category_name_map = {
            'phone_login': '手机号登录相关的接口',
            'email': '邮箱相关的接口',
            'weibo': '微博相关的接口',
            'personal': '个人相关的接口',
            'sport_record': '运动记录相关的接口',
            'target_sport': '目标运动相关的接口',
            'device': '设备相关的接口',
            'program': '程序相关的接口',
            'product': '商品相关的接口',
            'course': '课程相关的接口',
            'product_info': '产品相关的接口',
            'heart_rate': '心率相关的接口',
            'family': '家庭活动相关的接口',
            'xiaodu': '小度相关的接口',
            'plan': '计划相关的接口',
            'after_sale': '售后相关单接口',
            'message': '消息相关的接口',
            'ad': '广告相关的接口',
            'activity': '活动相关的接口',
            'firmware': '固件相关的接口',
            'oauth': 'oauth相关的接口',
            'ranking': '排行榜相关的接口',
            'dumbbell': '哑铃相关的接口',
            'bike': '单车相关的接口',
            'ai': 'AI相关的接口',
            'wechat': '微信相关的接口',
            'xiaomi': '小米相关的接口',
            'vivo': 'vivo相关的接口',
            'qrcode': '二维码相关的接口',
            'app': 'app相关的接口',
            'google': '谷歌相关的接口',
            'other': '其他'
        }
        
        # 用于跟踪已使用的场景名称，处理重复名称（使用set确保唯一性）
        used_scenario_names = set()
        
        for group_idx, group in enumerate(groups):
            if len(group) == 0:
                continue
            
            # 按相似度和CRUD顺序排序接口（包括登录接口，登录接口总是第一个）
            # 获取登录接口信息
            login_interface_for_sort = None
            if login_db_id:
                # 尝试从group中找到登录接口
                for iface in group:
                    iface_db_id = iface.get('id') or interface_id_to_db_id.get(str(analyzer._get_interface_id(iface)))
                    if str(iface_db_id) == str(login_db_id):
                        login_interface_for_sort = iface
                        break
                # 如果没找到，使用虚拟登录接口
                if not login_interface_for_sort:
                    login_interface_for_sort = {
                        'id': login_db_id,
                        'name': '手机用户名密码登录',
                        'title': '手机用户名密码登录',
                        'method': 'POST',
                        'path': '/V0.1/index.php',
                        'url': 'https://test-xj.kingsmith.com.cn/V0.1/index.php',
                        'version': 'V0.1'
                    }
            
            sorted_interfaces = analyzer._sort_interfaces_by_crud(
                group,
                include_login=True,
                login_interface=login_interface_for_sort,
                project_id=project_id
            )
            
            # 获取该组的类别（使用组内大多数接口的类别）
            group_category = None
            if sorted_interfaces:
                # 统计组内所有接口的类别
                category_counts = {}
                for iface in sorted_interfaces:
                    # 跳过登录接口，因为它不应该影响组的类别
                    if iface.get('_crud_type') == 'LOGIN':
                        continue
                    category = analyzer._get_interface_category_by_name(iface)
                    if category and category != 'other':
                        category_counts[category] = category_counts.get(category, 0) + 1
                
                # 如果找到了类别，使用出现次数最多的类别
                if category_counts:
                    group_category = max(category_counts.items(), key=lambda x: x[1])[0]
                else:
                    # 如果没有找到类别，尝试使用第一个非登录接口的类别
                    for iface in sorted_interfaces:
                        if iface.get('_crud_type') != 'LOGIN':
                            category = analyzer._get_interface_category_by_name(iface)
                            if category:
                                group_category = category
                                break
                
                if group_category is None:
                    group_category = 'other'
            
            # 构建依赖链：登录接口 -> 创建 -> 修改 -> 查询 -> 删除
            # sorted_interfaces已经包含了登录接口并且排在第一位
            dependency_chain = []
            for iface in sorted_interfaces:
                # 跳过登录接口（已经在sorted_interfaces的第一位，但我们需要单独处理）
                if iface.get('_crud_type') == 'LOGIN':
                    # 登录接口使用login_db_id
                    if login_db_id:
                        dependency_chain.append(str(login_db_id))
                    else:
                        dependency_chain.append(login_id)
                else:
                    # 使用数据库ID
                    iface_db_id = iface.get('id') or interface_id_to_db_id.get(str(analyzer._get_interface_id(iface)))
                    if iface_db_id:
                        dependency_chain.append(str(iface_db_id))
                    else:
                        # 如果找不到数据库ID，使用接口ID
                        iface_id = str(analyzer._get_interface_id(iface))
                        dependency_chain.append(iface_id)
            
            # 生成场景名称（直接使用分组名称，重复时加上版本号）
            if sorted_interfaces and group_category:
                category_display = category_name_map.get(group_category, group_category)
                
                # 获取该组的版本信息（只统计非登录接口的版本）
                versions_in_group = set()
                for iface in sorted_interfaces:
                    # 跳过登录接口
                    if iface.get('_crud_type') == 'LOGIN':
                        continue
                    version = analyzer._normalize_version((iface.get('version', '') or '').strip())
                    if version:
                        versions_in_group.add(version)
                
                # 确定基础场景名称（直接使用分组名称）
                base_scenario_name = category_display
                
                # 获取主要版本号（使用第一个非登录接口的版本）
                main_version = None
                for iface in sorted_interfaces:
                    if iface.get('_crud_type') != 'LOGIN':
                        main_version = analyzer._normalize_version((iface.get('version', '') or '').strip())
                        if main_version:
                            break
                
                # 检查是否有重复名称
                scenario_name = base_scenario_name
                if scenario_name in used_scenario_names:
                    # 有重复，添加版本号后缀
                    if main_version:
                        scenario_name = f'{base_scenario_name}[{main_version}]'
                    else:
                        scenario_name = f'{base_scenario_name}[无版本]'
                    
                    # 如果还是重复，继续添加版本号或序号
                    counter = 1
                    original_scenario_name = scenario_name
                    while scenario_name in used_scenario_names:
                        counter += 1
                        # 如果已经有版本号，在版本号后面加序号
                        if main_version:
                            scenario_name = f'{base_scenario_name}[{main_version}]_{counter}'
                        else:
                            scenario_name = f'{base_scenario_name}[无版本]_{counter}'
                else:
                    # 没有重复，但如果该组有版本信息，也可以选择是否添加版本号
                    # 根据用户要求，不重复时不需要添加版本号
                    pass
                
                # 记录已使用的场景名称（使用set确保唯一性）
                used_scenario_names.add(scenario_name)
            else:
                scenario_name = f'场景_{group_idx + 1}'
            
            scenarios.append({
                'scenario_name': scenario_name,
                '_original_name': scenario_name,  # 保存原始名称，用于后续匹配
                'dependency_chain': dependency_chain,
                'interfaces': sorted_interfaces
            })
            
            # 构建拓扑图数据（用于存储到Neo4j和Redis）
            chain_nodes = []
            chain_edges = []
            
            # 添加登录接口节点（使用数据库ID）
            login_node_id = str(login_db_id) if login_db_id else login_id
            login_node = {
                'id': login_node_id,
                'db_id': login_db_id if isinstance(login_db_id, int) else None,
                'name': login_interface.get('title') or login_interface.get('name', '登录接口'),
                'method': login_interface.get('method', 'POST'),
                'url': login_interface.get('url', ''),
                'path': login_interface.get('path', '/V0.1/index.php'),
                'version': login_interface.get('version', 'V0.1'),
                'type': 'LOGIN',
                'category': 'login'
            }
            chain_nodes.append(login_node)
            
            # 添加其他接口节点（使用数据库ID）
            for iface in sorted_interfaces:
                iface_id = str(analyzer._get_interface_id(iface))
                iface_db_id = iface.get('id') or interface_id_to_db_id.get(iface_id)
                iface_node_id = str(iface_db_id) if iface_db_id else iface_id
                
                chain_nodes.append({
                    'id': iface_node_id,
                    'db_id': iface_db_id if isinstance(iface_db_id, int) else None,
                    'name': iface.get('name', ''),
                    'method': iface.get('method', 'GET'),
                    'url': iface.get('url', ''),
                    'path': iface.get('path', ''),
                    'version': iface.get('version', ''),
                    'type': analyzer._extract_crud_type(iface),
                    'category': analyzer._get_interface_category(iface)
                })
            
            # 构建依赖边（链式结构：每个节点指向下一个节点）
            for i in range(len(chain_nodes) - 1):
                chain_edges.append({
                    'source': chain_nodes[i]['id'],
                    'target': chain_nodes[i + 1]['id'],
                    'source_db_id': chain_nodes[i]['db_id'],
                    'target_db_id': chain_nodes[i + 1]['db_id'],
                    'type': 'dependency_chain',
                    'description': f'{chain_nodes[i]["name"]} -> {chain_nodes[i+1]["name"]}',
                    'dependency_path': f'{chain_nodes[i]["type"]} -> {chain_nodes[i+1]["type"]}'
                })
            
            all_scenario_chains.append({
                'scenario_name': scenario_name,  # 这个会在存储时更新为最终名称
                '_original_name': scenario_name,  # 保存原始名称，用于匹配
                'nodes': chain_nodes,
                'edges': chain_edges
            })
        
        print(f"构建了 {len(scenarios)} 个场景用例集")
        
        # 6. 存储场景用例集到数据库
        stored_count = 0
        # 用于跟踪本次生成中已使用的场景名称（确保本次生成不重复）
        current_scenario_names = set()
        
        for scenario in scenarios:
            scenario_name = scenario['scenario_name']
            dependency_chain = scenario['dependency_chain']
            
            # 转换为数据库ID
            db_ids = []
            for interface_id in dependency_chain:
                # 如果是登录接口，使用真实的数据库ID（如果找到了真实接口）或使用标识符
                if interface_id == login_id or str(interface_id) == str(login_db_id):
                    if login_db_id and isinstance(login_db_id, int):
                        # 如果找到了真实的登录接口，使用它的数据库ID
                        db_ids.append(str(login_db_id))
                    else:
                        # 如果没找到，使用标识符
                        db_ids.append('__LOGIN_INTERFACE__')
                else:
                    # 尝试从映射中获取数据库ID
                    db_id = interface_id_to_db_id.get(str(interface_id))
                    if db_id:
                        db_ids.append(str(db_id))
                    elif str(interface_id).isdigit():
                        # 如果interface_id本身就是数字，可能是数据库ID
                        db_ids.append(str(interface_id))
            
            if not db_ids:
                continue
            
            # 处理重复名称：scenario_name已经在生成阶段处理过重复，这里只需要检查数据库中的重复
            final_scenario_name = scenario_name
            # 检查数据库中是否已存在相同名称
            existing_db = db.query(TestCaseSuite).filter(
                TestCaseSuite.project_id == project_id,
                TestCaseSuite.name == final_scenario_name
            ).first()
            
            # 如果数据库中已存在，添加版本号后缀
            if existing_db and final_scenario_name not in current_scenario_names:
                # 获取该场景的版本信息（从第一个非登录接口获取）
                main_version = None
                if scenario.get('interfaces') and len(scenario['interfaces']) > 0:
                    for iface in scenario['interfaces']:
                        # 跳过登录接口
                        if iface.get('_crud_type') == 'LOGIN':
                            continue
                        main_version = analyzer._normalize_version((iface.get('version', '') or '').strip())
                        if main_version:
                            break
                
                # 添加版本号后缀
                if main_version:
                    final_scenario_name = f'{scenario_name}[{main_version}]'
                else:
                    final_scenario_name = f'{scenario_name}[无版本]'
                
                # 如果还是重复，在版本号后面加序号
                counter = 1
                original_name = final_scenario_name
                while db.query(TestCaseSuite).filter(
                    TestCaseSuite.project_id == project_id,
                    TestCaseSuite.name == final_scenario_name
                ).first() is not None:
                    counter += 1
                    if main_version:
                        final_scenario_name = f'{scenario_name}[{main_version}]_{counter}'
                    else:
                        final_scenario_name = f'{scenario_name}[无版本]_{counter}'
            
            # 检查数据库中是否已存在（如果存在，更新它；如果不存在，创建新的）
            existing = db.query(TestCaseSuite).filter(
                TestCaseSuite.project_id == project_id,
                TestCaseSuite.name == final_scenario_name
            ).first()
            
            if existing:
                # 如果已存在，更新它
                existing.test_case_ids = json.dumps(db_ids, ensure_ascii=False)
                existing.description = f'基于依赖分析结果生成，包含 {len(db_ids)} 个接口'
            else:
                # 创建新的场景用例集
                new_suite = TestCaseSuite(
                    project_id=project_id,
                    name=final_scenario_name,
                    description=f'基于依赖分析结果生成，包含 {len(db_ids)} 个接口',
                    test_case_ids=json.dumps(db_ids, ensure_ascii=False)
                )
                db.add(new_suite)
                stored_count += 1
            
            # 记录本次生成中已使用的场景名称
            current_scenario_names.add(final_scenario_name)
            
            # 更新scenarios列表中的场景名称（用于后续的Neo4j和Redis存储）
            scenario['scenario_name'] = final_scenario_name
            
            # 同时更新all_scenario_chains中对应的场景名称
            for chain in all_scenario_chains:
                if chain.get('_original_name') == scenario.get('_original_name'):
                    chain['scenario_name'] = final_scenario_name
                    break
        
        db.commit()
        print(f"存储了 {stored_count} 个场景用例集到数据库")
        
        # 7. 生成Cypher文件并存储到Neo4j（如果Neo4j可用）
        cypher_statements = []
        try:
            db_service = DatabaseService()
            neo4j_available = db_service.neo4j_driver is not None
            
            for chain in all_scenario_chains:
                scenario_name = chain['scenario_name']
                scenario_name_escaped = scenario_name.replace("'", "\\'")
                
                # 创建场景节点
                cypher_statements.append(f"""
                MERGE (s:Scenario {{name: '{scenario_name_escaped}', project_id: {project_id}}})
                SET s.created_at = datetime()
                """)
                
                # 创建接口节点和依赖关系
                for node in chain['nodes']:
                    node_id = node['id'].replace("'", "\\'")
                    node_name = node['name'].replace("'", "\\'")
                    node_type = node['type'].replace("'", "\\'")
                    node_method = node.get('method', 'GET').replace("'", "\\'")
                    node_url = node.get('url', '').replace("'", "\\'")
                    node_db_id = node.get('db_id', 'null')
                    
                    cypher_statements.append(f"""
                    MERGE (n:APIInterface {{id: '{node_id}', project_id: {project_id}}})
                    SET n.name = '{node_name}',
                        n.method = '{node_method}',
                        n.url = '{node_url}',
                        n.type = '{node_type}',
                        n.db_id = {node_db_id}
                    """)
                    
                    # 连接到场景节点
                    cypher_statements.append(f"""
                    MATCH (s:Scenario {{name: '{scenario_name_escaped}', project_id: {project_id}}})
                    MATCH (n:APIInterface {{id: '{node_id}', project_id: {project_id}}})
                    MERGE (s)-[:CONTAINS]->(n)
                    """)
                
                # 创建依赖关系边
                for edge in chain['edges']:
                    source_id = edge['source'].replace("'", "\\'")
                    target_id = edge['target'].replace("'", "\\'")
                    edge_desc = edge['description'].replace("'", "\\'")
                    edge_path = edge['dependency_path'].replace("'", "\\'")
                    
                    cypher_statements.append(f"""
                    MATCH (source:APIInterface {{id: '{source_id}', project_id: {project_id}}})
                    MATCH (target:APIInterface {{id: '{target_id}', project_id: {project_id}}})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '{edge_desc}',
                        r.dependency_path = '{edge_path}',
                        r.scenario_name = '{scenario_name_escaped}',
                        r.confidence = 0.9
                    """)
            
            # 执行所有Cypher语句（如果Neo4j可用）
            if neo4j_available and cypher_statements:
                try:
                    with db_service.neo4j_driver.session() as session:
                        for cypher in cypher_statements:
                            try:
                                session.run(cypher)
                            except Exception as e:
                                print(f"执行Cypher语句失败: {e}")
                                print(f"Cypher: {cypher[:200]}...")
                except Exception as e:
                    print(f"Neo4j会话创建失败: {e}")
            else:
                if not neo4j_available:
                    print("警告：Neo4j连接不可用，跳过存储到Neo4j，但会生成Cypher文件")
            
            # 保存Cypher文件到本地
            import os
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            cypher_dir = os.path.join(backend_dir, "cypher_files")
            os.makedirs(cypher_dir, exist_ok=True)
            
            cypher_file_path = os.path.join(cypher_dir, f"project_{project_id}_scenario_chains.cypher")
            with open(cypher_file_path, 'w', encoding='utf-8') as f:
                f.write("// 场景用例集依赖链拓扑图\n")
                f.write("// 生成时间: " + str(datetime.now()) + "\n\n")
                f.write("\n".join(cypher_statements))
            
            print(f"已生成Cypher文件: {cypher_file_path}")
            
        except Exception as e:
            print(f"存储到Neo4j失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 8. 存储到Redis（存储两种格式的数据）
        # 8.1 存储场景链数据（用于Neo4j等）
        redis_key_chains = f"project:{project_id}:scenario_chains"
        redis_client.set(
            redis_key_chains,
            json.dumps(all_scenario_chains, ensure_ascii=False),
            ex=86400 * 30
        )
        print(f"已存储场景链数据到Redis: {redis_key_chains}")
        
        # 8.2 存储场景用例集数据（格式与_store_scenarios_to_db_and_redis一致，用于读取）
        redis_key_scenarios = f"project:{project_id}:scenarios"
        # 构建符合读取格式的scenarios数据
        redis_scenarios = []
        for scenario in scenarios:
            redis_scenarios.append({
                'scenario_name': scenario.get('scenario_name', ''),
                'dependency_chain': scenario.get('dependency_chain', []),
                'analysis_summary': f'基于依赖分析结果生成，包含 {len(scenario.get("dependency_chain", []))} 个接口'
            })
        
        scenarios_data = {
            'scenarios': redis_scenarios,
            'total_count': len(redis_scenarios),
            'interfaces_count': len(all_interfaces),
            'login_interface': login_interface
        }
        redis_client.set(
            redis_key_scenarios,
            json.dumps(scenarios_data, ensure_ascii=False),
            ex=86400 * 30
        )
        print(f"已存储场景用例集数据到Redis: {redis_key_scenarios} (共 {len(redis_scenarios)} 个场景)")
        
        # 9. 存储到ChromaDB
        chroma_stored_count = 0
        try:
            from app.services.vector_service import VectorService
            vector_service = VectorService()
            vector_service._ensure_chroma_connected()
            
            # 为每个场景链创建向量化文本
            chroma_chunks = []
            chroma_metadata_list = []
            
            for chain in all_scenario_chains:
                scenario_name = chain.get('scenario_name', '')
                nodes = chain.get('nodes', [])
                edges = chain.get('edges', [])
                
                # 构建场景链的文本描述
                node_names = [node.get('name', '') for node in nodes]
                edge_descriptions = [edge.get('description', '') for edge in edges]
                
                scenario_text = f"""
场景名称: {scenario_name}
包含接口: {', '.join(node_names)}
依赖关系: {', '.join(edge_descriptions)}
                """.strip()
                
                chroma_chunks.append(scenario_text)
                
                # 构建元数据
                metadata = {
                    'type': 'scenario',
                    'project_id': str(project_id),
                    'scenario_name': scenario_name,
                    'node_count': str(len(nodes)),
                    'edge_count': str(len(edges))
                }
                chroma_metadata_list.append(metadata)
            
            if chroma_chunks:
                await vector_service.add_documents(project_id, chroma_chunks, chroma_metadata_list)
                chroma_stored_count = len(chroma_chunks)
                print(f"已存储 {chroma_stored_count} 个场景链到ChromaDB (project_id: {project_id})")
        except Exception as e:
            print(f"存储到ChromaDB失败: {e}")
            import traceback
            traceback.print_exc()
        
        return {
            "message": f"成功生成 {stored_count} 个小场景用例集",
            "project_id": project_id,
            "scenarios_count": len(scenarios),
            "stored_count": stored_count,
            "chains_stored_to_neo4j": len(all_scenario_chains),
            "chains_stored_to_redis": len(all_scenario_chains),
            "chains_stored_to_chromadb": chroma_stored_count
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成场景用例集失败: {str(e)}")


@router.get("/{suite_id}")
async def get_test_case_suite(
    suite_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试用例集合详情（从接口列表数据库表或Redis获取，过滤响应体为空或{}的接口）"""
    suite = db.query(TestCaseSuite).filter(TestCaseSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="TestCase suite not found")
    
    # 检查项目是否存在（无需登录）
    project = db.query(Project).filter(Project.id == suite.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    case_ids = json.loads(suite.test_case_ids) if suite.test_case_ids else []
    
    # 获取用例详情（如果test_case_ids是测试用例ID）
    test_cases = []
    if case_ids:
        # 检查是否是接口ID（字符串格式，如"api_123"或数字字符串）还是测试用例ID（整数）
        if isinstance(case_ids[0], int) if case_ids else False:
            # 是测试用例ID
            cases = db.query(TestCase).filter(TestCase.id.in_(case_ids)).all()
            test_cases = [
                {
                    "id": case.id,
                    "name": case.name,
                    "case_type": case.case_type,
                    "module": case.module,
                    "description": case.description
                }
                for case in cases
            ]
        else:
            # 是接口ID或接口名称（依赖链中的接口列表）
            # 从接口列表数据库表或Redis获取接口信息
            dependency_chain_interfaces = []
            
            # 获取登录接口配置（从测试环境配置中获取手机号和密码）
            from app.models import TestEnvironment
            login_interface = None
            
            # 首先尝试从Redis获取
            try:
                redis_key = f"project:{suite.project_id}:scenarios"
                scenarios_data = redis_client.get(redis_key)
                if scenarios_data:
                    scenarios_json = json.loads(scenarios_data)
                    login_interface = scenarios_json.get('login_interface')
            except Exception as e:
                print(f"从Redis获取登录接口配置失败: {e}")
            
            # 如果没有从Redis获取到，使用默认配置并从测试环境获取手机号和密码
            if not login_interface:
                # 默认值
                phone = "{{PHONE}}"
                password = "{{PWD}}"
                base_url = "https://test-xj.kingsmith.com.cn"
                
                # 不再从测试环境配置中获取手机号和密码
                
                login_interface = {
                    "title": "用手机号和密码登录",
                    "base_url": base_url,
                    "version": "V0.1",
                    "path": "/V0.1/index.php?__debug__=1&__sql__=true",
                    "method": "POST",
                    "headers": {
                        "language": "zh_CN",
                        "appver": "5.9.11",
                        "country": "AE",
                        "timeZoneName": "CST",
                        "timeZoneOffset": "8",
                        "content-type": "application/json"
                    },
                    "body": {
                        "service": "user.login",
                        "pwd": password,
                        "phone": phone,
                        "lng": "-7946048961065881",
                        "lat": "-8368059298647897",
                        "brand": "",
                        "IMEI": ""
                    },
                    "response_extract": {
                        "token": "token"
                    }
                }
            
            # 处理接口列表，第一个可能是登录接口标识
            login_token_extracted = False
            login_response_body = None
            analyzer = OptimizedDependencyAnalyzer(db)
            
            # 不再获取默认测试环境配置
            default_env = None
            
            # 获取few-shot示例（用于参数填充参考）
            few_shot_example = None
            try:
                few_shot_example = analyzer._get_few_shot_example(suite.project_id)
            except Exception as e:
                print(f"获取few-shot示例失败: {e}")
            
            for idx, interface_id in enumerate(case_ids):
                print(f"正在查找接口: {interface_id} (类型: {type(interface_id).__name__})")
                
                # 检查是否是登录接口标识
                if interface_id == '__LOGIN_INTERFACE__':
                    # 添加登录接口
                    login_interface_copy = login_interface.copy()
                    login_interface_copy['order'] = idx + 1
                    login_interface_copy['is_login'] = True
                    
                    # 不再从测试环境获取手机号和密码
                    
                    # 模拟登录响应体（用于提取token路径）
                    # 实际token应该从真实登录响应中提取，这里只是设置响应体结构
                    login_interface_copy['response_body'] = {
                        "ret": 200,
                        "data": {
                            "code": "0",
                            "info": {
                                "token": "{{TOKEN}}"
                            }
                        }
                    }
                    
                    # 确保登录接口的所有字段都有值
                    if not login_interface_copy.get('base_url'):
                        login_interface_copy['base_url'] = login_interface_copy.get('base_url') or (login_interface_copy.get('url', '').split('?')[0].split('/V')[0] if login_interface_copy.get('url') else '')
                    if not login_interface_copy.get('path'):
                        login_interface_copy['path'] = login_interface_copy.get('path') or '/V0.1/index.php'
                    if not login_interface_copy.get('headers'):
                        login_interface_copy['headers'] = login_interface_copy.get('headers') or {"Content-Type": "application/json"}
                    if not login_interface_copy.get('request_body'):
                        login_interface_copy['request_body'] = login_interface_copy.get('body') or login_interface_copy.get('request_body') or {}
                    if not login_interface_copy.get('response_headers'):
                        login_interface_copy['response_headers'] = {"Content-Type": "application/json"}
                    
                    dependency_chain_interfaces.append(login_interface_copy)
                    login_token_extracted = True
                    print(f"添加登录接口（第 {idx + 1} 个）")
                    continue
                
                # 获取普通接口信息
                interface_info = _get_interface_from_redis_or_db(interface_id, suite.project_id, db)
                if interface_info:
                    # 先设置默认值，确保响应体有效（不再过滤掉接口）
                    response_body = interface_info.get('response_body', {})
                    if isinstance(response_body, str):
                        try:
                            response_body = json.loads(response_body)
                        except:
                            response_body = {}
                    if not isinstance(response_body, dict):
                        response_body = {}
                    if not response_body or len(response_body) == 0:
                        response_body = {"status": "success", "message": "请求成功"}
                    interface_info['response_body'] = response_body
                    
                    # 添加顺序信息
                    interface_info['order'] = idx + 1
                    
                    # 如果登录接口已经处理过，处理token和参数填充
                    if login_token_extracted:
                        # 从登录接口响应体中提取token
                        if login_response_body is None:
                            # 使用analyzer的方法提取token（从登录接口的响应体）
                            login_iface = dependency_chain_interfaces[0] if dependency_chain_interfaces else None
                            if login_iface and login_iface.get('response_body'):
                                login_response_body = login_iface.get('response_body')
                                token = analyzer._extract_token_from_response(login_response_body)
                                if token:
                                    print(f"从登录接口响应中提取到token: {token[:20]}...")
                                else:
                                    # 如果没有提取到真实token，使用占位符
                                    token = "{{TOKEN}}"
                                    print("使用token占位符")
                            else:
                                token = "{{TOKEN}}"
                        
                        # 确保headers是字典格式
                        headers = interface_info.get('headers', {})
                        if isinstance(headers, str):
                            try:
                                headers = json.loads(headers)
                            except:
                                headers = {}
                        if not isinstance(headers, dict):
                            headers = {}
                        # 确保headers不为空
                        if not headers or len(headers) == 0:
                            headers = {"Content-Type": "application/json", "Accept": "application/json"}
                        interface_info['headers'] = headers
                        
                        # 确保request_body不为空
                        request_body = interface_info.get('request_body', {})
                        if isinstance(request_body, str):
                            try:
                                request_body = json.loads(request_body)
                            except:
                                request_body = {}
                        if not isinstance(request_body, dict):
                            request_body = {}
                        interface_info['request_body'] = request_body
                        
                        # 确保response_headers不为空
                        response_headers = interface_info.get('response_headers', {})
                        if isinstance(response_headers, str):
                            try:
                                response_headers = json.loads(response_headers)
                            except:
                                response_headers = {}
                        if not isinstance(response_headers, dict):
                            response_headers = {}
                        if not response_headers or len(response_headers) == 0:
                            response_headers = {"Content-Type": "application/json"}
                        interface_info['response_headers'] = response_headers
                        
                        # 确保response_body不为空
                        response_body = interface_info.get('response_body', {})
                        if isinstance(response_body, str):
                            try:
                                response_body = json.loads(response_body)
                            except:
                                response_body = {}
                        if not isinstance(response_body, dict):
                            response_body = {}
                        if not response_body or len(response_body) == 0:
                            response_body = {"status": "success", "message": "请求成功"}
                        interface_info['response_body'] = response_body
                        
                        # 确保base_url和path不为空
                        if not interface_info.get('base_url'):
                            if interface_info.get('url'):
                                try:
                                    from urllib.parse import urlparse
                                    parsed = urlparse(interface_info['url'])
                                    interface_info['base_url'] = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
                                except:
                                    pass
                        if not interface_info.get('path'):
                            if interface_info.get('url'):
                                try:
                                    from urllib.parse import urlparse
                                    parsed = urlparse(interface_info['url'])
                                    interface_info['path'] = parsed.path
                                    if parsed.query:
                                        interface_info['path'] = f"{interface_info['path']}?{parsed.query}"
                                except:
                                    pass
                        
                        # 添加token到headers（优先使用token字段，如果没有则使用authorized）
                        if 'token' not in headers or headers.get('token') == '{{TOKEN}}':
                            headers['token'] = token
                        if 'authorized' not in headers or headers.get('authorized') == '{{TOKEN}}':
                            headers['authorized'] = token
                        if 'Authorization' not in headers:
                            headers['Authorization'] = f"Bearer {token}"
                        interface_info['headers'] = headers
                        
                        # 填充请求参数（从few-shot或根据CRUD顺序）
                        interface_info = _fill_request_parameters(
                            interface_info, 
                            dependency_chain_interfaces, 
                            few_shot_example, 
                            default_env,
                            analyzer
                        )
                    
                    # 确保接口信息包含所有必要字段
                    if not interface_info.get('base_url'):
                        if interface_info.get('url'):
                            try:
                                from urllib.parse import urlparse
                                parsed = urlparse(interface_info['url'])
                                interface_info['base_url'] = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
                            except:
                                pass
                    if not interface_info.get('path'):
                        if interface_info.get('url'):
                            try:
                                from urllib.parse import urlparse
                                parsed = urlparse(interface_info['url'])
                                interface_info['path'] = parsed.path
                                if parsed.query:
                                    interface_info['path'] = f"{interface_info['path']}?{parsed.query}"
                            except:
                                pass
                    if not interface_info.get('headers') or (isinstance(interface_info.get('headers'), dict) and len(interface_info.get('headers', {})) == 0):
                        interface_info['headers'] = {"Content-Type": "application/json", "Accept": "application/json"}
                    if not interface_info.get('request_body') or (isinstance(interface_info.get('request_body'), dict) and len(interface_info.get('request_body', {})) == 0):
                        interface_info['request_body'] = {}
                    if not interface_info.get('response_headers') or (isinstance(interface_info.get('response_headers'), dict) and len(interface_info.get('response_headers', {})) == 0):
                        interface_info['response_headers'] = {"Content-Type": "application/json"}
                    if not interface_info.get('response_body') or (isinstance(interface_info.get('response_body'), dict) and len(interface_info.get('response_body', {})) == 0):
                        # 如果响应体为空，使用默认值（但通常不应该为空，因为会被过滤）
                        interface_info['response_body'] = {"status": "success", "message": "请求成功"}
                    
                    dependency_chain_interfaces.append(interface_info)
                    print(f"成功找到接口: {interface_id} -> {interface_info.get('name', 'N/A')}, base_url={interface_info.get('base_url', 'N/A')}, path={interface_info.get('path', 'N/A')}")
                else:
                    # 即使接口查找失败，也尝试从数据库直接查找并创建基本信息
                    print(f"未找到接口: {interface_id}，尝试从数据库直接查找")
                    try:
                        # 尝试将interface_id转换为整数（数据库ID）
                        doc_interface_id = None
                        if isinstance(interface_id, str):
                            if interface_id.isdigit():
                                doc_interface_id = int(interface_id)
                        elif isinstance(interface_id, int):
                            doc_interface_id = interface_id
                        
                        if doc_interface_id:
                            doc_interface = db.query(DocumentAPIInterface).filter(
                                DocumentAPIInterface.id == doc_interface_id,
                                DocumentAPIInterface.project_id == suite.project_id
                            ).first()
                            
                            if doc_interface:
                                # 构建基本信息
                                interface_info = {
                                    'id': doc_interface.id,
                                    'interface_id': str(doc_interface.id),
                                    'name': doc_interface.name or f'接口_{doc_interface.id}',
                                    'method': doc_interface.method or 'GET',
                                    'url': doc_interface.url or '',
                                    'path': doc_interface.path or '',
                                    'base_url': doc_interface.base_url or '',
                                    'service': doc_interface.service or '',
                                    'headers': json.loads(doc_interface.headers) if doc_interface.headers else {"Content-Type": "application/json"},
                                    'request_body': json.loads(doc_interface.request_body) if doc_interface.request_body else {},
                                    'response_headers': json.loads(doc_interface.response_headers) if doc_interface.response_headers else {"Content-Type": "application/json"},
                                    'response_body': json.loads(doc_interface.response_body) if doc_interface.response_body else {"status": "success", "message": "请求成功"},
                                    'description': doc_interface.description or '',
                                    'order': idx + 1
                                }
                                
                                # 确保base_url和path不为空
                                if not interface_info.get('base_url') and interface_info.get('url'):
                                    try:
                                        from urllib.parse import urlparse
                                        parsed = urlparse(interface_info['url'])
                                        interface_info['base_url'] = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
                                    except:
                                        pass
                                if not interface_info.get('path') and interface_info.get('url'):
                                    try:
                                        from urllib.parse import urlparse
                                        parsed = urlparse(interface_info['url'])
                                        interface_info['path'] = parsed.path
                                        if parsed.query:
                                            interface_info['path'] = f"{interface_info['path']}?{parsed.query}"
                                    except:
                                        pass
                                
                                dependency_chain_interfaces.append(interface_info)
                                print(f"从数据库直接找到接口: {interface_id} -> {interface_info.get('name', 'N/A')}")
                            else:
                                print(f"数据库中也未找到接口: {interface_id}")
                    except Exception as e:
                        print(f"查找接口 {interface_id} 时出错: {e}")
            
            print(f"总共找到 {len(dependency_chain_interfaces)} 个有效接口（共 {len(case_ids)} 个接口ID）")
            test_cases = dependency_chain_interfaces
    
    # 确保返回的test_cases包含所有必要字段
    enhanced_test_cases = []
    for test_case in test_cases:
        enhanced_case = {
            "id": test_case.get('id') or test_case.get('interface_id'),
            "interface_id": test_case.get('interface_id') or test_case.get('id'),
            "name": test_case.get('name', ''),
            "method": test_case.get('method', 'GET'),
            "url": test_case.get('url', ''),
            "path": test_case.get('path', ''),
            "base_url": test_case.get('base_url', ''),
            "service": test_case.get('service', ''),
            "headers": test_case.get('headers', {}),
            "request_body": test_case.get('request_body', {}),
            "response_headers": test_case.get('response_headers', {}),
            "response_body": test_case.get('response_body', {}),
            "description": test_case.get('description', ''),
            "order": test_case.get('order', 0)
        }
        # 如果字段为空，尝试从其他字段获取
        if not enhanced_case['base_url'] and enhanced_case['url']:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(enhanced_case['url'])
                enhanced_case['base_url'] = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
            except:
                pass
        if not enhanced_case['path'] and enhanced_case['url']:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(enhanced_case['url'])
                enhanced_case['path'] = parsed.path
                if parsed.query:
                    enhanced_case['path'] = f"{enhanced_case['path']}?{parsed.query}"
            except:
                pass
        enhanced_test_cases.append(enhanced_case)
    
    return {
        "id": suite.id,
        "name": suite.name,
        "description": suite.description,
        "test_case_ids": case_ids,
        "test_cases": enhanced_test_cases,  # 使用增强后的接口列表
        "test_case_count": len(enhanced_test_cases),  # 使用过滤后的数量
        "tags": suite.tags,
        "created_at": suite.created_at,
        "updated_at": suite.updated_at,
        "dependency_chain": case_ids  # 依赖链中的接口ID列表
    }


@router.put("/{suite_id}")
async def update_test_case_suite(
    suite_id: int,
    suite_update: TestCaseSuiteUpdate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """更新测试用例集合"""
    suite = db.query(TestCaseSuite).filter(TestCaseSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="TestCase suite not found")
    
    # 检查项目是否存在（无需登录）
    project = db.query(Project).filter(Project.id == suite.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 验证用例（如果更新用例列表）
    if suite_update.test_case_ids is not None:
        # 支持字符串ID（接口ID）和整数ID（测试用例ID）
        # 过滤掉登录接口标识
        interface_ids = [str(id) for id in suite_update.test_case_ids if str(id) != '__LOGIN_INTERFACE__']
        
        # 尝试转换为整数（测试用例ID）
        try:
            test_case_ids = [int(id) for id in interface_ids if id.isdigit()]
            if test_case_ids:
                valid_cases = db.query(TestCase).filter(
                    TestCase.id.in_(test_case_ids),
                    TestCase.project_id == suite.project_id
                ).all()
                
                if len(valid_cases) != len(test_case_ids):
                    # 如果不是测试用例ID，可能是接口ID，允许通过
                    pass
        except:
            # 如果不是测试用例ID，可能是接口ID，允许通过
            pass
    
    # 更新字段
    if suite_update.name is not None:
        suite.name = suite_update.name
    if suite_update.description is not None:
        suite.description = suite_update.description
    if suite_update.test_case_ids is not None:
        suite.test_case_ids = json.dumps(suite_update.test_case_ids)
    if suite_update.tags is not None:
        suite.tags = suite_update.tags
    
    db.commit()
    db.refresh(suite)
    return suite


@router.delete("/batch")
async def batch_delete_test_case_suites(
    project_id: int,
    payload: BatchDeleteSuitesRequest = Body(...),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """批量删除测试用例集合"""
    if not payload.suite_ids:
        raise HTTPException(status_code=400, detail="suite_ids 不能为空")
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    suites = db.query(TestCaseSuite).filter(
        TestCaseSuite.id.in_(payload.suite_ids),
        TestCaseSuite.project_id == project_id
    ).all()
    
    found_ids = [s.id for s in suites]
    not_found_ids = [sid for sid in payload.suite_ids if sid not in found_ids]
    
    for suite in suites:
        db.delete(suite)
    db.commit()
    
    # 删除Redis缓存，保证列表刷新
    try:
        redis_key = f"project:{project_id}:scenarios"
        redis_client.delete(redis_key)
    except Exception as e:
        print(f"[batch_delete_test_case_suites] 清理Redis缓存失败: {e}")
    
    return {
        "message": f"已删除 {len(found_ids)} 个用例集",
        "deleted_ids": found_ids,
        "not_found_ids": not_found_ids
    }

@router.post("/{suite_id}/generate-specs")
async def generate_test_cases_from_suite(
    suite_id: int,
    case_type: str = Query(..., description="用例类型: pytest(接口测试用例) 或 jmeter(性能测试用例)"),
    generate_type: str = Query("scenario", description="生成类型: scenario(场景用例) 或 interface(接口用例)"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """从场景用例集生成测试用例"""
    if case_type not in ["pytest", "jmeter"]:
        raise HTTPException(status_code=400, detail="不支持的用例类型，只支持 pytest 或 jmeter")
    
    suite = db.query(TestCaseSuite).filter(TestCaseSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="TestCase suite not found")
    
    project = db.query(Project).filter(Project.id == suite.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 如果是生成接口场景用例（scenario + pytest），使用特殊逻辑
    if generate_type == "scenario" and case_type == "pytest":
        return await _generate_scenario_test_case_special(
            suite_id=suite_id,
            suite=suite,
            db=db
        )
    
    # 原有的生成逻辑（用于其他类型）
    # 获取用例集中的接口列表
    case_ids = json.loads(suite.test_case_ids) if suite.test_case_ids else []
    
    # 提取接口ID（排除登录接口标识）
    interface_ids = []
    for case_id in case_ids:
        if case_id == '__LOGIN_INTERFACE__':
            continue
        
        # 尝试提取接口ID
        if isinstance(case_id, str):
            if case_id.startswith('api_'):
                try:
                    interface_ids.append(int(case_id.replace('api_', '')))
                except:
                    pass
            elif case_id.isdigit():
                interface_ids.append(int(case_id))
        elif isinstance(case_id, int):
            interface_ids.append(case_id)
    
    if not interface_ids:
        raise HTTPException(status_code=400, detail="用例集中没有有效的接口")
    
    # 获取接口信息
    from app.models import DocumentAPIInterface
    interfaces = db.query(DocumentAPIInterface).filter(
        DocumentAPIInterface.id.in_(interface_ids),
        DocumentAPIInterface.project_id == suite.project_id
    ).all()
    
    if len(interfaces) != len(interface_ids):
        raise HTTPException(status_code=400, detail="部分接口不存在")
    
    # 生成测试用例
    from app.celery_tasks import generate_test_case_task
    from app.models import APIInterface
    import json as json_module
    
    test_case_ids = []
    module_name = suite.name if generate_type == "scenario" else None
    
    for interface in interfaces:
        # 查找或创建对应的APIInterface记录（通过名称和URL匹配）
        api_interface = db.query(APIInterface).filter(
            APIInterface.project_id == suite.project_id,
            APIInterface.name == interface.name,
            APIInterface.url == interface.url
        ).first()
        
        if not api_interface:
            # 创建APIInterface记录
            api_interface = APIInterface(
                project_id=suite.project_id,
                name=interface.name,
                method=interface.method or "GET",
                url=interface.url or "",
                headers=interface.headers if isinstance(interface.headers, str) else json_module.dumps(interface.headers) if interface.headers else None,
                body=interface.request_body if isinstance(interface.request_body, str) else json_module.dumps(interface.request_body) if interface.request_body else None,
                params=interface.params if isinstance(interface.params, str) else json_module.dumps(interface.params) if interface.params else None,
                response_schema=interface.response_body if isinstance(interface.response_body, str) else json_module.dumps(interface.response_body) if interface.response_body else None,
                description=interface.description
            )
            db.add(api_interface)
            db.commit()
            db.refresh(api_interface)
        
        # 创建测试用例记录
        test_case_name = f"{suite.name}_{interface.name}" if generate_type == "scenario" else f"{interface.name}_测试用例"
        test_case = TestCase(
            project_id=suite.project_id,
            api_interface_id=api_interface.id,
            name=test_case_name,
            case_type=case_type,
            module=module_name,
            status="generating",
            generation_progress=0
        )
        db.add(test_case)
        db.commit()
        db.refresh(test_case)
        test_case_ids.append(test_case.id)
        
        # 提交异步任务
        task = generate_test_case_task.delay(
            test_case_id=test_case.id,
            case_type=case_type,
            project_id=suite.project_id,
            api_interface_id=api_interface.id,
            module=module_name
        )
        
        # 更新任务ID
        test_case.generation_task_id = task.id
        db.commit()
    
    return {
        "message": f"成功提交 {len(test_case_ids)} 个测试用例生成任务",
        "test_case_ids": test_case_ids,
        "case_type": case_type,
        "generate_type": generate_type,
        "suite_id": suite_id
    }


async def _generate_scenario_test_case_special(
    suite_id: int,
    suite: TestCaseSuite,
    db: Session
) -> Dict[str, Any]:
    """生成接口场景用例（特殊处理：使用DeepSeek + RAG + 向量检索，异步Celery任务）"""
    from app.models import DocumentAPIInterface, TestEnvironment
    from app.services.optimized_dependency_analyzer import OptimizedDependencyAnalyzer
    from app.services.vector_service import VectorService
    from app.celery_tasks import generate_scenario_test_case_task
    
    analyzer = OptimizedDependencyAnalyzer(db)
    vector_service = VectorService()
    
    # 获取用例集中的接口列表
    case_ids = json.loads(suite.test_case_ids) if suite.test_case_ids else []
    
    # 不再获取默认测试环境
    default_env = None
    
    # 获取登录接口响应体并提取token
    login_token = None
    login_interface_info = None
    scenario_interfaces_info = []  # 只包含场景用例的接口（不包括登录接口）
    all_few_shot_interfaces = []  # 收集所有few-shot接口信息
    
    # 处理接口列表，提取登录接口和token
    for idx, interface_id in enumerate(case_ids):
        if interface_id == '__LOGIN_INTERFACE__':
            # 获取登录接口配置
            try:
                redis_key = f"project:{suite.project_id}:scenarios"
                scenarios_data = redis_client.get(redis_key)
                if scenarios_data:
                    scenarios_json = json.loads(scenarios_data)
                    login_interface_info = scenarios_json.get('login_interface')
            except:
                pass
            
            if not login_interface_info:
                # 使用默认登录接口配置（不使用环境配置数据）
                login_interface_info = {
                    "name": "用户登录",
                    "method": "POST",
                    "base_url": "",
                    "path": "/V0.1/index.php?__debug__=1&__sql__=true",
                    "headers": {
                        "Content-Type": "application/json"
                    },
                    "request_body": {
                        "service": "user.login",
                        "phone": "",
                        "pwd": "",
                    }
                }
            
            # 从登录接口响应体中提取token
            # 优先从登录接口配置的response_body中提取
            if login_interface_info.get('response_body'):
                try:
                    response_body = login_interface_info['response_body']
                    if isinstance(response_body, str):
                        response_body = json.loads(response_body)
                    login_token = analyzer._extract_token_from_response(response_body)
                    if login_token:
                        print(f"从登录接口响应体中提取到token: {login_token[:20]}...")
                except Exception as e:
                    print(f"从登录接口响应体提取token失败: {e}")
            
            # 如果还没提取到，尝试从Redis获取few-shot示例中的登录响应
            if not login_token:
                try:
                    few_shot_example = analyzer._get_few_shot_example(suite.project_id)
                    if few_shot_example and few_shot_example.get('interfaces'):
                        for fs_interface in few_shot_example['interfaces']:
                            if 'login' in fs_interface.get('name', '').lower() or '登录' in fs_interface.get('name', ''):
                                if fs_interface.get('response_body'):
                                    response_body = fs_interface['response_body']
                                    if isinstance(response_body, str):
                                        response_body = json.loads(response_body)
                                    login_token = analyzer._extract_token_from_response(response_body)
                                    if login_token:
                                        print(f"从few-shot示例中提取到token")
                                        break
                except Exception as e:
                    print(f"从few-shot示例提取token失败: {e}")
            
            # 如果还是没有提取到，使用示例响应体结构（但token值仍为占位符）
            if not login_token:
                login_response_body = {
                    "ret": 200,
                    "data": {
                        "code": "0",
                        "info": {
                            "token": "{{TOKEN}}"
                        }
                    }
                }
                login_token = "{{TOKEN}}"
                login_interface_info['response_body'] = login_response_body
                print("使用token占位符")
            
            login_interface_info['order'] = idx + 1
            login_interface_info['is_login'] = True
            # 登录接口不添加到场景接口列表，只用于提取token
            continue
        
        # 获取普通接口信息（这些是场景用例的接口）
        interface_info = _get_interface_from_redis_or_db(interface_id, suite.project_id, db)
        if not interface_info:
            continue
        
        # 构建接口的向量检索查询文本
        interface_query = f"{interface_info.get('name', '')} {interface_info.get('path', '')} {interface_info.get('description', '')} {json.dumps(interface_info.get('request_body', {}), ensure_ascii=False)}"
        
        # 使用向量检索查找相似接口（few-shot）
        similar_interfaces = []
        few_shot_for_this_interface = []
        try:
            # vector_service.search是异步方法，直接await
            search_results = await vector_service.search(
                query=interface_query,
                top_k=5,
                use_rerank=True,
                document_id=suite.project_id
            )
            
            # 从检索结果中提取接口信息
            for result in search_results:
                metadata = result.get('metadata', {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except:
                        metadata = {}
                
                # 检查是否是接口类型的内容
                content_type = metadata.get('content_type') if isinstance(metadata, dict) else result.get('content_type', '')
                chunk_text = result.get('chunk_text', '')
                
                # 如果chunk_text包含接口信息，尝试解析
                if 'interface' in str(content_type).lower() or 'interface' in chunk_text.lower():
                    try:
                        # 尝试从chunk_text中提取接口信息
                        if isinstance(chunk_text, str):
                            # 查找JSON格式的接口信息
                            import re
                            json_match = re.search(r'\{.*\}', chunk_text, re.DOTALL)
                            if json_match:
                                interface_data = json.loads(json_match.group(0))
                                similar_interface = {
                                    "name": interface_data.get('name', ''),
                                    "method": interface_data.get('method', ''),
                                    "path": interface_data.get('path', ''),
                                    "request_body": interface_data.get('request_body', {}),
                                    "headers": interface_data.get('headers', {}),
                                    "similarity_score": result.get('final_score', result.get('score', 0))
                                }
                                similar_interfaces.append(similar_interface)
                                few_shot_for_this_interface.append(similar_interface)
                    except Exception as e:
                        print(f"解析接口信息失败: {e}")
                        pass
        except Exception as e:
            print(f"向量检索失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 将few-shot接口添加到总列表（去重）
        for fs_interface in few_shot_for_this_interface:
            # 检查是否已存在（根据name和path判断）
            existing = False
            for existing_fs in all_few_shot_interfaces:
                if existing_fs.get('name') == fs_interface.get('name') and existing_fs.get('path') == fs_interface.get('path'):
                    existing = True
                    break
            if not existing:
                all_few_shot_interfaces.append(fs_interface)
        
        # 填充请求参数
        # 1. 优先使用few-shot相似接口的请求参数
        filled_request_body = interface_info.get('request_body', {})
        if isinstance(filled_request_body, str):
            try:
                filled_request_body = json.loads(filled_request_body)
            except:
                filled_request_body = {}
        
        if similar_interfaces and len(similar_interfaces) > 0:
            # 使用相似度最高的接口作为参考
            best_match = similar_interfaces[0]
            reference_body = best_match.get('request_body', {})
            if isinstance(reference_body, dict):
                for key, value in reference_body.items():
                    if key not in ['xjid', 'phone', 'username', 'pwd', 'password'] and key not in filled_request_body:
                        filled_request_body[key] = value
        
        # 2. 不再从环境变量填充xjid、用户名、密码
        
        # 3. 如果没有few-shot，根据依赖顺序填充（从创建接口的响应中提取）
        if not similar_interfaces and len(scenario_interfaces_info) > 0:
            # 查找前面的CREATE接口
            for prev_interface in scenario_interfaces_info:
                crud_type = analyzer._extract_crud_type(prev_interface)
                if crud_type == 'CREATE':
                    prev_response = prev_interface.get('response_body', {})
                    if isinstance(prev_response, dict):
                        # 提取ID字段
                        for id_field in ['id', 'data_id', 'record_id', 'item_id']:
                            if id_field in prev_response:
                                filled_request_body['id'] = prev_response[id_field]
                                break
                            elif 'data' in prev_response and isinstance(prev_response['data'], dict):
                                if id_field in prev_response['data']:
                                    filled_request_body['id'] = prev_response['data'][id_field]
                                    break
        
        interface_info['request_body'] = filled_request_body
        
        # 填充token到请求头
        headers = interface_info.get('headers', {})
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except:
                headers = {}
        if not isinstance(headers, dict):
            headers = {}
        
        # 添加token到headers
        if 'token' not in headers:
            headers['token'] = login_token
        if 'Authorization' not in headers:
            headers['Authorization'] = f"Bearer {login_token}"
        
        interface_info['headers'] = headers
        interface_info['order'] = len(scenario_interfaces_info) + 1
        
        # 添加到场景接口列表（只包含场景用例的接口，不包括登录接口）
        scenario_interfaces_info.append(interface_info)
    
    # 验证场景接口列表是否为空
    if not scenario_interfaces_info or len(scenario_interfaces_info) == 0:
        error_msg = "场景接口列表为空，无法生成场景测试用例。"
        if not case_ids or len(case_ids) == 0:
            error_msg += "原因：用例集中没有配置任何接口。"
        else:
            # 统计有多少接口获取失败
            failed_count = 0
            failed_interface_ids = []
            for interface_id in case_ids:
                if interface_id != '__LOGIN_INTERFACE__':
                    interface_info = _get_interface_from_redis_or_db(interface_id, suite.project_id, db)
                    if not interface_info:
                        failed_count += 1
                        failed_interface_ids.append(str(interface_id))
            
            if failed_count > 0:
                error_msg += f"原因：用例集中的 {failed_count} 个接口无法获取（可能接口已被删除或不存在）。"
                if len(failed_interface_ids) <= 5:  # 如果失败接口不多，显示具体ID
                    error_msg += f" 失败的接口ID: {', '.join(failed_interface_ids)}"
            else:
                error_msg += "原因：用例集中只有登录接口，没有业务接口。"
        
        raise HTTPException(status_code=400, detail=error_msg)
    
    # 创建测试用例记录（状态为generating）
    test_case = TestCase(
        project_id=suite.project_id,
        name=f"{suite.name}_场景测试用例",
        case_type="pytest",
        module=suite.name,
        status="generating",
        generation_progress=0
    )
    db.add(test_case)
    db.commit()
    db.refresh(test_case)
    
    # 准备环境信息（不再使用环境配置数据）
    environment_info = {
        "base_url": "",
        "xjid": "",
        "username": "",
    }
    
    # 提交异步Celery任务
    try:
        task = generate_scenario_test_case_task.delay(
            test_case_id=test_case.id,
            suite_id=suite_id,
            project_id=suite.project_id,
            interfaces_info=scenario_interfaces_info,  # 只包含场景用例的接口
            login_token=login_token or "{{TOKEN}}",
            few_shot_interfaces=all_few_shot_interfaces,  # Few-shot接口信息
            environment_info=environment_info,
            login_interface_info=login_interface_info  # 登录接口信息
        )
        
        # 更新任务ID
        test_case.generation_task_id = task.id
        db.commit()
        
        # 清除测试用例列表缓存，确保新创建的场景用例能立即显示
        try:
            from app.services.cache_service import cache_service
            # 清除该项目的所有测试用例缓存（包括场景用例和普通用例）
            cache_pattern = f"test_cases:{suite.project_id}:*"
            deleted_count = cache_service.invalidate_cache(cache_pattern)
            print(f"[场景测试用例创建] 已清除测试用例缓存，删除 {deleted_count} 个缓存键")
        except Exception as cache_error:
            print(f"[场景测试用例创建] 清除缓存失败: {cache_error}")
        
        return {
            "message": f"场景测试用例生成任务已提交",
            "test_case_id": test_case.id,
            "task_id": task.id,
            "case_type": "pytest",
            "generate_type": "scenario",
            "suite_id": suite_id
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 更新错误状态
        test_case.status = "failed"
        test_case.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=f"提交场景测试用例生成任务失败: {str(e)}")







