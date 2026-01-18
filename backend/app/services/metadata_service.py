from typing import List, Dict, Any, Optional
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
import json
import re
from pathlib import Path

from app.services.db_service import DatabaseService
from app.services.llm_sync_helper import LLMServiceSync
from app.models import TableMetadata, ColumnMetadata, TableRelationship, DBConnection


class MetadataService:
    """元数据服务：提取、保存、分析表元数据"""
    
    def __init__(self):
        self.db_service = DatabaseService()
        self.llm_service = LLMServiceSync()
    
    def extract_table_comment(self, engine, table_name: str) -> str:
        """提取表的注释（含义）"""
        try:
            # MySQL获取表注释
            with engine.connect() as conn:
                # 获取当前数据库名
                db_result = conn.execute(text("SELECT DATABASE()"))
                db_name = db_result.fetchone()[0]
                
                if db_name:
                    result = conn.execute(text("""
                        SELECT TABLE_COMMENT 
                        FROM information_schema.TABLES 
                        WHERE TABLE_SCHEMA = :db_name 
                        AND TABLE_NAME = :table_name
                    """), {
                        "db_name": db_name,
                        "table_name": table_name
                    })
                    row = result.fetchone()
                    if row and row[0] and row[0].strip():
                        return row[0].strip()
        except Exception as e:
            print(f"提取表注释失败 {table_name}: {e}")
        
        # 如果没有注释，使用LLM推断表含义
        try:
            return self._infer_table_meaning(table_name)
        except:
            return ""
    
    def extract_column_comment(self, engine, table_name: str, column_name: str) -> str:
        """提取字段的注释（含义）"""
        try:
            # MySQL获取字段注释
            with engine.connect() as conn:
                # 获取当前数据库名
                db_result = conn.execute(text("SELECT DATABASE()"))
                db_name = db_result.fetchone()[0]
                
                if db_name:
                    result = conn.execute(text("""
                        SELECT COLUMN_COMMENT 
                        FROM information_schema.COLUMNS 
                        WHERE TABLE_SCHEMA = :db_name 
                        AND TABLE_NAME = :table_name 
                        AND COLUMN_NAME = :column_name
                    """), {
                        "db_name": db_name,
                        "table_name": table_name,
                        "column_name": column_name
                    })
                    row = result.fetchone()
                    if row and row[0] and row[0].strip():
                        return row[0].strip()
        except Exception as e:
            print(f"提取字段注释失败 {table_name}.{column_name}: {e}")
        
        # 如果没有注释，使用命名推断
        return self._infer_column_meaning(column_name)
    
    def _infer_table_meaning(self, table_name: str) -> str:
        """推断表的含义"""
        # 基于命名规则推断
        table_name_lower = table_name.lower()
        
        # 常见表名模式
        patterns = {
            r'user': '用户',
            r'order': '订单',
            r'product': '产品',
            r'goods': '商品',
            r'payment': '支付',
            r'account': '账户',
            r'customer': '客户',
            r'supplier': '供应商',
            r'inventory': '库存',
            r'log': '日志',
            r'config': '配置',
            r'setting': '设置'
        }
        
        for pattern, meaning in patterns.items():
            if re.search(pattern, table_name_lower):
                return meaning + "表"
        
        # 如果没有匹配，尝试使用LLM
        try:
            prompt = f"请根据表名 '{table_name}' 推断这个表的业务含义，用简短的中文描述（不超过10个字），只输出含义，不要其他文字："
            result = self.llm_service.chat(prompt, temperature=0.3, max_tokens=50)
            return result.strip().replace('表', '').strip() + '表'
        except Exception as e:
            print(f"LLM推断表含义失败: {e}")
            return ""
    
    def _infer_column_meaning(self, column_name: str) -> str:
        """推断字段的含义"""
        column_name_lower = column_name.lower()
        
        # 常见字段名模式
        patterns = {
            r'id$': '标识',
            r'name': '名称',
            r'create_time|created_at': '创建时间',
            r'update_time|updated_at': '更新时间',
            r'status': '状态',
            r'type': '类型',
            r'desc|description': '描述',
            r'price': '价格',
            r'amount': '金额',
            r'count|quantity': '数量',
            r'email': '邮箱',
            r'phone': '电话',
            r'address': '地址'
        }
        
        for pattern, meaning in patterns.items():
            if re.search(pattern, column_name_lower):
                return meaning
        
        return column_name
    
    def analyze_relationship_type(
        self,
        source_table: str,
        target_table: str,
        foreign_key_info: Dict[str, Any],
        schema_info: Dict[str, Any],
        business_context: Optional[str] = None
    ) -> str:
        """分析表与表之间的关系类型（扩展版）
        
        Args:
            source_table: 源表名
            target_table: 目标表名
            foreign_key_info: 外键信息
            schema_info: 数据库schema信息
            business_context: 业务上下文描述（从项目描述或数据库信息中获取）
        """
        # 获取表信息
        source_table_info = next((t for t in schema_info["tables"] if t["name"] == source_table), None)
        target_table_info = next((t for t in schema_info["tables"] if t["name"] == target_table), None)
        
        if not source_table_info or not target_table_info:
            return "depend_on"
        
        source_lower = source_table.lower()
        target_lower = target_table.lower()
        fk_columns = foreign_key_info.get("constrained_columns", [])
        
        # 使用LLM智能分析关系类型（基于业务语义）
        relationship_type = self._analyze_relationship_with_llm(
            source_table, target_table, fk_columns, source_table_info, target_table_info, business_context
        )
        
        if relationship_type:
            return relationship_type
        
        # 基于规则的快速判断（备用方案）
        # 1. 继承关系（is_a）
        if self._is_inheritance_relationship(source_table, target_table):
            return "is_a"
        
        # 2. 包含/拥有关系（has_a, contains, belongs_to）
        contains_rel = self._check_contains_relationship(source_table, target_table, source_table_info, target_table_info)
        if contains_rel:
            return contains_rel
        
        # 3. 绑定关系（binds_to）
        if self._check_bind_relationship(source_table, target_table, fk_columns):
            return "binds_to"
        
        # 4. 关联关系（associates_with）
        if self._check_associate_relationship(source_table, target_table):
            return "associates_with"
        
        # 5. 连接/控制关系（connects_to, controls）
        if self._check_connect_control_relationship(source_table, target_table):
            return "connects_to"
        
        # 6. 创建/使用关系（creates, uses）
        creates_rel = self._check_create_use_relationship(source_table, target_table, fk_columns)
        if creates_rel:
            return creates_rel
        
        # 7. 共享关系（shares_with）
        if self._check_share_relationship(source_table, target_table):
            return "shares_with"
        
        # 8. 默认依赖关系
        return "depend_on"
    
    def _analyze_relationship_with_llm(
        self,
        source_table: str,
        target_table: str,
        fk_columns: List[str],
        source_info: Dict[str, Any],
        target_info: Dict[str, Any],
        business_context: Optional[str] = None
    ) -> Optional[str]:
        """使用LLM智能分析关系类型
        
        Args:
            source_table: 源表名
            target_table: 目标表名
            fk_columns: 外键字段列表
            source_info: 源表信息
            target_info: 目标表信息
            business_context: 业务上下文描述（从数据库连接或项目描述中获取）
        """
        try:
            source_columns = [col["name"] for col in source_info.get("columns", [])]
            target_columns = [col["name"] for col in target_info.get("columns", [])]
            
            # 构建业务上下文提示
            context_prompt = ""
            if business_context:
                context_prompt = f"\n业务背景：{business_context}"
            else:
                context_prompt = "\n请根据表名和字段名推断业务语义。"
            
            prompt = f"""
请分析以下两个数据库表之间的关系类型。

源表：{source_table}
源表字段：{', '.join(source_columns[:10])}

目标表：{target_table}
目标表字段：{', '.join(target_columns[:10])}

外键字段：{', '.join(fk_columns) if fk_columns else '无'}
{context_prompt}

请根据业务语义判断关系类型。可能的关系类型：
1. is_a - 继承关系（如 admin_user is_a user）
2. has_a - 包含/拥有关系（如 user has_a 运动记录）
3. belongs_to - 属于关系（如 user belongs_to 群组）
4. contains - 包含关系（如 群组 contains 用户）
5. binds_to - 绑定关系（如 user binds_to 设备、邮箱、账号）
6. owns - 拥有关系（如 user owns 运动数据、运动记录）
7. associates_with - 关联关系（如 设备 associates_with 手环、app）
8. connects_to - 连接关系（如 app connects_to 设备）
9. controls - 控制关系（如 app controls 设备）
10. shares_with - 共享关系（如 运动数据 shares_with 第三方服务）
11. creates - 创建关系（如 user creates 计划、活动）
12. uses - 使用关系（如 user uses 课程、计划）
13. collects - 收藏关系（如 user collects 课程）
14. generates - 生成关系（如 记录 generates 计划）
15. participates_in - 参与关系（如 user participates_in 活动）
16. manages - 管理关系（如 user manages 家庭）
17. has_attribute - 有属性（如 设备 has_attribute 属性表）
18. has_version - 有版本（如 设备 has_version）
19. supports - 支持（如 设备 supports 模式）
20. upgrades - 升级关系（如 user upgrades 设备固件）
21. depend_on - 依赖关系（默认）

只输出关系类型，不要其他文字：
"""
            result = self.llm_service.chat(prompt, temperature=0.3, max_tokens=20)
            rel_type = result.strip().lower()
            
            # 验证关系类型是否有效
            valid_types = [
                "is_a", "has_a", "belongs_to", "contains", "binds_to", "owns",
                "associates_with", "connects_to", "controls", "shares_with",
                "creates", "uses", "collects", "generates", "participates_in",
                "manages", "has_attribute", "has_version", "supports", "upgrades",
                "depend_on"
            ]
            
            if rel_type in valid_types:
                return rel_type
        except Exception as e:
            print(f"LLM关系分析失败: {e}")
        
        return None
    
    def _is_inheritance_relationship(self, source: str, target: str) -> bool:
        """判断是否是继承关系"""
        source_lower = source.lower()
        target_lower = target.lower()
        
        # 模式：子表名通常包含父表名
        if source_lower in target_lower or target_lower in source_lower:
            # 检查是否是扩展表（如 user -> admin_user）
            if any(keyword in target_lower for keyword in ['admin', 'super', 'vip', 'premium']):
                return True
        
        return False
    
    def _is_composition_relationship(
        self,
        source: str,
        target: str,
        foreign_key_info: Dict[str, Any]
    ) -> bool:
        """判断是否是组合关系（has_a）"""
        source_lower = source.lower()
        target_lower = target.lower()
        
        # 模式1：目标表名包含源表名（如 order -> order_item）
        if source_lower in target_lower:
            return True
        
        # 模式2：通过字段名判断（如 order_id, user_id）
        fk_columns = foreign_key_info.get("constrained_columns", [])
        if any(source_lower.replace('_', '') in col.lower() for col in fk_columns):
            return True
        
        return False
    
    def _check_contains_relationship(
        self,
        source: str,
        target: str,
        source_info: Dict[str, Any],
        target_info: Dict[str, Any]
    ) -> Optional[str]:
        """检查包含/拥有关系"""
        source_lower = source.lower()
        target_lower = target.lower()
        
        # 群组包含用户
        if any(keyword in source_lower for keyword in ['group', '群组', 'team', 'family', '家庭']):
            if any(keyword in target_lower for keyword in ['user', '用户', 'member', '成员']):
                return "contains"
        
        # 用户拥有数据/记录
        if any(keyword in source_lower for keyword in ['user', '用户']):
            if any(keyword in target_lower for keyword in ['record', '记录', 'data', '数据', 'plan', '计划']):
                return "owns"
            
            # 用户包含各种属性表
            if any(keyword in target_lower for keyword in ['profile', 'profile', 'info', '信息', 'attribute', '属性']):
                return "has_a"
        
        # 设备包含属性、版本、模式等
        if any(keyword in source_lower for keyword in ['device', '设备', 'equipment']):
            if any(keyword in target_lower for keyword in ['attribute', '属性', 'version', '版本', 'mode', '模式', 'program', '程序']):
                return "has_a"
        
        return None
    
    def _check_bind_relationship(
        self,
        source: str,
        target: str,
        fk_columns: List[str]
    ) -> bool:
        """检查绑定关系"""
        source_lower = source.lower()
        target_lower = target.lower()
        
        # 用户绑定设备、账号、邮箱等
        if any(keyword in source_lower for keyword in ['user', '用户']):
            if any(keyword in target_lower for keyword in [
                'device', '设备', 'equipment', 'email', '邮箱', 'phone', '手机',
                'wechat', '微信', 'weibo', '微博', 'google', 'apple', 'account', '账号',
                'band', '手环', 'watch'
            ]):
                return True
        
        # 字段名包含bind、绑定
        if any('bind' in col.lower() or '绑定' in col.lower() for col in fk_columns):
            return True
        
        return False
    
    def _check_associate_relationship(
        self,
        source: str,
        target: str
    ) -> bool:
        """检查关联关系"""
        source_lower = source.lower()
        target_lower = target.lower()
        
        # 设备与手环、app、watch关联
        if any(keyword in source_lower for keyword in ['device', '设备', 'equipment']):
            if any(keyword in target_lower for keyword in ['band', '手环', 'watch', 'app', 'application', 'remote', '遥控器']):
                return True
        
        if any(keyword in target_lower for keyword in ['device', '设备', 'equipment']):
            if any(keyword in source_lower for keyword in ['band', '手环', 'watch', 'app', 'application', 'remote', '遥控器']):
                return True
        
        return False
    
    def _check_connect_control_relationship(
        self,
        source: str,
        target: str
    ) -> bool:
        """检查连接/控制关系"""
        source_lower = source.lower()
        target_lower = target.lower()
        
        # app/遥控器连接/控制设备
        if any(keyword in source_lower for keyword in ['app', 'application', 'remote', '遥控器']):
            if any(keyword in target_lower for keyword in ['device', '设备', 'equipment']):
                return True
        
        return False
    
    def _check_create_use_relationship(
        self,
        source: str,
        target: str,
        fk_columns: List[str]
    ) -> Optional[str]:
        """检查创建/使用关系"""
        source_lower = source.lower()
        target_lower = target.lower()
        
        # 用户创建计划、活动
        if any(keyword in source_lower for keyword in ['user', '用户']):
            if any(keyword in target_lower for keyword in ['plan', '计划', 'activity', '活动']):
                # 检查是否有creator_id、user_id等字段
                if any(keyword in ' '.join(fk_columns).lower() for keyword in ['creator', 'create', 'owner', 'user']):
                    return "creates"
            
            # 用户使用课程、计划
            if any(keyword in target_lower for keyword in ['course', '课程', 'plan', '计划', 'program', '程序']):
                if any(keyword in ' '.join(fk_columns).lower() for keyword in ['use', 'collect', '收藏']):
                    return "uses"
        
        return None
    
    def _check_share_relationship(
        self,
        source: str,
        target: str
    ) -> bool:
        """检查共享关系"""
        source_lower = source.lower()
        target_lower = target.lower()
        
        # 运动数据与第三方服务共享
        if any(keyword in source_lower for keyword in ['data', '数据', 'record', '记录']):
            if any(keyword in target_lower for keyword in ['third', '第三方', 'fit', 'health', '健康', 'google', 'huawei', '华为']):
                return True
        
        return False
    
    def generate_cypher_queries(
        self,
        relationships: List[Dict[str, Any]],
        project_id: int,
        tables: List[Dict[str, Any]]
    ) -> str:
        """生成Cypher查询文件内容"""
        from datetime import datetime
        
        cypher_lines = [
            "// 数据库知识图谱Cypher查询文件",
            f"// 项目ID: {project_id}",
            f"// 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "// 清空旧数据",
            f"MATCH (n) WHERE n.project_id = {project_id} DETACH DELETE n;",
            "",
            "// 创建表节点",
        ]
        
        # 创建表节点
        for table in tables:
            table_name = table.get("name", "")
            table_comment = table.get("comment", "")
            cypher_lines.append(f"CREATE (t:Table {{name: '{table_name}', project_id: {project_id}, comment: '{table_comment}'}});")
        
        cypher_lines.append("")
        cypher_lines.append("// 创建表关系")
        
        # 生成关系创建语句
        for rel in relationships:
            rel_type_map = {
                "has_a": "HAS_A",
                "is_a": "IS_A",
                "depend_on": "DEPEND_ON",
                "foreign_key": "HAS_FOREIGN_KEY",
                "belongs_to": "BELONGS_TO",
                "contains": "CONTAINS",
                "binds_to": "BINDS_TO",
                "owns": "OWNS",
                "associates_with": "ASSOCIATES_WITH",
                "connects_to": "CONNECTS_TO",
                "controls": "CONTROLS",
                "shares_with": "SHARES_WITH",
                "creates": "CREATES",
                "uses": "USES",
                "collects": "COLLECTS",
                "generates": "GENERATES",
                "participates_in": "PARTICIPATES_IN",
                "manages": "MANAGES",
                "has_attribute": "HAS_ATTRIBUTE",
                "has_version": "HAS_VERSION",
                "supports": "SUPPORTS",
                "upgrades": "UPGRADES"
            }
            cypher_type = rel_type_map.get(rel.get("relationship_type", ""), "RELATED_TO")
            
            source_table = rel.get("source_table_name", "")
            target_table = rel.get("target_table_name", "")
            description = rel.get("description", "").replace("'", "\\'")
            
            fk_cols = json.loads(rel.get("foreign_key_columns", "[]")) if rel.get("foreign_key_columns") else []
            ref_cols = json.loads(rel.get("referred_columns", "[]")) if rel.get("referred_columns") else []
            
            cypher_query = f"""// {description}
MATCH (t1:Table {{name: '{source_table}', project_id: {project_id}}})
MATCH (t2:Table {{name: '{target_table}', project_id: {project_id}}})
CREATE (t1)-[:{cypher_type} {{
    foreign_key_columns: {json.dumps(fk_cols, ensure_ascii=False)},
    referred_columns: {json.dumps(ref_cols, ensure_ascii=False)},
    description: '{description}'
}}]->(t2);"""
            cypher_lines.append(cypher_query)
            cypher_lines.append("")
        
        return "\n".join(cypher_lines)
    


