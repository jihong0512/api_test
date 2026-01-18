from sqlalchemy import Column, Integer, String, Text, BigInteger, ForeignKey, TIMESTAMP, DECIMAL, Boolean
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    projects = relationship("Project", back_populates="user")


class Project(Base):
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="projects")
    documents = relationship("Document", back_populates="project")
    api_interfaces = relationship("APIInterface", back_populates="project")
    test_cases = relationship("TestCase", back_populates="project")


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger)
    status = Column(String(50), default="uploaded")
    parse_result = Column(LONGTEXT)  # 使用LONGTEXT支持更大的数据
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    project = relationship("Project", back_populates="documents")


class APIInterface(Base):
    __tablename__ = "api_interfaces"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    method = Column(String(10), nullable=False)
    url = Column(Text, nullable=False)
    description = Column(Text)
    headers = Column(Text)
    params = Column(Text)
    body = Column(Text)
    response_schema = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    project = relationship("Project", back_populates="api_interfaces")
    test_cases = relationship("TestCase", back_populates="api_interface")


class DocumentAPIInterface(Base):
    """文档解析的API接口信息表（存储从文档中提取的详细接口信息）"""
    __tablename__ = "document_api_interfaces"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # 接口基本信息
    name = Column(String(200), nullable=False, comment="接口名称")
    method = Column(String(10), nullable=False, default="GET", comment="HTTP方法")
    url = Column(Text, nullable=False, comment="完整URL")
    base_url = Column(String(500), comment="Base URL")
    path = Column(String(500), comment="请求路径")
    service = Column(String(200), comment="服务名（如user.userLogin）")
    
    # 请求信息
    headers = Column(LONGTEXT, comment="请求头（JSON格式）")
    params = Column(LONGTEXT, comment="URL参数（JSON格式）")
    request_body = Column(LONGTEXT, comment="请求体（JSON格式）")
    
    # 响应信息
    response_headers = Column(LONGTEXT, comment="响应头（JSON格式）")
    response_body = Column(LONGTEXT, comment="响应体（JSON格式）")
    response_schema = Column(LONGTEXT, comment="响应Schema（JSON格式）")
    status_code = Column(Integer, default=200, comment="响应状态码")
    
    # 其他信息
    description = Column(Text, comment="接口描述")
    tags = Column(Text, comment="标签（JSON数组格式）")
    deprecated = Column(Boolean, default=False, comment="是否废弃")
    version = Column(String(50), comment="接口版本（如V1.0, V2.0等）")
    xjid = Column(String(50), comment="xjid字段（从测试环境获取）")
    
    # 关联字段
    file_id = Column(String(50), index=True, comment="文件ID（对应Redis中的file_id）")
    
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # 关系
    document = relationship("Document", backref="api_interfaces")
    project = relationship("Project")


class TestCase(Base):
    __tablename__ = "test_cases"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    api_interface_id = Column(Integer, ForeignKey("api_interfaces.id", ondelete="SET NULL"))
    name = Column(String(200), nullable=False)
    case_type = Column(String(50), default="pytest")  # pytest, jmeter
    module = Column(String(100), comment="模块分类")
    description = Column(Text)
    test_data = Column(Text)
    test_code = Column(Text, comment="生成的测试代码")
    assertions = Column(Text)
    dependencies = Column(Text)
    status = Column(String(50), default="active")  # active, generating, completed, failed
    generation_task_id = Column(String(100), comment="Celery任务ID")
    generation_progress = Column(Integer, default=0, comment="生成进度0-100")
    generation_checkpoint = Column(LONGTEXT, comment="生成断点续传数据（JSON格式）")
    error_message = Column(Text, comment="生成错误信息")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    project = relationship("Project", back_populates="test_cases")
    api_interface = relationship("APIInterface", back_populates="test_cases")


class TestEnvironment(Base):
    """测试环境配置"""
    __tablename__ = "test_environments"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)  # 环境名称：国内测试、国外测试、国内灰度、国外灰度
    env_type = Column(String(50), nullable=False)  # test_cn, test_overseas, gray_cn, gray_overseas
    base_url = Column(String(500), nullable=False)  # IP:port 或域名
    login_username = Column(String(100), comment="登录用户名")
    login_password = Column(String(255), comment="登录密码")
    xjid = Column(String(50), default="30110", comment="xjid字段")
    description = Column(Text)
    is_default = Column(Boolean, default=False)  # 是否默认环境
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


class TestCaseSuite(Base):
    """测试用例集合"""
    __tablename__ = "test_case_suites"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    test_case_ids = Column(Text, comment="JSON格式的用例ID列表")
    tags = Column(String(500), comment="标签，逗号分隔")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


