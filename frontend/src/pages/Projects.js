import React from 'react';
import { Card, Row, Col, Typography } from 'antd';
import {
  FileTextOutlined,
  DatabaseOutlined,
  ShareAltOutlined,
  CodeOutlined,
  PlayCircleOutlined,
  BarChartOutlined,
  ApartmentOutlined,
  MonitorOutlined,
  RocketOutlined,
  BulbOutlined,
  ThunderboltOutlined,
  SafetyOutlined,
} from '@ant-design/icons';
import '../styles/animations.css';

const { Title, Paragraph } = Typography;

const Projects = () => {
  const features = [
    {
      icon: <FileTextOutlined />,
      title: '智能文档解析',
      description: '支持PDF、Word、图片等多种格式，自动提取API接口信息，智能识别接口参数和响应结构',
      color: '#667eea',
    },
    {
      icon: <DatabaseOutlined />,
      title: '数据库连接',
      description: '快速连接数据库，自动分析表结构，提取业务数据关系，为测试用例生成提供数据支持',
      color: '#764ba2',
    },
    {
      icon: <ShareAltOutlined />,
      title: '接口依赖分析',
      description: '智能分析API接口之间的依赖关系，构建完整的接口调用链路，自动识别依赖顺序',
      color: '#f093fb',
    },
    {
      icon: <CodeOutlined />,
      title: '智能用例生成',
      description: '基于AI大模型自动生成测试用例，支持正常流程和异常场景，覆盖边界值测试',
      color: '#4facfe',
    },
    {
      icon: <PlayCircleOutlined />,
      title: '自动化测试执行',
      description: '一键执行测试任务，支持批量测试、定时执行，实时监控测试进度和结果',
      color: '#43e97b',
    },
    {
      icon: <BarChartOutlined />,
      title: '测试结果分析',
      description: '可视化测试报告，详细分析测试结果，提供趋势分析和性能指标统计',
      color: '#fa709a',
    },
    {
      icon: <ApartmentOutlined />,
      title: '知识图谱',
      description: '构建API知识图谱，可视化接口关系，支持智能检索和关联分析',
      color: '#fee140',
    },
    {
      icon: <MonitorOutlined />,
      title: '依赖监控',
      description: '实时监控API变更，自动检测接口变化，智能更新测试用例，保障测试质量',
      color: '#30cfd0',
    },
  ];

  const highlights = [
    {
      icon: <RocketOutlined />,
      title: 'AI驱动',
      description: '基于通义千问大模型，智能理解和分析API文档',
    },
    {
      icon: <ThunderboltOutlined />,
      title: '高效自动化',
      description: '从文档解析到用例生成，全流程自动化，提升测试效率',
    },
    {
      icon: <SafetyOutlined />,
      title: '质量保障',
      description: '智能依赖分析和变更监控，确保测试用例的准确性和时效性',
    },
    {
      icon: <BulbOutlined />,
      title: '智能推荐',
      description: '基于知识图谱和向量检索，智能推荐相关接口和测试场景',
    },
  ];

  return (
    <div style={{ padding: '48px 64px', height: '100%', overflow: 'auto' }}>
      {/* 欢迎区域 */}
      <div style={{ textAlign: 'center', marginBottom: '64px' }} className="fade-in">
        <div
          style={{
            fontSize: '48px',
            fontWeight: 'bold',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            marginBottom: '16px',
          }}
        >
          智能AI接口自动化测试平台
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
          基于AI大模型的智能接口测试平台，支持文档解析、用例生成、自动化执行和结果分析，
          让API测试变得简单高效
        </Paragraph>
      </div>

      {/* 核心亮点 */}
      <div style={{ marginBottom: '64px' }}>
        <Title level={2} style={{ textAlign: 'center', marginBottom: '40px' }}>
          核心亮点
        </Title>
        <Row gutter={[24, 24]}>
          {highlights.map((item, index) => (
            <Col xs={24} sm={12} md={6} key={index}>
              <Card
                style={{
                  textAlign: 'center',
                  borderRadius: '12px',
                  height: '100%',
                  border: 'none',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06)',
                  animationDelay: `${index * 0.1}s`,
                }}
                className="card-shadow hover-lift fade-in"
              >
                <div
                  style={{
                    fontSize: '48px',
                    color: '#667eea',
                    marginBottom: '16px',
                  }}
                >
                  {item.icon}
                </div>
                <Title level={4} style={{ marginBottom: '8px' }}>
                  {item.title}
                </Title>
                <Paragraph style={{ color: '#8c8c8c', margin: 0 }}>
                  {item.description}
                </Paragraph>
              </Card>
            </Col>
          ))}
        </Row>
      </div>

      {/* 功能特性 */}
      <div>
        <Title level={2} style={{ textAlign: 'center', marginBottom: '40px' }}>
          功能特性
        </Title>
        <Row gutter={[24, 24]}>
          {features.map((feature, index) => (
            <Col xs={24} sm={12} md={6} key={index}>
              <Card
                style={{
                  borderRadius: '12px',
                  height: '100%',
                  border: '1px solid #f0f0f0',
                  transition: 'all 0.3s ease',
                  animationDelay: `${index * 0.1}s`,
                }}
                className="card-shadow hover-lift fade-in"
                bodyStyle={{ padding: '24px' }}
              >
                <div
                  style={{
                    fontSize: '40px',
                    color: feature.color,
                    marginBottom: '16px',
                    display: 'inline-block',
                  }}
                >
                  {feature.icon}
                </div>
                <Title level={4} style={{ marginBottom: '12px', fontSize: '18px' }}>
                  {feature.title}
                </Title>
                <Paragraph
                  style={{
                    color: '#8c8c8c',
                    margin: 0,
                    lineHeight: '1.6',
                    fontSize: '14px',
                  }}
                >
                  {feature.description}
                </Paragraph>
              </Card>
            </Col>
          ))}
        </Row>
      </div>

      {/* 底部说明 */}
      <div
        style={{
          textAlign: 'center',
          marginTop: '64px',
          padding: '32px',
          background: 'linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%)',
          borderRadius: '12px',
        }}
        className="fade-in"
      >
        <Paragraph
          style={{
            fontSize: '16px',
            color: '#595959',
            margin: 0,
            lineHeight: '1.8',
          }}
        >
          请在左侧侧边栏中选择或创建项目，开始使用智能AI接口自动化测试功能
        </Paragraph>
      </div>
    </div>
  );
};

export default Projects;




