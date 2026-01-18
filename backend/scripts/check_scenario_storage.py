#!/usr/bin/env python3
"""
检查场景用例集的存储情况（Redis、Neo4j、数据库）
"""
import sys
import os
import json
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Project, TestCaseSuite
from app.config import settings
import redis
import os

def check_scenario_storage(project_id: int):
    """检查场景用例集的存储情况"""
    # 如果在Docker容器内运行，使用容器内的配置
    if os.getenv('MYSQL_HOST') == 'mysql':
        # Docker环境，使用环境变量
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        mysql_host = os.getenv('MYSQL_HOST', 'mysql')
        mysql_port = int(os.getenv('MYSQL_PORT', 3306))
        mysql_user = os.getenv('MYSQL_USER', 'root')
        mysql_password = os.getenv('MYSQL_PASSWORD', '123456')
        mysql_database = os.getenv('MYSQL_DATABASE', 'api_test')
        
        database_url = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"
        engine = create_engine(database_url)
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
    else:
        # 本地环境，使用默认配置
        db: Session = SessionLocal()
    
    try:
        print(f"\n{'='*60}")
        print(f"检查项目 {project_id} 的场景用例集存储情况")
        print(f"{'='*60}\n")
        
        # 1. 检查数据库中的场景用例集
        print("1. 检查数据库中的场景用例集:")
        suites = db.query(TestCaseSuite).filter(
            TestCaseSuite.project_id == project_id
        ).all()
        print(f"   数据库中的场景数: {len(suites)}")
        if suites:
            for i, suite in enumerate(suites, 1):
                case_ids = json.loads(suite.test_case_ids) if suite.test_case_ids else []
                print(f"   场景 {i}: {suite.name}")
                print(f"     - 接口数: {len(case_ids)}")
                print(f"     - 描述: {suite.description or '无'}")
                print(f"     - 创建时间: {suite.created_at}")
                if case_ids:
                    print(f"     - 接口ID列表: {case_ids[:5]}..." if len(case_ids) > 5 else f"     - 接口ID列表: {case_ids}")
        else:
            print("   ❌ 数据库中没有场景用例集")
        
        # 2. 检查Redis中的场景数据
        print(f"\n2. 检查Redis中的场景数据:")
        try:
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                encoding='utf-8'
            )
            
            redis_key = f"project:{project_id}:scenarios"
            scenarios_data_str = redis_client.get(redis_key)
            
            if scenarios_data_str:
                scenarios_data = json.loads(scenarios_data_str)
                print(f"   ✓ Redis中有场景数据")
                print(f"     - 场景总数: {scenarios_data.get('total_count', 0)}")
                print(f"     - 接口总数: {scenarios_data.get('interfaces_count', 0)}")
                print(f"     - 登录接口: {'存在' if scenarios_data.get('login_interface') else '不存在'}")
                
                scenarios = scenarios_data.get('scenarios', [])
                if scenarios:
                    print(f"     - 场景列表:")
                    for i, scenario in enumerate(scenarios[:5], 1):
                        print(f"       场景 {i}: {scenario.get('scenario_name', 'N/A')}")
                        print(f"         - 依赖链长度: {len(scenario.get('dependency_chain', []))}")
                        print(f"         - 依赖关系数: {scenario.get('dependencies_count', 0)}")
            else:
                print(f"   ❌ Redis中没有场景数据 (key: {redis_key})")
                
                # 检查其他可能的key
                pattern = f"project:{project_id}:*"
                keys = redis_client.keys(pattern)
                print(f"   Redis中项目相关的key:")
                for key in keys[:10]:
                    print(f"     - {key}")
                    
        except Exception as e:
            print(f"   ❌ 连接Redis失败: {e}")
        
        # 3. 检查Neo4j中的依赖关系数据
        print(f"\n3. 检查Neo4j中的依赖关系数据:")
        try:
            from app.services.db_service import DatabaseService
            db_service = DatabaseService()
            
            with db_service.neo4j_driver.session() as session:
                # 查询接口节点
                node_query = """
                MATCH (n:APIInterface)
                WHERE n.project_id = $project_id
                RETURN count(n) as node_count
                """
                node_result = session.run(node_query, project_id=project_id)
                node_count = node_result.single()['node_count'] if node_result.peek() else 0
                print(f"   Neo4j中的接口节点数: {node_count}")
                
                # 查询依赖关系
                edge_query = """
                MATCH (source:APIInterface)-[r:DEPENDS_ON]->(target:APIInterface)
                WHERE source.project_id = $project_id AND target.project_id = $project_id
                RETURN count(r) as edge_count
                """
                edge_result = session.run(edge_query, project_id=project_id)
                edge_count = edge_result.single()['edge_count'] if edge_result.peek() else 0
                print(f"   Neo4j中的依赖关系数: {edge_count}")
                
                if node_count == 0 and edge_count == 0:
                    print(f"   ❌ Neo4j中没有依赖分析数据")
                else:
                    print(f"   ✓ Neo4j中有依赖分析数据")
                    
        except Exception as e:
            print(f"   ❌ 连接Neo4j失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 4. 检查Redis中的依赖关系备份
        print(f"\n4. 检查Redis中的依赖关系备份:")
        try:
            redis_key = f"project:{project_id}:dependency_graph"
            graph_data_str = redis_client.get(redis_key)
            
            if graph_data_str:
                graph_data = json.loads(graph_data_str)
                nodes = graph_data.get('nodes', [])
                edges = graph_data.get('edges', [])
                print(f"   ✓ Redis中有依赖关系备份")
                print(f"     - 节点数: {len(nodes)}")
                print(f"     - 边数: {len(edges)}")
            else:
                print(f"   ❌ Redis中没有依赖关系备份 (key: {redis_key})")
        except Exception as e:
            print(f"   ❌ 检查Redis备份失败: {e}")
        
        # 5. 总结
        print(f"\n{'='*60}")
        print(f"诊断总结:")
        print(f"{'='*60}")
        print(f"数据库场景数: {len(suites)}")
        
        # 检查是否有数据但不一致
        if len(suites) == 0:
            print(f"\n❌ 问题：数据库中没有场景用例集")
            print(f"可能原因：")
            print(f"  1. 依赖分析未完成")
            print(f"  2. 场景生成逻辑未执行")
            print(f"  3. 所有场景都被过滤掉了")
            print(f"  4. 存储时出现错误")
        else:
            print(f"\n✓ 数据库中有 {len(suites)} 个场景用例集")
            print(f"建议检查：")
            print(f"  1. 前端是否正确调用API")
            print(f"  2. API返回的数据格式是否正确")
            print(f"  3. 前端是否正确解析和显示数据")
        
    except Exception as e:
        print(f"\n❌ 诊断过程中出错: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python check_scenario_storage.py <project_id>")
        sys.exit(1)
    
    project_id = int(sys.argv[1])
    check_scenario_storage(project_id)

