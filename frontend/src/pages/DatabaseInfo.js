import React, { useState, useEffect } from 'react';
import { Table, Card, Descriptions, Tag, Tabs, Button, Space, message, Modal, Form, Input, Select, InputNumber, Progress, Badge, List, Avatar, Timeline, Collapse } from 'antd';
import { DatabaseOutlined, TableOutlined, PlusOutlined, CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined, SyncOutlined, CheckCircleFilled, CloseCircleFilled, LoadingOutlined, StopOutlined } from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import client from '../api/client';
import { getErrorMessage } from '../utils/errorHandler';

const DatabaseInfo = () => {
  const { id } = useParams(); // project_id
  const [connectionId, setConnectionId] = useState(null);
  const [connections, setConnections] = useState([]);
  const [tables, setTables] = useState([]);
  const [selectedTable, setSelectedTable] = useState(null);
  const [columns, setColumns] = useState([]);
  const [relationships, setRelationships] = useState([]);
  const [loading, setLoading] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionModalVisible, setConnectionModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [taskStatuses, setTaskStatuses] = useState({}); // 存储任务状态 {connectionId: {metadataTask: {state, status, task_id}, graphTask: {}}}
  const [pollingTasks, setPollingTasks] = useState({}); // 存储正在轮询的任务ID
  const [taskIds, setTaskIds] = useState({}); // 存储任务ID {connectionId: {metadataTask: taskId, graphTask: taskId}}

  useEffect(() => {
    // 获取数据库连接列表
    fetchConnections();
  }, [id]);

  useEffect(() => {
    // 当连接列表变化时，更新当前连接ID
    if (connections && connections.length > 0) {
      const activeConnection = connections.find(c => c.status === 'active') || connections[0];
      if (activeConnection && activeConnection.id !== connectionId) {
        setConnectionId(activeConnection.id);
      }
      
      // 检查是否有正在解析的连接，需要定期刷新状态和查询任务
      const analyzingConnections = connections.filter(c => c.status === 'analyzing' || c.status === 'pending');
      if (analyzingConnections.length > 0) {
        // 为每个analyzing的连接查询任务ID并开始轮询
        analyzingConnections.forEach(async (conn) => {
          if (!taskStatuses[conn.id]?.metadataTask) {
            try {
              // 查询任务ID
              const taskInfo = await client.get(`/api/connections/${conn.id}/task`);
              if (taskInfo.task_id) {
                // 开始轮询任务状态
                pollTaskStatus(taskInfo.task_id, conn.id, 'metadataTask');
              }
            } catch (error) {
              console.error('查询任务ID失败', error);
            }
          }
        });
        
        // 设置定时刷新连接列表
        const interval = setInterval(() => {
          fetchConnections();
        }, 3000);
        
        return () => clearInterval(interval);
      }
    } else {
      setConnectionId(null);
    }
  }, [connections]);

  useEffect(() => {
    if (connectionId) {
      fetchTables();
      fetchRelationships();
    }
  }, [connectionId]);

  useEffect(() => {
    if (selectedTable) {
      fetchColumns(selectedTable.id);
    }
  }, [selectedTable]);

  const fetchConnections = async () => {
    try {
      const connectionsData = await client.get(`/api/connections/?project_id=${id}`);
      
      // 去重：根据 host + port + database_name 去重，保留ID最大的（最新的）
      if (connectionsData && connectionsData.length > 0) {
        const connectionMap = new Map();
        connectionsData.forEach(conn => {
          const key = `${conn.host}:${conn.port}:${conn.database_name}`;
          const existing = connectionMap.get(key);
          if (!existing || conn.id > existing.id) {
            // 保留ID最大的（最新的）
            connectionMap.set(key, conn);
          }
        });
        const uniqueConnections = Array.from(connectionMap.values());
        setConnections(uniqueConnections);
        
        // 如果当前连接不在列表中，重置
        if (uniqueConnections.length > 0) {
          const currentExists = uniqueConnections.find(c => c.id === connectionId);
          if (!currentExists) {
            const activeConnection = uniqueConnections.find(c => c.status === 'active') || uniqueConnections[0];
            setConnectionId(activeConnection?.id || null);
          }
        } else {
          setConnectionId(null);
        }
      } else {
        setConnections([]);
        setConnectionId(null);
      }
    } catch (error) {
      console.error('获取数据库连接列表失败', error);
      setConnections([]);
      setConnectionId(null);
      if (error.response?.status !== 404) {
        message.error('获取数据库连接列表失败');
      }
    }
  };

  // 轮询任务状态
  const pollTaskStatus = async (taskId, connectionId, taskType) => {
    if (!taskId || pollingTasks[taskId]) return;
    
    setPollingTasks(prev => ({ ...prev, [taskId]: true }));
    
    const poll = async () => {
      try {
        const status = await client.get(`/api/connections/task/${taskId}/status`);
        
        // 标准化状态：SUCCESS -> completed，避免前端继续显示等待
        const normalized = {
          ...status,
          state: status.state === 'SUCCESS' ? 'SUCCESS' : status.state,
          status: status.state === 'SUCCESS' ? '完成' : status.status,
          progress: status.state === 'SUCCESS' ? 100 : status.progress,
          meta: {
            ...(status.meta || {}),
            status: status.state === 'SUCCESS' ? 'completed' : (status.meta?.status || status.state)
          }
        };

        setTaskStatuses(prev => ({
          ...prev,
          [connectionId]: {
            ...prev[connectionId],
            [taskType]: { ...normalized, task_id: taskId }
          }
        }));
        
        // 同时存储 task_id
        setTaskIds(prev => ({
          ...prev,
          [connectionId]: {
            ...prev[connectionId],
            [taskType]: taskId
          }
        }));
        
        if (status.state === 'PENDING' || status.state === 'PROGRESS') {
          // 继续轮询
          setTimeout(poll, 2000);
        } else {
          // 任务完成或失败，停止轮询
          setPollingTasks(prev => {
            const newTasks = { ...prev };
            delete newTasks[taskId];
            return newTasks;
          });
          
          // 清除 task_id
          setTaskIds(prev => {
            const newTasks = { ...prev };
            if (newTasks[connectionId]) {
              delete newTasks[connectionId][taskType];
              if (Object.keys(newTasks[connectionId]).length === 0) {
                delete newTasks[connectionId];
              }
            }
            return newTasks;
          });
          
          if (status.state === 'SUCCESS') {
            message.success(status.message || '任务完成');
            // 刷新数据
            await fetchConnections();
            if (taskType === 'metadata') {
              await fetchTables();
              await fetchRelationships();
            }
          } else if (status.state === 'REVOKED') {
            message.info('任务已取消');
            await fetchConnections();
          } else {
            message.error(status.message || '任务执行失败');
            // 任务失败时也刷新连接列表，以便更新状态
            await fetchConnections();
          }
        }
      } catch (error) {
        console.error('获取任务状态失败', error);
        setPollingTasks(prev => {
          const newTasks = { ...prev };
          delete newTasks[taskId];
          return newTasks;
        });
      }
    };
    
    poll();
  };

  // 取消任务
  const handleCancelTask = async (taskId, connectionId, taskType) => {
    if (!taskId) {
      message.warning('没有正在执行的任务');
      return;
    }

    try {
      const response = await client.post(`/api/connections/task/${taskId}/cancel`);
      
      if (response.status === 'cancelled') {
        // 停止轮询
        setPollingTasks(prev => {
          const newTasks = { ...prev };
          delete newTasks[taskId];
          return newTasks;
        });
        
        // 清除 task_id
        setTaskIds(prev => {
          const newTasks = { ...prev };
          if (newTasks[connectionId]) {
            delete newTasks[connectionId][taskType];
            if (Object.keys(newTasks[connectionId]).length === 0) {
              delete newTasks[connectionId];
            }
          }
          return newTasks;
        });
        
        // 更新任务状态
        setTaskStatuses(prev => ({
          ...prev,
          [connectionId]: {
            ...prev[connectionId],
            [taskType]: {
              state: 'REVOKED',
              status: '已取消',
              message: '任务已被用户取消'
            }
          }
        }));
        
        message.success('任务已成功取消');
        
        // 刷新连接列表
        await fetchConnections();
      } else if (response.status === 'already_finished') {
        message.info(response.message);
        // 停止轮询
        setPollingTasks(prev => {
          const newTasks = { ...prev };
          delete newTasks[taskId];
          return newTasks;
        });
        // 清除 task_id
        setTaskIds(prev => {
          const newTasks = { ...prev };
          if (newTasks[connectionId]) {
            delete newTasks[connectionId][taskType];
            if (Object.keys(newTasks[connectionId]).length === 0) {
              delete newTasks[connectionId];
            }
          }
          return newTasks;
        });
        await fetchConnections();
      } else {
        message.warning(response.message || '取消任务请求已发送');
      }
    } catch (error) {
      console.error('取消任务失败', error);
      message.error('取消任务失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleCreateConnection = async (values) => {
    try {
      setLoading(true);
      const response = await client.post(`/api/connections/?project_id=${id}`, values);
      
      if (response && response.id) {
        message.success('数据库连接创建成功，正在解析元数据...');
        setConnectionModalVisible(false);
        form.resetFields();
        
        // 刷新连接列表
        await fetchConnections();
        
        // 如果返回了任务ID，立即开始轮询
        if (response.metadata_task_id) {
          pollTaskStatus(response.metadata_task_id, response.id, 'metadataTask');
        } else {
          // 否则等待后查询任务ID
          setTimeout(async () => {
            try {
              const taskInfo = await client.get(`/api/connections/${response.id}/task`);
              if (taskInfo.task_id) {
                pollTaskStatus(taskInfo.task_id, response.id, 'metadataTask');
              }
            } catch (error) {
              console.error('查询任务ID失败', error);
            }
          }, 2000);
        }
      } else {
        message.warning('连接已创建，但未返回连接信息');
        await fetchConnections();
      }
    } catch (error) {
      console.error('创建数据库连接错误:', error);
      const errorMsg = getErrorMessage(error);
      message.error(`创建数据库连接失败: ${errorMsg}`, 5);
    } finally {
      setLoading(false);
    }
  };

  const handleTestConnection = async () => {
    try {
      const values = await form.validateFields();
      setTestingConnection(true); // 使用独立的loading状态
      // 调用测试连接API
      const result = await client.post('/api/connections/test', values);
      if (result && result.success) {
        message.success(result.message || '连接测试成功！');
      } else {
        message.error(result?.message || '连接测试失败');
      }
    } catch (error) {
      console.error('测试连接错误:', error);
      const errorMsg = getErrorMessage(error);
      // 显示详细的错误信息
      message.error(`连接测试失败: ${errorMsg}`, 5); // 显示5秒
      console.error('完整错误信息:', {
        status: error.response?.status,
        statusText: error.response?.statusText,
        data: error.response?.data,
        message: error.message
      });
    } finally {
      setTestingConnection(false); // 使用独立的loading状态
    }
  };

  const fetchTables = async () => {
    if (!connectionId) {
      setTables([]);
      return;
    }
    setLoading(true);
    try {
      const data = await client.get(`/api/metadata/tables?connection_id=${connectionId}`);
      setTables(data);
    } catch (error) {
      message.error('获取表信息失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchColumns = async (tableId) => {
    setLoading(true);
    try {
      const data = await client.get(`/api/metadata/tables/${tableId}/columns`);
      setColumns(data);
    } catch (error) {
      message.error('获取字段信息失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchRelationships = async () => {
    if (!connectionId) {
      setRelationships([]);
      return;
    }
    try {
      const data = await client.get(`/api/metadata/relationships?connection_id=${connectionId}`);
      setRelationships(data);
    } catch (error) {
      console.error('获取关系信息失败', error);
    }
  };

  const tableColumns = [
    {
      title: '表名',
      dataIndex: 'table_name',
      key: 'table_name',
      render: (text, record) => (
        <Space>
          <TableOutlined />
          <a onClick={() => setSelectedTable(record)}>{text}</a>
        </Space>
      ),
    },
    {
      title: '表含义',
      dataIndex: 'table_comment',
      key: 'table_comment',
      render: (text) => text || '-',
    },
    {
      title: '字段数',
      dataIndex: 'column_count',
      key: 'column_count',
    },
    {
      title: '行数',
      dataIndex: 'row_count',
      key: 'row_count',
      render: (text) => text ? text.toLocaleString() : '-',
    },
    {
      title: '主键',
      dataIndex: 'primary_keys',
      key: 'primary_keys',
      render: (text) => {
        if (!text) return '-';
        try {
          const keys = JSON.parse(text);
          return keys.map((key, idx) => <Tag key={idx} color="blue">{key}</Tag>);
        } catch {
          return text;
        }
      },
    },
  ];

  const columnColumns = [
    {
      title: '字段名',
      dataIndex: 'column_name',
      key: 'column_name',
    },
    {
      title: '字段含义',
      dataIndex: 'column_comment',
      key: 'column_comment',
      render: (text) => text || '-',
    },
    {
      title: '数据类型',
      dataIndex: 'data_type',
      key: 'data_type',
      render: (text) => <Tag>{text}</Tag>,
    },
    {
      title: '可空',
      dataIndex: 'is_nullable',
      key: 'is_nullable',
      render: (text) => text === 'YES' ? <Tag color="green">是</Tag> : <Tag color="red">否</Tag>,
    },
    {
      title: '主键',
      dataIndex: 'is_primary_key',
      key: 'is_primary_key',
      render: (isPk) => isPk ? <Tag color="blue">主键</Tag> : '-',
    },
    {
      title: '外键',
      dataIndex: 'is_foreign_key',
      key: 'is_foreign_key',
      render: (isFk) => isFk ? <Tag color="orange">外键</Tag> : '-',
    },
    {
      title: '自增',
      dataIndex: 'auto_increment',
      key: 'auto_increment',
      render: (autoInc) => autoInc ? <Tag color="purple">是</Tag> : '-',
    },
  ];

  const relationshipColumns = [
    {
      title: '源表',
      dataIndex: 'source_table_name',
      key: 'source_table_name',
    },
    {
      title: '关系类型',
      dataIndex: 'relationship_type',
      key: 'relationship_type',
      render: (type) => {
        const typeMap = {
          has_a: { text: '包含', color: 'blue' },
          is_a: { text: '继承', color: 'green' },
          depend_on: { text: '依赖', color: 'orange' },
          foreign_key: { text: '外键', color: 'purple' },
        };
        const config = typeMap[type] || { text: type, color: 'default' };
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
    {
      title: '目标表',
      dataIndex: 'target_table_name',
      key: 'target_table_name',
    },
    {
      title: '外键字段',
      dataIndex: 'foreign_key_columns',
      key: 'foreign_key_columns',
      render: (text) => {
        if (!text) return '-';
        try {
          const cols = JSON.parse(text);
          return cols.join(', ');
        } catch {
          return text;
        }
      },
    },
    {
      title: '引用字段',
      dataIndex: 'referred_columns',
      key: 'referred_columns',
      render: (text) => {
        if (!text) return '-';
        try {
          const cols = JSON.parse(text);
          return cols.join(', ');
        } catch {
          return text;
        }
      },
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      render: (text) => text || '-',
    },
  ];

  const tabItems = [
    {
      key: 'tables',
      label: '表信息',
      children: (
        <Table
          columns={tableColumns}
          dataSource={tables}
          loading={loading}
          rowKey="id"
          pagination={{ pageSize: 10 }}
        />
      ),
    },
    {
      key: 'columns',
      label: '字段信息',
      children: selectedTable ? (
        <div>
          <Descriptions title={selectedTable.table_name} bordered style={{ marginBottom: 16 }}>
            <Descriptions.Item label="表含义">{selectedTable.table_comment || '-'}</Descriptions.Item>
            <Descriptions.Item label="字段数">{selectedTable.column_count}</Descriptions.Item>
            <Descriptions.Item label="行数">{selectedTable.row_count?.toLocaleString() || '-'}</Descriptions.Item>
          </Descriptions>
          <Table
            columns={columnColumns}
            dataSource={columns}
            loading={loading}
            rowKey="id"
            pagination={{ pageSize: 20 }}
          />
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 50 }}>
          请选择一个表查看字段信息
        </div>
      ),
    },
    {
      key: 'relationships',
      label: '表关系',
      children: (
        <Table
          columns={relationshipColumns}
          dataSource={relationships}
          loading={loading}
          rowKey="id"
          pagination={{ pageSize: 10 }}
        />
      ),
    },
  ];

  // 获取状态标签
  const getStatusTag = (status) => {
    const statusMap = {
      'active': { color: 'success', text: '活跃', icon: <CheckCircleOutlined /> },
      'pending': { color: 'default', text: '等待中', icon: <ClockCircleOutlined /> },
      'analyzing': { color: 'processing', text: '解析中', icon: <SyncOutlined spin /> },
      'error': { color: 'error', text: '错误', icon: <ExclamationCircleOutlined /> },
      'inactive': { color: 'default', text: '未激活', icon: <ClockCircleOutlined /> },
    };
    const config = statusMap[status] || statusMap['inactive'];
    return <Badge status={config.color} text={config.text} />;
  };

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>
          <DatabaseOutlined /> 数据库连接管理
        </h2>
        <Button 
          type="primary" 
          icon={<PlusOutlined />} 
          onClick={() => {
            // 如果有现有连接，回填最后一个连接的信息（通常是用户最近使用的）
            // 注意：后端出于安全考虑，不会返回密码字段，所以密码需要用户重新输入
            if (connections && connections.length > 0) {
              const lastConnection = connections[connections.length - 1];
              form.setFieldsValue({
                db_type: lastConnection.db_type || 'mysql',
                host: lastConnection.host || '',
                port: lastConnection.port || 3306,
                database_name: lastConnection.database_name || '',
                username: lastConnection.username || '',  // 如果后端返回username字段
                password: ''  // 密码不回填，需要用户重新输入（安全考虑）
              });
            } else {
              // 如果没有现有连接，使用uitest数据库的默认值（uitest作为被测系统）
              form.setFieldsValue({
                db_type: 'mysql',
                host: 'localhost',
                port: 3306,
                database_name: 'uitest',
                username: 'root',
                password: 'Qq204700'
              });
            }
            setConnectionModalVisible(true);
          }}
        >
          创建数据库连接
        </Button>
      </div>

      {/* 连接列表 */}
      <Card title="数据库连接列表" style={{ marginBottom: 16 }}>
        {connections.length > 0 ? (
          <List
            dataSource={connections}
            renderItem={(connection) => {
              const isSelected = connection.id === connectionId;
              const connectionStatus = taskStatuses[connection.id] || {};
              const metadataStatus = connectionStatus.metadataTask;
              const graphStatus = connectionStatus.graphTask;
              
              return (
                <List.Item
                  key={connection.id}
                  style={{
                    padding: '16px',
                    border: isSelected ? '2px solid #1890ff' : '1px solid #d9d9d9',
                    borderRadius: '4px',
                    marginBottom: '12px',
                    cursor: 'pointer',
                    backgroundColor: isSelected ? '#e6f7ff' : '#fff'
                  }}
                  onClick={() => setConnectionId(connection.id)}
                  actions={[
                    // 如果有正在执行的任务，显示取消按钮
                    (metadataStatus && (metadataStatus.state === 'PENDING' || metadataStatus.state === 'PROGRESS')) ? (
                      <Button
                        key="cancel"
                        danger
                        size="small"
                        icon={<StopOutlined />}
                        onClick={async (e) => {
                          e.stopPropagation();
                          // 从存储的 taskIds 中获取 task_id
                          let taskId = taskIds[connection.id]?.metadataTask;
                          
                          // 如果没有，尝试从任务状态中获取
                          if (!taskId && metadataStatus.task_id) {
                            taskId = metadataStatus.task_id;
                          }
                          
                          // 如果还是没有，尝试从 API 获取
                          if (!taskId) {
                            try {
                              const taskInfo = await client.get(`/api/connections/${connection.id}/task`);
                              taskId = taskInfo.task_id;
                            } catch (err) {
                              console.error('获取任务ID失败', err);
                            }
                          }
                          
                          if (taskId) {
                            handleCancelTask(taskId, connection.id, 'metadataTask');
                          } else {
                            message.warning('无法获取任务ID，请刷新页面后重试');
                          }
                        }}
                      >
                        取消
                      </Button>
                    ) : null,
                    <Button
                      key="select"
                      type={isSelected ? 'primary' : 'default'}
                      onClick={(e) => {
                        e.stopPropagation();
                        setConnectionId(connection.id);
                      }}
                    >
                      {isSelected ? '已选中' : '选择'}
                    </Button>
                  ].filter(Boolean)}
                >
                  <List.Item.Meta
                    avatar={<Avatar icon={<DatabaseOutlined />} />}
                    title={
                      <Space>
                        <span>{connection.database_name}</span>
                        {getStatusTag(connection.status)}
                      </Space>
                    }
                    description={
                      <div>
                        <div>
                          <Tag>{connection.db_type}</Tag>
                          <span>{connection.host}:{connection.port}</span>
                        </div>
                        {/* 任务状态显示 */}
                        {(connection.status === 'analyzing' || connection.status === 'pending' || (metadataStatus && (metadataStatus.state === 'PENDING' || metadataStatus.state === 'PROGRESS'))) && (
                          <div style={{ marginTop: 8 }}>
                            <Progress
                              percent={metadataStatus?.meta?.progress || metadataStatus?.progress || 0}
                              size="small"
                              status={metadataStatus?.state === 'FAILURE' ? 'exception' : 'active'}
                            />
                            <div style={{ fontSize: '12px', color: '#666', marginTop: 4 }}>
                              {metadataStatus?.meta?.message || metadataStatus?.message || (connection.status === 'pending' ? '等待中...' : '正在解析元数据...')}
                            </div>
                            {metadataStatus?.meta?.current_table && (
                              <div style={{ fontSize: '12px', color: '#1890ff', marginTop: 2 }}>
                                当前处理: {metadataStatus.meta.current_table}
                              </div>
                            )}
                            {metadataStatus?.meta?.total_tables && (
                              <div style={{ fontSize: '12px', color: '#666', marginTop: 2 }}>
                                进度: {metadataStatus.meta.processed_tables || 0} / {metadataStatus.meta.total_tables} 个表
                              </div>
                            )}
                            {/* 显示解析节点 */}
                            {metadataStatus?.meta?.nodes && metadataStatus.meta.nodes.length > 0 && (
                              <Collapse
                                size="small"
                                style={{ marginTop: 8 }}
                                items={[{
                                  key: 'nodes',
                                  label: '解析节点详情',
                                  children: (
                                    <Timeline
                                      size="small"
                                      items={metadataStatus.meta.nodes.map(node => ({
                                        dot: node.status === 'completed' ? (
                                          <CheckCircleFilled style={{ color: '#52c41a' }} />
                                        ) : node.status === 'failed' ? (
                                          <CloseCircleFilled style={{ color: '#ff4d4f' }} />
                                        ) : (
                                          <LoadingOutlined style={{ color: '#1890ff' }} />
                                        ),
                                        children: (
                                          <div>
                                            <div style={{ fontWeight: 500 }}>
                                              {node.name}
                                            </div>
                                            <div style={{ fontSize: '12px', color: '#666', marginTop: 2 }}>
                                              {node.message}
                                            </div>
                                          </div>
                                        )
                                      }))}
                                    />
                                  )
                                }]}
                              />
                            )}
                          </div>
                        )}
                        {metadataStatus && metadataStatus.state !== 'SUCCESS' && (
                          <div style={{ marginTop: 8, fontSize: '12px' }}>
                            <Tag color={metadataStatus.state === 'PROGRESS' ? 'processing' : metadataStatus.state === 'FAILURE' ? 'error' : 'default'}>
                              元数据: {metadataStatus.status}
                            </Tag>
                            {metadataStatus.progress !== undefined && (
                              <Progress
                                percent={metadataStatus.progress}
                                size="small"
                                style={{ display: 'inline-block', width: '100px', marginLeft: 8 }}
                              />
                            )}
                          </div>
                        )}
                        {graphStatus && graphStatus.state !== 'SUCCESS' && (
                          <div style={{ marginTop: 4, fontSize: '12px' }}>
                            <Tag color={graphStatus.state === 'PROGRESS' ? 'processing' : graphStatus.state === 'FAILURE' ? 'error' : 'default'}>
                              知识图谱: {graphStatus.status}
                            </Tag>
                            {graphStatus.progress !== undefined && (
                              <Progress
                                percent={graphStatus.progress}
                                size="small"
                                style={{ display: 'inline-block', width: '100px', marginLeft: 8 }}
                              />
                            )}
                          </div>
                        )}
                      </div>
                    }
                  />
                </List.Item>
              );
            }}
          />
        ) : (
          <div style={{ textAlign: 'center', padding: 50 }}>
            <DatabaseOutlined style={{ fontSize: 48, color: '#ccc', marginBottom: 16 }} />
            <p>该项目尚未配置数据库连接</p>
            <Button 
              type="primary" 
              icon={<PlusOutlined />} 
              onClick={() => {
                // 如果有现有连接，回填最后一个连接的信息
                if (connections && connections.length > 0) {
                  const lastConnection = connections[connections.length - 1];
                  form.setFieldsValue({
                    db_type: lastConnection.db_type || 'mysql',
                    host: lastConnection.host || '',
                    port: lastConnection.port || 3306,
                    database_name: lastConnection.database_name || '',
                    username: lastConnection.username || '',
                    password: ''  // 密码不回填，需要用户重新输入（安全考虑）
                  });
                } else {
                  // 如果没有现有连接，使用uitest数据库的默认值（uitest作为被测系统）
                  form.setFieldsValue({
                    db_type: 'mysql',
                    host: 'localhost',
                    port: 3306,
                    database_name: 'uitest',
                    username: 'root',
                    password: 'Qq204700'
                  });
                }
                setConnectionModalVisible(true);
              }}
            >
              创建数据库连接
            </Button>
          </div>
        )}
      </Card>

      {/* 数据库元数据展示 */}
      {connectionId ? (
        <Card title="数据库元数据">
          <Tabs items={tabItems} />
        </Card>
      ) : (
        <Card>
          <div style={{ textAlign: 'center', padding: 50, color: '#999' }}>
            请选择一个数据库连接查看元数据信息
          </div>
        </Card>
      )}

      <Modal
        title="创建数据库连接"
        open={connectionModalVisible}
        onCancel={() => {
          setConnectionModalVisible(false);
          form.resetFields();
        }}
        footer={null}
        width={600}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateConnection}
        >
          <Form.Item name="db_type" label="数据库类型" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="mysql">MySQL</Select.Option>
              <Select.Option value="postgresql">PostgreSQL</Select.Option>
              <Select.Option value="sqlite">SQLite</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="host" label="主机地址" rules={[{ required: true }]}>
            <Input placeholder="例如: localhost 或 127.0.0.1" />
          </Form.Item>
          <Form.Item name="port" label="端口" rules={[{ required: true }]}>
            <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="例如: 3312 (uitest数据库端口)" />
          </Form.Item>
          <Form.Item name="database_name" label="数据库名" rules={[{ required: true }]}>
            <Input placeholder="例如: uitest" />
          </Form.Item>
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input placeholder="例如: root" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true }]}>
            <Input.Password placeholder="请输入密码" />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button onClick={handleTestConnection} loading={testingConnection}>
                测试连接
              </Button>
              <Button type="primary" htmlType="submit" loading={loading}>
                创建
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default DatabaseInfo;
