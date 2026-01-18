from typing import Dict, Any, List, Optional, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
import json

from app.config import settings
from app.services.llm_service import LLMService
from app.services.rag_service import HybridRAGService
from app.services.db_service import DatabaseService


class AgentState(TypedDict):
    """Agent状态"""
    messages: List[BaseMessage]
    current_task: str
    parsed_interfaces: List[Dict[str, Any]]
    dependencies: Dict[str, Any]
    test_cases: List[Dict[str, Any]]
    context: Dict[str, Any]
    project_id: int


class InterfaceParserAgent:
    """接口解析Agent"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.rag_service = HybridRAGService()
    
    async def parse(self, state: AgentState) -> AgentState:
        """解析接口信息"""
        messages = state["messages"]
        current_task = state.get("current_task", "")
        project_id = state.get("project_id", 0)
        
        # 使用RAG检索相关上下文
        rag_results = await self.rag_service.hybrid_search(
            current_task,
            project_id,
            top_k=5
        )
        
        context = "\n".join([r.get("text", "") for r in rag_results])
        
        prompt = f"""
作为一个专业的API接口解析专家，请从以下上下文中提取和解析API接口信息。

任务描述：{current_task}

相关上下文：
{context}

请提取所有API接口信息，包括：
1. 接口名称
2. HTTP方法（GET/POST/PUT/DELETE等）
3. 接口URL
4. 请求参数（查询参数、路径参数、请求体）
5. 请求头
6. 响应格式
7. 接口描述

请以JSON格式输出解析结果，格式如下：
{{
    "interfaces": [
        {{
            "name": "接口名称",
            "method": "GET",
            "url": "/api/example",
            "headers": {{}},
            "params": {{}},
            "body": {{}},
            "description": "接口描述",
            "response_schema": {{}}
        }}
    ]
}}
"""
        
        result = await self.llm_service.chat(prompt, temperature=0.3)
        
        try:
            parsed_data = json.loads(result)
            interfaces = parsed_data.get("interfaces", [])
        except:
            interfaces = []
        
        state["parsed_interfaces"] = interfaces
        state["context"]["parser_context"] = context
        
        return state


class DependencyAnalyzerAgent:
    """依赖分析Agent"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.db_service = DatabaseService()
    
    async def analyze(self, state: AgentState) -> AgentState:
        """分析接口依赖关系"""
        interfaces = state.get("parsed_interfaces", [])
        project_id = state.get("project_id", 0)
        
        if not interfaces:
            state["dependencies"] = {}
            return state
        
        # 从知识图谱中获取数据关系
        relationships = self.db_service.get_table_relationships(project_id)
        
        # 构建依赖分析提示
        interfaces_json = json.dumps(interfaces, ensure_ascii=False, indent=2)
        relationships_json = json.dumps(relationships, ensure_ascii=False, indent=2)
        
        prompt = f"""
作为一个专业的API依赖分析专家，请分析以下接口之间的依赖关系。

接口列表：
{interfaces_json}

数据库关系：
{relationships_json}

请分析：
1. 接口之间的调用依赖（哪些接口依赖其他接口的响应）
2. 数据流依赖（参数如何在不同接口间传递）
3. 业务逻辑依赖（接口的执行顺序）
4. 数据依赖（接口参数与数据库表的关系）

请以JSON格式输出分析结果：
{{
    "call_dependencies": [
        {{"source": "接口A", "target": "接口B", "type": "response_dependency"}}
    ],
    "data_dependencies": [
        {{"source": "接口A", "target": "接口B", "data_flow": "A的response字段 -> B的request参数"}}
    ],
    "business_dependencies": [
        {{"interface": "接口A", "requires": ["接口B"], "order": 1}}
    ],
    "database_dependencies": [
        {{"interface": "接口A", "tables": ["table1", "table2"], "operation": "read/write"}}
    ]
}}
"""
        
        result = await self.llm_service.chat(prompt, temperature=0.3)
        
        try:
            dependencies = json.loads(result)
        except:
            dependencies = {}
        
        state["dependencies"] = dependencies
        
        return state


