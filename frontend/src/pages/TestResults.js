import React, { useState, useEffect } from 'react';
import {
  Card,
  Table,
  Tag,
  Space,
  Button,
  Select,
  message,
  Drawer,
  Descriptions,
  Tabs,
  Spin,
  Empty,
  Alert,
  Collapse,
  Timeline,
  Progress,
  Input,
  Form,
  Modal,
  InputNumber,
  Checkbox,
  Row,
  Col
} from 'antd';
import {
  EyeOutlined,
  DownloadOutlined,
  ReloadOutlined,
  BarChartOutlined,
  BugOutlined,
  BulbOutlined,
  RiseOutlined,
  FileTextOutlined,
  FilterOutlined,
  SearchOutlined
} from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import client from '../api/client';
import ReactECharts from 'echarts-for-react';
import MonacoEditor from '@monaco-editor/react';

const { TabPane } = Tabs;
const { Panel } = Collapse;

const TestResults = () => {
  const { id } = useParams();
  const [tasks, setTasks] = useState([]);
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedResult, setSelectedResult] = useState(null);
  const [htmlReportUrl, setHtmlReportUrl] = useState(null);
  const [failureAnalysis, setFailureAnalysis] = useState(null);
  const [aiSuggestions, setAiSuggestions] = useState(null);
  const [trendData, setTrendData] = useState(null);
  const [filters, setFilters] = useState({
    status: null,
    statusCode: null,
    minExecutionTime: null,
    maxExecutionTime: null,
    keyword: ''
  });
  const [reportModalVisible, setReportModalVisible] = useState(false);
  const [reportForm] = Form.useForm();
  const [generatingReport, setGeneratingReport] = useState(false);

  useEffect(() => {
    fetchTasks();
    fetchTrendData();
  }, [id]);

  useEffect(() => {
    if (selectedTaskId) {
      fetchResults();
    }
  }, [selectedTaskId]);

  const fetchTasks = async () => {
    try {
      const data = await client.get(`/api/jobs/?project_id=${id}&status=completed`);
      setTasks(data || []);
      if (data && data.length > 0 && !selectedTaskId) {
        setSelectedTaskId(data[0].id);
      }
    } catch (error) {
      console.error('获取任务列表失败', error);
    }
  };

  const fetchResults = async () => {
    if (!selectedTaskId) return;
    
    setLoading(true);
    try {
      let url = `/api/results/?task_id=${selectedTaskId}`;
      if (filters.status) {
        url += `&status=${filters.status}`;
      }
      const data = await client.get(url);
      
      // 前端筛选
      let filteredData = data || [];
      
      if (filters.statusCode) {
        filteredData = filteredData.filter(r => r.status_code === filters.statusCode);
      }
      
      if (filters.minExecutionTime !== null) {
        filteredData = filteredData.filter(r => 
          r.execution_time && r.execution_time * 1000 >= filters.minExecutionTime
        );
      }
      
      if (filters.maxExecutionTime !== null) {
        filteredData = filteredData.filter(r => 
          r.execution_time && r.execution_time * 1000 <= filters.maxExecutionTime
        );
      }
      
      if (filters.keyword) {
        const keyword = filters.keyword.toLowerCase();
        filteredData = filteredData.filter(r => 
          JSON.stringify(r).toLowerCase().includes(keyword)
        );
      }
      
      setResults(filteredData);
    } catch (error) {
      console.error('获取测试结果失败', error);
      message.error('获取测试结果失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchResults();
  }, [selectedTaskId, filters]);

  const fetchTrendData = async () => {
    try {
      const data = await client.get(`/api/reports/trend-analysis/${id}?days=30&group_by=day`);
      setTrendData(data);
    } catch (error) {
      console.error('获取趋势数据失败', error);
    }
  };

  const handleView = async (result) => {
    try {
      const data = await client.get(`/api/results/${result.id}`);
      setSelectedResult(data);
      setDrawerVisible(true);
    } catch (error) {
      message.error('获取结果详情失败');
    }
  };

  const handleViewHtmlReport = async () => {
    if (!selectedTaskId) {
      message.warning('请先选择任务');
      return;
    }

    try {
      // 直接打开HTML报告，报告已在任务执行时生成
      const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8004';
      window.open(`${apiUrl}/api/jobs/${selectedTaskId}/allure-report`, '_blank');
    } catch (error) {
      message.error('打开HTML报告失败');
    }
  };

  const handleAnalyzeFailures = async () => {
    if (!selectedTaskId) {
      message.warning('请先选择任务');
      return;
    }

    try {
      setLoading(true);
      const data = await client.post(`/api/reports/${selectedTaskId}/analyze-failures`);
      setFailureAnalysis(data);
      message.success('失败分析完成');
    } catch (error) {
      message.error('失败分析失败');
    } finally {
      setLoading(false);
    }
  };

  const handleGetAiSuggestions = async () => {
    if (!selectedTaskId) {
      message.warning('请先选择任务');
      return;
    }

    try {
      setLoading(true);
      const data = await client.get(`/api/reports/${selectedTaskId}/ai-suggestions?days=30`);
      setAiSuggestions(data);
      message.success('AI建议已生成');
    } catch (error) {
      message.error('获取AI建议失败');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateCustomReport = async () => {
    if (!selectedTaskId) {
      message.warning('请先选择任务');
      return;
    }

    try {
      const values = await reportForm.validateFields();
      setGeneratingReport(true);
      
      const config = {
        report_title: values.report_title || '测试报告',
        include_passed: values.include_passed !== false,
        include_failed: values.include_failed !== false,
        include_skipped: values.include_skipped || false,
        include_request_data: values.include_request_data !== false,
        include_response_data: values.include_response_data !== false,
        include_performance_metrics: values.include_performance_metrics !== false,
        include_failure_analysis: values.include_failure_analysis !== false,
        include_trends: values.include_trends || false,
        format: values.format || 'html'
      };

      if (values.format === 'json') {
        const data = await client.post(`/api/custom/generate/${selectedTaskId}`, config);
        // 下载JSON文件
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `test_report_${selectedTaskId}_${new Date().getTime()}.json`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        message.success('报告已生成并下载');
      } else {
        const response = await client.post(`/api/custom/generate/${selectedTaskId}`, config, {
          responseType: 'blob'
        });
        
        // 创建下载链接
        const blob = new Blob([response], { type: 'text/html' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `test_report_${selectedTaskId}_${new Date().getTime()}.html`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        message.success('报告已生成并下载');
      }
      
      setReportModalVisible(false);
    } catch (error) {
      message.error('生成报告失败');
    } finally {
      setGeneratingReport(false);
    }
  };

  const getStatusColor = (status) => {
    const colorMap = {
      'passed': 'green',
      'failed': 'red',
      'skipped': 'orange',
      'error': 'red'
    };
    return colorMap[status] || 'default';
  };

  const columns = [
    {
      title: '用例ID',
      dataIndex: 'test_case_id',
      key: 'test_case_id',
      width: 100
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status) => (
        <Tag color={getStatusColor(status)}>
          {status === 'passed' ? '通过' : status === 'failed' ? '失败' : status === 'skipped' ? '跳过' : status}
        </Tag>
      )
    },
    {
      title: '状态码',
      dataIndex: 'status_code',
      key: 'status_code',
      width: 100
    },
    {
      title: '执行时间',
      dataIndex: 'execution_time',
      key: 'execution_time',
      width: 120,
      render: (time) => time ? `${(time * 1000).toFixed(0)}ms` : '-'
    },
    {
      title: '请求大小',
      dataIndex: 'request_size',
      key: 'request_size',
      width: 100,
      render: (size) => size ? `${(size / 1024).toFixed(2)}KB` : '-'
    },
    {
      title: '响应大小',
      dataIndex: 'response_size',
      key: 'response_size',
      width: 100,
      render: (size) => size ? `${(size / 1024).toFixed(2)}KB` : '-'
    },
    {
      title: '错误信息',
      dataIndex: 'error_message',
      key: 'error_message',
      ellipsis: true,
      render: (text) => text ? (
        <Tag color="red" style={{ maxWidth: 300 }}>
          {text.length > 50 ? `${text.substring(0, 50)}...` : text}
        </Tag>
      ) : '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Button
          type="link"
          size="small"
          icon={<EyeOutlined />}
          onClick={() => handleView(record)}
        >
          查看
        </Button>
      )
    }
  ];

  const getStatusChart = () => {
    const passed = results.filter(r => r.status === 'passed').length;
    const failed = results.filter(r => r.status === 'failed').length;
    const skipped = results.filter(r => r.status === 'skipped').length;

    return {
      title: {
        text: '测试结果统计',
        left: 'center'
      },
      tooltip: {
        trigger: 'item'
      },
      legend: {
        orient: 'vertical',
        left: 'left'
      },
      series: [
        {
          name: '测试结果',
          type: 'pie',
          radius: '50%',
          data: [
            { value: passed, name: '通过', itemStyle: { color: '#52c41a' } },
            { value: failed, name: '失败', itemStyle: { color: '#ff4d4f' } },
            { value: skipped, name: '跳过', itemStyle: { color: '#faad14' } }
          ],
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          }
        }
      ]
    };
  };

  const getPerformanceChart = () => {
    const executionTimes = results
      .filter(r => r.execution_time)
      .map(r => r.execution_time * 1000)
      .sort((a, b) => a - b);

    if (executionTimes.length === 0) return null;

    return {
      title: {
        text: '执行时间分布',
        left: 'center'
      },
      tooltip: {
        trigger: 'axis'
      },
      xAxis: {
        type: 'category',
        data: executionTimes.map((_, i) => `用例${i + 1}`)
      },
      yAxis: {
        type: 'value',
        name: '时间(ms)'
      },
      series: [
        {
          name: '执行时间',
          type: 'bar',
          data: executionTimes,
          itemStyle: {
            color: '#1890ff'
          }
        }
      ]
    };
  };

  const getTrendChart = () => {
    if (!trendData || !trendData.trend_data) return null;

    return {
      title: {
        text: '测试通过率趋势',
        left: 'center'
      },
      tooltip: {
        trigger: 'axis'
      },
      legend: {
        data: ['通过率'],
        top: 30
      },
      xAxis: {
        type: 'category',
        data: trendData.trend_data.map(d => d.date)
      },
      yAxis: {
        type: 'value',
        name: '通过率(%)',
        max: 100,
        min: 0
      },
      series: [
        {
          name: '通过率',
          type: 'line',
          data: trendData.trend_data.map(d => d.pass_rate),
          smooth: true,
          itemStyle: { color: '#52c41a' },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(82, 196, 26, 0.3)' },
                { offset: 1, color: 'rgba(82, 196, 26, 0.1)' }
              ]
            }
          }
        }
      ]
    };
  };

  const selectedTask = tasks.find(t => t.id === selectedTaskId);

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>测试结果分析</h2>
        <Space>
          <Select
            value={selectedTaskId}
            onChange={setSelectedTaskId}
            style={{ width: 300 }}
            placeholder="选择任务"
          >
            {tasks.map(task => (
              <Select.Option key={task.id} value={task.id}>
                {task.name} - {task.status === 'completed' ? '已完成' : task.status}
              </Select.Option>
            ))}
          </Select>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleViewHtmlReport}
            disabled={!selectedTaskId}
          >
            查看HTML报告
          </Button>
          <Button
            icon={<BugOutlined />}
            onClick={handleAnalyzeFailures}
            disabled={!selectedTaskId}
          >
            失败分析
          </Button>
          <Button
            icon={<BulbOutlined />}
            onClick={handleGetAiSuggestions}
            disabled={!selectedTaskId}
          >
            AI建议
          </Button>
          <Button
            icon={<FileTextOutlined />}
            onClick={() => setReportModalVisible(true)}
            disabled={!selectedTaskId}
          >
            自定义报告
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={fetchResults}
            disabled={!selectedTaskId}
          >
            刷新
          </Button>
        </Space>
      </div>

      {selectedTask && (
        <Card style={{ marginBottom: 16 }}>
          <Descriptions column={4} size="small">
            <Descriptions.Item label="任务名称">{selectedTask.name}</Descriptions.Item>
            <Descriptions.Item label="总用例数">{selectedTask.total_cases || 0}</Descriptions.Item>
            <Descriptions.Item label="通过">
              <Tag color="green">{selectedTask.passed_cases || 0}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="失败">
              <Tag color="red">{selectedTask.failed_cases || 0}</Tag>
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      <Space direction="vertical" style={{ width: '100%' }} size="large">
        <Card 
          title="测试结果列表"
          extra={
            <Space>
              <Input
                placeholder="搜索关键词"
                prefix={<SearchOutlined />}
                style={{ width: 200 }}
                value={filters.keyword}
                onChange={(e) => setFilters({...filters, keyword: e.target.value})}
                allowClear
              />
              <Select
                placeholder="按状态筛选"
                style={{ width: 120 }}
                allowClear
                value={filters.status}
                onChange={(value) => setFilters({...filters, status: value})}
              >
                <Select.Option value="passed">通过</Select.Option>
                <Select.Option value="failed">失败</Select.Option>
                <Select.Option value="skipped">跳过</Select.Option>
              </Select>
              <Button
                icon={<FilterOutlined />}
                onClick={() => {
                  Modal.info({
                    title: '高级筛选',
                    content: (
                      <Form layout="vertical" style={{ marginTop: 16 }}>
                        <Form.Item label="状态码">
                          <InputNumber
                            style={{ width: '100%' }}
                            placeholder="HTTP状态码"
                            value={filters.statusCode}
                            onChange={(value) => setFilters({...filters, statusCode: value})}
                          />
                        </Form.Item>
                        <Form.Item label="最小执行时间(ms)">
                          <InputNumber
                            style={{ width: '100%' }}
                            value={filters.minExecutionTime}
                            onChange={(value) => setFilters({...filters, minExecutionTime: value})}
                          />
                        </Form.Item>
                        <Form.Item label="最大执行时间(ms)">
                          <InputNumber
                            style={{ width: '100%' }}
                            value={filters.maxExecutionTime}
                            onChange={(value) => setFilters({...filters, maxExecutionTime: value})}
                          />
                        </Form.Item>
                        <Form.Item>
                          <Button
                            type="primary"
                            onClick={() => {
                              setFilters({
                                status: null,
                                statusCode: null,
                                minExecutionTime: null,
                                maxExecutionTime: null,
                                keyword: filters.keyword
                              });
                              Modal.destroyAll();
                            }}
                          >
                            清除筛选
                          </Button>
                        </Form.Item>
                      </Form>
                    ),
                    width: 400
                  });
                }}
              >
                高级筛选
              </Button>
            </Space>
          }
        >
          <Table
            columns={columns}
            dataSource={results}
            loading={loading}
            rowKey="id"
            pagination={{
              pageSize: 20,
              showTotal: (total) => `共 ${total} 条记录`
            }}
          />
        </Card>

        {results.length > 0 && (
          <>
            <Card title="结果统计" extra={<BarChartOutlined />}>
              <ReactECharts
                option={getStatusChart()}
                style={{ height: '400px', width: '100%' }}
              />
            </Card>

            {getPerformanceChart() && (
              <Card title="性能分析">
                <ReactECharts
                  option={getPerformanceChart()}
                  style={{ height: '300px', width: '100%' }}
                />
              </Card>
            )}
          </>
        )}

        {trendData && trendData.trend_data && trendData.trend_data.length > 0 && (
          <Card title="趋势分析" extra={<RiseOutlined />}>
            <ReactECharts
              option={getTrendChart()}
              style={{ height: '400px', width: '100%' }}
            />
            {trendData.trend_direction && (
              <Alert
                message={trendData.trend_direction.message}
                type={trendData.trend_direction.direction === 'improving' ? 'success' : 
                      trendData.trend_direction.direction === 'declining' ? 'warning' : 'info'}
                style={{ marginTop: 16 }}
              />
            )}
          </Card>
        )}

        {failureAnalysis && (
          <Card title="失败分析" extra={<BugOutlined />}>
            <Collapse>
              <Panel header={`失败用例总数: ${failureAnalysis.total_failures}`} key="summary">
                <Descriptions column={2} bordered>
                  <Descriptions.Item label="失败类别分布">
                    {Object.entries(failureAnalysis.failure_categories || {}).map(([cat, count]) => (
                      <Tag key={cat} color="red">{cat}: {count}</Tag>
                    ))}
                  </Descriptions.Item>
                  <Descriptions.Item label="状态码分布">
                    {Object.entries(failureAnalysis.status_codes || {}).map(([code, count]) => (
                      <Tag key={code}>{code}: {count}</Tag>
                    ))}
                  </Descriptions.Item>
                </Descriptions>
                {failureAnalysis.detailed_analysis && failureAnalysis.detailed_analysis.length > 0 && (
                  <Timeline style={{ marginTop: 16 }}>
                    {failureAnalysis.detailed_analysis.map((item, index) => (
                      <Timeline.Item key={index} color="red">
                        <h4>{item.test_case_name}</h4>
                        {item.analysis && (
                          <div>
                            <p><strong>失败原因:</strong> {item.analysis.failure_reason}</p>
                            <p><strong>类别:</strong> <Tag>{item.analysis.category}</Tag></p>
                            {item.analysis.fix_suggestions && item.analysis.fix_suggestions.length > 0 && (
                              <div>
                                <strong>修复建议:</strong>
                                <ul>
                                  {item.analysis.fix_suggestions.map((suggestion, i) => (
                                    <li key={i}>{suggestion}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        )}
                      </Timeline.Item>
                    ))}
                  </Timeline>
                )}
              </Panel>
            </Collapse>
          </Card>
        )}

        {aiSuggestions && (
          <Card title="AI优化建议" extra={<BulbOutlined />}>
            {aiSuggestions.suggestions && aiSuggestions.suggestions.map((suggestion, index) => (
              <Alert
                key={index}
                message={suggestion.title}
                description={
                  <div>
                    <p>{suggestion.description}</p>
                    {suggestion.recommendations && (
                      <ul style={{ marginTop: 8 }}>
                        {suggestion.recommendations.map((rec, i) => (
                          <li key={i}>{rec}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                }
                type={suggestion.priority === 'high' ? 'error' : 'warning'}
                style={{ marginBottom: 16 }}
                showIcon
              />
            ))}
          </Card>
        )}

        {htmlReportUrl && (
          <Card title="HTML测试报告">
            <Button
              type="primary"
              href={`http://localhost:8004${htmlReportUrl}`}
              target="_blank"
              icon={<DownloadOutlined />}
            >
              打开HTML报告
            </Button>
          </Card>
        )}
      </Space>

      <Modal
        title="生成自定义报告"
        open={reportModalVisible}
        onOk={handleGenerateCustomReport}
        onCancel={() => setReportModalVisible(false)}
        width={700}
        okText="生成报告"
        cancelText="取消"
        confirmLoading={generatingReport}
      >
        <Form form={reportForm} layout="vertical" initialValues={{
          report_title: '测试报告',
          include_passed: true,
          include_failed: true,
          include_skipped: false,
          include_request_data: true,
          include_response_data: true,
          include_performance_metrics: true,
          include_failure_analysis: true,
          include_trends: false,
          format: 'html'
        }}>
          <Form.Item
            name="report_title"
            label="报告标题"
            rules={[{ required: true }]}
          >
            <Input placeholder="请输入报告标题" />
          </Form.Item>

          <Form.Item
            name="format"
            label="报告格式"
            rules={[{ required: true }]}
          >
            <Select>
              <Select.Option value="html">HTML</Select.Option>
              <Select.Option value="json">JSON</Select.Option>
            </Select>
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="include_passed" valuePropName="checked">
                <Checkbox>包含通过的用例</Checkbox>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="include_failed" valuePropName="checked">
                <Checkbox>包含失败的用例</Checkbox>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="include_skipped" valuePropName="checked">
                <Checkbox>包含跳过的用例</Checkbox>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="include_trends" valuePropName="checked">
                <Checkbox>包含趋势分析</Checkbox>
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="include_request_data" valuePropName="checked">
                <Checkbox>包含请求数据</Checkbox>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="include_response_data" valuePropName="checked">
                <Checkbox>包含响应数据</Checkbox>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="include_performance_metrics" valuePropName="checked">
                <Checkbox>包含性能指标</Checkbox>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="include_failure_analysis" valuePropName="checked">
                <Checkbox>包含失败分析</Checkbox>
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Drawer
        title="结果详情"
        placement="right"
        width={1000}
        open={drawerVisible}
        onClose={() => setDrawerVisible(false)}
      >
        {selectedResult && (
          <Tabs defaultActiveKey="basic">
            <TabPane tab="基本信息" key="basic">
              <Descriptions column={1} bordered>
                <Descriptions.Item label="状态">
                  <Tag color={getStatusColor(selectedResult.status)}>{selectedResult.status}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="状态码">{selectedResult.status_code || '-'}</Descriptions.Item>
                <Descriptions.Item label="执行时间">
                  {selectedResult.execution_time ? `${(selectedResult.execution_time * 1000).toFixed(0)}ms` : '-'}
                </Descriptions.Item>
                {selectedResult.retry_info && (
                  <>
                    <Descriptions.Item label="重试次数">
                      <Tag color="orange">{selectedResult.retry_info.retry_count || 0}</Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="错误类型">
                      <Tag>
                        {selectedResult.retry_info.error_type === 'rate_limit' ? '限流错误' :
                         selectedResult.retry_info.error_type === 'network_error' ? '网络错误' :
                         selectedResult.retry_info.error_type === 'server_error' ? '服务器错误' :
                         selectedResult.retry_info.error_type}
                      </Tag>
                    </Descriptions.Item>
                  </>
                )}
                <Descriptions.Item label="请求大小">
                  {selectedResult.request_size ? `${(selectedResult.request_size / 1024).toFixed(2)}KB` : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="响应大小">
                  {selectedResult.response_size ? `${(selectedResult.response_size / 1024).toFixed(2)}KB` : '-'}
                </Descriptions.Item>
                {selectedResult.error_message && (
                  <Descriptions.Item label="错误信息">
                    <Tag color="red">{selectedResult.error_message}</Tag>
                  </Descriptions.Item>
                )}
              </Descriptions>
            </TabPane>

            <TabPane tab="请求数据" key="request">
              {selectedResult.request_data ? (
                <MonacoEditor
                  height="600px"
                  language="json"
                  value={JSON.stringify(selectedResult.request_data, null, 2)}
                  theme="vs-dark"
                  options={{
                    readOnly: true,
                    minimap: { enabled: true }
                  }}
                />
              ) : (
                <Empty description="暂无请求数据" />
              )}
            </TabPane>

            <TabPane tab="响应数据" key="response">
              {selectedResult.response_data ? (
                <MonacoEditor
                  height="600px"
                  language="json"
                  value={JSON.stringify(selectedResult.response_data, null, 2)}
                  theme="vs-dark"
                  options={{
                    readOnly: true,
                    minimap: { enabled: true }
                  }}
                />
              ) : (
                <Empty description="暂无响应数据" />
              )}
            </TabPane>

            <TabPane tab="断言结果" key="assertions">
              {selectedResult.assertions_result ? (
                <MonacoEditor
                  height="600px"
                  language="json"
                  value={JSON.stringify(selectedResult.assertions_result, null, 2)}
                  theme="vs-dark"
                  options={{
                    readOnly: true,
                    minimap: { enabled: true }
                  }}
                />
              ) : (
                <Empty description="暂无断言结果" />
              )}
            </TabPane>

            {selectedResult.failure_analysis && (
              <TabPane tab="失败分析" key="analysis">
                <Descriptions column={1} bordered>
                  <Descriptions.Item label="失败原因">
                    {selectedResult.failure_analysis.failure_reason}
                  </Descriptions.Item>
                  <Descriptions.Item label="类别">
                    <Tag>{selectedResult.failure_analysis.category}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="根本原因">
                    {selectedResult.failure_analysis.root_cause}
                  </Descriptions.Item>
                  <Descriptions.Item label="修复建议">
                    <ul>
                      {selectedResult.failure_analysis.fix_suggestions?.map((suggestion, i) => (
                        <li key={i}>{suggestion}</li>
                      ))}
                    </ul>
                  </Descriptions.Item>
                </Descriptions>
              </TabPane>
            )}
          </Tabs>
        )}
      </Drawer>
    </div>
  );
};

export default TestResults;
