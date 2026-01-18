import React, { useState, useEffect, useRef } from 'react';
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  message,
  Progress,
  Drawer,
  Descriptions,
  Tabs,
  Badge,
  Tooltip,
  Popconfirm,
  InputNumber,
  Empty
} from 'antd';
import {
  PlayCircleOutlined,
  PauseOutlined,
  StopOutlined,
  ReloadOutlined,
  EyeOutlined,
  PlusOutlined,
  RedoOutlined,
  RocketOutlined,
  FileTextOutlined,
  BarChartOutlined
} from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import client from '../api/client';
import ReactECharts from 'echarts-for-react';
import { getErrorMessage } from '../utils/errorHandler';

const { TextArea } = Input;
const { TabPane } = Tabs;

const TestTasks = () => {
  const { id } = useParams();
  const [tasks, setTasks] = useState([]);
  const [groupedTasks, setGroupedTasks] = useState({
    scenario: [],
    interface: [],
    performance: [],
    other: []
  });
  const [activeTab, setActiveTab] = useState('scenario');
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedTask, setSelectedTask] = useState(null);
  const [form] = Form.useForm();
  const [environments, setEnvironments] = useState([]);
  const [testCases, setTestCases] = useState([]);
  const [defaultEnvironmentId, setDefaultEnvironmentId] = useState(null);
  const intervalRef = useRef(null);

  useEffect(() => {
    fetchTasks();
    fetchEnvironments();
    fetchTestCases();

    // 设置定时刷新，每3秒更新一次运行中的任务
    intervalRef.current = setInterval(() => {
      refreshRunningTasks();
    }, 3000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [id]);

  useEffect(() => {
    if (modalVisible && defaultEnvironmentId) {
      const currentEnv = form.getFieldValue('environment_id');
      if (!currentEnv) {
        form.setFieldsValue({ environment_id: defaultEnvironmentId });
      }
    }
  }, [modalVisible, defaultEnvironmentId, form]);

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const data = await client.get(`/api/jobs/?project_id=${id}&grouped=true`);
      setGroupedTasks(data || {
        scenario: [],
        interface: [],
        performance: [],
        other: []
      });
      // 合并所有任务用于刷新
      const allTasks = [
        ...(data?.scenario || []),
        ...(data?.interface || []),
        ...(data?.performance || []),
        ...(data?.other || [])
      ];
      setTasks(allTasks);
    } catch (error) {
      console.error('获取任务列表失败', error);
      message.error('获取任务列表失败');
    } finally {
      setLoading(false);
    }
  };

  const refreshRunningTasks = async () => {
    try {
      const runningTasks = tasks.filter(t => t.status === 'running' || t.status === 'paused');
      if (runningTasks.length > 0) {
        const data = await client.get(`/api/jobs/?project_id=${id}&grouped=true`);
        setGroupedTasks(data || {
          scenario: [],
          interface: [],
          performance: [],
          other: []
        });
        const allTasks = [
          ...(data?.scenario || []),
          ...(data?.interface || []),
          ...(data?.performance || []),
          ...(data?.other || [])
        ];
        setTasks(allTasks);
      }
    } catch (error) {
      // 静默失败
    }
  };

  const fetchEnvironments = async () => {
    try {
      const data = await client.get(`/api/configs/?project_id=${id}`);
      setEnvironments(data || []);
      if (data && data.length > 0) {
        const defaultEnv = data.find(env => env.is_default) || data[0];
        setDefaultEnvironmentId(defaultEnv?.id || null);
      } else {
        setDefaultEnvironmentId(null);
      }
    } catch (error) {
      console.error('获取环境列表失败', error);
    }
  };

  const fetchTestCases = async () => {
    try {
      // 使用最大允许的 page_size 获取测试用例（后端限制最大100）
      const response = await client.get(`/api/specs/?project_id=${id}&page_size=100`);
      // 后端返回的是分页对象 {data: [...], pagination: {...}}
      const cases = Array.isArray(response) ? response : (response?.data || []);
      console.log('获取到的测试用例数量:', cases.length);
      console.log('测试用例数据示例:', cases.slice(0, 3));
      setTestCases(cases);
    } catch (error) {
      console.error('获取用例列表失败', error);
      setTestCases([]); // 出错时设置为空数组
    }
  };

  const handleExecute = async (taskId) => {
    try {
      await client.post(`/api/jobs/${taskId}/execute`);
      message.success('任务已启动');
      fetchTasks();
    } catch (error) {
      message.error('任务启动失败');
    }
  };

  const handlePause = async (taskId) => {
    try {
      await client.post(`/api/jobs/${taskId}/pause`);
      message.success('任务已暂停');
      fetchTasks();
    } catch (error) {
      message.error('暂停失败: ' + getErrorMessage(error));
    }
  };

  const handleResume = async (taskId) => {
    try {
      await client.post(`/api/jobs/${taskId}/resume`);
      message.success('任务已继续');
      fetchTasks();
    } catch (error) {
      message.error('继续失败: ' + getErrorMessage(error));
    }
  };

  const handleStop = async (taskId) => {
    try {
      await client.post(`/api/jobs/${taskId}/stop`);
      message.success('任务已停止');
      fetchTasks();
    } catch (error) {
      message.error('停止失败');
    }
  };

  const handleRetry = async (taskId) => {
    try {
      await client.post(`/api/jobs/${taskId}/retry`);
      message.success('任务已重新提交执行');
      fetchTasks();
    } catch (error) {
      message.error('重试失败: ' + getErrorMessage(error));
    }
  };

  const handleRestart = async (taskId) => {
    try {
      await client.post(`/api/jobs/${taskId}/restart`);
      message.success('任务已重新启动');
      fetchTasks();
    } catch (error) {
      message.error('重新启动失败');
    }
  };

  const handleDelete = async (taskId) => {
    try {
      await client.delete(`/api/jobs/${taskId}`);
      message.success('删除成功');
      fetchTasks();
    } catch (error) {
      if (error.response?.status === 400) {
        Modal.confirm({
          title: '强制删除',
          content: getErrorMessage(error),
          onOk: async () => {
            try {
              await client.delete(`/api/jobs/${taskId}?force=true`);
              message.success('删除成功');
              fetchTasks();
            } catch (err) {
              message.error('删除失败');
            }
          }
        });
      } else {
        message.error('删除失败');
      }
    }
  };

  const handleAdd = () => {
    setSelectedTask(null);
    form.resetFields();
    form.setFieldsValue({
      task_type: 'immediate',
      auto_prepare: true,
      max_retries: 3,
      execution_task_type: 'interface',
      environment_id: defaultEnvironmentId || undefined
    });
    setModalVisible(true);
  };

  const handleView = async (task) => {
    try {
      const data = await client.get(`/api/jobs/${task.id}`);
      setSelectedTask(data);
      setDrawerVisible(true);
    } catch (error) {
      message.error('获取任务详情失败');
    }
  };

  const handleViewReport = (task) => {
    console.log('[handleViewReport] 查看报告按钮被点击，任务类型:', task.execution_task_type);
    if (task.execution_task_type === 'performance') {
      // 性能测试报告 - "查看JTL报告"按钮始终打开JTL报告（JMeter原始报告）
      if (task.jtl_report_path) {
        const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8004';
        const url = `${apiUrl}/api/jobs/${task.id}/jtl-report`;
        console.log('[handleViewReport] 打开JTL报告URL:', url);
        window.open(url, '_blank');
      } else {
        message.warning('该任务尚未生成JTL测试报告');
      }
    } else if (task.execution_task_type === 'scenario' || task.execution_task_type === 'interface') {
      // HTML测试报告
      if (task.allure_report_path) {
        const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8004';
        window.open(`${apiUrl}/api/jobs/${task.id}/allure-report`, '_blank');
      } else {
        message.warning('该任务尚未生成测试报告');
      }
    } else {
      message.warning('该任务类型不支持报告');
    }
  };

  const handleGeneratePerformanceAnalysis = async (task) => {
    console.log('[handleGeneratePerformanceAnalysis] 性能分析按钮被点击');
    if (task.execution_task_type !== 'performance') {
      message.warning('只有性能测试任务才能生成性能瓶颈分析报告');
      return;
    }

    if (!task.jtl_report_path) {
      message.warning('该任务尚未生成JTL报告，无法进行分析');
      return;
    }
    
    // 如果已经有性能分析报告，直接打开
    if (task.performance_report_html) {
      const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8004';
      const url = `${apiUrl}/api/jobs/${task.id}/performance-report`;
      console.log('[handleGeneratePerformanceAnalysis] 打开性能瓶颈分析报告URL:', url);
      window.open(url, '_blank');
      return;
    }
    
    // 如果没有，则生成新的分析报告
    try {
      message.loading('正在生成性能瓶颈分析报告，请稍候...', 0);
      const response = await client.post(`/api/jobs/${task.id}/generate-performance-analysis`);
      message.destroy();
      message.success('性能瓶颈分析报告生成成功');
      
      // 打开报告
      const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8004';
      const url = `${apiUrl}${response.report_url}`;
      console.log('[handleGeneratePerformanceAnalysis] 生成后打开性能瓶颈分析报告URL:', url);
      window.open(url, '_blank');
      
      // 刷新任务列表
      fetchTasks();
    } catch (error) {
      message.destroy();
      message.error(getErrorMessage(error) || '生成性能瓶颈分析报告失败');
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        ...values,
      };

      if (!payload.environment_id) {
        if (!defaultEnvironmentId) {
          message.error('请先为项目配置测试环境');
          return;
        }
        payload.environment_id = defaultEnvironmentId;
      }

      await client.post(`/api/jobs/?project_id=${id}`, payload);
      message.success('创建成功');
      setModalVisible(false);
      fetchTasks();
    } catch (error) {
      message.error('创建失败: ' + getErrorMessage(error));
    }
  };

  const getStatusColor = (status) => {
    const colorMap = {
      'pending': 'default',
      'running': 'processing',
      'paused': 'warning',
      'completed': 'success',
      'failed': 'error',
      'stopped': 'default'
    };
    return colorMap[status] || 'default';
  };

  const getStatusText = (status) => {
    const textMap = {
      'pending': '待执行',
      'running': '执行中',
      'paused': '已暂停',
      'completed': '已完成',
      'failed': '失败',
      'stopped': '已停止'
    };
    return textMap[status] || status;
  };

  const columns = [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      render: (text, record) => (
        <Space>
          <a onClick={() => handleView(record)}>{text}</a>
          {record.scenario && (
            <Tag color="cyan">{record.scenario}</Tag>
          )}
        </Space>
      )
    },
    {
      title: '类型',
      dataIndex: 'task_type',
      key: 'task_type',
      render: (type) => (
        <Tag>{type === 'immediate' ? '立即执行' : '定时任务'}</Tag>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status, record) => (
        <Space>
          <Badge status={getStatusColor(status)} text={getStatusText(status)} />
          {status === 'running' && record.progress !== undefined && (
            <Progress
              percent={record.progress}
              size="small"
              style={{ width: 100 }}
              format={(percent) => `${percent}%`}
            />
          )}
        </Space>
      )
    },
    {
      title: '进度',
      key: 'progress_info',
      render: (_, record) => {
        if (record.total_cases) {
          return (
            <Space>
              <span>总计: {record.total_cases}</span>
              <Tag color="green">通过: {record.passed_cases || 0}</Tag>
              <Tag color="red">失败: {record.failed_cases || 0}</Tag>
              <Tag color="orange">跳过: {record.skipped_cases || 0}</Tag>
            </Space>
          );
        }
        return '-';
      }
    },
    {
      title: '执行时间',
      dataIndex: 'executed_at',
      key: 'executed_at',
      render: (time) => time ? new Date(time).toLocaleString() : '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 300,
      render: (_, record) => {
        const isRunning = record.status === 'running';
        const isPaused = record.status === 'paused';
        const isFailed = record.status === 'failed';
        const isStopped = record.status === 'stopped';
        const isCompleted = record.status === 'completed';

        return (
          <Space>
            {!isRunning && !isPaused && record.status !== 'completed' && (
              <Tooltip title="执行">
                <Button
                  type="link"
                  size="small"
                  icon={<PlayCircleOutlined />}
                  onClick={() => handleExecute(record.id)}
                />
              </Tooltip>
            )}
            {isRunning && (
              <Tooltip title="暂停">
                <Button
                  type="link"
                  size="small"
                  icon={<PauseOutlined />}
                  onClick={() => handlePause(record.id)}
                />
              </Tooltip>
            )}
            {isPaused && (
              <Tooltip title="继续">
                <Button
                  type="link"
                  size="small"
                  icon={<PlayCircleOutlined />}
                  onClick={() => handleResume(record.id)}
                />
              </Tooltip>
            )}
            {(isRunning || isPaused) && (
              <Tooltip title="停止">
                <Popconfirm
                  title="确定要停止任务吗？"
                  onConfirm={() => handleStop(record.id)}
                >
                  <Button
                    type="link"
                    size="small"
                    danger
                    icon={<StopOutlined />}
                  />
                </Popconfirm>
              </Tooltip>
            )}
            {(isFailed || isStopped || isCompleted) && (
              <Tooltip title="重试">
                <Button
                  type="link"
                  size="small"
                  icon={<RedoOutlined />}
                  onClick={() => handleRetry(record.id)}
                />
              </Tooltip>
            )}
            {(isFailed || isStopped || isCompleted) && (
              <Tooltip title="重新执行">
                <Popconfirm
                  title="确定要重新执行任务吗？"
                  onConfirm={() => handleRestart(record.id)}
                >
                  <Button
                    type="link"
                    size="small"
                    icon={<RocketOutlined />}
                  />
                </Popconfirm>
              </Tooltip>
            )}
            <Tooltip title="查看详情">
              <Button
                type="link"
                size="small"
                icon={<EyeOutlined />}
                onClick={() => handleView(record)}
              />
            </Tooltip>
            {(record.status === 'completed' || record.status === 'failed') && record.execution_task_type !== 'performance' && (
              <Tooltip title="查看测试报告">
                <Button
                  type="link"
                  size="small"
                  icon={<FileTextOutlined />}
                  onClick={() => handleViewReport(record)}
                >
                  查看报告
                </Button>
              </Tooltip>
            )}
            {record.execution_task_type === 'performance' && (
              <Tooltip title={record.jtl_report_path ? (record.performance_report_html ? "查看性能瓶颈分析报告（DeepSeek分析）" : "生成性能瓶颈分析报告（DeepSeek分析）") : "需要先完成性能测试才能生成分析报告"}>
                <Button
                  type="link"
                  size="small"
                  icon={<BarChartOutlined />}
                  onClick={() => handleGeneratePerformanceAnalysis(record)}
                  disabled={!record.jtl_report_path}
                >
                  {record.performance_report_html ? '查看分析' : '性能分析'}
                </Button>
              </Tooltip>
            )}
            <Popconfirm
              title="确定要删除任务吗？"
              onConfirm={() => handleDelete(record.id)}
            >
              <Button
                type="link"
                size="small"
                danger
              >
                删除
              </Button>
            </Popconfirm>
          </Space>
        );
      }
    }
  ];

  const getProgressChart = () => {
    if (!selectedTask) return null;

    return {
      title: {
        text: '执行进度'
      },
      tooltip: {
        trigger: 'axis'
      },
      legend: {
        data: ['通过', '失败', '跳过']
      },
      xAxis: {
        type: 'category',
        data: ['用例统计']
      },
      yAxis: {
        type: 'value'
      },
      series: [
        {
          name: '通过',
          type: 'bar',
          data: [selectedTask.passed_cases || 0],
          itemStyle: { color: '#52c41a' }
        },
        {
          name: '失败',
          type: 'bar',
          data: [selectedTask.failed_cases || 0],
          itemStyle: { color: '#ff4d4f' }
        },
        {
          name: '跳过',
          type: 'bar',
          data: [selectedTask.skipped_cases || 0],
          itemStyle: { color: '#faad14' }
        }
      ]
    };
  };

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>测试任务管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          新建任务
        </Button>
      </div>

      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'scenario',
              label: `场景接口测试任务 (${groupedTasks.scenario?.length || 0})`,
            },
            {
              key: 'interface',
              label: `接口测试任务 (${groupedTasks.interface?.length || 0})`,
            },
            {
              key: 'performance',
              label: `性能测试任务 (${groupedTasks.performance?.length || 0})`,
            },
          ]}
        >
        </Tabs>
        <Table
          columns={columns}
          dataSource={groupedTasks[activeTab] || []}
          loading={loading}
          rowKey="id"
          pagination={{
            pageSize: 20,
            showTotal: (total) => `共 ${total} 条记录`
          }}
        />
      </Card>

      <Modal
        title="新建测试任务"
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={800}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="任务名称"
            rules={[{ required: true, message: '请输入任务名称' }]}
          >
            <Input placeholder="请输入任务名称" />
          </Form.Item>

          <Form.Item
            name="scenario"
            label="执行场景"
          >
            <TextArea rows={2} placeholder="描述测试场景" />
          </Form.Item>

          <Form.Item
            name="task_type"
            label="任务类型"
            rules={[{ required: true }]}
          >
            <Select>
              <Select.Option value="immediate">立即执行</Select.Option>
              <Select.Option value="scheduled">定时任务</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) =>
              prevValues.task_type !== currentValues.task_type
            }
          >
            {({ getFieldValue }) =>
              getFieldValue('task_type') === 'scheduled' ? (
                <Form.Item
                  name="cron_expression"
                  label="Cron表达式"
                  rules={[{ required: true, message: '请输入Cron表达式' }]}
                >
                  <Input placeholder="例: 0 2 * * * (每天凌晨2点)" />
                </Form.Item>
              ) : null
            }
          </Form.Item>

          <Form.Item
            name="execution_task_type"
            label="测试任务类型"
            rules={[{ required: true, message: '请选择测试任务类型' }]}
          >
            <Select
              placeholder="选择测试任务类型"
              onChange={() => {
                form.setFieldsValue({ test_case_ids: [] });
              }}
            >
              <Select.Option value="scenario">场景测试任务执行</Select.Option>
              <Select.Option value="interface">接口测试任务执行</Select.Option>
              <Select.Option value="performance">性能测试任务执行</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item name="environment_id" hidden>
            <Input type="hidden" />
          </Form.Item>

          <Form.Item
            shouldUpdate={(prevValues, currentValues) =>
              prevValues.execution_task_type !== currentValues.execution_task_type
            }
            noStyle
          >
            {({ getFieldValue }) => {
              const execType = getFieldValue('execution_task_type') || 'interface';
              // 确保 testCases 是数组
              const safeTestCases = Array.isArray(testCases) ? testCases : [];
              const filteredCases = safeTestCases.filter(testCase => {
                if (execType === 'performance') {
                  // 性能测试任务：只显示 jmeter 类型的用例
                  return testCase.case_type === 'jmeter';
                } else if (execType === 'scenario') {
                  // 场景测试任务：只显示场景用例（pytest类型，且名称包含"场景"）
                  return testCase.case_type === 'pytest' && testCase.name && testCase.name.includes('场景');
                } else if (execType === 'interface') {
                  // 接口测试任务：只显示接口测试用例（pytest类型，且名称不包含"场景"）
                  return testCase.case_type === 'pytest' && (!testCase.name || !testCase.name.includes('场景'));
                }
                // 其他类型：显示所有非 jmeter 类型的用例
                return testCase.case_type !== 'jmeter';
              });
              return (
                <Form.Item
                  name="test_case_ids"
                  label="测试用例"
                  rules={[{ required: true, message: '请选择测试用例' }]}
                >
                  <Select
                    mode="multiple"
                    placeholder="选择测试用例"
                    showSearch
                    filterOption={(input, option) => {
                      const label = typeof option?.children === 'string'
                        ? option.children
                        : String(option?.children || '');
                      return label.toLowerCase().indexOf(input.toLowerCase()) >= 0;
                    }}
                  >
                    {filteredCases.map(testCase => (
                      <Select.Option key={testCase.id} value={testCase.id}>
                        {testCase.name} ({testCase.module || '未分类'})
                      </Select.Option>
                    ))}
                    {filteredCases.length === 0 && (
                      <Select.Option disabled key="empty" value="">
                        暂无符合条件的测试用例
                      </Select.Option>
                    )}
                  </Select>
                </Form.Item>
              );
            }}
          </Form.Item>

          <Form.Item
            name="max_retries"
            label="最大重试次数"
          >
            <InputNumber min={0} max={10} defaultValue={3} />
          </Form.Item>

          <Form.Item
            name="auto_prepare"
            label="自动准备"
            valuePropName="checked"
          >
            <Select defaultValue={true}>
              <Select.Option value={true}>是（自动分析依赖、构造数据）</Select.Option>
              <Select.Option value={false}>否</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title="任务详情"
        placement="right"
        width={1000}
        open={drawerVisible}
        onClose={() => setDrawerVisible(false)}
      >
        {selectedTask && (
          <Tabs defaultActiveKey="basic">
            <TabPane tab="基本信息" key="basic">
              <Descriptions column={1} bordered>
                <Descriptions.Item label="任务名称">{selectedTask.name}</Descriptions.Item>
                <Descriptions.Item label="场景">{selectedTask.scenario || '-'}</Descriptions.Item>
                <Descriptions.Item label="任务类型">
                  <Tag>{selectedTask.task_type === 'immediate' ? '立即执行' : '定时任务'}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="状态">
                  <Badge status={getStatusColor(selectedTask.status)} text={getStatusText(selectedTask.status)} />
                </Descriptions.Item>
                <Descriptions.Item label="进度">
                  {selectedTask.progress !== undefined ? (
                    <Progress percent={selectedTask.progress} />
                  ) : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="用例统计">
                  {selectedTask.total_cases ? (
                    <Space>
                      <span>总计: {selectedTask.total_cases}</span>
                      <Tag color="green">通过: {selectedTask.passed_cases || 0}</Tag>
                      <Tag color="red">失败: {selectedTask.failed_cases || 0}</Tag>
                      <Tag color="orange">跳过: {selectedTask.skipped_cases || 0}</Tag>
                    </Space>
                  ) : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="重试次数">
                  {selectedTask.retry_count || 0} / {selectedTask.max_retries || 3}
                </Descriptions.Item>
                <Descriptions.Item label="执行时间">
                  {selectedTask.executed_at ? new Date(selectedTask.executed_at).toLocaleString() : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="完成时间">
                  {selectedTask.completed_at ? new Date(selectedTask.completed_at).toLocaleString() : '-'}
                </Descriptions.Item>
                {selectedTask.error_message && (
                  <Descriptions.Item label="错误信息">
                    <Tag color="red">{selectedTask.error_message}</Tag>
                  </Descriptions.Item>
                )}
              </Descriptions>
            </TabPane>

            <TabPane tab="进度统计" key="progress">
              {selectedTask.total_cases ? (
                <ReactECharts
                  option={getProgressChart()}
                  style={{ height: '400px', width: '100%' }}
                />
              ) : (
                <Empty description="暂无进度数据" />
              )}
            </TabPane>
          </Tabs>
        )}
      </Drawer>
    </div>
  );
};

export default TestTasks;