class TestDebugRecord(Base):
    """测试用例调试记录"""
    __tablename__ = "test_debug_records"
    
    id = Column(Integer, primary_key=True, index=True)
    test_case_id = Column(Integer, ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    environment_id = Column(Integer, ForeignKey("test_environments.id", ondelete="SET NULL"), index=True)
    task_id = Column(String(100), comment="Celery任务ID", index=True)
    execution_status = Column(String(50), default="pending", comment="执行状态: pending, running, success, failed")
    execution_result = Column(Text, comment="执行结果摘要")
    debug_logs = Column(LONGTEXT, comment="调试日志（完整输出）")
    error_message = Column(Text, comment="错误信息")
    execution_time = Column(TIMESTAMP, server_default=func.now(), index=True, comment="执行时间")
    duration = Column(Integer, comment="执行耗时（秒）")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    test_case = relationship("TestCase", backref="debug_records")
    environment = relationship("TestEnvironment")


class TestTask(Base):
    __tablename__ = "test_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    scenario = Column(Text, comment="执行场景描述")
    task_type = Column(String(50), default="immediate")  # immediate, scheduled
    execution_task_type = Column(String(50), default="interface", comment="执行任务类型: scenario(接口场景用例执行), interface(接口测试用例执行), performance(性能测试执行), other(其他)")
    cron_expression = Column(String(100))
    test_case_ids = Column(Text, comment="JSON格式的用例ID列表（已按依赖关系排序）")
    test_case_suite_id = Column(Integer, ForeignKey("test_case_suites.id", ondelete="SET NULL"), comment="用例集合ID")
    environment_id = Column(Integer, ForeignKey("test_environments.id", ondelete="SET NULL"), comment="测试环境ID")
    threads = Column(Integer, default=10, comment="性能测试线程数（5,10,20,50,100）")
    duration = Column(Integer, default=5, comment="性能测试执行时长（分钟，5,10,15,20,30）")
    dependency_analysis = Column(Text, comment="依赖关系分析结果，JSON格式")
    test_data_config = Column(Text, comment="测试数据配置，JSON格式")
    status = Column(String(50), default="pending")  # pending, running, paused, completed, failed, stopped
    execution_task_id = Column(String(100), comment="Celery执行任务ID")
    progress = Column(Integer, default=0, comment="执行进度0-100")
    execution_checkpoint = Column(LONGTEXT, comment="执行断点续传数据（JSON格式）")
    total_cases = Column(Integer, default=0, comment="总用例数")
    passed_cases = Column(Integer, default=0, comment="通过用例数")
    failed_cases = Column(Integer, default=0, comment="失败用例数")
    skipped_cases = Column(Integer, default=0, comment="跳过用例数")
    retry_count = Column(Integer, default=0, comment="重试次数")
    max_retries = Column(Integer, default=3, comment="最大重试次数")
    executed_at = Column(TIMESTAMP)
    completed_at = Column(TIMESTAMP)
    paused_at = Column(TIMESTAMP, comment="暂停时间")
    error_message = Column(Text, comment="错误信息")
    result_summary = Column(Text, comment="结果摘要")
    allure_report_path = Column(String(500), comment="Allure报告路径")
    jtl_report_path = Column(String(500), comment="JTL报告路径（HTML）")
    performance_analysis = Column(LONGTEXT, comment="性能分析结果（DeepSeek分析）")
    performance_report_html = Column(LONGTEXT, comment="性能分析报告HTML（包含图表）")
    execution_logs = Column(LONGTEXT, comment="执行日志")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    environment = relationship("TestEnvironment")


class TestResult(Base):
    __tablename__ = "test_results"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("test_tasks.id", ondelete="CASCADE"), nullable=False)
    test_case_id = Column(Integer, ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), nullable=False)  # passed, failed, skipped, error
    request_data = Column(Text, comment="请求数据，JSON格式")
    response_data = Column(Text, comment="响应数据，JSON格式")
    assertions_result = Column(Text, comment="断言结果，JSON格式")
    error_message = Column(Text, comment="错误信息")
    execution_time = Column(DECIMAL(10, 3), comment="执行耗时（秒）")
    request_size = Column(Integer, comment="请求大小（字节）")
    response_size = Column(Integer, comment="响应大小（字节）")
    status_code = Column(Integer, comment="HTTP状态码")
    performance_metrics = Column(Text, comment="性能指标，JSON格式")
    failure_analysis = Column(Text, comment="失败分析结果，JSON格式")
    ai_suggestions = Column(Text, comment="AI优化建议，JSON格式")
    created_at = Column(TIMESTAMP, server_default=func.now())


class DBConnection(Base):
    __tablename__ = "db_connections"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    db_type = Column(String(50), nullable=False)
    host = Column(String(200), nullable=False)
    port = Column(Integer, nullable=False)
    database_name = Column(String(100), nullable=False)
    username = Column(String(100), nullable=False)
    password = Column(String(255), nullable=False)
    status = Column(String(50), default="inactive")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


class VectorDocument(Base):
    __tablename__ = "vector_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    vector_id = Column(String(100))
    metadata_json = Column(Text, name="metadata", comment="元数据，JSON格式")
    created_at = Column(TIMESTAMP, server_default=func.now())


