import React, { useState, useEffect } from 'react';
import { useParams, Routes, Route, useNavigate, useLocation, Navigate } from 'react-router-dom';
import { Tabs } from 'antd';
import {
  FileTextOutlined,
  DatabaseOutlined,
  ShareAltOutlined,
  CodeOutlined,
  PlayCircleOutlined,
  BarChartOutlined,
  ApartmentOutlined,
  EnvironmentOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import Documents from './Documents';
import Interfaces from './Interfaces';
import TestCases from './TestCases';
import TestTasks from './TestTasks';
import KnowledgeGraph from './KnowledgeGraph';
import DatabaseInfo from './DatabaseInfo';
import ApiDependencies from './ApiDependencies';
import TestEnvironments from './TestEnvironments';
import ScenarioSuites from './ScenarioSuites';
import '../styles/animations.css';

const ProjectDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const getCurrentTabKey = () => {
    const path = location.pathname;
    const match = path.match(/\/projects\/\d+\/(.+)$/);
    return match ? match[1] : 'documents';
  };

  const [activeKey, setActiveKey] = useState(getCurrentTabKey());
  const [contentKey, setContentKey] = useState(0);


  const tabItems = [
    {
      key: 'documents',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <FileTextOutlined />
          文档管理
        </span>
      ),
    },
    {
      key: 'interfaces',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CodeOutlined />
          接口列表
        </span>
      ),
    },
    {
      key: 'database-info',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <DatabaseOutlined />
          数据库信息
        </span>
      ),
    },
    {
      key: 'api-dependencies',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ShareAltOutlined />
          接口依赖分析
        </span>
      ),
    },
    {
      key: 'test-cases',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CodeOutlined />
          测试用例
        </span>
      ),
    },
    {
      key: 'test-environments',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <EnvironmentOutlined />
          测试环境
        </span>
      ),
    },
    {
      key: 'test-tasks',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <PlayCircleOutlined />
          测试任务
        </span>
      ),
    },
    {
      key: 'knowledge-graph',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ApartmentOutlined />
          知识图谱
        </span>
      ),
    },
    {
      key: 'scenario-suites',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <UnorderedListOutlined />
          小场景用例集
        </span>
      ),
    },
  ];

  useEffect(() => {
    const currentKey = getCurrentTabKey();
    setActiveKey(currentKey);
    setContentKey((prev) => prev + 1);
  }, [location.pathname]);

  const handleTabChange = (key) => {
    setActiveKey(key);
    // 使用绝对路径，避免URL累加
    navigate(`/projects/${id}/${key}`, { replace: true });
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div
        style={{
          padding: '24px 32px 0',
          background: 'linear-gradient(180deg, #f8f9fa 0%, transparent 100%)',
          borderBottom: '1px solid #f0f0f0',
        }}
        className="fade-in"
      >
        <Tabs
          activeKey={activeKey}
          items={tabItems}
          onChange={handleTabChange}
          style={{
            marginBottom: 0,
          }}
          tabBarStyle={{
            marginBottom: 0,
            borderBottom: 'none',
          }}
        />
      </div>
      <div
        key={contentKey}
        style={{
          flex: 1,
          padding: '24px 32px',
          overflow: 'auto',
          background: '#ffffff',
        }}
        className="fade-in scale-in"
      >
        <Routes>
          <Route index element={<Navigate to="documents" replace />} />
          <Route path="documents" element={<Documents />} />
          <Route path="interfaces" element={<Interfaces />} />
          <Route path="database-info" element={<DatabaseInfo />} />
          <Route path="api-dependencies" element={<ApiDependencies />} />
          <Route path="test-cases" element={<TestCases />} />
          <Route path="test-environments" element={<TestEnvironments />} />
          <Route path="test-tasks" element={<TestTasks />} />
          <Route path="knowledge-graph" element={<KnowledgeGraph />} />
          <Route path="scenario-suites" element={<ScenarioSuites />} />
        </Routes>
      </div>
    </div>
  );
};

export default ProjectDetail;


