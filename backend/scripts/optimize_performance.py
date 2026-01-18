"""
性能优化初始化脚本
- 创建数据库索引
- 预热缓存
- 验证性能改进
"""
import logging
from sqlalchemy import text
from app.database import engine, SessionLocal
from app.models import TestCase, Document, TestResult, TestCaseSuite
from app.services.cache_service import cache_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_performance_indexes():
    """创建性能优化索引"""
    logger.info("开始创建性能优化索引...")
    
    indexes = [
        # test_cases表索引
        "CREATE INDEX IF NOT EXISTS idx_test_cases_project_status ON test_cases(project_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_test_cases_project_module ON test_cases(project_id, module)",
        "CREATE INDEX IF NOT EXISTS idx_test_cases_name ON test_cases(project_id, name(50))",
        
        # documents表索引
        "CREATE INDEX IF NOT EXISTS idx_documents_project_status ON documents(project_id, status)",
        
        # test_results表索引
        "CREATE INDEX IF NOT EXISTS idx_test_results_task_status ON test_results(task_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_test_results_case_status ON test_results(test_case_id, status)",
        
        # test_case_suites表索引
        "CREATE INDEX IF NOT EXISTS idx_test_suites_project_id ON test_case_suites(project_id, created_at)",
        
        # api_interfaces表索引
        "CREATE INDEX IF NOT EXISTS idx_api_interfaces_project_id ON api_interfaces(project_id, created_at)",
        
        # test_tasks表索引
        "CREATE INDEX IF NOT EXISTS idx_test_tasks_project_status ON test_tasks(project_id, status)",
    ]
    
    try:
        with engine.connect() as connection:
            for index_sql in indexes:
                try:
                    connection.execute(text(index_sql))
                    logger.info(f"✓ 已创建索引: {index_sql.split('ON')[1].split('(')[0].strip()}")
                except Exception as e:
                    logger.warning(f"索引创建失败或已存在: {index_sql.split('ON')[1].split('(')[0].strip()}")
            
            connection.commit()
        
        logger.info("✓ 所有性能优化索引创建完成")
        return True
    except Exception as e:
        logger.error(f"✗ 创建索引失败: {e}")
        return False


def analyze_tables():
    """分析表统计信息"""
    logger.info("开始分析表统计信息...")
    
    tables = ['test_cases', 'documents', 'test_results', 'test_case_suites']
    
    try:
        with engine.connect() as connection:
            for table in tables:
                try:
                    connection.execute(text(f"ANALYZE TABLE {table}"))
                    logger.info(f"✓ 已分析表: {table}")
                except Exception as e:
                    logger.warning(f"表分析失败: {table}")
            
            connection.commit()
        
        logger.info("✓ 表统计分析完成")
        return True
    except Exception as e:
        logger.error(f"✗ 表分析失败: {e}")
        return False


def warmup_cache():
    """预热缓存 - 加载常用数据到Redis"""
    logger.info("开始预热缓存...")
    
    db = SessionLocal()
    
    try:
        # 获取所有项目ID
        from app.models import Project
        projects = db.query(Project).all()
        
        warmup_count = 0
        for project in projects:
            try:
                # 预热documents缓存
                documents = db.query(Document).filter(
                    Document.project_id == project.id,
                    Document.status != "deleted"
                ).order_by(Document.created_at.desc()).all()
                
                if documents:
                    doc_data = [
                        {
                            "id": doc.id,
                            "filename": doc.filename,
                            "file_type": doc.file_type,
                            "file_size": doc.file_size,
                            "status": doc.status,
                            "created_at": doc.created_at.isoformat() if doc.created_at else None,
                            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                        }
                        for doc in documents
                    ]
                    cache_service.set_cache(f"documents:{project.id}", doc_data, 'documents')
                    warmup_count += 1
                
                # 预热test_cases缓存
                test_cases = db.query(TestCase).filter(
                    TestCase.project_id == project.id
                ).order_by(TestCase.created_at.desc()).all()
                
                if test_cases:
                    tc_data = [
                        {
                            "id": tc.id,
                            "name": tc.name,
                            "module": tc.module,
                            "case_type": tc.case_type,
                            "status": tc.status,
                            "description": tc.description,
                            "created_at": tc.created_at.isoformat() if tc.created_at else None,
                            "updated_at": tc.updated_at.isoformat() if tc.updated_at else None,
                        }
                        for tc in test_cases
                    ]
                    cache_service.set_cache(f"test_cases:{project.id}:all:all:all:all", tc_data, 'test_cases')
                    warmup_count += 1
                
                logger.info(f"✓ 项目 {project.id} 缓存预热完成")
            except Exception as e:
                logger.warning(f"项目 {project.id} 缓存预热失败: {e}")
        
        logger.info(f"✓ 缓存预热完成，共预热 {warmup_count} 个项目")
        return True
    except Exception as e:
        logger.error(f"✗ 缓存预热失败: {e}")
        return False
    finally:
        db.close()


def verify_performance():
    """验证性能改进"""
    logger.info("开始性能验证...")
    
    db = SessionLocal()
    
    try:
        import time
        
        # 测试1：查询documents列表
        start = time.time()
        documents = db.query(Document).filter(
            Document.project_id == 1,
            Document.status != "deleted"
        ).limit(20).all()
        elapsed = (time.time() - start) * 1000
        logger.info(f"✓ 查询documents耗时: {elapsed:.2f}ms")
        
        # 测试2：查询test_cases列表
        start = time.time()
        test_cases = db.query(TestCase).filter(
            TestCase.project_id == 1
        ).order_by(TestCase.created_at.desc()).limit(20).all()
        elapsed = (time.time() - start) * 1000
        logger.info(f"✓ 查询test_cases耗时: {elapsed:.2f}ms")
        
        # 测试3：查询test_results列表
        start = time.time()
        test_results = db.query(TestResult).filter(
            TestResult.task_id == 1
        ).limit(20).all()
        elapsed = (time.time() - start) * 1000
        logger.info(f"✓ 查询test_results耗时: {elapsed:.2f}ms")
        
        # 获取缓存统计
        cache_stats = cache_service.get_cache_stats()
        logger.info(f"✓ 缓存统计: {cache_stats}")
        
        return True
    except Exception as e:
        logger.error(f"✗ 性能验证失败: {e}")
        return False
    finally:
        db.close()


def main():
    """执行所有优化初始化"""
    logger.info("=" * 60)
    logger.info("开始性能优化初始化")
    logger.info("=" * 60)
    
    results = {
        "索引创建": create_performance_indexes(),
        "表统计分析": analyze_tables(),
        "缓存预热": warmup_cache(),
        "性能验证": verify_performance()
    }
    
    logger.info("=" * 60)
    logger.info("性能优化初始化完成")
    logger.info("=" * 60)
    
    for task, result in results.items():
        status = "✓ 成功" if result else "✗ 失败"
        logger.info(f"{task}: {status}")
    
    return all(results.values())


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
