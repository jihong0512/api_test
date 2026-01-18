from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import DBConnection, User
from app.routers.auth import get_current_user_optional
from app.services.db_service import DatabaseService
from app.services.ner_service import KnowledgeGraphEnricher, NERService

router = APIRouter()


@router.post("/extract/{connection_id}")
async def extract_entities_from_tables(
    connection_id: int,
    table_names: Optional[List[str]] = Query(None, description="要处理的表名列表，为空则处理所有表"),
    limit: int = Query(100, description="每个表采样的数据量"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """从数据库表中抽取实体和关系"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    db_service = DatabaseService()
    try:
        engine = db_service.connect_database(
            connection.db_type,
            connection.host,
            connection.port,
            connection.database_name,
            connection.username,
            connection.password
        )
        
        # 获取要处理的表列表
        if not table_names:
            schema_info = db_service.analyze_database_schema(engine)
            table_names = [table["name"] for table in schema_info["tables"]]
        
        # 创建丰富服务
        from app.services.metadata_service import MetadataService
        metadata_service = MetadataService()
        enricher = KnowledgeGraphEnricher(db_service, metadata_service)
        
        results = {}
        all_cypher_statements = []
        
        for table_name in table_names:
            try:
                ner_result = enricher.enrich_from_table_data(
                    engine, table_name, limit=limit, project_id=connection.project_id
                )
                
                results[table_name] = {
                    "entities": ner_result.get("entities", []),
                    "relationships": ner_result.get("relationships", []),
                    "entities_count": len(ner_result.get("entities", [])),
                    "relationships_count": len(ner_result.get("relationships", [])),
                    "total_texts_processed": ner_result.get("total_texts_processed", 0)
                }
                
                # 生成Cypher语句
                if ner_result.get("entities") or ner_result.get("relationships"):
                    cypher = enricher.generate_cypher_for_entities(
                        table_name,
                        ner_result.get("entities", []),
                        ner_result.get("relationships", []),
                        connection.project_id
                    )
                    all_cypher_statements.append(cypher)
                
            except Exception as e:
                results[table_name] = {
                    "error": str(e)
                }
        
        return {
            "message": "实体和关系抽取完成",
            "tables_processed": len(results),
            "results": results,
            "cypher_statements": "\n\n".join(all_cypher_statements)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"实体抽取失败: {str(e)}")


@router.get("/entities/{connection_id}")
async def get_extracted_entities(
    connection_id: int,
    table_name: Optional[str] = Query(None, description="表名，为空则返回所有"),
    entity_type: Optional[str] = Query(None, description="实体类型过滤"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取从数据库中抽取的实体"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    db_service = DatabaseService()
    try:
        # 从Neo4j查询实体
        query = f"""
        MATCH (e:Entity {{project_id: {connection.project_id}}})
        """
        
        if table_name:
            query += f" WHERE e.source_table = '{table_name}'"
        
        if entity_type:
            if 'WHERE' in query:
                query += f" AND e.type = '{entity_type}'"
            else:
                query += f" WHERE e.type = '{entity_type}'"
        
        query += " RETURN e.name as name, e.type as type, e.source_table as source_table, id(e) as id"
        
        entities = db_service.query_knowledge_graph(query, connection.project_id)
        
        return {
            "connection_id": connection_id,
            "entities": entities,
            "total": len(entities)
        }
    except Exception as e:
        # Neo4j连接失败时返回空数据，而不是抛出异常
        print(f"获取NER实体失败（Neo4j可能不可用）: {e}")
        return {
            "connection_id": connection_id,
            "entities": [],
            "total": 0,
            "message": "Neo4j不可用或未抽取实体"
        }


@router.get("/relationships/{connection_id}")
async def get_extracted_relationships(
    connection_id: int,
    source_entity: Optional[str] = Query(None, description="源实体名"),
    target_entity: Optional[str] = Query(None, description="目标实体名"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """获取从数据库中抽取的实体关系"""
    connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    db_service = DatabaseService()
    try:
        # 构建查询
        query = f"""
        MATCH (e1:Entity {{project_id: {connection.project_id}}})-[r]->(e2:Entity {{project_id: {connection.project_id}}})
        WHERE r.source = 'NER'
        """
        
        if source_entity:
            query += f" AND e1.name = '{source_entity}'"
        
        if target_entity:
            query += f" AND e2.name = '{target_entity}'"
        
        query += " RETURN e1.name as source, type(r) as type, e2.name as target, r.context as context, r.confidence as confidence"
        
        relationships = db_service.query_knowledge_graph(query, connection.project_id)
        
        return {
            "connection_id": connection_id,
            "relationships": relationships,
            "total": len(relationships)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取关系失败: {str(e)}")









