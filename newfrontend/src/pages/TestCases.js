import React, { useState, useEffect } from 'react';
import {
  Card,
  Tree,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  message,
  Drawer,
  Descriptions,
  Tabs,
  Spin,
  Empty,
  InputNumber,
  Table,
  Switch,
  Progress
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  FileTextOutlined,
  ReloadOutlined,
  BugOutlined,
  PlayCircleOutlined,
  RocketOutlined,
  CloseCircleOutlined,
  HistoryOutlined,
  AppstoreFilled,
  ApiFilled,
  ThunderboltFilled
} from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import client from '../api/client';
import MonacoEditor from '@monaco-editor/react';
import { getErrorMessage } from '../utils/errorHandler';
import '../styles/test-cases-cool.css';

const { TextArea } = Input;

const TestCases = () => {
  const { id } = useParams();
  const [treeData, setTreeData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState([]);
  const [expandedKeys, setExpandedKeys] = useState([]);
  const [autoExpandParent, setAutoExpandParent] = useState(true);
  const [modalVisible, setModalVisible] = useState(false);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [editingCase, setEditingCase] = useState(null);
  const [isEditMode, setIsEditMode] = useState(false); // 是否处于编辑模式
  const [form] = Form.useForm();
  const [modules, setModules] = useState([]);
  const [detailData, setDetailData] = useState(null);
  const [debugModalVisible, setDebugModalVisible] = useState(false);
  const [debugging, setDebugging] = useState(false);
  const [debugResult, setDebugResult] = useState(null);
  const [environments, setEnvironments] = useState([]);
  const [debugForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState('scenario'); // 'scenario'(接口场景用例), 'interface'(接口测试用例), 或 'performance'(性能测试用例)
  const [executeTaskModalVisible, setExecuteTaskModalVisible] = useState(false);
  const [executeTaskForm] = Form.useForm();
  const [executing, setExecuting] = useState(false);
  const [checkedKeys, setCheckedKeys] = useState([]); // 选中的用例ID
  const [checkedNodes, setCheckedNodes] = useState([]); // 选中的用例节点数据
  const [testCaseSuites, setTestCaseSuites] = useState([]); // 测试用例集列表
  const [selectedSuiteIds, setSelectedSuiteIds] = useState([]); // 选中的用例集ID
  const [editingSuiteInterfaces, setEditingSuiteInterfaces] = useState({}); // 编辑中的用例集接口信息 {suiteId: [interfaces]}
  const [testCodeValue, setTestCodeValue] = useState(''); // 测试代码值（用于MonacoEditor）
  const [testDataValue, setTestDataValue] = useState(''); // 测试数据值（用于MonacoEditor）
  const [assertionsValue, setAssertionsValue] = useState(''); // 断言值（用于MonacoEditor）
  const [debugRecordsModalVisible, setDebugRecordsModalVisible] = useState(false); // 调试记录弹窗
  const [debugRecords, setDebugRecords] = useState([]); // 调试记录列表
  const [loadingDebugRecords, setLoadingDebugRecords] = useState(false); // 加载调试记录状态
  const [selectedDebugRecord, setSelectedDebugRecord] = useState(null); // 选中的调试记录
  const [generatingByModule, setGeneratingByModule] = useState({}); // 记录每个模块的生成状态 {module_caseType: true/false}

  useEffect(() => {
    fetchTestCases();
    fetchModules();
    fetchEnvironments();
    fetchTestCaseSuites();
    
    const refreshKey = `test_cases_refresh_${id}`;
    
    // 监听测试用例生成完成的通知，自动刷新数据
    const handleStorageChange = (e) => {
      // 检查是否是测试用例刷新标记
      if (e.key === refreshKey) {
        console.log('检测到测试用例生成完成，自动刷新测试用例列表');
        fetchTestCases();
      }
    };
    
    // 监听storage事件（跨标签页通信）
    window.addEventListener('storage', handleStorageChange);
    
    // 定期检查刷新标记（用于同页面内的事件，因为同页面的storage事件可能不会触发）
    const checkInterval = setInterval(() => {
      if (localStorage.getItem(refreshKey)) {
        console.log('检测到测试用例生成完成标记，自动刷新测试用例列表');
        fetchTestCases();
        localStorage.removeItem(refreshKey);
      }
    }, 1000); // 每秒检查一次
    
    return () => {
      window.removeEventListener('storage', handleStorageChange);
      clearInterval(checkInterval);
    };
  }, [id, activeTab]); // 当activeTab改变时重新获取数据

  const fetchTestCaseSuites = async () => {
    try {
      const data = await client.get(`/api/suites/?project_id=${id}`);
      setTestCaseSuites(data || []);
    } catch (error) {
      console.error('获取测试用例集失败', error);
      message.error('获取测试用例集失败');
    }
  };

  // 编辑用例集
  const handleEditSuite = async (suiteId) => {
    try {
      // 获取用例集的详细信息（包括接口列表）
      const suite = await client.get(`/api/suites/${suiteId}`);
      
      // 获取用例集的接口列表
      let interfaces = [];
      if (suite.test_case_ids && Array.isArray(suite.test_case_ids) && suite.test_case_ids.length > 0) {
        // 从接口ID获取接口详情
        for (const interfaceId of suite.test_case_ids) {
          // 处理特殊ID（字符串格式）
          if (interfaceId === '__LOGIN_INTERFACE__' || String(interfaceId) === '__LOGIN_INTERFACE__') {
            interfaces.push({
              id: '__LOGIN_INTERFACE__',
              name: '登录接口',
              method: 'POST',
              path: '/V0.1/index.php?__debug__=1&__sql__=true',
              order: interfaces.length + 1
            });
          } else {
            // 尝试获取接口详情
            try {
              // 如果是数字ID，可能是测试用例ID或接口ID
              const interfaceData = await client.get(`/api/endpoints/${interfaceId}`);
              interfaces.push({
                id: interfaceId,
                name: interfaceData.name || `接口 #${interfaceId}`,
                method: interfaceData.method || 'GET',
                path: interfaceData.path || interfaceData.url || '',
                order: interfaces.length + 1
              });
            } catch (err) {
              // 如果获取失败，可能是测试用例ID，或者接口不存在
              // 尝试从测试用例获取
              try {
                const testCase = await client.get(`/api/specs/${interfaceId}`);
                interfaces.push({
                  id: interfaceId,
                  name: testCase.name || `用例 #${interfaceId}`,
                  method: 'N/A',
                  path: 'N/A',
                  order: interfaces.length + 1
                });
              } catch (err2) {
                // 如果都失败，添加一个占位符
                console.error(`获取接口/用例 ${interfaceId} 失败`, err2);
                interfaces.push({
                  id: interfaceId,
                  name: `未知接口 #${interfaceId}`,
                  method: 'N/A',
                  path: 'N/A',
                  order: interfaces.length + 1
                });
              }
            }
          }
        }
      }
      
      setEditingSuiteInterfaces({
        [suiteId]: interfaces
      });
    } catch (error) {
      message.error('获取用例集信息失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const fetchModules = async () => {
    try {
      const data = await client.get(`/api/specs/modules?project_id=${id}`);
      // 确保返回的是数组
      setModules(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('获取模块列表失败', error);
      setModules([]); // 出错时设置为空数组
    }
  };

  const fetchEnvironments = async () => {
    try {
      const data = await client.get(`/api/configs/?project_id=${id}`);
      setEnvironments(data || []);
    } catch (error) {
      console.error('获取环境列表失败', error);
    }
  };

  const fetchTestCases = async () => {
    setLoading(true);
    try {
      // 根据当前tab筛选用例类型
      let caseType;
      let isScenario = null; // 用于区分场景用例和普通接口用例
      
      if (activeTab === 'scenario') {
        // 接口场景用例：pytest类型，且是场景用例
        caseType = 'pytest';
        isScenario = true;
      } else if (activeTab === 'interface') {
        // 接口测试用例：pytest类型，但不是场景用例（普通接口用例）
        caseType = 'pytest';
        isScenario = false;
      } else {
        // 性能测试用例
        caseType = 'jmeter';
        isScenario = null;
      }
      
      // 构建查询参数
      let url = `/api/specs/?project_id=${id}&case_type=${caseType}`;
      if (isScenario !== null) {
        url += `&is_scenario=${isScenario}`;
      }
      
      const response = await client.get(url);
      // 后端返回的是分页对象 {data: [...], pagination: {...}}
      const cases = Array.isArray(response) ? response : (response?.data || []);
      buildTreeData(cases);
    } catch (error) {
      console.error('获取测试用例列表失败', error);
      message.error('获取测试用例列表失败');
    } finally {
      setLoading(false);
    }
  };

  const buildTreeData = (cases) => {
    // 确保 cases 是数组
    if (!Array.isArray(cases)) {
      console.warn('buildTreeData: cases is not an array', cases);
      setTreeData([]);
      return;
    }
    
    // 按模块分组
    const moduleMap = {};
    
    // 根据当前tab确定默认模块名称
    const defaultModule = (activeTab === 'interface' || activeTab === 'performance') ? '单接口' : '未分类';
    
    cases.forEach((testCase) => {
      const module = testCase.module || defaultModule;
      if (!moduleMap[module]) {
        moduleMap[module] = {
          title: module,
          key: `module_${module}`,
          type: 'module',
          children: []
        };
      }
      
      moduleMap[module].children.push({
        title: testCase.name,
        key: `case_${testCase.id}`,
        type: 'testCase',
        caseId: testCase.id,
        data: testCase,
        isLeaf: true
      });
    });

    const tree = Object.values(moduleMap);
    
    // 如果有多个模块，可以添加根节点
    if (tree.length > 1) {
      setTreeData([
        {
          title: '所有模块',
          key: 'root',
          type: 'root',
          children: tree
        }
      ]);
      setExpandedKeys(['root']);
    } else {
      setTreeData(tree);
      setExpandedKeys(tree.map(item => item.key));
    }
  };

  const handleSelect = (keys, info) => {
    setSelectedKeys(keys);
    if (info.node.type === 'testCase') {
      fetchCaseDetail(info.node.caseId);
      setIsEditMode(false); // 选择时进入只读模式
      setDrawerVisible(true);
    }
  };

  const fetchCaseDetail = async (caseId) => {
    try {
      const data = await client.get(`/api/specs/${caseId}`);
      setDetailData(data);
    } catch (error) {
      console.error('获取用例详情失败', error);
      message.error('获取用例详情失败');
    }
  };

  const handleAdd = () => {
    setEditingCase(null);
    form.resetFields();
    // 根据当前tab设置默认的case_type
    const defaultCaseType = (activeTab === 'scenario' || activeTab === 'interface') ? 'pytest' : 'jmeter';
    form.setFieldsValue({ case_type: defaultCaseType });
    setModalVisible(true);
  };

  const handleEdit = async (node) => {
    if (node.type === 'testCase' && node.caseId) {
      // 获取用例详情并打开Drawer的编辑模式
      try {
        const data = await client.get(`/api/specs/${node.caseId}`);
        setDetailData(data);
        setEditingCase(data);
        const testDataStr = typeof data.test_data === 'string' ? data.test_data : JSON.stringify(data.test_data || {}, null, 2);
        const assertionsStr = typeof data.assertions === 'string' ? data.assertions : JSON.stringify(data.assertions || {}, null, 2);
        
      form.setFieldsValue({
          name: data.name,
          module: data.module,
          case_type: data.case_type,
          description: data.description,
          test_data: testDataStr,
          test_code: data.test_code || '',
          assertions: assertionsStr
        });
        setTestCodeValue(data.test_code || '');
        setTestDataValue(testDataStr);
        setAssertionsValue(assertionsStr);
        setIsEditMode(true);
        setDrawerVisible(true);
      } catch (error) {
        message.error('获取用例详情失败');
      }
    }
  };

  const handleDelete = async (node) => {
    if (node.type === 'testCase' && node.caseId) {
      Modal.confirm({
        title: '确认删除',
        content: `确定要删除用例"${node.title}"吗？`,
        onOk: async () => {
          try {
            await client.delete(`/api/specs/${node.caseId}`);
            message.success('删除成功');
            fetchTestCases();
          } catch (error) {
            message.error('删除失败');
          }
        }
      });
    }
  };

  const handleDebug = (node) => {
    if (node.type === 'testCase' && node.data) {
      setEditingCase(node.data);
      debugForm.setFieldsValue({
        environment_id: environments.length > 0 ? environments[0].id : undefined
      });
      setDebugModalVisible(true);
    }
  };

  const [debugTaskId, setDebugTaskId] = useState(null);
  const [debugProgress, setDebugProgress] = useState(0);
  const [debugMessage, setDebugMessage] = useState('');
  const [debugRealtimeLogs, setDebugRealtimeLogs] = useState(''); // 实时调试日志
  const [pollIntervalRef, setPollIntervalRef] = useState(null); // 保存轮询间隔的引用
  const [userSuggestion, setUserSuggestion] = useState(''); // 用户修复建议
  const [fixTaskId, setFixTaskId] = useState(null); // DeepSeek修复任务ID
  const [fixing, setFixing] = useState(false); // 是否正在修复

  const handleDebugSubmit = async () => {
    if (!editingCase) return;
    
    // 检查是否有测试环境
    if (environments.length === 0) {
      message.error('请先配置测试环境');
      return;
    }
    
    try {
      setDebugging(true);
      setDebugResult(null);
      setDebugProgress(0);
      setDebugMessage('提交调试任务...');
      setDebugRealtimeLogs(''); // 清空实时日志
      
      // 使用默认的第一个测试环境
      const defaultEnvironmentId = environments[0].id;
      
      // 调用新的执行代码API（只执行，不自动修复）
      const response = await client.post(`/api/specs/execute-code?project_id=${id}`, {
        test_case_id: editingCase.id,
        environment_id: defaultEnvironmentId
      });
      
      setDebugTaskId(response.task_id);
      setDebugMessage('任务已提交，正在执行...');
      
      // 轮询任务状态
      const pollInterval = setInterval(async () => {
        try {
          const taskResult = await client.get(`/api/specs/task-status/${response.task_id}`);
          
          if (taskResult.state === 'SUCCESS') {
            clearInterval(pollInterval);
            setPollIntervalRef(null);
            setDebugging(false);
            setDebugProgress(100);
            const finalLogs = taskResult.result?.debug_logs || taskResult.result?.output || '';
            setDebugRealtimeLogs(finalLogs); // 更新最终日志
            setDebugResult({
              status: 'success',
              output: taskResult.result?.output || '',
              message: taskResult.result?.message || '执行成功',
              attempts: taskResult.result?.attempts || 1,
              debug_logs: finalLogs
            });
            setDebugMessage('执行成功');
      message.success('调试执行完成');
            fetchTestCases(); // 刷新用例列表
          } else if (taskResult.state === 'FAILURE' || taskResult.state === 'REVOKED') {
            clearInterval(pollInterval);
            setPollIntervalRef(null);
            setDebugging(false);
            const finalLogs = taskResult.result?.debug_logs || taskResult.error || taskResult.traceback || '';
            setDebugRealtimeLogs(finalLogs || '任务已被中断'); // 更新最终日志
            setDebugResult({
              status: taskResult.state === 'REVOKED' ? 'cancelled' : 'error',
              error: taskResult.result?.error || taskResult.error || taskResult.traceback || (taskResult.state === 'REVOKED' ? '任务已被用户中断' : '执行失败'),
              message: taskResult.state === 'REVOKED' ? '任务已中断' : (taskResult.result?.message || '执行失败'),
              attempts: taskResult.result?.attempts || 1,
              debug_logs: finalLogs || '任务已被中断',
              stderr: taskResult.result?.stderr || '',
              stdout: taskResult.result?.stdout || ''
            });
            setDebugMessage(taskResult.state === 'REVOKED' ? '任务已中断' : '执行失败');
            message.warning(taskResult.state === 'REVOKED' ? '调试任务已中断' : '调试执行失败');
          } else if (taskResult.state === 'PROGRESS') {
            // 更新进度
            const progress = taskResult.meta?.progress || 0;
            const message = taskResult.meta?.message || '执行中...';
            const debugLogs = taskResult.meta?.debug_logs || '';
            setDebugProgress(progress);
            setDebugMessage(message);
            // 更新实时日志
            if (debugLogs) {
              setDebugRealtimeLogs(prev => {
                // 追加新日志，避免重复
                if (debugLogs && !prev.includes(debugLogs.slice(-500))) {
                  return prev + '\n' + debugLogs;
                }
                return prev;
              });
            }
            // 如果有关键错误信息，也显示
            if (taskResult.meta?.error) {
              setDebugResult({
                status: 'error',
                message: message,
                error: taskResult.meta.error,
                debug_logs: debugLogs
              });
            }
          }
    } catch (error) {
          console.error('轮询任务状态失败', error);
        }
      }, 2000); // 每2秒轮询一次
      
      // 保存轮询间隔引用
      setPollIntervalRef(pollInterval);
      
      // 30分钟后停止轮询
      setTimeout(() => {
        clearInterval(pollInterval);
        setPollIntervalRef(null);
        if (debugging) {
          setDebugging(false);
          message.warning('执行超时，请检查任务状态');
        }
      }, 30 * 60 * 1000);
      
    } catch (error) {
      setDebugging(false);
      setPollIntervalRef(null);
      message.error('调试执行失败: ' + getErrorMessage(error));
    }
  };

  // DeepSeek修复
  const handleDeepSeekFix = async () => {
    if (!editingCase || !debugResult || debugResult.status !== 'error') {
      message.warning('只能在测试执行失败时使用DeepSeek修复');
      return;
    }

    try {
      setFixing(true);
      setFixTaskId(null);

      // 调用DeepSeek修复API
      const response = await client.post(`/api/specs/fix?project_id=${id}`, {
        test_case_id: editingCase.id,
        error_output: debugResult.error || debugResult.debug_logs || '',
        user_suggestion: userSuggestion
      });

      setFixTaskId(response.task_id);
      message.info('DeepSeek修复任务已提交，请稍候...');

      // 轮询修复任务状态
      const pollInterval = setInterval(async () => {
        try {
          const taskResult = await client.get(`/api/specs/task-status/${response.task_id}`);
          
          if (taskResult.state === 'SUCCESS') {
            clearInterval(pollInterval);
            setFixing(false);
            message.success('代码修复完成，请重新执行测试');
            
            // 刷新测试用例详情，获取修复后的代码
            fetchCaseDetail(editingCase.id);
            
            // 清空修复建议
            setUserSuggestion('');
          } else if (taskResult.state === 'FAILURE') {
            clearInterval(pollInterval);
            setFixing(false);
            message.error('DeepSeek修复失败: ' + (taskResult.error || '未知错误'));
          } else if (taskResult.state === 'PROGRESS') {
            // 更新进度
            const progressMsg = taskResult.meta?.message || '修复中...';
            message.info(progressMsg);
          }
        } catch (error) {
          console.error('轮询修复任务状态失败', error);
        }
      }, 2000);

      // 5分钟后停止轮询
      setTimeout(() => {
        clearInterval(pollInterval);
        if (fixing) {
          setFixing(false);
          message.warning('修复任务执行超时，请检查任务状态');
        }
      }, 5 * 60 * 1000);

    } catch (error) {
      setFixing(false);
      message.error('提交修复任务失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  // 中断调试任务
  const handleCancelDebug = async () => {
    if (!debugTaskId) {
      message.warning('没有正在执行的任务');
      return;
    }

    try {
      // 调用取消任务API
      const response = await client.post(`/api/specs/task-cancel/${debugTaskId}`);
      
      if (response.status === 'cancelled') {
        // 清除轮询
        if (pollIntervalRef) {
          clearInterval(pollIntervalRef);
          setPollIntervalRef(null);
        }
        
      setDebugging(false);
        setDebugMessage('任务已中断');
        setDebugRealtimeLogs(prev => prev + '\n\n[用户中断] 任务已被用户手动终止');
        
        setDebugResult({
          status: 'cancelled',
          message: '任务已被用户中断',
          debug_logs: debugRealtimeLogs + '\n\n[用户中断] 任务已被用户手动终止'
        });
        
        message.success('任务已成功中断');
      } else if (response.status === 'already_finished') {
        message.info(response.message);
        // 清除轮询
        if (pollIntervalRef) {
          clearInterval(pollIntervalRef);
          setPollIntervalRef(null);
        }
        setDebugging(false);
      }
    } catch (error) {
      console.error('中断任务失败', error);
      message.error('中断任务失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      
      if (editingCase) {
        await client.put(`/api/specs/${editingCase.id}?project_id=${id}`, values);
        message.success('更新成功');
      } else {
        await client.post(`/api/specs/?project_id=${id}`, values);
        message.success('创建成功');
      }
      
      setModalVisible(false);
      fetchTestCases();
    } catch (error) {
      message.error(editingCase ? '更新失败' : '创建失败');
    }
  };

  // 根据模块生成测试用例
  const handleGenerateByModule = async (moduleName, caseType) => {
    const key = `${moduleName}_${caseType}`;
    setGeneratingByModule(prev => ({ ...prev, [key]: true }));
    
    try {
      const response = await client.post(
        `/api/specs/generate-by-module?project_id=${id}&module=${encodeURIComponent(moduleName)}&case_type=${caseType}`
      );
      
      message.success(response.message || '测试用例生成任务已提交');
      
      // 刷新测试用例列表
      setTimeout(() => {
        fetchTestCases();
      }, 1000);
    } catch (error) {
      console.error('生成测试用例失败', error);
      message.error('生成测试用例失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setGeneratingByModule(prev => ({ ...prev, [key]: false }));
    }
  };

  const titleRender = (nodeData) => {
    if (nodeData.type === 'module' || nodeData.type === 'root') {
      // 模块节点：不显示生成按钮（按钮已移到用例级别）
      return (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <span>
            <FileTextOutlined style={{ marginRight: 8 }} />
            <strong>{nodeData.title}</strong>
            <span style={{ marginLeft: 8, color: '#999', fontSize: 12 }}>
              ({nodeData.children?.length || 0} 个用例)
            </span>
          </span>
        </div>
      );
    } else if (nodeData.type === 'testCase') {
      const status = nodeData.data?.status;
      const caseType = nodeData.data?.case_type;
      
      // 改进模块名称获取逻辑
      let moduleName = nodeData.data?.module;
      
      // 如果module为空、null、undefined或包含"None"，尝试从用例名称或场景用例集名称获取
      if (!moduleName || moduleName === 'None' || moduleName === 'null' || moduleName.includes('None')) {
        // 尝试从用例名称提取（格式可能是：场景_1_接口名 或 场景用例集名_接口名）
        const titleParts = nodeData.title.split('_');
        if (titleParts.length > 1) {
          // 如果用例名称包含下划线，尝试匹配场景用例集名称
          // 例如："场景_1_接口名" -> 尝试匹配 "场景_1"
          const potentialModuleName = titleParts.slice(0, 2).join('_'); // 取前两部分，如 "场景_1"
          
          // 首先尝试精确匹配场景用例集名称
          const exactMatch = testCaseSuites.find(suite => suite.name === potentialModuleName);
          if (exactMatch) {
            moduleName = exactMatch.name;
          } else {
            // 如果精确匹配失败，尝试模糊匹配（场景用例集名称包含潜在模块名）
            const fuzzyMatch = testCaseSuites.find(suite => {
              return suite.name.includes(potentialModuleName) || potentialModuleName.includes(suite.name);
            });
            if (fuzzyMatch) {
              moduleName = fuzzyMatch.name;
            } else {
              // 如果还是找不到，使用第一部分作为模块名（例如："场景"）
              moduleName = titleParts[0];
            }
          }
        } else {
          // 如果用例名称不包含下划线，尝试从场景用例集中查找匹配的
          // 查找包含用例名称的场景用例集
          const matchedSuite = testCaseSuites.find(suite => {
            // 检查场景用例集名称是否包含用例名称的一部分
            return nodeData.title.includes(suite.name) || suite.name.includes(nodeData.title.split('_')[0]);
          });
          if (matchedSuite) {
            moduleName = matchedSuite.name;
          } else {
            // 如果还是找不到，使用用例名称的第一个词
            moduleName = nodeData.title.split('_')[0];
          }
        }
      }
      
      // 只在接口场景用例tab下显示生成按钮
      const showGenerateButtons = activeTab === 'scenario';
      
      return (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <Space>
            <span>{nodeData.title}</span>
            {caseType && <Tag color="blue">{caseType}</Tag>}
            {status && (
              <Tag className={`status-tag ${status === 'active' || status === 'completed' ? 'active' : status === 'generating' ? 'generating' : status === 'failed' ? 'failed' : 'completed'}`}>
                {status === 'active' ? '活跃' : status === 'completed' ? '已完成' : status === 'generating' ? '生成中' : status === 'failed' ? '失败' : status}
              </Tag>
            )}
            {nodeData.data?.generation_progress && (
              <Tag>{nodeData.data.generation_progress}%</Tag>
            )}
            {/* 所有用例类型都支持调试 */}
            <Button
              className="card-action-button"
              type="link"
              size="small"
              icon={<BugOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                handleDebug(nodeData);
              }}
              title={caseType === 'jmeter' ? '调试性能测试（使用2个线程）' : '调试执行'}
            />
            <Button
              className="card-action-button"
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                handleEdit(nodeData);
              }}
              title={caseType === 'jmeter' ? '编辑性能测试用例' : '编辑测试用例'}
            />
            <Button
              className="card-action-button"
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                handleDelete(nodeData);
              }}
            />
          </Space>
          {showGenerateButtons && (
            <Space size="small" onClick={(e) => e.stopPropagation()} style={{ marginLeft: 8 }}>
              <Button
                type="primary"
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  handleGenerateByModule(moduleName, 'pytest');
                }}
                loading={generatingByModule[`${moduleName}_pytest`]}
              >
                生成接口用例
              </Button>
              <Button
                type="primary"
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  handleGenerateByModule(moduleName, 'jmeter');
                }}
                loading={generatingByModule[`${moduleName}_jmeter`]}
              >
                生成性能用例
              </Button>
            </Space>
          )}
        </div>
      );
    }
    return nodeData.title;
  };

  const onExpand = (expandedKeysValue) => {
    setExpandedKeys(expandedKeysValue);
    setAutoExpandParent(false);
  };

  // 计算统计数据
  const getStats = () => {
    const scenarioCount = activeTab === 'scenario' ? treeData.reduce((count, node) => {
      const countChildren = (n) => {
        if (n.type === 'testCase') return 1;
        if (n.children) return n.children.reduce((sum, child) => sum + countChildren(child), 0);
        return 0;
      };
      return count + countChildren(node);
    }, 0) : 0;
    
    const interfaceCount = activeTab === 'interface' ? treeData.reduce((count, node) => {
      const countChildren = (n) => {
        if (n.type === 'testCase') return 1;
        if (n.children) return n.children.reduce((sum, child) => sum + countChildren(child), 0);
        return 0;
      };
      return count + countChildren(node);
    }, 0) : 0;
    
    const performanceCount = activeTab === 'performance' ? treeData.reduce((count, node) => {
      const countChildren = (n) => {
        if (n.type === 'testCase') return 1;
        if (n.children) return n.children.reduce((sum, child) => sum + countChildren(child), 0);
        return 0;
      };
      return count + countChildren(node);
    }, 0) : 0;
    
    return { scenarioCount, interfaceCount, performanceCount, totalCount: scenarioCount + interfaceCount + performanceCount };
  };

  const stats = getStats();

  return (
    <div className="test-cases-container">
      {/* 统计信息栏 */}
      <div className="stats-bar">
        <div className="stat-item">
          <span className="stat-label">场景用例:</span>
          <span className="stat-value">{stats.scenarioCount}</span>
          <span className="stat-label">个</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">单接口用例:</span>
          <span className="stat-value">{stats.interfaceCount}</span>
          <span className="stat-label">个</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">性能用例:</span>
          <span className="stat-value">{stats.performanceCount}</span>
          <span className="stat-label">个</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">总计:</span>
          <span className="stat-value">{stats.totalCount}</span>
          <span className="stat-label">个用例</span>
        </div>
      </div>

      <div className="tabs-container">
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>用例库管理</h2>
          <Space>
            <Button className="cool-button" icon={<ReloadOutlined />} onClick={fetchTestCases}>
              刷新
            </Button>
            <Button 
              className="cool-button cool-button-primary"
              type="primary" 
              icon={<RocketOutlined />} 
              onClick={() => {
              // 允许选择用例集或单个用例
              if (checkedKeys.length === 0 && selectedSuiteIds.length === 0) {
                message.warning('请至少选择一个测试用例或用例集');
                return;
              }
              // 获取选中的用例数据
              const selectedCases = [];
              const collectCases = (nodes) => {
                nodes.forEach(node => {
                  if (node.type === 'testCase' && node.caseId) {
                    if (checkedKeys.includes(`case_${node.caseId}`)) {
                      selectedCases.push({
                        id: node.caseId,
                        name: node.data?.name || node.title,
                        case_type: node.data?.case_type || ((activeTab === 'scenario' || activeTab === 'interface') ? 'pytest' : 'jmeter')
                      });
                    }
                  }
                  if (node.children) {
                    collectCases(node.children);
                  }
                });
              };
              collectCases(treeData);
              setCheckedNodes(selectedCases);
              executeTaskForm.setFieldsValue({
                name: `测试任务_${new Date().toLocaleString()}`,
                environment_id: environments.length > 0 ? environments[0].id : undefined,
                test_case_suite_ids: selectedSuiteIds
              });
              setExecuteTaskModalVisible(true);
            }}
            disabled={checkedKeys.length === 0 && selectedSuiteIds.length === 0}
          >
            生成执行任务
          </Button>
        </Space>
        </div>

        <Card className="tree-card">
        <Tabs 
          activeKey={activeTab} 
          onChange={setActiveTab}
          className="cool-tabs"
          style={{ marginBottom: 16 }}
          items={[
            {
              key: 'scenario',
              label: (
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <AppstoreFilled style={{ fontSize: '14px' }} />
                  场景用例
                </span>
              ),
              children: (
                <Spin spinning={loading}>
                  {treeData.length > 0 ? (
                    <Tree
                      treeData={treeData}
                      expandedKeys={expandedKeys}
                      selectedKeys={selectedKeys}
                      checkedKeys={checkedKeys}
                      autoExpandParent={autoExpandParent}
                      onSelect={handleSelect}
                      onCheck={(checkedKeysValue, info) => {
                        setCheckedKeys(checkedKeysValue);
                      }}
                      onExpand={onExpand}
                      titleRender={titleRender}
                      checkable
                      blockNode
                    />
                  ) : (
                    <div className="cool-empty">
                      <div className="cool-empty-icon">📋</div>
                      <div className="cool-empty-text">暂无场景用例，请先创建</div>
                    </div>
                  )}
                </Spin>
              )
            },
            {
              key: 'interface',
              label: (
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <ApiFilled style={{ fontSize: '14px' }} />
                  单接口用例
                </span>
              ),
              children: (
                <Spin spinning={loading}>
                  {treeData.length > 0 ? (
                    <Tree
                      treeData={treeData}
                      expandedKeys={expandedKeys}
                      selectedKeys={selectedKeys}
                      checkedKeys={checkedKeys}
                      autoExpandParent={autoExpandParent}
                      onSelect={handleSelect}
                      onCheck={(checkedKeysValue, info) => {
                        setCheckedKeys(checkedKeysValue);
                      }}
                      onExpand={onExpand}
                      titleRender={titleRender}
                      checkable
                      blockNode
                    />
                  ) : (
                    <div className="cool-empty">
                      <div className="cool-empty-icon">📝</div>
                      <div className="cool-empty-text">暂无单接口用例，请先创建</div>
                    </div>
                  )}
                </Spin>
              )
            },
            {
              key: 'performance',
              label: (
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <ThunderboltFilled style={{ fontSize: '14px' }} />
                  性能用例
                </span>
              ),
              children: (
                <Spin spinning={loading}>
                  {treeData.length > 0 ? (
                    <Tree
                      treeData={treeData}
                      expandedKeys={expandedKeys}
                      selectedKeys={selectedKeys}
                      checkedKeys={checkedKeys}
                      autoExpandParent={autoExpandParent}
                      onSelect={handleSelect}
                      onCheck={(checkedKeysValue, info) => {
                        setCheckedKeys(checkedKeysValue);
                      }}
                      onExpand={onExpand}
                      titleRender={titleRender}
                      checkable
                      blockNode
                    />
                  ) : (
                    <div className="cool-empty">
                      <div className="cool-empty-icon">⚡</div>
                      <div className="cool-empty-text">暂无性能用例，请先创建</div>
                    </div>
                  )}
                </Spin>
              )
            }
          ]}
        />
        </Card>
      </div>

      <Modal
        className="cool-modal"
        title={editingCase ? '编辑测试用例' : '新建测试用例'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={800}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="用例名称"
            rules={[{ required: true, message: '请输入用例名称' }]}
          >
            <Input placeholder="请输入用例名称" />
          </Form.Item>

          <Form.Item
            name="module"
            label="模块"
          >
            <Select
              placeholder="选择模块"
              showSearch
              allowClear
              filterOption={(input, option) =>
                option.children.toLowerCase().indexOf(input.toLowerCase()) >= 0
              }
            >
              {Array.isArray(modules) && modules.length > 0 ? (
                modules.map((module, index) => (
                  <Select.Option key={module || index} value={module}>
                    {module}
                  </Select.Option>
                ))
              ) : (
                <Select.Option value="" disabled>暂无模块</Select.Option>
              )}
            </Select>
          </Form.Item>

          <Form.Item
            name="case_type"
            label="用例类型"
            rules={[{ required: true, message: '请选择用例类型' }]}
          >
            <Select placeholder="选择用例类型">
              <Select.Option value="pytest">单接口用例 (Pytest)</Select.Option>
              <Select.Option value="jmeter">性能用例 (JMeter)</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="description"
            label="描述"
          >
            <TextArea rows={3} placeholder="请输入用例描述" />
          </Form.Item>

          <Form.Item
            name="test_data"
            label="测试数据"
            tooltip="JSON格式的测试数据"
          >
            <MonacoEditor
              height="200px"
              language="json"
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                automaticLayout: true
              }}
            />
          </Form.Item>

          <Form.Item
            name="assertions"
            label="断言配置"
            tooltip="JSON格式的断言配置"
          >
            <MonacoEditor
              height="150px"
              language="json"
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                automaticLayout: true
              }}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        className="cool-drawer"
        title={isEditMode ? "编辑用例" : "用例详情"}
        placement="right"
        width={1000}
        open={drawerVisible}
        onClose={() => {
          setDrawerVisible(false);
          setIsEditMode(false);
          form.resetFields();
        }}
        extra={
          isEditMode ? (
            <Space>
              <Button onClick={() => {
                setIsEditMode(false);
                form.resetFields();
                if (detailData) {
                  form.setFieldsValue({
                    name: detailData.name,
                    module: detailData.module,
                    case_type: detailData.case_type,
                    description: detailData.description,
                    test_data: typeof detailData.test_data === 'string' ? detailData.test_data : JSON.stringify(detailData.test_data || {}, null, 2),
                    test_code: detailData.test_code || '',
                    assertions: typeof detailData.assertions === 'string' ? detailData.assertions : JSON.stringify(detailData.assertions || {}, null, 2)
                  });
                }
              }}>
                取消
              </Button>
              <Button type="primary" onClick={async () => {
                try {
                  const values = await form.validateFields();
                  
                  // 使用状态变量中的值（MonacoEditor的值）
                  const finalTestCode = testCodeValue || values.test_code || '';
                  const finalTestData = testDataValue || values.test_data || '';
                  const finalAssertions = assertionsValue || values.assertions || '';
                  
                  // 处理test_data和assertions的JSON字符串
                  let test_data = finalTestData;
                  let assertions = finalAssertions;
                  
                  if (test_data && typeof test_data === 'string') {
                    try {
                      test_data = JSON.parse(test_data);
                    } catch (e) {
                      // 如果解析失败，保持原字符串
                    }
                  }
                  
                  if (assertions && typeof assertions === 'string') {
                    try {
                      assertions = JSON.parse(assertions);
                    } catch (e) {
                      // 如果解析失败，保持原字符串
                    }
                  }
                  
                  const updateData = {
                    name: values.name,
                    module: values.module,
                    case_type: values.case_type,
                    description: values.description,
                    test_data: test_data,
                    test_code: finalTestCode,
                    assertions: assertions
                  };
                  
                  await client.put(`/api/specs/${editingCase.id}?project_id=${id}`, updateData);
                  message.success('更新成功');
                  setIsEditMode(false);
                  fetchCaseDetail(editingCase.id); // 刷新详情
                  fetchTestCases(); // 刷新列表
                } catch (error) {
                  message.error('更新失败: ' + (error.response?.data?.detail || error.message));
                }
              }}>
                保存
              </Button>
            </Space>
          ) : detailData ? (
            <Button type="primary" onClick={() => {
              const testDataStr = typeof detailData.test_data === 'string' ? detailData.test_data : JSON.stringify(detailData.test_data || {}, null, 2);
              const assertionsStr = typeof detailData.assertions === 'string' ? detailData.assertions : JSON.stringify(detailData.assertions || {}, null, 2);
              
              form.setFieldsValue({
                name: detailData.name,
                module: detailData.module,
                case_type: detailData.case_type,
                description: detailData.description,
                test_data: testDataStr,
                test_code: detailData.test_code || '',
                assertions: assertionsStr
              });
              setTestCodeValue(detailData.test_code || '');
              setTestDataValue(testDataStr);
              setAssertionsValue(assertionsStr);
              setIsEditMode(true);
            }}>
              编辑
            </Button>
          ) : null
        }
      >
        {isEditMode ? (
          <Form form={form} layout="vertical">
            <Tabs defaultActiveKey="basic" items={[
              {
                key: 'basic',
                label: '基本信息',
                children: (
                  <>
                    <Form.Item
                      name="name"
                      label="用例名称"
                      rules={[{ required: true, message: '请输入用例名称' }]}
                    >
                      <Input placeholder="请输入用例名称" />
                    </Form.Item>

                    <Form.Item
                      name="module"
                      label="模块"
                    >
                      <Select
                        placeholder="选择模块"
                        showSearch
                        allowClear
                        filterOption={(input, option) =>
                          option.children.toLowerCase().indexOf(input.toLowerCase()) >= 0
                        }
                      >
                        {Array.isArray(modules) && modules.length > 0 ? (
                          modules.map((module, index) => (
                            <Select.Option key={module || index} value={module}>
                              {module}
                            </Select.Option>
                          ))
                        ) : (
                          <Select.Option value="" disabled>暂无模块</Select.Option>
                        )}
                      </Select>
                    </Form.Item>

                    <Form.Item
                      name="case_type"
                      label="用例类型"
                      rules={[{ required: true, message: '请选择用例类型' }]}
                    >
                      <Select placeholder="选择用例类型">
                        <Select.Option value="pytest">接口测试用例 (Pytest)</Select.Option>
                        <Select.Option value="jmeter">性能测试用例 (JMeter)</Select.Option>
                      </Select>
                    </Form.Item>

                    <Form.Item
                      name="description"
                      label="描述"
                    >
                      <TextArea rows={3} placeholder="请输入用例描述" />
                    </Form.Item>

                    <Descriptions column={1} bordered style={{ marginTop: 16 }}>
                      <Descriptions.Item label="状态">
                        <Tag color={detailData?.status === 'active' ? 'green' : 'default'}>
                          {detailData?.status || '-'}
                        </Tag>
                      </Descriptions.Item>
                      <Descriptions.Item label="创建时间">
                        {detailData?.created_at ? new Date(detailData.created_at).toLocaleString() : '-'}
                      </Descriptions.Item>
                    </Descriptions>
                  </>
                )
              },
              {
                key: 'code',
                label: '测试代码',
                children: (
                  <Form.Item
                    name="test_code"
                    label="测试代码"
                  >
                    <MonacoEditor
                      height="600px"
                      language={form.getFieldValue('case_type') === 'pytest' ? 'python' : 'xml'}
                      value={testCodeValue}
                      theme="vs-dark"
                      options={{
                        minimap: { enabled: true },
                        scrollBeyondLastLine: false,
                        automaticLayout: true
                      }}
                      onChange={(newValue) => {
                        setTestCodeValue(newValue || '');
                        form.setFieldsValue({ test_code: newValue || '' });
                      }}
                    />
                  </Form.Item>
                )
              },
              {
                key: 'testData',
                label: '测试数据',
                children: (
                  <Form.Item
                    name="test_data"
                    label="测试数据"
                    tooltip="JSON格式的测试数据"
                  >
                    <MonacoEditor
                      height="600px"
                      language="json"
                      value={testDataValue}
                      theme="vs-dark"
                      options={{
                        minimap: { enabled: true },
                        scrollBeyondLastLine: false,
                        automaticLayout: true
                      }}
                      onChange={(newValue) => {
                        setTestDataValue(newValue || '');
                        form.setFieldsValue({ test_data: newValue || '' });
                      }}
                    />
                  </Form.Item>
                )
              },
              {
                key: 'assertions',
                label: '断言',
                children: (
                  <Form.Item
                    name="assertions"
                    label="断言配置"
                    tooltip="JSON格式的断言配置"
                  >
                    <MonacoEditor
                      height="600px"
                      language="json"
                      value={assertionsValue}
                      theme="vs-dark"
                      options={{
                        minimap: { enabled: true },
                        scrollBeyondLastLine: false,
                        automaticLayout: true
                      }}
                      onChange={(newValue) => {
                        setAssertionsValue(newValue || '');
                        form.setFieldsValue({ assertions: newValue || '' });
                      }}
                    />
                  </Form.Item>
                )
              }
            ]} />
          </Form>
        ) : detailData ? (
          <Tabs defaultActiveKey="basic" items={[
            {
              key: 'basic',
              label: '基本信息',
              children: (
                <Descriptions column={1} bordered>
                  <Descriptions.Item label="用例名称">{detailData.name}</Descriptions.Item>
                  <Descriptions.Item label="模块">{detailData.module || '未分类'}</Descriptions.Item>
                  <Descriptions.Item label="用例类型">
                    <Tag>{detailData.case_type}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="状态">
                    <Tag color={detailData.status === 'active' ? 'green' : 'default'}>
                      {detailData.status}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="描述">{detailData.description || '-'}</Descriptions.Item>
                  <Descriptions.Item label="创建时间">
                    {detailData.created_at ? new Date(detailData.created_at).toLocaleString() : '-'}
                  </Descriptions.Item>
                </Descriptions>
              )
            },
            {
              key: 'code',
              label: '测试代码',
              children: (
                detailData.test_code ? (
                  <MonacoEditor
                    height="600px"
                    language={detailData.case_type === 'pytest' ? 'python' : 'xml'}
                    value={detailData.test_code}
                    theme="vs-dark"
                    options={{
                      readOnly: true,
                      minimap: { enabled: true },
                      scrollBeyondLastLine: false
                    }}
                  />
                ) : (
                  <Empty description="暂无测试代码" />
                )
              )
            },
            {
              key: 'testData',
              label: '测试数据',
              children: (
                detailData.test_data ? (
                  <MonacoEditor
                    height="600px"
                    language="json"
                    value={typeof detailData.test_data === 'string' ? detailData.test_data : JSON.stringify(detailData.test_data, null, 2)}
                    theme="vs-dark"
                    options={{
                      readOnly: true,
                      minimap: { enabled: true }
                    }}
                  />
                ) : (
                  <Empty description="暂无测试数据" />
                )
              )
            },
            {
              key: 'assertions',
              label: '断言',
              children: (
                detailData.assertions ? (
                  <MonacoEditor
                    height="600px"
                    language="json"
                    value={typeof detailData.assertions === 'string' ? detailData.assertions : JSON.stringify(detailData.assertions, null, 2)}
                    theme="vs-dark"
                    options={{
                      readOnly: true,
                      minimap: { enabled: true }
                    }}
                  />
                ) : (
                  <Empty description="暂无断言配置" />
                )
              )
            }
          ]} />
        ) : null}
      </Drawer>

      {/* 调试记录弹窗 */}
      <Modal
        className="cool-modal"
        title="调试记录"
        open={debugRecordsModalVisible}
        onCancel={() => {
          setDebugRecordsModalVisible(false);
          setSelectedDebugRecord(null);
        }}
        footer={null}
        width={1200}
      >
        {loadingDebugRecords ? (
          <Spin spinning={true} style={{ textAlign: 'center', padding: '40px 0' }}>
            <div>加载调试记录中...</div>
          </Spin>
        ) : (
          <div>
            <Table
              dataSource={debugRecords}
              rowKey="id"
              columns={[
                {
                  title: '执行时间',
                  dataIndex: 'execution_time',
                  key: 'execution_time',
                  width: 180,
                  render: (text) => text ? new Date(text).toLocaleString() : '-'
                },
                {
                  title: '执行结果',
                  dataIndex: 'execution_status',
                  key: 'execution_status',
                  width: 120,
                  render: (status) => (
                    <Tag color={status === 'success' ? 'green' : status === 'failed' ? 'red' : 'orange'}>
                      {status === 'success' ? '成功' : status === 'failed' ? '失败' : status === 'running' ? '执行中' : '待执行'}
                    </Tag>
                  )
                },
                {
                  title: '执行结果摘要',
                  dataIndex: 'execution_result',
                  key: 'execution_result',
                  ellipsis: true
                },
                {
                  title: '耗时',
                  dataIndex: 'duration',
                  key: 'duration',
                  width: 100,
                  render: (duration) => duration ? `${duration}秒` : '-'
                },
                {
                  title: '操作',
                  key: 'action',
                  width: 120,
                  render: (_, record) => (
                    <Button
                      type="link"
                      onClick={() => setSelectedDebugRecord(record)}
                    >
                      查看详情
                    </Button>
                  )
                }
              ]}
              pagination={{
                pageSize: 10,
                showTotal: (total) => `共 ${total} 条记录`
              }}
            />
            
            {selectedDebugRecord && (
              <div style={{ marginTop: 24 }}>
                <h4>调试记录详情</h4>
                <Descriptions column={1} bordered style={{ marginBottom: 16 }}>
                  <Descriptions.Item label="执行时间">
                    {selectedDebugRecord.execution_time ? new Date(selectedDebugRecord.execution_time).toLocaleString() : '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="执行状态">
                    <Tag color={selectedDebugRecord.execution_status === 'success' ? 'green' : 'red'}>
                      {selectedDebugRecord.execution_status === 'success' ? '成功' : '失败'}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="执行结果">
                    {selectedDebugRecord.execution_result || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="耗时">
                    {selectedDebugRecord.duration ? `${selectedDebugRecord.duration}秒` : '-'}
                  </Descriptions.Item>
                  {selectedDebugRecord.error_message && (
                    <Descriptions.Item label="错误信息">
                      <div style={{ maxHeight: 150, overflow: 'auto' }}>
                        <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {selectedDebugRecord.error_message}
                        </pre>
                      </div>
                    </Descriptions.Item>
                  )}
                </Descriptions>
                
                {selectedDebugRecord.debug_logs && (
                  <div>
                    <h4>调试日志</h4>
                    <MonacoEditor
                      height="400px"
                      language="text"
                      value={selectedDebugRecord.debug_logs}
                      theme="vs-dark"
                      options={{
                        readOnly: true,
                        minimap: { enabled: true },
                        wordWrap: 'on',
                        lineNumbers: 'on',
                        automaticLayout: true
                      }}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>

      <Modal
        className="cool-modal"
        title={editingCase?.case_type === 'jmeter' ? '调试性能测试用例（JMeter）' : '调试测试用例'}
        open={debugModalVisible}
        onCancel={() => {
          // 如果正在调试，先中断任务
          if (debugging && debugTaskId) {
            handleCancelDebug();
          }
          // 清除轮询
          if (pollIntervalRef) {
            clearInterval(pollIntervalRef);
            setPollIntervalRef(null);
          }
          setDebugModalVisible(false);
          setDebugResult(null);
          setDebugRealtimeLogs('');
          setDebugging(false);
          setDebugTaskId(null);
        }}
        footer={null}
        width={1200}
      >
        {editingCase && (
          <Tabs defaultActiveKey="config" items={[
            {
              key: 'config',
              label: '调试执行',
              children: (
                <>
              {!debugging && !debugResult && (
                <div style={{ textAlign: 'center', padding: '40px 0' }}>
                  <Form form={debugForm} layout="vertical">
                    <Form.Item>
                      <Space>
                        <Button
                          type="primary"
                          icon={<PlayCircleOutlined />}
                          onClick={handleDebugSubmit}
                          size="large"
                        >
                          {editingCase?.case_type === 'jmeter' ? '执行JMeter性能测试（2线程）' : '执行调试（自动修复）'}
                        </Button>
                        <Button
                          icon={<EditOutlined />}
                          onClick={() => {
                            if (editingCase) {
                              // 调用编辑函数，打开编辑弹窗
                              handleEdit({ type: 'testCase', caseId: editingCase.id });
                            }
                          }}
                          size="large"
                        >
                          修改测试用例
                        </Button>
                        <Button
                          icon={<HistoryOutlined />}
                          onClick={async () => {
                            if (!editingCase) return;
                            setLoadingDebugRecords(true);
                            setDebugRecordsModalVisible(true);
                            setSelectedDebugRecord(null);
                            try {
                              const response = await client.get(`/api/specs/debug/${editingCase.id}?project_id=${id}`);
                              setDebugRecords(response.records || []);
                            } catch (error) {
                              message.error('获取调试记录失败: ' + (error.response?.data?.detail || error.message));
                              setDebugRecords([]);
                            } finally {
                              setLoadingDebugRecords(false);
                            }
                          }}
                          size="large"
                        >
                          查看调试记录
                        </Button>
                      </Space>
                </Form.Item>
                    <Form.Item>
                      <div style={{ color: '#666', fontSize: 14, textAlign: 'center' }}>
                        提示：系统会自动执行测试代码，如果失败会自动调用DeepSeek修复，直到通过或达到最大重试次数
                      </div>
                </Form.Item>
                  </Form>
                </div>
              )}

              {debugging && (
                <div>
                  <div style={{ textAlign: 'center', padding: '20px 0', marginBottom: 20 }}>
                    <Spin size="large" />
                    <div style={{ marginTop: 16, fontSize: 16, color: '#1890ff' }}>
                      {editingCase?.case_type === 'jmeter' ? 'JMeter性能测试执行中，请稍后...' : '测试用例调试执行进行中，请稍后...'}
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <Progress 
                        percent={debugProgress} 
                        status="active"
                        format={(percent) => `${percent}%`}
                        style={{ maxWidth: 400, margin: '0 auto' }}
                      />
                    </div>
                    <div style={{ marginTop: 8, color: '#666', fontSize: 14 }}>
                      {debugMessage}
                    </div>
                    <div style={{ marginTop: 16 }}>
                      <Space>
                        <Button
                          danger
                          icon={<CloseCircleOutlined />}
                          onClick={handleCancelDebug}
                        >
                          中断执行
                        </Button>
                        <Button
                          icon={<EditOutlined />}
                          onClick={() => {
                            if (editingCase) {
                              // 调用编辑函数，打开编辑弹窗
                              handleEdit({ type: 'testCase', caseId: editingCase.id });
                            }
                          }}
                        >
                          修改测试用例
                        </Button>
                        <Button
                          icon={<HistoryOutlined />}
                          onClick={async () => {
                            if (!editingCase) return;
                            setLoadingDebugRecords(true);
                            setDebugRecordsModalVisible(true);
                            setSelectedDebugRecord(null);
                            try {
                              const response = await client.get(`/api/specs/debug/${editingCase.id}?project_id=${id}`);
                              setDebugRecords(response.records || []);
                            } catch (error) {
                              message.error('获取调试记录失败: ' + (error.response?.data?.detail || error.message));
                              setDebugRecords([]);
                            } finally {
                              setLoadingDebugRecords(false);
                            }
                          }}
                        >
                          查看调试记录
                        </Button>
                      </Space>
                    </div>
                  </div>

                  {/* 实时调试日志显示 */}
                  {debugRealtimeLogs && (
                    <Form.Item label="调试日志（实时）">
                  <MonacoEditor
                        height="500px"
                        language="text"
                        value={debugRealtimeLogs}
                    theme="vs-dark"
                    options={{
                          readOnly: true, 
                          minimap: { enabled: true },
                          wordWrap: 'on',
                          lineNumbers: 'on',
                          automaticLayout: true
                    }}
                  />
                </Form.Item>
                  )}
                </div>
              )}

              {!debugging && debugResult && (
                <div>
                  <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <Tag color={debugResult.status === 'success' ? 'green' : debugResult.status === 'cancelled' ? 'orange' : 'red'}>
                        {debugResult.status === 'success' ? '执行成功' : debugResult.status === 'cancelled' ? '已中断' : '执行失败'}
                      </Tag>
                      {debugResult.message && (
                        <span style={{ marginLeft: 8 }}>{debugResult.message}</span>
                      )}
                    </div>
                    <Button
                      icon={<EditOutlined />}
                      onClick={() => {
                        if (editingCase) {
                          // 调用编辑函数，打开编辑弹窗
                          handleEdit({ type: 'testCase', caseId: editingCase.id });
                        }
                      }}
                    >
                      修改测试用例
                    </Button>
                    <Button
                      icon={<HistoryOutlined />}
                      onClick={async () => {
                        if (!editingCase) return;
                        setLoadingDebugRecords(true);
                        setDebugRecordsModalVisible(true);
                        setSelectedDebugRecord(null);
                        try {
                          const response = await client.get(`/api/specs/debug/${editingCase.id}?project_id=${id}`);
                          setDebugRecords(response.records || []);
                        } catch (error) {
                          message.error('获取调试记录失败: ' + (error.response?.data?.detail || error.message));
                          setDebugRecords([]);
                        } finally {
                          setLoadingDebugRecords(false);
                        }
                      }}
                    >
                      查看调试记录
                    </Button>
                  </div>

                  {/* 执行失败时显示修复建议输入框和DeepSeek修复按钮 */}
                  {debugResult.status === 'error' && (
                    <div style={{ marginBottom: 16, padding: 16, background: '#fffbe6', borderRadius: 4, border: '1px solid #ffe58f' }}>
                      <Form.Item label="修复建议（可选）">
                        <TextArea
                          rows={4}
                          placeholder="请输入修复建议，DeepSeek将参考您的建议进行修复..."
                          value={userSuggestion}
                          onChange={(e) => setUserSuggestion(e.target.value)}
                        />
                      </Form.Item>
                      <Form.Item>
                        <Button
                          type="primary"
                          icon={<BugOutlined />}
                          onClick={handleDeepSeekFix}
                          loading={fixing}
                          disabled={fixing}
                        >
                          DeepSeek修复
                        </Button>
                        {fixing && (
                          <span style={{ marginLeft: 8, color: '#666', fontSize: 12 }}>
                            正在调用DeepSeek修复代码...
                          </span>
                        )}
                      </Form.Item>
                    </div>
                  )}

                  {/* 调试日志显示 */}
                  {debugResult.debug_logs && (
                    <Form.Item label="调试日志">
                      <MonacoEditor
                        height="500px"
                        language="text"
                        value={debugResult.debug_logs}
                        theme="vs-dark"
                        options={{
                          readOnly: true, 
                          minimap: { enabled: true },
                          wordWrap: 'on',
                          lineNumbers: 'on',
                          automaticLayout: true
                        }}
                      />
                    </Form.Item>
                  )}
                </div>
              )}
                </>
              )
            },
            ...(debugResult ? [{
              key: 'result',
              label: '执行结果',
              children: (
                <>
                
                {debugResult && (
                  <>
                <Descriptions column={1} bordered>
                  <Descriptions.Item label="状态">
                        <Tag color={debugResult.status === 'success' ? 'green' : 'red'}>
                          {debugResult.status === 'success' ? '通过' : '失败'}
                    </Tag>
                  </Descriptions.Item>
                      {debugResult.attempts && (
                        <Descriptions.Item label="尝试次数">
                          {debugResult.attempts} 次
                  </Descriptions.Item>
                      )}
                      {debugResult.message && (
                        <Descriptions.Item label="消息">
                          {debugResult.message}
                        </Descriptions.Item>
                      )}
                      {debugResult.error && (
                    <Descriptions.Item label="错误信息">
                          <div style={{ maxHeight: 200, overflow: 'auto' }}>
                            <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                              {debugResult.error}
                            </pre>
                          </div>
                    </Descriptions.Item>
                  )}
                </Descriptions>

                    {/* 调试日志 */}
                <div style={{ marginTop: 16 }}>
                      <h4>
                        <Tag color="blue">调试日志</Tag>
                      </h4>
                      <MonacoEditor
                        height="400px"
                        language="text"
                        value={debugResult.debug_logs || debugResult.output || debugResult.error || '暂无调试日志'}
                        theme="vs-dark"
                        options={{ 
                          readOnly: true, 
                          minimap: { enabled: true },
                          wordWrap: 'on',
                          lineNumbers: 'on'
                        }}
                      />
                    </div>

                    {/* 执行输出（成功时） */}
                    {debugResult.output && debugResult.status === 'success' && (
                      <div style={{ marginTop: 16 }}>
                        <h4>
                          <Tag color="green">执行输出</Tag>
                        </h4>
                  <MonacoEditor
                    height="300px"
                          language="text"
                          value={debugResult.output}
                    theme="vs-dark"
                    options={{ readOnly: true, minimap: { enabled: true } }}
                  />
                </div>
                    )}

                    {/* 错误详情（失败时） */}
                    {debugResult.error && (
                <div style={{ marginTop: 16 }}>
                        <h4>
                          <Tag color="red">错误详情</Tag>
                        </h4>
                  <MonacoEditor
                    height="400px"
                          language="text"
                          value={debugResult.error}
                    theme="vs-dark"
                          options={{ 
                            readOnly: true, 
                            minimap: { enabled: true },
                            wordWrap: 'on',
                            lineNumbers: 'on'
                          }}
                  />
                </div>
                    )}

                    {/* 标准错误输出 */}
                    {debugResult.stderr && (
                      <div style={{ marginTop: 16 }}>
                        <h4>
                          <Tag color="orange">标准错误输出 (stderr)</Tag>
                        </h4>
                        <MonacoEditor
                          height="300px"
                          language="text"
                          value={debugResult.stderr}
                          theme="vs-dark"
                          options={{ 
                            readOnly: true, 
                            minimap: { enabled: true },
                            wordWrap: 'on'
                          }}
                        />
                      </div>
                    )}

                    {/* 标准输出 */}
                    {debugResult.stdout && debugResult.status === 'error' && (
                      <div style={{ marginTop: 16 }}>
                        <h4>
                          <Tag color="blue">标准输出 (stdout)</Tag>
                        </h4>
                        <MonacoEditor
                          height="300px"
                          language="text"
                          value={debugResult.stdout}
                          theme="vs-dark"
                          options={{ 
                            readOnly: true, 
                            minimap: { enabled: true },
                            wordWrap: 'on'
                          }}
                        />
                      </div>
                    )}
                  </>
                )}
                
                {!debugResult && debugging && (
                  <Empty description="正在执行测试代码，请稍候..." />
                )}
                </>
              )
            }] : [])
          ]} />
        )}
      </Modal>

      {/* 生成执行任务Modal */}
      <Modal
        className="cool-modal"
        title="生成测试执行任务"
        open={executeTaskModalVisible}
        onOk={async () => {
          try {
            const values = await executeTaskForm.validateFields();
            
            // 检查是否选择了用例或用例集
            if (checkedNodes.length === 0 && (!values.test_case_suite_ids || values.test_case_suite_ids.length === 0)) {
              message.warning('请至少选择一个测试用例或用例集');
              return;
            }
            
            setExecuting(true);
            
            // 如果选择了用例集，使用用例集ID；否则使用单个用例ID
            let taskData = {
              name: values.name,
              scenario: values.scenario || `执行${checkedNodes.length + (values.test_case_suite_ids?.length || 0)}个测试用例/用例集`,
              task_type: 'immediate',
              execution_task_type: values.execution_task_type || 'interface',
              environment_id: values.environment_id,
              auto_prepare: values.auto_prepare !== false,
              max_retries: values.max_retries || 3
            };
            
            // 如果选择了用例集，优先使用用例集
            if (values.test_case_suite_ids && values.test_case_suite_ids.length > 0) {
              // 如果有多个用例集，需要合并或创建多个任务
              // 这里先支持单个用例集
              if (values.test_case_suite_ids.length === 1) {
                taskData.test_case_suite_id = values.test_case_suite_ids[0];
              } else {
                // 多个用例集，创建多个任务或合并
                message.warning('暂不支持多个用例集，请选择一个用例集，或使用单个用例');
                setExecuting(false);
                return;
              }
            } else if (checkedNodes.length > 0) {
              // 使用单个用例
              const testCaseIds = checkedNodes.map(node => node.id);
              taskData.test_case_ids = testCaseIds;
            }
            
            // 创建测试任务
            const response = await client.post(`/api/jobs/?project_id=${id}`, taskData);
            
            message.success('测试任务创建成功，任务已开始执行');
            setExecuteTaskModalVisible(false);
            executeTaskForm.resetFields();
            setCheckedKeys([]);
            setCheckedNodes([]);
            setSelectedSuiteIds([]);
            
            // 可以跳转到任务列表页面
            // window.location.href = `/projects/${id}/test-tasks`;
          } catch (error) {
            message.error('创建测试任务失败: ' + (error.response?.data?.detail || error.message));
          } finally {
            setExecuting(false);
          }
        }}
        onCancel={() => {
          setExecuteTaskModalVisible(false);
          executeTaskForm.resetFields();
          setSelectedSuiteIds([]);
        }}
        width={800}
        okText="创建并执行"
        cancelText="取消"
        confirmLoading={executing}
      >
        <Form form={executeTaskForm} layout="vertical">
          <Form.Item
            name="name"
            label="任务名称"
            rules={[{ required: true, message: '请输入任务名称' }]}
          >
            <Input placeholder="请输入任务名称" />
          </Form.Item>

          <Form.Item
            name="scenario"
            label="执行场景描述"
          >
            <TextArea 
              rows={3} 
              placeholder="描述本次测试的执行场景（可选）"
            />
          </Form.Item>

          <Form.Item
            name="environment_id"
            label="测试环境"
            rules={[{ required: true, message: '请选择测试环境' }]}
          >
            <Select placeholder="选择测试环境">
              {environments.map(env => (
                <Select.Option key={env.id} value={env.id}>
                  {env.name} {env.is_default && <Tag color="green">默认</Tag>}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="execution_task_type"
            label="任务类型"
            rules={[{ required: true, message: '请选择任务类型' }]}
            initialValue="interface"
            tooltip="选择测试任务的执行类型"
          >
            <Select 
              placeholder="选择任务类型"
              onChange={(value) => {
                // 根据任务类型清空已选择的用例，因为用例类型可能不匹配
                if (value === 'performance') {
                  // 性能测试只能选择性能用例
                  const filteredNodes = checkedNodes.filter(node => node.case_type === 'jmeter');
                  setCheckedNodes(filteredNodes);
                  setCheckedKeys(filteredNodes.map(n => n.id));
                } else {
                  // 接口和场景测试只能选择接口用例
                  const filteredNodes = checkedNodes.filter(node => node.case_type !== 'jmeter');
                  setCheckedNodes(filteredNodes);
                  setCheckedKeys(filteredNodes.map(n => n.id));
                }
              }}
            >
              <Select.Option value="scenario">场景任务执行</Select.Option>
              <Select.Option value="interface">接口任务执行</Select.Option>
              <Select.Option value="performance">性能任务执行</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="test_case_suite_ids"
            label="选择用例集（可选）"
            tooltip="可以选择用例集，也可以选择单个用例"
          >
            <Select
              mode="multiple"
              placeholder="选择用例集（可选）"
              value={selectedSuiteIds}
              onChange={(value) => {
                setSelectedSuiteIds(value);
                executeTaskForm.setFieldsValue({ test_case_suite_ids: value });
              }}
              optionRender={(option) => (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{option.label}</span>
                  <Button
                    type="link"
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleEditSuite(option.value);
                    }}
                  >
                    编辑
                  </Button>
                </div>
              )}
            >
              {testCaseSuites.map(suite => (
                <Select.Option key={suite.id} value={suite.id}>
                  {suite.name} ({suite.test_case_count || 0}个接口)
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="auto_prepare"
            label="自动准备"
            valuePropName="checked"
            initialValue={true}
            tooltip="自动分析依赖关系、构造测试数据"
          >
            <Switch checkedChildren="是" unCheckedChildren="否" />
          </Form.Item>

          <Form.Item
            name="max_retries"
            label="最大重试次数"
            initialValue={3}
          >
            <InputNumber min={0} max={10} />
          </Form.Item>

          <Form.Item label="已选择的测试用例">
            <div style={{ maxHeight: 200, overflowY: 'auto', border: '1px solid #d9d9d9', padding: 8, borderRadius: 4 }}>
              {checkedNodes.length > 0 ? (
                <Space direction="vertical" style={{ width: '100%' }}>
                  {checkedNodes.map((node, index) => (
                    <div key={node.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>
                        <Tag color={node.case_type === 'pytest' ? 'blue' : 'orange'}>
                          {node.case_type === 'pytest' ? '接口用例' : '性能用例'}
                        </Tag>
                        {node.name || `用例 #${node.id}`}
                      </span>
                    </div>
                  ))}
                </Space>
              ) : (
                <span style={{ color: '#999' }}>未选择单个用例（可通过用例集选择）</span>
              )}
            </div>
            <div style={{ marginTop: 8, color: '#666', fontSize: 12 }}>
              共选择 {checkedNodes.length} 个测试用例
              {selectedSuiteIds.length > 0 && `，${selectedSuiteIds.length} 个用例集`}
            </div>
          </Form.Item>

          {/* 显示选中的用例集信息 */}
          {selectedSuiteIds.length > 0 && (
            <Form.Item label="已选择的用例集">
              <div style={{ maxHeight: 200, overflowY: 'auto', border: '1px solid #d9d9d9', padding: 8, borderRadius: 4 }}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  {selectedSuiteIds.map(suiteId => {
                    const suite = testCaseSuites.find(s => s.id === suiteId);
                    if (!suite) return null;
                    return (
                      <div key={suiteId} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 8, background: '#f5f5f5', borderRadius: 4 }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 'bold', marginBottom: 4 }}>{suite.name}</div>
                          <div style={{ fontSize: 12, color: '#666' }}>
                            接口数: {suite.test_case_count || 0}
                            {suite.description && ` | 描述: ${suite.description}`}
                          </div>
                        </div>
                        <Button
                          type="link"
                          size="small"
                          onClick={() => handleEditSuite(suiteId)}
                        >
                          编辑用例集
                        </Button>
                      </div>
                    );
                  })}
                </Space>
              </div>
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* 编辑用例集Modal */}
      <Modal
        className="cool-modal"
        title="编辑用例集信息"
        open={!!editingSuiteInterfaces && Object.keys(editingSuiteInterfaces).length > 0}
        onOk={async () => {
          try {
            // 保存编辑后的用例集信息
            for (const suiteId of Object.keys(editingSuiteInterfaces)) {
              const interfaces = editingSuiteInterfaces[suiteId];
              // 提取接口ID列表（保持顺序）
              const testCaseIds = interfaces.map(iface => iface.id);
              
              // 调用更新用例集的API
              await client.put(`/api/suites/${suiteId}?project_id=${id}`, {
                test_case_ids: testCaseIds
              });
            }
            
            message.success('用例集信息已更新');
            setEditingSuiteInterfaces({});
            await fetchTestCaseSuites();
          } catch (error) {
            message.error('保存用例集信息失败: ' + (error.response?.data?.detail || error.message));
          }
        }}
        onCancel={() => {
          setEditingSuiteInterfaces({});
        }}
        width={1000}
        okText="保存"
        cancelText="取消"
      >
        {Object.keys(editingSuiteInterfaces).map(suiteId => {
          const suite = testCaseSuites.find(s => s.id === parseInt(suiteId));
          const interfaces = editingSuiteInterfaces[suiteId] || [];
          
          // 处理接口顺序调整
          const moveInterface = (fromIndex, toIndex) => {
            const newInterfaces = [...interfaces];
            const [moved] = newInterfaces.splice(fromIndex, 1);
            newInterfaces.splice(toIndex, 0, moved);
            // 更新顺序号
            newInterfaces.forEach((iface, index) => {
              iface.order = index + 1;
            });
            setEditingSuiteInterfaces({
              [suiteId]: newInterfaces
            });
          };
          
          return (
            <div key={suiteId}>
              <h3>{suite?.name || `用例集 #${suiteId}`}</h3>
              <p style={{ color: '#666', marginBottom: 16 }}>
                接口数量: {interfaces.length} | 
                可以拖拽调整顺序（点击上移/下移按钮）
              </p>
              <Table
                size="small"
                dataSource={interfaces}
                columns={[
                  { 
                    title: '顺序', 
                    dataIndex: 'order', 
                    key: 'order', 
                    width: 80,
                    render: (text, record, index) => (
                      <Space>
                        <span>{text}</span>
                        {index > 0 && (
                          <Button
                            type="link"
                            size="small"
                            onClick={() => moveInterface(index, index - 1)}
                          >
                            上移
                          </Button>
                        )}
                        {index < interfaces.length - 1 && (
                          <Button
                            type="link"
                            size="small"
                            onClick={() => moveInterface(index, index + 1)}
                          >
                            下移
                          </Button>
                        )}
                      </Space>
                    )
                  },
                  { title: '接口名称', dataIndex: 'name', key: 'name' },
                  { 
                    title: '方法', 
                    dataIndex: 'method', 
                    key: 'method', 
                    width: 100,
                    render: (method) => <Tag color={method === 'POST' ? 'blue' : method === 'GET' ? 'green' : 'default'}>{method}</Tag>
                  },
                  { title: '路径', dataIndex: 'path', key: 'path', ellipsis: true },
                  {
                    title: '操作',
                    key: 'action',
                    width: 100,
                    render: (_, record, index) => (
                      <Button
                        type="link"
                        danger
                        size="small"
                        onClick={() => {
                          const newInterfaces = interfaces.filter((_, i) => i !== index);
                          newInterfaces.forEach((iface, i) => {
                            iface.order = i + 1;
                          });
                          setEditingSuiteInterfaces({
                            [suiteId]: newInterfaces
                          });
                        }}
                      >
                        删除
                      </Button>
                    )
                  }
                ]}
                pagination={false}
                rowKey={(record, index) => record.id || `interface_${index}`}
              />
            </div>
          );
        })}
      </Modal>
    </div>
  );
};

export default TestCases;
