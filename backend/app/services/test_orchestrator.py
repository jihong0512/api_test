"""
测试编排服务
统一管理整个测试流程：文档解析 → 接口创建 → 用例生成 → 数据准备 → 测试执行 → 结果分析
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
import json

from app.models import (
    Project, Document, APIInterface, TestCase, TestTask,
    TestEnvironment, TestCaseSuite, TestResult
)
from app.services.document_parser import DocumentParser
from app.services.test_case_generator import PytestCaseGenerator, JMeterCaseGenerator
from app.services.task_preparation import TaskPreparationService
from app.services.report_generator import AllureReportGenerator


class TestOrchestrator:
    """测试编排服务：串联整个测试流程"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.document_parser = DocumentParser()
        self.pytest_generator = PytestCaseGenerator()
        self.jmeter_generator = JMeterCaseGenerator()
        self.task_preparation = TaskPreparationService(db_session)  # 传入db_session
        self.report_generator = AllureReportGenerator()
    
    async def full_test_flow(
        self,
        project_id: int,
        document_id: Optional[int] = None,
        document_file_path: Optional[str] = None,
        environment_id: Optional[int] = None,
        test_suite_id: Optional[int] = None,
        auto_execute: bool = False
    ) -> Dict[str, Any]:
        """
        完整的测试流程编排
        
        Args:
            project_id: 项目ID
            document_id: 文档ID（如果已有文档）
            document_file_path: 文档文件路径（如果要上传新文档）
            environment_id: 测试环境ID
            test_suite_id: 测试套件ID（可选）
            auto_execute: 是否自动执行测试
        
        Returns:
            流程执行结果
        """
        result = {
            "project_id": project_id,
            "steps": [],
            "errors": [],
            "test_case_ids": [],
            "task_id": None
        }
        
        try:
            # 步骤1: 文档解析（如果需要）
            if document_file_path:
                step1 = await self._parse_document(project_id, document_file_path)
                result["steps"].append(step1)
                if step1.get("error"):
                    result["errors"].append(step1["error"])
                    return result
            
            # 步骤2: 获取API接口
            api_interfaces = self._get_api_interfaces(project_id)
            if not api_interfaces:
                result["errors"].append("项目中没有API接口")
                return result
            
            result["steps"].append({
                "step": "获取API接口",
                "count": len(api_interfaces),
                "status": "success"
            })
            
            # 步骤3: 生成测试用例
            test_cases = await self._generate_test_cases(
                project_id, api_interfaces, case_type="pytest"
            )
            result["test_case_ids"] = [tc["id"] for tc in test_cases]
            result["steps"].append({
                "step": "生成测试用例",
                "count": len(test_cases),
                "status": "success"
            })
            
            # 步骤4: 准备测试数据（如果提供了套件或环境）
            if result["test_case_ids"]:
                preparation_result = await self._prepare_test_data(
                    project_id,
                    result["test_case_ids"],
                    test_suite_id,
                    environment_id
                )
                result["steps"].append(preparation_result)
            
            # 步骤5: 执行测试（如果启用）
            if auto_execute and environment_id:
                task = await self._execute_test_task(
                    project_id,
                    result["test_case_ids"],
                    environment_id
                )
                result["task_id"] = task.get("id")
                result["steps"].append({
                    "step": "执行测试任务",
                    "task_id": task.get("id"),
                    "status": "success"
                })
            
            result["status"] = "success"
            return result
        
        except Exception as e:
            result["errors"].append(str(e))
            result["status"] = "error"
            return result
    
    async def _parse_document(
        self,
        project_id: int,
        file_path: str
    ) -> Dict[str, Any]:
        """解析文档"""
        try:
            file_ext = file_path.split('.')[-1].lower()
            parsed_data = await self.document_parser.parse(file_path, file_ext)
            api_interfaces = self.document_parser.extract_api_interfaces(parsed_data)
            
            # 保存接口到数据库
            created_count = 0
            for iface_data in api_interfaces:
                # 检查是否已存在
                existing = self.db.query(APIInterface).filter(
                    APIInterface.project_id == project_id,
                    APIInterface.url == iface_data.get("url", ""),
                    APIInterface.method == iface_data.get("method", "GET")
                ).first()
                
                if not existing:
                    db_interface = APIInterface(
                        project_id=project_id,
                        name=iface_data.get("name", ""),
                        method=iface_data.get("method", "GET"),
                        url=iface_data.get("url", ""),
                        description=iface_data.get("description", ""),
                        headers=json.dumps(iface_data.get("headers", {}), ensure_ascii=False) if iface_data.get("headers") else None,
                        params=json.dumps(iface_data.get("params", {}), ensure_ascii=False) if iface_data.get("params") else None,
                        body=json.dumps(iface_data.get("body", {}), ensure_ascii=False) if iface_data.get("body") else None,
                        response_schema=json.dumps(iface_data.get("response_schema", {}), ensure_ascii=False) if iface_data.get("response_schema") else None
                    )
                    self.db.add(db_interface)
                    created_count += 1
            
            self.db.commit()
            
            return {
                "step": "解析文档",
                "count": created_count,
                "status": "success"
            }
        except Exception as e:
            return {
                "step": "解析文档",
                "status": "error",
                "error": str(e)
            }
    
    def _get_api_interfaces(self, project_id: int) -> List[APIInterface]:
        """获取项目的API接口"""
        return self.db.query(APIInterface).filter(
            APIInterface.project_id == project_id
        ).all()
    
    async def _generate_test_cases(
        self,
        project_id: int,
        api_interfaces: List[APIInterface],
        case_type: str = "pytest"
    ) -> List[Dict[str, Any]]:
        """生成测试用例"""
        test_cases = []
        
        for api_interface in api_interfaces:
            # 检查是否已有测试用例
            existing = self.db.query(TestCase).filter(
                TestCase.project_id == project_id,
                TestCase.api_interface_id == api_interface.id,
                TestCase.case_type == case_type
            ).first()
            
            if existing:
                test_cases.append({
                    "id": existing.id,
                    "name": existing.name,
                    "status": "existing"
                })
                continue
            
            # 构建API接口数据
            api_data = {
                "id": api_interface.id,
                "name": api_interface.name,
                "method": api_interface.method,
                "url": api_interface.url,
                "params": json.loads(api_interface.params) if api_interface.params else {},
                "headers": json.loads(api_interface.headers) if api_interface.headers else {},
                "body": json.loads(api_interface.body) if api_interface.body else {},
                "response_schema": json.loads(api_interface.response_schema) if api_interface.response_schema else {},
                "description": api_interface.description or ""
            }
            
            # 生成测试代码
            if case_type == "pytest":
                generator = self.pytest_generator
            else:
                generator = self.jmeter_generator
            
            test_code = generator.generate_test_case(
                api_interface=api_data,
                test_data={},
                extracted_data=None
            )
            
            # 创建测试用例
            test_case = TestCase(
                project_id=project_id,
                api_interface_id=api_interface.id,
                name=f"{api_interface.name}_测试用例",
                case_type=case_type,
                test_code=test_code,
                status="completed"
            )
            self.db.add(test_case)
            self.db.commit()
            self.db.refresh(test_case)
            
            test_cases.append({
                "id": test_case.id,
                "name": test_case.name,
                "status": "created"
            })
        
        return test_cases
    
    async def _prepare_test_data(
        self,
        project_id: int,
        test_case_ids: List[int],
        test_suite_id: Optional[int] = None,
        environment_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """准备测试数据"""
        try:
            # 检查是否有数据库连接用于数据生成
            from app.models import DBConnection
            db_connection = self.db.query(DBConnection).filter(
                DBConnection.project_id == project_id
            ).first()
            connection_id = db_connection.id if db_connection else None
            
            # 使用prepare_task方法（传入正确的参数）
            preparation_result = self.task_preparation.prepare_task(
                test_case_ids=test_case_ids,
                project_id=project_id,
                connection_id=connection_id
            )
            
            return {
                "step": "准备测试数据",
                "status": "success",
                "dependency_analysis": preparation_result.get("dependency_analysis"),
                "sorted_case_ids": preparation_result.get("sorted_case_ids"),
                "test_data_config": preparation_result.get("test_data_config")
            }
        except Exception as e:
            return {
                "step": "准备测试数据",
                "status": "error",
                "error": str(e)
            }
    
    async def _execute_test_task(
        self,
        project_id: int,
        test_case_ids: List[int],
        environment_id: int
    ) -> Dict[str, Any]:
        """执行测试任务"""
        # 这里应该调用celery任务，简化处理
        test_task = TestTask(
            project_id=project_id,
            name="自动执行测试任务",
            task_type="immediate",
            test_case_ids=json.dumps(test_case_ids, ensure_ascii=False),
            environment_id=environment_id,
            status="pending"
        )
        self.db.add(test_task)
        self.db.commit()
        self.db.refresh(test_task)
        
        # 实际应该异步执行
        # from app.celery_task_executor import execute_test_task
        # execute_test_task.delay(test_task.id)
        
        return {
            "id": test_task.id,
            "name": test_task.name,
            "status": test_task.status
        }
    
    def get_test_flow_status(
        self,
        project_id: int
    ) -> Dict[str, Any]:
        """获取测试流程状态"""
        # 统计项目中的接口、用例、任务数量
        interface_count = self.db.query(APIInterface).filter(
            APIInterface.project_id == project_id
        ).count()
        
        test_case_count = self.db.query(TestCase).filter(
            TestCase.project_id == project_id
        ).count()
        
        task_count = self.db.query(TestTask).filter(
            TestTask.project_id == project_id
        ).count()
        
        completed_task_count = self.db.query(TestTask).filter(
            TestTask.project_id == project_id,
            TestTask.status == "completed"
        ).count()
        
        return {
            "project_id": project_id,
            "interface_count": interface_count,
            "test_case_count": test_case_count,
            "task_count": task_count,
            "completed_task_count": completed_task_count,
            "completion_rate": completed_task_count / task_count if task_count > 0 else 0
        }
