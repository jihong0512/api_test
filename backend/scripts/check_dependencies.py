#!/usr/bin/env python3
"""
检查Neo4j和Redis中的接口依赖关系数据
"""

import sys
import os
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.services.db_service import DatabaseService
from app.config import settings
import redis

# Redis连接
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    encoding='utf-8'
)

def check_neo4j_dependencies(project_id: int):
    """检查Neo4j中的依赖关系"""
    print("=" * 60)
    print(f"检查Neo4j中的依赖关系（project_id: {project_id}）")
    print("=" * 60)
    
    try:
        db_service = DatabaseService()
        session = db_service._get_neo4j_session()
        
        with session as neo4j_session:
            # 检查节点数量
            nodes_result = neo4j_session.run("""
                MATCH (api:APIInterface {project_id: $project_id})
                RETURN count(api) as node_count
            """, project_id=project_id)
            
            node_count = nodes_result.single()['node_count']
            print(f"\n节点数量: {node_count}")
            
            # 检查边数量
            edges_result = neo4j_session.run("""
                MATCH (source:APIInterface {project_id: $project_id})-[r:DEPENDS_ON]->(target:APIInterface {project_id: $project_id})
                RETURN count(r) as edge_count
            """, project_id=project_id)
            
            edge_count = edges_result.single()['edge_count']
            print(f"依赖关系边数量: {edge_count}")
            
            if edge_count > 0:
                # 显示前10条依赖关系
                print("\n前10条依赖关系:")
                edges_detail = neo4j_session.run("""
                    MATCH (source:APIInterface {project_id: $project_id})-[r:DEPENDS_ON]->(target:APIInterface {project_id: $project_id})
                    RETURN source.id as source_id, source.name as source_name, 
                           target.id as target_id, target.name as target_name,
                           r.type as type, r.description as description
                    LIMIT 10
                """, project_id=project_id)
                
                for i, record in enumerate(edges_detail, 1):
                    print(f"  {i}. {record['source_name']} ({record['source_id']}) -> {record['target_name']} ({record['target_id']})")
                    print(f"     类型: {record.get('type', 'N/A')}, 描述: {record.get('description', 'N/A')}")
            else:
                print("\n⚠️  没有找到依赖关系边！")
            
            # 检查是否有孤立节点（没有边的节点）
            isolated_nodes = neo4j_session.run("""
                MATCH (api:APIInterface {project_id: $project_id})
                WHERE NOT (api)-[:DEPENDS_ON]->() AND NOT ()-[:DEPENDS_ON]->(api)
                RETURN count(api) as isolated_count
            """, project_id=project_id)
            
            isolated_count = isolated_nodes.single()['isolated_count']
            if isolated_count > 0:
                print(f"\n⚠️  有 {isolated_count} 个孤立节点（没有依赖关系）")
            
        return node_count, edge_count
        
    except Exception as e:
        print(f"❌ 检查Neo4j失败: {e}")
        import traceback
        traceback.print_exc()
        return 0, 0


def check_redis_dependencies(project_id: int):
    """检查Redis中的依赖关系"""
    print("\n" + "=" * 60)
    print(f"检查Redis中的依赖关系（project_id: {project_id}）")
    print("=" * 60)
    
    try:
        # 检查依赖关系图
        dependency_key = f"dependency_graph:project:{project_id}"
        graph_data = redis_client.get(dependency_key)
        
        if graph_data:
            graph = json.loads(graph_data)
            nodes = graph.get('nodes', [])
            edges = graph.get('edges', [])
            
            print(f"\n节点数量: {len(nodes)}")
            print(f"依赖关系边数量: {len(edges)}")
            
            if edges:
                print("\n前10条依赖关系:")
                for i, edge in enumerate(edges[:10], 1):
                    source_id = edge.get('source', 'N/A')
                    target_id = edge.get('target', 'N/A')
                    edge_type = edge.get('type', 'N/A')
                    description = edge.get('description', 'N/A')
                    print(f"  {i}. {source_id} -> {target_id}")
                    print(f"     类型: {edge_type}, 描述: {description}")
            else:
                print("\n⚠️  没有找到依赖关系边！")
        else:
            print(f"\n⚠️  Redis中没有找到依赖关系图（key: {dependency_key}）")
            
            # 检查其他可能的key
            pattern = f"*project:{project_id}*"
            keys = redis_client.keys(pattern)
            if keys:
                print(f"\n找到 {len(keys)} 个相关key:")
                for key in keys[:10]:
                    print(f"  - {key}")
        
        return len(nodes) if graph_data else 0, len(edges) if graph_data else 0
        
    except Exception as e:
        print(f"❌ 检查Redis失败: {e}")
        import traceback
        traceback.print_exc()
        return 0, 0


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法: python check_dependencies.py <project_id>")
        sys.exit(1)
    
    project_id = int(sys.argv[1])
    
    print("\n" + "=" * 60)
    print("接口依赖关系数据检查工具")
    print("=" * 60)
    
    # 检查Neo4j
    neo4j_nodes, neo4j_edges = check_neo4j_dependencies(project_id)
    
    # 检查Redis
    redis_nodes, redis_edges = check_redis_dependencies(project_id)
    
    # 总结
    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)
    print(f"Neo4j: {neo4j_nodes} 个节点, {neo4j_edges} 条边")
    print(f"Redis: {redis_nodes} 个节点, {redis_edges} 条边")
    
    if neo4j_edges == 0 and redis_edges == 0:
        print("\n❌ 警告：Neo4j和Redis中都没有依赖关系边！")
        print("   可能的原因：")
        print("   1. 依赖关系没有正确生成")
        print("   2. 依赖关系没有正确保存到Neo4j/Redis")
        print("   3. 接口分组后每组只有1个接口（没有依赖关系）")
    elif neo4j_edges > 0:
        print("\n✅ Neo4j中有依赖关系数据")
    elif redis_edges > 0:
        print("\n✅ Redis中有依赖关系数据（但Neo4j中没有）")


if __name__ == "__main__":
    main()





