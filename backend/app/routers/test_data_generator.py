from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json

from app.database import get_db
from app.models import APIInterface, Project, User, DBConnection
from app.routers.auth import get_current_user_optional
from app.services.smart_test_data_generator import SmartTestDataGenerator
from app.services.db_service import DatabaseService

router = APIRouter()
data_generator = SmartTestDataGenerator()
db_service = DatabaseService()


class GenerateTestDataRequest(BaseModel):
    api_interface_id: int
    connection_id: Optional[int] = None
    use_real_data: bool = True
    count: int = 1


class TestDataResponse(BaseModel):
    test_data: Dict[str, Any]
    api_info: Dict[str, Any]
    metadata: Dict[str, Any]


@router.post("/generate", response_model=TestDataResponse)
async def generate_test_data(
    project_id: int,
    request: GenerateTestDataRequest,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """生成智能测试数据"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取API接口信息
    api_interface = db.query(APIInterface).filter(
        APIInterface.id == request.api_interface_id,
        APIInterface.project_id == project_id
    ).first()
    if not api_interface:
        raise HTTPException(status_code=404, detail="API interface not found")
    
    # 获取数据库连接ID（如果没有提供，尝试从项目获取）
    connection_id = request.connection_id
    if not connection_id:
        connection = db.query(DBConnection).filter(
            DBConnection.project_id == project_id
        ).first()
        if connection:
            connection_id = connection.id
    
    if not connection_id:
        raise HTTPException(status_code=400, detail="No database connection found")
    
    # 连接数据库
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Database connection not found")
    
    try:
        engine = db_service.connect_database(
            connection.db_type,
            connection.host,
            connection.port,
            connection.database_name,
            connection.username,
            connection.password
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")
    
    # 构建API信息（统一使用模型字段）
    api_info = {
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
    
    # 生成测试数据
    if request.count == 1:
        test_data = data_generator.generate_test_data_for_api(
            api_info=api_info,
            connection_id=connection_id,
            project_id=project_id,
            use_real_data=request.use_real_data,
            db_session=db,
            engine=engine
        )
        test_data_list = [test_data]
    else:
        test_data_list = data_generator.generate_batch_test_data(
            api_info=api_info,
            connection_id=connection_id,
            project_id=project_id,
            count=request.count,
            use_real_data=request.use_real_data,
            db_session=db,
            engine=engine
        )
    
    # 获取元数据信息
    metadata = {
        "connection_id": connection_id,
        "use_real_data": request.use_real_data,
        "data_count": len(test_data_list),
        "knowledge_graph_used": True
    }
    
    return {
        "test_data": test_data_list[0] if len(test_data_list) == 1 else test_data_list,
        "api_info": api_info,
        "metadata": metadata
    }


@router.get("/analyze/{connection_id}")
async def analyze_data_patterns(
    connection_id: int,
    table_name: str = Query(..., description="表名"),
    column_name: Optional[str] = Query(None, description="字段名"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """分析数据模式"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Database connection not found")
    
    try:
        engine = db_service.connect_database(
            connection.db_type,
            connection.host,
            connection.port,
            connection.database_name,
            connection.username,
            connection.password
        )
        
        # 分析数据特征
        if column_name:
            # 分析特定字段
            features = db_service.analyze_data_features(engine, table_name)
            column_features = features.get("columns", {}).get(column_name, {})
            return {
                "table_name": table_name,
                "column_name": column_name,
                "features": column_features
            }
        else:
            # 分析整个表
            features = db_service.analyze_data_features(engine, table_name)
            return {
                "table_name": table_name,
                "features": features
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data analysis failed: {str(e)}")


@router.get("/preview/{connection_id}")
async def preview_real_data(
    connection_id: int,
    table_name: str = Query(..., description="表名"),
    limit: int = Query(10, description="预览数量"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """预览真实数据"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Database connection not found")
    
    try:
        engine = db_service.connect_database(
            connection.db_type,
            connection.host,
            connection.port,
            connection.database_name,
            connection.username,
            connection.password
        )
        
        # 采样数据
        sample_data = db_service.sample_data(engine, table_name, limit)
        
        return {
            "table_name": table_name,
            "sample_size": len(sample_data),
            "data": sample_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data preview failed: {str(e)}")

