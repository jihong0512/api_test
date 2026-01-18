import React, { useState, useEffect } from 'react';
import { 
  Button, Modal, Form, Input, Select, message, Space, Tag, 
  Descriptions, Popconfirm, Divider, Badge, InputNumber, Tooltip, Progress, Radio, Checkbox, Spin
} from 'antd';
import { 
  EditOutlined, DeleteOutlined, BugOutlined, EyeOutlined, 
  CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined,
  BranchesOutlined, FileTextOutlined, ThunderboltOutlined, CodeOutlined
} from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import client from '../api/client';
import { getErrorMessage } from '../utils/errorHandler';
import '../styles/animations.css';
import '../styles/minimal-card.css';

const { Option } = Select;
const { TextArea } = Input;

const Interfaces = () => {
  const { id } = useParams();
  const [interfaces, setInterfaces] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [debugModalVisible, setDebugModalVisible] = useState(false);
  const [viewModalVisible, setViewModalVisible] = useState(false);
  const [editingInterface, setEditingInterface] = useState(null);
  const [debugResponse, setDebugResponse] = useState(null);
  const [debugLoading, setDebugLoading] = useState(false);
  const [form] = Form.useForm();
  const [debugForm] = Form.useForm();
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [generateModalVisible, setGenerateModalVisible] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [caseType, setCaseType] = useState('pytest');
  const [taskStatuses, setTaskStatuses] = useState({}); // {testCaseId: {status, progress, message}}
  const [progressModalVisible, setProgressModalVisible] = useState(false);

  useEffect(() => {
    fetchInterfaces();
  }, [id]);

  const fetchInterfaces = async () => {
    setLoading(true);
    try {
      const data = await client.get(`/api/endpoints/project/${id}`);
      setInterfaces(data);
    } catch (error) {
      message.error('获取接口管理失败: ' + getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (record) => {
    setEditingInterface(record);
    form.setFieldsValue({
      name: record.name,
      method: record.method,
      url: record.url,
      base_url: record.base_url,
      path: record.path,
      service: record.service,
      headers: record.headers ? JSON.stringify(record.headers, null, 2) : '',
      params: record.params ? JSON.stringify(record.params, null, 2) : '',
      request_body: record.request_body ? JSON.stringify(record.request_body, null, 2) : '',
      response_body: record.response_body ? JSON.stringify(record.response_body, null, 2) : '',
      response_schema: record.response_schema ? JSON.stringify(record.response_schema, null, 2) : '',
      status_code: record.status_code,
      description: record.description,
      tags: record.tags ? record.tags.join(', ') : '',
      deprecated: record.deprecated,
      version: record.version || ''
    });
    setModalVisible(true);
  };

  const handleView = (record) => {
    setEditingInterface(record);
    setViewModalVisible(true);
  };

  const handleDelete = async (interfaceId) => {
    try {
      await client.delete(`/api/endpoints/${interfaceId}`);
      message.success('接口删除成功');
      fetchInterfaces();
    } catch (error) {
      message.error('删除接口失败: ' + getErrorMessage(error));
    }
  };

  const handleBatchDelete = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请至少选择一个接口进行删除');
      return;
    }
    
    Modal.confirm({
      title: '确认批量删除',
      content: `确定要删除选中的 ${selectedRowKeys.length} 个接口吗？此操作不可恢复。`,
      okText: '确定',
      cancelText: '取消',
      okType: 'danger',
      onOk: async () => {
        setDeleting(true);
        try {
          const response = await client.post('/api/endpoints/batch-delete', {
            interface_ids: selectedRowKeys
          });
          message.success(`成功删除 ${response.deleted_count || selectedRowKeys.length} 个接口`);
          setSelectedRowKeys([]);
          fetchInterfaces();
        } catch (error) {
          message.error('批量删除失败: ' + getErrorMessage(error));
        } finally {
          setDeleting(false);
        }
      }
    });
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      
      // 解析JSON字段
      const updateData = {
        name: values.name,
        method: values.method,
        url: values.url,
        base_url: values.base_url,
        path: values.path,
        service: values.service,
        status_code: values.status_code,
        description: values.description,
        deprecated: values.deprecated,
        version: values.version || ''
      };

      if (values.headers) {
        try {
          updateData.headers = JSON.parse(values.headers);
        } catch {
          message.error('请求头格式不正确（需要JSON格式）');
          return;
        }
      }

      if (values.params) {
        try {
          updateData.params = JSON.parse(values.params);
        } catch {
          message.error('URL参数格式不正确（需要JSON格式）');
          return;
        }
      }

      if (values.request_body) {
        try {
          updateData.request_body = JSON.parse(values.request_body);
        } catch {
          message.error('请求体格式不正确（需要JSON格式）');
          return;
        }
      }

      if (values.response_body) {
        try {
          updateData.response_body = JSON.parse(values.response_body);
        } catch {
          message.error('响应体格式不正确（需要JSON格式）');
          return;
        }
      }

      if (values.response_schema) {
        try {
          updateData.response_schema = JSON.parse(values.response_schema);
        } catch {
          message.error('响应Schema格式不正确（需要JSON格式）');
          return;
        }
      }

      if (values.tags) {
        updateData.tags = values.tags.split(',').map(t => t.trim()).filter(t => t);
      }

      await client.put(`/api/endpoints/${editingInterface.id}`, updateData);
      message.success('接口更新成功');
      setModalVisible(false);
      setEditingInterface(null);
      form.resetFields();
      fetchInterfaces();
    } catch (error) {
      if (error.errorFields) {
        // Form validation errors
        return;
      }
      message.error('更新接口失败: ' + getErrorMessage(error));
    }
  };

  const handleAnalyzeDependencies = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请至少选择一个接口进行依赖分析');
      return;
    }
    
    setAnalyzing(true);
    try {
      const result = await client.post(`/api/relations/analyze-selected/${id}`, {
        interface_ids: selectedRowKeys,
        connection_id: null  // 让后端自动获取
      });
      
      message.success(result.message || `已成功分析 ${selectedRowKeys.length} 个接口的依赖关系`);
      setSelectedRowKeys([]);
    } catch (error) {
      message.error('依赖分析失败: ' + getErrorMessage(error));
    } finally {
      setAnalyzing(false);
    }
  };

  const handleGenerateTestCases = () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请至少选择一个接口生成测试用例');
      return;
    }
    setGenerateModalVisible(true);
  };

  const handleGenerateConfirm = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请至少选择一个接口');
      return;
    }

    setGenerating(true);
    try {
      const response = await client.post(`/api/specs/generate?project_id=${id}`, {
        api_interface_ids: selectedRowKeys,
        case_type: caseType,
        generate_async: true, // 默认异步生成
        module: null
      });

      if (response.async && response.test_case_ids) {
        // 初始化任务状态
        const newTaskStatuses = {};
        response.test_case_ids.forEach(testCaseId => {
          newTaskStatuses[testCaseId] = {
            status: 'generating',
            progress: 0,
            message: '任务已提交，等待执行...'
          };
        });
        setTaskStatuses(prev => ({ ...prev, ...newTaskStatuses }));
        setGenerateModalVisible(false);
        setProgressModalVisible(true);
        
        // 开始轮询任务状态
        response.test_case_ids.forEach(testCaseId => {
          pollTestCaseStatus(testCaseId);
        });

        message.success(`已提交 ${response.test_case_ids.length} 个测试用例生成任务`);
        setSelectedRowKeys([]);
      } else {
        message.success(response.message || '测试用例生成完成');
        setGenerateModalVisible(false);
        setSelectedRowKeys([]);
      }
    } catch (error) {
      console.error('生成测试用例失败', error);
      message.error('生成测试用例失败: ' + getErrorMessage(error));
    } finally {
      setGenerating(false);
    }
  };

  const pollTestCaseStatus = async (testCaseId) => {
    const pollInterval = setInterval(async () => {
      try {
        const testCase = await client.get(`/api/specs/${testCaseId}`);
        
        const status = testCase.status || 'generating';
        const progress = testCase.generation_progress || 0;
        const errorMessage = testCase.error_message;

        setTaskStatuses(prev => ({
          ...prev,
          [testCaseId]: {
            status: (status === 'completed' || status === 'active') ? 'completed' : status === 'failed' ? 'failed' : 'generating',
            progress: progress,
            message: (status === 'completed' || status === 'active') ? '生成完成' :
                     status === 'failed' ? (errorMessage || '生成失败') :
                     `生成中... ${progress}%`,
            errorMessage: errorMessage
          }
        }));

        // 如果任务完成或失败，停止轮询
        if (status === 'completed' || status === 'active' || status === 'failed') {
          clearInterval(pollInterval);
          
          if (status === 'completed' || status === 'active') {
            message.success(`测试用例 ${testCase.name} 生成完成`);
            
            // 通知用例库页面刷新数据
            const refreshKey = `test_cases_refresh_${id}`;
            localStorage.setItem(refreshKey, Date.now().toString());
            // 触发storage事件，让其他页面可以监听到
            window.dispatchEvent(new Event('storage'));
          } else {
            message.error(`测试用例 ${testCase.name} 生成失败: ${errorMessage || '未知错误'}`);
          }

          // 检查是否所有任务都完成了
          setTimeout(() => {
            setTaskStatuses(prev => {
              const allCompleted = Object.values(prev).every(
                status => status.status === 'completed' || status.status === 'failed'
              );
              if (allCompleted) {
                // 所有任务完成，3秒后自动关闭进度Modal
                setTimeout(() => {
                  setProgressModalVisible(false);
                  setTaskStatuses({});
                }, 3000);
              }
              return prev;
            });
          }, 1000);
        }
      } catch (error) {
        console.error('获取测试用例状态失败', error);
        // 继续轮询，不中断
      }
    }, 2000); // 每2秒轮询一次

    // 30分钟后自动停止轮询（防止内存泄漏）
    setTimeout(() => {
      clearInterval(pollInterval);
    }, 30 * 60 * 1000);
  };

  const handleDebug = (record) => {
    setEditingInterface(record);
    debugForm.setFieldsValue({
      url: record.url,
      method: record.method,
      headers: record.headers ? JSON.stringify(record.headers, null, 2) : '',
      body: record.request_body ? JSON.stringify(record.request_body, null, 2) : '',
      timeout: 30
    });
    setDebugModalVisible(true);
    setDebugResponse(null);
  };

  const handleDebugRequest = async () => {
    try {
      const values = await debugForm.validateFields();
      
      const debugRequest = {
        url: values.url,
        method: values.method,
        timeout: values.timeout,
        interface_id: editingInterface?.id || null  // 添加接口ID，用于保存响应体
      };

      if (values.headers) {
        try {
          debugRequest.headers = JSON.parse(values.headers);
        } catch {
          message.error('请求头格式不正确（需要JSON格式）');
          return;
        }
      }

      if (values.body && ['POST', 'PUT', 'PATCH'].includes(values.method)) {
        try {
          debugRequest.body = JSON.parse(values.body);
        } catch {
          message.error('请求体格式不正确（需要JSON格式）');
          return;
        }
      }

      setDebugLoading(true);
      const response = await client.post('/api/endpoints/debug', debugRequest);
      setDebugResponse(response);
      
      if (response.error) {
        message.error('请求失败: ' + response.error);
      } else if (response.status_code >= 200 && response.status_code < 300) {
        message.success('请求成功，响应体已保存到数据库');
        // 刷新接口管理以显示更新的响应体
        fetchInterfaces();
      } else {
        message.warning(`请求返回状态码: ${response.status_code}`);
      }
    } catch (error) {
      message.error('调试请求失败: ' + getErrorMessage(error));
    } finally {
      setDebugLoading(false);
    }
  };

  // 获取方法徽章样式类名
  const getMethodBadgeClass = (method) => {
    const methodUpper = (method || '').toUpperCase();
    if (methodUpper === 'GET') return 'badge-get';
    if (methodUpper === 'POST') return 'badge-post';
    if (methodUpper === 'PUT' || methodUpper === 'PATCH') return 'badge-put';
    if (methodUpper === 'DELETE') return 'badge-delete';
    return 'badge-options';
  };

  // 计算统计信息
  const stats = {
    total: interfaces.length,
    get: interfaces.filter(i => (i.method || '').toUpperCase() === 'GET').length,
    post: interfaces.filter(i => (i.method || '').toUpperCase() === 'POST').length,
    put: interfaces.filter(i => ['PUT', 'PATCH'].includes((i.method || '').toUpperCase())).length,
    delete: interfaces.filter(i => (i.method || '').toUpperCase() === 'DELETE').length,
  };

  const getStatusIcon = (statusCode) => {
    if (!statusCode) return null;
    if (statusCode >= 200 && statusCode < 300) {
      return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    } else if (statusCode >= 400) {
      return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
    }
    return <ClockCircleOutlined style={{ color: '#faad14' }} />;
  };

  return (
    <div style={{ padding: '24px' }}>
      {/* 页面头部 */}
      <div className="page-header">
        <div className="page-title">
          <CodeOutlined />
          <span>接口管理</span>
          </div>
        <div className="page-actions">
          {selectedRowKeys.length > 0 && (
            <>
                <Button
                  type="primary"
                  icon={<FileTextOutlined />}
                  loading={generating}
                  onClick={handleGenerateTestCases}
                  style={{ background: '#52c41a', borderColor: '#52c41a' }}
                >
                  生成测试用例 ({selectedRowKeys.length})
                </Button>
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  loading={deleting}
                  onClick={handleBatchDelete}
                >
                  批量删除 ({selectedRowKeys.length})
                </Button>
                <Button
                  type="primary"
                  icon={<BranchesOutlined />}
                  loading={analyzing}
                  onClick={handleAnalyzeDependencies}
                >
                分析依赖 ({selectedRowKeys.length})
                </Button>
            </>
          )}
        </div>
      </div>

      {/* 统计信息栏 */}
      <div className="stats-bar">
        <div className="stat-item">
          <span className="stat-label">总计:</span>
          <span className="stat-value">{stats.total}</span>
          <span className="stat-label">个接口</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">GET:</span>
          <span className="stat-value">{stats.get}</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">POST:</span>
          <span className="stat-value">{stats.post}</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">PUT/PATCH:</span>
          <span className="stat-value">{stats.put}</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">DELETE:</span>
          <span className="stat-value">{stats.delete}</span>
        </div>
      </div>

      {/* 极简卡片列表 */}
      <Spin spinning={loading}>
        {interfaces.length === 0 && !loading && (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#999', background: '#fff', borderRadius: '6px' }}>
            <p style={{ fontSize: 16, marginBottom: 8 }}>暂无接口数据</p>
            <p style={{ fontSize: 14 }}>请前往"接口文档库"页面上传并解析接口文档</p>
          </div>
        )}
        <div>
          {interfaces.map((record) => {
            const isSelected = selectedRowKeys.includes(record.id);
            const method = (record.method || '').toUpperCase();
            const tags = record.tags || [];
            const serviceTag = record.service ? [record.service] : [];
            const allTags = [...serviceTag, ...tags];
            
            return (
              <div
                key={record.id}
                className="minimal-card"
                onClick={() => handleView(record)}
                style={{
                  borderColor: isSelected ? '#1890ff' : undefined,
                  background: isSelected ? '#f0f7ff' : undefined,
                }}
              >
                <div className="card-row">
                  <Checkbox
                    checked={isSelected}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => {
                      e.stopPropagation();
                      if (e.target.checked) {
                        setSelectedRowKeys([...selectedRowKeys, record.id]);
                      } else {
                        setSelectedRowKeys(selectedRowKeys.filter(id => id !== record.id));
                      }
                    }}
                  />
                  <span className={`method-badge ${getMethodBadgeClass(record.method)}`}>
                    {method || 'N/A'}
                  </span>
                  <div className="card-content">
                    <div className="card-title">
                      {record.name || record.service || '未命名接口'}
                    </div>
                    <div className="card-url">
                      {record.url || record.path || '-'}
                    </div>
                  </div>
                  <div className="card-meta">
                    {record.status_code && (
                      <>
                        <span>{record.status_code}</span>
                        <span>•</span>
                      </>
                    )}
                    {allTags.length > 0 ? (
                      allTags.slice(0, 2).map((tag, idx) => (
                        <Tag key={idx} color="blue" style={{ margin: 0 }}>
                          {tag}
                        </Tag>
                      ))
                    ) : (
                      <span>-</span>
                    )}
                    {record.version && (
                      <>
                        <span>•</span>
                        <Tag color="cyan" style={{ margin: 0 }}>{record.version}</Tag>
                      </>
                    )}
                    {record.deprecated && (
                      <>
                        <span>•</span>
                        <Tag color="red" style={{ margin: 0 }}>已废弃</Tag>
                      </>
                    )}
                  </div>
                  <Space size="small" onClick={(e) => e.stopPropagation()}>
                    <Button
                      type="link"
                      size="small"
                      icon={<EyeOutlined />}
                      onClick={() => handleView(record)}
                      style={{ padding: 0 }}
                    >
                      查看
                    </Button>
                    <Button
                      type="link"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => handleEdit(record)}
                      style={{ padding: 0 }}
                    >
                      编辑
                    </Button>
                    <Button
                      type="link"
                      size="small"
                      icon={<BugOutlined />}
                      onClick={() => handleDebug(record)}
                      style={{ padding: 0 }}
                    >
                      调试
                    </Button>
                    <Popconfirm
                      title="确定要删除这个接口吗？"
                      onConfirm={() => handleDelete(record.id)}
                      okText="确定"
                      cancelText="取消"
                      onCancel={(e) => e?.stopPropagation()}
                    >
                      <Button
                        type="link"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        style={{ padding: 0 }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        删除
                      </Button>
                    </Popconfirm>
                  </Space>
                </div>
              </div>
            );
          })}
        </div>
      </Spin>

      {/* 查看模态框 */}
      <Modal
        title="接口详情"
        open={viewModalVisible}
        onCancel={() => {
          setViewModalVisible(false);
          setEditingInterface(null);
        }}
        footer={[
          <Button key="close" onClick={() => {
            setViewModalVisible(false);
            setEditingInterface(null);
          }}>关闭</Button>,
          <Button key="debug" type="primary" icon={<BugOutlined />} onClick={() => {
            setViewModalVisible(false);
            handleDebug(editingInterface);
          }}>调试</Button>
        ]}
        width={800}
      >
        {editingInterface && (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="接口名称">{editingInterface.name}</Descriptions.Item>
            <Descriptions.Item label="HTTP方法">
              <Tag color="blue">{editingInterface.method}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="完整URL">{editingInterface.url}</Descriptions.Item>
            <Descriptions.Item label="Base URL">{editingInterface.base_url || '-'}</Descriptions.Item>
            <Descriptions.Item label="路径">{editingInterface.path || '-'}</Descriptions.Item>
            <Descriptions.Item label="服务">{editingInterface.service || '-'}</Descriptions.Item>
            <Descriptions.Item label="版本">
              {editingInterface.version ? <Tag color="blue">{editingInterface.version}</Tag> : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="状态码">
              {getStatusIcon(editingInterface.status_code)}
              <span style={{ marginLeft: 8 }}>{editingInterface.status_code}</span>
            </Descriptions.Item>
            <Descriptions.Item label="描述">{editingInterface.description || '-'}</Descriptions.Item>
            <Descriptions.Item label="标签">
              {editingInterface.tags && editingInterface.tags.length > 0 ? (
                editingInterface.tags.map(tag => <Tag key={tag}>{tag}</Tag>)
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="是否废弃">
              <Tag color={editingInterface.deprecated ? 'red' : 'green'}>
                {editingInterface.deprecated ? '是' : '否'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="请求头">
              <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                {editingInterface.headers ? JSON.stringify(editingInterface.headers, null, 2) : '-'}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="URL参数">
              <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                {editingInterface.params ? JSON.stringify(editingInterface.params, null, 2) : '-'}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="请求体">
              <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                {editingInterface.request_body ? JSON.stringify(editingInterface.request_body, null, 2) : '-'}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="响应体">
              <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                {editingInterface.response_body ? JSON.stringify(editingInterface.response_body, null, 2) : '-'}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="响应Schema">
              <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto' }}>
                {editingInterface.response_schema ? JSON.stringify(editingInterface.response_schema, null, 2) : '-'}
              </pre>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>

      {/* 编辑模态框 */}
      <Modal
        title="编辑接口"
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          setEditingInterface(null);
          form.resetFields();
        }}
        onOk={handleSave}
        width={900}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="接口名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Space>
            <Form.Item name="method" label="HTTP方法" rules={[{ required: true }]} style={{ width: 150 }}>
              <Select>
                <Option value="GET">GET</Option>
                <Option value="POST">POST</Option>
                <Option value="PUT">PUT</Option>
                <Option value="DELETE">DELETE</Option>
                <Option value="PATCH">PATCH</Option>
              </Select>
            </Form.Item>
            <Form.Item name="status_code" label="状态码" style={{ width: 150 }}>
              <InputNumber min={100} max={599} />
            </Form.Item>
          </Space>
          <Form.Item name="url" label="完整URL" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Space>
            <Form.Item name="base_url" label="Base URL" style={{ width: '48%' }}>
              <Input />
            </Form.Item>
            <Form.Item name="path" label="路径" style={{ width: '48%' }}>
              <Input />
            </Form.Item>
          </Space>
          <Form.Item name="service" label="服务">
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="version" label="版本">
            <Input placeholder="如: V0.1, V1.0, v2" />
          </Form.Item>
          <Form.Item name="tags" label="标签（逗号分隔）">
            <Input placeholder="tag1, tag2, tag3" />
          </Form.Item>
          <Form.Item name="deprecated" label="是否废弃" valuePropName="checked">
            <Select>
              <Option value={false}>否</Option>
              <Option value={true}>是</Option>
            </Select>
          </Form.Item>
          <Divider>请求信息</Divider>
          <Form.Item name="headers" label="请求头（JSON格式）">
            <TextArea rows={4} placeholder='{"Content-Type": "application/json"}' />
          </Form.Item>
          <Form.Item name="params" label="URL参数（JSON格式）">
            <TextArea rows={4} placeholder='{"key": "value"}' />
          </Form.Item>
          <Form.Item name="request_body" label="请求体（JSON格式）">
            <TextArea rows={6} placeholder='{"key": "value"}' />
          </Form.Item>
          <Divider>响应信息</Divider>
          <Form.Item name="response_body" label="响应体（JSON格式）">
            <TextArea rows={6} placeholder='{"code": 200, "data": {}}' />
          </Form.Item>
          <Form.Item name="response_schema" label="响应Schema（JSON格式）">
            <TextArea rows={6} placeholder='{"type": "object", "properties": {}}' />
          </Form.Item>
        </Form>
      </Modal>

      {/* 调试模态框 */}
      <Modal
        title="调试接口"
        open={debugModalVisible}
        onCancel={() => {
          setDebugModalVisible(false);
          setEditingInterface(null);
          debugForm.resetFields();
          setDebugResponse(null);
        }}
        width={900}
        footer={[
          <Button key="cancel" onClick={() => {
            setDebugModalVisible(false);
            setEditingInterface(null);
            debugForm.resetFields();
            setDebugResponse(null);
          }}>取消</Button>,
          <Button key="debug" type="primary" loading={debugLoading} onClick={handleDebugRequest}>
            发送请求
          </Button>
        ]}
      >
        <Form form={debugForm} layout="vertical">
          <Space>
            <Form.Item name="method" label="HTTP方法" rules={[{ required: true }]} style={{ width: 150 }}>
              <Select>
                <Option value="GET">GET</Option>
                <Option value="POST">POST</Option>
                <Option value="PUT">PUT</Option>
                <Option value="DELETE">DELETE</Option>
                <Option value="PATCH">PATCH</Option>
              </Select>
            </Form.Item>
            <Form.Item name="timeout" label="超时时间（秒）" style={{ width: 150 }}>
              <InputNumber min={1} max={300} />
            </Form.Item>
          </Space>
          <Form.Item name="url" label="请求URL" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="headers" label="请求头（JSON格式）">
            <TextArea rows={4} placeholder='{"Content-Type": "application/json", "Authorization": "Bearer token"}' />
          </Form.Item>
          <Form.Item name="body" label="请求体（JSON格式，仅POST/PUT/PATCH）">
            <TextArea rows={6} placeholder='{"key": "value"}' />
          </Form.Item>
        </Form>

        {debugResponse && (
          <div style={{ marginTop: 24 }}>
            <Divider>响应结果</Divider>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="状态码">
                {getStatusIcon(debugResponse.status_code)}
                <span style={{ marginLeft: 8 }}>{debugResponse.status_code}</span>
              </Descriptions.Item>
              <Descriptions.Item label="响应时间">
                {debugResponse.elapsed_time.toFixed(3)} 秒
              </Descriptions.Item>
              {debugResponse.error && (
                <Descriptions.Item label="错误信息">
                  <span style={{ color: 'red' }}>{debugResponse.error}</span>
                </Descriptions.Item>
              )}
              <Descriptions.Item label="响应头">
                <pre style={{ margin: 0, maxHeight: 150, overflow: 'auto', fontSize: 12 }}>
                  {JSON.stringify(debugResponse.headers, null, 2)}
                </pre>
              </Descriptions.Item>
              <Descriptions.Item label="响应体">
                <pre style={{ margin: 0, maxHeight: 300, overflow: 'auto', fontSize: 12 }}>
                  {debugResponse.body ? JSON.stringify(debugResponse.body, null, 2) : debugResponse.text}
                </pre>
              </Descriptions.Item>
            </Descriptions>
          </div>
        )}
      </Modal>

      {/* 生成测试用例模态框 */}
      <Modal
        title={
          <Space>
            <FileTextOutlined style={{ color: '#52c41a' }} />
            <span>生成测试用例</span>
          </Space>
        }
        open={generateModalVisible}
        onCancel={() => {
          setGenerateModalVisible(false);
        }}
        onOk={handleGenerateConfirm}
        confirmLoading={generating}
        width={600}
        okText="开始生成"
        cancelText="取消"
      >
        <div style={{ padding: '16px 0' }}>
          <div style={{ marginBottom: 24 }}>
            <div style={{ marginBottom: 8, fontSize: 14, color: '#666' }}>
              已选择 <strong>{selectedRowKeys.length}</strong> 个接口
            </div>
            <div style={{ fontSize: 12, color: '#999' }}>
              测试用例将通过异步任务生成，生成完成后可在"用例库"页面查看
            </div>
          </div>

          <Divider />

          <div style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 12, fontSize: 14, fontWeight: 500 }}>
              用例类型 <span style={{ color: '#ff4d4f' }}>*</span>
            </div>
            <Radio.Group
              value={caseType}
              onChange={(e) => setCaseType(e.target.value)}
              style={{ width: '100%', display: 'flex', gap: '12px' }}
            >
              <Radio.Button 
                value="pytest" 
                style={{ 
                  flex: 1, 
                  height: 'auto', 
                  padding: '16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: '4px'
                }}
              >
                <div style={{ textAlign: 'center', width: '100%' }}>
                  <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <FileTextOutlined style={{ marginRight: 8, color: '#1890ff', fontSize: 18 }} />
                    接口测试用例 (pytest)
                  </div>
                  <div style={{ fontSize: 12, color: '#999', lineHeight: '1.5' }}>
                    生成功能测试用例，使用HttpRunner框架
                  </div>
                </div>
              </Radio.Button>
              <Radio.Button 
                value="jmeter" 
                style={{ 
                  flex: 1, 
                  height: 'auto', 
                  padding: '16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: '4px'
                }}
              >
                <div style={{ textAlign: 'center', width: '100%' }}>
                  <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <ThunderboltOutlined style={{ marginRight: 8, color: '#fa8c16', fontSize: 18 }} />
                    性能测试用例 (JMeter)
                  </div>
                  <div style={{ fontSize: 12, color: '#999', lineHeight: '1.5' }}>
                    生成性能测试脚本，使用JMeter
                  </div>
                </div>
              </Radio.Button>
            </Radio.Group>
          </div>

          <Divider />

          <div style={{ 
            background: '#f0f2f5', 
            padding: '12px', 
            borderRadius: '4px',
            fontSize: 13,
            color: '#666'
          }}>
            <div style={{ marginBottom: 4 }}>
              <strong>提示：</strong>
            </div>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              <li>测试用例将通过异步任务生成，不影响当前操作</li>
              <li>生成完成后可在"测试用例"页面查看和管理</li>
              <li>生成过程中可以在进度窗口中查看实时状态</li>
            </ul>
          </div>
        </div>
      </Modal>

      {/* 生成进度模态框 */}
      <Modal
        title={
          <Space>
            <FileTextOutlined style={{ color: '#52c41a' }} />
            <span>测试用例生成进度</span>
          </Space>
        }
        open={progressModalVisible}
        onCancel={() => {
          const hasRunning = Object.values(taskStatuses).some(
            status => status.status === 'generating'
          );
          if (hasRunning) {
            Modal.confirm({
              title: '确认关闭',
              content: '仍有任务正在生成中，关闭后仍可在"测试用例"页面查看生成状态。是否确认关闭？',
              onOk: () => {
                setProgressModalVisible(false);
                setTaskStatuses({});
              }
            });
          } else {
            setProgressModalVisible(false);
            setTaskStatuses({});
          }
        }}
        footer={[
          <Button key="close" onClick={() => {
            const hasRunning = Object.values(taskStatuses).some(
              status => status.status === 'generating'
            );
            if (hasRunning) {
              Modal.confirm({
                title: '确认关闭',
                content: '仍有任务正在生成中，关闭后仍可在"测试用例"页面查看生成状态。是否确认关闭？',
                onOk: () => {
                  setProgressModalVisible(false);
                  setTaskStatuses({});
                }
              });
            } else {
              setProgressModalVisible(false);
              setTaskStatuses({});
            }
          }}>
            关闭
          </Button>
        ]}
        width={700}
        closable={true}
      >
        <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
          {Object.keys(taskStatuses).length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: '#999' }}>
              暂无生成任务
            </div>
          ) : (
            Object.entries(taskStatuses).map(([testCaseId, status]) => (
              <div key={testCaseId} style={{ marginBottom: 24, padding: '16px', background: '#fafafa', borderRadius: '4px' }}>
                <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 14, fontWeight: 500 }}>
                    测试用例 ID: {testCaseId}
                  </span>
                  <Tag color={
                    status.status === 'completed' ? 'success' :
                    status.status === 'failed' ? 'error' :
                    'processing'
                  }>
                    {status.status === 'completed' ? '完成' :
                     status.status === 'failed' ? '失败' :
                     '生成中'}
                  </Tag>
                </div>
                <Progress
                  percent={status.progress}
                  status={
                    status.status === 'completed' ? 'success' :
                    status.status === 'failed' ? 'exception' :
                    'active'
                  }
                  strokeColor={
                    status.status === 'completed' ? '#52c41a' :
                    status.status === 'failed' ? '#ff4d4f' :
                    '#1890ff'
                  }
                />
                <div style={{ marginTop: 8, fontSize: 13, color: '#666' }}>
                  {status.message}
                </div>
                {status.errorMessage && (
                  <div style={{ marginTop: 8, padding: '8px', background: '#fff2f0', borderRadius: '4px', fontSize: 12, color: '#ff4d4f' }}>
                    {status.errorMessage}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </Modal>
    </div>
  );
};

export default Interfaces;

