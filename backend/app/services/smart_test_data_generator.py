from typing import List, Dict, Any, Optional
from faker import Faker
import json
import random
from datetime import datetime, timedelta
import re

from app.services.db_service import DatabaseService
from app.services.metadata_service import MetadataService
from sqlalchemy import inspect, text


class SmartTestDataGenerator:
    """智能测试数据生成器：结合知识图谱和实际数据模式"""
    
    def __init__(self):
        self.db_service = DatabaseService()
        self.metadata_service = MetadataService()
        self.faker = Faker('zh_CN')
        self.faker_en = Faker('en_US')
        
        # 字段名到Faker方法的映射
        self.field_patterns = {
            # 用户相关
            'user': {'name': self.faker.name, 'phone': self.faker.phone_number},
            'username': self.faker.user_name,
            'password': lambda: self.faker.password(length=12),
            'email': self.faker.email,
            'phone': self.faker.phone_number,
            'mobile': self.faker.phone_number,
            'address': self.faker.address,
            
            # 运动相关
            '运动': {'duration': lambda: random.randint(300, 3600), 'distance': lambda: round(random.uniform(1.0, 10.0), 2)},
            'course': {'name': lambda: random.choice(['跑步机课程', '走步机课程', '划船机课程'])},
            
            # 设备相关
            'device': {'name': lambda: random.choice(['跑步机', '走步机', '划船机', '智能哑铃'])},
            'version': lambda: f"v{random.randint(1, 5)}.{random.randint(0, 9)}.{random.randint(0, 9)}",
            
            # 通用
            'name': self.faker.name,
            'title': self.faker.sentence,
            'description': self.faker.text,
            'content': self.faker.text,
            'remark': self.faker.text,
            'note': self.faker.text,
            'url': self.faker.url,
            'ip': self.faker.ipv4,
        }
    
    def generate_test_data_for_api(
        self,
        api_info: Dict[str, Any],
        connection_id: Optional[int] = None,
        project_id: int = None,
        use_real_data: bool = True,
        db_session: Any = None,
        engine: Any = None
    ) -> Dict[str, Any]:
        """为API生成智能测试数据"""
        # 如果没有连接ID，跳过数据库相关操作
        if not connection_id:
            use_real_data = False
        
        # 1. 获取数据库知识图谱信息
        knowledge_graph_info = self._get_knowledge_graph_info(connection_id, project_id) if connection_id else {}
        
        # 2. 获取表元数据信息
        table_metadata = self._get_table_metadata(connection_id, api_info, db_session) if connection_id else {}
        
        # 3. 分析API字段
        api_fields = self._analyze_api_fields(api_info)
        
        # 4. 生成测试数据
        test_data = {
            "params": {},
            "headers": {},
            "body": {},
            "path_params": {}  # 路径参数从URL中提取（如/api/users/{userId}）
        }
        
        # 从URL中提取路径参数（如/api/users/{userId}中的{userId}）
        url = api_info.get("url", "")
        if url:
            import re
            path_params = re.findall(r'\{(\w+)\}', url)
            for param_name in path_params:
                # 尝试从知识图谱或元数据获取类型信息
                param_info = {"type": "integer" if "id" in param_name.lower() else "string"}
                test_data["path_params"][param_name] = self._generate_field_value(
                    param_name, param_info, knowledge_graph_info, table_metadata, use_real_data, engine, connection_id
                )
        
        # 生成查询参数
        params = api_info.get("params", {})
        if isinstance(params, dict) and params:
            for param, param_info in params.items():
                if isinstance(param_info, dict):
                    test_data["params"][param] = self._generate_field_value(
                        param, param_info, knowledge_graph_info, table_metadata, use_real_data, engine, connection_id
                    )
                else:
                    # 如果param_info是简单类型，使用默认生成
                    test_data["params"][param] = self._generate_field_value(
                        param, {"type": str(param_info)}, knowledge_graph_info, table_metadata, use_real_data, engine, connection_id
                    )
        
        # 生成请求体
        body = api_info.get("body", {})
        if isinstance(body, dict) and body:
            for field, field_info in body.items():
                if isinstance(field_info, dict):
                    test_data["body"][field] = self._generate_field_value(
                        field, field_info, knowledge_graph_info, table_metadata, use_real_data, engine, connection_id
                    )
                else:
                    # 如果field_info是简单类型
                    test_data["body"][field] = self._generate_field_value(
                        field, {"type": str(field_info)}, knowledge_graph_info, table_metadata, use_real_data, engine, connection_id
                    )
        elif isinstance(body, str):
            try:
                body_dict = json.loads(body)
                if isinstance(body_dict, dict):
                    for field, field_info in body_dict.items():
                        test_data["body"][field] = self._generate_field_value(
                            field, field_info if isinstance(field_info, dict) else {"type": str(field_info)},
                            knowledge_graph_info, table_metadata, use_real_data, engine, connection_id
                        )
            except:
                # 如果不是JSON，直接使用字符串
                test_data["body"] = body
        
        # 5. 基于知识图谱验证和增强数据关系
        test_data = self._enhance_with_relationships(
            test_data, api_info, knowledge_graph_info, table_metadata
        )
        
        return test_data
    
    def _get_knowledge_graph_info(
        self,
        connection_id: int,
        project_id: int
    ) -> Dict[str, Any]:
        """从Neo4j获取知识图谱信息"""
        try:
            # 获取表关系
            query = f"""
            MATCH (t1:Table {{project_id: {project_id}}})-[r]->(t2:Table {{project_id: {project_id}}})
            RETURN t1.name as source_table, type(r) as relationship_type, 
                   t2.name as target_table, r.description as description,
                   r.foreign_key_columns as fk_columns, r.referred_columns as ref_columns
            """
            relationships = self.db_service.query_knowledge_graph(query, project_id)
            
            # 获取实体信息
            entity_query = f"""
            MATCH (e:Entity {{project_id: {project_id}}})
            RETURN e.name as name, e.type as type, e.source_table as source_table
            LIMIT 100
            """
            entities = self.db_service.query_knowledge_graph(entity_query, project_id)
            
            return {
                "relationships": relationships,
                "entities": entities
            }
        except Exception as e:
            print(f"获取知识图谱信息失败: {e}")
            return {"relationships": [], "entities": []}
    
    def _get_table_metadata(
        self,
        connection_id: int,
        api_info: Dict[str, Any],
        db_session: Any = None
    ) -> Dict[str, Any]:
        """获取相关表的元数据"""
        from app.models import TableMetadata, ColumnMetadata, DBConnection
        
        if not db_session:
            return {}
        
        connection = db_session.query(DBConnection).filter(
            DBConnection.id == connection_id
        ).first()
        
        if not connection:
            return {}
        
        # 从API信息推断可能的表名
        possible_tables = self._infer_tables_from_api(api_info)
        
        metadata = {}
        for table_name in possible_tables:
            table_meta = db_session.query(TableMetadata).filter(
                TableMetadata.db_connection_id == connection_id,
                TableMetadata.table_name == table_name
            ).first()
            
            if table_meta:
                columns = db_session.query(ColumnMetadata).filter(
                    ColumnMetadata.table_metadata_id == table_meta.id
                ).all()
                
                metadata[table_name] = {
                    "table_name": table_name,
                    "columns": [
                        {
                            "name": col.column_name,
                            "type": col.data_type,
                            "is_primary_key": col.is_primary_key,
                            "is_foreign_key": col.is_foreign_key,
                            "comment": col.column_comment
                        }
                        for col in columns
                    ],
                    "primary_keys": json.loads(table_meta.primary_keys) if table_meta.primary_keys else [],
                    "foreign_keys": json.loads(table_meta.foreign_keys) if table_meta.foreign_keys else []
                }
        
        return metadata
    
    def _infer_tables_from_api(self, api_info: Dict[str, Any]) -> List[str]:
        """从API信息推断相关表名"""
        tables = []
        url = api_info.get("url", "").lower()
        name = api_info.get("name", "").lower()
        
        # 基于URL路径推断
        if "/user" in url or "/users" in url:
            tables.append("users")
        if "/device" in url or "/equipment" in url:
            tables.append("devices")
        if "/course" in url or "/courses" in url:
            tables.append("courses")
        if "/record" in url or "/records" in url:
            tables.append("records")
        if "/plan" in url or "/plans" in url:
            tables.append("plans")
        
        return tables
    
    def _analyze_api_fields(self, api_info: Dict[str, Any]) -> Dict[str, Any]:
        """分析API字段信息"""
        fields = {}
        
        # 从URL中提取路径参数
        url = api_info.get("url", "")
        if url:
            import re
            path_params = re.findall(r'\{(\w+)\}', url)
            for param_name in path_params:
                fields[param_name] = {"type": "integer" if "id" in param_name.lower() else "string"}
        
        # 分析查询参数
        if api_info.get("params"):
            fields.update(api_info["params"])
        
        # 分析请求体
        if api_info.get("body"):
            if isinstance(api_info["body"], dict):
                fields.update(api_info["body"])
        
        return fields
    
    def _generate_field_value(
        self,
        field_name: str,
        field_info: Any,
        knowledge_graph: Dict[str, Any],
        table_metadata: Dict[str, Any],
        use_real_data: bool,
        engine: Any = None,
        connection_id: int = None
    ) -> Any:
        """生成字段值（智能判断类型和生成规则）"""
        field_lower = field_name.lower()
        
        # 1. 检查是否是外键字段（需要从关联表获取值）
        fk_value = self._get_foreign_key_value(field_name, knowledge_graph, use_real_data, engine, connection_id)
        if fk_value:
            return fk_value
        
        # 2. 根据字段名模式判断
        if isinstance(field_info, dict):
            field_type = field_info.get("type", "").lower()
            field_description = field_info.get("description", "").lower()
        else:
            field_type = str(field_info).lower()
            field_description = ""
        
        # 3. 基于字段名模式生成
        if "id" in field_lower:
            if use_real_data and engine:
                # 尝试获取真实ID
                real_id = self._get_real_id(field_name, knowledge_graph, engine, table_metadata)
                if real_id:
                    return real_id
            # 基于实际数据模式生成ID
            pattern = self._analyze_id_pattern(field_name, table_metadata, engine)
            if pattern:
                return pattern
            return random.randint(1, 10000)
        
        if "email" in field_lower:
            return self.faker.email()
        
        if "phone" in field_lower or "mobile" in field_lower or "tel" in field_lower:
            return self.faker.phone_number()
        
        if "password" in field_lower:
            return self.faker.password(length=12)
        
        if "name" in field_lower or "username" in field_lower:
            return self.faker.user_name() if "username" in field_lower else self.faker.name()
        
        if "time" in field_lower or "date" in field_lower:
            if field_type in ["datetime", "timestamp"]:
                return self.faker.iso8601()
            else:
                return self.faker.date().isoformat()
        
        if "price" in field_lower or "amount" in field_lower or "cost" in field_lower:
            return round(random.uniform(0.01, 10000.0), 2)
        
        if "count" in field_lower or "quantity" in field_lower or "num" in field_lower:
            return random.randint(1, 100)
        
        if "status" in field_lower or "state" in field_lower:
            return random.choice([0, 1]) if field_type == "integer" else random.choice(["active", "inactive"])
        
        if "type" in field_lower:
            # 基于业务场景返回类型
            if "device" in field_lower or "equipment" in field_lower:
                return random.choice(["treadmill", "walking", "rowing", "dumbbell"])
            if "course" in field_lower:
                return random.choice(["running", "walking", "training", "rowing"])
            return random.choice(["type1", "type2", "type3"])
        
        # 4. 基于数据类型生成
        if field_type == "string" or field_type == "text":
            if "description" in field_lower or "content" in field_lower or "remark" in field_lower:
                return self.faker.text(max_nb_chars=200)
            elif "url" in field_lower:
                return self.faker.url()
            else:
                return self.faker.word()
        
        if field_type == "integer" or field_type == "int":
            return random.randint(1, 1000)
        
        if field_type == "number" or field_type == "float" or field_type == "decimal":
            return round(random.uniform(0.0, 1000.0), 2)
        
        if field_type == "boolean" or field_type == "bool":
            return random.choice([True, False])
        
        if field_type == "date":
            return self.faker.date().isoformat()
        
        if field_type == "datetime" or field_type == "timestamp":
            return self.faker.iso8601()
        
        # 5. 基于业务实体生成（从知识图谱中获取）
        entity_value = self._get_entity_value(field_name, knowledge_graph)
        if entity_value:
            return entity_value
        
        # 默认值
        return self.faker.word()
    
    def _get_foreign_key_value(
        self,
        field_name: str,
        knowledge_graph: Dict[str, Any],
        use_real_data: bool,
        engine: Any = None,
        connection_id: int = None
    ) -> Optional[Any]:
        """获取外键字段的值"""
        relationships = knowledge_graph.get("relationships", [])
        
        # 查找相关的表关系
        for rel in relationships:
            fk_columns = rel.get("fk_columns", [])
            if isinstance(fk_columns, str):
                try:
                    fk_columns = json.loads(fk_columns)
                except:
                    fk_columns = []
            
            # 检查字段名是否在外键列表中
            if field_name.lower() in [col.lower() for col in fk_columns]:
                target_table = rel.get("target_table", "")
                # 如果是外键，需要返回目标表的主键值
                if use_real_data and engine:
                    # 尝试从数据库获取真实值
                    real_id = self._get_real_id_from_table(target_table, engine)
                    if real_id:
                        return real_id
                
                # 生成合理的ID值
                return random.randint(1, 1000)
        
        return None
    
    def _get_real_id(
        self,
        field_name: str,
        knowledge_graph: Dict[str, Any],
        engine: Any = None,
        table_metadata: Dict[str, Any] = None
    ) -> Optional[Any]:
        """获取真实的ID值（从数据库）"""
        if not engine:
            return None
        
        # 从字段名推断表名
        field_lower = field_name.lower()
        possible_tables = []
        
        if "user" in field_lower:
            possible_tables = ["users", "user", "members"]
        elif "device" in field_lower or "equipment" in field_lower:
            possible_tables = ["devices", "equipment", "device"]
        elif "course" in field_lower:
            possible_tables = ["courses", "course"]
        elif "record" in field_lower:
            possible_tables = ["records", "record"]
        elif "plan" in field_lower:
            possible_tables = ["plans", "plan"]
        
        # 尝试从表中获取真实ID
        for table_name in possible_tables:
            real_id = self._get_real_id_from_table(table_name, engine)
            if real_id:
                return real_id
        
        return None
    
    def _get_real_id_from_table(self, table_name: str, engine: Any) -> Optional[Any]:
        """从指定表获取真实ID"""
        if not engine:
            return None
        
        try:
            from sqlalchemy import text, inspect
            
            with engine.connect() as conn:
                # 尝试获取主键字段
                inspector = inspect(engine)
                pk_constraint = inspector.get_pk_constraint(table_name)
                
                if pk_constraint and pk_constraint.get("constrained_columns"):
                    pk_column = pk_constraint["constrained_columns"][0]
                    result = conn.execute(
                        text(f"SELECT `{pk_column}` FROM `{table_name}` LIMIT 1")
                    )
                    row = result.fetchone()
                    if row:
                        return row[0]
        except Exception as e:
            print(f"获取表 {table_name} 真实ID失败: {e}")
        
        return None
    
    def _analyze_id_pattern(
        self,
        field_name: str,
        table_metadata: Dict[str, Any],
        engine: Any = None
    ) -> Optional[Any]:
        """分析ID字段的模式并生成符合模式的值"""
        if not engine:
            return None
        
        # 从表元数据中查找字段信息
        for table_name, meta in table_metadata.items():
            columns = meta.get("columns", [])
            for col in columns:
                if col["name"].lower() == field_name.lower():
                    # 如果字段是自增主键，返回合理的ID范围
                    if col.get("is_primary_key") and col.get("auto_increment"):
                        # 基于现有数据范围生成
                        if engine:
                            try:
                                from sqlalchemy import text
                                with engine.connect() as conn:
                                    result = conn.execute(
                                        text(f"SELECT MAX(`{field_name}`), MIN(`{field_name}`) FROM `{table_name}`")
                                    )
                                    row = result.fetchone()
                                    if row and row[0]:
                                        max_id = row[0]
                                        return random.randint(1, max_id + 100)
                            except:
                                pass
        
        return None
    
    def _get_entity_value(
        self,
        field_name: str,
        knowledge_graph: Dict[str, Any]
    ) -> Optional[str]:
        """从知识图谱实体中获取值"""
        entities = knowledge_graph.get("entities", [])
        
        # 根据字段名匹配实体类型
        field_lower = field_name.lower()
        for entity in entities:
            entity_name = entity.get("name", "").lower()
            entity_type = entity.get("type", "")
            
            # 如果字段名包含实体名或实体类型匹配
            if field_lower in entity_name or entity_name in field_lower:
                return entity.get("name")
        
        return None
    
    def _enhance_with_relationships(
        self,
        test_data: Dict[str, Any],
        api_info: Dict[str, Any],
        knowledge_graph: Dict[str, Any],
        table_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """基于知识图谱关系增强测试数据"""
        relationships = knowledge_graph.get("relationships", [])
        
        # 检查并修复数据关系
        for rel in relationships:
            source_table = rel.get("source_table", "")
            target_table = rel.get("target_table", "")
            rel_type = rel.get("relationship_type", "")
            
            # 如果测试数据中包含了两个表的相关字段，确保关系正确
            source_fields = self._get_table_fields(source_table, test_data)
            target_fields = self._get_table_fields(target_table, test_data)
            
            if source_fields and target_fields:
                # 确保外键关系正确
                fk_columns = rel.get("fk_columns", [])
                ref_columns = rel.get("ref_columns", [])
                
                if fk_columns and ref_columns:
                    # 如果测试数据中同时包含外键字段和引用字段，确保它们匹配
                    for fk_col, ref_col in zip(fk_columns, ref_columns):
                        if fk_col in test_data.get("body", {}):
                            # 外键值应该引用目标表的主键
                            # 这里简化处理，如果需要可以查询真实数据
                            pass
        
        return test_data
    
    def _get_table_fields(self, table_name: str, test_data: Dict[str, Any]) -> List[str]:
        """从测试数据中获取指定表的字段"""
        # 基于字段名模式推断是否属于某个表
        fields = []
        all_fields = []
        
        for section in [test_data.get("params", {}), test_data.get("body", {})]:
            all_fields.extend(section.keys())
        
        # 简化的表字段匹配
        table_lower = table_name.lower()
        for field in all_fields:
            field_lower = field.lower()
            if table_lower in field_lower or field_lower in table_lower:
                fields.append(field)
        
        return fields
    
    def generate_batch_test_data(
        self,
        api_info: Dict[str, Any],
        connection_id: int,
        project_id: int,
        count: int = 10,
        use_real_data: bool = True,
        db_session: Any = None,
        engine: Any = None
    ) -> List[Dict[str, Any]]:
        """批量生成测试数据"""
        test_data_list = []
        
        for i in range(count):
            test_data = self.generate_test_data_for_api(
                api_info, connection_id, project_id, use_real_data, db_session, engine
            )
            test_data["_batch_index"] = i + 1
            test_data_list.append(test_data)
        
        return test_data_list
    
    def analyze_data_patterns(
        self,
        table_name: str,
        column_name: str,
        connection_id: int
    ) -> Dict[str, Any]:
        """分析实际数据模式"""
        # 从数据库服务获取数据特征分析
        try:
            from app.models import DBConnection
            from app.database import get_db
            from sqlalchemy.orm import Session
            
            # 这里需要数据库会话，简化处理
            # 实际应该调用db_service.analyze_data_features
            return {
                "data_type": "string",
                "pattern": "random",
                "sample_values": []
            }
        except:
            return {
                "data_type": "string",
                "pattern": "random",
                "sample_values": []
            }

