import React, { useState, useEffect } from 'react';
import { Card, List, Button, Modal, Table, Tag, message, Space, Descriptions, Popconfirm, Progress, Badge, Collapse, Checkbox } from 'antd';
import { useParams } from 'react-router-dom';
import { EyeOutlined, PlusOutlined, DeleteOutlined, EditOutlined, PlusCircleOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import client from '../api/client';
import { getErrorMessage } from '../utils/errorHandler';

const ScenarioSuites = () => {
  const { id } = useParams();
  const [suites, setSuites] = useState([]);
  const [loading, setLoading] = useState(false);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedSuite, setSelectedSuite] = useState(null);
  const [interfaces, setInterfaces] = useState([]);
  const [interfacesLoading, setInterfacesLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [addInterfaceModalVisible, setAddInterfaceModalVisible] = useState(false);
  const [editInterfaceModalVisible, setEditInterfaceModalVisible] = useState(false);
  const [editingInterface, setEditingInterface] = useState(null);
  const [editingIndex, setEditingIndex] = useState(-1);
  const [availableInterfaces, setAvailableInterfaces] = useState([]);
  const [availableInterfacesLoading, setAvailableInterfacesLoading] = useState(false);
  const [generatingTestCases, setGeneratingTestCases] = useState({}); // 记录每个suite的生成状态
  const [taskStatuses, setTaskStatuses] = useState({}); // 记录任务状态 {taskId: {status, progress, message, testCaseId}}
  const [generatedTestCases, setGeneratedTestCases] = useState({}); // 记录生成的测试用例 {suiteId_caseType_generateType: [testCases]}
  const [selectedSuiteIds, setSelectedSuiteIds] = useState([]);
  const [batchDeleting, setBatchDeleting] = useState(false);

  useEffect(() => {
    fetchSuites();
    
    const refreshKey = `scenario_suites_refresh_${id}`;
    
    // 监听依赖分析完成的通知，自动刷新数据
    const handleStorageChange = (e) => {
      // 检查是否是场景用例集刷新标记
      if (e.key === refreshKey) {
        console.log('检测到依赖分析完成，自动刷新场景用例集数据');
        fetchSuites();
      }
    };
    
    // 监听storage事件（跨标签页通信）
    window.addEventListener('storage', handleStorageChange);
    
    // 定期检查刷新标记（用于同页面内的事件，因为同页面的storage事件可能不会触发）
    const checkInterval = setInterval(() => {
      if (localStorage.getItem(refreshKey)) {
        console.log('检测到依赖分析完成标记，自动刷新场景用例集数据');
        fetchSuites();
        localStorage.removeItem(refreshKey);
      }
    }, 1000); // 每秒检查一次
    
    return () => {
      window.removeEventListener('storage', handleStorageChange);
      clearInterval(checkInterval);
    };
  }, [id]);

  const fetchSuites = async () => {
    setLoading(true);
    try {
      const data = await client.get(`/api/suites/?project_id=${id}`);
      setSuites(data || []);
      setSelectedSuiteIds([]);
    } catch (error) {
      console.error('获取小场景用例集失败', error);
      const errorMsg = getErrorMessage(error);
      message.error('获取小场景用例集失败: ' + errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateFromDependencies = async () => {
    setGenerating(true);
    try {
      const response = await client.post(`/api/suites/generate-from-dependencies/${id}`);
      message.success(response.message || `成功生成 ${response.stored_count || 0} 个小场景用例集`);
      
      // 刷新列表
      await fetchSuites();
    } catch (error) {
      console.error('生成小场景用例集失败', error);
      const errorMsg = getErrorMessage(error);
      message.error('生成小场景用例集失败: ' + errorMsg);
    } finally {
      setGenerating(false);
    }
  };

  const handleSelectSuite = (suiteId, checked) => {
    setSelectedSuiteIds((prev) => {
      if (checked) {
        return Array.from(new Set([...prev, suiteId]));
      }
      return prev.filter((id) => id !== suiteId);
    });
  };

  const handleBatchDeleteSuites = async () => {
    if (!selectedSuiteIds.length) {
      message.warning('请选择要删除的用例集');
      return;
    }
    setBatchDeleting(true);
    try {
      // 确保suite_ids是整数数组
      const suiteIds = selectedSuiteIds.map(id => typeof id === 'string' ? parseInt(id, 10) : id);
      await client.delete(`/api/suites/batch?project_id=${id}`, {
        data: { suite_ids: suiteIds }
      });
      message.success('批量删除成功');
      await fetchSuites();
      setSelectedSuiteIds([]); // 清空选中项
    } catch (error) {
      console.error('批量删除失败', error);
      const errorMsg = getErrorMessage(error);
      message.error('批量删除失败: ' + errorMsg);
    } finally {
      setBatchDeleting(false);
    }
  };

  // 从场景用例集生成测试用例
  const handleGenerateTestCases = async (suiteId, caseType, generateType) => {
    const key = `${suiteId}_${caseType}_${generateType}`;
    setGeneratingTestCases(prev => ({ ...prev, [key]: true }));
    
    try {
      const response = await client.post(
        `/api/suites/${suiteId}/generate-specs?case_type=${caseType}&generate_type=${generateType}`
      );
      
      // 保存task_id并开始轮询
      const taskId = response.task_id;
      const testCaseId = response.test_case_id;
      
      if (taskId) {
        // 初始化任务状态
        setTaskStatuses(prev => ({
          ...prev,
          [taskId]: {
            status: 'PENDING',
            progress: 0,
            message: '任务已提交，等待执行...',
            testCaseId: testCaseId,
            suiteId: suiteId,
            caseType: caseType,
            generateType: generateType
          }
        }));
        
        // 开始轮询任务状态
        pollTaskStatus(taskId, testCaseId, suiteId, caseType, generateType);
      }
      
      message.success(response.message || '测试用例生成任务已提交');
    } catch (error) {
      console.error('生成测试用例失败', error);
      const errorMsg = getErrorMessage(error);
      message.error('生成测试用例失败: ' + errorMsg);
      setGeneratingTestCases(prev => ({ ...prev, [key]: false }));
    }
  };

  // 轮询任务状态
  const pollTaskStatus = async (taskId, testCaseId, suiteId, caseType, generateType) => {
    const key = `${suiteId}_${caseType}_${generateType}`;
    const pollInterval = setInterval(async () => {
      try {
        // 通过测试用例ID获取状态（因为测试用例会更新进度）
        const testCase = await client.get(`/api/specs/${testCaseId}`);
        
        const status = testCase.status || 'generating';
        const progress = testCase.generation_progress || 0;
        const errorMessage = testCase.error_message;
        
        // 更新任务状态
        setTaskStatuses(prev => ({
          ...prev,
          [taskId]: {
            status: status === 'completed' ? 'SUCCESS' : status === 'failed' ? 'FAILURE' : 'PROGRESS',
            progress: progress,
            message: status === 'completed' ? '生成完成' : 
                     status === 'failed' ? (errorMessage || '生成失败') : 
                     `生成中... ${progress}%`,
            testCaseId: testCaseId,
            suiteId: suiteId,
            caseType: caseType,
            generateType: generateType
          }
        }));
        
        // 如果任务完成或失败，停止轮询
        if (status === 'completed' || status === 'failed') {
          clearInterval(pollInterval);
          setGeneratingTestCases(prev => ({ ...prev, [key]: false }));
          
          // 如果成功，刷新测试用例列表并添加到生成列表
          if (status === 'completed') {
            setGeneratedTestCases(prev => ({
              ...prev,
              [key]: [...(prev[key] || []), testCase]
            }));
            
            // 刷新测试用例列表
            message.success('测试用例生成完成');
          } else {
            message.error('测试用例生成失败: ' + (errorMessage || '未知错误'));
          }
        }
      } catch (error) {
        console.error('获取任务状态失败', error);
        // 继续轮询，不中断
      }
    }, 2000); // 每2秒轮询一次
    
    // 30分钟后自动停止轮询（防止内存泄漏）
    setTimeout(() => {
      clearInterval(pollInterval);
    }, 30 * 60 * 1000);
  };

  // 调整接口顺序
  const handleMoveInterface = async (index, direction) => {
    if (!selectedSuite) return;
    
    const newInterfaces = [...interfaces];
    if (direction === 'up' && index > 0) {
      [newInterfaces[index - 1], newInterfaces[index]] = [newInterfaces[index], newInterfaces[index - 1]];
    } else if (direction === 'down' && index < newInterfaces.length - 1) {
      [newInterfaces[index], newInterfaces[index + 1]] = [newInterfaces[index + 1], newInterfaces[index]];
    }
    
    // 更新顺序
    newInterfaces.forEach((iface, idx) => {
      iface.order = idx + 1;
    });
    
    setInterfaces(newInterfaces);
    
    // 保存到后端
    try {
      const interfaceIds = newInterfaces.map(iface => {
        if (iface.id === '__LOGIN_INTERFACE__' || iface.interface_id === '__LOGIN_INTERFACE__') {
          return '__LOGIN_INTERFACE__';
        }
        return String(iface.id || iface.interface_id);
      });
      
      await client.put(`/api/suites/${selectedSuite.id}`, {
        test_case_ids: interfaceIds
      });
      
      message.success('接口顺序已更新');
      await fetchSuiteInterfaces(selectedSuite.id);
    } catch (error) {
      console.error('更新接口顺序失败', error);
      const errorMsg = getErrorMessage(error);
      message.error('更新接口顺序失败: ' + errorMsg);
      // 恢复原顺序
      await fetchSuiteInterfaces(selectedSuite.id);
    }
  };

  // 删除接口
  const handleDeleteInterface = async (index) => {
    if (!selectedSuite) return;
    
    const newInterfaces = interfaces.filter((_, idx) => idx !== index);
    
    // 更新顺序
    newInterfaces.forEach((iface, idx) => {
      iface.order = idx + 1;
    });
    
    setInterfaces(newInterfaces);
    
    // 保存到后端
    try {
      const interfaceIds = newInterfaces.map(iface => {
        if (iface.id === '__LOGIN_INTERFACE__' || iface.interface_id === '__LOGIN_INTERFACE__') {
          return '__LOGIN_INTERFACE__';
        }
        return String(iface.id || iface.interface_id);
      });
      
      await client.put(`/api/suites/${selectedSuite.id}`, {
        test_case_ids: interfaceIds
      });
      
      message.success('接口已删除');
      await fetchSuiteInterfaces(selectedSuite.id);
    } catch (error) {
      console.error('删除接口失败', error);
      const errorMsg = getErrorMessage(error);
      message.error('删除接口失败: ' + errorMsg);
      // 恢复原列表
      await fetchSuiteInterfaces(selectedSuite.id);
    }
  };

  // 编辑接口
  const handleEditInterface = (record, index) => {
    setEditingInterface({ ...record });
    setEditingIndex(index);
    setEditInterfaceModalVisible(true);
  };

  // 保存编辑的接口
  const handleSaveEditInterface = async () => {
    if (!selectedSuite || !editingInterface || editingIndex === -1) return;
    
    const newInterfaces = [...interfaces];
    newInterfaces[editingIndex] = { ...editingInterface };
    
    setInterfaces(newInterfaces);
    
    // 保存到后端
    try {
      const interfaceIds = newInterfaces.map(iface => {
        if (iface.id === '__LOGIN_INTERFACE__' || iface.interface_id === '__LOGIN_INTERFACE__') {
          return '__LOGIN_INTERFACE__';
        }
        return String(iface.id || iface.interface_id);
      });
      
      await client.put(`/api/suites/${selectedSuite.id}`, {
        test_case_ids: interfaceIds
      });
      
      message.success('接口已更新');
      setEditInterfaceModalVisible(false);
      setEditingInterface(null);
      setEditingIndex(-1);
      await fetchSuiteInterfaces(selectedSuite.id);
    } catch (error) {
      console.error('更新接口失败', error);
      const errorMsg = getErrorMessage(error);
      message.error('更新接口失败: ' + errorMsg);
      await fetchSuiteInterfaces(selectedSuite.id);
    }
  };

  // 打开添加接口弹窗
  const handleOpenAddInterface = async () => {
    setAddInterfaceModalVisible(true);
    setAvailableInterfacesLoading(true);
    try {
      // 获取所有可用的接口
      const data = await client.get(`/api/endpoints/?project_id=${id}`);
      // 过滤掉已经在用例集中的接口
      const existingIds = new Set(interfaces.map(iface => String(iface.id || iface.interface_id)));
      const available = (data || []).filter(iface => 
        !existingIds.has(String(iface.id)) && 
        iface.response_body && 
        Object.keys(iface.response_body).length > 0
      );
      setAvailableInterfaces(available);
    } catch (error) {
      console.error('获取可用接口失败', error);
      message.error('获取可用接口失败');
    } finally {
      setAvailableInterfacesLoading(false);
    }
  };

  // 添加接口
  const handleAddInterface = async (selectedInterface) => {
    if (!selectedSuite || !selectedInterface) return;
    
    const newInterface = {
      id: selectedInterface.id,
      interface_id: selectedInterface.id,
      name: selectedInterface.name || '',
      method: selectedInterface.method || 'GET',
      url: selectedInterface.url || '',
      path: selectedInterface.path || '',
      base_url: selectedInterface.base_url || '',
      service: selectedInterface.service || '',
      headers: selectedInterface.headers || {},
      request_body: selectedInterface.request_body || {},
      response_headers: selectedInterface.response_headers || {},
      response_body: selectedInterface.response_body || {},
      description: selectedInterface.description || '',
      order: interfaces.length + 1
    };
    
    const newInterfaces = [...interfaces, newInterface];
    setInterfaces(newInterfaces);
    setAddInterfaceModalVisible(false);
    
    // 保存到后端
    try {
      const interfaceIds = newInterfaces.map(iface => {
        if (iface.id === '__LOGIN_INTERFACE__' || iface.interface_id === '__LOGIN_INTERFACE__') {
          return '__LOGIN_INTERFACE__';
        }
        return String(iface.id || iface.interface_id);
      });
      
      await client.put(`/api/suites/${selectedSuite.id}`, {
        test_case_ids: interfaceIds
      });
      
      message.success('接口已添加');
      await fetchSuiteInterfaces(selectedSuite.id);
    } catch (error) {
      console.error('添加接口失败', error);
      const errorMsg = getErrorMessage(error);
      message.error('添加接口失败: ' + errorMsg);
      await fetchSuiteInterfaces(selectedSuite.id);
    }
  };

  const fetchSuiteInterfaces = async (suiteId) => {
    setInterfacesLoading(true);
    try {
      const suite = await client.get(`/api/suites/${suiteId}`);
      setSelectedSuite(suite);
      
      // 获取依赖链中的接口列表
      if (suite.test_cases && suite.test_cases.length > 0) {
        // 如果test_cases已经包含接口信息（从依赖链中获取的）
        const interfaceList = suite.test_cases.map((testCase, index) => {
          // 如果testCase已经包含接口信息（从依赖链返回的）
          if (testCase.interface_id || testCase.name || testCase.url) {
            return {
              id: testCase.id || testCase.interface_id,
              interface_id: testCase.interface_id || testCase.id,
              name: testCase.name || testCase.interface_id || '',
              method: testCase.method || 'GET',
              url: testCase.url || '',
              path: testCase.path || '',
              base_url: testCase.base_url || '',
              service: testCase.service || '',
              headers: testCase.headers || {},
              request_body: testCase.request_body || {},
              response_headers: testCase.response_headers || {},
              response_body: testCase.response_body || {},
              description: testCase.description || '',
              order: index + 1  // 依赖链中的顺序
            };
          }
          return null;
        }).filter(i => i !== null);
        
        setInterfaces(interfaceList);
      } else if (suite.test_case_ids && suite.test_case_ids.length > 0) {
        // 兼容旧格式：从test_case_ids获取接口信息
        // 检查是否是接口ID（字符串）还是测试用例ID（整数）
        const isInterfaceIds = suite.test_case_ids.length > 0 && typeof suite.test_case_ids[0] === 'string';
        
        if (isInterfaceIds) {
          // 是接口ID列表（依赖链）
          // 尝试从接口ID获取接口详情
          const interfacePromises = suite.test_case_ids.map(async (interfaceId) => {
            try {
              // 尝试提取接口ID
              if (interfaceId.startsWith('api_')) {
                const docId = interfaceId.replace('api_', '');
                const interfaceData = await client.get(`/api/endpoints/${docId}`);
                return interfaceData;
              } else {
                // 尝试通过其他方式查找
                return { interface_id: interfaceId, name: interfaceId };
              }
            } catch (err) {
              console.error(`获取接口 ${interfaceId} 失败`, err);
              return { interface_id: interfaceId, name: interfaceId };
            }
          });
          
          const interfaceList = await Promise.all(interfacePromises);
          setInterfaces(interfaceList.filter(i => i !== null));
        } else {
          // 是测试用例ID列表
          const casePromises = suite.test_case_ids.map(async (caseId) => {
            try {
              const testCase = await client.get(`/api/specs/${caseId}`);
              if (testCase.interface_id) {
                const interfaceData = await client.get(`/api/endpoints/${testCase.interface_id}`);
                return {
                  ...interfaceData,
                  testCaseId: testCase.id,
                  testCaseName: testCase.name
                };
              }
              return null;
            } catch (err) {
              console.error(`获取测试用例 ${caseId} 失败`, err);
              return null;
            }
          });
          
          const cases = await Promise.all(casePromises);
          setInterfaces(cases.filter(i => i !== null));
        }
      } else {
        setInterfaces([]);
      }
    } catch (error) {
      console.error('获取用例集详情失败', error);
      const errorMsg = getErrorMessage(error);
      message.error('获取用例集详情失败: ' + errorMsg);
    } finally {
      setInterfacesLoading(false);
    }
  };

  const handleViewDetail = async (suite) => {
    setDetailModalVisible(true);
    await fetchSuiteInterfaces(suite.id);
  };

  const interfaceColumns = [
    {
      title: '顺序',
      dataIndex: 'order',
      key: 'order',
      width: 80,
      render: (order) => order || '-'
    },
    {
      title: '接口名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: '请求方法',
      dataIndex: 'method',
      key: 'method',
      width: 100,
      render: (method) => {
        const colorMap = {
          GET: 'blue',
          POST: 'green',
          PUT: 'orange',
          DELETE: 'red',
          PATCH: 'purple',
        };
        return <Tag color={colorMap[method] || 'default'}>{method}</Tag>;
      },
    },
    {
      title: '请求路径',
      dataIndex: 'path',
      key: 'path',
      width: 250,
    },
    {
      title: 'Base URL',
      dataIndex: 'base_url',
      key: 'base_url',
      width: 200,
    },
    {
      title: '请求头',
      dataIndex: 'headers',
      key: 'headers',
      width: 200,
      render: (headers) => {
        if (!headers || typeof headers !== 'object') return '-';
        return (
          <div style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {JSON.stringify(headers).substring(0, 100)}
            {JSON.stringify(headers).length > 100 ? '...' : ''}
          </div>
        );
      },
    },
    {
      title: '请求体',
      dataIndex: 'request_body',
      key: 'request_body',
      width: 200,
      render: (body) => {
        if (!body || (typeof body !== 'object' && typeof body !== 'string')) return '-';
        const bodyStr = typeof body === 'string' ? body : JSON.stringify(body);
        return (
          <div style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {bodyStr.substring(0, 100)}
            {bodyStr.length > 100 ? '...' : ''}
          </div>
        );
      },
    },
    {
      title: '响应头',
      dataIndex: 'response_headers',
      key: 'response_headers',
      width: 200,
      render: (headers) => {
        if (!headers || typeof headers !== 'object') return '-';
        return (
          <div style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {JSON.stringify(headers).substring(0, 100)}
            {JSON.stringify(headers).length > 100 ? '...' : ''}
          </div>
        );
      },
    },
    {
      title: '响应体',
      dataIndex: 'response_body',
      key: 'response_body',
      width: 200,
      render: (body) => {
        if (!body || (typeof body !== 'object' && typeof body !== 'string')) return '-';
        const bodyStr = typeof body === 'string' ? body : JSON.stringify(body);
        return (
          <div style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {bodyStr.substring(0, 100)}
            {bodyStr.length > 100 ? '...' : ''}
          </div>
        );
      },
    },
  ];

  return (
    <div>
      <Card 
        title="小场景用例集"
        extra={
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleGenerateFromDependencies}
              loading={generating}
            >
              生成用例集
            </Button>
            <Popconfirm
              title="确认批量删除选中的用例集吗？"
              onConfirm={handleBatchDeleteSuites}
              okButtonProps={{ danger: true, disabled: !selectedSuiteIds.length }}
              disabled={!selectedSuiteIds.length}
            >
              <Button
                danger
                icon={<DeleteOutlined />}
                loading={batchDeleting}
                disabled={!selectedSuiteIds.length}
              >
                批量删除
              </Button>
            </Popconfirm>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <List
          loading={loading}
          dataSource={suites}
          locale={{ emptyText: '暂无小场景用例集' }}
          itemLayout="horizontal"
          renderItem={(suite) => (
            <List.Item
              actions={[
                <Button
                  key="generate"
                  type="primary"
                  size="small"
                  onClick={() => handleGenerateTestCases(suite.id, 'pytest', 'scenario')}
                  loading={generatingTestCases[`${suite.id}_pytest_scenario`]}
                >
                  生成接口场景用例
                </Button>,
                <Button
                  key="view"
                  type="link"
                  icon={<EyeOutlined />}
                  onClick={() => handleViewDetail(suite)}
                >
                  查看详情
                </Button>,
              ]}
            >
              <Checkbox
                checked={selectedSuiteIds.includes(suite.id)}
                onChange={(e) => handleSelectSuite(suite.id, e.target.checked)}
                style={{ marginRight: 12 }}
              />
              <List.Item.Meta
                title={suite.name}
                description={
                  <Space size="middle">
                    <span>接口数: {suite.test_case_count || 0}</span>
                    {suite.description && <span>描述: {suite.description}</span>}
                    {suite.tags && suite.tags.split(',').map((tag, idx) => (
                      <Tag key={idx}>{tag.trim()}</Tag>
                    ))}
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Card>

      <Modal
        title={`用例集详情: ${selectedSuite?.name || ''}`}
        open={detailModalVisible}
        onCancel={() => {
          setDetailModalVisible(false);
          setSelectedSuite(null);
          setInterfaces([]);
        }}
        footer={[
          <Button key="close" onClick={() => {
            setDetailModalVisible(false);
            setSelectedSuite(null);
            setInterfaces([]);
          }}>
            关闭
          </Button>,
        ]}
        width={1200}
      >
        {selectedSuite && (
          <div>
            <Descriptions column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="用例集名称">{selectedSuite.name}</Descriptions.Item>
              <Descriptions.Item label="接口数">{selectedSuite.test_case_count || 0}</Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>
                {selectedSuite.description || '-'}
              </Descriptions.Item>
              {selectedSuite.tags && (
                <Descriptions.Item label="标签" span={2}>
                  {selectedSuite.tags.split(',').map((tag, idx) => (
                    <Tag key={idx}>{tag.trim()}</Tag>
                  ))}
                </Descriptions.Item>
              )}
            </Descriptions>

            <div style={{ marginTop: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h4 style={{ margin: 0 }}>接口列表:</h4>
                <Button 
                  type="primary" 
                  icon={<PlusCircleOutlined />}
                  onClick={handleOpenAddInterface}
                >
                  添加接口
                </Button>
              </div>
              <Table
                loading={interfacesLoading}
                columns={interfaceColumns.map(col => {
                  if (col.key === 'order') {
                    return {
                      ...col,
                      render: (order, record, index) => (
                        <Space>
                          <Button
                            type="link"
                            size="small"
                            icon={<ArrowUpOutlined />}
                            disabled={index === 0}
                            onClick={() => handleMoveInterface(index, 'up')}
                            title="上移"
                          />
                          <span>{order || index + 1}</span>
                          <Button
                            type="link"
                            size="small"
                            icon={<ArrowDownOutlined />}
                            disabled={index === interfaces.length - 1}
                            onClick={() => handleMoveInterface(index, 'down')}
                            title="下移"
                          />
                        </Space>
                      )
                    };
                  }
                  return col;
                }).concat([
                  {
                    title: '操作',
                    key: 'action',
                    width: 150,
                    fixed: 'right',
                    render: (_, record, index) => (
                      <Space>
                        <Button
                          type="link"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => handleEditInterface(record, index)}
                        >
                          编辑
                        </Button>
                        <Popconfirm
                          title="确定要删除这个接口吗？"
                          onConfirm={() => handleDeleteInterface(index)}
                          okText="确定"
                          cancelText="取消"
                        >
                          <Button
                            type="link"
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                          >
                            删除
                          </Button>
                        </Popconfirm>
                      </Space>
                    )
                  }
                ])}
                dataSource={interfaces.map((iface, idx) => ({
                  ...iface,
                  key: iface.id || iface.interface_id || idx,
                  order: iface.order || idx + 1,
                }))}
                pagination={false}
                scroll={{ x: 1400 }}
                expandable={{
                  expandedRowRender: (record) => (
                    <div style={{ padding: '16px', background: '#f5f5f5' }}>
                      <Descriptions column={1} bordered size="small">
                        <Descriptions.Item label="请求头">
                          <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                            {JSON.stringify(record.headers || {}, null, 2)}
                          </pre>
                        </Descriptions.Item>
                        <Descriptions.Item label="请求参数">
                          <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                            {JSON.stringify(record.params || {}, null, 2)}
                          </pre>
                        </Descriptions.Item>
                        <Descriptions.Item label="请求体">
                          <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                            {typeof record.request_body === 'string'
                              ? record.request_body
                              : JSON.stringify(record.request_body || {}, null, 2)}
                          </pre>
                        </Descriptions.Item>
                        <Descriptions.Item label="响应头">
                          <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                            {JSON.stringify(record.response_headers || {}, null, 2)}
                          </pre>
                        </Descriptions.Item>
                        <Descriptions.Item label="响应体">
                          <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                            {typeof record.response_body === 'string'
                              ? record.response_body
                              : JSON.stringify(record.response_body || {}, null, 2)}
                          </pre>
                        </Descriptions.Item>
                        <Descriptions.Item label="响应状态码">
                          {record.status_code || '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="版本">
                          {record.version || '-'}
                        </Descriptions.Item>
                      </Descriptions>
                    </div>
                  ),
                }}
              />
            </div>
          </div>
        )}
      </Modal>

      {/* 添加接口弹窗 */}
      <Modal
        title="添加接口"
        open={addInterfaceModalVisible}
        onCancel={() => setAddInterfaceModalVisible(false)}
        footer={null}
        width={800}
      >
        <Table
          loading={availableInterfacesLoading}
          columns={[
            { title: '接口名称', dataIndex: 'name', key: 'name' },
            { title: '方法', dataIndex: 'method', key: 'method', render: (method) => <Tag color={method === 'GET' ? 'blue' : method === 'POST' ? 'green' : 'orange'}>{method}</Tag> },
            { title: 'URL', dataIndex: 'url', key: 'url' },
            {
              title: '操作',
              key: 'action',
              render: (_, record) => (
                <Button
                  type="primary"
                  size="small"
                  onClick={() => handleAddInterface(record)}
                >
                  添加
                </Button>
              )
            }
          ]}
          dataSource={availableInterfaces}
          pagination={{ pageSize: 10 }}
          rowKey="id"
        />
      </Modal>

      {/* 编辑接口弹窗 */}
      <Modal
        title="编辑接口"
        open={editInterfaceModalVisible}
        onOk={handleSaveEditInterface}
        onCancel={() => {
          setEditInterfaceModalVisible(false);
          setEditingInterface(null);
          setEditingIndex(-1);
        }}
        width={800}
      >
        {editingInterface && (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="接口名称">
              <span>{editingInterface.name}</span>
            </Descriptions.Item>
            <Descriptions.Item label="Base URL">
              <span>{editingInterface.base_url || '-'}</span>
            </Descriptions.Item>
            <Descriptions.Item label="Path">
              <span>{editingInterface.path || '-'}</span>
            </Descriptions.Item>
            <Descriptions.Item label="请求头">
              <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                {JSON.stringify(editingInterface.headers || {}, null, 2)}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="请求体">
              <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                {JSON.stringify(editingInterface.request_body || {}, null, 2)}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="响应头">
              <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                {JSON.stringify(editingInterface.response_headers || {}, null, 2)}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="响应体">
              <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                {JSON.stringify(editingInterface.response_body || {}, null, 2)}
              </pre>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default ScenarioSuites;
