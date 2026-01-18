from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db
from app.routers import (
    auth, projects, documents, api_interfaces, document_interfaces,
    test_cases, test_tasks, test_results, test_reports, test_case_debug, custom_report,
    test_environments, test_case_suites, request_builder_api,
    advanced_data_generator,
    db_connections, knowledge_graph, intelligent_enhancement, db_metadata, ner_entities,
    test_data_generator, test_flows, api_dependencies, scenario_generator,
    document_change, cicd_integration, test_orchestrator_api, interface_grouping
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化
    await init_db()
    yield
    # 关闭时清理
    pass


app = FastAPI(
    title="智能API管理系统",
    description="基于大模型的智能API管理与分析平台",
    version="1.0.0",
    lifespan=lifespan
)

# CORS配置 - 允许所有来源（开发环境）
# 明确允许的源列表（包括localhost的不同端口）
# 注意：如果使用allow_credentials=True，不能使用"*"，必须明确指定来源
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:3006",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3006",
    "http://127.0.0.1:3001",
]

# 开发环境：允许所有来源（不使用credentials）
# 生产环境：应该明确指定允许的来源
import os
if os.getenv("ENVIRONMENT", "development") == "development":
    # 开发环境：允许所有来源
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 允许所有来源
        allow_credentials=False,  # 不允许携带凭证（使用"*"时）
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=3600,
    )
else:
    # 生产环境：明确指定允许的来源
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,  # 允许携带凭证
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=3600,
    )

# 异常处理器 - 确保所有响应都包含CORS头部
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器，确保所有响应都包含CORS头部"""
    from fastapi import HTTPException
    import traceback
    
    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        detail = exc.detail
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = str(exc)
        # 打印完整的错误堆栈
        print(f"未处理的异常: {exc}")
        traceback.print_exc()
    
    response = JSONResponse(
        status_code=status_code,
        content={"detail": detail, "error": str(exc)}
    )
    
    # 添加CORS头部
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"
    
    return response

# 注册路由
app.include_router(auth.router, prefix="/api/session", tags=["会话管理"])
app.include_router(projects.router, prefix="/api/workspaces", tags=["工作空间"])
app.include_router(documents.router, prefix="/api/files", tags=["文件管理"])
app.include_router(api_interfaces.router, prefix="/api/services", tags=["服务管理"])
app.include_router(document_interfaces.router, prefix="/api/endpoints", tags=["端点管理"])
app.include_router(api_dependencies.router, prefix="/api/relations", tags=["关系分析"])
app.include_router(scenario_generator.router, prefix="/api/sequences", tags=["序列生成"])
app.include_router(test_cases.router, prefix="/api/specs", tags=["规范管理"])
app.include_router(test_data_generator.router, prefix="/api/data", tags=["数据生成"])
app.include_router(test_flows.router, prefix="/api/flows", tags=["流程管理"])
app.include_router(test_tasks.router, prefix="/api/jobs", tags=["任务管理"])
app.include_router(test_results.router, prefix="/api/results", tags=["结果管理"])
app.include_router(test_reports.router, prefix="/api/reports", tags=["报告管理"])
app.include_router(test_case_debug.router, prefix="/api/specs", tags=["规范调试"])
app.include_router(custom_report.router, prefix="/api/custom", tags=["自定义"])
# app.include_router(dependency_monitor.router, prefix="/api/dependency-monitor", tags=["依赖服务监控"])  # 已禁用依赖监控功能
app.include_router(request_builder_api.router, prefix="/api/builder", tags=["构造器"])
app.include_router(advanced_data_generator.router, prefix="/api/advanced", tags=["高级功能"])
app.include_router(test_environments.router, prefix="/api/configs", tags=["配置管理"])
app.include_router(test_case_suites.router, prefix="/api/suites", tags=["套件管理"])
app.include_router(interface_grouping.router, tags=["分组管理"])
app.include_router(db_connections.router, prefix="/api/connections", tags=["连接管理"])
app.include_router(db_metadata.router, prefix="/api/metadata", tags=["元数据管理"])
app.include_router(ner_entities.router, prefix="/api/entities", tags=["实体抽取"])
app.include_router(knowledge_graph.router, prefix="/api/graphs", tags=["图谱管理"])
app.include_router(intelligent_enhancement.router, prefix="/api/insights", tags=["智能洞察"])
app.include_router(document_change.router, prefix="/api/changes", tags=["变更检测"])
app.include_router(cicd_integration.router, prefix="/api/integration", tags=["集成管理"])
app.include_router(test_orchestrator_api.router, prefix="/api/orchestrator", tags=["编排管理"])


@app.get("/")
async def root():
    return {"message": "智能API管理系统", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """返回favicon以避免404/500错误"""
    try:
        from fastapi.responses import Response
        # 返回一个简单的SVG图标
        svg_icon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <text y=".9em" font-size="90">🔧</text>
    </svg>"""
        return Response(content=svg_icon, media_type="image/svg+xml")
    except Exception as e:
        # 如果出错，返回空响应
        return Response(status_code=204)

# 也处理 /api/favicon.ico 的请求（前端代理可能会添加 /api 前缀）
@app.get("/api/favicon.ico", include_in_schema=False)
async def favicon_api():
    """返回favicon（处理代理请求）"""
    try:
        from fastapi.responses import Response
        svg_icon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <text y=".9em" font-size="90">🔧</text>
    </svg>"""
        return Response(content=svg_icon, media_type="image/svg+xml")
    except Exception as e:
        # 如果出错，返回空响应
        return Response(status_code=204)


