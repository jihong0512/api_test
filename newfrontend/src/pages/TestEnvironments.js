import React, { useState, useEffect } from 'react';
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
  Popconfirm,
  Badge,
  Descriptions,
  Switch,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  EnvironmentOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import client from '../api/client';
import { getErrorMessage } from '../utils/errorHandler';
import '../styles/animations.css';

const { TextArea } = Input;
const { Option } = Select;

const TestEnvironments = () => {
  const { id } = useParams();
  const [environments, setEnvironments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [editingEnv, setEditingEnv] = useState(null);
  const [form] = Form.useForm();
  const [currentEnvId, setCurrentEnvId] = useState(null);

  useEffect(() => {
    fetchEnvironments();
  }, [id]);

  const fetchEnvironments = async () => {
    setLoading(true);
    try {
      const data = await client.get(`/api/configs/?project_id=${id}`);
      setEnvironments(Array.isArray(data) ? data : []);
      // 找到默认环境
      const defaultEnv = data?.find((env) => env.is_default);
      if (defaultEnv) {
        setCurrentEnvId(defaultEnv.id);
      }
    } catch (error) {
      console.error('获取环境配置列表失败', error);
      message.error('获取环境配置列表失败');
      setEnvironments([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingEnv(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (record) => {
    setEditingEnv(record);
    form.setFieldsValue({
      name: record.name,
      env_type: record.env_type,
      base_url: record.base_url,
      login_username: record.login_username,
      login_password: record.login_password,
      description: record.description,
      is_default: record.is_default,
    });
    setModalVisible(true);
  };

  const handleSubmit = async (values) => {
    try {
      if (editingEnv) {
        await client.put(`/api/configs/${editingEnv.id}`, values);
        message.success('环境配置更新成功');
      } else {
        await client.post(`/api/configs/?project_id=${id}`, values);
        message.success('环境配置创建成功');
      }
      setModalVisible(false);
      form.resetFields();
      await fetchEnvironments();
    } catch (error) {
      message.error(editingEnv ? '更新失败: ' : '创建失败: ' + getErrorMessage(error));
    }
  };

  const handleDelete = async (envId) => {
    try {
      await client.delete(`/api/configs/${envId}`);
      message.success('环境配置删除成功');
      await fetchEnvironments();
    } catch (error) {
      message.error('删除失败: ' + getErrorMessage(error));
    }
  };

  const handleSetDefault = async (envId) => {
    try {
      await client.put(`/api/configs/${envId}`, { is_default: true });
      message.success('默认环境设置成功');
      setCurrentEnvId(envId);
      await fetchEnvironments();
    } catch (error) {
      message.error('设置失败: ' + getErrorMessage(error));
    }
  };

  const handleSwitchEnvironment = async (envId, envName) => {
    try {
      const response = await client.post(
        `/api/configs/${envId}/set-current?project_id=${id}`
      );
      message.success(response.message || `已切换到环境: ${envName}`);
      setCurrentEnvId(envId);
      await fetchEnvironments();
    } catch (error) {
      message.error('切换失败: ' + getErrorMessage(error));
    }
  };

  const handleViewDetail = (record) => {
    setEditingEnv(record);
    setDetailModalVisible(true);
  };

  const envTypeMap = {
    test_cn: { text: '国内测试', color: 'blue' },
    test_overseas: { text: '国外测试', color: 'cyan' },
    gray_cn: { text: '国内灰度', color: 'orange' },
    gray_overseas: { text: '国外灰度', color: 'purple' },
  };

  const columns = [
    {
      title: '环境名称',
      dataIndex: 'name',
      key: 'name',
      render: (text, record) => (
        <Space>
          <span>{text}</span>
          {record.is_default && (
            <Badge
              count="默认"
              style={{ backgroundColor: '#52c41a' }}
              title="默认环境"
            />
          )}
          {currentEnvId === record.id && !record.is_default && (
            <Tag color="processing">当前使用</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '环境类型',
      dataIndex: 'env_type',
      key: 'env_type',
      render: (type) => {
        const config = envTypeMap[type] || { text: type, color: 'default' };
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
    {
      title: 'Base URL',
      dataIndex: 'base_url',
      key: 'base_url',
      render: (url) => (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
          <LinkOutlined style={{ marginTop: '2px', flexShrink: 0 }} />
          <span 
            style={{ 
              fontFamily: 'monospace', 
              wordBreak: 'break-all',
              whiteSpace: 'normal',
              lineHeight: '1.5'
            }}
          >
            {url}
          </span>
        </div>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (time) => (time ? new Date(time).toLocaleString() : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 280,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            icon={<EnvironmentOutlined />}
            onClick={() => handleViewDetail(record)}
          >
            详情
          </Button>
          {currentEnvId !== record.id && (
            <Button
              type="link"
              style={{ color: '#1890ff' }}
              onClick={() => handleSwitchEnvironment(record.id, record.name)}
            >
              切换
            </Button>
          )}
          {!record.is_default && (
            <Button
              type="link"
              icon={<CheckCircleOutlined />}
              onClick={() => handleSetDefault(record.id)}
            >
              设为默认
            </Button>
          )}
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这个环境配置吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Card
        title={
          <Space>
            <EnvironmentOutlined />
            <span>环境配置管理</span>
          </Space>
        }
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新建环境
          </Button>
        }
        className="fade-in card-shadow"
      >
        <Table
          columns={columns}
          dataSource={environments}
          loading={loading}
          rowKey="id"
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 个环境`,
          }}
        />
      </Card>

      {/* 创建/编辑环境Modal */}
      <Modal
        title={editingEnv ? '编辑环境配置' : '新建环境配置'}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          form.resetFields();
          setEditingEnv(null);
        }}
        footer={null}
        width={600}
        className="fade-in"
      >
        <Form
          form={form}
          onFinish={handleSubmit}
          layout="vertical"
          style={{ marginTop: 24 }}
        >
          <Form.Item
            name="name"
            label="环境名称"
            rules={[{ required: true, message: '请输入环境名称' }]}
          >
            <Input placeholder="例如: 国内环境" />
          </Form.Item>

          <Form.Item
            name="env_type"
            label="环境类型"
            rules={[{ required: true, message: '请选择环境类型' }]}
          >
            <Select 
              placeholder="选择环境类型"
              onChange={(value) => {
                // 如果选择国内环境，自动填充默认登录名和密码
                if (value === 'test_cn') {
                  form.setFieldsValue({
                    login_username: '13126827685',
                    login_password: '5973ea46bea2afae24c2ce6517fa6f7f'
                  });
                }
              }}
            >
              <Option value="test_cn">国内测试</Option>
              <Option value="test_overseas">国外测试</Option>
              <Option value="gray_cn">国内灰度</Option>
              <Option value="gray_overseas">国外灰度</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="base_url"
            label="Base URL"
            rules={[
              { required: true, message: '请输入Base URL' },
              {
                pattern: /^(https?:\/\/)?[\w\.-]+(:\d+)?(\/.*)?$/,
                message: '请输入有效的URL格式',
              },
            ]}
          >
            <Input
              placeholder="例如: https://api.example.com 或 192.168.1.100:8080"
              prefix={<LinkOutlined />}
            />
          </Form.Item>

          <Form.Item
            name="login_username"
            label="登录用户名"
          >
            <Input placeholder="请输入登录用户名（可选）" />
          </Form.Item>

          <Form.Item
            name="login_password"
            label="登录密码"
          >
            <Input.Password placeholder="请输入登录密码（可选）" />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <TextArea
              rows={3}
              placeholder="请输入环境描述（可选）"
              maxLength={500}
              showCount
            />
          </Form.Item>

          <Form.Item
            name="is_default"
            label="设为默认环境"
            valuePropName="checked"
          >
            <Switch />
            <div style={{ marginTop: 8, color: '#8c8c8c', fontSize: 12 }}>
              设置为默认环境后，执行测试时将优先使用此环境
            </div>
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, marginTop: 24 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => setModalVisible(false)}>取消</Button>
              <Button type="primary" htmlType="submit">
                {editingEnv ? '更新' : '创建'}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 环境详情Modal */}
      <Modal
        title="环境配置详情"
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            关闭
          </Button>,
          <Button
            key="edit"
            type="primary"
            onClick={() => {
              setDetailModalVisible(false);
              handleEdit(editingEnv);
            }}
          >
            编辑
          </Button>,
        ]}
        width={700}
        className="fade-in"
      >
        {editingEnv && (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="环境名称">{editingEnv.name}</Descriptions.Item>
            <Descriptions.Item label="环境类型">
              <Tag color={envTypeMap[editingEnv.env_type]?.color || 'default'}>
                {envTypeMap[editingEnv.env_type]?.text || editingEnv.env_type}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Base URL">
              <span 
                style={{ 
                  fontFamily: 'monospace',
                  wordBreak: 'break-all',
                  whiteSpace: 'normal',
                  lineHeight: '1.5',
                  display: 'block'
                }}
              >
                {editingEnv.base_url}
              </span>
            </Descriptions.Item>
            <Descriptions.Item label="登录用户名">
              {editingEnv.login_username || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="登录密码">
              {editingEnv.login_password ? '••••••••' : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="描述">
              {editingEnv.description || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="默认环境">
              {editingEnv.is_default ? (
                <Badge status="success" text="是" />
              ) : (
                <Badge status="default" text="否" />
              )}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {editingEnv.created_at
                ? new Date(editingEnv.created_at).toLocaleString()
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="更新时间">
              {editingEnv.updated_at
                ? new Date(editingEnv.updated_at).toLocaleString()
                : '-'}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default TestEnvironments;

