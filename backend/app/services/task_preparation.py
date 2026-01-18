from typing import List, Dict, Any, Optional
import json
from sqlalchemy.orm import Session

from app.models import TestCase, APIInterface, DBConnection
from app.services.dependency_analyzer import DependencyAnalyzer
from app.services.smart_test_data_generator import SmartTestDataGenerator
from app.services.db_service import DatabaseService


class TaskPreparationService:
    """任务准备服务：分析依赖关系、构造测试数据"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.dependency_analyzer = DependencyAnalyzer(db_session)
        self.data_generator = SmartTestDataGenerator()
        self.db_service = DatabaseService()
    
    def prepare_task(
        self,
        test_case_ids: List[int],
        project_id: int,
        connection_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        准备任务：分析依赖关系、构造测试数据
        
        Args:
            test_case_ids: 测试用例ID列表
            project_id: 项目ID
            connection_id: 数据库连接ID（可选）
        
        Returns:
            准备结果，包含排序后的用例ID、依赖关系、测试数据配置
        """
        # 1. 获取测试用例和对应的API接口
        test_cases = self.db.query(TestCase).filter(
            TestCase.id.in_(test_case_ids),
            TestCase.project_id == project_id
        ).all()
        
        if not test_cases:
            raise ValueError("没有找到有效的测试用例")
        
        # 获取API接口信息
        api_interface_ids = [tc.api_interface_id for tc in test_cases if tc.api_interface_id]
        api_interfaces = self.db.query(APIInterface).filter(
            APIInterface.id.in_(api_interface_ids),
            APIInterface.project_id == project_id
        ).all()
        
        if not api_interfaces:
            raise ValueError("没有找到有效的API接口")
        
        # 构建API接口列表（统一使用模型字段）
        api_list = [
            {
                "id": api.id,
                "name": api.name,
                "method": api.method,
                "url": api.url,  # 统一使用url字段
                "params": json.loads(api.params) if api.params else {},
                "body": json.loads(api.body) if api.body else {},
                "response_schema": json.loads(api.response_schema) if api.response_schema else {},
                "headers": json.loads(api.headers) if api.headers else {},
                "description": api.description or ""
            }
            for api in api_interfaces
        ]
        
        # 2. 分析接口依赖关系
        if not connection_id:
            from app.models import DBConnection as DBConnModel
            db_connection = self.db.query(DBConnModel).filter(
                DBConnModel.project_id == project_id
            ).first()
            if db_connection:
                connection_id = db_connection.id
        
        dependency_graph = None
        if connection_id:
            try:
                dependency_graph = self.dependency_analyzer.analyze_api_dependencies(
                    api_list, connection_id, project_id
                )
            except Exception as e:
                print(f"依赖关系分析失败: {e}")
        
        # 3. 根据依赖关系排序用例
        sorted_case_ids = self._sort_test_cases_by_dependency(
            test_cases, api_list, dependency_graph
        )
        
        # 4. 为每个用例构造测试数据
        test_data_config = {}
        
        # 获取数据库连接用于数据生成
        db_connection = None
        if connection_id:
            from app.models import DBConnection as DBConnModel
            db_connection = self.db.query(DBConnModel).filter(
                DBConnModel.id == connection_id
            ).first()
        
        engine = None
        if db_connection:
            try:
                engine = self.db_service.connect_database(
                    db_connection.db_type,
                    db_connection.host,
                    db_connection.port,
                    db_connection.database_name,
                    db_connection.username,
                    db_connection.password
                )
            except Exception as e:
                print(f"连接数据库失败: {e}")
        
        # 存储已提取的数据（用于数据传递）
        extracted_data = {}
        
        for case_id in sorted_case_ids:
            test_case = next((tc for tc in test_cases if tc.id == case_id), None)
            if not test_case or not test_case.api_interface_id:
                continue
            
            api_interface = next((api for api in api_interfaces if api.id == test_case.api_interface_id), None)
            if not api_interface:
                continue
            
            # 构建API信息（统一使用模型字段）
            api_info = {
                "id": api_interface.id,
                "name": api_interface.name,
                "method": api_interface.method,
                "url": api_interface.url,  # 统一使用url字段
                "params": json.loads(api_interface.params) if api_interface.params else {},
                "body": json.loads(api_interface.body) if api_interface.body else {},
                "response_schema": json.loads(api_interface.response_schema) if api_interface.response_schema else {},
                "headers": json.loads(api_interface.headers) if api_interface.headers else {},
                "description": api_interface.description or ""
            }
            
            # 生成测试数据
            try:
                case_test_data = self.data_generator.generate_test_data_for_api(
                    api_info=api_info,
                    connection_id=connection_id if connection_id else None,
                    project_id=project_id,
                    use_real_data=bool(connection_id and engine),
                    db_session=self.db,
                    engine=engine
                )
                
                # 使用已提取的数据填充（如token）
                if extracted_data.get("authToken"):
                    if isinstance(case_test_data.get("headers"), dict):
                        case_test_data["headers"]["Authorization"] = f"Bearer {extracted_data['authToken']}"
                
                # 填充提取的ID
                for key in ["newPostId", "deviceId", "courseId", "familyId"]:
                    if extracted_data.get(key):
                        snake_key = self._camel_to_snake(key)
                        if isinstance(case_test_data.get("body"), dict):
                            case_test_data["body"][snake_key] = extracted_data[key]
                            if f"{snake_key}_id" in case_test_data["body"]:
                                case_test_data["body"][f"{snake_key}_id"] = extracted_data[key]
                
                test_data_config[str(case_id)] = case_test_data
                
                # 预测会提取的数据（用于后续用例）
                # 这里只是预测，实际执行时会从响应中提取
                api_name = api_info.get("name", "").lower()
                api_url = api_info.get("url", "").lower()
                
                if "登录" in api_name or "login" in api_url:
                    # 登录接口会提取token
                    extracted_data["authToken"] = "TOKEN_PLACEHOLDER"
                
                # 创建类接口会提取ID
                if any(keyword in api_name for keyword in ["创建", "create", "add", "post"]) or \
                   any(keyword in api_url for keyword in ["/create", "/add", "/post"]):
                    if "文章" in api_name or "post" in api_name:
                        extracted_data["newPostId"] = "POST_ID_PLACEHOLDER"
                    elif "评论" in api_name or "comment" in api_name:
                        extracted_data["newCommentId"] = "COMMENT_ID_PLACEHOLDER"
                    elif "设备" in api_name or "device" in api_name:
                        extracted_data["deviceId"] = "DEVICE_ID_PLACEHOLDER"
                    elif "课程" in api_name or "course" in api_name:
                        extracted_data["courseId"] = "COURSE_ID_PLACEHOLDER"
                    elif "家庭" in api_name or "family" in api_name:
                        extracted_data["familyId"] = "FAMILY_ID_PLACEHOLDER"
            
            except Exception as e:
                print(f"为用例 {case_id} 生成测试数据失败: {e}")
                test_data_config[str(case_id)] = {}
        
        # 5. 构建依赖关系摘要
        dependency_summary = self._build_dependency_summary(
            sorted_case_ids, test_cases, api_list, dependency_graph
        )
        
        return {
            "sorted_case_ids": sorted_case_ids,
            "dependency_analysis": dependency_summary,
            "test_data_config": test_data_config,
            "total_cases": len(sorted_case_ids),
            "dependency_graph": dependency_graph.get("edges", []) if dependency_graph else []
        }
    
    def _sort_test_cases_by_dependency(
        self,
        test_cases: List[TestCase],
        api_list: List[Dict[str, Any]],
        dependency_graph: Optional[Dict[str, Any]]
    ) -> List[int]:
        """根据依赖关系排序测试用例"""
        if not dependency_graph or not dependency_graph.get("nodes"):
            # 如果没有依赖关系，返回原始顺序
            return [tc.id for tc in test_cases]
        
        # 构建用例ID到API ID的映射
        case_to_api = {tc.id: tc.api_interface_id for tc in test_cases if tc.api_interface_id}
        
        # 构建依赖关系图（用例级别）
        dependencies = {}  # {case_id: [dependent_case_ids]}
        dependents = {}  # {case_id: [dependency_case_ids]}
        
        for node in dependency_graph.get("nodes", []):
            api_id = node.get("id")
            case_id = next((cid for cid, aid in case_to_api.items() if aid == api_id), None)
            
            if not case_id:
                continue
            
            if case_id not in dependencies:
                dependencies[case_id] = []
            if case_id not in dependents:
                dependents[case_id] = []
            
            # 找出依赖的API
            all_deps = node.get("data_flow_deps", []) + node.get("business_logic_deps", [])
            for dep in all_deps:
                dep_api_id = dep.get("api_id")
                dep_case_id = next((cid for cid, aid in case_to_api.items() if aid == dep_api_id), None)
                
                if dep_case_id and dep_case_id != case_id:
                    if dep_case_id not in dependencies[case_id]:
                        dependencies[case_id].append(dep_case_id)
                    if case_id not in dependents[dep_case_id]:
                        dependents[dep_case_id].append(case_id)
        
        # 拓扑排序
        sorted_ids = []
        remaining = set(case_to_api.keys())
        in_degree = {cid: len(dependencies.get(cid, [])) for cid in remaining}
        
        # 找出所有入度为0的节点（没有依赖的用例）
        queue = [cid for cid, degree in in_degree.items() if degree == 0]
        
        while queue:
            case_id = queue.pop(0)
            if case_id in remaining:
                sorted_ids.append(case_id)
                remaining.remove(case_id)
                
                # 更新依赖此用例的其他用例的入度
                for dependent_id in dependents.get(case_id, []):
                    if dependent_id in in_degree:
                        in_degree[dependent_id] -= 1
                        if in_degree[dependent_id] == 0:
                            queue.append(dependent_id)
        
        # 添加剩余的用例（可能存在循环依赖）
        sorted_ids.extend(list(remaining))
        
        return sorted_ids if sorted_ids else [tc.id for tc in test_cases]
    
    def _build_dependency_summary(
        self,
        sorted_case_ids: List[int],
        test_cases: List[TestCase],
        api_list: List[Dict[str, Any]],
        dependency_graph: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """构建依赖关系摘要"""
        summary = {
            "total_cases": len(sorted_case_ids),
            "dependency_count": 0,
            "dependencies": []
        }
        
        if not dependency_graph:
            return summary
        
        # 构建用例ID到API ID的映射
        case_to_api = {tc.id: tc.api_interface_id for tc in test_cases if tc.api_interface_id}
        api_to_case = {api_id: case_id for case_id, api_id in case_to_api.items()}
        
        # 找出依赖关系
        for edge in dependency_graph.get("edges", []):
            source_api_id = edge.get("source")
            target_api_id = edge.get("target")
            
            source_case_id = api_to_case.get(source_api_id)
            target_case_id = api_to_case.get(target_api_id)
            
            if source_case_id and target_case_id:
                summary["dependencies"].append({
                    "source_case_id": source_case_id,
                    "source_case_name": next((tc.name for tc in test_cases if tc.id == source_case_id), ""),
                    "target_case_id": target_case_id,
                    "target_case_name": next((tc.name for tc in test_cases if tc.id == target_case_id), ""),
                    "dependency_type": edge.get("type", "unknown"),
                    "description": edge.get("description", "")
                })
                summary["dependency_count"] += 1
        
        return summary
    
    def _camel_to_snake(self, name: str) -> str:
        """驼峰转下划线"""
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

