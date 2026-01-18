from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, inspect, text, MetaData, Table
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import pymysql
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError, ClientError
import json
import pandas as pd
import statistics
from datetime import datetime
import time
from threading import Lock

from app.config import settings


class DatabaseService:
    """数据库服务，用于连接和分析数据库"""
    
    def __init__(self):
        self.neo4j_driver = None
        self._neo4j_lock = Lock()
        self._last_neo4j_connect_time = 0
        self._neo4j_connect_delay = 5  # 连接失败后延迟5秒重试
        self._init_neo4j_connection()
    
    def _init_neo4j_connection(self):
        """初始化Neo4j连接，带重试机制"""
        try:
            self.neo4j_driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                connection_timeout=10,
                max_connection_lifetime=3600
            )
            # 测试连接
            with self.neo4j_driver.session() as session:
                session.run("RETURN 1")
        except (AuthError, ClientError) as e:
            error_code = getattr(e, 'code', '')
            if 'AuthenticationRateLimit' in str(error_code):
                print(f"Neo4j认证被锁定，将在{self._neo4j_connect_delay}秒后重试")
                self.neo4j_driver = None
            else:
                print(f"Neo4j连接失败: {e}")
                self.neo4j_driver = None
        except Exception as e:
            print(f"Neo4j初始化失败: {e}")
            self.neo4j_driver = None
    
    def _get_neo4j_session(self):
        """获取Neo4j会话，带自动重连"""
        with self._neo4j_lock:
            current_time = time.time()
            
            # 如果连接不存在或上次连接失败后等待时间不够，尝试重连
            if self.neo4j_driver is None:
                if current_time - self._last_neo4j_connect_time < self._neo4j_connect_delay:
                    raise ServiceUnavailable("Neo4j连接被锁定，请稍后重试")
                self._last_neo4j_connect_time = current_time
                self._init_neo4j_connection()
            
            # 如果仍然连接失败，返回None
            if self.neo4j_driver is None:
                raise ServiceUnavailable("Neo4j连接不可用")
            
            try:
                return self.neo4j_driver.session()
            except (AuthError, ClientError) as e:
                error_code = getattr(e, 'code', '')
                if 'AuthenticationRateLimit' in str(error_code):
                    print("Neo4j认证被锁定，关闭连接并延迟重试")
                    try:
                        self.neo4j_driver.close()
                    except:
                        pass
                    self.neo4j_driver = None
                    self._last_neo4j_connect_time = current_time
                    raise ServiceUnavailable("Neo4j认证被锁定，请稍后重试")
                raise
    
    def connect_database(
        self,
        db_type: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        charset: str = "utf8mb4"
    ):
        """连接数据库（支持MySQL）"""
        if db_type.lower() == "mysql":
            # 转义密码和数据库名中的特殊字符（包括中文）
            from urllib.parse import quote_plus
            encoded_password = quote_plus(password)
            encoded_database = quote_plus(database)  # 对数据库名进行URL编码以支持中文
            connection_string = f"mysql+pymysql://{username}:{encoded_password}@{host}:{port}/{encoded_database}?charset={charset}&connect_timeout=10"
            engine = create_engine(
                connection_string,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
                pool_timeout=10,
                connect_args={
                    "connect_timeout": 10,
                    "read_timeout": 10,
                    "write_timeout": 10,
                }
            )
            return engine
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")
    
    def connect_mysql(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str
    ):
        """连接MySQL数据库（兼容旧方法）"""
        return self.connect_database("mysql", host, port, database, username, password)
    
    def test_connection(
        self,
        db_type: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str
    ) -> Dict[str, Any]:
        """测试数据库连接"""
        try:
            engine = self.connect_database(db_type, host, port, database, username, password)
            with engine.connect() as conn:
                # 测试连接，设置超时
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
                return {
                    "success": True,
                    "message": "连接成功",
                    "version": self._get_database_version(engine)
                }
        except SQLAlchemyError as e:
            error_msg = str(e)
            # 提供更友好的错误信息
            if "timed out" in error_msg or "timeout" in error_msg.lower():
                return {
                    "success": False,
                    "message": "连接超时，请检查网络连接和数据库服务器是否可访问"
                }
            elif "Lost connection" in error_msg:
                return {
                    "success": False,
                    "message": "连接丢失，可能是网络不稳定或服务器繁忙，请稍后重试"
                }
            elif "Access denied" in error_msg or "1045" in error_msg:
                return {
                    "success": False,
                    "message": "数据库认证失败，请检查用户名和密码"
                }
            elif "Unknown database" in error_msg or "1049" in error_msg:
                return {
                    "success": False,
                    "message": f"数据库 '{database}' 不存在，请检查数据库名称"
                }
            else:
                return {
                    "success": False,
                    "message": f"连接失败: {error_msg}"
                }
        except Exception as e:
            error_msg = str(e)
            if "timed out" in error_msg or "timeout" in error_msg.lower():
                return {
                    "success": False,
                    "message": "连接超时，请检查网络连接和数据库服务器是否可访问"
                }
            return {
                "success": False,
                "message": f"连接失败: {error_msg}"
            }
    
    def _get_database_version(self, engine) -> str:
        """获取数据库版本"""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT VERSION()"))
                version = result.fetchone()[0]
                return version
        except:
            return "Unknown"
    
    def analyze_database_schema(self, engine) -> Dict[str, Any]:
        """分析数据库元数据：表结构、字段类型、约束关系"""
        inspector = inspect(engine)
        schema_info = {
            "database_name": str(engine.url).split('/')[-1].split('?')[0],
            "tables": [],
            "table_count": 0,
            "total_columns": 0
        }
        
        table_names = inspector.get_table_names()
        schema_info["table_count"] = len(table_names)
        
        for table_name in table_names:
            table_info = {
                "name": table_name,
                "columns": [],
                "foreign_keys": [],
                "indexes": [],
                "primary_keys": [],
                "column_count": 0
            }
            
            # 获取列信息
            columns = inspector.get_columns(table_name)
            for column in columns:
                column_info = {
                    "name": column["name"],
                    "type": str(column["type"]),
                    "nullable": column["nullable"],
                    "default": str(column.get("default", "")) if column.get("default") is not None else None,
                    "primary_key": column.get("primary_key", False),
                    "autoincrement": column.get("autoincrement", False)
                }
                table_info["columns"].append(column_info)
                schema_info["total_columns"] += 1
            
            table_info["column_count"] = len(table_info["columns"])
            
            # 获取主键信息
            pk_constraint = inspector.get_pk_constraint(table_name)
            if pk_constraint:
                table_info["primary_keys"] = pk_constraint.get("constrained_columns", [])
            
            # 获取外键信息
            for fk in inspector.get_foreign_keys(table_name):
                fk_info = {
                    "name": fk.get("name", ""),
                    "constrained_columns": fk["constrained_columns"],
                    "referred_table": fk["referred_table"],
                    "referred_columns": fk["referred_columns"],
                    "ondelete": fk.get("ondelete", "NO ACTION"),
                    "onupdate": fk.get("onupdate", "NO ACTION")
                }
                table_info["foreign_keys"].append(fk_info)
            
            # 获取索引信息
            indexes = inspector.get_indexes(table_name)
            for idx in indexes:
                idx_info = {
                    "name": idx.get("name", ""),
                    "columns": idx.get("column_names", []),
                    "unique": idx.get("unique", False)
                }
                table_info["indexes"].append(idx_info)
            
            schema_info["tables"].append(table_info)
        
        return schema_info
    
    def sample_data(self, engine, table_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """采样数据"""
        with engine.connect() as conn:
            # 使用参数化查询防止SQL注入
            result = conn.execute(text(f"SELECT * FROM `{table_name}` LIMIT :limit"), {"limit": limit})
            columns = result.keys()
            rows = result.fetchall()
            return [dict(zip(columns, row)) for row in rows]
    
    def analyze_data_features(
        self,
        engine,
        table_name: str,
        sample_size: int = 1000
    ) -> Dict[str, Any]:
        """分析实际数据特征和数据分布"""
        try:
            # 获取表的总行数
            with engine.connect() as conn:
                count_result = conn.execute(text(f"SELECT COUNT(*) as count FROM `{table_name}`"))
                total_rows = count_result.fetchone()[0]
            
            # 采样数据
            sample_data = self.sample_data(engine, table_name, min(sample_size, total_rows))
            
            if not sample_data:
                return {
                    "table_name": table_name,
                    "total_rows": total_rows,
                    "sample_size": 0,
                    "columns": {}
                }
            
            # 转换为DataFrame进行分析
            df = pd.DataFrame(sample_data)
            
            # 获取列信息
            inspector = inspect(engine)
            columns_info = inspector.get_columns(table_name)
            column_types = {col["name"]: str(col["type"]) for col in columns_info}
            
            features = {
                "table_name": table_name,
                "total_rows": total_rows,
                "sample_size": len(sample_data),
                "columns": {}
            }
            
            # 分析每个字段的特征
            for column_name in df.columns:
                col_data = df[column_name]
                col_type = column_types.get(column_name, "unknown")
                
                column_features = {
                    "type": col_type,
                    "non_null_count": col_data.notna().sum(),
                    "null_count": col_data.isna().sum(),
                    "null_percentage": (col_data.isna().sum() / len(col_data)) * 100,
                    "unique_count": col_data.nunique(),
                    "unique_percentage": (col_data.nunique() / len(col_data)) * 100
                }
                
                # 数值型字段的统计
                if pd.api.types.is_numeric_dtype(col_data):
                    numeric_data = col_data.dropna()
                    if len(numeric_data) > 0:
                        column_features.update({
                            "min": float(numeric_data.min()) if not pd.isna(numeric_data.min()) else None,
                            "max": float(numeric_data.max()) if not pd.isna(numeric_data.max()) else None,
                            "mean": float(numeric_data.mean()) if not pd.isna(numeric_data.mean()) else None,
                            "median": float(numeric_data.median()) if not pd.isna(numeric_data.median()) else None,
                            "std": float(numeric_data.std()) if not pd.isna(numeric_data.std()) else None
                        })
                
                # 字符串型字段的统计
                if pd.api.types.is_string_dtype(col_data) or pd.api.types.is_object_dtype(col_data):
                    string_data = col_data.dropna().astype(str)
                    if len(string_data) > 0:
                        lengths = string_data.str.len()
                        column_features.update({
                            "avg_length": float(lengths.mean()) if not pd.isna(lengths.mean()) else None,
                            "min_length": int(lengths.min()) if not pd.isna(lengths.min()) else None,
                            "max_length": int(lengths.max()) if not pd.isna(lengths.max()) else None,
                            "most_common_values": string_data.value_counts().head(5).to_dict() if len(string_data.value_counts()) > 0 else {}
                        })
                
                # 日期型字段的统计
                if pd.api.types.is_datetime64_any_dtype(col_data):
                    datetime_data = pd.to_datetime(col_data.dropna())
                    if len(datetime_data) > 0:
                        column_features.update({
                            "earliest": datetime_data.min().isoformat() if not pd.isna(datetime_data.min()) else None,
                            "latest": datetime_data.max().isoformat() if not pd.isna(datetime_data.max()) else None
                        })
                
                features["columns"][column_name] = column_features
            
            return features
        except Exception as e:
            return {
                "table_name": table_name,
                "error": str(e)
            }
    
    def analyze_data_distribution(
        self,
        engine,
        table_name: str,
        column_name: str,
        bins: int = 10
    ) -> Dict[str, Any]:
        """分析数据分布"""
        try:
            sample_data = self.sample_data(engine, table_name, 10000)
            df = pd.DataFrame(sample_data)
            
            if column_name not in df.columns:
                return {"error": f"列 {column_name} 不存在"}
            
            col_data = df[column_name].dropna()
            
            distribution = {
                "column_name": column_name,
                "total_values": len(col_data),
                "null_count": df[column_name].isna().sum()
            }
            
            if pd.api.types.is_numeric_dtype(col_data):
                # 数值型分布
                distribution.update({
                    "type": "numeric",
                    "histogram": pd.cut(col_data, bins=bins).value_counts().sort_index().to_dict(),
                    "percentiles": {
                        "p25": float(col_data.quantile(0.25)),
                        "p50": float(col_data.quantile(0.50)),
                        "p75": float(col_data.quantile(0.75)),
                        "p90": float(col_data.quantile(0.90)),
                        "p95": float(col_data.quantile(0.95)),
                        "p99": float(col_data.quantile(0.99))
                    }
                })
            else:
                # 分类型分布
                value_counts = col_data.value_counts()
                distribution.update({
                    "type": "categorical",
                    "distribution": value_counts.head(20).to_dict(),
                    "total_categories": len(value_counts)
                })
            
            return distribution
        except Exception as e:
            return {"error": str(e)}
    
    def build_knowledge_graph(
        self,
        schema_info: Dict[str, Any],
        project_id: int,
        data_features: Optional[Dict[str, Any]] = None,
        business_context: Optional[str] = None
    ):
        """构建知识图谱：节点（数据表、字段、数据类型），关系（外键关联、数据依赖、业务逻辑关系）"""
        # 检查Neo4j连接是否可用
        if self.neo4j_driver is None:
            raise ServiceUnavailable("Neo4j服务不可用，无法构建知识图谱。请检查Neo4j配置或稍后重试。")

        try:
            session = self._get_neo4j_session()
        except ServiceUnavailable as e:
            raise ServiceUnavailable(f"Neo4j连接失败: {str(e)}")

        with session:
            # 清空旧数据
            session.run(
                "MATCH (n) WHERE n.project_id = $project_id DETACH DELETE n",
                project_id=project_id
            )
            
            # 创建数据类型节点（先统计所有数据类型）
            data_types = set()
            for table in schema_info["tables"]:
                for column in table["columns"]:
                    col_type = column.get("type", "")
                    # 提取基础类型（去除长度等参数）
                    base_type = col_type.split('(')[0].upper() if '(' in col_type else col_type.upper()
                    data_types.add(base_type)
            
            # 创建数据类型节点
            for data_type in data_types:
                session.run("""
                    MERGE (dt:DataType {
                        name: $type_name,
                        project_id: $project_id
                    })
                """, type_name=data_type, project_id=project_id)
            
            # 创建表节点
            for table in schema_info["tables"]:
                # 获取表的特征信息
                table_features = None
                if data_features:
                    for feat in data_features.values():
                        if isinstance(feat, dict) and feat.get("table_name") == table["name"]:
                            table_features = feat
                            break
                
                table_props = {
                    "name": table["name"],
                    "project_id": project_id,
                    "column_count": table.get("column_count", 0)
                }
                
                if table_features:
                    table_props["total_rows"] = table_features.get("total_rows", 0)
                    table_props["sample_size"] = table_features.get("sample_size", 0)
                
                session.run("""
                    CREATE (t:Table $props)
                """, props=table_props)
                
                # 创建字段节点并关联
                for column in table["columns"]:
                    col_type = column.get("type", "")
                    base_type = col_type.split('(')[0].upper() if '(' in col_type else col_type.upper()
                    
                    # 获取字段的特征信息
                    col_features = None
                    if table_features and table_features.get("columns"):
                        col_features = table_features["columns"].get(column["name"])
                    
                    column_props = {
                        "name": column["name"],
                        "type": col_type,
                        "base_type": base_type,
                        "nullable": column.get("nullable", True),
                        "is_primary_key": column.get("primary_key", False),
                        "auto_increment": column.get("autoincrement", False),
                        "default_value": column.get("default")
                    }
                    
                    if col_features:
                        column_props.update({
                            "null_percentage": col_features.get("null_percentage"),
                            "unique_percentage": col_features.get("unique_percentage")
                        })
                    
                    # 创建字段节点
                    session.run("""
                        MATCH (t:Table {name: $table_name, project_id: $project_id})
                        CREATE (c:Column $column_props)
                        CREATE (t)-[:HAS_COLUMN]->(c)
                        
                        WITH c
                        MATCH (dt:DataType {name: $base_type, project_id: $project_id})
                        CREATE (c)-[:HAS_TYPE]->(dt)
                    """,
                        table_name=table["name"],
                        project_id=project_id,
                        column_props=column_props,
                        base_type=base_type
                    )
                
                # 创建主键关系
                if table.get("primary_keys"):
                    for pk_col in table["primary_keys"]:
                        session.run("""
                            MATCH (t:Table {name: $table_name, project_id: $project_id})
                            MATCH (c:Column {name: $column_name})
                            WHERE (t)-[:HAS_COLUMN]->(c)
                            CREATE (t)-[:HAS_PRIMARY_KEY]->(c)
                        """,
                            table_name=table["name"],
                            project_id=project_id,
                            column_name=pk_col
                        )
                
                # 创建外键关系（数据依赖关系）
                for fk in table["foreign_keys"]:
                    session.run("""
                        MATCH (t1:Table {name: $table1, project_id: $project_id})
                        MATCH (t2:Table {name: $table2, project_id: $project_id})
                        CREATE (t1)-[r:HAS_FOREIGN_KEY {
                            columns: $columns,
                            referred_columns: $referred_columns,
                            ondelete: $ondelete,
                            onupdate: $onupdate
                        }]->(t2)
                        SET r.type = 'data_dependency'
                    """,
                        table1=table["name"],
                        table2=fk["referred_table"],
                        project_id=project_id,
                        columns=fk.get("constrained_columns", []),
                        referred_columns=fk.get("referred_columns", []),
                        ondelete=fk.get("ondelete", "NO ACTION"),
                        onupdate=fk.get("onupdate", "NO ACTION")
                    )
                
                # 创建索引关系
                for idx in table.get("indexes", []):
                    if idx.get("columns"):
                        for col_name in idx["columns"]:
                            session.run("""
                                MATCH (t:Table {name: $table_name, project_id: $project_id})
                                MATCH (c:Column {name: $column_name})
                                WHERE (t)-[:HAS_COLUMN]->(c)
                                MERGE (t)-[:HAS_INDEX {
                                    index_name: $index_name,
                                    unique: $unique
                                }]->(c)
                            """,
                                table_name=table["name"],
                                project_id=project_id,
                                column_name=col_name,
                                index_name=idx.get("name", ""),
                                unique=idx.get("unique", False)
                            )
            
            # 识别业务逻辑关系（基于数据特征和业务语义）
            if data_features:
                self._build_business_relationships(session, schema_info, data_features, project_id, business_context)
    
    def _build_business_relationships(
        self,
        session,
        schema_info: Dict[str, Any],
        data_features: Dict[str, Any],
        project_id: int,
        business_context: Optional[str] = None
    ):
        """基于数据特征和业务语义构建业务逻辑关系
        
        Args:
            session: Neo4j session
            schema_info: 数据库schema信息
            data_features: 数据特征
            project_id: 项目ID
            business_context: 业务上下文描述（可选，从项目描述中获取）
        """
        tables = {t["name"]: t for t in schema_info["tables"]}
        
        # 通用业务关系识别规则（可根据business_context调整）
        relationship_patterns = {
            # 群组包含用户
            ("group", "user"): ("CONTAINS", "群组包含用户"),
            ("群组", "用户"): ("CONTAINS", "群组包含用户"),
            ("team", "user"): ("CONTAINS", "团队包含用户"),
            ("family", "user"): ("CONTAINS", "家庭包含用户"),
            ("家庭", "用户"): ("CONTAINS", "家庭包含用户"),
            
            # 用户拥有各种数据
            ("user", "record"): ("OWNS", "用户拥有运动记录"),
            ("用户", "记录"): ("OWNS", "用户拥有运动记录"),
            ("user", "data"): ("OWNS", "用户拥有运动数据"),
            ("用户", "数据"): ("OWNS", "用户拥有运动数据"),
            
            # 用户绑定设备、账号
            ("user", "device"): ("BINDS_TO", "用户绑定设备"),
            ("用户", "设备"): ("BINDS_TO", "用户绑定设备"),
            ("user", "equipment"): ("BINDS_TO", "用户绑定设备"),
            ("user", "email"): ("BINDS_TO", "用户绑定邮箱"),
            ("用户", "邮箱"): ("BINDS_TO", "用户绑定邮箱"),
            ("user", "band"): ("BINDS_TO", "用户绑定手环"),
            ("用户", "手环"): ("BINDS_TO", "用户绑定手环"),
            
            # 设备关联手环、app、watch
            ("device", "band"): ("ASSOCIATES_WITH", "设备关联手环"),
            ("设备", "手环"): ("ASSOCIATES_WITH", "设备关联手环"),
            ("device", "app"): ("ASSOCIATES_WITH", "设备关联APP"),
            ("设备", "app"): ("ASSOCIATES_WITH", "设备关联APP"),
            ("device", "watch"): ("ASSOCIATES_WITH", "设备关联手表"),
            ("设备", "watch"): ("ASSOCIATES_WITH", "设备关联手表"),
            
            # app/遥控器连接/控制设备
            ("app", "device"): ("CONNECTS_TO", "APP连接设备"),
            ("remote", "device"): ("CONNECTS_TO", "遥控器连接设备"),
            ("遥控器", "设备"): ("CONNECTS_TO", "遥控器连接设备"),
            
            # 用户创建计划、活动
            ("user", "plan"): ("CREATES", "用户创建计划"),
            ("用户", "计划"): ("CREATES", "用户创建计划"),
            ("user", "activity"): ("CREATES", "用户创建活动"),
            ("用户", "活动"): ("CREATES", "用户创建活动"),
            
            # 用户使用课程、计划
            ("user", "course"): ("USES", "用户使用课程"),
            ("用户", "课程"): ("USES", "用户使用课程"),
            
            # 用户收藏课程
            ("user", "collection"): ("COLLECTS", "用户收藏"),
            ("用户", "收藏"): ("COLLECTS", "用户收藏"),
            
            # 记录生成计划
            ("record", "plan"): ("GENERATES", "记录生成计划"),
            ("记录", "计划"): ("GENERATES", "记录生成计划"),
            
            # 用户参与活动
            ("user", "participation"): ("PARTICIPATES_IN", "用户参与活动"),
            ("用户", "参与"): ("PARTICIPATES_IN", "用户参与活动"),
            
            # 用户管理家庭
            ("user", "family"): ("MANAGES", "用户管理家庭"),
            ("用户", "家庭"): ("MANAGES", "用户管理家庭"),
            
            # 设备有属性、版本
            ("device", "attribute"): ("HAS_ATTRIBUTE", "设备有属性"),
            ("设备", "属性"): ("HAS_ATTRIBUTE", "设备有属性"),
            ("device", "version"): ("HAS_VERSION", "设备有版本"),
            ("设备", "版本"): ("HAS_VERSION", "设备有版本"),
            ("device", "mode"): ("SUPPORTS", "设备支持模式"),
            ("设备", "模式"): ("SUPPORTS", "设备支持模式"),
            
            # 数据共享
            ("data", "third"): ("SHARES_WITH", "数据与第三方共享"),
            ("数据", "第三方"): ("SHARES_WITH", "数据与第三方共享"),
        }
        
        # 识别业务关系
        for table_name, table in tables.items():
            table_lower = table_name.lower()
            
            for (source_pattern, target_pattern), (rel_type, desc) in relationship_patterns.items():
                source_match = any(keyword in table_lower for keyword in [source_pattern])
                
                if source_match:
                    # 查找匹配的目标表
                    for other_table_name, other_table in tables.items():
                        if other_table_name != table_name:
                            other_table_lower = other_table_name.lower()
                            target_match = any(keyword in other_table_lower for keyword in [target_pattern])
                            
                            if target_match:
                                # 检查是否已有外键关系
                                has_fk = any(
                                    fk.get("referred_table") == other_table_name
                                    for fk in table.get("foreign_keys", [])
                                ) or any(
                                    fk.get("referred_table") == table_name
                                    for fk in other_table.get("foreign_keys", [])
                                )
                                
                                # 创建业务关系（如果没有外键，也创建业务语义关系）
                                session.run("""
                                    MATCH (t1:Table {name: $table1, project_id: $project_id})
                                    MATCH (t2:Table {name: $table2, project_id: $project_id})
                                    MERGE (t1)-[r:BUSINESS_RELATION {
                                        type: $rel_type,
                                        description: $description,
                                        has_foreign_key: $has_fk
                                    }]->(t2)
                                """,
                                    table1=table_name,
                                    table2=other_table_name,
                                    project_id=project_id,
                                    rel_type=rel_type,
                                    description=desc,
                                    has_fk=has_fk
                                )
    
    def query_knowledge_graph(
        self,
        query: str,
        project_id: int
    ) -> List[Dict[str, Any]]:
        """查询知识图谱"""
        try:
            with self._get_neo4j_session() as session:
                result = session.run(query, project_id=project_id)
                return [record.data() for record in result]
        except Exception as e:
            print(f"查询知识图谱失败（Neo4j可能不可用）: {e}")
            return []
    
    def get_table_relationships(self, project_id: int) -> List[Dict[str, Any]]:
        """获取表之间的关系"""
        try:
            query = """
            MATCH (t1:Table {project_id: $project_id})-[r]->(t2:Table {project_id: $project_id})
            RETURN 
                t1.name as source, 
                t2.name as target, 
                type(r) as relationship_type,
                properties(r) as properties
            """
            with self._get_neo4j_session() as session:
                result = session.run(query, project_id=project_id)
                return [record.data() for record in result]
        except Exception as e:
            print(f"获取表关系失败（Neo4j可能不可用）: {e}")
            return []
    
    def get_knowledge_graph_data(self, project_id: int, connection_id: Optional[int] = None) -> Dict[str, Any]:
        """获取知识图谱数据，用于前端可视化（只返回数据库元数据，不包括API接口依赖）"""
        try:
            with self._get_neo4j_session() as session:
                # 只获取数据库元数据相关的节点（Table, Column, DataType等），排除APIInterface
                # 如果指定了connection_id，只获取该连接的数据
                if connection_id:
                    nodes_query = """
                    MATCH (n)
                    WHERE n.project_id = $project_id 
                      AND n.connection_id = $connection_id
                      AND NOT 'APIInterface' IN labels(n)
                    RETURN 
                        labels(n) as labels,
                        properties(n) as properties
                    """
                    nodes_result = session.run(nodes_query, project_id=project_id, connection_id=connection_id)
                else:
                    nodes_query = """
                    MATCH (n)
                    WHERE n.project_id = $project_id 
                      AND NOT 'APIInterface' IN labels(n)
                    RETURN 
                        labels(n) as labels,
                        properties(n) as properties
                    """
                    nodes_result = session.run(nodes_query, project_id=project_id)
                
                nodes = []
                node_ids = {}
                
                for record in nodes_result:
                    labels = record["labels"]
                    props = record["properties"]
                    node_type = labels[0] if labels else "Node"
                    # 跳过APIInterface节点
                    if node_type == "APIInterface":
                        continue
                    node_id = f"{node_type}_{props.get('name', props.get('id', ''))}"
                    
                    node_data = {
                        "id": node_id,
                        "type": node_type,
                        "label": props.get("name", node_id),
                        "properties": props
                    }
                    nodes.append(node_data)
                    node_ids[node_id] = node_data
                
                # 只获取数据库元数据相关的关系（排除API接口依赖关系）
                if connection_id:
                    edges_query = """
                    MATCH (n1)-[r]->(n2)
                    WHERE n1.project_id = $project_id 
                      AND n2.project_id = $project_id
                      AND n1.connection_id = $connection_id
                      AND n2.connection_id = $connection_id
                      AND NOT 'APIInterface' IN labels(n1)
                      AND NOT 'APIInterface' IN labels(n2)
                      AND type(r) <> 'DEPENDS_ON'
                    RETURN 
                        n1.name as source_name,
                        labels(n1) as source_labels,
                        n2.name as target_name,
                        labels(n2) as target_labels,
                        type(r) as relationship_type,
                        properties(r) as properties
                    """
                    edges_result = session.run(edges_query, project_id=project_id, connection_id=connection_id)
                else:
                    edges_query = """
                    MATCH (n1)-[r]->(n2)
                    WHERE n1.project_id = $project_id 
                      AND n2.project_id = $project_id
                      AND NOT 'APIInterface' IN labels(n1)
                      AND NOT 'APIInterface' IN labels(n2)
                      AND type(r) <> 'DEPENDS_ON'
                    RETURN 
                        n1.name as source_name,
                        labels(n1) as source_labels,
                        n2.name as target_name,
                        labels(n2) as target_labels,
                        type(r) as relationship_type,
                        properties(r) as properties
                    """
                    edges_result = session.run(edges_query, project_id=project_id)
                
                edges = []
                
                for record in edges_result:
                    source_labels = record["source_labels"]
                    target_labels = record["target_labels"]
                    source_type = source_labels[0] if source_labels else "Node"
                    target_type = target_labels[0] if target_labels else "Node"
                    
                    # 跳过APIInterface相关的关系
                    if source_type == "APIInterface" or target_type == "APIInterface":
                        continue
                    
                    source_id = f"{source_type}_{record['source_name']}"
                    target_id = f"{target_type}_{record['target_name']}"
                    
                    # 确保source和target都在nodes中
                    if source_id not in node_ids or target_id not in node_ids:
                        continue
                    
                    edge_data = {
                        "source": source_id,
                        "target": target_id,
                        "type": record["relationship_type"],
                        "properties": record["properties"]
                    }
                    edges.append(edge_data)
                
                return {
                    "nodes": nodes,
                    "edges": edges
                }
        except Exception as e:
            # Neo4j连接失败时返回空数据，而不是抛出异常
            print(f"获取知识图谱数据失败（Neo4j可能不可用）: {e}")
            import traceback
            traceback.print_exc()
            return {
                "nodes": [],
                "edges": []
            }

