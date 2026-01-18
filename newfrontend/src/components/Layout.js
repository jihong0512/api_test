import React, { useState, useEffect, useRef } from 'react';
import { Layout as AntLayout, Button, Modal, Form, Input, message, Menu, Select, Typography, Avatar, Dropdown, Space } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  ProjectOutlined,
  RocketOutlined,
  PlusOutlined,
  HomeOutlined,
  DatabaseOutlined,
  EnvironmentOutlined,
  ApartmentOutlined,
  UserOutlined,
  LogoutOutlined,
  FileTextOutlined,
  CodeOutlined,
  ShareAltOutlined,
  PlayCircleOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import client from '../api/client';
import { getErrorMessage } from '../utils/errorHandler';
import '../styles/animations.css';

const { Header, Content, Sider } = AntLayout;
const { Title } = Typography;

const Layout = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [currentProject, setCurrentProject] = useState(null);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    fetchProjects();
  }, []);

  // 获取当前项目ID
  const getCurrentProjectId = () => {
    const match = location.pathname.match(/\/projects\/(\d+)/);
    return match ? parseInt(match[1]) : null;
  };

  const currentProjectId = getCurrentProjectId();

  // 当项目ID变化时，获取项目详情
  useEffect(() => {
    if (currentProjectId) {
      fetchCurrentProject(currentProjectId);
    } else {
      setCurrentProject(null);
    }
  }, [currentProjectId]);

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const data = await client.get('/api/workspaces/');
      setProjects(data);
    } catch (error) {
      console.error('获取项目列表失败', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchCurrentProject = async (projectId) => {
    try {
      const data = await client.get(`/api/workspaces/${projectId}`);
      setCurrentProject(data);
    } catch (error) {
      console.error('获取项目详情失败', error);
      setCurrentProject(null);
    }
  };

  const handleCreate = async (values) => {
    try {
      const response = await client.post('/api/workspaces/', values);
      message.success('项目创建成功');
      setModalVisible(false);
      form.resetFields();
      await fetchProjects();
      if (response && response.id) {
        navigate(`/projects/${response.id}`);
      }
    } catch (error) {
      message.error('项目创建失败: ' + getErrorMessage(error));
    }
  };

  // 获取当前页面标题
  const getPageTitle = () => {
    if (location.pathname === '/projects') {
      return '项目管理';
    }
    if (currentProjectId) {
      const path = location.pathname;
      if (path.includes('/documents')) return '接口文档库';
      if (path.includes('/interfaces')) return '接口管理';
      if (path.includes('/api-dependencies')) return '接口依赖图';
      if (path.includes('/test-cases')) return '用例库';
      if (path.includes('/test-tasks')) return '执行任务';
      if (path.includes('/scenario-suites')) return '场景组合';
      if (path.includes('/database-info')) return '数据源配置';
      if (path.includes('/test-environments')) return '环境配置';
      if (path.includes('/knowledge-graph')) return '数据表关系';
      return currentProject ? currentProject.name : '项目详情';
    }
    return '智能AI接口自动化测试';
  };

  // 配置菜单项
  const configMenuItems = [
    {
      key: 'database',
      icon: <DatabaseOutlined />,
      label: '数据源配置',
      onClick: () => {
        if (currentProjectId) {
          navigate(`/projects/${currentProjectId}/database-info`);
        } else {
          message.warning('请先选择一个项目');
        }
      },
    },
    {
      key: 'environment',
      icon: <EnvironmentOutlined />,
      label: '环境配置',
      onClick: () => {
        if (currentProjectId) {
          navigate(`/projects/${currentProjectId}/test-environments`);
        } else {
          message.warning('请先选择一个项目');
        }
      },
    },
    {
      key: 'knowledge',
      icon: <ApartmentOutlined />,
      label: '数据表关系',
      onClick: () => {
        if (currentProjectId) {
          navigate(`/projects/${currentProjectId}/knowledge-graph`);
        } else {
          message.warning('请先选择一个项目');
        }
      },
    },
  ];

  // 用户菜单项
  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人信息',
    },
    {
      type: 'divider',
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
    },
  ];

  const handleUserMenuClick = ({ key }) => {
    if (key === 'logout') {
      localStorage.removeItem('access_token');
      navigate('/login');
    }
  };

  // 左侧菜单项
  const menuItems = [
    {
      key: '/projects',
      icon: <HomeOutlined />,
      label: '首页',
    },
    {
      type: 'divider',
    },
    {
      key: 'projects',
      icon: <ProjectOutlined />,
      label: '项目列表',
      children: projects.map((project) => ({
        key: `/projects/${project.id}`,
        label: project.name,
      })),
    },
  ];

  const handleMenuClick = ({ key }) => {
    if (key.startsWith('/projects/')) {
      navigate(key);
    } else if (key === '/projects') {
      navigate('/projects');
    }
  };

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      {/* 左侧深色菜单 - 参考 uitest */}
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="dark"
        width={220}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            fontSize: collapsed ? 16 : 18,
            fontWeight: 'bold',
          }}
        >
          {collapsed ? 'API' : 'AI接口测试平台'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
        />
        <div style={{ padding: '16px', borderTop: '1px solid rgba(255, 255, 255, 0.1)' }}>
          <Button
            type="text"
            icon={<PlusOutlined />}
            onClick={() => setModalVisible(true)}
            style={{
              width: '100%',
              color: 'rgba(255, 255, 255, 0.65)',
              textAlign: 'left',
            }}
          >
            {collapsed ? '' : '新建项目'}
          </Button>
        </div>
      </Sider>

      <AntLayout>
        {/* 顶部白色 Header - 参考 uitest */}
        <Header
          style={{
            padding: '0 24px',
            background: '#fff',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            boxShadow: '0 1px 4px rgba(0,21,41,.08)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <Title level={4} style={{ margin: 0 }}>
              {getPageTitle()}
            </Title>
            {currentProjectId && (
              <Select
                value={currentProjectId}
                style={{ width: 200 }}
                onChange={(projectId) => {
                  if (projectId) {
                    navigate(`/projects/${projectId}`);
                  } else {
                    navigate('/projects');
                  }
                }}
                dropdownRender={(menu) => (
                  <div>
                    {menu}
                    <div style={{ padding: '8px', borderTop: '1px solid #f0f0f0' }}>
                      <Button
                        type="link"
                        icon={<PlusOutlined />}
                        onClick={() => setModalVisible(true)}
                        style={{ width: '100%', textAlign: 'left' }}
                      >
                        新建项目
                      </Button>
                    </div>
                  </div>
                )}
              >
                {projects.map((project) => (
                  <Select.Option key={project.id} value={project.id}>
                    {project.name}
                  </Select.Option>
                ))}
              </Select>
            )}
            {currentProjectId && (
              <Dropdown menu={{ items: configMenuItems, onClick: ({ key }) => {
                const item = configMenuItems.find(i => i.key === key);
                if (item && item.onClick) item.onClick();
              }}}>
                <Button type="default" style={{ marginLeft: '8px' }}>
                  项目配置
                </Button>
              </Dropdown>
            )}
          </div>
          <Dropdown menu={{ items: userMenuItems, onClick: handleUserMenuClick }}>
            <Space style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} />
              <span>管理员</span>
            </Space>
          </Dropdown>
        </Header>

        {/* 主内容区 - 参考 uitest */}
        <Content className="workflow-layout-container" style={{ margin: '24px 16px', padding: 0 }}>
          {children}
        </Content>
      </AntLayout>

      {/* 创建项目Modal */}
      <Modal
        title={<div style={{ fontSize: '20px', fontWeight: 'bold' }}>创建新项目</div>}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
        width={600}
        styles={{
          body: { padding: '32px' },
        }}
      >
        <Form
          form={form}
          onFinish={handleCreate}
          layout="vertical"
          style={{ marginTop: '16px' }}
        >
          <Form.Item
            name="name"
            label={<span style={{ fontWeight: 500 }}>项目名称</span>}
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input size="large" placeholder="请输入项目名称" />
          </Form.Item>
          <Form.Item
            name="description"
            label={<span style={{ fontWeight: 500 }}>项目描述</span>}
          >
            <Input.TextArea
              rows={4}
              placeholder="请输入项目描述（可选）"
              size="large"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0, marginTop: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <Button onClick={() => setModalVisible(false)}>取消</Button>
              <Button
                type="primary"
                htmlType="submit"
                size="large"
              >
                创建
              </Button>
            </div>
          </Form.Item>
        </Form>
      </Modal>
    </AntLayout>
  );
};

export default Layout;
