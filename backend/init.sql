CREATE DATABASE IF NOT EXISTS api_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE api_test;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    user_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 文档表
CREATE TABLE IF NOT EXISTS documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size BIGINT,
    status VARCHAR(50) DEFAULT 'uploaded',
    parse_result LONGTEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 接口信息表
CREATE TABLE IF NOT EXISTS api_interfaces (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    name VARCHAR(200) NOT NULL,
    method VARCHAR(10) NOT NULL,
    url TEXT NOT NULL,
    description TEXT,
    headers TEXT,
    params TEXT,
    body TEXT,
    response_schema TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 文档解析的API接口表（存储从文档中提取的详细接口信息）
CREATE TABLE IF NOT EXISTS document_api_interfaces (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    project_id INT NOT NULL,
    -- 接口基本信息
    name VARCHAR(200) NOT NULL COMMENT '接口名称',
    method VARCHAR(10) NOT NULL DEFAULT 'GET' COMMENT 'HTTP方法',
    url TEXT NOT NULL COMMENT '完整URL',
    base_url VARCHAR(500) COMMENT 'Base URL',
    path VARCHAR(500) COMMENT '请求路径',
    service VARCHAR(200) COMMENT '服务名（如user.userLogin）',
    -- 请求信息
    headers LONGTEXT COMMENT '请求头（JSON格式）',
    params LONGTEXT COMMENT 'URL参数（JSON格式）',
    request_body LONGTEXT COMMENT '请求体（JSON格式）',
    -- 响应信息
    response_headers LONGTEXT COMMENT '响应头（JSON格式）',
    response_body LONGTEXT COMMENT '响应体（JSON格式）',
    response_schema LONGTEXT COMMENT '响应Schema（JSON格式）',
    status_code INT DEFAULT 200 COMMENT '响应状态码',
    -- 其他信息
    description TEXT COMMENT '接口描述',
    tags TEXT COMMENT '标签（JSON数组格式）',
    deprecated TINYINT(1) DEFAULT 0 COMMENT '是否废弃',
    version VARCHAR(50) COMMENT '接口版本（如V1.0, V2.0等）',
    xjid VARCHAR(50) COMMENT 'xjid字段（从测试环境获取）',
    -- 关联字段
    file_id VARCHAR(50) COMMENT '文件ID（对应Redis中的file_id）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    INDEX idx_document_id (document_id),
    INDEX idx_project_id (project_id),
    INDEX idx_file_id (file_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 测试用例表
CREATE TABLE IF NOT EXISTS test_cases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    api_interface_id INT,
    name VARCHAR(200) NOT NULL,
    case_type VARCHAR(50) DEFAULT 'pytest',
    module VARCHAR(100) COMMENT '模块分类',
    description TEXT,
    test_data TEXT,
    test_code TEXT COMMENT '生成的测试代码',
    assertions TEXT,
    dependencies TEXT,
    status VARCHAR(50) DEFAULT 'active' COMMENT 'active, generating, completed, failed',
    generation_task_id VARCHAR(100) COMMENT 'Celery任务ID',
    generation_progress INT DEFAULT 0 COMMENT '生成进度0-100',
    error_message TEXT COMMENT '生成错误信息',
    generation_checkpoint LONGTEXT COMMENT '生成断点续传数据（JSON格式）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (api_interface_id) REFERENCES api_interfaces(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 添加模块索引
CREATE INDEX idx_test_cases_module ON test_cases(module);
CREATE INDEX idx_test_cases_status ON test_cases(status);
-- 性能优化索引
CREATE INDEX IF NOT EXISTS idx_test_cases_project_status ON test_cases(project_id, status);
CREATE INDEX IF NOT EXISTS idx_test_cases_project_module ON test_cases(project_id, module);
CREATE INDEX IF NOT EXISTS idx_test_cases_name ON test_cases(project_id, name(50));

-- 测试用例集合表
CREATE TABLE IF NOT EXISTS test_case_suites (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    test_case_ids TEXT COMMENT 'JSON格式的用例ID列表',
    tags VARCHAR(500) COMMENT '标签，逗号分隔',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 测试环境表
CREATE TABLE IF NOT EXISTS test_environments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    name VARCHAR(100) NOT NULL COMMENT '环境名称：国内测试、国外测试、国内灰度、国外灰度',
    env_type VARCHAR(50) NOT NULL COMMENT 'test_cn, test_overseas, gray_cn, gray_overseas',
    base_url VARCHAR(500) NOT NULL COMMENT 'IP:port 或域名',
    login_username VARCHAR(100) COMMENT '登录用户名',
    login_password VARCHAR(255) COMMENT '登录密码',
    xjid VARCHAR(50) DEFAULT '30110' COMMENT 'xjid字段',
    description TEXT,
    is_default TINYINT(1) DEFAULT 0 COMMENT '是否默认环境',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 测试任务表
CREATE TABLE IF NOT EXISTS test_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    name VARCHAR(200) NOT NULL,
    scenario TEXT COMMENT '执行场景描述',
    task_type VARCHAR(50) DEFAULT 'immediate' COMMENT 'immediate, scheduled',
    execution_task_type VARCHAR(50) DEFAULT 'interface' COMMENT '执行任务类型: scenario(接口场景用例执行), interface(接口测试用例执行), performance(性能测试执行), other(其他)',
    cron_expression VARCHAR(100),
    test_case_ids TEXT COMMENT 'JSON格式的用例ID列表（已按依赖关系排序）',
    test_case_suite_id INT COMMENT '用例集合ID',
    environment_id INT COMMENT '测试环境ID',
    threads INT DEFAULT 10 COMMENT '性能测试线程数（5,10,20,50,100）',
    duration INT DEFAULT 5 COMMENT '性能测试执行时长（分钟，5,10,15,20,30）',
    dependency_analysis TEXT COMMENT '依赖关系分析结果，JSON格式',
    test_data_config TEXT COMMENT '测试数据配置，JSON格式',
    status VARCHAR(50) DEFAULT 'pending' COMMENT 'pending, running, paused, completed, failed, stopped',
    execution_task_id VARCHAR(100) COMMENT 'Celery执行任务ID',
    progress INT DEFAULT 0 COMMENT '执行进度0-100',
    execution_checkpoint LONGTEXT COMMENT '执行断点续传数据（JSON格式）',
    total_cases INT DEFAULT 0 COMMENT '总用例数',
    passed_cases INT DEFAULT 0 COMMENT '通过用例数',
    failed_cases INT DEFAULT 0 COMMENT '失败用例数',
    skipped_cases INT DEFAULT 0 COMMENT '跳过用例数',
    retry_count INT DEFAULT 0 COMMENT '重试次数',
    max_retries INT DEFAULT 3 COMMENT '最大重试次数',
    executed_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    paused_at TIMESTAMP NULL COMMENT '暂停时间',
    error_message TEXT COMMENT '错误信息',
    result_summary TEXT COMMENT '结果摘要',
    allure_report_path VARCHAR(500) COMMENT 'Allure报告路径',
    jtl_report_path VARCHAR(500) COMMENT 'JTL报告路径（HTML）',
    performance_analysis LONGTEXT COMMENT '性能分析结果（DeepSeek分析）',
    performance_report_html LONGTEXT COMMENT '性能分析报告HTML（包含图表）',
    execution_logs LONGTEXT COMMENT '执行日志',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (test_case_suite_id) REFERENCES test_case_suites(id) ON DELETE SET NULL,
    FOREIGN KEY (environment_id) REFERENCES test_environments(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 添加索引
CREATE INDEX idx_test_case_suites_project_id ON test_case_suites(project_id);
CREATE INDEX idx_test_environments_project_id ON test_environments(project_id);
CREATE INDEX idx_test_tasks_project_id ON test_tasks(project_id);
CREATE INDEX idx_test_tasks_status ON test_tasks(status);
CREATE INDEX idx_test_tasks_environment_id ON test_tasks(environment_id);

-- 测试结果表
CREATE TABLE IF NOT EXISTS test_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_id INT NOT NULL,
    test_case_id INT NOT NULL,
    status VARCHAR(50) NOT NULL COMMENT 'passed, failed, skipped, error',
    request_data TEXT COMMENT '请求数据，JSON格式',
    response_data TEXT COMMENT '响应数据，JSON格式',
    assertions_result TEXT COMMENT '断言结果，JSON格式',
    error_message TEXT COMMENT '错误信息',
    execution_time DECIMAL(10, 3) COMMENT '执行耗时（秒）',
    request_size INT COMMENT '请求大小（字节）',
    response_size INT COMMENT '响应大小（字节）',
    status_code INT COMMENT 'HTTP状态码',
    performance_metrics TEXT COMMENT '性能指标，JSON格式',
    failure_analysis TEXT COMMENT '失败分析结果，JSON格式',
    ai_suggestions TEXT COMMENT 'AI优化建议，JSON格式',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES test_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (test_case_id) REFERENCES test_cases(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 添加索引
CREATE INDEX idx_test_results_task_id ON test_results(task_id);
CREATE INDEX idx_test_results_status ON test_results(status);
CREATE INDEX idx_test_results_created_at ON test_results(created_at);

-- 测试用例调试记录表
CREATE TABLE IF NOT EXISTS test_debug_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    test_case_id INT NOT NULL,
    environment_id INT,
    task_id VARCHAR(100) COMMENT 'Celery任务ID',
    execution_status VARCHAR(50) DEFAULT 'pending' COMMENT '执行状态: pending, running, success, failed',
    execution_result TEXT COMMENT '执行结果摘要',
    debug_logs LONGTEXT COMMENT '调试日志（完整输出）',
    error_message TEXT COMMENT '错误信息',
    execution_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '执行时间',
    duration INT COMMENT '执行耗时（秒）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_test_case_id (test_case_id),
    INDEX idx_environment_id (environment_id),
    INDEX idx_task_id (task_id),
    INDEX idx_execution_time (execution_time),
    FOREIGN KEY (test_case_id) REFERENCES test_cases(id) ON DELETE CASCADE,
    FOREIGN KEY (environment_id) REFERENCES test_environments(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试用例调试记录表';

-- 数据库连接配置表
CREATE TABLE IF NOT EXISTS db_connections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    db_type VARCHAR(50) NOT NULL,
    host VARCHAR(200) NOT NULL,
    port INT NOT NULL,
    database_name VARCHAR(100) NOT NULL,
    username VARCHAR(100) NOT NULL,
    password VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'inactive',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 向量文档表（用于RAG检索）
CREATE TABLE IF NOT EXISTS vector_documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_index INT NOT NULL,
    vector_id VARCHAR(100),
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 表元数据表
CREATE TABLE IF NOT EXISTS table_metadata (
    id INT AUTO_INCREMENT PRIMARY KEY,
    db_connection_id INT NOT NULL,
    table_name VARCHAR(200) NOT NULL,
    table_comment TEXT COMMENT '表的含义/注释',
    primary_keys TEXT COMMENT '主键列表，JSON格式',
    indexes TEXT COMMENT '索引信息，JSON格式',
    foreign_keys TEXT COMMENT '外键信息，JSON格式',
    column_count INT DEFAULT 0,
    row_count BIGINT DEFAULT 0,
    metadata TEXT COMMENT '额外元数据，JSON格式',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (db_connection_id) REFERENCES db_connections(id) ON DELETE CASCADE,
    UNIQUE KEY uk_table (db_connection_id, table_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 字段元数据表
CREATE TABLE IF NOT EXISTS column_metadata (
    id INT AUTO_INCREMENT PRIMARY KEY,
    table_metadata_id INT NOT NULL,
    column_name VARCHAR(200) NOT NULL,
    column_comment TEXT COMMENT '字段含义/注释',
    data_type VARCHAR(100) NOT NULL,
    is_nullable VARCHAR(10) DEFAULT 'YES',
    default_value TEXT,
    is_primary_key TINYINT(1) DEFAULT 0,
    is_foreign_key TINYINT(1) DEFAULT 0,
    auto_increment TINYINT(1) DEFAULT 0,
    position INT COMMENT '字段位置',
    metadata TEXT COMMENT '额外元数据，JSON格式',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (table_metadata_id) REFERENCES table_metadata(id) ON DELETE CASCADE,
    UNIQUE KEY uk_column (table_metadata_id, column_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 表关系表
CREATE TABLE IF NOT EXISTS table_relationships (
    id INT AUTO_INCREMENT PRIMARY KEY,
    db_connection_id INT NOT NULL,
    source_table_id INT NOT NULL,
    target_table_id INT NOT NULL,
    relationship_type VARCHAR(50) NOT NULL COMMENT '关系类型: has_a, is_a, depend_on, foreign_key',
    relationship_name VARCHAR(200) COMMENT '关系名称',
    foreign_key_columns TEXT COMMENT '外键字段，JSON格式',
    referred_columns TEXT COMMENT '引用字段，JSON格式',
    description TEXT COMMENT '关系描述',
    cypher_query TEXT COMMENT 'Cypher查询语句',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (db_connection_id) REFERENCES db_connections(id) ON DELETE CASCADE,
    FOREIGN KEY (source_table_id) REFERENCES table_metadata(id) ON DELETE CASCADE,
    FOREIGN KEY (target_table_id) REFERENCES table_metadata(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 创建索引
CREATE INDEX idx_projects_user_id ON projects(user_id);
CREATE INDEX idx_documents_project_id ON documents(project_id);
-- 文档表性能优化索引
CREATE INDEX IF NOT EXISTS idx_documents_project_status ON documents(project_id, status);
CREATE INDEX idx_api_interfaces_project_id ON api_interfaces(project_id);
-- API接口表性能优化索引
CREATE INDEX IF NOT EXISTS idx_api_interfaces_project_id_perf ON api_interfaces(project_id, created_at);
CREATE INDEX idx_test_cases_project_id ON test_cases(project_id);
CREATE INDEX idx_test_cases_api_interface_id ON test_cases(api_interface_id);
CREATE INDEX idx_test_tasks_project_id ON test_tasks(project_id);
-- 测试任务表性能优化索引
CREATE INDEX IF NOT EXISTS idx_test_tasks_project_status ON test_tasks(project_id, status);
CREATE INDEX idx_test_results_task_id ON test_results(task_id);
-- 测试结果表性能优化索引
CREATE INDEX IF NOT EXISTS idx_test_results_task_status ON test_results(task_id, status);
CREATE INDEX IF NOT EXISTS idx_test_results_case_status ON test_results(test_case_id, status);
CREATE INDEX idx_test_results_test_case_id ON test_results(test_case_id);
-- 测试用例集合表性能优化索引
CREATE INDEX IF NOT EXISTS idx_test_suites_project_id ON test_case_suites(project_id, created_at);
CREATE INDEX idx_table_metadata_db_connection_id ON table_metadata(db_connection_id);
CREATE INDEX idx_column_metadata_table_metadata_id ON column_metadata(table_metadata_id);
CREATE INDEX idx_table_relationships_db_connection_id ON table_relationships(db_connection_id);
CREATE INDEX idx_table_relationships_source_table_id ON table_relationships(source_table_id);
CREATE INDEX idx_table_relationships_target_table_id ON table_relationships(target_table_id);

-- API文档快照表
CREATE TABLE IF NOT EXISTS api_document_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    document_id INT NOT NULL,
    snapshot_data TEXT COMMENT '快照数据，JSON格式存储接口列表',
    version VARCHAR(50) COMMENT '版本号',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- API变更历史表
CREATE TABLE IF NOT EXISTS api_change_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    snapshot_id INT NOT NULL,
    old_snapshot_id INT COMMENT '旧快照ID',
    change_type VARCHAR(50) NOT NULL COMMENT '变更类型: added, deleted, modified',
    change_summary TEXT COMMENT '变更摘要，JSON格式',
    affected_interfaces TEXT COMMENT '受影响的接口ID列表，JSON格式',
    change_level VARCHAR(20) COMMENT '变更级别: low, medium, high, breaking',
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (snapshot_id) REFERENCES api_document_snapshots(id) ON DELETE CASCADE,
    FOREIGN KEY (old_snapshot_id) REFERENCES api_document_snapshots(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 更新建议表
CREATE TABLE IF NOT EXISTS update_suggestions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    change_history_id INT NOT NULL,
    test_case_id INT NOT NULL,
    strategy VARCHAR(50) NOT NULL COMMENT '更新策略: regenerate, incremental',
    reasoning TEXT COMMENT '策略选择理由',
    update_plan TEXT COMMENT '更新计划，JSON格式',
    manual_interventions TEXT COMMENT '需要人工介入的部分，JSON格式',
    estimated_effort VARCHAR(20) COMMENT '预估工作量: low, medium, high',
    automation_rate DECIMAL(5, 2) COMMENT '自动化率，0-1之间',
    status VARCHAR(50) DEFAULT 'pending' COMMENT '状态: pending, applied, rejected, ignored',
    applied_at TIMESTAMP COMMENT '应用时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (change_history_id) REFERENCES api_change_history(id) ON DELETE CASCADE,
    FOREIGN KEY (test_case_id) REFERENCES test_cases(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 添加索引
CREATE INDEX idx_api_document_snapshots_project_id ON api_document_snapshots(project_id);
CREATE INDEX idx_api_document_snapshots_document_id ON api_document_snapshots(document_id);
CREATE INDEX idx_api_change_history_project_id ON api_change_history(project_id);
CREATE INDEX idx_api_change_history_snapshot_id ON api_change_history(snapshot_id);
CREATE INDEX idx_api_change_history_old_snapshot_id ON api_change_history(old_snapshot_id);
CREATE INDEX idx_update_suggestions_change_history_id ON update_suggestions(change_history_id);
CREATE INDEX idx_update_suggestions_test_case_id ON update_suggestions(test_case_id);
CREATE INDEX idx_update_suggestions_status ON update_suggestions(status);