class DatabaseMetadataManager:
    """数据库元数据管理器：提取、保存、分析"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.metadata_service = MetadataService()
        self.db_service = DatabaseService()
    
    def extract_and_save_metadata(
        self,
        db_connection: DBConnection,
        engine,
        schema_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """提取并保存数据库元数据"""
        saved_tables = []
        
        for table_info in schema_info["tables"]:
            table_name = table_info["name"]
            
            # 提取表注释
            table_comment = self.metadata_service.extract_table_comment(engine, table_name)
            
            # 获取表行数
            row_count = self._get_table_row_count(engine, table_name)
            
            # 保存表元数据
            table_metadata = TableMetadata(
                db_connection_id=db_connection.id,
                table_name=table_name,
                table_comment=table_comment,
                primary_keys=json.dumps(table_info.get("primary_keys", [])),
                indexes=json.dumps(table_info.get("indexes", [])),
                foreign_keys=json.dumps(table_info.get("foreign_keys", [])),
                column_count=table_info.get("column_count", 0),
                row_count=row_count,
                metadata=json.dumps({
                    "database_name": schema_info.get("database_name", "")
                })
            )
            
            # 检查是否已存在
            existing = self.db.query(TableMetadata).filter(
                TableMetadata.db_connection_id == db_connection.id,
                TableMetadata.table_name == table_name
            ).first()
            
            if existing:
                # 更新
                for key, value in table_metadata.__dict__.items():
                    if not key.startswith('_'):
                        setattr(existing, key, value)
                table_metadata = existing
            else:
                self.db.add(table_metadata)
            
            self.db.flush()
            
            # 保存字段元数据
            for idx, column_info in enumerate(table_info["columns"]):
                column_name = column_info["name"]
                
                # 提取字段注释
                column_comment = self.metadata_service.extract_column_comment(
                    engine, table_name, column_name
                )
                
                column_metadata = ColumnMetadata(
                    table_metadata_id=table_metadata.id,
                    column_name=column_name,
                    column_comment=column_comment,
                    data_type=str(column_info["type"]),
                    is_nullable="YES" if column_info.get("nullable", True) else "NO",
                    default_value=str(column_info.get("default", "")) if column_info.get("default") else None,
                    is_primary_key=column_info.get("primary_key", False),
                    is_foreign_key=any(
                        column_name in fk.get("constrained_columns", [])
                        for fk in table_info.get("foreign_keys", [])
                    ),
                    auto_increment=column_info.get("autoincrement", False),
                    position=idx + 1
                )
                
                # 检查是否已存在
                existing_col = self.db.query(ColumnMetadata).filter(
                    ColumnMetadata.table_metadata_id == table_metadata.id,
                    ColumnMetadata.column_name == column_name
                ).first()
                
                if existing_col:
                    for key, value in column_metadata.__dict__.items():
                        if not key.startswith('_'):
                            setattr(existing_col, key, value)
                else:
                    self.db.add(column_metadata)
            
            saved_tables.append(table_metadata)
        
        self.db.commit()
        
        return {
            "saved_tables": len(saved_tables),
            "tables": saved_tables
        }
    
    def analyze_and_save_relationships(
        self,
        db_connection: DBConnection,
        engine,
        schema_info: Dict[str, Any],
        business_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """分析并保存表关系
        
        Args:
            db_connection: 数据库连接对象
            engine: 数据库引擎
            schema_info: 数据库schema信息
            business_context: 业务上下文描述（从项目描述中获取）
        """
        saved_relationships = []
        
        # 如果没有提供业务上下文，尝试从项目描述中获取
        if not business_context:
            from app.models import Project
            project = self.db.query(Project).filter(Project.id == db_connection.project_id).first()
            if project and project.description:
                business_context = project.description
        
        # 构建完整的业务上下文（包括数据库信息）
        full_context = ""
        if business_context:
            full_context = f"项目描述：{business_context}。"
        full_context += f"数据库类型：{db_connection.db_type}，数据库名：{db_connection.database_name}。"
        
        # 获取已保存的表元数据
        table_metadata_map = {
            tm.table_name: tm
            for tm in self.db.query(TableMetadata).filter(
                TableMetadata.db_connection_id == db_connection.id
            ).all()
        }
        
        for table_info in schema_info["tables"]:
            source_table_name = table_info["name"]
            source_table_meta = table_metadata_map.get(source_table_name)
            
            if not source_table_meta:
                continue
            
            # 分析外键关系
            for fk_info in table_info.get("foreign_keys", []):
                target_table_name = fk_info["referred_table"]
                target_table_meta = table_metadata_map.get(target_table_name)
                
                if not target_table_meta:
                    continue
                
                # 综合分析关系类型（可能返回多个关系）
                from app.services.relationship_analyzer import RelationshipAnalyzer
                relationship_analyzer = RelationshipAnalyzer()
                
                source_table_info = next((t for t in schema_info["tables"] if t["name"] == source_table_name), None)
                target_table_info = next((t for t in schema_info["tables"] if t["name"] == target_table_name), None)
                
                source_columns = [col["name"] for col in (source_table_info.get("columns", []) if source_table_info else [])]
                target_columns = [col["name"] for col in (target_table_info.get("columns", []) if target_table_info else [])]
                
                # 综合分析所有关系
                all_relationships = relationship_analyzer.analyze_comprehensive_relationships(
                    source_table_name,
                    target_table_name,
                    source_columns,
                    target_columns,
                    fk_info,
                    schema_info,
                    business_context=full_context
                )
                
                # 选择置信度最高的关系作为主关系
                if all_relationships:
                    main_relationship = max(all_relationships, key=lambda x: x.get("confidence", 0))
                    relationship_type = main_relationship.get("type", "depend_on")
                    description = main_relationship.get("description", "")
                else:
                    # 备用方案：使用原有方法
                    relationship_type = self.metadata_service.analyze_relationship_type(
                        source_table_name,
                        target_table_name,
                        fk_info,
                        schema_info,
                        business_context=full_context
                    )
                    description = self._build_relationship_description(
                        source_table_name,
                        target_table_name,
                        relationship_type,
                        fk_info
                    )
                
                # 生成Cypher查询
                cypher_query = self._generate_cypher_for_relationship(
                    source_table_name,
                    target_table_name,
                    relationship_type,
                    fk_info,
                    db_connection.project_id
                )
                
                # 创建主关系
                relationship = TableRelationship(
                    db_connection_id=db_connection.id,
                    source_table_id=source_table_meta.id,
                    target_table_id=target_table_meta.id,
                    relationship_type=relationship_type,
                    relationship_name=f"{source_table_name}_{relationship_type}_{target_table_name}",
                    foreign_key_columns=json.dumps(fk_info.get("constrained_columns", [])),
                    referred_columns=json.dumps(fk_info.get("referred_columns", [])),
                    description=description,
                    cypher_query=cypher_query
                )
                
                # 检查是否已存在
                existing = self.db.query(TableRelationship).filter(
                    TableRelationship.source_table_id == source_table_meta.id,
                    TableRelationship.target_table_id == target_table_meta.id,
                    TableRelationship.relationship_type == relationship_type
                ).first()
                
                if existing:
                    for key, value in relationship.__dict__.items():
                        if not key.startswith('_'):
                            setattr(existing, key, value)
                    relationship = existing
                else:
                    self.db.add(relationship)
                
                saved_relationships.append(relationship)
                
                # 如果有多个关系，创建额外的关系记录（但不作为主外键关系）
                if len(all_relationships) > 1:
                    for rel in all_relationships:
                        if rel.get("type") != relationship_type:
                            # 创建业务语义关系（不作为主外键）
                            semantic_rel = TableRelationship(
                                db_connection_id=db_connection.id,
                                source_table_id=source_table_meta.id,
                                target_table_id=target_table_meta.id,
                                relationship_type=rel.get("type", "depend_on"),
                                relationship_name=f"{source_table_name}_{rel.get('type')}_{target_table_name}",
                                foreign_key_columns=None,  # 业务语义关系可能没有外键
                                referred_columns=None,
                                description=rel.get("description", ""),
                                cypher_query=None
                            )
                            
                            # 检查是否已存在
                            existing_semantic = self.db.query(TableRelationship).filter(
                                TableRelationship.source_table_id == source_table_meta.id,
                                TableRelationship.target_table_id == target_table_meta.id,
                                TableRelationship.relationship_type == rel.get("type")
                            ).first()
                            
                            if not existing_semantic:
                                self.db.add(semantic_rel)
                                saved_relationships.append(semantic_rel)
        
        self.db.commit()
        
        return {
            "saved_relationships": len(saved_relationships),
            "relationships": saved_relationships
        }
    
    def _get_table_row_count(self, engine, table_name: str) -> int:
        """获取表的行数"""
        try:
            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`"))
                return result.fetchone()[0]
        except:
            return 0
    
    def _build_relationship_description(
        self,
        source: str,
        target: str,
        rel_type: str,
        fk_info: Dict[str, Any]
    ) -> str:
        """构建关系描述"""
        fk_cols = ", ".join(fk_info.get("constrained_columns", []))
        ref_cols = ", ".join(fk_info.get("referred_columns", []))
        
        type_map = {
            "has_a": "包含",
            "is_a": "继承",
            "depend_on": "依赖"
        }
        type_desc = type_map.get(rel_type, "关联")
        
        return f"{source}通过字段({fk_cols}){type_desc}{target}的字段({ref_cols})"
    
    def _generate_cypher_for_relationship(
        self,
        source: str,
        target: str,
        rel_type: str,
        fk_info: Dict[str, Any],
        project_id: int
    ) -> str:
        """生成关系的Cypher查询"""
        rel_type_map = {
            "has_a": "HAS_A",
            "is_a": "IS_A",
            "depend_on": "DEPEND_ON",
            "foreign_key": "HAS_FOREIGN_KEY"
        }
        cypher_type = rel_type_map.get(rel_type, "RELATED_TO")
        
        fk_cols = json.dumps(fk_info.get("constrained_columns", []))
        ref_cols = json.dumps(fk_info.get("referred_columns", []))
        
        return f"""MATCH (t1:Table {{name: '{source}', project_id: {project_id}}})
