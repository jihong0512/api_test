from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import TestCase, TestEnvironment, TestDebugRecord, Document
from app.services.cache_service import cache_service
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import tempfile
import os
import re
import textwrap


def safe_update_failure_state(task_self, error_msg: str):
    """
    安全地更新任务失败状态，避免序列化错误
    
    Args:
        task_self: Celery任务实例（self）
        error_msg: 错误消息
    """
    # 确保错误消息是字符串格式，避免序列化问题
    safe_error_msg = str(error_msg) if error_msg else "未知错误"
    # 限制错误消息长度，避免过长导致序列化问题
    if len(safe_error_msg) > 1000:
        safe_error_msg = safe_error_msg[:1000] + "..."
    
    try:
        task_self.update_state(
            # 不直接置为FAILURE，避免Celery将meta视为异常结果而要求exc_type
            state='PROGRESS',
            meta={
                'progress': 0,
                'message': safe_error_msg,
                'error': safe_error_msg,
                'status': 'failed'
            }
        )
    except Exception as update_error:
        # 如果update_state失败，至少记录日志
        print(f"更新任务状态失败: {update_error}")
        import traceback
        traceback.print_exc()
    
    return safe_error_msg

# 在文件末尾添加新的Celery任务
@celery_app.task(bind=True, time_limit=2400, soft_time_limit=2300)  # 增加到40分钟
def generate_jmeter_performance_test_task(
    self,
    test_case_id: int,
    suite_id: int,
    project_id: int,
    interfaces_info: List[Dict[str, Any]],
    login_token: str,
    few_shot_interfaces: List[Dict[str, Any]],
    environment_info: Dict[str, Any],
    login_interface_info: Optional[Dict[str, Any]] = None,
    threads: int = 10
):
    """
    异步生成JMeter性能测试脚本任务（使用DeepSeek + RAG）
    
    Args:
        test_case_id: 测试用例ID
        suite_id: 测试用例集ID
        project_id: 项目ID
        interfaces_info: 场景接口信息列表（不包括登录接口）
        login_token: 登录token（可能是占位符{{TOKEN}}）
        few_shot_interfaces: Few-shot示例接口信息
        environment_info: 环境信息（base_url, xjid, username等）
        login_interface_info: 登录接口信息
        threads: 并发线程数（默认10）
    """
    db = SessionLocal()
    test_case = None
    generated_jmx = None
    full_prompt = ""
    
    try:
        from app.models import TestCase, TestCaseSuite
        
        # 获取测试用例记录
        test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
        if not test_case:
            raise Exception(f"测试用例不存在: {test_case_id}")
        # 确保用例类型标记为jmeter，便于前端过滤展示
        if test_case.case_type != 'jmeter':
            test_case.case_type = 'jmeter'
            db.commit()
        
        # 获取测试用例集
        suite = db.query(TestCaseSuite).filter(TestCaseSuite.id == suite_id).first()
        if not suite:
            raise Exception(f"测试用例集不存在: {suite_id}")
        
        # 检查是否有checkpoint（断点续传）
        checkpoint = None
        if test_case.generation_checkpoint:
            try:
                checkpoint = json.loads(test_case.generation_checkpoint)
                if checkpoint.get('generated_jmx'):
                    generated_jmx = checkpoint['generated_jmx']
                    full_prompt = checkpoint.get('prompt', '')
                    print(f"[性能测试用例生成] 从checkpoint恢复JMX，进度: {checkpoint.get('progress', 0)}%")
                    self.update_state(
                        state='PROGRESS',
                        meta={'progress': checkpoint.get('progress', 0), 'message': '从checkpoint恢复，正在清理JMX脚本...'}
                    )
                    test_case.generation_progress = checkpoint.get('progress', 0)
                    db.commit()
            except Exception as e:
                print(f"[性能测试用例生成] 解析checkpoint失败: {e}")
                checkpoint = None
        
        # 更新测试用例状态为"生成中"
        test_case.status = "generating"
        # 如果不是从checkpoint恢复，才重置进度
        if generated_jmx is None:
            test_case.generation_progress = 0
        test_case.error_message = None
        db.commit()
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 0, 'message': '开始生成性能测试用例...'}
        )
        
        # 新逻辑：接口分组 + 分批调用 + 合并（支持断点续传）
        # 仅当接口数量大于5时启用分组流程；否则走原单次生成逻辑
        enable_grouped = len(interfaces_info or []) > 5
        grouped_checkpoint = None
        if checkpoint and checkpoint.get('mode') == 'grouped':
            grouped_checkpoint = checkpoint
            enable_grouped = True

        def chunk_interfaces(interfaces: List[Dict[str, Any]], max_group_size: int = 6) -> List[List[Dict[str, Any]]]:
            groups = []
            current = []
            for item in interfaces:
                current.append(item)
                if len(current) >= max_group_size:
                    groups.append(current)
                    current = []
            if current:
                groups.append(current)
            return groups

        def build_skeleton_xml(suite_name: str, threads_count: int, env_info: Dict[str, Any], login_info: Optional[Dict[str, Any]]) -> str:
            # 构建符合标准格式的JMX骨架，包含Test Plan、Setup Thread Group（登录）、主Thread Group
            import xml.etree.ElementTree as ET
            from xml.dom import minidom

            # 解析环境信息
            base_url = env_info.get('base_url', '') if env_info else ''
            domain = ''
            protocol = 'https'
            if base_url:
                from urllib.parse import urlparse
                parsed = urlparse(base_url)
                domain = parsed.netloc or parsed.hostname or ''
                protocol = parsed.scheme or 'https'

            root = ET.Element("jmeterTestPlan", version="1.2", properties="5.0", jmeter="5.6.2")
            hash_tree = ET.SubElement(root, "hashTree")

            # TestPlan - 按照标准格式
            test_plan = ET.SubElement(hash_tree, "TestPlan", guiclass="TestPlanGui", testclass="TestPlan", testname=f"{suite_name}_性能测试", enabled="true")
            ET.SubElement(test_plan, "stringProp", name="TestPlan.comments").text = ""
            ET.SubElement(test_plan, "boolProp", name="TestPlan.functional_mode").text = "false"
            ET.SubElement(test_plan, "boolProp", name="TestPlan.tearDown_on_shutdown").text = "true"
            ET.SubElement(test_plan, "boolProp", name="TestPlan.serialize_threadgroups").text = "false"
            # 用户定义的变量
            user_vars = ET.SubElement(test_plan, "elementProp", name="TestPlan.user_defined_variables", elementType="Arguments", guiclass="ArgumentsPanel", testclass="Arguments", testname="用户定义的变量", enabled="true")
            ET.SubElement(user_vars, "collectionProp", name="Arguments.arguments")
            ET.SubElement(test_plan, "stringProp", name="TestPlan.user_define_classpath").text = ""

            # TestPlan 的 hashTree（容器）
            test_plan_tree = ET.SubElement(hash_tree, "hashTree")

            # Setup Thread Group（登录）
            setup_tg = ET.SubElement(test_plan_tree, "SetupThreadGroup", guiclass="SetupThreadGroupGui", testclass="SetupThreadGroup", testname="Setup Thread Group", enabled="true")
            ET.SubElement(setup_tg, "stringProp", name="ThreadGroup.on_sample_error").text = "continue"
            # LoopController - 使用标准格式（intProp而不是stringProp）
            setup_loop = ET.SubElement(setup_tg, "elementProp", name="ThreadGroup.main_controller", elementType="LoopController", guiclass="LoopControlPanel", testclass="LoopController", testname="循环控制器")
            ET.SubElement(setup_loop, "boolProp", name="LoopController.continue_forever").text = "false"
            ET.SubElement(setup_loop, "intProp", name="LoopController.loops").text = "1"
            ET.SubElement(setup_tg, "stringProp", name="ThreadGroup.num_threads").text = "1"
            ET.SubElement(setup_tg, "stringProp", name="ThreadGroup.ramp_time").text = "1"
            ET.SubElement(setup_tg, "boolProp", name="ThreadGroup.scheduler").text = "false"
            ET.SubElement(setup_tg, "stringProp", name="ThreadGroup.duration").text = ""
            ET.SubElement(setup_tg, "stringProp", name="ThreadGroup.delay").text = ""

            setup_tree = ET.SubElement(test_plan_tree, "hashTree")

            # 如果提供了登录接口信息，则在Setup中添加一个登录请求 + JSON Extractor 提取token
            if login_info:
                login_path = login_info.get('path') or login_info.get('url') or '/'
                if '?' in login_path:
                    login_path = login_path.split('?')[0]
                
                # HTTPSamplerProxy - 按照标准格式
                http = ET.SubElement(setup_tree, "HTTPSamplerProxy", guiclass="HttpTestSampleGui", testclass="HTTPSamplerProxy", testname=login_info.get('name', '用户登录'), enabled="true")
                # HTTPsampler.Arguments
                args_elem = ET.SubElement(http, "elementProp", name="HTTPsampler.Arguments", elementType="Arguments", guiclass="HTTPArgumentsPanel", testclass="Arguments", testname="用户定义的变量", enabled="true")
                args_collection = ET.SubElement(args_elem, "collectionProp", name="Arguments.arguments")
                
                # 如果有请求体，添加到Arguments中
                if login_info.get('request_body'):
                    arg_elem = ET.SubElement(args_collection, "elementProp", name="", elementType="HTTPArgument")
                    ET.SubElement(arg_elem, "boolProp", name="HTTPArgument.always_encode").text = "false"
                    ET.SubElement(arg_elem, "stringProp", name="Argument.value").text = login_info.get('request_body', '')
                    ET.SubElement(arg_elem, "stringProp", name="Argument.metadata").text = "="
                
                ET.SubElement(http, "stringProp", name="HTTPSampler.domain").text = domain
                ET.SubElement(http, "stringProp", name="HTTPSampler.port").text = ""
                ET.SubElement(http, "stringProp", name="HTTPSampler.protocol").text = protocol
                ET.SubElement(http, "stringProp", name="HTTPSampler.contentEncoding").text = ""
                ET.SubElement(http, "stringProp", name="HTTPSampler.path").text = login_path
                ET.SubElement(http, "stringProp", name="HTTPSampler.method").text = (login_info.get('method') or 'POST').upper()
                ET.SubElement(http, "boolProp", name="HTTPSampler.follow_redirects").text = "true"
                ET.SubElement(http, "boolProp", name="HTTPSampler.auto_redirects").text = "false"
                ET.SubElement(http, "boolProp", name="HTTPSampler.use_keepalive").text = "true"
                ET.SubElement(http, "boolProp", name="HTTPSampler.DO_MULTIPART_POST").text = "false"
                ET.SubElement(http, "stringProp", name="HTTPSampler.embedded_url_re").text = ""
                ET.SubElement(http, "stringProp", name="HTTPSampler.connect_timeout").text = ""
                ET.SubElement(http, "stringProp", name="HTTPSampler.response_timeout").text = ""

                http_ht = ET.SubElement(setup_tree, "hashTree")
                # HeaderManager
                header_mgr = ET.SubElement(http_ht, "HeaderManager", guiclass="HeaderPanel", testclass="HeaderManager", testname="HTTP信息头管理器", enabled="true")
                header_collection = ET.SubElement(header_mgr, "collectionProp", name="HeaderManager.headers")
                header_elem = ET.SubElement(header_collection, "elementProp", name="", elementType="Header")
                ET.SubElement(header_elem, "stringProp", name="Header.name").text = "Content-Type"
                ET.SubElement(header_elem, "stringProp", name="Header.value").text = "application/json"
                ET.SubElement(http_ht, "hashTree")
                
                # 提取token（JSONPostProcessor - 按照标准格式）
                json_extractor = ET.SubElement(http_ht, "JSONPostProcessor", guiclass="JSONPostProcessorGui", testclass="JSONPostProcessor", testname="JSON Extractor", enabled="true")
                ET.SubElement(json_extractor, "stringProp", name="JSONPostProcessor.referenceNames").text = "token"
                ET.SubElement(json_extractor, "stringProp", name="JSONPostProcessor.jsonPathExpr").text = "$.data.info.token"
                ET.SubElement(json_extractor, "stringProp", name="JSONPostProcessor.match_numbers").text = "0"
                ET.SubElement(json_extractor, "stringProp", name="JSONPostProcessor.defaultValues").text = ""
                ET.SubElement(json_extractor, "stringProp", name="JSONPostProcessor.compute_concat").text = "false"
                ET.SubElement(http_ht, "hashTree")
                
                # 备用方案：正则表达式提取器（如果JSON提取失败）
                regex_extractor = ET.SubElement(http_ht, "RegexExtractor", guiclass="RegexExtractorGui", testclass="RegexExtractor", testname="Regular Expression Extractor (Backup)", enabled="true")
                ET.SubElement(regex_extractor, "stringProp", name="RegexExtractor.useHeaders").text = "false"
                ET.SubElement(regex_extractor, "stringProp", name="RegexExtractor.refname").text = "token_backup"
                ET.SubElement(regex_extractor, "stringProp", name="RegexExtractor.regex").text = '"token"\s*:\s*"([^"]+)"'
                ET.SubElement(regex_extractor, "stringProp", name="RegexExtractor.template").text = "$1$"
                ET.SubElement(regex_extractor, "stringProp", name="RegexExtractor.default").text = ""
                ET.SubElement(regex_extractor, "stringProp", name="RegexExtractor.match_number").text = "1"
                ET.SubElement(http_ht, "hashTree")
                
                # 使用JSR223 PostProcessor来合并token（如果JSON提取失败，使用正则表达式提取的token）
                # 注意：PostProcessor在请求和提取器之后执行
                jsr223_postprocessor = ET.SubElement(http_ht, "JSR223PostProcessor", guiclass="TestBeanGUI", testclass="JSR223PostProcessor", testname="Token Fallback (JSR223)", enabled="true")
                ET.SubElement(jsr223_postprocessor, "stringProp", name="scriptLanguage").text = "groovy"
                ET.SubElement(jsr223_postprocessor, "stringProp", name="parameters").text = ""
                ET.SubElement(jsr223_postprocessor, "stringProp", name="filename").text = ""
                ET.SubElement(jsr223_postprocessor, "stringProp", name="cacheKey").text = "true"
                script_content = """// Token Fallback: 如果JSON提取失败，使用正则表达式提取的token
String token = vars.get("token");
if (token == null || token.isEmpty()) {
    String backupToken = vars.get("token_backup");
    if (backupToken != null && !backupToken.isEmpty()) {
        vars.put("token", backupToken);
        log.info("使用备用token提取方式，token长度: " + backupToken.length());
    } else {
        log.warn("警告: token和token_backup都为空，后续请求可能失败");
    }
} else {
    log.info("JSON提取token成功，token长度: " + token.length());
}"""
                ET.SubElement(jsr223_postprocessor, "stringProp", name="script").text = script_content
                ET.SubElement(http_ht, "hashTree")

            # 主Thread Group
            thread_group = ET.SubElement(test_plan_tree, "ThreadGroup", guiclass="ThreadGroupGui", testclass="ThreadGroup", testname="Thread Group", enabled="true")
            ET.SubElement(thread_group, "stringProp", name="ThreadGroup.on_sample_error").text = "continue"
            # LoopController - 使用标准格式，持续运行使用-1
            tg_loop = ET.SubElement(thread_group, "elementProp", name="ThreadGroup.main_controller", elementType="LoopController", guiclass="LoopControlPanel", testclass="LoopController", testname="循环控制器")
            ET.SubElement(tg_loop, "boolProp", name="LoopController.continue_forever").text = "false"
            ET.SubElement(tg_loop, "intProp", name="LoopController.loops").text = "-1"  # -1表示持续运行
            ET.SubElement(thread_group, "stringProp", name="ThreadGroup.num_threads").text = str(threads_count)
            ET.SubElement(thread_group, "stringProp", name="ThreadGroup.ramp_time").text = "10"
            ET.SubElement(thread_group, "boolProp", name="ThreadGroup.scheduler").text = "true"  # 启用调度器以支持duration
            ET.SubElement(thread_group, "stringProp", name="ThreadGroup.duration").text = "300"
            ET.SubElement(thread_group, "stringProp", name="ThreadGroup.delay").text = ""

            # 主TG下的hashTree（我们将把各组的采样器追加到这里）
            main_tg_tree = ET.SubElement(test_plan_tree, "hashTree")

            # 默认的HTTP Header Manager（包含Authorization）- 按照标准格式
            header_manager = ET.SubElement(main_tg_tree, "HeaderManager", guiclass="HeaderPanel", testclass="HeaderManager", testname="HTTP信息头管理器", enabled="true")
            collection_prop = ET.SubElement(header_manager, "collectionProp", name="HeaderManager.headers")
            for k, v in {"Authorization": "Bearer ${token}", "Content-Type": "application/json"}.items():
                ep = ET.SubElement(collection_prop, "elementProp", name="", elementType="Header")
                ET.SubElement(ep, "stringProp", name="Header.name").text = k
                ET.SubElement(ep, "stringProp", name="Header.value").text = v
            # header_manager 的hashTree
            ET.SubElement(main_tg_tree, "hashTree")

            xml_str = ET.tostring(root, encoding='unicode')
            # 使用自定义格式化，减少空行
            dom = minidom.parseString(xml_str)
            pretty = dom.toprettyxml(indent="  ")
            # 移除多余的空行（保留单个空行用于分隔主要元素）
            import re
            pretty = re.sub(r'\n\s*\n\s*\n+', '\n\n', pretty)
            # 添加XML声明
            if not pretty.strip().startswith('<?xml'):
                pretty = '<?xml version="1.0" encoding="UTF-8"?>\n' + pretty
            return pretty

        def append_group_samplers_to_skeleton(skeleton_xml: str, group_fragment_xml: str) -> str:
            import xml.etree.ElementTree as ET
            from xml.dom import minidom
            # 解析骨架
            # 移除XML声明（如果有）以便正确解析
            skeleton_clean = skeleton_xml.strip()
            if skeleton_clean.startswith('<?xml'):
                # 找到第一个>的位置
                decl_end = skeleton_clean.find('?>')
                if decl_end > 0:
                    skeleton_clean = skeleton_clean[decl_end + 2:].strip()
            sk_tree = ET.ElementTree(ET.fromstring(skeleton_clean))
            sk_root = sk_tree.getroot()
            
            # 验证LoopController是否存在（调试用）
            setup_controllers = sk_root.findall('.//SetupThreadGroup/elementProp[@name="ThreadGroup.main_controller"]')
            tg_controllers = sk_root.findall('.//ThreadGroup/elementProp[@name="ThreadGroup.main_controller"]')
            if len(setup_controllers) == 0 or len(tg_controllers) == 0:
                print(f"[append_group_samplers_to_skeleton] 警告：骨架XML中缺少LoopController！Setup: {len(setup_controllers)}, ThreadGroup: {len(tg_controllers)}")

            # 定位主Thread Group的hashTree（更稳健地遍历 TestPlan 下的第二层 hashTree）
            # 预期结构：root/hashTree -> TestPlan, hashTree(PlanTree) -> [SetupTG, hashTree, ThreadGroup, hashTree(main)]
            testplan_hash = sk_root.find('./hashTree')
            main_hash = None
            if testplan_hash is not None:
                plan_children = list(testplan_hash)
                # 在 TestPlan 同级的 hashTree 容器中查找 ThreadGroup 之后的 hashTree
                for child in plan_children:
                    if child.tag != 'hashTree':
                        continue
                    container_children = list(child)
                    for idx, sub in enumerate(container_children):
                        if sub.tag == 'ThreadGroup':
                            # 取紧随其后的 hashTree 作为主TG的容器
                            if idx + 1 < len(container_children) and container_children[idx + 1].tag == 'hashTree':
                                main_hash = container_children[idx + 1]
                                break
                    if main_hash is not None:
                        break
            if main_hash is None:
                return skeleton_xml

            # 解析组片段，提取HTTPSamplerProxy及其紧随的hashTree
            try:
                frag_root = ET.fromstring(group_fragment_xml)
            except Exception:
                # 如果不是完整XML，尝试包裹后再解析
                wrapped = f"<FragmentRoot>{group_fragment_xml}</FragmentRoot>"
                frag_root = ET.fromstring(wrapped)

            # 查找所有HTTPSamplerProxy，并将其和紧随的hashTree一起追加
            nodes = list(frag_root.iter()) if frag_root.tag != 'FragmentRoot' else list(frag_root)
            # 遍历节点序列，按顺序把 sampler 和它后面的 hashTree 拼接
            # 去重：根据 (method, path, testname) 组合键去重
            existing_keys = set()
            # 预先从骨架中收集已有HTTPSamplerProxy键
            for sampler in sk_root.findall('.//HTTPSamplerProxy'):
                method = ''
                path = ''
                for sp in sampler.findall('.//stringProp'):
                    n = sp.get('name') or ''
                    if n == 'HTTPSampler.method':
                        method = sp.text or ''
                    elif n == 'HTTPSampler.path':
                        path = sp.text or ''
                key = (method.upper(), path, sampler.get('testname', ''))
                existing_keys.add(key)

            i = 0
            while i < len(nodes):
                node = nodes[i]
                if node.tag == 'HTTPSamplerProxy':
                    # 生成去重键
                    method = ''
                    path = ''
                    for sp in node.findall('.//stringProp'):
                        n = sp.get('name') or ''
                        if n == 'HTTPSampler.method':
                            method = sp.text or ''
                        elif n == 'HTTPSampler.path':
                            path = sp.text or ''
                    key = (method.upper(), path, node.get('testname', ''))
                    if key in existing_keys:
                        i += 1
                        continue
                    existing_keys.add(key)
                    # 复制节点
                    main_hash.append(node)
                    # 如果下一个是hashTree则也追加
                    j = i + 1
                    if j < len(nodes) and nodes[j].tag == 'hashTree':
                        main_hash.append(nodes[j])
                        i = j
                i += 1

            out_str = ET.tostring(sk_root, encoding='unicode')
            # 使用自定义格式化，减少空行
            dom = minidom.parseString(out_str)
            pretty = dom.toprettyxml(indent="  ")
            # 移除多余的空行（保留单个空行用于分隔主要元素）
            import re
            pretty = re.sub(r'\n\s*\n\s*\n+', '\n\n', pretty)
            return pretty

        def clean_llm_xml(raw: str) -> str:
            import re as _re
            if not raw:
                return ""
            s = _re.sub(r"```xml\s*\n?", "", raw)
            s = _re.sub(r"```\s*\n?", "", s)
            s = s.strip()
            s = _re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)', '&amp;', s)
            return s

        # 分组流程（包含断点续传）
        if enable_grouped:
            def grouped_flow() -> Dict[str, Any]:
                groups = None
                current_group_idx = 0
                group_results = []
                skeleton_xml_local = None

                if grouped_checkpoint:
                    groups = chunk_interfaces(grouped_checkpoint.get('interfaces_info') or interfaces_info)
                    current_group_idx = int(grouped_checkpoint.get('current_group', 0))
                    group_results = grouped_checkpoint.get('group_results', []) or []
                    skeleton_xml_local = grouped_checkpoint.get('skeleton_xml')
                else:
                    groups = chunk_interfaces(interfaces_info)

                total_groups = len(groups)
                if total_groups == 0:
                    raise Exception("接口分组为空，无法生成JMX")

                if not skeleton_xml_local:
                    skeleton_xml_local = build_skeleton_xml(suite.name, threads, environment_info, login_interface_info)

                def calc_progress(idx: int) -> int:
                    if total_groups <= 0:
                        return 10
                    portion = int((idx / total_groups) * 70)
                    return 10 + portion

                import requests, time, threading
                from app.config import settings
                deepseek_api_key = settings.DEEPSEEK_API_KEY
                deepseek_url = settings.DEEPSEEK_BASE_URL + "/chat/completions" if settings.DEEPSEEK_BASE_URL else "https://api.deepseek.com/v1/chat/completions"
                connect_timeout, read_timeout = 30, 120

                for g_idx in range(current_group_idx, total_groups):
                    group = groups[g_idx]
                    prog = calc_progress(g_idx)
                    self.update_state(state='PROGRESS', meta={'progress': prog, 'message': f'正在生成第{g_idx+1}/{total_groups}组接口脚本...'})
                    test_case.generation_progress = prog
                    db.commit()

                    prompt_parts = []
                    prompt_parts.append("你是资深性能测试工程师，请只生成JMeter主Thread Group中的HTTP采样器片段（HTTPSamplerProxy及其紧随的hashTree），不要包含TestPlan、Setup Thread Group或Thread Group定义。\n")
                    prompt_parts.append("严格规则：\n")
                    prompt_parts.append("1) 绝对不要在URL中添加任何debug或sql参数\n")
                    prompt_parts.append("2) 使用变量 ${token} 传递鉴权，不要硬编码\n")
                    prompt_parts.append("3) 每个接口包含适当的断言\n")
                    prompt_parts.append("4) 输出必须是XML片段，可直接插入JMX，不要额外文字\n\n")
                    prompt_parts.append(f"用例集: {suite.name}\n")
                    prompt_parts.append(f"线程数: {threads}\n")
                    prompt_parts.append("本组接口：\n")
                    for interface in group:
                        path_or_url = interface.get('path') or interface.get('url') or '/'
                        if '?' in path_or_url:
                            path_or_url = path_or_url.split('?')[0]
                        prompt_parts.append(f"- 名称: {interface.get('name','')}, 方法: {interface.get('method','GET')}, 路径: {path_or_url}\n")
                        headers = interface.get('headers') or {}
                        important_headers = {k: v for k, v in headers.items() if k.lower() in ['content-type', 'accept']}
                        if important_headers:
                            prompt_parts.append(f"  头: {json.dumps(important_headers, ensure_ascii=False)}\n")
                        request_body = interface.get('request_body') or {}
                        if request_body:
                            rb = json.dumps(request_body, ensure_ascii=False)
                            if len(rb) > 300:
                                rb = rb[:300] + "..."
                            prompt_parts.append(f"  体: {rb}\n")

                    group_prompt = "".join(prompt_parts)

                    heartbeat_stop = threading.Event()
                    def _heartbeat():
                        while not heartbeat_stop.is_set():
                            print(f"[分组生成] 仍在等待LLM返回，第{g_idx+1}组...")
                            heartbeat_stop.wait(5)
                    threading.Thread(target=_heartbeat, daemon=True).start()

                    request_start_time = time.time()
                    try:
                        messages = [
                            {"role": "system", "content": "只生成JMeter主Thread Group中的采样器XML片段（HTTPSamplerProxy及其相邻hashTree），不要包含TestPlan/ThreadGroup等其它部分。"},
                            {"role": "user", "content": group_prompt}
                        ]
                        response = requests.post(
                            deepseek_url,
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {deepseek_api_key}"
                            },
                            json={
                                "model": "deepseek-chat",
                                "messages": messages,
                                "temperature": 0.2,
                                "max_tokens": 5000
                            },
                            timeout=(connect_timeout, read_timeout),
                            stream=False
                        )
                        heartbeat_stop.set()
                        if response.status_code != 200:
                            raise Exception(f"DeepSeek API失败: {response.status_code} - {response.text[:300]}")
                        result = response.json()
                        fragment_raw = result["choices"][0]["message"]["content"]
                        fragment_xml = clean_llm_xml(fragment_raw)
                        if not fragment_xml:
                            raise Exception("LLM返回的片段为空")

                        group_results.append(fragment_xml)
                        grouped_checkpoint_data = {
                            'mode': 'grouped',
                            'progress': calc_progress(g_idx + 1),
                            'suite_id': suite_id,
                            'interfaces_info': interfaces_info,
                            'environment_info': environment_info,
                            'login_interface_info': login_interface_info,
                            'threads': threads,
                            'current_group': g_idx + 1,
                            'total_groups': total_groups,
                            'group_results': group_results,
                            'skeleton_xml': skeleton_xml_local
                        }
                        test_case.generation_checkpoint = json.dumps(grouped_checkpoint_data, ensure_ascii=False)
                        test_case.generation_progress = calc_progress(g_idx + 1)
                        db.commit()
                    except Exception as e:
                        heartbeat_stop.set()
                        elapsed_time = time.time() - request_start_time
                        print(f"[分组生成] 第{g_idx+1}组生成失败，耗时{elapsed_time:.1f}s: {e}")
                        raise

                # 合并
                self.update_state(state='PROGRESS', meta={'progress': 85, 'message': '正在合并各组脚本...'})
                test_case.generation_progress = 85
                db.commit()

                merged_xml = skeleton_xml_local
                for frag in group_results:
                    merged_xml = append_group_samplers_to_skeleton(merged_xml, frag)

                # 验证合并后的XML是否包含LoopController
                import xml.etree.ElementTree as ET
                try:
                    merged_clean = merged_xml.strip()
                    if merged_clean.startswith('<?xml'):
                        decl_end = merged_clean.find('?>')
                        if decl_end > 0:
                            merged_clean = merged_clean[decl_end + 2:].strip()
                    merged_root = ET.fromstring(merged_clean)
                    setup_controllers = merged_root.findall('.//SetupThreadGroup/elementProp[@name="ThreadGroup.main_controller"]')
                    tg_controllers = merged_root.findall('.//ThreadGroup/elementProp[@name="ThreadGroup.main_controller"]')
                    if len(setup_controllers) == 0 or len(tg_controllers) == 0:
                        print(f"[分组生成] 警告：合并后的XML缺少LoopController！Setup: {len(setup_controllers)}, ThreadGroup: {len(tg_controllers)}")
                        # 如果缺少，重新生成骨架并重新合并
                        print(f"[分组生成] 重新生成骨架XML...")
                        skeleton_xml_local = build_skeleton_xml(suite.name, threads, environment_info, login_interface_info)
                        merged_xml = skeleton_xml_local
                        for frag in group_results:
                            merged_xml = append_group_samplers_to_skeleton(merged_xml, frag)
                except Exception as e:
                    print(f"[分组生成] 验证LoopController时出错: {e}")

                final_jmx = clean_llm_xml(merged_xml)

                self.update_state(state='PROGRESS', meta={'progress': 90, 'message': '正在保存JMX脚本...'})
                test_case.generation_progress = 90
                db.commit()

                test_case.test_code = final_jmx
                test_case.status = 'active'
                test_case.generation_progress = 100
                test_case.error_message = None
                test_case.generation_checkpoint = None
                db.commit()
                # 生成成功后清理测试用例列表缓存，确保前端立刻能看到新用例
                try:
                    cache_service.invalidate_cache(f"test_cases:{project_id}:*")
                except Exception as cache_error:
                    print(f"[性能测试用例生成] 清理缓存失败: {cache_error}")

                self.update_state(state='PROGRESS', meta={'progress': 100, 'message': 'JMeter性能测试脚本生成成功（分组）'})
                return {
                    "status": "success",
                    "test_case_id": test_case_id,
                    "message": "JMeter性能测试脚本生成成功（分组）",
                    "jmx_length": len(final_jmx)
                }

            return grouped_flow()

        # ========= 旧逻辑（单次生成） =========
        if generated_jmx is None:
            # 更新任务进度和测试用例进度
            self.update_state(
                state='PROGRESS',
                meta={'progress': 10, 'message': '开始构建RAG上下文...'}
            )
            test_case.generation_progress = 10
            db.commit()
            
            # 构建JMeter提示词
            prompt_parts = []
            
            # 1. 测试用例集信息
            prompt_parts.append(f"## 测试用例集信息\n")
            prompt_parts.append(f"- 用例集名称: {suite.name}\n")
            prompt_parts.append(f"- 用例集描述: {suite.description or '无'}\n")
            prompt_parts.append(f"\n")
            
            # 2. 环境信息
            prompt_parts.append(f"## 测试环境信息\n")
            prompt_parts.append(f"- 基础URL: {environment_info.get('base_url', '')}\n")
            prompt_parts.append(f"- 用户ID: {environment_info.get('xjid', '')}\n")
            prompt_parts.append(f"- 用户名: {environment_info.get('username', '')}\n")
            prompt_parts.append(f"- 并发线程数: {threads}\n")
            prompt_parts.append(f"\n")
            
            # 3. 登录接口信息（需要在Setup Thread Group中执行）
            prompt_parts.append(f"## 登录接口信息（必须在Setup Thread Group中执行）\n")
            if login_interface_info:
                login_path = login_interface_info.get('path', '/V0.1/index.php')
                # 移除URL中的debug参数
                if '?' in login_path:
                    login_path = login_path.split('?')[0]
                login_url_full = f"{login_interface_info.get('base_url', environment_info.get('base_url', ''))}{login_path}"
                
                prompt_parts.append(f"### 登录接口详情:\n")
                prompt_parts.append(f"- 接口名称: {login_interface_info.get('name', '用户登录')}\n")
                prompt_parts.append(f"- 请求方法: {login_interface_info.get('method', 'POST')}\n")
                prompt_parts.append(f"- 请求URL: {login_url_full}\n")
                
                # 简化请求头，只保留关键字段
                headers = login_interface_info.get('headers', {})
                if headers:
                    # 只保留Content-Type等关键头
                    important_headers = {k: v for k, v in headers.items() if k.lower() in ['content-type', 'accept']}
                    if important_headers:
                        prompt_parts.append(f"- 请求头: {json.dumps(important_headers, ensure_ascii=False)}\n")
                
                # 简化请求体，限制长度
                request_body = login_interface_info.get('request_body', {})
                if request_body:
                    request_body_str = json.dumps(request_body, ensure_ascii=False)
                    if len(request_body_str) > 500:
                        # 如果请求体太长，只保留前500字符
                        request_body_str = request_body_str[:500] + "..."
                    prompt_parts.append(f"- 请求体: {request_body_str}\n")
                
                # 简化响应体，只保留token相关字段
                if login_interface_info.get('response_body'):
                    response_body = login_interface_info.get('response_body')
                    if isinstance(response_body, str):
                        try:
                            response_body = json.loads(response_body)
                        except:
                            response_body = {}
                    
                    # 只提取包含token的路径信息
                    if isinstance(response_body, dict):
                        # 查找token字段
                        token_path = None
                        def find_token_path(obj, path=""):
                            if isinstance(obj, dict):
                                for k, v in obj.items():
                                    if 'token' in k.lower():
                                        return f"{path}.{k}" if path else k
                                    result = find_token_path(v, f"{path}.{k}" if path else k)
                                    if result:
                                        return result
                            elif isinstance(obj, list) and obj:
                                return find_token_path(obj[0], f"{path}[0]")
                            return None
                        
                        token_path = find_token_path(response_body)
                        if token_path:
                            prompt_parts.append(f"- Token路径: $.{token_path}\n")
                        else:
                            # 如果找不到，只显示响应体的前200字符
                            response_str = json.dumps(response_body, ensure_ascii=False)
                            if len(response_str) > 200:
                                response_str = response_str[:200] + "..."
                            prompt_parts.append(f"- 响应体示例: {response_str}\n")
            
            prompt_parts.append(f"\n")
            prompt_parts.append(f"**重要要求：**\n")
            prompt_parts.append(f"1. 登录接口必须在Setup Thread Group中执行\n")
            prompt_parts.append(f"2. 使用JSON Extractor或Regular Expression Extractor提取token\n")
            prompt_parts.append(f"3. token提取路径：`$.data.info.token` 或使用正则表达式 `\"token\":\"(.+?)\"`\n")
            prompt_parts.append(f"4. 将提取的token保存为JMeter变量 ${{token}}\n")
            prompt_parts.append(f"5. 后续所有接口的请求头中使用 `Authorization: Bearer ${{token}}` 或请求体中使用token变量\n")
            prompt_parts.append(f"\n")
            
            # 4. Few-shot示例接口（简化，只保留1-2个示例）
            if few_shot_interfaces and len(few_shot_interfaces) > 0:
                prompt_parts.append(f"## Few-shot示例接口（参考请求参数格式）\n")
                for idx, fs_interface in enumerate(few_shot_interfaces[:2], 1):  # 最多2个示例
                    prompt_parts.append(f"\n### 示例 {idx}: {fs_interface.get('name', '')}\n")
                    prompt_parts.append(f"- 方法: {fs_interface.get('method', '')}\n")
                    prompt_parts.append(f"- 路径: {fs_interface.get('path', '')}\n")
                    # 简化请求体，限制长度（进一步优化）
                    request_body = fs_interface.get('request_body', {})
                    if request_body:
                        request_body_str = json.dumps(request_body, ensure_ascii=False)
                        if len(request_body_str) > 200:  # 从300减少到200，few-shot示例不需要太详细
                            request_body_str = request_body_str[:200] + "..."
                        prompt_parts.append(f"- 请求体: {request_body_str}\n")
                prompt_parts.append(f"\n")
            
            # 5. 场景接口列表（按调用顺序）
            prompt_parts.append(f"## 场景接口列表（按调用顺序）\n")
            prompt_parts.append(f"以下接口需要按顺序生成JMeter测试脚本，每个接口都需要:\n")
            prompt_parts.append(f"1. 使用从Setup Thread Group中提取的token变量 ${{token}}\n")
            prompt_parts.append(f"2. 使用正确的请求参数（参考few-shot示例）\n")
            prompt_parts.append(f"3. 添加响应断言（验证HTTP状态码、响应体关键字段）\n")
            prompt_parts.append(f"4. 使用JSON Path断言验证响应体结构\n")
            prompt_parts.append(f"\n")
            
            for idx, interface in enumerate(interfaces_info, 1):
                interface_url = interface.get('url', '') or interface.get('path', '')
                if '?' in interface_url:
                    interface_url = interface_url.split('?')[0]
                interface_url_full = f"{interface.get('base_url', environment_info.get('base_url', ''))}{interface_url}"
                
                prompt_parts.append(f"\n### 接口 {idx}: {interface.get('name', '')}\n")
                prompt_parts.append(f"- 方法: {interface.get('method', 'GET')}\n")
                prompt_parts.append(f"- URL: {interface_url_full}\n")
                
                # 简化请求头，只保留关键字段
                headers = interface.get('headers', {})
                if headers:
                    important_headers = {k: v for k, v in headers.items() if k.lower() in ['content-type', 'accept', 'authorization']}
                    if important_headers:
                        prompt_parts.append(f"- 请求头: {json.dumps(important_headers, ensure_ascii=False)}\n")
                
                # 简化请求体，限制长度（进一步优化，减少prompt大小）
                request_body = interface.get('request_body', {})
                if request_body:
                    request_body_str = json.dumps(request_body, ensure_ascii=False)
                    if len(request_body_str) > 300:  # 从500减少到300，加快API响应
                        # 如果请求体太长，只保留前300字符
                        request_body_str = request_body_str[:300] + "..."
                    prompt_parts.append(f"- 请求体: {request_body_str}\n")
                
                # 移除响应体示例，因为对生成JMeter脚本不是必需的
                # 只在需要时提供简化的响应结构
                if interface.get('response_body'):
                    response_body = interface.get('response_body')
                    if isinstance(response_body, str):
                        try:
                            response_body = json.loads(response_body)
                        except:
                            response_body = {}
                    
                    # 只提取关键字段用于断言
                    if isinstance(response_body, dict):
                        # 查找常见的成功标识字段
                        key_fields = []
                        for key in ['code', 'status', 'ret', 'success', 'result']:
                            if key in response_body:
                                key_fields.append(f"{key}={response_body[key]}")
                        if key_fields:
                            prompt_parts.append(f"- 响应关键字段: {', '.join(key_fields)}\n")
            
            prompt_parts.append(f"\n## JMeter脚本要求\n")
            prompt_parts.append(f"生成完整JMX文件，包含：\n")
            prompt_parts.append(f"1. Test Plan: {suite.name}_性能测试\n")
            prompt_parts.append(f"2. Setup Thread Group: 1线程，执行登录，提取token到${{token}}\n")
            prompt_parts.append(f"3. Thread Group: {threads}线程，Ramp-up 10秒，持续300秒\n")
            prompt_parts.append(f"4. HTTP Header Manager: Authorization Bearer ${{token}}, Content-Type application/json\n")
            prompt_parts.append(f"5. 每个接口HTTP Request: 按顺序执行，包含请求体和断言\n")
            prompt_parts.append(f"6. 断言: HTTP状态码200，JSON Path验证关键字段\n")
            prompt_parts.append(f"7. 监听器: View Results Tree, Summary Report, Aggregate Graph\n")
            prompt_parts.append(f"\n**重要规则：**\n")
            prompt_parts.append(f"1. 禁止在URL中添加debug或sql参数\n")
            prompt_parts.append(f"2. 使用${{token}}变量，不能硬编码\n")
            prompt_parts.append(f"3. 接口按顺序执行\n")
            prompt_parts.append(f"4. JMX必须是有效XML格式\n")
            prompt_parts.append(f"\n只返回XML代码，不要解释文字。\n")
            
            full_prompt = "".join(prompt_parts)
            
            # 保存checkpoint（包含prompt）
            checkpoint_data = {
                'progress': 30,
                'prompt': full_prompt,
                'suite_id': suite_id,
                'interfaces_info': interfaces_info,
                'environment_info': environment_info,
                'login_interface_info': login_interface_info,
                'threads': threads
            }
            test_case.generation_checkpoint = json.dumps(checkpoint_data, ensure_ascii=False)
            
            # 更新任务进度和测试用例进度
            self.update_state(
                state='PROGRESS',
                meta={'progress': 30, 'message': '正在调用DeepSeek API生成JMeter脚本...'}
            )
            test_case.generation_progress = 30
            db.commit()
        else:
            # 从checkpoint恢复，使用保存的prompt
            full_prompt = checkpoint.get('prompt', '')
            print(f"[性能测试用例生成] 使用checkpoint中的prompt，长度: {len(full_prompt)}")
        
        # 调用DeepSeek API（只有在没有从checkpoint恢复JMX时才调用）
        if generated_jmx is None:
            import requests
            from app.config import settings
            deepseek_api_key = settings.DEEPSEEK_API_KEY
            deepseek_url = settings.DEEPSEEK_BASE_URL + "/chat/completions" if settings.DEEPSEEK_BASE_URL else "https://api.deepseek.com/v1/chat/completions"
            
            print(f"[性能测试用例生成] 开始调用DeepSeek API，prompt长度: {len(full_prompt)}")
            
            messages = [
                {
                    "role": "system",
                    "content": """你是一个专业的性能测试工程师，擅长编写高质量的JMeter性能测试脚本。
请根据提供的接口信息，严格按照以下要求生成JMeter测试脚本：

**JMeter脚本要求：**
1. 生成完整的JMX XML文件内容
2. 必须包含Setup Thread Group用于登录和提取token
3. 必须包含Thread Group用于性能测试（默认10个并发线程）
4. 使用HTTP Header Manager传递token：`Authorization: Bearer ${{token}}`
5. 每个接口必须包含响应断言和JSON Path断言
6. 必须包含监听器（View Results Tree、Summary Report、Aggregate Graph）
7. 所有URL必须使用原始URL，不能添加任何debug或sql参数

**重要规则：**
1. **URL规则（严格禁止）：绝对不要在URL中添加任何debug或sql参数**，如 `?__debug__=1&__sql__=true` 等后缀
2. 必须使用JMeter变量 ${{token}} 传递token，不能硬编码
3. **生成的JMX文件必须是有效的XML格式，所有XML标签必须正确闭合，所有属性值中的特殊字符（&、<、>、"、'）必须正确转义**
4. **XML格式要求（非常重要）：**
   - 所有标签必须正确闭合（如 `<stringProp name="xxx">value</stringProp>` 或 `<boolProp name="xxx">true</boolProp>`）
   - **绝对禁止未闭合的标签**（如 `<requestHeaders>` 必须有对应的 `</requestHeaders>`）
   - 属性值中的特殊字符必须转义：`&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;`, `"` → `&quot;`, `'` → `&apos;`
   - 不要在属性值中使用未转义的特殊字符
   - 确保所有字符串属性值都在引号内
   - **每个开始标签都必须有对应的结束标签，不能有任何遗漏**
5. 所有接口必须按顺序执行
6. 必须包含完整的断言检查

**特别注意：生成的XML必须完整且格式正确，所有标签都必须正确闭合。在生成代码时，请仔细检查每个标签是否都有对应的闭合标签。**

请严格按照提供的接口信息生成完整的JMX XML文件内容，只返回XML代码，不要包含其他解释性文字。确保生成的XML格式完全正确，可以通过XML解析器验证。"""
            },
            {
                "role": "user",
                "content": full_prompt
            }
        ]
        
        print(f"[性能测试用例生成] 准备发送请求到DeepSeek API，消息数量: {len(messages)}")
        
        import time
        request_start_time = time.time()
        print(f"[性能测试用例生成] 开始发送请求，时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            print(f"[性能测试用例生成] 调用requests.post，URL: {deepseek_url}")
            request_body_str = json.dumps(messages, ensure_ascii=False)
            print(f"[性能测试用例生成] 请求体大小: {len(request_body_str)} 字符")
            print(f"[性能测试用例生成] prompt长度: {len(full_prompt)} 字符")
            
            # 如果prompt太长，警告并尝试进一步优化
            if len(full_prompt) > 10000:
                print(f"[性能测试用例生成] 警告：prompt长度超过10000字符，可能导致API响应慢")
            
            # 使用更短的超时时间，并添加连接超时
            connect_timeout = 10  # 连接超时10秒
            read_timeout = 600    # 读取超时600秒（10分钟），因为性能测试用例生成可能更复杂
            
            print(f"[性能测试用例生成] 设置超时: 连接{connect_timeout}秒，读取{read_timeout}秒")
            print(f"[性能测试用例生成] 开始发送请求...")
            
            # 使用threading添加心跳日志
            import threading
            heartbeat_stop = threading.Event()
            
            def heartbeat_log():
                """定期输出心跳日志，确认请求还在等待"""
                wait_interval = 30  # 每30秒输出一次
                elapsed = 0
                # 保存任务ID和测试用例ID，避免在线程中访问self时出现问题
                task_id = self.request.id
                saved_test_case_id = test_case_id
                
                while not heartbeat_stop.wait(wait_interval):
                    elapsed += wait_interval
                    print(f"[性能测试用例生成] 等待DeepSeek API响应中... 已等待{elapsed}秒（超时时间：{read_timeout}秒）")
                    # 每30秒更新一次进度（更频繁的更新）
                    if elapsed < read_timeout - 10:
                        try:
                            # 进度从30%逐步增加到80%（根据已等待时间）
                            progress = 30 + int((elapsed / read_timeout) * 50)  # 30%到80%之间
                            
                            # 只更新数据库进度，不调用self.update_state()（避免线程中任务上下文丢失）
                            # 使用新的数据库会话，避免线程安全问题
                            from app.database import SessionLocal
                            thread_db = SessionLocal()
                            try:
                                thread_test_case = thread_db.query(TestCase).filter(TestCase.id == saved_test_case_id).first()
                                if thread_test_case:
                                    thread_test_case.generation_progress = progress
                                    thread_db.commit()
                                    print(f"[性能测试用例生成] 已更新数据库进度: {progress}%")
                                    
                                    # 注意：不在线程中更新Celery任务状态，因为线程中无法访问任务上下文
                                    # 前端可以通过查询测试用例的generation_progress字段来获取实时进度
                            except Exception as db_error:
                                print(f"[性能测试用例生成] 数据库更新失败: {db_error}")
                            finally:
                                thread_db.close()
                        except Exception as update_error:
                            print(f"[性能测试用例生成] 更新进度失败: {update_error}")
                    if elapsed >= read_timeout - 10:
                        print(f"[性能测试用例生成] 警告：即将超时（{read_timeout}秒）")
                        break
            
            heartbeat_thread = threading.Thread(target=heartbeat_log, daemon=True)
            heartbeat_thread.start()
            
            try:
                # 使用stream=False但添加更详细的日志
                response = requests.post(
                    deepseek_url,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {deepseek_api_key}"
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": messages,
                        "temperature": 0.3,
                        "max_tokens": 6000  # 减少到6000，加快响应速度
                    },
                    timeout=(connect_timeout, read_timeout),  # (连接超时, 读取超时)
                    stream=False  # 不使用流式，等待完整响应
                )
                
                heartbeat_stop.set()  # 停止心跳日志
                print(f"[性能测试用例生成] requests.post调用完成，收到响应")
                
                request_end_time = time.time()
                elapsed_time = request_end_time - request_start_time
                print(f"[性能测试用例生成] DeepSeek API响应状态码: {response.status_code}，耗时: {elapsed_time:.2f}秒")
                
                if response.status_code != 200:
                    error_detail = response.text[:500] if response.text else "无响应内容"
                    raise Exception(f"DeepSeek API请求失败: {response.status_code} - {error_detail}")
                    
                print(f"[性能测试用例生成] DeepSeek API响应成功，开始解析响应")
                result = response.json()
                generated_jmx = result["choices"][0]["message"]["content"]
                print(f"[性能测试用例生成] 生成的JMX脚本长度: {len(generated_jmx) if generated_jmx else 0}")
                
                # 保存checkpoint（包含生成的JMX）
                checkpoint_data = {
                    'progress': 80,
                    'generated_jmx': generated_jmx,
                    'prompt': full_prompt
                }
                test_case.generation_checkpoint = json.dumps(checkpoint_data, ensure_ascii=False)
                test_case.generation_progress = 80
                db.commit()
                
            except requests.exceptions.Timeout as e:
                heartbeat_stop.set()  # 停止心跳日志
                elapsed_time = time.time() - request_start_time
                print(f"[性能测试用例生成] DeepSeek API请求超时，耗时: {elapsed_time:.2f}秒，错误: {str(e)}")
                raise Exception(f"DeepSeek API请求超时（{elapsed_time:.0f}秒），请稍后重试")
            except requests.exceptions.ConnectionError as e:
                heartbeat_stop.set()  # 停止心跳日志
                elapsed_time = time.time() - request_start_time
                print(f"[性能测试用例生成] DeepSeek API连接错误，耗时: {elapsed_time:.2f}秒，错误: {str(e)}")
                raise Exception(f"无法连接到DeepSeek API: {str(e)}")
            except requests.exceptions.RequestException as e:
                heartbeat_stop.set()  # 停止心跳日志
                elapsed_time = time.time() - request_start_time
                print(f"[性能测试用例生成] DeepSeek API请求异常，耗时: {elapsed_time:.2f}秒，错误: {str(e)}")
                raise Exception(f"DeepSeek API请求异常: {str(e)}")
            except Exception as e:
                heartbeat_stop.set()  # 停止心跳日志
                elapsed_time = time.time() - request_start_time
                print(f"[性能测试用例生成] 未知错误，耗时: {elapsed_time:.2f}秒，错误类型: {type(e).__name__}，错误: {str(e)}")
                import traceback
                traceback.print_exc()
                raise Exception(f"DeepSeek API调用失败: {str(e)}")
        except requests.exceptions.Timeout as e:
            elapsed_time = time.time() - request_start_time if 'request_start_time' in locals() else 0
            print(f"[性能测试用例生成] DeepSeek API请求超时，耗时: {elapsed_time:.2f}秒，错误: {str(e)}")
            raise Exception(f"DeepSeek API请求超时（{elapsed_time:.0f}秒），请稍后重试")
        except requests.exceptions.ConnectionError as e:
            elapsed_time = time.time() - request_start_time if 'request_start_time' in locals() else 0
            print(f"[性能测试用例生成] DeepSeek API连接错误，耗时: {elapsed_time:.2f}秒，错误: {str(e)}")
            raise Exception(f"无法连接到DeepSeek API: {str(e)}")
        except requests.exceptions.RequestException as e:
            elapsed_time = time.time() - request_start_time if 'request_start_time' in locals() else 0
            print(f"[性能测试用例生成] DeepSeek API请求异常，耗时: {elapsed_time:.2f}秒，错误: {str(e)}")
            raise Exception(f"DeepSeek API请求异常: {str(e)}")
        except Exception as e:
            elapsed_time = time.time() - request_start_time if 'request_start_time' in locals() else 0
            print(f"[性能测试用例生成] 未知错误，耗时: {elapsed_time:.2f}秒，错误类型: {type(e).__name__}，错误: {str(e)}")
            import traceback
            traceback.print_exc()
            raise Exception(f"DeepSeek API调用失败: {str(e)}")
        
        # 更新任务进度和测试用例进度（无论是否从checkpoint恢复）
        self.update_state(
            state='PROGRESS',
            meta={'progress': 80, 'message': '正在清理生成的JMX脚本...'}
        )
        test_case.generation_progress = 80
        db.commit()
        
        # 检查生成的JMX是否为空
        if not generated_jmx or not generated_jmx.strip():
            raise Exception("DeepSeek API返回的JMX脚本为空，请检查API响应")
        
        # 清理生成的JMX（移除markdown代码块标记）
        import re
        # 移除 ```xml 和 ``` 标记
        generated_jmx = re.sub(r'```xml\s*\n?', '', generated_jmx)
        generated_jmx = re.sub(r'```\s*\n?', '', generated_jmx)
        # 移除开头的空行
        generated_jmx = generated_jmx.strip()
        
        # 再次检查清理后的JMX是否为空
        if not generated_jmx:
            raise Exception("清理后的JMX脚本为空，可能是格式不正确")
        
        # 只做基本的XML格式检查（修复未转义的&符号），详细校验延迟到执行时
        # 这样可以避免生成时过度校验导致失败，让JMeter在执行时自己处理格式问题
        self.update_state(
            state='PROGRESS',
            meta={'progress': 85, 'message': '正在清理JMX脚本格式...'}
        )
        test_case.generation_progress = 85
        db.commit()
        
        # 只修复最基本的XML问题：未转义的&符号
        # 其他格式问题（如标签不匹配、未闭合等）让JMeter在执行时处理
        import re
        # 修复未转义的&符号（不在实体中的）
        generated_jmx = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)', '&amp;', generated_jmx)
        
        print(f"[性能测试用例生成] 已完成基本XML格式清理，详细校验将在执行时进行")
        
        # 更新任务进度和测试用例进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 90, 'message': '正在保存JMX脚本...'}
        )
        test_case.generation_progress = 90
        db.commit()
        
        # 保存JMX脚本到测试用例
        test_case.test_code = generated_jmx
        test_case.status = 'active'  # 生成成功，标记为active
        test_case.generation_progress = 100
        test_case.error_message = None
        test_case.generation_checkpoint = None  # 清除checkpoint
        db.commit()
        # 生成成功后清理测试用例列表缓存，确保前端立刻能看到新用例
        try:
            cache_service.invalidate_cache(f"test_cases:{project_id}:*")
        except Exception as cache_error:
            print(f"[性能测试用例生成] 清理缓存失败: {cache_error}")
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 100, 'message': 'JMeter性能测试脚本生成成功'}
        )
        
        return {
            "status": "success",
            "test_case_id": test_case_id,
            "message": "JMeter性能测试脚本生成成功",
            "jmx_length": len(generated_jmx)
        }
        
    except Exception as e:
        import traceback
        error_msg = f"生成JMeter性能测试脚本失败: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        
        # 更新测试用例状态为失败，并保存错误信息
        try:
            if test_case:
                test_case.status = 'failed'
                test_case.generation_progress = 0
                # 限制错误消息长度，避免过长
                safe_error_msg = str(error_msg)
                if len(safe_error_msg) > 500:
                    safe_error_msg = safe_error_msg[:500] + "..."
                test_case.error_message = safe_error_msg
            db.commit()
        except Exception as save_error:
            print(f"保存测试用例失败状态时出错: {save_error}")
            db.rollback()
        
        # 使用安全的失败状态更新
        safe_error_msg = safe_update_failure_state(self, error_msg)
        
        # 限制错误消息长度，避免Celery序列化问题
        if len(safe_error_msg) > 500:
            safe_error_msg = safe_error_msg[:500] + "..."
        
        # 使用明确的异常类型，确保Celery可以正确序列化
        # RuntimeError是标准异常类型，Celery可以正确序列化
        raise RuntimeError(safe_error_msg)
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=600, soft_time_limit=500)
def execute_test_case_task(
    self,
    test_case_id: int,
    environment_id: int
):
    """
    执行测试用例任务（保存调试记录）
    
    Args:
        test_case_id: 测试用例ID
        environment_id: 测试环境ID
    """
    db = SessionLocal()
    debug_record = None
    execution_start_time = datetime.now()
    
    try:
        import subprocess
        
        # 获取测试用例和环境
        test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
        if not test_case:
            raise Exception(f"测试用例不存在: {test_case_id}")
        
        # 严格检查用例类型，如果是jmeter类型，绝对不能使用pytest执行
        case_type = test_case.case_type or 'pytest'
        print(f"[execute_test_case_task] 用例ID: {test_case_id}, 用例类型: {case_type}, 用例名称: {test_case.name}")
        
        if case_type == 'jmeter':
            error_msg = f"错误：JMeter性能测试用例（ID: {test_case_id}, 名称: {test_case.name}）不能使用pytest执行！应该使用execute_jmeter_performance_test_task。"
            print(f"[execute_test_case_task] {error_msg}")
            raise Exception(error_msg)
        
        environment = db.query(TestEnvironment).filter(TestEnvironment.id == environment_id).first()
        if not environment:
            raise Exception(f"测试环境不存在: {environment_id}")
        
        if not test_case.test_code:
            raise Exception("测试用例没有测试代码")
        
        # 创建调试记录
        debug_record = TestDebugRecord(
            test_case_id=test_case_id,
            environment_id=environment_id,
            task_id=self.request.id,
            execution_status="running",
            execution_time=execution_start_time
        )
        db.add(debug_record)
        db.commit()
        db.refresh(debug_record)
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': '开始执行测试用例...'}
        )
        
        # 创建临时文件保存测试代码
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, dir='/tmp') as f:
            test_code = test_case.test_code
            # 修复代码中的bare except
            test_code = re.sub(r'except:\s*$', 'except Exception:\n    pass', test_code, flags=re.MULTILINE)
            f.write(test_code)
            temp_file = f.name
        
        try:
            # 执行pytest
            self.update_state(
                state='PROGRESS',
                meta={'progress': 30, 'message': '正在执行测试代码...'}
            )
            
            result = subprocess.run(
                ['pytest', temp_file, '-v', '--tb=short', '-rs'],  # -rs显示跳过原因
                capture_output=True,
                text=True,
                timeout=300,
                cwd=os.path.dirname(temp_file)
            )
            
            execution_duration = int((datetime.now() - execution_start_time).total_seconds())
            output = result.stdout + result.stderr
            debug_logs = output
            
            # 判断执行结果
            is_success = (
                result.returncode == 0 and
                'passed' in output.lower() and
                'failed' not in output.lower() and
                'error' not in output.lower()
            )
            
            # 更新调试记录
            debug_record.execution_status = "success" if is_success else "failed"
            debug_record.execution_result = "执行成功" if is_success else "执行失败"
            debug_record.debug_logs = debug_logs
            debug_record.error_message = None if is_success else output
            debug_record.duration = execution_duration
            db.commit()
            
            # 更新任务进度
            self.update_state(
                state='PROGRESS',
                meta={
                    'progress': 100,
                    'message': '执行完成' if is_success else '执行失败',
                    'debug_logs': debug_logs
                }
            )
            
            return {
                "status": "success" if is_success else "failed",
                "test_case_id": test_case_id,
                "output": output,
                "debug_logs": debug_logs,
                "message": "执行成功" if is_success else "执行失败",
                "attempts": 1
            }
            
        except subprocess.TimeoutExpired:
            execution_duration = int((datetime.now() - execution_start_time).total_seconds())
            error_msg = "测试执行超时"
            
            # 更新调试记录
            debug_record.execution_status = "failed"
            debug_record.execution_result = "执行超时"
            debug_record.error_message = error_msg
            debug_record.duration = execution_duration
            db.commit()
            
            self.update_state(
                # 标记失败信息但避免直接进入FAILURE状态以触发exc_type校验
                state='PROGRESS',
                meta={'progress': 0, 'message': error_msg, 'status': 'failed', 'error': error_msg}
            )
            
            raise Exception(error_msg)
            
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_file)
            except:
                pass
        
    except Exception as e:
        import traceback
        error_msg = f"执行测试用例失败: {str(e)}"
        execution_duration = int((datetime.now() - execution_start_time).total_seconds()) if execution_start_time else 0
        
        # 保存调试记录（即使出错也要保存）
        try:
            if debug_record:
                debug_record.execution_status = "failed"
                debug_record.execution_result = "执行异常"
                debug_record.error_message = error_msg
                debug_record.debug_logs = traceback.format_exc()
                debug_record.duration = execution_duration
                db.commit()
            else:
                # 如果调试记录还没创建，现在创建
                debug_record = TestDebugRecord(
                    test_case_id=test_case_id,
                    environment_id=environment_id,
                    task_id=self.request.id,
                    execution_status="failed",
                    execution_result="执行异常",
                    error_message=error_msg,
                    debug_logs=traceback.format_exc(),
                    duration=execution_duration,
                    execution_time=execution_start_time
                )
                db.add(debug_record)
                db.commit()
        except Exception as save_error:
            print(f"保存调试记录失败: {save_error}")
            traceback.print_exc()
        
        print(error_msg)
        traceback.print_exc()
        
        # 使用安全的失败状态更新
        safe_error_msg = safe_update_failure_state(self, error_msg)
        
        # 使用明确的异常类型，确保Celery可以正确序列化
        raise RuntimeError(safe_error_msg)
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=600, soft_time_limit=500)
def execute_jmeter_performance_test_task(
    self,
    test_case_id: int,
    environment_id: int,
    threads: int = 2
):
    """
    执行JMeter性能测试脚本任务（使用2个线程用于调试）
    
    Args:
        test_case_id: 测试用例ID
        environment_id: 测试环境ID
        threads: 并发线程数（默认2，用于调试）
    """
    db = SessionLocal()
    debug_record = None
    execution_start_time = datetime.now()
    
    try:
        import subprocess
        
        # 获取测试用例和环境
        test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
        if not test_case:
            raise Exception(f"测试用例不存在: {test_case_id}")
        
        # 严格检查：必须是jmeter类型才能执行
        case_type = test_case.case_type or 'pytest'
        print(f"[execute_jmeter_performance_test_task] 用例ID: {test_case_id}, 用例类型: {case_type}, 用例名称: {test_case.name}")
        
        if case_type != 'jmeter':
            error_msg = f"错误：测试用例（ID: {test_case_id}, 类型: {case_type}, 名称: {test_case.name}）不是JMeter性能测试用例，不能使用JMeter执行！"
            print(f"[execute_jmeter_performance_test_task] {error_msg}")
            raise Exception(error_msg)
        
        if not test_case.test_code:
            raise Exception("测试用例没有测试代码（JMX脚本）")
        
        environment = db.query(TestEnvironment).filter(TestEnvironment.id == environment_id).first()
        if not environment:
            raise Exception(f"测试环境不存在: {environment_id}")
        
        # 创建调试记录
        debug_record = TestDebugRecord(
            test_case_id=test_case_id,
            environment_id=environment_id,
            task_id=self.request.id,
            execution_status="running",
            execution_time=execution_start_time
        )
        db.add(debug_record)
        db.commit()
        db.refresh(debug_record)
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': '开始执行JMeter性能测试...'}
        )
        
        # 创建临时JMX文件，并修改线程数
        import xml.etree.ElementTree as ET
        import re
        
        # 检查是否有XML声明
        xml_declaration = ""
        jmx_content = test_case.test_code
        if jmx_content.strip().startswith('<?xml'):
            # 提取XML声明
            decl_match = re.match(r'<\?xml[^>]*\?>', jmx_content)
            if decl_match:
                xml_declaration = decl_match.group(0) + "\n"
                jmx_content = jmx_content[decl_match.end():].strip()
        
        try:
            # 解析JMX文件（XML格式）
            root = ET.fromstring(jmx_content)
            
            # 查找所有ThreadGroup元素，更新线程数
            thread_count_updated = 0
            for thread_group in root.findall('.//ThreadGroup'):
                num_threads_elem = thread_group.find(".//stringProp[@name='ThreadGroup.num_threads']")
                if num_threads_elem is not None:
                    num_threads_elem.text = str(threads)
                    thread_count_updated += 1
                    print(f"[execute_jmeter_performance_test_task] 已更新ThreadGroup线程数: {threads}")
            
            if thread_count_updated == 0:
                print(f"[execute_jmeter_performance_test_task] 警告：未找到ThreadGroup.num_threads元素，尝试使用正则表达式")
                raise Exception("未找到ThreadGroup元素")
            
            # 将修改后的XML写回字符串
            modified_jmx_content = ET.tostring(root, encoding='unicode')
            # 添加XML声明（如果有）
            if xml_declaration:
                modified_jmx_content = xml_declaration + modified_jmx_content
        except Exception as e:
            # 如果XML解析失败，尝试使用正则表达式修改
            print(f"[execute_jmeter_performance_test_task] XML解析失败，使用正则表达式: {e}")
            # 使用正则表达式替换线程数
            pattern = r'(<stringProp name="ThreadGroup\.num_threads">)\d+(</stringProp>)'
            # 使用函数替换，避免\1{threads}\2被当作单个分组编号造成invalid group reference
            def replace_threads(match):
                return f"{match.group(1)}{threads}{match.group(2)}"
            try:
                modified_jmx_content = re.sub(pattern, replace_threads, test_case.test_code)
            except re.error as regex_error:
                # 极端情况下正则本身解析失败（例如内容异常），直接回退到原始脚本
                print(f"[execute_jmeter_performance_test_task] 正则替换线程数失败，使用原始JMX: {regex_error}")
                modified_jmx_content = test_case.test_code
            if modified_jmx_content == test_case.test_code:
                print(f"[execute_jmeter_performance_test_task] 警告：正则表达式未找到匹配项，使用原始JMX文件")
                modified_jmx_content = test_case.test_code
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jmx', delete=False, dir='/tmp', encoding='utf-8') as f:
            f.write(modified_jmx_content)
            temp_jmx_file = f.name
        
        try:
            # 更新任务进度
            self.update_state(
                state='PROGRESS',
                meta={'progress': 30, 'message': '正在检查JMeter容器...'}
            )
            
            # 检查JMeter容器是否运行（直接尝试执行命令，如果失败说明容器不存在或未运行）
            # 使用docker exec测试容器是否可访问，比docker ps更可靠
            try:
                test_result = subprocess.run(
                    ['docker', 'exec', 'api_test_jmeter', 'echo', 'test'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if test_result.returncode != 0:
                    raise Exception("JMeter容器未运行或无法访问")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
                # 如果docker命令不存在，尝试使用docker ps
                try:
                    result = subprocess.run(
                        ['docker', 'ps', '--filter', 'name=api_test_jmeter', '--format', '{{.Names}}'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode != 0 or not result.stdout.strip():
                        raise Exception("JMeter容器不存在或未运行，请确保容器已启动")
                except Exception as ps_error:
                    raise Exception(f"无法检查JMeter容器状态: {str(ps_error)}")
            
            # 将JMX文件复制到容器中
            self.update_state(
                state='PROGRESS',
                meta={'progress': 40, 'message': '正在上传JMX脚本到容器...'}
            )
            
            # 使用docker cp复制文件
            subprocess.run([
                'docker', 'cp', temp_jmx_file, 
                f'api_test_jmeter:/app/jmeter-scripts/test_{test_case_id}.jmx'
            ], check=True)
            
            container_script_path = f'/app/jmeter-scripts/test_{test_case_id}.jmx'
            
            # 更新任务进度
            self.update_state(
                state='PROGRESS',
                meta={'progress': 50, 'message': f'正在执行JMeter测试（线程数: {threads}）...'}
            )
            
            # 执行JMeter测试
            result_dir = f'/app/jmeter-results/test_{test_case_id}'
            result_file = f'{result_dir}/result.jtl'
            log_file = f'{result_dir}/jmeter.log'
            
            # 创建结果目录（使用docker exec）
            subprocess.run([
                'docker', 'exec', 'api_test_jmeter',
                'mkdir', '-p', result_dir
            ], check=True)
            
            # 清理旧的结果文件和报告目录
            print(f"[execute_jmeter_performance_test_task] 清理旧的结果文件和报告目录...")
            
            # 1. 清理旧的result.jtl文件（如果存在）
            try:
                check_file = subprocess.run(
                    ['docker', 'exec', 'api_test_jmeter', 'test', '-f', result_file],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if check_file.returncode == 0:
                    print(f"[execute_jmeter_performance_test_task] 检测到旧的result.jtl文件，开始删除...")
                    subprocess.run(
                        ['docker', 'exec', 'api_test_jmeter', 'rm', '-f', result_file],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=True
                    )
                    print(f"[execute_jmeter_performance_test_task] result.jtl文件已删除")
            except Exception as e:
                print(f"[execute_jmeter_performance_test_task] 清理result.jtl文件时出错: {e}")
            
            # 2. 清理旧的HTML报告目录（如果存在且不为空）
            html_report_dir = f'{result_dir}/html-report'
            try:
                # 先检查目录是否存在
                check_result = subprocess.run(
                    ['docker', 'exec', 'api_test_jmeter', 'test', '-d', html_report_dir],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if check_result.returncode == 0:
                    # 目录存在，删除它
                    print(f"[execute_jmeter_performance_test_task] 检测到报告目录存在，开始清理...")
                    rm_result = subprocess.run(
                        ['docker', 'exec', 'api_test_jmeter', 'rm', '-rf', html_report_dir],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=True
                    )
                    print(f"[execute_jmeter_performance_test_task] HTML报告目录已成功清理")
                else:
                    print(f"[execute_jmeter_performance_test_task] 报告目录不存在，无需清理")
            except subprocess.CalledProcessError as e:
                print(f"[execute_jmeter_performance_test_task] 清理报告目录失败: {e.stderr if e.stderr else str(e)}")
                # 即使清理失败，也继续执行，让JMeter自己处理
            except Exception as e:
                print(f"[execute_jmeter_performance_test_task] 清理报告目录时出错: {e}")
                # 即使清理失败，也继续执行
            
            # 构建JMeter命令
            jmeter_cmd = f"jmeter -n -t {container_script_path} -l {result_file} -j {log_file} -e -o {html_report_dir}"
            
            print(f"[execute_jmeter_performance_test_task] 准备执行JMeter命令: {jmeter_cmd}")
            print(f"[execute_jmeter_performance_test_task] 线程数: {threads}, 脚本路径: {container_script_path}")
            
            # 执行命令（使用docker exec）
            print(f"[execute_jmeter_performance_test_task] 开始执行JMeter命令...")
            
            # 设置超时时间：根据线程数和测试持续时间估算
            # 默认测试持续300秒，加上启动和报告生成时间，设置总超时为400秒
            jmeter_timeout = 400
            
            # 使用线程定期更新进度
            import threading
            import time
            progress_update_stop = threading.Event()
            
            def update_progress_periodically():
                """定期更新进度，显示JMeter正在执行"""
                elapsed = 0
                while not progress_update_stop.wait(10):  # 每10秒更新一次
                    elapsed += 10
                    try:
                        # 计算进度：50% + (elapsed / jmeter_timeout) * 40%
                        # 50%是执行前的进度，40%是执行期间的进度范围
                        progress = min(50 + int((elapsed / jmeter_timeout) * 40), 90)
                        # 仅在绑定了任务id时更新celery state，避免 task_id 为空告警
                        if getattr(self, "request", None) and getattr(self.request, "id", None):
                            self.update_state(
                                state='PROGRESS',
                                meta={'progress': progress, 'message': f'正在执行JMeter测试（线程数: {threads}），已运行{elapsed}秒...'}
                            )
                        # 同时更新数据库中的调试记录进度（前端可能从数据库读取）
                        if debug_record:
                            debug_record.execution_status = "running"
                            db.commit()
                        print(f"[execute_jmeter_performance_test_task] JMeter执行中，已运行{elapsed}秒，进度: {progress}%")
                    except Exception as e:
                        print(f"[execute_jmeter_performance_test_task] 更新进度时出错: {e}")
                        pass
                    if elapsed >= jmeter_timeout - 10:
                        break
            
            progress_thread = threading.Thread(target=update_progress_periodically, daemon=True)
            progress_thread.start()
            
            # 初始化变量，确保在异常情况下也能使用
            returncode = -1
            exec_stdout = ""
            exec_stderr = ""
            
            try:
                # 使用Popen而不是run，避免输出缓冲区过大导致卡住
                import subprocess as sp
                exec_process = sp.Popen(
                    ['docker', 'exec', '-w', '/app', 'api_test_jmeter', 'sh', '-c', jmeter_cmd],
                    stdout=sp.PIPE,
                    stderr=sp.PIPE,
                    text=True,
                    bufsize=1  # 行缓冲
                )
                
                # 等待进程完成，但定期检查进度更新和JTL文件生成
                import time as time_module
                start_wait = time_module.time()
                last_check_time = start_wait
                while exec_process.poll() is None:
                    # 检查是否超时
                    current_time = time_module.time()
                    if current_time - start_wait > jmeter_timeout:
                        exec_process.kill()
                        progress_update_stop.set()
                        raise Exception(f"JMeter测试执行超时（{jmeter_timeout}秒）")
                    
                    # 每5秒检查一次JTL文件是否生成（如果生成了，说明测试可能已完成，即使进程还没退出）
                    if current_time - last_check_time >= 5:
                        try:
                            check_jtl = subprocess.run(
                                ['docker', 'exec', 'api_test_jmeter', 'test', '-f', result_file],
                                capture_output=True,
                                timeout=2
                            )
                            if check_jtl.returncode == 0:
                                # JTL文件已生成，检查文件大小是否在增长（说明测试还在进行）
                                size_result = subprocess.run(
                                    ['docker', 'exec', 'api_test_jmeter', 'stat', '-c', '%s', result_file],
                                    capture_output=True,
                                    text=True,
                                    timeout=2
                                )
                                if size_result.returncode == 0:
                                    file_size = int(size_result.stdout.strip())
                                    # 如果文件大小大于1MB，说明测试在进行，继续等待
                                    # 如果文件大小稳定且测试时长已超过预期，可以提前结束等待
                                    test_duration = current_time - start_wait
                                    if file_size > 1024 * 1024 and test_duration > 60:
                                        # 测试已运行超过1分钟且有结果，可以尝试结束等待
                                        print(f"[execute_jmeter_performance_test_task] 检测到JTL文件已生成（{file_size}字节），测试可能已完成")
                        except:
                            pass
                        last_check_time = current_time
                    
                    time_module.sleep(1)  # 每秒检查一次
                
                # 获取输出（使用非阻塞方式，避免卡住）
                try:
                    stdout, stderr = exec_process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    # 如果communicate超时，说明输出太大，直接终止并读取部分输出
                    print(f"[execute_jmeter_performance_test_task] 警告：进程输出读取超时，可能输出过大")
                    exec_process.kill()
                    stdout, stderr = exec_process.communicate(timeout=2)
                
                returncode = exec_process.returncode
                
                progress_update_stop.set()
                print(f"[execute_jmeter_performance_test_task] JMeter命令执行完成，退出码: {returncode}")
                
                # 如果退出码不为0，记录错误信息
                if returncode != 0:
                    error_msg = stderr[:1000] if stderr else "未知错误"
                    print(f"[execute_jmeter_performance_test_task] JMeter执行失败: {error_msg}")
                
                # 保存输出用于后续使用
                exec_stdout = stdout if stdout else ""
                exec_stderr = stderr if stderr else ""
            except subprocess.TimeoutExpired:
                progress_update_stop.set()
                print(f"[execute_jmeter_performance_test_task] JMeter命令执行超时（{jmeter_timeout}秒）")
                # 尝试终止JMeter进程
                try:
                    subprocess.run(
                        ['docker', 'exec', 'api_test_jmeter', 'pkill', '-f', f'test_{test_case_id}.jmx'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                except:
                    pass
                raise Exception(f"JMeter测试执行超时（{jmeter_timeout}秒），请检查测试配置或增加超时时间")
            
            execution_duration = int((datetime.now() - execution_start_time).total_seconds())
            
            # 读取结果文件
            self.update_state(
                state='PROGRESS',
                meta={'progress': 80, 'message': '正在读取测试结果...'}
            )
            
            # 读取日志文件
            log_content = ""
            try:
                log_result = subprocess.run(
                    ['docker', 'exec', 'api_test_jmeter', 'cat', log_file],
                    capture_output=True,
                    text=True
                )
                if log_result.returncode == 0:
                    log_content = log_result.stdout
            except:
                pass
            
            # 读取结果文件（JTL格式）
            result_content = ""
            try:
                result_read = subprocess.run(
                    ['docker', 'exec', 'api_test_jmeter', 'cat', result_file],
                    capture_output=True,
                    text=True
                )
                if result_read.returncode == 0:
                    result_content = result_read.stdout
            except:
                pass
            
            # 判断执行结果
            output = f"Exit Code: {returncode}\n\n"
            output += f"=== JMeter Command Output ===\n{exec_stdout}\n\n"
            if exec_stderr:
                output += f"=== JMeter Error Output ===\n{exec_stderr}\n\n"
            output += f"=== JMeter Log ===\n{log_content}\n\n"
            output += f"=== Test Results ===\n{result_content[:5000]}\n"  # 限制长度
            
            # 检查执行结果：不仅检查returncode，还要检查日志中的错误
            is_success = returncode == 0
            # 检查日志中是否有错误
            if is_success:
                # 检查日志中是否有"Test failed!"或"ERROR"
                log_lower = (log_content + exec_stderr).lower()
                if "test failed!" in log_lower or "error generating the report" in log_lower:
                    # 检查是否有实际的测试错误（排除警告）
                    if "nosuchelementexception" in log_lower or "nullpointerexception" in log_lower:
                        is_success = False
                # 检查结果文件是否为空或没有有效样本
                if result_content and len(result_content.strip()) > 0:
                    # 检查是否有非标题行的数据
                    lines = result_content.strip().split('\n')
                    data_lines = [l for l in lines if l.strip() and not l.strip().startswith('timeStamp')]
                    if len(data_lines) == 0:
                        # 没有测试样本，可能是执行失败
                        is_success = False
            
            # 更新调试记录
            debug_record.execution_status = "success" if is_success else "failed"
            debug_record.execution_result = "执行成功" if is_success else "执行失败"
            debug_record.debug_logs = output
            debug_record.error_message = None if is_success else output
            debug_record.duration = execution_duration
            db.commit()
            
            # 更新任务进度
            self.update_state(
                state='PROGRESS',
                meta={
                    'progress': 100,
                    'message': '执行完成' if is_success else '执行失败',
                    'debug_logs': output
                }
            )
            
            return {
                "status": "success" if is_success else "failed",
                "test_case_id": test_case_id,
                "output": output,
                "debug_logs": output,
                "message": "执行成功" if is_success else "执行失败",
                "exit_code": returncode,
                "duration": execution_duration
            }
            
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_jmx_file)
            except:
                pass
        
    except Exception as e:
        import traceback
        error_msg = f"执行JMeter性能测试失败: {str(e)}"
        execution_duration = int((datetime.now() - execution_start_time).total_seconds()) if execution_start_time else 0
        
        # 保存调试记录
        try:
            if debug_record:
                debug_record.execution_status = "failed"
                debug_record.execution_result = "执行异常"
                debug_record.error_message = error_msg
                debug_record.debug_logs = traceback.format_exc()
                debug_record.duration = execution_duration
                db.commit()
            else:
                debug_record = TestDebugRecord(
                    test_case_id=test_case_id,
                    environment_id=environment_id,
                    task_id=self.request.id,
                    execution_status="failed",
                    execution_result="执行异常",
                    error_message=error_msg,
                    debug_logs=traceback.format_exc(),
                    duration=execution_duration,
                    execution_time=execution_start_time
                )
                db.add(debug_record)
                db.commit()
        except Exception as save_error:
            print(f"保存调试记录失败: {save_error}")
            traceback.print_exc()
        
        print(error_msg)
        traceback.print_exc()
        
        # 使用安全的失败状态更新
        safe_error_msg = safe_update_failure_state(self, error_msg)
        
        # 使用明确的异常类型，确保Celery可以正确序列化
        raise RuntimeError(safe_error_msg)
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=1800, soft_time_limit=1700)
def parse_document_task(
    self,
    document_id: int,
    file_path: str,
    file_type: str,
    is_few_shot: bool = False
):
    """
    异步解析文档任务 - 解析文档并提取接口信息保存到数据库
    
    Args:
        document_id: 文档ID
        file_path: 文件路径或URL
        file_type: 文件类型
        is_few_shot: 是否为接口测试参考用例
    """
    db = SessionLocal()
    try:
        from app.models import Document, APIInterface, DocumentAPIInterface, Project
        from app.services.enhanced_document_parser import EnhancedDocumentParser
        from app.services.vector_service import VectorService
        import asyncio
        
        # 获取文档记录
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise Exception(f"文档不存在: {document_id}")
        
        project_id = document.project_id
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': '开始解析文档...'}
        )
        
        # 创建解析器
        parser = EnhancedDocumentParser()
        
        # 解析文档（异步方法需要在线程中运行）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            parse_result = loop.run_until_complete(parser.parse(file_path, file_type))
        finally:
            loop.close()
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 40, 'message': '解析完成，正在提取接口信息...'}
        )
        
        # 提取接口信息
        try:
            api_interfaces = parser.extract_api_interfaces(parse_result)
            print(f"[解析文档] 从文档 {document_id} 提取了 {len(api_interfaces)} 个接口")
        except Exception as e:
            print(f"[解析文档] 提取接口信息失败: {e}")
            api_interfaces = []
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 60, 'message': f'正在保存 {len(api_interfaces)} 个接口信息到数据库...'}
        )
        
        # 保存接口信息到数据库
        created_interfaces_count = 0
        created_document_interfaces_count = 0
        if api_interfaces:
            for iface_data in api_interfaces:
                try:
                    # 准备接口数据
                    interface_name = iface_data.get("name", "")[:200] if iface_data.get("name") else ""
                    interface_description = iface_data.get("description", "")[:500] if iface_data.get("description") else ""
                    interface_url = iface_data.get("url", "")
                    interface_method = iface_data.get("method", "GET")
                    
                    # 1. 保存到 APIInterface 表（通用接口表）
                    existing_api = db.query(APIInterface).filter(
                        APIInterface.project_id == project_id,
                        APIInterface.url == interface_url,
                        APIInterface.method == interface_method
                    ).first()
                    
                    if not existing_api:
                        db_interface = APIInterface(
                            project_id=project_id,
                            name=interface_name,
                            method=interface_method,
                            url=interface_url,
                            description=interface_description,
                            headers=json.dumps(iface_data.get("headers", {}), ensure_ascii=False) if iface_data.get("headers") else None,
                            params=json.dumps(iface_data.get("params", {}), ensure_ascii=False) if iface_data.get("params") else None,
                            body=json.dumps(iface_data.get("request_body", iface_data.get("body", {})), ensure_ascii=False) if (iface_data.get("request_body") or iface_data.get("body")) else None,
                            response_schema=json.dumps(iface_data.get("response_schema", {}), ensure_ascii=False) if iface_data.get("response_schema") else None
                        )
                        db.add(db_interface)
                        created_interfaces_count += 1
                    else:
                        print(f"[解析文档] APIInterface已存在，跳过: {interface_method} {interface_url}")
                    
                    # 2. 保存到 DocumentAPIInterface 表（文档接口表，用于接口列表页面展示）
                    existing_doc_interface = db.query(DocumentAPIInterface).filter(
                        DocumentAPIInterface.document_id == document_id,
                        DocumentAPIInterface.project_id == project_id,
                        DocumentAPIInterface.url == interface_url,
                        DocumentAPIInterface.method == interface_method
                    ).first()
                    
                    if not existing_doc_interface:
                        # 解析URL获取base_url和path
                        base_url = ""
                        path = ""
                        if interface_url:
                            try:
                                from urllib.parse import urlparse
                                parsed = urlparse(interface_url)
                                base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
                                path = parsed.path if parsed.path else ""
                            except:
                                pass
                        
                        doc_interface = DocumentAPIInterface(
                            document_id=document_id,
                            project_id=project_id,
                            name=interface_name,
                            method=interface_method,
                            url=interface_url,
                            base_url=base_url if base_url else iface_data.get("base_url", ""),
                            path=path if path else iface_data.get("path", ""),
                            service=iface_data.get("service", ""),
                            headers=json.dumps(iface_data.get("headers", {}), ensure_ascii=False) if iface_data.get("headers") else None,
                            params=json.dumps(iface_data.get("params", {}), ensure_ascii=False) if iface_data.get("params") else None,
                            request_body=json.dumps(iface_data.get("request_body", iface_data.get("body", {})), ensure_ascii=False) if (iface_data.get("request_body") or iface_data.get("body")) else None,
                            response_schema=json.dumps(iface_data.get("response_schema", {}), ensure_ascii=False) if iface_data.get("response_schema") else None,
                            status_code=iface_data.get("status_code", 200),
                            description=interface_description,
                            tags=json.dumps(iface_data.get("tags", []), ensure_ascii=False) if iface_data.get("tags") else None,
                            deprecated=iface_data.get("deprecated", False),
                            version=iface_data.get("version", ""),
                            file_id=str(document_id)  # 使用document_id作为file_id
                        )
                        db.add(doc_interface)
                        created_document_interfaces_count += 1
                    else:
                        print(f"[解析文档] DocumentAPIInterface已存在，跳过: {interface_method} {interface_url}")
                        
                except Exception as e:
                    print(f"[解析文档] 保存接口失败: {iface_data.get('url')} - {e}")
                    import traceback
                    traceback.print_exc()
            
            # 批量保存所有接口
            try:
                db.commit()
                print(f"[解析文档] 成功保存 {created_interfaces_count} 个新接口到APIInterface表，{created_document_interfaces_count} 个新接口到DocumentAPIInterface表")
            except Exception as e:
                db.rollback()
                print(f"[解析文档] 保存接口到数据库失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 80, 'message': '正在更新文档状态...'}
        )
        
        # 更新文档状态和解析结果
        document.status = "parsed"
        
        # 保留原有的 is_few_shot_example 标记
        existing_parse_result = {}
        existing_is_few_shot = is_few_shot  # 默认使用传入的参数
        if document.parse_result:
            try:
                existing_parse_result = json.loads(document.parse_result)
                # 优先使用原有的标记
                if "is_few_shot_example" in existing_parse_result:
                    existing_is_few_shot = existing_parse_result["is_few_shot_example"]
                    print(f"[解析文档] 从原有parse_result读取 is_few_shot_example: {existing_is_few_shot}")
            except Exception as e:
                print(f"[解析文档] 解析原有parse_result失败: {e}")
        
        # 合并解析结果，确保 is_few_shot_example 标记在最顶层
        if isinstance(parse_result, dict):
            final_parse_result = parse_result.copy()
        else:
            final_parse_result = {"content": parse_result}
        
        # 确保 is_few_shot_example 标记在最顶层
        final_parse_result["is_few_shot_example"] = existing_is_few_shot
        print(f"[解析文档] 文档 {document_id} 最终 is_few_shot_example: {existing_is_few_shot}")
        
        document.parse_result = json.dumps(final_parse_result, ensure_ascii=False)
        db.commit()
        print(f"[解析文档] 已保存文档 {document_id} 的 parse_result，包含 is_few_shot_example={existing_is_few_shot}")
        
        # 清除相关缓存
        try:
            from app.services.cache_service import cache_service
            # 清除项目的API接口缓存
            cache_service.invalidate_cache(f"api_interfaces:{project_id}*")
            # 清除文档列表缓存，确保解析完成后的文档状态能及时更新（清除所有相关的缓存键）
            cache_service.invalidate_cache(f"documents:{project_id}*")
            print(f"[解析文档] 已清除项目 {project_id} 的接口和文档列表缓存（所有 is_few_shot 变体）")
        except Exception as e:
            print(f"[解析文档] 清除缓存失败: {e}")
        
        # 如果启用了向量服务，将解析结果存入向量数据库
        try:
            vector_service = VectorService()
            # 这里可以添加向量存储逻辑
        except Exception as e:
            print(f"[解析文档] 向量存储失败（可选功能）: {e}")
        
        return {
            "status": "success",
            "document_id": document_id,
            "parse_result": parse_result,
            "interfaces_extracted": len(api_interfaces),
            "interfaces_saved": created_interfaces_count,
            "document_interfaces_saved": created_document_interfaces_count
        }
        
    except Exception as e:
        import traceback
        error_msg = f"解析文档失败: {str(e)}"
        
        # 更新文档状态为错误
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                document.status = "error"
                # 保留原始错误信息，但限制长度
                # 保留原有的 is_few_shot_example 标记
                existing_is_few_shot = is_few_shot
                if document.parse_result:
                    try:
                        existing_parse_result = json.loads(document.parse_result)
                        if "is_few_shot_example" in existing_parse_result:
                            existing_is_few_shot = existing_parse_result["is_few_shot_example"]
                    except:
                        pass
                
                error_info = {
                    "error": error_msg[:500] if len(error_msg) > 500 else error_msg,
                    "traceback": traceback.format_exc()[:1000] if len(traceback.format_exc()) > 1000 else traceback.format_exc(),
                    "is_few_shot_example": existing_is_few_shot
                }
                document.parse_result = json.dumps(error_info, ensure_ascii=False)
                db.commit()
                print(f"[解析文档] 已更新文档 {document_id} 状态为 error")
        except Exception as update_error:
            print(f"[解析文档] 更新文档状态失败: {update_error}")
            import traceback
            traceback.print_exc()
        
        print(f"[解析文档] 错误: {error_msg}")
        traceback.print_exc()
        
        # 使用安全的状态更新方法
        safe_error_msg = str(error_msg)[:500] if len(str(error_msg)) > 500 else str(error_msg)
        self.update_state(
            state='PROGRESS',
            meta={'progress': 0, 'message': safe_error_msg, 'status': 'failed', 'error': safe_error_msg}
        )
        
        raise Exception(error_msg)
    finally:
        try:
            db.close()
        except:
            pass


@celery_app.task(bind=True, time_limit=1800, soft_time_limit=1700)
def generate_test_case_task(
    self,
    test_case_id: int,
    case_type: str,
    project_id: int,
    api_interface_id: int,
    module: Optional[str] = None
):
    """
    生成单个测试用例任务
    
    Args:
        test_case_id: 测试用例ID
        case_type: 用例类型 (pytest 或 jmeter)
        project_id: 项目ID
        api_interface_id: API接口ID
        module: 模块名称
    """
    db = SessionLocal()
    try:
        from app.models import TestCase, APIInterface, DocumentAPIInterface
        from app.services.test_case_generator import PytestCaseGenerator, JMeterCaseGenerator
        
        # 获取测试用例
        test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
        if not test_case:
            raise Exception(f"测试用例不存在: {test_case_id}")
        
        # 获取API接口信息
        api_interface = db.query(APIInterface).filter(APIInterface.id == api_interface_id).first()
        if not api_interface:
            # 尝试从DocumentAPIInterface获取
            api_interface = db.query(DocumentAPIInterface).filter(DocumentAPIInterface.id == api_interface_id).first()
            if not api_interface:
                raise Exception(f"API接口不存在: {api_interface_id}")
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': f'开始生成{case_type}测试用例...'}
        )
        
        # 构建接口信息字典
        interface_info = {
            'id': api_interface.id,
            'name': api_interface.name or 'test_api',
            'method': getattr(api_interface, 'method', 'GET') or 'GET',
            'url': getattr(api_interface, 'url', '') or '',
            'path': getattr(api_interface, 'path', '') or '',
            'headers': getattr(api_interface, 'headers', '{}') or '{}',
            'params': getattr(api_interface, 'params', '{}') or '{}',
            'body': getattr(api_interface, 'body', '{}') or getattr(api_interface, 'request_body', '{}') or '{}',
            'description': getattr(api_interface, 'description', '') or ''
        }
        
        # 解析JSON字符串
        if isinstance(interface_info['headers'], str):
            try:
                interface_info['headers'] = json.loads(interface_info['headers'])
            except:
                interface_info['headers'] = {}
        if isinstance(interface_info['params'], str):
            try:
                interface_info['params'] = json.loads(interface_info['params'])
            except:
                interface_info['params'] = {}
        if isinstance(interface_info['body'], str):
            try:
                interface_info['body'] = json.loads(interface_info['body'])
            except:
                interface_info['body'] = {}
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 50, 'message': '正在生成测试代码...'}
        )
        
        # 根据用例类型选择生成器
        if case_type == 'jmeter':
            generator = JMeterCaseGenerator()
        else:
            generator = PytestCaseGenerator()
        
        # 生成测试代码
        test_code = generator.generate_test_case(
            api_interface=interface_info,
            project_id=project_id
        )
        
        # 更新测试用例
        test_case.test_code = test_code
        test_case.status = "active"
        test_case.generation_progress = 100
        db.commit()
        
        # 生成成功后清理测试用例列表缓存，确保前端立刻能看到新用例
        try:
            cache_service.invalidate_cache(f"test_cases:{project_id}:*")
        except Exception as cache_error:
            print(f"[测试用例生成] 清理缓存失败: {cache_error}")
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 100, 'message': '测试用例生成完成'}
        )
        
        return {
            "status": "success",
            "test_case_id": test_case_id,
            "message": "测试用例生成完成"
        }
        
    except Exception as e:
        db.rollback()
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        
        # 更新测试用例状态为失败，并保存错误信息
        try:
            test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
            if test_case:
                test_case.status = "failed"
                test_case.generation_progress = 0
                # 保存错误信息（限制长度避免数据库字段溢出）
                safe_error_msg = error_msg[:500] if len(error_msg) <= 500 else error_msg[:500] + "..."
                test_case.error_message = safe_error_msg
                db.commit()
        except Exception as save_error:
            print(f"保存测试用例错误信息失败: {save_error}")
            import traceback
            traceback.print_exc()
        
        safe_error_msg = safe_update_failure_state(self, f'生成失败: {error_msg}')
        raise RuntimeError(f"生成测试用例失败: {safe_error_msg}")
    
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=3600, soft_time_limit=3500)
def batch_generate_test_cases_task(
    self,
    test_case_ids: List[int],
    case_type: str,
    project_id: int,
    module: Optional[str] = None
):
    """
    批量生成测试用例任务
    
    Args:
        test_case_ids: 测试用例ID列表
        case_type: 用例类型 (pytest 或 jmeter)
        project_id: 项目ID
        module: 模块名称
    """
    db = SessionLocal()
    try:
        from app.models import TestCase
        
        total = len(test_case_ids)
        success_count = 0
        failed_count = 0
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 0, 'message': f'开始批量生成{total}个测试用例...'}
        )
        
        for index, test_case_id in enumerate(test_case_ids):
            try:
                # 获取测试用例
                test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
                if not test_case:
                    failed_count += 1
                    continue
                
                # 获取API接口ID
                api_interface_id = test_case.api_interface_id
                if not api_interface_id:
                    failed_count += 1
                    continue
                
                # 直接调用生成逻辑（不使用Celery任务，避免嵌套）
                from app.models import APIInterface, DocumentAPIInterface
                from app.services.test_case_generator import PytestCaseGenerator, JMeterCaseGenerator
                
                # 获取API接口信息
                api_interface = db.query(APIInterface).filter(APIInterface.id == api_interface_id).first()
                if not api_interface:
                    api_interface = db.query(DocumentAPIInterface).filter(DocumentAPIInterface.id == api_interface_id).first()
                    if not api_interface:
                        failed_count += 1
                        continue
                
                # 构建接口信息字典
                interface_info = {
                    'id': api_interface.id,
                    'name': api_interface.name or 'test_api',
                    'method': getattr(api_interface, 'method', 'GET') or 'GET',
                    'url': getattr(api_interface, 'url', '') or '',
                    'path': getattr(api_interface, 'path', '') or '',
                    'headers': getattr(api_interface, 'headers', '{}') or '{}',
                    'params': getattr(api_interface, 'params', '{}') or '{}',
                    'body': getattr(api_interface, 'body', '{}') or getattr(api_interface, 'request_body', '{}') or '{}',
                    'description': getattr(api_interface, 'description', '') or ''
                }
                
                # 解析JSON字符串
                if isinstance(interface_info['headers'], str):
                    try:
                        interface_info['headers'] = json.loads(interface_info['headers'])
                    except:
                        interface_info['headers'] = {}
                if isinstance(interface_info['params'], str):
                    try:
                        interface_info['params'] = json.loads(interface_info['params'])
                    except:
                        interface_info['params'] = {}
                if isinstance(interface_info['body'], str):
                    try:
                        interface_info['body'] = json.loads(interface_info['body'])
                    except:
                        interface_info['body'] = {}
                
                # 根据用例类型选择生成器
                if case_type == 'jmeter':
                    generator = JMeterCaseGenerator()
                else:
                    generator = PytestCaseGenerator()
                
                # 生成测试代码
                test_code = generator.generate_test_case(
                    api_interface=interface_info,
                    project_id=project_id
                )
                
                # 更新测试用例
                test_case.test_code = test_code
                test_case.status = "active"
                test_case.generation_progress = 100
                db.commit()
                
                success_count += 1
                
                # 更新进度
                progress = int((index + 1) / total * 100)
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'progress': progress,
                        'message': f'已生成 {index + 1}/{total} 个测试用例 (成功: {success_count}, 失败: {failed_count})'
                    }
                )
                
            except Exception as e:
                failed_count += 1
                print(f"生成测试用例 {test_case_id} 失败: {e}")
                continue
        
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 100,
                'message': f'批量生成完成 (成功: {success_count}, 失败: {failed_count})'
            }
        )
        
        return {
            "status": "success",
            "total": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "message": f"批量生成完成: 成功 {success_count} 个, 失败 {failed_count} 个"
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        
        safe_error_msg = safe_update_failure_state(self, f'批量生成失败: {error_msg}')
        raise RuntimeError(f"批量生成测试用例失败: {safe_error_msg}")
    
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=600, soft_time_limit=500)
def fix_test_case_with_deepseek_task(
    self,
    test_case_id: int,
    error_output: str,
    user_suggestion: str = ""
):
    """
    使用DeepSeek修复测试用例代码
    
    Args:
        test_case_id: 测试用例ID
        error_output: 执行错误信息
        user_suggestion: 用户提供的修复建议
    """
    db = SessionLocal()
    test_case = None
    
    try:
        from app.models import TestCase
        import requests
        import re
        
        # 获取测试用例
        test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
        if not test_case:
            raise Exception(f"测试用例不存在: {test_case_id}")
        
        if not test_case.test_code:
            raise Exception("测试用例没有测试代码")
        
        # 登录密码
        LOGIN_PASSWORD = "5973ea46bea2afae24c2ce6517fa6f7f"
        
        # 获取当前测试代码
        current_code = test_case.test_code
        
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 50,
                'message': '正在调用DeepSeek修复代码...'
            }
        )
        
        # 构建修复提示词
        user_suggestion_text = f"\n## 用户修复建议：\n{user_suggestion}\n" if user_suggestion else ""
        
        fix_prompt = f"""请修复以下Python测试代码中的错误。

## 测试用例信息：
- 用例名称: {test_case.name}
- 用例类型: {test_case.case_type}
- 用例描述: {test_case.description or '无'}

## 当前测试代码：
```python
{current_code}
```

## 执行错误信息：
```
{error_output}
```
{user_suggestion_text}
## 要求：
1. 修复代码中的错误，确保测试能够通过
2. 保留登录密码配置：{LOGIN_PASSWORD}
3. 保留所有调试日志（logger.debug）
4. 确保代码结构完整，包含所有必要的导入和类定义
5. 只返回修复后的Python代码，不要包含其他解释性文字
6. {"请参考用户的修复建议。" if user_suggestion else ""}

## 修复后的代码：
```python
"""
        
        # 调用DeepSeek API
        from app.config import settings
        deepseek_api_key = settings.DEEPSEEK_API_KEY
        deepseek_url = settings.DEEPSEEK_BASE_URL + "/v1/chat/completions" if settings.DEEPSEEK_BASE_URL else "https://api.deepseek.com/v1/chat/completions"
        
        response = requests.post(
            deepseek_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {deepseek_api_key}"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的Python测试代码修复专家。请根据错误信息修复测试代码，确保代码能够正确执行。"
                    },
                    {
                        "role": "user",
                        "content": fix_prompt
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 4000
            },
            timeout=120
        )
        
        if response.status_code != 200:
            raise Exception(f"DeepSeek API请求失败: {response.status_code} - {response.text}")
        
        result_json = response.json()
        fixed_code = result_json["choices"][0]["message"]["content"]
        
        # 清理生成的代码（移除markdown代码块标记）
        fixed_code = re.sub(r'```python\s*\n?', '', fixed_code)
        fixed_code = re.sub(r'```\s*\n?', '', fixed_code)
        fixed_code = fixed_code.strip()
        
        # 更新测试用例代码
        test_case.test_code = fixed_code
        db.commit()
        
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 100,
                'message': '代码修复完成'
            }
        )
        
        return {
            "status": "success",
            "message": "代码修复完成",
            "test_case_id": test_case_id,
            "fixed_code": fixed_code
        }
        
    except Exception as e:
        db.rollback()
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        
        safe_error_msg = safe_update_failure_state(self, f'修复失败: {error_msg}')
        raise RuntimeError(f"修复失败: {safe_error_msg}")
    
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=2400, soft_time_limit=2300)
def generate_interface_test_case_from_scenario_task(
    self,
    test_case_id: int,
    suite_id: int,
    project_id: int,
    api_interface_id: int,
    module: Optional[str] = None,
    scenario_test_cases: Optional[List[Dict[str, Any]]] = None,
    scenario_interfaces_info: Optional[List[Dict[str, Any]]] = None,
    login_interface_info: Optional[Dict[str, Any]] = None
):
    """
    从场景生成接口测试用例任务
    
    Args:
        test_case_id: 测试用例ID
        suite_id: 场景用例集ID
        project_id: 项目ID
        api_interface_id: API接口ID
        module: 模块名称
        scenario_test_cases: 场景测试用例列表
        scenario_interfaces_info: 场景接口信息列表
        login_interface_info: 登录接口信息
    """
    db = SessionLocal()
    try:
        from app.models import TestCase, APIInterface, DocumentAPIInterface
        from app.services.test_case_generator import PytestCaseGenerator
        
        # 获取测试用例
        test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
        if not test_case:
            raise Exception(f"测试用例不存在: {test_case_id}")
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': '开始从场景生成接口测试用例...'}
        )
        
        # 获取API接口信息
        api_interface = db.query(APIInterface).filter(APIInterface.id == api_interface_id).first()
        if not api_interface:
            api_interface = db.query(DocumentAPIInterface).filter(DocumentAPIInterface.id == api_interface_id).first()
            if not api_interface:
                raise Exception(f"API接口不存在: {api_interface_id}")
        
        # 构建接口信息字典
        interface_info = {
            'id': api_interface.id,
            'name': api_interface.name or 'test_api',
            'method': getattr(api_interface, 'method', 'GET') or 'GET',
            'url': getattr(api_interface, 'url', '') or '',
            'path': getattr(api_interface, 'path', '') or '',
            'headers': getattr(api_interface, 'headers', '{}') or '{}',
            'params': getattr(api_interface, 'params', '{}') or '{}',
            'body': getattr(api_interface, 'body', '{}') or getattr(api_interface, 'request_body', '{}') or '{}',
            'description': getattr(api_interface, 'description', '') or ''
        }
        
        # 解析JSON字符串
        if isinstance(interface_info['headers'], str):
            try:
                interface_info['headers'] = json.loads(interface_info['headers'])
            except:
                interface_info['headers'] = {}
        if isinstance(interface_info['params'], str):
            try:
                interface_info['params'] = json.loads(interface_info['params'])
            except:
                interface_info['params'] = {}
        if isinstance(interface_info['body'], str):
            try:
                interface_info['body'] = json.loads(interface_info['body'])
            except:
                interface_info['body'] = {}
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 50, 'message': '正在基于场景生成测试代码...'}
        )
        
        # 使用PytestCaseGenerator生成（场景用例通常是pytest类型）
        generator = PytestCaseGenerator(use_llm=True)  # 使用LLM生成，可以更好地利用场景信息
        
        # 生成测试代码（可以传入场景信息作为上下文）
        test_code = generator.generate_test_case(
            api_interface=interface_info,
            project_id=project_id
        )
        
        # 更新测试用例
        test_case.test_code = test_code
        test_case.status = "active"
        test_case.generation_progress = 100
        db.commit()
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 100, 'message': '从场景生成测试用例完成'}
        )
        
        return {
            "status": "success",
            "test_case_id": test_case_id,
            "message": "从场景生成测试用例完成"
        }
        
    except Exception as e:
        db.rollback()
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        
        try:
            test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
            if test_case:
                test_case.status = "failed"
                test_case.generation_progress = 0
                db.commit()
        except:
            pass
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 0, 'message': f'生成失败: {error_msg}', 'status': 'failed', 'error': error_msg}
        )
        
        raise Exception(f"从场景生成测试用例失败: {error_msg}")
    
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=2400, soft_time_limit=2300)
def generate_scenario_test_case_task(
    self,
    test_case_id: int,
    suite_id: int,
    project_id: int,
    interfaces_info: List[Dict[str, Any]],
    login_token: str,
    few_shot_interfaces: List[Dict[str, Any]],
    environment_info: Dict[str, Any],
    login_interface_info: Optional[Dict[str, Any]] = None,
    threads: int = 10
):
    """
    从场景接口用例生成接口测试用例任务
    
    Args:
        test_case_id: 测试用例ID
        suite_id: 测试用例集ID
        project_id: 项目ID
        interfaces_info: 场景业务接口信息列表（不包含登录接口，只包含需要生成测试用例的业务接口）
        login_token: 登录token占位符
        few_shot_interfaces: Few-shot示例接口信息
        login_interface_info: 登录接口信息（可选，单独传递）
        environment_info: 环境信息
        login_interface_info: 登录接口信息（与interfaces_info[0]相同）
        threads: 未使用（保留兼容性）
    """
    db = SessionLocal()
    test_case = None
    test_task = None
    
    try:
        from app.models import TestCase, TestCaseSuite, TestTask
        
        # 获取测试用例记录
        test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
        if not test_case:
            raise Exception(f"测试用例不存在: {test_case_id}")
        
        # 获取测试用例集
        suite = db.query(TestCaseSuite).filter(TestCaseSuite.id == suite_id).first()
        if not suite:
            raise Exception(f"测试用例集不存在: {suite_id}")
        
        # 创建TestTask记录用于跟踪生成任务（显示在场景接口测试任务tab中）
        test_task = TestTask(
            project_id=project_id,
            name=f"场景用例生成: {test_case.name}",
            scenario=f"生成场景测试用例 - {suite.name}",
            task_type="immediate",
            execution_task_type="scenario",  # 设置为scenario，使其显示在场景接口测试任务tab中
            test_case_suite_id=suite_id,
            status="running",
            execution_task_id=self.request.id,
            progress=0
        )
        db.add(test_task)
        db.commit()
        db.refresh(test_task)
        
        # 更新测试用例状态为"生成中"
        test_case.status = "generating"
        test_case.generation_progress = 0
        test_case.error_message = None
        db.commit()
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 0, 'message': '开始生成场景接口测试用例...'}
        )
        
        # 更新TestTask进度
        if test_task:
            test_task.progress = 0
            db.commit()
        
        # 验证场景接口列表
        if not interfaces_info or len(interfaces_info) == 0:
            raise Exception("场景接口列表为空，无法生成场景测试用例。请确保用例集中至少包含一个业务接口（不包括登录接口）。")
        
        # interfaces_info 只包含业务接口（不包含登录接口）
        # login_interface_info 是单独传递的登录接口信息
        business_interfaces = interfaces_info
        login_interface = login_interface_info
        
        if not business_interfaces:
            raise Exception("场景中除了登录接口外没有其他接口需要生成测试用例")
        
        print(f"[场景测试用例生成] 登录接口: {login_interface.get('name', '') if login_interface else '未配置'}")
        print(f"[场景测试用例生成] 业务接口数量: {len(business_interfaces)}")
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': '开始构建测试用例生成提示词...'}
        )
        test_case.generation_progress = 10
        if test_task:
            test_task.progress = 10
        db.commit()
        
        # 构建提示词
        prompt_parts = []
        
        # 1. 测试用例集信息
        prompt_parts.append(f"## 测试用例集信息\n")
        prompt_parts.append(f"- 用例集名称: {suite.name}\n")
        prompt_parts.append(f"- 用例集描述: {suite.description or '无'}\n")
        prompt_parts.append(f"\n")
        
        # 2. 环境信息
        prompt_parts.append(f"## 测试环境信息\n")
        prompt_parts.append(f"- 基础URL: {environment_info.get('base_url', '')}\n")
        prompt_parts.append(f"- 用户ID: {environment_info.get('xjid', '')}\n")
        prompt_parts.append(f"- 用户名: {environment_info.get('username', '')}\n")
        prompt_parts.append(f"\n")
        
        # 3. 登录接口信息（用于token提取）
        prompt_parts.append(f"## 登录接口信息（用于提取token）\n")
        if login_interface:
            login_path = login_interface.get('path', '') or login_interface.get('url', '')
            if '?' in login_path:
                login_path = login_path.split('?')[0]
            login_url_full = f"{login_interface.get('base_url', environment_info.get('base_url', ''))}{login_path}"
            
            prompt_parts.append(f"- 接口名称: {login_interface.get('name', '用户登录')}\n")
            prompt_parts.append(f"- 请求方法: {login_interface.get('method', 'POST')}\n")
            prompt_parts.append(f"- 请求URL: {login_url_full}\n")
            
            # 简化登录接口的请求体和响应体
            login_request_body = login_interface.get('request_body', {})
            if login_request_body:
                if isinstance(login_request_body, str):
                    try:
                        login_request_body = json.loads(login_request_body)
                    except:
                        login_request_body = {}
                request_body_str = json.dumps(login_request_body, ensure_ascii=False)
                if len(request_body_str) > 500:
                    request_body_str = request_body_str[:500] + "..."
                prompt_parts.append(f"- 请求体: {request_body_str}\n")
            
            # 提取token路径
            login_response_body = login_interface.get('response_body', {})
            if login_response_body:
                if isinstance(login_response_body, str):
                    try:
                        login_response_body = json.loads(login_response_body)
                    except:
                        login_response_body = {}
                
                if isinstance(login_response_body, dict):
                    def find_token_path(obj, path=""):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if 'token' in k.lower():
                                    return f"{path}.{k}" if path else k
                                result = find_token_path(v, f"{path}.{k}" if path else k)
                                if result:
                                    return result
                        elif isinstance(obj, list) and obj:
                            return find_token_path(obj[0], f"{path}[0]")
                        return None
                    
                    token_path = find_token_path(login_response_body)
                    if token_path:
                        prompt_parts.append(f"- Token提取路径: $.{token_path}\n")
                    else:
                        prompt_parts.append(f"- Token提取路径: $.data.token 或 $.token（需要根据实际响应调整）\n")
        else:
            # 如果没有登录接口，使用默认提示
            prompt_parts.append(f"- 接口名称: 用户登录（未配置）\n")
            prompt_parts.append(f"- 请求方法: POST\n")
            prompt_parts.append(f"- 请求URL: {environment_info.get('base_url', '')}/api/login（示例）\n")
            prompt_parts.append(f"- Token提取路径: $.data.token 或 $.token（需要根据实际响应调整）\n")
        
        prompt_parts.append(f"\n")
        prompt_parts.append(f"**重要：登录接口的响应体中的token需要被提取并传递给后续接口的请求头（Authorization: Bearer ${{token}}）或请求体中的token字段。**\n")
        prompt_parts.append(f"\n")
        
        # 4. 业务接口列表（需要生成测试用例的接口）
        prompt_parts.append(f"## 业务接口列表（需要生成测试用例）\n")
        prompt_parts.append(f"**重要：以下所有接口的测试用例必须生成在同一个Python文件中，每个接口都有独立的测试函数。**\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"以下接口需要生成pytest测试用例，每个接口都需要：\n")
        prompt_parts.append(f"1. 使用从登录接口提取的token（通过fixture传递）\n")
        prompt_parts.append(f"2. 根据请求体中的关键字段设置数据驱动测试用例\n")
        prompt_parts.append(f"3. 考虑正常场景、异常场景、边界值等情况\n")
        prompt_parts.append(f"4. **每个接口都有独立的测试函数，但所有测试函数都在同一个文件中**\n")
        prompt_parts.append(f"\n")
        
        for idx, interface in enumerate(business_interfaces, 1):
            interface_url = interface.get('url', '') or interface.get('path', '')
            if '?' in interface_url:
                interface_url = interface_url.split('?')[0]
            interface_url_full = f"{interface.get('base_url', environment_info.get('base_url', ''))}{interface_url}"
            
            prompt_parts.append(f"\n### 接口 {idx}: {interface.get('name', '')}\n")
            prompt_parts.append(f"- 请求方法: {interface.get('method', 'GET')}\n")
            prompt_parts.append(f"- 请求URL: {interface_url_full}\n")
            
            # 请求头（需要回填token）
            headers = interface.get('headers', {})
            if headers:
                # 标记哪些字段需要token
                token_headers = {k: v for k, v in headers.items() if 'token' in k.lower() or 'authorization' in k.lower()}
                if token_headers:
                    prompt_parts.append(f"- 请求头（需要token）: {json.dumps(token_headers, ensure_ascii=False)}\n")
                other_headers = {k: v for k, v in headers.items() if 'token' not in k.lower() and 'authorization' not in k.lower()}
                if other_headers:
                    important_headers = {k: v for k, v in other_headers.items() if k.lower() in ['content-type', 'accept']}
                    if important_headers:
                        prompt_parts.append(f"- 其他请求头: {json.dumps(important_headers, ensure_ascii=False)}\n")
            
            # 请求体（用于数据驱动）
            request_body = interface.get('request_body', {})
            if request_body:
                if isinstance(request_body, str):
                    try:
                        request_body = json.loads(request_body)
                    except:
                        request_body = {}
                request_body_str = json.dumps(request_body, ensure_ascii=False)
                if len(request_body_str) > 1000:
                    request_body_str = request_body_str[:1000] + "..."
                prompt_parts.append(f"- 请求体: {request_body_str}\n")
                prompt_parts.append(f"- **数据驱动字段**: 请识别请求体中的关键字段，用于生成数据驱动测试用例（正常值、异常值、边界值）\n")
            
            # 响应体（用于断言）
            response_body = interface.get('response_body', {})
            if response_body:
                if isinstance(response_body, str):
                    try:
                        response_body = json.loads(response_body)
                    except:
                        response_body = {}
                if isinstance(response_body, dict):
                    key_fields = []
                    for key in ['code', 'status', 'ret', 'success', 'result', 'message']:
                        if key in response_body:
                            key_fields.append(f"{key}={response_body[key]}")
                    if key_fields:
                        prompt_parts.append(f"- 响应关键字段: {', '.join(key_fields)}\n")
        
        prompt_parts.append(f"\n")
        prompt_parts.append(f"## 测试用例生成要求\n")
        prompt_parts.append(f"请生成完整的pytest测试用例代码，要求如下：\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 1. 代码结构\n")
        prompt_parts.append(f"- 使用pytest框架\n")
        prompt_parts.append(f"- 模块化设计，代码清晰易维护\n")
        prompt_parts.append(f"- 使用fixture管理token的提取和传递\n")
        prompt_parts.append(f"- 使用fixture进行Setup/Teardown（测试数据构造和清理）\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 2. Token管理\n")
        prompt_parts.append(f"- 创建一个fixture（如@pytest.fixture(scope='session')）来执行登录并提取token\n")
        prompt_parts.append(f"- token从登录接口的响应体中提取（使用JSON路径，如$.data.token）\n")
        prompt_parts.append(f"- token通过fixture传递给所有测试用例\n")
        prompt_parts.append(f"- 后续接口的请求头中的Authorization字段或请求体中的token字段要使用提取的token值\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 3. 数据驱动测试\n")
        prompt_parts.append(f"- 使用@pytest.mark.parametrize实现数据驱动\n")
        prompt_parts.append(f"- 根据每个接口的请求体中的关键字段生成测试数据\n")
        prompt_parts.append(f"- 测试数据要包括：\n")
        prompt_parts.append(f"  * 正常场景：有效的正常值\n")
        prompt_parts.append(f"  * 异常场景：无效值、错误格式、缺失必填字段等\n")
        prompt_parts.append(f"  * 边界值：最大值、最小值、空值、特殊字符等\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 4. Allure报告\n")
        prompt_parts.append(f"- 使用@allure.step装饰器标记测试步骤\n")
        prompt_parts.append(f"- 使用allure.attach添加请求和响应附件\n")
        prompt_parts.append(f"- 生成详细的测试报告，包含步骤和附件\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 5. 智能断言\n")
        prompt_parts.append(f"- 根据响应体的结构和关键字段进行智能断言\n")
        prompt_parts.append(f"- 验证HTTP状态码（200表示成功，其他状态码根据业务逻辑判断）\n")
        prompt_parts.append(f"- 验证响应体中的关键字段（如code、status、ret、success等）\n")
        prompt_parts.append(f"- 验证响应体的数据结构（字段是否存在、类型是否正确）\n")
        prompt_parts.append(f"- 对于正常场景，验证业务逻辑的正确性（如创建成功返回ID、查询成功返回数据等）\n")
        prompt_parts.append(f"- 对于异常场景，验证错误信息的正确性（如错误码、错误消息等）\n")
        prompt_parts.append(f"- 使用JSONPath或直接访问字典来提取和验证响应数据\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 6. 错误处理\n")
        prompt_parts.append(f"- 完善的异常处理和跳过机制\n")
        prompt_parts.append(f"- **重要：不要使用pytest.skip()跳过测试，除非有明确的业务逻辑要求（如某些接口需要特定条件才执行）**\n")
        prompt_parts.append(f"- 使用try-except捕获和处理异常，但不要跳过测试\n")
        prompt_parts.append(f"- 所有测试用例都应该正常执行，不要默认跳过\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"### 7. 代码示例结构\n")
        prompt_parts.append(f"```python\n")
        prompt_parts.append(f"import pytest\n")
        prompt_parts.append(f"import requests\n")
        prompt_parts.append(f"import json\n")
        prompt_parts.append(f"import allure\n")
        prompt_parts.append(f"from typing import Dict, Any\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"@pytest.fixture(scope='session')\n")
        prompt_parts.append(f"def base_url():\n")
        prompt_parts.append(f"    # 返回测试环境的基础URL\n")
        prompt_parts.append(f"    return '{environment_info.get('base_url', '')}'\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"@pytest.fixture(scope='session')\n")
        prompt_parts.append(f"def auth_token(base_url):\n")
        prompt_parts.append(f"    # 执行登录，提取token\n")
        prompt_parts.append(f"    # 如果登录失败，应该抛出异常，不要使用pytest.skip()\n")
        prompt_parts.append(f"    login_url = f\"{{base_url}}/V0.1/index.php\"\n")
        prompt_parts.append(f"    response = requests.post(login_url, json={{...}})\n")
        prompt_parts.append(f"    assert response.status_code == 200\n")
        prompt_parts.append(f"    return response.json()['data']['token']\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"@pytest.mark.parametrize('test_data', [...])\n")
        prompt_parts.append(f"def test_interface_name(auth_token, base_url, test_data):\n")
        prompt_parts.append(f"    with allure.step('发送请求'):\n")
        prompt_parts.append(f"        # 测试代码\n")
        prompt_parts.append(f"        # 不要使用pytest.skip()，所有测试都应该正常执行\n")
        prompt_parts.append(f"        response = requests.post(...)\n")
        prompt_parts.append(f"        assert response.status_code == 200\n")
        prompt_parts.append(f"```\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"**重要规则：**\n")
        prompt_parts.append(f"1. **所有业务接口的测试用例必须生成在同一个Python文件中**\n")
        prompt_parts.append(f"2. **每个接口都有独立的测试函数（如test_interface_1_name, test_interface_2_name等）**\n")
        prompt_parts.append(f"3. 使用pytest的模块级函数来组织所有测试用例（不需要使用class）\n")
        prompt_parts.append(f"4. 只生成除登录接口以外的业务接口的测试用例\n")
        prompt_parts.append(f"5. 每个接口都要有数据驱动测试用例\n")
        prompt_parts.append(f"6. 代码要完整、可运行，所有测试用例在同一个文件中\n")
        prompt_parts.append(f"7. 使用实际的URL、请求体结构\n")
        prompt_parts.append(f"8. token必须从登录接口提取，不能硬编码\n")
        prompt_parts.append(f"9. **组内的接口测试用例要写在一起，不要按接口单独写**\n")
        prompt_parts.append(f"10. **绝对不要使用pytest.skip()跳过测试，所有测试用例都应该正常执行**\n")
        prompt_parts.append(f"11. **如果token获取失败，应该抛出异常或重试，而不是跳过测试**\n")
        prompt_parts.append(f"12. **必须定义base_url fixture，返回测试环境的基础URL: {environment_info.get('base_url', '')}**\n")
        prompt_parts.append(f"13. **必须定义auth_token fixture，使用base_url fixture执行登录并返回token**\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"**代码组织方式（推荐）：**\n")
        prompt_parts.append(f"```python\n")
        prompt_parts.append(f"import pytest\n")
        prompt_parts.append(f"import requests\n")
        prompt_parts.append(f"import json\n")
        prompt_parts.append(f"import allure\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"# 所有测试用例共享的fixture\n")
        prompt_parts.append(f"@pytest.fixture(scope='session')\n")
        prompt_parts.append(f"def base_url():\n")
        prompt_parts.append(f"    # 返回测试环境的基础URL\n")
        prompt_parts.append(f"    return '{environment_info.get('base_url', '')}'\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"@pytest.fixture(scope='session')\n")
        prompt_parts.append(f"def auth_token(base_url):\n")
        prompt_parts.append(f"    # 执行登录，提取token\n")
        prompt_parts.append(f"    # 如果登录失败，应该抛出异常，不要使用pytest.skip()\n")
        prompt_parts.append(f"    login_url = f\"{{base_url}}/V0.1/index.php\"\n")
        prompt_parts.append(f"    response = requests.post(login_url, json={{...}})\n")
        prompt_parts.append(f"    assert response.status_code == 200\n")
        prompt_parts.append(f"    return response.json()['data']['token']\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"# 第一个接口的测试用例\n")
        prompt_parts.append(f"@pytest.mark.parametrize('test_data', [...])\n")
        prompt_parts.append(f"def test_interface_1_name(auth_token, base_url, test_data):\n")
        prompt_parts.append(f"    # 测试代码\n")
        prompt_parts.append(f"    pass\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"# 第二个接口的测试用例\n")
        prompt_parts.append(f"@pytest.mark.parametrize('test_data', [...])\n")
        prompt_parts.append(f"def test_interface_2_name(auth_token, base_url, test_data):\n")
        prompt_parts.append(f"    # 测试代码\n")
        prompt_parts.append(f"    pass\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"# 所有接口的测试用例都在这个文件中\n")
        prompt_parts.append(f"```\n")
        prompt_parts.append(f"\n")
        prompt_parts.append(f"请生成完整的pytest测试用例代码，**所有业务接口的测试用例必须在同一个Python文件中**，只返回Python代码，不要包含其他解释性文字。\n")
        
        full_prompt = "".join(prompt_parts)
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 30, 'message': '正在调用DeepSeek API生成测试用例...'}
        )
        test_case.generation_progress = 30
        if test_task:
            test_task.progress = 30
        db.commit()
        
        # 调用DeepSeek API
        import requests
        import time
        from app.config import settings
        deepseek_api_key = settings.DEEPSEEK_API_KEY
        deepseek_url = settings.DEEPSEEK_BASE_URL + "/chat/completions" if settings.DEEPSEEK_BASE_URL else "https://api.deepseek.com/v1/chat/completions"
        
        print(f"[场景测试用例生成] 开始调用DeepSeek API，prompt长度: {len(full_prompt)}")
        
        messages = [
            {
                "role": "system",
                "content": """你是一个专业的测试工程师，擅长编写高质量的pytest测试用例。
请根据提供的接口信息，严格按照要求生成pytest测试用例代码。

**核心要求：**
1. **所有业务接口的测试用例必须生成在同一个Python文件中**
2. 使用pytest框架和fixture管理token
3. 使用@pytest.mark.parametrize实现数据驱动
4. 使用Allure生成详细测试报告
5. 考虑正常场景、异常场景、边界值
6. 智能断言：根据响应体结构和关键字段进行验证
7. 完善的错误处理和模块化设计

**智能断言要求：**
- 验证HTTP状态码和响应体关键字段
- 根据业务逻辑验证响应数据的正确性
- 对于正常场景验证成功标识，对于异常场景验证错误信息
- 使用JSONPath或字典访问提取和验证数据

**重要规则：**
1. **绝对不要使用pytest.skip()跳过测试，除非有明确的业务逻辑要求**
2. **所有测试用例都应该正常执行，不要默认跳过**
3. **如果token获取失败，应该抛出异常或重试，而不是跳过测试**
4. **生成的代码必须是完整、可运行的，所有测试用例都应该执行**

请生成完整、可运行的pytest测试用例代码，确保所有测试用例都能正常执行。"""
            },
            {
                "role": "user",
                "content": full_prompt
            }
        ]
        
        print(f"[场景测试用例生成] 准备发送请求到DeepSeek API，消息数量: {len(messages)}")
        
        request_start_time = time.time()
        print(f"[场景测试用例生成] 开始发送请求，时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            print(f"[场景测试用例生成] 调用requests.post，URL: {deepseek_url}")
            request_body_str = json.dumps(messages, ensure_ascii=False)
            print(f"[场景测试用例生成] 请求体大小: {len(request_body_str)} 字符")
            
            connect_timeout = 10
            read_timeout = 300
            
            print(f"[场景测试用例生成] 设置超时: 连接{connect_timeout}秒，读取{read_timeout}秒")
            print(f"[场景测试用例生成] 开始发送请求...")
            
            response = requests.post(
                deepseek_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {deepseek_api_key}"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 8000
                },
                timeout=(connect_timeout, read_timeout),
                stream=False
            )
            
            print(f"[场景测试用例生成] requests.post调用完成，开始等待响应...")
            
            request_end_time = time.time()
            elapsed_time = request_end_time - request_start_time
            print(f"[场景测试用例生成] DeepSeek API响应状态码: {response.status_code}，耗时: {elapsed_time:.2f}秒")
            
            if response.status_code != 200:
                error_detail = response.text[:500] if response.text else "无响应内容"
                raise Exception(f"DeepSeek API请求失败: {response.status_code} - {error_detail}")
                
        except requests.exceptions.Timeout as e:
            elapsed_time = time.time() - request_start_time
            print(f"[场景测试用例生成] DeepSeek API请求超时，耗时: {elapsed_time:.2f}秒，错误: {str(e)}")
            raise Exception(f"DeepSeek API请求超时（{elapsed_time:.0f}秒），请稍后重试")
        except requests.exceptions.ConnectionError as e:
            elapsed_time = time.time() - request_start_time
            print(f"[场景测试用例生成] DeepSeek API连接错误，耗时: {elapsed_time:.2f}秒，错误: {str(e)}")
            raise Exception(f"无法连接到DeepSeek API: {str(e)}")
        except requests.exceptions.RequestException as e:
            elapsed_time = time.time() - request_start_time
            print(f"[场景测试用例生成] DeepSeek API请求异常，耗时: {elapsed_time:.2f}秒，错误: {str(e)}")
            raise Exception(f"DeepSeek API请求异常: {str(e)}")
        except Exception as e:
            elapsed_time = time.time() - request_start_time
            print(f"[场景测试用例生成] 未知错误，耗时: {elapsed_time:.2f}秒，错误类型: {type(e).__name__}，错误: {str(e)}")
            import traceback
            traceback.print_exc()
            raise Exception(f"DeepSeek API调用失败: {str(e)}")
        
        print(f"[场景测试用例生成] DeepSeek API响应成功，开始解析响应")
        result = response.json()
        generated_code = result["choices"][0]["message"]["content"]
        print(f"[场景测试用例生成] 生成的测试用例代码长度: {len(generated_code) if generated_code else 0}")
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 80, 'message': '正在清理生成的测试用例代码...'}
        )
        test_case.generation_progress = 80
        if test_task:
            test_task.progress = 80
        db.commit()
        
        # 清理生成的代码（移除markdown代码块标记）
        import re
        generated_code = re.sub(r'```python\s*\n?', '', generated_code)
        generated_code = re.sub(r'```\s*\n?', '', generated_code)
        generated_code = generated_code.strip()
        
        if not generated_code:
            raise Exception("清理后的测试用例代码为空，可能是格式不正确")
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 90, 'message': '正在保存测试用例代码...'}
        )
        test_case.generation_progress = 90
        if test_task:
            test_task.progress = 90
        db.commit()
        
        # 保存测试用例代码
        test_case.test_code = generated_code
        test_case.status = 'active'
        test_case.generation_progress = 100
        test_case.error_message = None
        
        # 更新TestTask状态为完成
        if test_task:
            test_task.status = 'completed'
            test_task.progress = 100
            test_task.completed_at = datetime.now()
        
        db.commit()
        
        # 清除测试用例列表缓存，确保新生成的场景用例能立即显示
        try:
            from app.services.cache_service import cache_service
            # 清除该项目的所有测试用例缓存（包括场景用例和普通用例）
            cache_pattern = f"test_cases:{project_id}:*"
            deleted_count = cache_service.invalidate_cache(cache_pattern)
            print(f"[场景测试用例生成] 已清除测试用例缓存，删除 {deleted_count} 个缓存键")
        except Exception as cache_error:
            print(f"[场景测试用例生成] 清除缓存失败: {cache_error}")
        
        # 更新任务进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 100, 'message': '场景接口测试用例生成成功'}
        )
        
        return {
            "status": "success",
            "test_case_id": test_case_id,
            "test_task_id": test_task.id if test_task else None,
            "message": "场景接口测试用例生成成功",
            "code_length": len(generated_code)
        }
        
    except Exception as e:
        import traceback
        error_msg = f"生成场景接口测试用例失败: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        
        # 更新测试用例状态为失败，并保存错误信息
        try:
            if test_case:
                test_case.status = 'failed'
                test_case.generation_progress = 0
                safe_error_msg = str(error_msg)
                if len(safe_error_msg) > 500:
                    safe_error_msg = safe_error_msg[:500] + "..."
                test_case.error_message = safe_error_msg
            
            # 更新TestTask状态为失败
            if test_task:
                test_task.status = 'failed'
                test_task.progress = 0
                test_task.error_message = safe_error_msg if test_case else str(error_msg)[:500]
            
            db.commit()
        except Exception as save_error:
            print(f"保存测试用例失败状态时出错: {save_error}")
            db.rollback()
        
        # 使用安全的失败状态更新
        safe_error_msg = safe_update_failure_state(self, error_msg)
        
        # 使用明确的异常类型，确保Celery可以正确序列化
        raise RuntimeError(safe_error_msg)
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=3600, soft_time_limit=3500)
def analyze_api_dependencies_task(
    self,
    interface_id: int,
    project_id: int
):
    """
    分析单个API接口的依赖关系
    
    Args:
        interface_id: 接口ID
        project_id: 项目ID
    """
    db = SessionLocal()
    try:
        from app.models import DocumentAPIInterface
        from app.services.api_dependency_analyzer import APIDependencyAnalyzer
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': '开始分析API依赖关系...'}
        )
        
        # 获取接口信息
        interface = db.query(DocumentAPIInterface).filter(
            DocumentAPIInterface.id == interface_id,
            DocumentAPIInterface.project_id == project_id
        ).first()
        
        if not interface:
            raise Exception(f"接口不存在: {interface_id}")
        
        # 构建接口信息字典
        interface_info = {
            'id': interface.id,
            'name': interface.name,
            'method': interface.method,
            'url': interface.url,
            'path': interface.path,
            'headers': interface.headers,
            'request_body': interface.request_body,
            'response_body': interface.response_body,
            'description': interface.description
        }
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 50, 'message': '正在分析依赖关系...'}
        )
        
        # 使用依赖分析器
        analyzer = APIDependencyAnalyzer()
        dependencies = analyzer.analyze_dependencies([interface_info])
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 100, 'message': 'API依赖分析完成'}
        )
        
        return {
            "status": "success",
            "interface_id": interface_id,
            "dependencies": dependencies,
            "message": "API依赖分析完成"
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        
        safe_error_msg = safe_update_failure_state(self, f'分析失败: {error_msg}')
        raise RuntimeError(f"分析API依赖失败: {safe_error_msg}")
    
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=7200, soft_time_limit=7000)
def analyze_all_interfaces_task(
    self,
    project_id: int,
    connection_id: Optional[int] = None
):
    """
    分析项目中所有接口的依赖关系
    
    Args:
        project_id: 项目ID
        connection_id: 数据库连接ID（可选）
    """
    db = SessionLocal()
    try:
        from app.models import DocumentAPIInterface
        from app.services.optimized_dependency_analyzer import OptimizedDependencyAnalyzer
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 5, 'message': '开始获取所有接口信息...'}
        )
        
        # 获取项目下所有接口
        interfaces = db.query(DocumentAPIInterface).filter(
            DocumentAPIInterface.project_id == project_id
        ).all()
        
        if not interfaces:
            raise Exception(f"项目 {project_id} 下没有接口")
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': f'找到 {len(interfaces)} 个接口，开始分析...'}
        )
        
        # 构建接口信息列表
        interfaces_info = []
        for interface in interfaces:
            try:
                headers = interface.headers
                if headers and isinstance(headers, str):
                    try:
                        headers = json.loads(headers)
                    except:
                        headers = {}
                
                params = {}
                request_body = interface.request_body
                if request_body and isinstance(request_body, str):
                    try:
                        request_body = json.loads(request_body)
                    except:
                        request_body = {}
                
                response_body = interface.response_body
                if response_body and isinstance(response_body, str):
                    try:
                        response_body = json.loads(response_body)
                    except:
                        response_body = {}
                
                interfaces_info.append({
                    'id': interface.id,
                    'name': interface.name,
                    'method': interface.method or 'GET',
                    'url': interface.url or '',
                    'path': interface.path or '',
                    'headers': headers,
                    'params': params,
                    'request_body': request_body,
                    'response_body': response_body,
                    'description': interface.description or ''
                })
            except Exception as e:
                print(f"解析接口 {interface.id} 失败: {e}")
                continue
        
        if not interfaces_info:
            raise Exception("没有有效的接口数据可分析")
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 20, 'message': '开始分析接口依赖关系...'}
        )
        
        # 使用优化后的依赖分析器
        analyzer = OptimizedDependencyAnalyzer(db)
        
        # 设置进度回调函数，将进度更新到Celery任务状态
        def progress_callback(progress: int, message: str):
            """进度回调函数，更新Celery任务状态"""
            try:
                # 将进度映射到20-95%的范围（因为开始和结束已经有进度更新）
                mapped_progress = 20 + int((progress / 100) * 75)  # 20% -> 95%
                self.update_state(
                    state='PROGRESS',
                    meta={'progress': mapped_progress, 'message': message}
                )
            except Exception as e:
                # 如果更新失败，只记录错误，不中断任务
                print(f"更新进度失败: {e}")
        
        analyzer.set_progress_callback(progress_callback)
        
        # 如果没有connection_id，使用默认值0
        if connection_id is None:
            connection_id = 0
        
        # 分析所有接口
        result = analyzer.analyze_interfaces(
            interfaces=interfaces_info,
            connection_id=connection_id,
            project_id=project_id,
            resume=False
        )
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 100, 'message': '所有接口依赖分析完成'}
        )
        
        return {
            "status": "success",
            "project_id": project_id,
            "total_interfaces": len(interfaces_info),
            "result": result,
            "message": "所有接口依赖分析完成"
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        
        safe_error_msg = safe_update_failure_state(self, f'分析失败: {error_msg}')
        raise RuntimeError(f"分析所有接口依赖失败: {safe_error_msg}")
    
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=3600, soft_time_limit=3500)
def analyze_database_metadata_task(
    self,
    connection_id: int
):
    """
    分析数据库元数据
    
    Args:
        connection_id: 数据库连接ID
    """
    db = SessionLocal()
    try:
        from app.models import DBConnection
        from app.services.db_service import DatabaseService
        from app.services.metadata_service import DatabaseMetadataManager
        from sqlalchemy import create_engine
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': '开始分析数据库元数据...'}
        )
        
        # 获取数据库连接信息
        db_connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
        if not db_connection:
            raise Exception(f"数据库连接不存在: {connection_id}")
        
        # 更新连接状态为 analyzing
        db_connection.status = 'analyzing'
        db.commit()
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 30, 'message': '正在连接数据库...'}
        )
        
        # 创建数据库引擎
        if db_connection.db_type == 'mysql':
            connection_string = f"mysql+pymysql://{db_connection.username}:{db_connection.password}@{db_connection.host}:{db_connection.port}/{db_connection.database_name}"
        elif db_connection.db_type == 'postgresql':
            connection_string = f"postgresql://{db_connection.username}:{db_connection.password}@{db_connection.host}:{db_connection.port}/{db_connection.database_name}"
        else:
            raise Exception(f"不支持的数据库类型: {db_connection.db_type}")
        
        engine = create_engine(connection_string)
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 50, 'message': '正在分析数据库结构...'}
        )
        
        # 分析数据库结构
        db_service = DatabaseService()
        schema_info = db_service.analyze_database_schema(engine)
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 70, 'message': '正在保存元数据...'}
        )
        
        # 保存元数据
        metadata_manager = DatabaseMetadataManager(db)
        result = metadata_manager.extract_and_save_metadata(
            db_connection=db_connection,
            engine=engine,
            schema_info=schema_info
        )
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 90, 'message': '正在分析关系...'}
        )
        
        # 分析并保存关系
        relationship_result = metadata_manager.analyze_and_save_relationships(
            db_connection=db_connection,
            engine=engine,
            schema_info=schema_info
        )
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 100, 'message': '数据库元数据分析完成'}
        )
        
        # 更新连接状态为 active（已完成）
        db_connection.status = 'active'
        db.commit()
        
        return {
            "status": "success",
            "connection_id": connection_id,
            "tables_saved": result.get("saved_tables", 0),
            "relationships_saved": relationship_result.get("saved_relationships", 0),
            "message": "数据库元数据分析完成"
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        
        # 限制错误消息长度，避免Celery序列化问题
        safe_error_msg = error_msg[:500] + "..." if len(error_msg) > 500 else error_msg
        
        # 更新连接状态为 error
        try:
            db_connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
            if db_connection:
                db_connection.status = 'error'
                db.commit()
        except Exception:
            # 如果更新状态失败，忽略错误
            pass
        
        # 更新任务进度状态（不设置为FAILURE，让Celery自动处理）
        try:
            self.update_state(
                state='PROGRESS',
                meta={
                    'progress': 0,
                    'message': f'分析失败: {safe_error_msg}',
                    'error': safe_error_msg
                }
            )
        except Exception:
            # 如果更新状态失败，忽略错误，继续抛出原始异常
            pass
        
        # 直接抛出异常，让Celery自动处理状态更新和序列化
        raise RuntimeError(f"分析数据库元数据失败: {safe_error_msg}")
    
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=3600, soft_time_limit=3500)
def extract_knowledge_graph_task(
    self,
    connection_id: int
):
    """
    提取知识图谱
    
    Args:
        connection_id: 数据库连接ID
    """
    db = SessionLocal()
    try:
        from app.models import DBConnection, TableMetadata, ColumnMetadata
        from app.services.relationship_analyzer import RelationshipAnalyzer
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': '开始提取知识图谱...'}
        )
        
        # 获取数据库连接信息
        db_connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
        if not db_connection:
            raise Exception(f"数据库连接不存在: {connection_id}")
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 30, 'message': '正在获取表元数据...'}
        )
        
        # 获取所有表元数据
        tables = db.query(TableMetadata).filter(
            TableMetadata.db_connection_id == connection_id
        ).all()
        
        if not tables:
            raise Exception("没有找到表元数据，请先执行数据库元数据分析")
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 50, 'message': '正在分析关系...'}
        )
        
        # 构建表信息
        tables_info = []
        for table in tables:
            columns = db.query(ColumnMetadata).filter(
                ColumnMetadata.table_metadata_id == table.id
            ).all()
            
            table_info = {
                'name': table.table_name,
                'comment': table.table_comment,
                'columns': [{
                    'name': col.column_name,
                    'type': col.data_type,
                    'comment': col.column_comment,
                    'is_primary_key': col.is_primary_key,
                    'is_foreign_key': col.is_foreign_key
                } for col in columns],
                'foreign_keys': json.loads(table.foreign_keys) if table.foreign_keys else []
            }
            tables_info.append(table_info)
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 70, 'message': '正在分析综合关系...'}
        )
        
        # 使用关系分析器提取知识图谱
        analyzer = RelationshipAnalyzer()
        relationships = analyzer.analyze_comprehensive_relationships(tables_info)
        
        self.update_state(
            state='PROGRESS',
            meta={'progress': 100, 'message': '知识图谱提取完成'}
        )
        
        return {
            "status": "success",
            "connection_id": connection_id,
            "relationships_count": len(relationships),
            "relationships": relationships,
            "message": "知识图谱提取完成"
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        
        safe_error_msg = safe_update_failure_state(self, f'提取失败: {error_msg}')
        raise RuntimeError(f"提取知识图谱失败: {safe_error_msg}")
    
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=300, soft_time_limit=280)
def delete_document_task(self, document_id: int, file_path: str):
    """异步删除文档及其相关数据（Redis、ChromaDB、物理文件和数据库）"""
    db = SessionLocal()
    redis_client = None
    
    try:
        import redis
        from app.config import settings
        from app.services.vector_service import VectorService
        
        # 初始化Redis连接
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            encoding='utf-8'
        )
        
        fileid = document_id
        
        # 第1步：删除Redis中的数据（批量删除以提高性能）
        self.update_state(state='PROGRESS', meta={'progress': 20, 'message': '正在清理缓存数据...'})
        try:
            redis_key_prefix = f"file:{fileid}"
            redis_keys = [
                f"{redis_key_prefix}:info",
                f"{redis_key_prefix}:text",
                f"{redis_key_prefix}:tables",
                f"{redis_key_prefix}:images",
                f"{redis_key_prefix}:formulas",
                f"{redis_key_prefix}:interfaces",
                f"{redis_key_prefix}:metadata",
                f"{redis_key_prefix}:full"
            ]
            
            # 使用管道批量删除，提高性能
            if redis_keys:
                pipe = redis_client.pipeline()
                for key in redis_keys:
                    pipe.delete(key)
                # 从索引集合中移除
                pipe.srem("files:parsed", str(fileid))
                pipe.execute()
            
            print(f"已从Redis删除fileid={fileid}的所有数据")
        except Exception as e:
            print(f"删除Redis数据失败: {e}")
        
        # 第2步：删除ChromaDB中的向量数据（如果ChromaDB可用）
        self.update_state(state='PROGRESS', meta={'progress': 40, 'message': '正在清理向量数据...'})
        try:
            vector_service = VectorService()
            vector_service.delete_documents(fileid)
            print(f"已从ChromaDB删除fileid={fileid}的向量数据")
        except Exception as e:
            print(f"删除ChromaDB数据失败: {e}")
        
        # 第3步：删除物理文件
        self.update_state(state='PROGRESS', meta={'progress': 60, 'message': '正在删除文件...'})
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                print(f"已删除物理文件: {file_path}")
        except Exception as e:
            print(f"删除物理文件失败: {e}")
        
        # 第4步：从数据库中删除记录
        self.update_state(state='PROGRESS', meta={'progress': 80, 'message': '正在更新数据库...'})
        try:
            from app.models import DocumentAPIInterface, VectorDocument, APIDocumentSnapshot
            
            # 先删除所有关联记录，避免外键约束错误
            # 删除 DocumentAPIInterface 记录
            try:
                db.query(DocumentAPIInterface).filter(
                    DocumentAPIInterface.document_id == document_id
                ).delete(synchronize_session=False)
                print(f"已删除文档ID={document_id}的关联接口记录")
            except Exception as e:
                print(f"删除关联接口记录失败: {e}")
            
            # 删除 VectorDocument 记录
            try:
                db.query(VectorDocument).filter(
                    VectorDocument.document_id == document_id
                ).delete(synchronize_session=False)
                print(f"已删除文档ID={document_id}的向量记录")
            except Exception as e:
                print(f"删除向量记录失败: {e}")
            
            # 删除 APIDocumentSnapshot 记录
            try:
                db.query(APIDocumentSnapshot).filter(
                    APIDocumentSnapshot.document_id == document_id
                ).delete(synchronize_session=False)
                print(f"已删除文档ID={document_id}的快照记录")
            except Exception as e:
                print(f"删除快照记录失败: {e}")
            
            # 最后删除 Document 记录
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                db.delete(document)
                db.commit()
                print(f"已从数据库删除文档ID={document_id}的记录")
            else:
                print(f"文档ID={document_id}不存在，可能已被删除")
        except Exception as e:
            print(f"删除数据库记录失败: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
        
        self.update_state(state='PROGRESS', meta={'progress': 100, 'message': '删除完成'})
        
        return {
            "status": "success",
            "document_id": document_id,
            "message": "文档删除成功，已清理Redis、ChromaDB和物理文件"
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        safe_update_failure_state(self, f'删除文档失败: {error_msg}')
        raise RuntimeError(f"删除文档失败: {error_msg}")
    
    finally:
        try:
            db.close()
        except:
            pass
        try:
            if redis_client:
                redis_client.close()
        except:
            pass
