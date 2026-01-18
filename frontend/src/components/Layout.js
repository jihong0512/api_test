import React, { useState, useEffect } from 'react';
import { Layout as AntLayout, Menu, Dropdown, Avatar, Space, Badge, Button, Modal, Form, Input, message } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  ProjectOutlined,
  UserOutlined,
  RocketOutlined,
  PlusOutlined,
  HomeOutlined,
} from '@ant-design/icons';
// import { useAuthStore } from '../store/authStore'; // 已禁用登录功能
import client from '../api/client';
import { getErrorMessage } from '../utils/errorHandler';
import '../styles/animations.css';

const { Header, Content, Sider } = AntLayout;

const Layout = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  // const { user, logout } = useAuthStore(); // 已禁用登录功能
  const user = { username: '用户' }; // 默认用户显示
  const [headerScrolled, setHeaderScrolled] = useState(false);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    const handleScroll = () => {
      setHeaderScrolled(window.scrollY > 10);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    fetchProjects();
  }, []);

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

  const handleCreate = async (values) => {
    try {
      const response = await client.post('/api/workspaces/', values);
      message.success('项目创建成功');
      setModalVisible(false);
      form.resetFields();
      await fetchProjects();
      // 创建成功后跳转到项目详情页
      if (response && response.id) {
        navigate(`/projects/${response.id}`);
      }
    } catch (error) {
      message.error('项目创建失败: ' + getErrorMessage(error));
    }
  };

  // 项目删除功能已禁用
  // const handleDeleteProject = async (projectId, e) => {
  //   if (e && e.stopPropagation) {
  //     e.stopPropagation();
  //   }
  //   try {
  //     await client.delete(`/api/workspaces/${projectId}`);
  //     message.success('项目删除成功');
  //     await fetchProjects();
  //     // 如果删除的是当前项目，跳转到首页
  //     if (location.pathname.startsWith(`/projects/${projectId}`)) {
  //       navigate('/projects');
  //     }
  //   } catch (error) {
  //     message.error('删除项目失败: ' + getErrorMessage(error));
  //   }
  // };

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
      key: 'projects-header',
      label: (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0' }}>
          <span style={{ fontWeight: 'bold', color: '#595959' }}>项目列表</span>
          <Button
            type="text"
            size="small"
            icon={<PlusOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              setModalVisible(true);
            }}
            style={{ color: '#667eea' }}
          />
        </div>
      ),
      disabled: true,
    },
    ...projects.map((project) => ({
      key: `/projects/${project.id}`,
      icon: <ProjectOutlined />,
      label: project.name,
    })),
  ];

  const handleMenuClick = ({ key }) => {
    if (key === '/projects') {
      navigate('/projects');
    } else if (key.startsWith('/projects/')) {
      navigate(key);
    }
  };

  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人信息',
    },
  ];

  const headerStyle = {
    background: headerScrolled
      ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
      : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    padding: '0 32px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    position: 'sticky',
    top: 0,
    zIndex: 1000,
    boxShadow: headerScrolled ? '0 4px 20px rgba(0, 0, 0, 0.15)' : 'none',
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    height: '64px',
  };

  const titleStyle = {
    color: 'white',
    fontSize: '22px',
    fontWeight: 'bold',
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    textShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
    letterSpacing: '0.5px',
  };

  const siderStyle = {
    background: 'linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%)',
    boxShadow: '2px 0 8px rgba(0, 0, 0, 0.05)',
    height: '100vh',
    position: 'sticky',
    top: 64,
  };

  return (
    <AntLayout style={{ minHeight: '100vh', background: '#f5f7fa' }}>
      <Header style={headerStyle} className="fade-in">
        <div style={titleStyle}>
          <RocketOutlined style={{ fontSize: '24px', animation: 'pulse 2s ease-in-out infinite' }} />
          <span>智能AI接口自动化测试</span>
        </div>
        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
          <Space
            style={{
              cursor: 'pointer',
              color: 'white',
              padding: '8px 16px',
              borderRadius: '20px',
              background: 'rgba(255, 255, 255, 0.15)',
              transition: 'all 0.3s ease',
            }}
            className="hover-lift"
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.25)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.15)';
            }}
          >
            <Avatar
              icon={<UserOutlined />}
              style={{
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                border: '2px solid rgba(255, 255, 255, 0.3)',
              }}
            />
            <span style={{ fontWeight: 500 }}>{user?.username || '用户'}</span>
          </Space>
        </Dropdown>
      </Header>
      <AntLayout>
        <Sider width={280} style={siderStyle} className="slide-in-left">
          <Menu
            mode="inline"
            selectedKeys={[
              location.pathname === '/projects'
                ? '/projects'
                : location.pathname.startsWith('/projects/')
                ? location.pathname
                : location.pathname.split('/').slice(0, 2).join('/'),
            ]}
            items={menuItems}
            onClick={handleMenuClick}
            style={{
              height: '100%',
              borderRight: 0,
              background: 'transparent',
              padding: '16px 8px',
            }}
            className="smooth-transition"
          />
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
                <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
                  <Button onClick={() => setModalVisible(false)}>取消</Button>
                  <Button
                    type="primary"
                    htmlType="submit"
                    size="large"
                    style={{
                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                      border: 'none',
                    }}
                  >
                    创建
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          </Modal>
        </Sider>
        <AntLayout style={{ padding: '24px', minHeight: 'calc(100vh - 64px)', background: '#f5f7fa' }}>
          <Content
            style={{
              background: 'linear-gradient(180deg, #ffffff 0%, #fafbfc 100%)',
              padding: 0,
              borderRadius: '12px',
              boxShadow: '0 2px 12px rgba(0, 0, 0, 0.08)',
              minHeight: 280,
              overflow: 'hidden',
            }}
            className="slide-in-right fade-in"
          >
            {children}
          </Content>
        </AntLayout>
      </AntLayout>
    </AntLayout>
  );
};

export default Layout;