MATCH (t2:Table {{name: '{target}', project_id: {project_id}}})
CREATE (t1)-[:{cypher_type} {{
    foreign_key_columns: {fk_cols},
    referred_columns: {ref_cols}
}}]->(t2)"""
    
    def generate_cypher_file(
        self,
        db_connection: DBConnection,
        output_path: Optional[str] = None
    ) -> str:
        """生成Cypher文件"""
        from app.models import TableMetadata
        
        relationships_query = self.db.query(TableRelationship).filter(
            TableRelationship.db_connection_id == db_connection.id
        ).all()
        
        # 转换为字典格式
        relationships = []
        for rel in relationships_query:
            source_table = self.db.query(TableMetadata).filter(TableMetadata.id == rel.source_table_id).first()
            target_table = self.db.query(TableMetadata).filter(TableMetadata.id == rel.target_table_id).first()
            
            relationships.append({
                "source_table_name": source_table.table_name if source_table else "",
                "target_table_name": target_table.table_name if target_table else "",
                "relationship_type": rel.relationship_type,
                "relationship_name": rel.relationship_name,
                "description": rel.description,
                "foreign_key_columns": rel.foreign_key_columns,
                "referred_columns": rel.referred_columns
            })
        
        # 获取所有表
        tables_query = self.db.query(TableMetadata).filter(
            TableMetadata.db_connection_id == db_connection.id
        ).all()
        
        tables = [
            {
                "name": t.table_name,
                "comment": t.table_comment or ""
            }
            for t in tables_query
        ]
        
        cypher_content = self.metadata_service.generate_cypher_queries(
            relationships,
            db_connection.project_id,
            tables
        )
        
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(cypher_content)
        
        return cypher_content

