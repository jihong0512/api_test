from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel

from app.database import get_db
from app.models import TestCase, Project, User, APIInterface, DocumentAPIInterface
from app.routers.auth import get_current_user_optional
from app.celery_tasks import generate_test_case_task, batch_generate_test_cases_task, generate_jmeter_performance_test_task
from app.celery_app import celery_app
import json
import redis
from app.config import settings
from app.services.cache_service import cache_service

router = APIRouter()


class TestCaseCreate(BaseModel):
    api_interface_id: Optional[int] = None
    name: str
    case_type: str = "pytest"  # pytest, jmeter
    module: Optional[str] = None
    description: Optional[str] = None
    test_data: Optional[Dict[str, Any]] = None
    assertions: Optional[List[Dict[str, Any]]] = None
    dependencies: Optional[str] = None


class TestCaseUpdate(BaseModel):
    api_interface_id: Optional[int] = None
    name: Optional[str] = None
    case_type: Optional[str] = None  # pytest, jmeter
    module: Optional[str] = None
    description: Optional[str] = None
    test_data: Optional[Any] = None  # 可以是Dict或字符串
    test_code: Optional[str] = None  # 测试代码
    assertions: Optional[Any] = None  # 可以是List[Dict]或字符串
    dependencies: Optional[str] = None


class TestCaseGenerateRequest(BaseModel):
    api_interface_ids: List[int]
    case_type: str = "pytest"  # pytest, jmeter
    module: Optional[str] = None
    generate_async: bool = True  # 是否异步生成


class TestCaseResponse(BaseModel):
    id: int
    project_id: int
    name: str
    case_type: str
    
    class Config:
        from_attributes = True