class TableMetadata(Base):
    """表元数据"""
    __tablename__ = "table_metadata"
    
    id = Column(Integer, primary_key=True, index=True)
    db_connection_id = Column(Integer, ForeignKey("db_connections.id", ondelete="CASCADE"), nullable=False)
    table_name = Column(String(200), nullable=False)
    table_comment = Column(Text, comment="表的含义/注释")
    primary_keys = Column(Text, comment="主键列表，JSON格式")
    indexes = Column(Text, comment="索引信息，JSON格式")
    foreign_keys = Column(Text, comment="外键信息，JSON格式")
    column_count = Column(Integer, default=0)
    row_count = Column(BigInteger, default=0)
    metadata_json = Column(Text, name="metadata", comment="额外元数据，JSON格式")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    columns = relationship("ColumnMetadata", back_populates="table", cascade="all, delete-orphan")
    relationships = relationship("TableRelationship", foreign_keys="TableRelationship.source_table_id", back_populates="source_table")


class ColumnMetadata(Base):
    """字段元数据"""
    __tablename__ = "column_metadata"
    
    id = Column(Integer, primary_key=True, index=True)
    table_metadata_id = Column(Integer, ForeignKey("table_metadata.id", ondelete="CASCADE"), nullable=False)
    column_name = Column(String(200), nullable=False)
    column_comment = Column(Text, comment="字段含义/注释")
    data_type = Column(String(100), nullable=False)
    is_nullable = Column(String(10), default="YES")
    default_value = Column(Text)
    is_primary_key = Column(Boolean, default=False)
    is_foreign_key = Column(Boolean, default=False)
    auto_increment = Column(Boolean, default=False)
    position = Column(Integer, comment="字段位置")
    metadata_json = Column(Text, name="metadata", comment="额外元数据，JSON格式")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    table = relationship("TableMetadata", back_populates="columns")


class TableRelationship(Base):
    """表关系"""
    __tablename__ = "table_relationships"
    
    id = Column(Integer, primary_key=True, index=True)
    db_connection_id = Column(Integer, ForeignKey("db_connections.id", ondelete="CASCADE"), nullable=False)
    source_table_id = Column(Integer, ForeignKey("table_metadata.id", ondelete="CASCADE"), nullable=False)
    target_table_id = Column(Integer, ForeignKey("table_metadata.id", ondelete="CASCADE"), nullable=False)
    relationship_type = Column(String(50), nullable=False, comment="关系类型: has_a, is_a, depend_on, foreign_key")
    relationship_name = Column(String(200), comment="关系名称")
    foreign_key_columns = Column(Text, comment="外键字段，JSON格式")
    referred_columns = Column(Text, comment="引用字段，JSON格式")
    description = Column(Text, comment="关系描述")
    cypher_query = Column(Text, comment="Cypher查询语句")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    source_table = relationship("TableMetadata", foreign_keys=[source_table_id], back_populates="relationships")


class APIDocumentSnapshot(Base):
    """API文档快照，用于记录文档版本"""
    __tablename__ = "api_document_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    snapshot_data = Column(Text, comment="快照数据，JSON格式存储接口列表")
    version = Column(String(50), comment="版本号")
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    project = relationship("Project")
    document = relationship("Document")
    changes = relationship("APIChangeHistory", foreign_keys="APIChangeHistory.snapshot_id", back_populates="snapshot")


class APIChangeHistory(Base):
    """API变更历史"""
    __tablename__ = "api_change_history"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    snapshot_id = Column(Integer, ForeignKey("api_document_snapshots.id", ondelete="CASCADE"))
    old_snapshot_id = Column(Integer, ForeignKey("api_document_snapshots.id", ondelete="SET NULL"), comment="旧快照ID")
    change_type = Column(String(50), nullable=False, comment="变更类型: added, deleted, modified")
    change_summary = Column(Text, comment="变更摘要，JSON格式")
    affected_interfaces = Column(Text, comment="受影响的接口ID列表，JSON格式")
    change_level = Column(String(20), comment="变更级别: low, medium, high, breaking")
    detected_at = Column(TIMESTAMP, server_default=func.now())
    
    project = relationship("Project")
    snapshot = relationship("APIDocumentSnapshot", foreign_keys=[snapshot_id])
    suggestions = relationship("UpdateSuggestion", back_populates="change_history")


class UpdateSuggestion(Base):
    """更新建议"""
    __tablename__ = "update_suggestions"
    
    id = Column(Integer, primary_key=True, index=True)
    change_history_id = Column(Integer, ForeignKey("api_change_history.id", ondelete="CASCADE"), nullable=False)
    test_case_id = Column(Integer, ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False)
    strategy = Column(String(50), nullable=False, comment="更新策略: regenerate, incremental")
    reasoning = Column(Text, comment="策略选择理由")
    update_plan = Column(Text, comment="更新计划，JSON格式")
    manual_interventions = Column(Text, comment="需要人工介入的部分，JSON格式")
    estimated_effort = Column(String(20), comment="预估工作量: low, medium, high")
    automation_rate = Column(DECIMAL(5, 2), comment="自动化率，0-1之间")
    status = Column(String(50), default="pending", comment="状态: pending, applied, rejected, ignored")
    applied_at = Column(TIMESTAMP, comment="应用时间")
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    change_history = relationship("APIChangeHistory", back_populates="suggestions")
    test_case = relationship("TestCase")