class TestCaseGeneratorAgent:
    """测试用例生成Agent"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.rag_service = HybridRAGService()
    
    async def generate(self, state: AgentState) -> AgentState:
        """生成测试用例"""
        interfaces = state.get("parsed_interfaces", [])
        dependencies = state.get("dependencies", {})
        project_id = state.get("project_id", 0)
        
        if not interfaces:
            state["test_cases"] = []
            return state
        
        # 使用GraphRAG获取上下文
        graph_rag_context = await self.rag_service.graph_rag_search(
            "测试用例生成",
            project_id,
            top_k=5
        )
        
        test_cases = []
        
        for interface in interfaces:
            # 构建测试用例生成提示
            interface_json = json.dumps(interface, ensure_ascii=False, indent=2)
            related_deps = [
                dep for dep in dependencies.get("call_dependencies", [])
                if dep.get("source") == interface.get("name") or dep.get("target") == interface.get("name")
            ]
            
            prompt = f"""
作为一个专业的测试用例生成专家，请为以下API接口生成测试用例。

接口信息：
{interface_json}

相关依赖：
{json.dumps(related_deps, ensure_ascii=False, indent=2)}

知识图谱上下文：
{graph_rag_context.get("graph_context", "")}

请生成以下类型的测试用例：
1. 正常场景测试用例
2. 边界值测试用例
3. 异常场景测试用例
4. 依赖场景测试用例（如果有依赖）

请以JSON格式输出：
{{
    "interface_name": "接口名称",
    "test_cases": [
        {{
            "name": "测试用例名称",
            "type": "normal|boundary|exception|dependency",
            "description": "测试用例描述",
            "test_data": {{
                "params": {{}},
                "headers": {{}},
                "body": {{}}
            }},
            "assertions": [
                {{"type": "status_code", "expected": 200}},
                {{"type": "contains", "field": "data", "value": ""}}
            ],
            "dependencies": ["依赖的接口名称"]
        }}
    ]
}}
"""
            
            result = await self.llm_service.chat(prompt, temperature=0.5)
            
            try:
                case_data = json.loads(result)
                test_cases.extend(case_data.get("test_cases", []))
            except:
                pass
        
        state["test_cases"] = test_cases
        
        return state


class MultiAgentOrchestrator:
    """多Agent协调器，使用LangGraph"""
    
    def __init__(self):
        self.parser_agent = InterfaceParserAgent()
        self.dependency_agent = DependencyAnalyzerAgent()
        self.testcase_agent = TestCaseGeneratorAgent()
        
        # 构建工作流图
        self.workflow = self._build_workflow()
    
    def _build_workflow(self) -> StateGraph:
        """构建Agent工作流"""
        workflow = StateGraph(AgentState)
        
        # 添加节点
        workflow.add_node("parser", self._parser_node)
        workflow.add_node("dependency_analyzer", self._dependency_node)
        workflow.add_node("testcase_generator", self._testcase_node)
        
        # 定义流程
        workflow.set_entry_point("parser")
        workflow.add_edge("parser", "dependency_analyzer")
        workflow.add_edge("dependency_analyzer", "testcase_generator")
        workflow.add_edge("testcase_generator", END)
        
        return workflow.compile()
    
    async def _parser_node(self, state: AgentState) -> AgentState:
        """解析节点"""
        return await self.parser_agent.parse(state)
    
    async def _dependency_node(self, state: AgentState) -> AgentState:
        """依赖分析节点"""
        return await self.dependency_agent.analyze(state)
    
    async def _testcase_node(self, state: AgentState) -> AgentState:
        """测试用例生成节点"""
        return await self.testcase_generator.generate(state)
    
    async def process(
        self,
        task: str,
        project_id: int,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """处理任务"""
        initial_state: AgentState = {
            "messages": [HumanMessage(content=task)],
            "current_task": task,
            "parsed_interfaces": [],
            "dependencies": {},
            "test_cases": [],
            "context": initial_context or {},
            "project_id": project_id
        }
        
        # 执行工作流
        final_state = await self.workflow.ainvoke(initial_state)
        
        return {
            "interfaces": final_state["parsed_interfaces"],
            "dependencies": final_state["dependencies"],
            "test_cases": final_state["test_cases"],
            "context": final_state["context"]
        }

