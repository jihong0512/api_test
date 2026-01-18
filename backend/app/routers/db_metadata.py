from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import DBConnection, Project, User, TableMetadata, ColumnMetadata, TableRelationship
from app.routers.auth import get_current_user_optional

router = APIRouter()


class TableMetadataResponse(BaseModel):
    id: int
    table_name: str
    table_comment: Optional[str]
    primary_keys: Optional[str]
    column_count: int
    row_count: int
    
    class Config:
        from_attributes = True


class ColumnMetadataResponse(BaseModel):
    id: int
    column_name: str
    column_comment: Optional[str]
    data_type: str
    is_nullable: str
    is_primary_key: bool
    is_foreign_key: bool
    position: int
    
    class Config:
        from_attributes = True


class TableRelationshipResponse(BaseModel):
    id: int
    source_table_name: str
    target_table_name: str
    relationship_type: str
    relationship_name: Optional[str]
    description: Optional[str]
    foreign_key_columns: Optional[str]
    referred_columns: Optional[str]
    
    class Config:
        from_attributes = True


@router.get("/tables", response_model=List[TableMetadataResponse])
async def get_tables_metadata(
    connection_id: int = Query(...),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取数据库所有表的元数据信息"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    tables = db.query(TableMetadata).filter(
        TableMetadata.db_connection_id == connection_id
    ).order_by(TableMetadata.table_name).all()
    
    return tables


@router.get("/tables/{table_id}", response_model=TableMetadataResponse)
async def get_table_detail(
    table_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取表的详细信息"""
    table = db.query(TableMetadata).filter(TableMetadata.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    
    return table


@router.get("/tables/{table_id}/columns", response_model=List[ColumnMetadataResponse])
async def get_table_columns(
    table_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取表的所有字段信息"""
    table = db.query(TableMetadata).filter(TableMetadata.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    
    columns = db.query(ColumnMetadata).filter(
        ColumnMetadata.table_metadata_id == table_id
    ).order_by(ColumnMetadata.position).all()
    
    return columns


@router.get("/relationships", response_model=List[TableRelationshipResponse])
async def get_table_relationships(
    connection_id: int = Query(...),
    relationship_type: Optional[str] = Query(None, description="关系类型: has_a, is_a, depend_on, foreign_key"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取表之间的关系"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    query = db.query(TableRelationship).filter(
        TableRelationship.db_connection_id == connection_id
    )
    
    if relationship_type:
        query = query.filter(TableRelationship.relationship_type == relationship_type)
    
    relationships = query.all()
    
    # 补充表名信息
    result = []
    for rel in relationships:
        source_table = db.query(TableMetadata).filter(TableMetadata.id == rel.source_table_id).first()
        target_table = db.query(TableMetadata).filter(TableMetadata.id == rel.target_table_id).first()
        
        rel_dict = {
            "id": rel.id,
            "source_table_name": source_table.table_name if source_table else "",
            "target_table_name": target_table.table_name if target_table else "",
            "relationship_type": rel.relationship_type,
            "relationship_name": rel.relationship_name,
            "description": rel.description,
            "foreign_key_columns": rel.foreign_key_columns,
            "referred_columns": rel.referred_columns
        }
        result.append(rel_dict)
    
    return result


@router.get("/cypher-file")
async def get_cypher_file(
    connection_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取生成的Cypher文件内容"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    from app.services.metadata_service import DatabaseMetadataManager
    
    metadata_manager = DatabaseMetadataManager(db)
    cypher_content = metadata_manager.generate_cypher_file(connection)
    
    return {
        "connection_id": connection_id,
        "cypher_content": cypher_content
    }












