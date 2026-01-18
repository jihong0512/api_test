import React from 'react';
import { Card, Row, Col, Typography } from 'antd';
import {
  BookFilled,
  DatabaseFilled,
  BranchesOutlined,
  ApiFilled,
  ThunderboltFilled,
  BarChartOutlined,
  ApartmentOutlined,
  MonitorOutlined,
  RocketFilled,
  BulbFilled,
  ThunderboltOutlined,
  SafetyCertificateFilled,
} from '@ant-design/icons';
import '../styles/animations.css';
import '../styles/projects-cool.css';

const { Title, Paragraph } = Typography;

const Projects = () => {
  const features = [
    {
      icon: <BookFilled />,
      title: '接口文档库',
      description: '支持PDF、Word、图片等多种格式，自动提取接口信息，智能识别接口参数和响应结构',
      gradient: 'linear-gradient(135deg, #8360c3 0%, #2ebf91 100%)',
    },
    {
      icon: <BranchesOutlined />,
      title: '接口依赖图',
      description: '智能分析接口之间的依赖关系，构建完整的接口调用链路，自动识别依赖顺序',
      gradient: 'linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%)',
    },
    {
      icon: <ApiFilled />,
      title: '用例库',
      description: '基于AI大模型自动生成用例，支持正常流程和异常场景，覆盖边界值测试',
      gradient: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
    },
    {
      icon: <ThunderboltFilled />,
      title: '执行任务',
      description: '一键执行任务，支持批量执行、定时调度，实时监控执行进度和结果',
      gradient: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
    },
    {
      icon: <BarChartOutlined />,
      title: '结果分析',
      description: '可视化执行报告，详细分析执行结果，提供趋势分析和性能指标统计',
      gradient: 'linear-gradient(135deg, #fa8bff 0%, #2bd2ff 50%, #2bff88 100%)',
    },
    {
      icon: <DatabaseFilled />,
      title: '数据源配置',
      description: '快速连接数据库，自动分析表结构，提取业务数据关系，为用例库生成提供数据支持',
      gradient: 'linear-gradient(135deg, #a855f7 0%, #3b82f6 100%)',
    },
    {
      icon: <ApartmentOutlined />,
      title: '数据表关系',
      description: '构建数据表关系图谱，可视化表间关系，支持智能检索和关联分析',
      gradient: 'linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%)',
    },
    {
      icon: <MonitorOutlined />,
      title: '变更监控',
      description: '实时监控接口变更，自动检测接口变化，智能更新用例库，保障测试质量',
      gradient: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)',
    },
  ];

  const highlights = [
    {
      icon: <RocketFilled />,
      title: 'AI智能',
      description: '基于AI大模型，智能理解和分析接口文档',
      gradient: 'linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%)',
    },
    {
      icon: <ThunderboltOutlined />,
      title: '自动化流程',
      description: '从文档解析到用例生成，全流程自动化，提升测试效率',
      gradient: 'linear-gradient(135deg, #10b981 0%, #06b6d4 100%)',
    },
    {
      icon: <SafetyCertificateFilled />,
      title: '质量保障',
      description: '智能依赖分析和变更监控，确保用例库的准确性和时效性',
      gradient: 'linear-gradient(135deg, #f59e0b 0%, #ef4444 100%)',
    },
    {
      icon: <BulbFilled />,
      title: '智能推荐',
      description: '基于数据表关系和向量检索，智能推荐相关接口和测试场景',
      gradient: 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)',
    },
  ];

  return (
    <div className="projects-cool-container" style={{ padding: '48px 64px', height: '100%', overflow: 'auto' }}>
      {/* 欢迎区域 */}
      <div style={{ textAlign: 'center', marginBottom: '64px' }} className="fade-in">
        <div className="projects-main-title">
          AI接口测试平台
        </div>
        <Paragraph
          style={{
            fontSize: '18px',
            color: '#8c8c8c',
            maxWidth: '800px',
            margin: '0 auto',
            lineHeight: '1.8',
          }}
        >
          基于AI大模型的接口测试平台，支持接口文档库管理、用例库生成、执行任务调度和结果分析，
          让接口测试更加高效便捷
        </Paragraph>
      </div>

      {/* 核心亮点 */}
      <div style={{ marginBottom: '64px' }}>
        <Title level={2} className="section-title">核心亮点</Title>
        <Row gutter={[24, 24]}>
          {highlights.map((item, index) => (
            <Col xs={24} sm={12} md={6} key={index}>
              <Card
                className="highlight-card fade-in"
                style={{
                  textAlign: 'center',
                  borderRadius: '16px',
                  height: '100%',
                  border: 'none',
                  background: 'linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%)',
                  animationDelay: `${index * 0.1}s`,
                }}
              >
                <div
                  className="highlight-icon"
                  style={{
                    fontSize: '56px',
                    marginBottom: '20px',
                    background: item.gradient,
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    backgroundClip: 'text',
                    display: 'inline-block',
                    animation: 'float 3s ease-in-out infinite',
                    animationDelay: `${index * 0.2}s`,
                  }}
                >
                  {item.icon}
                </div>
                <Title level={4} className="highlight-title">{item.title}</Title>
                <Paragraph className="highlight-description">{item.description}</Paragraph>
              </Card>
            </Col>
          ))}
        </Row>
      </div>

      {/* 功能特性 */}
      <div>
        <Title level={2} className="section-title">功能特性</Title>
        <Row gutter={[24, 24]}>
          {features.map((feature, index) => (
            <Col xs={24} sm={12} md={6} key={index}>
              <Card
                className="feature-card fade-in"
                style={{
                  borderRadius: '16px',
                  height: '100%',
                  border: 'none',
                  background: 'linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%)',
                  animationDelay: `${index * 0.1}s`,
                  position: 'relative',
                  overflow: 'hidden',
                }}
                bodyStyle={{ padding: '28px', position: 'relative', zIndex: 1 }}
              >
                <div
                  className="feature-icon-wrapper"
                  style={{
                    position: 'relative',
                    display: 'inline-block',
                    marginBottom: '20px',
                  }}
                >
                  <div
                    className="feature-icon-bg"
                    style={{
                      position: 'absolute',
                      width: '80px',
                      height: '80px',
                      borderRadius: '20px',
                      background: feature.gradient,
                      opacity: 0.1,
                      top: '50%',
                      left: '50%',
                      transform: 'translate(-50%, -50%)',
                      animation: 'pulse 2s ease-in-out infinite',
                    }}
                  />
                  <div
                    className="feature-icon"
                    style={{
                      fontSize: '48px',
                      background: feature.gradient,
                      WebkitBackgroundClip: 'text',
                      WebkitTextFillColor: 'transparent',
                      backgroundClip: 'text',
                      position: 'relative',
                      zIndex: 1,
                    }}
                  >
                    {feature.icon}
                  </div>
                </div>
                <Title level={4} className="feature-title">{feature.title}</Title>
                <Paragraph className="feature-description">{feature.description}</Paragraph>
              </Card>
            </Col>
          ))}
        </Row>
      </div>

      {/* 底部说明 */}
      <div className="projects-footer fade-in">
        <Paragraph className="footer-text">
          请在左侧侧边栏中选择或创建项目，开始使用AI接口测试平台功能
        </Paragraph>
      </div>
    </div>
  );
};

export default Projects;