@router.post("/generate")
async def generate_test_case(
    project_id: int,
    request: TestCaseGenerateRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成测试用例（支持异步队列）"""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 验证API接口存在（支持APIInterface和DocumentAPIInterface）
    api_interfaces = db.query(APIInterface).filter(
        APIInterface.id.in_(request.api_interface_ids),
        APIInterface.project_id == project_id
    ).all()
    
    # 如果APIInterface中没有找到所有接口，尝试从DocumentAPIInterface查找
    found_ids = {iface.id for iface in api_interfaces}
    missing_ids = set(request.api_interface_ids) - found_ids
    
    if missing_ids:
        document_interfaces = db.query(DocumentAPIInterface).filter(
            DocumentAPIInterface.id.in_(list(missing_ids)),
            DocumentAPIInterface.project_id == project_id
        ).all()
        
        # 将DocumentAPIInterface转换为APIInterface格式（用于后续处理）
        for doc_iface in document_interfaces:
            # 检查是否已存在对应的APIInterface记录
            existing_api_iface = db.query(APIInterface).filter(
                APIInterface.project_id == project_id,
                APIInterface.name == doc_iface.name,
                APIInterface.url == doc_iface.url
            ).first()
            
            if not existing_api_iface:
                # 创建APIInterface记录（用于测试用例关联）
                api_iface = APIInterface(
                    project_id=project_id,
                    name=doc_iface.name,
                    method=doc_iface.method or 'GET',
                    url=doc_iface.url or '',
                    headers=doc_iface.headers if isinstance(doc_iface.headers, str) else json.dumps(doc_iface.headers, ensure_ascii=False) if doc_iface.headers else None,
                    params=doc_iface.params if isinstance(doc_iface.params, str) else json.dumps(doc_iface.params, ensure_ascii=False) if doc_iface.params else None,
                    body=doc_iface.request_body if isinstance(doc_iface.request_body, str) else json.dumps(doc_iface.request_body, ensure_ascii=False) if doc_iface.request_body else None,
                    response_schema=doc_iface.response_schema if isinstance(doc_iface.response_schema, str) else json.dumps(doc_iface.response_schema, ensure_ascii=False) if doc_iface.response_schema else None,
                    description=doc_iface.description
                )
                db.add(api_iface)
                db.commit()
                db.refresh(api_iface)
                api_interfaces.append(api_iface)
            else:
                api_interfaces.append(existing_api_iface)
    
    # 最终验证
    if len(api_interfaces) != len(request.api_interface_ids):
        raise HTTPException(status_code=400, detail="部分API接口不存在")
    
    if request.generate_async:
        # 异步生成：创建测试用例记录，然后提交Celery任务
        test_case_ids = []
        for api_interface in api_interfaces:
            test_case = TestCase(
                project_id=project_id,
                api_interface_id=api_interface.id,
                name=f"{api_interface.name}_测试用例",
                case_type=request.case_type,
                module=request.module,
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
                case_type=request.case_type,
                project_id=project_id,
                api_interface_id=api_interface.id,
                module=request.module
            )
            
            # 更新任务ID
            test_case.generation_task_id = task.id
            db.commit()
        
        return {
            "message": "测试用例生成任务已提交",
            "test_case_ids": test_case_ids,
            "task_ids": [tc.generation_task_id for tc in db.query(TestCase).filter(TestCase.id.in_(test_case_ids)).all()],
            "async": True
        }
    else:
        # 同步生成（不推荐，可能超时）
        from app.services.test_case_generator import PytestCaseGenerator, JMeterCaseGenerator
        from app.services.smart_test_data_generator import SmartTestDataGenerator
        
        results = []
        generator = SmartTestDataGenerator()
        
        for api_interface in api_interfaces:
            api_data = {
                "id": api_interface.id,
                "name": api_interface.name,
                "method": api_interface.method,
                "url": api_interface.url,  # 统一使用url字段
                "params": json.loads(api_interface.params) if api_interface.params else {},
                "headers": json.loads(api_interface.headers) if api_interface.headers else {},
                "body": json.loads(api_interface.body) if api_interface.body else {},
                "response_schema": json.loads(api_interface.response_schema) if api_interface.response_schema else {},
                "description": api_interface.description or ""
            }
            
            test_data = generator.generate_test_data_for_api(
                api_info=api_data,
                connection_id=None,
                project_id=project_id,
                use_real_data=False,
                db_session=db
            )
            
            if request.case_type == "pytest":
                case_generator = PytestCaseGenerator()
                test_code = case_generator.generate_test_case(api_interface=api_data, test_data=test_data)
            elif request.case_type == "jmeter":
                case_generator = JMeterCaseGenerator()
                test_code = case_generator.generate_test_case(api_interface=api_data, test_data=test_data)
            else:
                raise HTTPException(status_code=400, detail=f"不支持的用例类型: {request.case_type}")
            
            test_case = TestCase(
                project_id=project_id,
                api_interface_id=api_interface.id,
                name=f"{api_interface.name}_测试用例",
                case_type=request.case_type,
                module=request.module,
                test_code=test_code,
                status="completed",
                generation_progress=100
            )
            db.add(test_case)
            results.append(test_case.id)
        
        db.commit()
        
        return {
            "message": "测试用例生成完成",
            "test_case_ids": results,
            "async": False
        }


@router.post("/", response_model=TestCaseResponse)
async def create_test_case(
    project_id: int,
    test_case: TestCaseCreate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """创建测试用例"""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    import json
    db_case = TestCase(
        project_id=project_id,
        api_interface_id=test_case.api_interface_id,
        name=test_case.name,
        case_type=test_case.case_type,
        module=test_case.module,
        description=test_case.description,
        test_data=json.dumps(test_case.test_data) if test_case.test_data else None,
        assertions=json.dumps(test_case.assertions) if test_case.assertions else None,
        dependencies=test_case.dependencies,
        status="active"
    )
    db.add(db_case)
    db.commit()
    db.refresh(db_case)
    return db_case


@router.get("/")
async def list_test_cases(
    project_id: int,
    module: Optional[str] = Query(None, description="按模块筛选"),
    case_type: Optional[str] = Query(None, description="按类型筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    is_scenario: Optional[bool] = Query(None, description="是否为场景用例（true=场景用例，false=普通接口用例）"),
    page: int = Query(1, ge=1, description="页码（从1开始）"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量（1-100）"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试用例列表（支持模块筛选和分页，优先从Redis读取缓存）"""
    from app.services.cache_service import cache_service
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 定义数据获取函数（当缓存缺失时调用）
    def fetch_all_test_cases():
        """从数据库获取所有测试用例"""
        query = db.query(TestCase).filter(TestCase.project_id == project_id)
        
        # 应用SQL层过滤（在数据库中执行，而不是在Python中）
        if module:
            query = query.filter(TestCase.module == module)
        if case_type:
            query = query.filter(TestCase.case_type == case_type)
        if status:
            query = query.filter(TestCase.status == status)
        
        # 使用SQL的LIKE过滤场景用例（比Python过滤更高效）
        if is_scenario is not None:
            if is_scenario:
                # 只返回场景用例：名称包含"场景"的用例
                query = query.filter(TestCase.name.like('%场景%'))
            else:
                # 只返回普通接口用例：名称不包含"场景"的用例
                query = query.filter(~TestCase.name.like('%场景%'))
        
        test_cases = query.order_by(TestCase.created_at.desc()).all()
        
        # 转换为字典列表（用于JSON序列化和缓存）
        result = []
        for tc in test_cases:
            result.append({
                "id": tc.id,
                "name": tc.name,
                "module": tc.module,
                "case_type": tc.case_type,
                "status": tc.status,
                "description": tc.description,
                "created_at": tc.created_at.isoformat() if tc.created_at else None,
                "updated_at": tc.updated_at.isoformat() if tc.updated_at else None
            })
        
        return result
    
    # 性能测试用例Tab对实时性要求高，跳过缓存直接查数据库
    if case_type == "jmeter":
        data = fetch_all_test_cases()
        total_count = len(data)
        total_pages = (total_count + page_size - 1) // page_size
        if page < 1:
            page = 1
        if page > total_pages and total_pages > 0:
            page = total_pages
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_data = data[start_idx:end_idx]
        current_page = page
    else:
        # 构建缓存键（包含所有过滤条件）
        cache_key = f"test_cases:{project_id}:{module or 'all'}:{case_type or 'all'}:{status or 'all'}:{is_scenario or 'all'}"
        
        # 使用缓存服务获取分页数据
        paginated_data, total_count, total_pages, current_page = cache_service.get_paginated_list(
            cache_key=cache_key,
            page=page,
            page_size=page_size,
            fetch_all_func=fetch_all_test_cases,
            cache_type='test_cases'
        )
    
    return {
        "data": paginated_data,
        "pagination": {
            "page": current_page,
            "page_size": page_size,
            "total": total_count,
            "total_pages": total_pages
        }
    }


@router.get("/modules")
async def get_modules(
    project_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取项目下的所有模块列表（无需登录）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    modules = db.query(TestCase.module).filter(
        TestCase.project_id == project_id,
        TestCase.module.isnot(None),
        TestCase.module != ""
    ).distinct().all()
    
    return {"modules": [m[0] for m in modules]}


@router.post("/generate-by-module")
async def generate_test_cases_by_module(
    project_id: int,
    module: str = Query(..., description="模块名称"),
    case_type: str = Query(..., description="用例类型: pytest(接口测试用例) 或 jmeter(性能测试用例)"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """根据模块生成测试用例（考虑正常场景、异常场景、边界值等）"""
    if case_type not in ["pytest", "jmeter"]:
        raise HTTPException(status_code=400, detail="不支持的用例类型，只支持 pytest 或 jmeter")
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取该模块下的所有接口
    # 策略1: 从数据库中的场景用例集获取接口信息（优先）
    interfaces_info = []
    # 创建Redis客户端（在函数作用域内）
    redis_client_temp = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
        encoding='utf-8'
    )
    
    try:
        # 首先尝试从数据库查找场景用例集
        from app.models import TestCaseSuite
        
        # 清理模块名称：去除"None"、"null"等无效后缀
        cleaned_module = module
        if cleaned_module:
            # 去除常见的无效后缀
            for suffix in ['_None', '_null', '_None_', 'None', 'null']:
                if cleaned_module.endswith(suffix):
                    cleaned_module = cleaned_module[:-len(suffix)].rstrip('_')
                    break
            # 如果清理后为空，使用原始值
            if not cleaned_module:
                cleaned_module = module
        
        # 优先精确匹配（使用原始模块名和清理后的模块名）
        suite = db.query(TestCaseSuite).filter(
            TestCaseSuite.project_id == project_id,
            TestCaseSuite.name == module
        ).first()
        
        # 如果原始模块名精确匹配失败，尝试清理后的模块名精确匹配
        if not suite and cleaned_module != module:
            suite = db.query(TestCaseSuite).filter(
                TestCaseSuite.project_id == project_id,
                TestCaseSuite.name == cleaned_module
            ).first()
        
        # 如果精确匹配失败，尝试模糊匹配
        if not suite:
            all_suites = db.query(TestCaseSuite).filter(
                TestCaseSuite.project_id == project_id
            ).all()
            
            # 优先精确匹配（使用清理后的模块名），并且优先选择更短的名称（避免选择 '其他[V1]' 而不是 '其他'）
            # 先收集所有精确匹配的候选
            exact_matches = []
            for s in all_suites:
                suite_name = s.name or ''
                if suite_name == cleaned_module or suite_name == module:
                    exact_matches.append((s, suite_name))
            
            if exact_matches:
                # 如果有多个精确匹配，选择名称最短的（更精确）
                exact_matches.sort(key=lambda x: len(x[1]))
                suite, suite_name = exact_matches[0]
                print(f"精确匹配到场景用例集: '{suite_name}' (模块名: '{module}', 清理后: '{cleaned_module}')")
            else:
                # 如果精确匹配失败，尝试反向匹配：如果场景用例集名称包含在模块名中（例如："其他" 包含在 "其他_None" 中）
                # 同样优先选择更短的名称
                reverse_matches = []
                for s in all_suites:
                    suite_name = s.name or ''
                    if suite_name in cleaned_module or suite_name in module:
                        reverse_matches.append((s, suite_name))
                
                if reverse_matches:
                    # 如果有多个反向匹配，选择名称最短的（更精确）
                    reverse_matches.sort(key=lambda x: len(x[1]))
                    suite, suite_name = reverse_matches[0]
                    print(f"反向匹配到场景用例集: '{suite_name}' (模块名: '{module}')")
                else:
                    # 如果反向匹配失败，尝试正向匹配
                    forward_matches = []
                    for s in all_suites:
                        suite_name = s.name or ''
                        # 包含匹配
                        if cleaned_module in suite_name or module in suite_name:
                            forward_matches.append((s, suite_name))
                        # 去除"相关的接口"后缀后匹配
                        elif cleaned_module.replace('相关的接口', '') in suite_name.replace('相关的接口', ''):
                            forward_matches.append((s, suite_name))
                    
                    if forward_matches:
                        # 如果有多个正向匹配，选择名称最短的（更精确）
                        forward_matches.sort(key=lambda x: len(x[1]))
                        suite, suite_name = forward_matches[0]
                        print(f"包含匹配到场景用例集: '{suite_name}' (模块名: '{module}')")
        
        if suite:
            print(f"✓ 成功匹配到场景用例集: '{suite.name}' (ID: {suite.id})")
            # 从场景用例集中提取接口信息
            try:
                case_ids = json.loads(suite.test_case_ids) if suite.test_case_ids else []
            except Exception as e:
                print(f"✗ 解析test_case_ids失败: {e}")
                print(f"  test_case_ids原始值: {suite.test_case_ids}")
                case_ids = []
            
            print(f"从数据库场景用例集 '{suite.name}' 找到 {len(case_ids)} 个用例ID")
            if len(case_ids) > 0:
                print(f"用例ID示例: {case_ids[:3]}")
            else:
                print(f"⚠️  警告：场景用例集 '{suite.name}' 的test_case_ids为空或格式不正确")
            
            found_count = 0
            skipped_count = 0
            for case_id in case_ids:
                if case_id == '__LOGIN_INTERFACE__':
                    skipped_count += 1
                    continue
                
                # 尝试从数据库获取接口信息
                interface_info = None
                interface_id = None
                
                # 处理不同类型的case_id格式
                if isinstance(case_id, str):
                    # 可能是 "api_123" 格式
                    if case_id.startswith('api_'):
                        try:
                            interface_id = int(case_id.replace('api_', ''))
                        except Exception as e:
                            print(f"解析api_格式失败: {case_id}, 错误: {e}")
                            pass
                    # 可能是纯数字字符串 "123" 或 "1198"
                    elif case_id.isdigit():
                        try:
                            interface_id = int(case_id)
                            print(f"成功解析数字字符串: {case_id} -> {interface_id}")
                        except Exception as e:
                            print(f"解析数字字符串失败: {case_id}, 错误: {e}")
                            pass
                    else:
                        # 尝试直接转换为整数（处理其他可能的数字格式）
                        try:
                            interface_id = int(case_id)
                            print(f"直接转换成功: {case_id} -> {interface_id}")
                        except:
                            print(f"无法识别的字符串格式: {case_id}")
                elif isinstance(case_id, int):
                    interface_id = case_id
                else:
                    print(f"无法识别的case_id类型: {type(case_id)}, 值: {case_id}")
                
                if interface_id:
                    interface_info = db.query(DocumentAPIInterface).filter(
                        DocumentAPIInterface.id == interface_id,
                        DocumentAPIInterface.project_id == project_id
                    ).first()
                    
                    if interface_info:
                        interfaces_info.append({
                            'id': interface_info.id,
                            'name': interface_info.name,
                            'method': interface_info.method,
                            'url': interface_info.url,
                            'path': interface_info.path,
                            'headers': interface_info.headers,
                            'request_body': interface_info.request_body,
                            'response_body': interface_info.response_body,
                            'description': interface_info.description
                        })
                        found_count += 1
                    else:
                        print(f"警告：接口ID {interface_id} 在DocumentAPIInterface中不存在（project_id={project_id}）")
                else:
                    print(f"警告：无法解析用例ID: {case_id} (类型: {type(case_id)})")
            
            print(f"从场景用例集中成功提取 {found_count} 个接口信息 (跳过登录接口: {skipped_count} 个)")
            if found_count == 0 and len(case_ids) > skipped_count:
                print(f"⚠️  警告：场景用例集 '{suite.name}' 有 {len(case_ids)} 个用例ID，但无法解析或找不到对应的接口")
                print(f"  请检查：1) 接口ID是否正确；2) DocumentAPIInterface表中是否存在这些接口")
        else:
            print(f"✗ 数据库中没有找到匹配的场景用例集 (模块名: '{module}', 清理后: '{cleaned_module}')")
            # 如果数据库中没有，尝试从Redis获取
            redis_key = f"project:{project_id}:scenarios"
            scenarios_data = redis_client_temp.get(redis_key)
            
            if scenarios_data:
                scenarios_json = json.loads(scenarios_data)
                scenarios = scenarios_json.get('scenarios', [])
                print(f"从Redis获取到 {len(scenarios)} 个场景用例集")
                
                # 查找匹配模块名称的场景用例集（支持多种匹配方式）
                matched_scenario = None
                
                # 优先精确匹配
                for scenario in scenarios:
                    scenario_name = scenario.get('name', '')
                    if scenario_name == cleaned_module or scenario_name == module:
                        matched_scenario = scenario
                        print(f"✓ Redis中精确匹配到场景用例集: '{scenario_name}'")
                        break
                
                # 如果精确匹配失败，尝试反向匹配
                if not matched_scenario:
                    for scenario in scenarios:
                        scenario_name = scenario.get('name', '')
                        # 如果场景用例集名称包含在模块名中（例如："其他" 包含在 "其他_None" 中）
                        if scenario_name in cleaned_module or scenario_name in module:
                            matched_scenario = scenario
                            print(f"✓ Redis中反向匹配到场景用例集: '{scenario_name}'")
                            break
                
                # 如果反向匹配失败，尝试正向匹配
                if not matched_scenario:
                    for scenario in scenarios:
                        scenario_name = scenario.get('name', '')
                        # 包含匹配（模块名称包含在场景名称中，或场景名称包含在模块名称中）
                        if cleaned_module in scenario_name or module in scenario_name:
                            matched_scenario = scenario
                            print(f"✓ Redis中包含匹配到场景用例集: '{scenario_name}'")
                            break
                        # 去除"相关的接口"后缀后匹配
                        elif cleaned_module.replace('相关的接口', '') in scenario_name.replace('相关的接口', ''):
                            matched_scenario = scenario
                            print(f"✓ Redis中去除后缀后匹配到场景用例集: '{scenario_name}'")
                            break
                
                if matched_scenario:
                    # 从场景用例集中提取接口信息
                    case_ids = matched_scenario.get('test_case_ids', [])
                    print(f"从Redis场景用例集 '{matched_scenario.get('name')}' 找到 {len(case_ids)} 个用例ID")
                    
                    redis_found_count = 0
                    for case_id in case_ids:
                        if case_id == '__LOGIN_INTERFACE__':
                            continue
                        
                        # 尝试从数据库获取接口信息
                        interface_info = None
                        interface_id = None
                        
                        # 处理不同类型的case_id格式（与数据库逻辑一致）
                        if isinstance(case_id, str):
                            if case_id.startswith('api_'):
                                try:
                                    interface_id = int(case_id.replace('api_', ''))
                                except:
                                    pass
                            elif case_id.isdigit():
                                try:
                                    interface_id = int(case_id)
                                except:
                                    pass
                            else:
                                try:
                                    interface_id = int(case_id)
                                except:
                                    pass
                        elif isinstance(case_id, int):
                            interface_id = case_id
                        
                        if interface_id:
                            interface_info = db.query(DocumentAPIInterface).filter(
                                DocumentAPIInterface.id == interface_id,
                                DocumentAPIInterface.project_id == project_id
                            ).first()
                            
                            if interface_info:
                                interfaces_info.append({
                                    'id': interface_info.id,
                                    'name': interface_info.name,
                                    'method': interface_info.method,
                                    'url': interface_info.url,
                                    'path': interface_info.path,
                                    'headers': interface_info.headers,
                                    'request_body': interface_info.request_body,
                                    'response_body': interface_info.response_body,
                                    'description': interface_info.description
                                })
                                redis_found_count += 1
                            else:
                                print(f"警告：Redis场景用例集中的接口ID {interface_id} 在DocumentAPIInterface中不存在")
                    
                    print(f"从Redis场景用例集中成功提取 {redis_found_count} 个接口信息")
            else:
                print(f"Redis中没有场景用例集数据（key: {redis_key}）")
    except Exception as e:
        print(f"从场景用例集获取接口信息失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 调试信息：打印找到的接口数量
    print(f"模块 '{module}' 找到 {len(interfaces_info)} 个接口（策略1）")
    
    # 策略2: 从已有的测试用例中查找
    if not interfaces_info:
        print(f"策略1未找到接口，尝试策略2：从已有测试用例查找")
        # 首先尝试精确匹配模块名
        test_cases = db.query(TestCase).filter(
            TestCase.project_id == project_id,
            TestCase.module == module
        ).all()
        
        # 如果精确匹配找不到，尝试模糊匹配（模块名包含在测试用例的module字段中，或反之）
        if not test_cases:
            print(f"精确匹配模块名 '{module}' 未找到测试用例，尝试模糊匹配")
            all_test_cases = db.query(TestCase).filter(
                TestCase.project_id == project_id
            ).all()
            
            # 查找模块名包含在测试用例module字段中，或测试用例module字段包含在模块名中的用例
            for tc in all_test_cases:
                if tc.module:
                    if module in tc.module or tc.module in module:
                        test_cases.append(tc)
        
        print(f"找到 {len(test_cases)} 个匹配的测试用例")
        
        interface_ids = [tc.api_interface_id for tc in test_cases if tc.api_interface_id]
        print(f"从测试用例中提取到 {len(interface_ids)} 个接口ID")
        
        if interface_ids:
            document_interfaces = db.query(DocumentAPIInterface).filter(
                DocumentAPIInterface.id.in_(interface_ids),
                DocumentAPIInterface.project_id == project_id
            ).all()
            
            print(f"从DocumentAPIInterface中找到 {len(document_interfaces)} 个接口")
            
            for interface_info in document_interfaces:
                # 检查是否已经添加过（避免重复）
                if not any(iface['id'] == interface_info.id for iface in interfaces_info):
                    interfaces_info.append({
                        'id': interface_info.id,
                        'name': interface_info.name,
                        'method': interface_info.method,
                        'url': interface_info.url,
                        'path': interface_info.path,
                        'headers': interface_info.headers,
                        'request_body': interface_info.request_body,
                        'response_body': interface_info.response_body,
                        'description': interface_info.description
                    })
            
            print(f"策略2成功添加 {len(interfaces_info)} 个接口")
    
    # 策略3: 从DocumentAPIInterface中通过名称匹配
    if not interfaces_info:
        print(f"策略2未找到接口，尝试策略3：从DocumentAPIInterface中通过名称匹配")
        document_interfaces = db.query(DocumentAPIInterface).filter(
            DocumentAPIInterface.project_id == project_id
        ).all()
        
        # 如果模块名称是单个词（如"场景"），尝试匹配以该词开头的场景用例集
        # 例如：模块名"场景"应该匹配"场景_1"、"场景_2"等场景用例集
        if module and '_' not in module and len(module) <= 10:  # 单个词且不太长
            # 尝试查找以该模块名开头的场景用例集
            from app.models import TestCaseSuite
            prefix_suites = db.query(TestCaseSuite).filter(
                TestCaseSuite.project_id == project_id,
                TestCaseSuite.name.like(f"{module}_%")
            ).all()
            
            if prefix_suites:
                print(f"找到 {len(prefix_suites)} 个以 '{module}' 开头的场景用例集")
                # 合并所有匹配的场景用例集的接口
                for suite in prefix_suites:
                    try:
                        case_ids = json.loads(suite.test_case_ids) if suite.test_case_ids else []
                        for case_id in case_ids:
                            if case_id == '__LOGIN_INTERFACE__':
                                continue
                            
                            interface_id = None
                            if isinstance(case_id, str):
                                if case_id.startswith('api_'):
                                    try:
                                        interface_id = int(case_id.replace('api_', ''))
                                    except:
                                        pass
                                elif case_id.isdigit():
                                    try:
                                        interface_id = int(case_id)
                                    except:
                                        pass
                            elif isinstance(case_id, int):
                                interface_id = case_id
                            
                            if interface_id:
                                interface_info = db.query(DocumentAPIInterface).filter(
                                    DocumentAPIInterface.id == interface_id,
                                    DocumentAPIInterface.project_id == project_id
                                ).first()
                                
                                if interface_info:
                                    # 检查是否已经添加过（避免重复）
                                    if not any(iface['id'] == interface_info.id for iface in interfaces_info):
                                        interfaces_info.append({
                                            'id': interface_info.id,
                                            'name': interface_info.name,
                                            'method': interface_info.method,
                                            'url': interface_info.url,
                                            'path': interface_info.path,
                                            'headers': interface_info.headers,
                                            'request_body': interface_info.request_body,
                                            'response_body': interface_info.response_body,
                                            'description': interface_info.description
                                        })
                    except Exception as e:
                        print(f"处理场景用例集 '{suite.name}' 时出错: {e}")
                
                if interfaces_info:
                    print(f"策略3（前缀匹配）找到 {len(interfaces_info)} 个接口")
        
        # 如果前缀匹配没有找到接口，继续使用原有的名称匹配逻辑
        if not interfaces_info:
            # 如果接口名称包含模块名称，则认为是该模块的接口
            matched_interfaces = [
                iface for iface in document_interfaces
                if module in (iface.name or '') or module in (iface.path or '') or (iface.description and module in iface.description)
            ]
            
            for interface_info in matched_interfaces:
                # 检查是否已经添加过（避免重复）
                if not any(iface['id'] == interface_info.id for iface in interfaces_info):
                    interfaces_info.append({
                        'id': interface_info.id,
                        'name': interface_info.name,
                        'method': interface_info.method,
                        'url': interface_info.url,
                        'path': interface_info.path,
                        'headers': interface_info.headers,
                        'request_body': interface_info.request_body,
                        'response_body': interface_info.response_body,
                        'description': interface_info.description
                    })
            print(f"策略3（名称匹配）找到 {len(interfaces_info)} 个接口")
    
    # 策略4: 兜底策略 - 如果模块名是通用词（如"场景"）且无法匹配，合并所有场景用例集的接口
    if not interfaces_info and module and '_' not in module and len(module) <= 10:
        print(f"策略3未找到接口，尝试策略4（兜底）：合并所有场景用例集的接口")
        from app.models import TestCaseSuite
        all_suites = db.query(TestCaseSuite).filter(
            TestCaseSuite.project_id == project_id
        ).all()
        
        if all_suites:
            print(f"找到 {len(all_suites)} 个场景用例集，尝试合并所有接口")
            for suite in all_suites:
                try:
                    case_ids = json.loads(suite.test_case_ids) if suite.test_case_ids else []
                    for case_id in case_ids:
                        if case_id == '__LOGIN_INTERFACE__':
                            continue
                        
                        interface_id = None
                        if isinstance(case_id, str):
                            if case_id.startswith('api_'):
                                try:
                                    interface_id = int(case_id.replace('api_', ''))
                                except:
                                    pass
                            elif case_id.isdigit():
                                try:
                                    interface_id = int(case_id)
                                except:
                                    pass
                        elif isinstance(case_id, int):
                            interface_id = case_id
                        
                        if interface_id:
                            interface_info = db.query(DocumentAPIInterface).filter(
                                DocumentAPIInterface.id == interface_id,
                                DocumentAPIInterface.project_id == project_id
                            ).first()
                            
                            if interface_info:
                                # 检查是否已经添加过（避免重复）
                                if not any(iface['id'] == interface_info.id for iface in interfaces_info):
                                    interfaces_info.append({
                                        'id': interface_info.id,
                                        'name': interface_info.name,
                                        'method': interface_info.method,
                                        'url': interface_info.url,
                                        'path': interface_info.path,
                                        'headers': interface_info.headers,
                                        'request_body': interface_info.request_body,
                                        'response_body': interface_info.response_body,
                                        'description': interface_info.description
                                    })
                except Exception as e:
                    print(f"处理场景用例集 '{suite.name}' 时出错: {e}")
            
            if interfaces_info:
                print(f"策略4（兜底）找到 {len(interfaces_info)} 个接口（来自所有场景用例集）")
    
    if not interfaces_info:
        # 提供更详细的调试信息和可用的场景用例集列表
        available_suite_names = []
        try:
            # 从数据库获取所有场景用例集名称
            from app.models import TestCaseSuite
            all_suites = db.query(TestCaseSuite).filter(
                TestCaseSuite.project_id == project_id
            ).all()
            available_suite_names = [s.name for s in all_suites if s.name]
            
            # 检查Redis中是否有数据
            redis_key = f"project:{project_id}:scenarios"
            scenarios_data = redis_client_temp.get(redis_key)
            if scenarios_data:
                scenarios_json = json.loads(scenarios_data)
                scenarios = scenarios_json.get('scenarios', [])
                redis_scenario_names = [s.get('name', '') for s in scenarios if s.get('name')]
                # 合并去重
                for name in redis_scenario_names:
                    if name and name not in available_suite_names:
                        available_suite_names.append(name)
                print(f"Redis中的场景用例集名称列表: {redis_scenario_names}")
            else:
                print(f"Redis中没有场景用例集数据（key: {redis_key}）")
            
            print(f"数据库中的场景用例集名称列表: {[s.name for s in all_suites]}")
        except Exception as e:
            print(f"获取场景用例集列表失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 检查是否有测试用例使用该模块名
        test_cases_count = db.query(TestCase).filter(
            TestCase.project_id == project_id,
            TestCase.module == module
        ).count()
        
        # 构建详细的错误信息
        error_detail = f"模块 '{module}' 下没有找到接口。"
        
        if test_cases_count > 0:
            error_detail += f"\n注意：找到 {test_cases_count} 个使用该模块名的测试用例，但这些用例可能没有关联接口。"
            error_detail += f"\n建议：请检查这些测试用例的 api_interface_id 字段是否正确设置。"
        
        if available_suite_names:
            error_detail += f"\n可用的场景用例集名称: {', '.join(available_suite_names[:10])}"  # 最多显示10个
            if len(available_suite_names) > 10:
                error_detail += f" 等共{len(available_suite_names)}个"
            error_detail += f"\n提示：如果模块名 '{module}' 与场景用例集名称不匹配，请："
            error_detail += f"\n  1) 在'场景用例集'页面查看实际的场景用例集名称"
            error_detail += f"\n  2) 使用场景用例集名称作为模块名重新生成"
            error_detail += f"\n  3) 或者从'场景用例集'页面直接生成测试用例"
        else:
            error_detail += "\n未找到任何场景用例集。"
        
        error_detail += "\n请确保：1) 已运行全局接口依赖分析；2) 该模块名称与场景用例集名称匹配；3) 接口名称或路径包含模块关键词"
        
        raise HTTPException(status_code=400, detail=error_detail)
    
    # 根据用例类型决定生成策略
    if case_type == "jmeter":
        # 性能测试用例：一个场景用例组只生成一个用例
        # 直接在这里处理，不进入后续的循环逻辑
        try:
            from app.models import TestCaseSuite
            # 查找匹配模块名称的场景用例集
            suite = db.query(TestCaseSuite).filter(
                TestCaseSuite.project_id == project_id,
                TestCaseSuite.name == module
            ).first()
            
            # 如果精确匹配失败，尝试模糊匹配
            if not suite:
                all_suites = db.query(TestCaseSuite).filter(
                    TestCaseSuite.project_id == project_id
                ).all()
                for s in all_suites:
                    suite_name = s.name or ''
                    if module in suite_name or suite_name in module:
                        suite = s
                        break
                    elif module.replace('相关的接口', '') in suite_name.replace('相关的接口', ''):
                        suite = s
                        break
            
            if not suite:
                raise HTTPException(status_code=400, detail=f"未找到场景用例集: {module}。请确保已运行全局接口依赖分析。")
            
            # 检查是否已经为该场景用例集生成了性能测试用例
            existing_jmeter_case = db.query(TestCase).filter(
                TestCase.project_id == project_id,
                TestCase.module == module,
                TestCase.case_type == 'jmeter',
                TestCase.name.like(f'%{module}%性能测试%')
            ).first()
            
            if existing_jmeter_case:
                # 如果已存在，更新状态为生成中，并重新生成
                existing_jmeter_case.status = "generating"
                existing_jmeter_case.generation_progress = 0
                existing_jmeter_case.error_message = None
                db.commit()
                db.refresh(existing_jmeter_case)
                final_test_case = existing_jmeter_case
                test_case_ids = [existing_jmeter_case.id]
            else:
                # 创建新的性能测试用例（一个场景用例组只生成一个）
                jmeter_case_name = f"{module}_性能测试用例"
                jmeter_case = TestCase(
                    project_id=project_id,
                    api_interface_id=None,  # jmeter用例不关联单个接口
                    name=jmeter_case_name,
                    case_type='jmeter',
                    module=module,
                    status="generating",
                    generation_progress=0
                )
                db.add(jmeter_case)
                db.commit()
                db.refresh(jmeter_case)
                final_test_case = jmeter_case
                test_case_ids = [jmeter_case.id]
            
            # 从场景用例集生成性能测试用例
            from app.celery_tasks import generate_jmeter_performance_test_task
            
            # 获取场景用例集的接口信息
            case_ids = json.loads(suite.test_case_ids) if suite.test_case_ids else []
            scenario_interfaces_info = []
            login_interface_info = None
            environment_info = {"base_url": "", "xjid": "", "username": ""}
            
            print(f"[性能测试用例生成] 场景用例集 '{suite.name}' 的case_ids: {case_ids}, 数量: {len(case_ids)}")
            
            # 从Redis获取场景用例集的详细信息
            try:
                redis_key = f"project:{project_id}:scenarios"
                scenarios_data = redis_client_temp.get(redis_key)
                if scenarios_data:
                    scenarios_json = json.loads(scenarios_data)
                    scenarios = scenarios_json.get('scenarios', [])
                    matched_scenario = next((s for s in scenarios if s.get('name') == module), None)
                    if matched_scenario:
                        login_interface_info = scenarios_json.get('login_interface')
                        print(f"[性能测试用例生成] 从Redis获取到登录接口信息: {login_interface_info is not None}")
            except Exception as e:
                print(f"[性能测试用例生成] 从Redis获取场景信息失败: {e}")
                pass
            
            # 构建接口信息列表（包括所有场景中的接口）
            found_interface_count = 0
            for case_id in case_ids:
                if case_id == '__LOGIN_INTERFACE__':
                    continue
                
                interface_id = None
                if isinstance(case_id, str):
                    if case_id.startswith('api_'):
                        try:
                            interface_id = int(case_id.replace('api_', ''))
                        except:
                            pass
                    elif case_id.isdigit():
                        try:
                            interface_id = int(case_id)
                        except:
                            pass
                elif isinstance(case_id, int):
                    interface_id = case_id
                
                if interface_id:
                    interface_info = db.query(DocumentAPIInterface).filter(
                        DocumentAPIInterface.id == interface_id,
                        DocumentAPIInterface.project_id == project_id
                    ).first()
                    if interface_info:
                        # 解析headers和request_body
                        headers = interface_info.headers
                        if headers and isinstance(headers, str):
                            try:
                                headers = json.loads(headers)
                            except:
                                headers = {}
                        
                        request_body = interface_info.request_body
                        if request_body and isinstance(request_body, str):
                            try:
                                request_body = json.loads(request_body)
                            except:
                                request_body = {}
                        
                        response_body = interface_info.response_body
                        if response_body and isinstance(response_body, str):
                            try:
                                response_body = json.loads(response_body)
                            except:
                                response_body = {}
                        
                        scenario_interfaces_info.append({
                            'id': interface_info.id,
                            'name': interface_info.name,
                            'method': interface_info.method or 'GET',
                            'url': interface_info.url or '',
                            'path': interface_info.path or '',
                            'base_url': interface_info.base_url or '',
                            'headers': headers,
                            'request_body': request_body,
                            'response_body': response_body,
                            'description': interface_info.description or ''
                        })
                        found_interface_count += 1
                        print(f"[性能测试用例生成] 找到接口 {found_interface_count}: {interface_info.name} (ID: {interface_id})")
                    else:
                        print(f"[性能测试用例生成] 警告: 接口ID {interface_id} 在DocumentAPIInterface中不存在")
                else:
                    print(f"[性能测试用例生成] 警告: 无法解析case_id: {case_id}")
            
            # 检查是否找到接口
            if not scenario_interfaces_info or len(scenario_interfaces_info) == 0:
                error_msg = f"性能测试用例接口列表为空。场景用例集 '{suite.name}' 的case_ids: {case_ids}，但未找到有效的接口信息。可能原因：1) case_ids为空或格式不正确；2) 接口ID在DocumentAPIInterface中不存在；3) 接口的project_id不匹配"
                print(f"[性能测试用例生成] 错误: {error_msg}")
                raise HTTPException(status_code=400, detail=error_msg)
            
            print(f"[性能测试用例生成] 成功构建 {len(scenario_interfaces_info)} 个接口信息")
            
            # 获取测试环境信息（用于base_url等）
            try:
                from app.models import TestEnvironment
                test_env = db.query(TestEnvironment).filter(
                    TestEnvironment.project_id == project_id,
                    TestEnvironment.is_default == True
                ).first()
                if test_env:
                    environment_info = {
                        "base_url": test_env.base_url or "",
                        "xjid": test_env.xjid or "",
                        "username": test_env.login_username or ""
                    }
            except:
                pass
            
            # 提交JMeter性能测试用例生成任务（整个场景用例组生成一个JMX）
            task = generate_jmeter_performance_test_task.delay(
                test_case_id=final_test_case.id,
                suite_id=suite.id,
                project_id=project_id,
                interfaces_info=scenario_interfaces_info,
                login_token="{{TOKEN}}",
                few_shot_interfaces=[],
                environment_info=environment_info,
                login_interface_info=login_interface_info,
                threads=10
            )
            
            # 更新任务ID
            final_test_case.generation_task_id = task.id
            db.commit()
            
            # 清理测试用例列表缓存，避免性能测试用例Tab读取到旧缓存
            try:
                cache_service.invalidate_cache(f"test_cases:{project_id}:*")
            except Exception as cache_error:
                print(f"[性能测试用例生成] 清理缓存失败: {cache_error}")
            
            return {
                "message": f"性能测试用例生成任务已提交",
                "test_case_ids": test_case_ids,
                "module": module,
                "case_type": case_type,
                "async": True
            }
        except Exception as e:
            print(f"生成性能测试用例失败: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"生成性能测试用例失败: {str(e)}")
    
    # 接口测试用例：为每个接口创建或查找对应的APIInterface记录
    from app.models import APIInterface
    test_case_ids = []
    
    # 修改逻辑：一个模块/组只生成一个测试用例文件，包含该组内所有接口的测试用例
    if case_type == "pytest" and len(interfaces_info) > 0:
        # 对于pytest类型的接口测试用例，一个模块只生成一个测试用例文件
        # 检查是否已存在该模块的测试用例
        module_test_case_name = f"{module}_测试用例"
        existing_module_case = db.query(TestCase).filter(
            TestCase.project_id == project_id,
            TestCase.case_type == case_type,
            TestCase.module == module,
            TestCase.name == module_test_case_name,
            TestCase.api_interface_id.is_(None)  # 模块级测试用例不关联单个接口
        ).first()
        
        if existing_module_case:
            # 如果已存在，更新状态为生成中
            existing_module_case.status = "generating"
            existing_module_case.generation_progress = 0
            existing_module_case.error_message = None
            db.commit()
            db.refresh(existing_module_case)
            test_case_ids.append(existing_module_case.id)
            final_test_case = existing_module_case
        else:
            # 创建新的模块级测试用例记录
            module_test_case = TestCase(
                project_id=project_id,
                api_interface_id=None,  # 模块级测试用例不关联单个接口
                name=module_test_case_name,
                case_type=case_type,
                module=module,
                status="generating",
                generation_progress=0
            )
            db.add(module_test_case)
            db.commit()
            db.refresh(module_test_case)
            test_case_ids.append(module_test_case.id)
            final_test_case = module_test_case
        
        # 查找匹配模块名称的场景用例集
        from app.models import TestCaseSuite
        suite = db.query(TestCaseSuite).filter(
            TestCaseSuite.project_id == project_id,
            TestCaseSuite.name == module
        ).first()
        
        # 如果精确匹配失败，尝试模糊匹配
        if not suite:
            all_suites = db.query(TestCaseSuite).filter(
                TestCaseSuite.project_id == project_id
            ).all()
            for s in all_suites:
                suite_name = s.name or ''
                if module in suite_name or suite_name in module:
                    suite = s
                    break
                elif module.replace('相关的接口', '') in suite_name.replace('相关的接口', ''):
                    suite = s
                    break
        
        # 构建所有接口的信息（用于生成测试用例）
        all_interfaces_info = []
        login_interface_info = None
        
        # 从Redis获取登录接口信息
        try:
            redis_key = f"project:{project_id}:scenarios"
            scenarios_data = redis_client_temp.get(redis_key)
            if scenarios_data:
                scenarios_json = json.loads(scenarios_data)
                login_interface_info = scenarios_json.get('login_interface')
        except:
            pass
        
        # 构建接口信息列表
        for interface_data in interfaces_info:
            interface_name = interface_data.get('name', '')
            interface_url = interface_data.get('url') or interface_data.get('path', '')
            
            # 解析headers和request_body
            headers = interface_data.get('headers')
            if headers and isinstance(headers, str):
                try:
                    headers = json.loads(headers)
                except:
                    headers = {}
            
            request_body = interface_data.get('request_body')
            if request_body and isinstance(request_body, str):
                try:
                    request_body = json.loads(request_body)
                except:
                    request_body = {}
            
            response_body = interface_data.get('response_body')
            if response_body and isinstance(response_body, str):
                try:
                    response_body = json.loads(response_body)
                except:
                    response_body = {}
            
            all_interfaces_info.append({
                'id': interface_data.get('id'),
                'name': interface_name,
                'method': interface_data.get('method', 'GET'),
                'url': interface_url,
                'path': interface_data.get('path', ''),
                'base_url': interface_data.get('base_url', ''),
                'headers': headers,
                'request_body': request_body,
                'response_body': response_body,
                'description': interface_data.get('description', '')
            })
        
        # 获取测试环境信息
        from app.models import TestEnvironment
        environment_info = {"base_url": "", "xjid": "", "username": ""}
        try:
            test_env = db.query(TestEnvironment).filter(
                TestEnvironment.project_id == project_id,
                TestEnvironment.is_default == True
            ).first()
            if test_env:
                environment_info = {
                    "base_url": test_env.base_url or "",
                    "xjid": test_env.xjid or "",
                    "username": test_env.login_username or ""
                }
        except:
            pass
        
        # 使用场景测试用例生成任务，但生成普通接口测试用例（不是场景用例）
        # 第一个接口作为登录接口，后续接口是需要生成测试用例的业务接口
        if suite:
            from app.celery_tasks import generate_scenario_test_case_task
            
            # 将登录接口放在第一个位置
            interfaces_with_login = []
            if login_interface_info:
                interfaces_with_login.append(login_interface_info)
            interfaces_with_login.extend(all_interfaces_info)
            
            # 提交任务生成包含所有接口的测试用例
            task = generate_scenario_test_case_task.delay(
                test_case_id=final_test_case.id,
                suite_id=suite.id,
                project_id=project_id,
                interfaces_info=interfaces_with_login,
                login_token="{{TOKEN}}",
                few_shot_interfaces=[],
                environment_info=environment_info,
                login_interface_info=login_interface_info,
                threads=10
            )
        else:
            # 如果没有场景用例集，使用普通生成任务（但只生成一个测试用例文件）
            from app.celery_tasks import generate_test_case_task
            # 使用第一个接口作为代表（实际上不会使用，因为会生成所有接口的测试用例）
            first_interface = interfaces_info[0] if interfaces_info else None
            if first_interface:
                # 查找或创建APIInterface记录
                interface_name = first_interface.get('name', '')
                interface_url = first_interface.get('url') or first_interface.get('path', '')
                api_interface = db.query(APIInterface).filter(
                    APIInterface.project_id == project_id,
                    APIInterface.name == interface_name,
                    APIInterface.url == interface_url
                ).first()
                
                if not api_interface:
                    api_interface = APIInterface(
                        project_id=project_id,
                        name=interface_name,
                        method=first_interface.get('method', 'GET') or "GET",
                        url=interface_url,
                        headers=json.dumps(first_interface.get('headers', {}), ensure_ascii=False) if first_interface.get('headers') else None,
                        body=json.dumps(first_interface.get('request_body', {}), ensure_ascii=False) if first_interface.get('request_body') else None,
                        response_schema=json.dumps(first_interface.get('response_body', {}), ensure_ascii=False) if first_interface.get('response_body') else None,
                        description=first_interface.get('description')
                    )
                    db.add(api_interface)
                    db.commit()
                    db.refresh(api_interface)
                
                final_test_case.api_interface_id = api_interface.id
                db.commit()
                
                task = generate_test_case_task.delay(
                    test_case_id=final_test_case.id,
                    case_type=case_type,
                    project_id=project_id,
                    api_interface_id=api_interface.id,
                    module=module
                )
            else:
                raise HTTPException(status_code=400, detail="没有找到接口信息")
        
        # 更新任务ID
        final_test_case.generation_task_id = task.id
        db.commit()
        
        return {
            "message": f"已为模块 '{module}' 提交测试用例生成任务（包含 {len(interfaces_info)} 个接口）",
            "test_case_ids": test_case_ids,
            "module": module,
            "case_type": case_type,
            "async": True
        }
    
    # 对于jmeter类型或其他情况，保持原有逻辑（为每个接口生成一个测试用例）
    for interface_data in interfaces_info:
        # 查找或创建对应的APIInterface记录
        interface_name = interface_data.get('name', '')
        interface_url = interface_data.get('url') or interface_data.get('path', '')
        
        api_interface = db.query(APIInterface).filter(
            APIInterface.project_id == project_id,
            APIInterface.name == interface_name,
            APIInterface.url == interface_url
        ).first()
        
        if not api_interface:
            # 创建APIInterface记录
            headers = interface_data.get('headers')
            if headers and not isinstance(headers, str):
                headers = json.dumps(headers, ensure_ascii=False)
            
            request_body = interface_data.get('request_body')
            if request_body and not isinstance(request_body, str):
                request_body = json.dumps(request_body, ensure_ascii=False)
            
            response_body = interface_data.get('response_body')
            if response_body and not isinstance(response_body, str):
                response_body = json.dumps(response_body, ensure_ascii=False)
            
            api_interface = APIInterface(
                project_id=project_id,
                name=interface_name,
                method=interface_data.get('method', 'GET') or "GET",
                url=interface_url,
                headers=headers,
                body=request_body,
                params=None,  # DocumentAPIInterface可能没有params字段
                response_schema=response_body,
                description=interface_data.get('description')
            )
            db.add(api_interface)
            db.commit()
            db.refresh(api_interface)
        
        # 创建测试用例记录
        # 根据case_type决定用例名称格式：
        # - pytest类型且不是场景用例：不包含"场景"字样，显示在"接口测试用例"tab
        # - jmeter类型：显示在"性能测试用例"tab
        if case_type == "pytest":
            # 普通接口用例：不包含"场景"字样
            test_case_name = f"{module}_{interface_name}_测试用例"
        else:
            # 性能测试用例
            test_case_name = f"{module}_{interface_name}_性能测试用例"
        
        # 检查是否已存在相同的测试用例
        existing_case = db.query(TestCase).filter(
            TestCase.project_id == project_id,
            TestCase.api_interface_id == api_interface.id,
            TestCase.case_type == case_type,
            TestCase.module == module,
            TestCase.name == test_case_name
        ).first()
        
        if existing_case:
            # 如果已存在，更新状态为生成中
            existing_case.status = "generating"
            existing_case.generation_progress = 0
            existing_case.error_message = None
            db.commit()
            db.refresh(existing_case)
            test_case_ids.append(existing_case.id)
            final_test_case = existing_case
        else:
            # 创建新的测试用例记录
            test_case = TestCase(
                project_id=project_id,
                api_interface_id=api_interface.id,
                name=test_case_name,
                case_type=case_type,
                module=module,
                status="generating",
                generation_progress=0
            )
            db.add(test_case)
            db.commit()
            db.refresh(test_case)
            test_case_ids.append(test_case.id)
            final_test_case = test_case
        
        # 提交异步生成任务（只处理pytest类型的接口测试用例）
        if case_type == "pytest":
            # 接口测试用例（pytest）：需要从场景用例中获取代码，构建RAG上下文
            try:
                from app.models import TestCaseSuite
                # 查找匹配模块名称的场景用例集
                suite = db.query(TestCaseSuite).filter(
                    TestCaseSuite.project_id == project_id,
                    TestCaseSuite.name == module
                ).first()
                
                # 如果精确匹配失败，尝试模糊匹配
                if not suite:
                    all_suites = db.query(TestCaseSuite).filter(
                        TestCaseSuite.project_id == project_id
                    ).all()
                    for s in all_suites:
                        suite_name = s.name or ''
                        if module in suite_name or suite_name in module:
                            suite = s
                            break
                        elif module.replace('相关的接口', '') in suite_name.replace('相关的接口', ''):
                            suite = s
                            break
                
                if suite:
                    # 从场景用例集中获取场景测试用例的代码
                    from app.celery_tasks import generate_interface_test_case_from_scenario_task
                    
                    # 获取场景用例集中对应的场景测试用例（名称包含"场景"）
                    scenario_test_cases = db.query(TestCase).filter(
                        TestCase.project_id == project_id,
                        TestCase.module == module,
                        TestCase.case_type == 'pytest',
                        TestCase.name.like('%场景%')
                    ).all()
                    
                    # 获取场景用例集的接口信息
                    case_ids = json.loads(suite.test_case_ids) if suite.test_case_ids else []
                    scenario_interfaces_info = []
                    
                    for case_id in case_ids:
                        if case_id == '__LOGIN_INTERFACE__':
                            continue
                        
                        interface_id = None
                        if isinstance(case_id, str):
                            if case_id.startswith('api_'):
                                try:
                                    interface_id = int(case_id.replace('api_', ''))
                                except:
                                    pass
                            elif case_id.isdigit():
                                try:
                                    interface_id = int(case_id)
                                except:
                                    pass
                        elif isinstance(case_id, int):
                            interface_id = case_id
                        
                        if interface_id:
                            interface_info = db.query(DocumentAPIInterface).filter(
                                DocumentAPIInterface.id == interface_id,
                                DocumentAPIInterface.project_id == project_id
                            ).first()
                            if interface_info:
                                scenario_interfaces_info.append({
                                    'id': interface_info.id,
                                    'name': interface_info.name,
                                    'method': interface_info.method,
                                    'url': interface_info.url,
                                    'path': interface_info.path,
                                    'headers': interface_info.headers,
                                    'request_body': interface_info.request_body,
                                    'response_body': interface_info.response_body,
                                    'description': interface_info.description
                                })
                    
                    # 从Redis获取场景用例集的详细信息（包括登录接口）
                    login_interface_info = None
                    try:
                        redis_key = f"project:{project_id}:scenarios"
                        scenarios_data = redis_client_temp.get(redis_key)
                        if scenarios_data:
                            scenarios_json = json.loads(scenarios_data)
                            login_interface_info = scenarios_json.get('login_interface')
                    except:
                        pass
                    
                    # 提交接口测试用例生成任务（从场景用例生成）
                    task = generate_interface_test_case_from_scenario_task.delay(
                        test_case_id=final_test_case.id,
                        suite_id=suite.id,
                        project_id=project_id,
                        api_interface_id=api_interface.id,
                        module=module,
                        scenario_test_cases=[{
                            'id': tc.id,
                            'name': tc.name,
                            'test_code': tc.test_code,
                            'module': tc.module
                        } for tc in scenario_test_cases],
                        scenario_interfaces_info=scenario_interfaces_info,
                        login_interface_info=login_interface_info
                    )
                else:
                    # 如果没有找到场景用例集，使用普通生成任务
                    task = generate_test_case_task.delay(
                        test_case_id=final_test_case.id,
                        case_type=case_type,
                        project_id=project_id,
                        api_interface_id=api_interface.id,
                        module=module
                    )
            except Exception as e:
                print(f"生成接口测试用例失败，使用普通生成任务: {e}")
                import traceback
                traceback.print_exc()
                task = generate_test_case_task.delay(
                    test_case_id=final_test_case.id,
                    case_type=case_type,
                    project_id=project_id,
                    api_interface_id=api_interface.id,
                    module=module
                )
        
        # 更新任务ID
        final_test_case.generation_task_id = task.id
        db.commit()
    
    return {
        "message": f"已为模块 '{module}' 提交 {len(test_case_ids)} 个测试用例生成任务",
        "test_case_ids": test_case_ids,
        "module": module,
        "case_type": case_type,
        "async": True
    }


@router.get("/{test_case_id}")
async def get_test_case(
    test_case_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取测试用例详情"""
    test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
    if not test_case:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    
    # 检查权限（如果用户已登录）
    # 注意：如果用户未登录，允许访问（因为get_current_user_optional可能返回None）
    if current_user and hasattr(current_user, 'id') and current_user.id:
        project = db.query(Project).filter(
            Project.id == test_case.project_id,
            Project.user_id == current_user.id
        ).first()
        if not project:
            raise HTTPException(status_code=403, detail="无权访问")
    
    # 如果是异步生成，检查任务状态
    task_status = None
    if test_case.generation_task_id:
        try:
            from app.celery_app import celery_app
            from celery.result import AsyncResult
            
            try:
                task = AsyncResult(test_case.generation_task_id, app=celery_app)
                
                # 安全地获取任务状态
                try:
                    task_state = task.state
                except Exception as state_error:
                    print(f"获取任务状态失败: {state_error}")
                    task_state = "UNKNOWN"
                
                # 获取任务详细信息
                task_info = {}
                try:
                    if task_state == 'PROGRESS':
                        task_info = task.info or {}
                    elif task_state == 'SUCCESS':
                        task_info = task.result or {}
                    elif task_state == 'FAILURE':
                        try:
                            task_info = {
                                'error': str(task.info) if task.info else '任务执行失败',
                                'traceback': task.traceback if hasattr(task, 'traceback') else None
                            }
                        except Exception as info_error:
                            task_info = {'error': '无法获取错误详情'}
                    
                    task_status = {
                        "task_id": test_case.generation_task_id,
                        "state": task_state,
                        "progress": task_info.get('progress', test_case.generation_progress) if task_info else test_case.generation_progress,
                        "message": task_info.get('message', ''),
                        "result": task.result if hasattr(task, 'result') and task.ready() else None,
                        "error": task_info.get('error') if task_state == 'FAILURE' else None
                    }
                except Exception as info_error:
                    print(f"获取任务详细信息失败: {info_error}")
                    task_status = {
                        "task_id": test_case.generation_task_id,
                        "state": task_state,
                        "progress": test_case.generation_progress,
                        "message": f"获取任务详细信息失败: {str(info_error)}",
                        "result": None,
                        "error": None
                    }
            except Exception as task_error:
                print(f"创建AsyncResult对象失败: {task_error}")
                task_status = {
                    "task_id": test_case.generation_task_id,
                    "state": "UNKNOWN",
                    "progress": test_case.generation_progress,
                    "message": f"无法创建任务对象: {str(task_error)}",
                    "result": None,
                    "error": None
                }
        except Exception as e:
            # 如果获取任务状态失败，不影响返回测试用例信息
            import traceback
            print(f"获取任务状态失败: {e}")
            traceback.print_exc()
            task_status = {
                "task_id": test_case.generation_task_id,
                "state": "UNKNOWN",
                "progress": test_case.generation_progress,
                "message": f"获取任务状态失败: {str(e)}",
                "result": None,
                "error": None
            }
    
    return {
        **{
            "id": test_case.id,
            "project_id": test_case.project_id,
            "api_interface_id": test_case.api_interface_id,
            "name": test_case.name,
            "case_type": test_case.case_type,
            "module": test_case.module,
            "description": test_case.description,
            "test_data": test_case.test_data,
            "test_code": test_case.test_code,
            "assertions": test_case.assertions,
            "status": test_case.status,
            "generation_progress": test_case.generation_progress,
            "error_message": test_case.error_message,
            "created_at": test_case.created_at,
            "updated_at": test_case.updated_at
        },
        "task_status": task_status
    }


@router.put("/{test_case_id}")
async def update_test_case(
    test_case_id: int,
    project_id: int,
    test_case: TestCaseUpdate,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """更新测试用例"""
    db_case = db.query(TestCase).filter(
        TestCase.id == test_case_id,
        TestCase.project_id == project_id
    ).first()
    if not db_case:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    
    # 检查权限（如果用户已登录）
    if current_user and hasattr(current_user, 'id') and current_user.id:
        project = db.query(Project).filter(
            Project.id == project_id,
            Project.user_id == current_user.id
        ).first()
        if not project:
            raise HTTPException(status_code=403, detail="无权访问")
    
    import json
    
    # 只更新提供的字段
    if test_case.name is not None:
        db_case.name = test_case.name
    if test_case.case_type is not None:
        db_case.case_type = test_case.case_type
    if test_case.module is not None:
        db_case.module = test_case.module
    if test_case.description is not None:
        db_case.description = test_case.description
    if test_case.test_data is not None:
        # 处理test_data：如果是字符串，保持不变；如果是dict，转换为JSON字符串
        if isinstance(test_case.test_data, str):
            db_case.test_data = test_case.test_data
        else:
            db_case.test_data = json.dumps(test_case.test_data, ensure_ascii=False) if test_case.test_data else None
    if test_case.test_code is not None:
        db_case.test_code = test_case.test_code
    if test_case.assertions is not None:
        # 处理assertions：如果是字符串，保持不变；如果是list/dict，转换为JSON字符串
        if isinstance(test_case.assertions, str):
            db_case.assertions = test_case.assertions
        else:
            db_case.assertions = json.dumps(test_case.assertions, ensure_ascii=False) if test_case.assertions else None
    if test_case.dependencies is not None:
        db_case.dependencies = test_case.dependencies
    if test_case.api_interface_id is not None:
        db_case.api_interface_id = test_case.api_interface_id
    
    db.commit()
    db.refresh(db_case)
    return db_case


@router.delete("/{test_case_id}")
async def delete_test_case(
    test_case_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """删除测试用例"""
    test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
    if not test_case:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    
    # 检查权限（如果提供了用户信息，则验证权限；否则允许删除，因为可能是无登录模式）
    if current_user:
        project = db.query(Project).filter(
            Project.id == test_case.project_id,
            Project.user_id == current_user.id
        ).first()
        if not project:
            raise HTTPException(status_code=403, detail="无权访问")
    
    project_id = test_case.project_id
    
    # 删除测试用例
    db.delete(test_case)
    db.commit()
    
    # 清除该项目的所有测试用例缓存（包括不同过滤条件的缓存）
    try:
        from app.services.cache_service import cache_service
        cache_pattern = f"test_cases:{project_id}:*"
        deleted_count = cache_service.invalidate_cache(cache_pattern)
        print(f"[删除测试用例] 已清除测试用例缓存，删除 {deleted_count} 个缓存键")
    except Exception as cache_error:
        print(f"[删除测试用例] 清除缓存失败: {cache_error}")
    
    return {"message": "测试用例已删除"}
