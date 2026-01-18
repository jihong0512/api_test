import React, { useState, useEffect } from 'react';
import { useParams, Routes, Route, useNavigate, useLocation, Navigate } from 'react-router-dom';
import {
  BookFilled,
  BranchesOutlined,
  ApiFilled,
  ThunderboltFilled,
  AppstoreFilled,
} from '@ant-design/icons';
import Documents from './Documents';
import Interfaces from './Interfaces';
import TestCases from './TestCases';
import TestTasks from './TestTasks';
import ApiDependencies from './ApiDependencies';
import ScenarioSuites from './ScenarioSuites';
import DatabaseInfo from './DatabaseInfo';
import TestEnvironments from './TestEnvironments';
import KnowledgeGraph from './KnowledgeGraph';
import '../styles/animations.css';
import '../styles/workflow-layout.css';

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

  // 6个核心流程步骤
  const workflowSteps = [
    {
      key: 'documents',
      icon: '📚',
      title: '接口文档库',
      description: '上传和管理API文档',
      component: BookFilled,
      color: '#667eea', // 紫色
    },
    {
      key: 'interfaces',
      icon: '🔗',
      title: '接口管理',
      description: '查看和管理所有接口',
      component: ApiFilled,
      color: '#48bb78', // 绿色
    },
    {
      key: 'api-dependencies',
      icon: '🌐',
      title: '接口依赖图',
      description: '分析接口依赖关系',
      component: BranchesOutlined,
      color: '#ed8936', // 橙色
    },
    {
      key: 'test-cases',
      icon: '📋',
      title: '用例库',
      description: '管理和查看测试用例',
      component: ApiFilled,
      color: '#4299e1', // 蓝色
    },
    {
      key: 'test-tasks',
      icon: '⚡',
      title: '执行任务',
      description: '执行测试任务并查看结果',
      component: ThunderboltFilled,
      color: '#f56565', // 红色
    },
    {
      key: 'scenario-suites',
      icon: '📦',
      title: '场景组合',
      description: '管理场景用例集',
      component: AppstoreFilled,
      color: '#9f7aea', // 紫罗兰色
    },
  ];

  const getStepStatus = (stepKey) => {
    const currentIndex = workflowSteps.findIndex(step => step.key === activeKey);
    const stepIndex = workflowSteps.findIndex(step => step.key === stepKey);
    
    if (stepIndex < currentIndex) return 'completed';
    if (stepIndex === currentIndex) return 'active';
    return 'pending';
  };

  useEffect(() => {
    const currentKey = getCurrentTabKey();
    setActiveKey(currentKey);
    setContentKey((prev) => prev + 1);
  }, [location.pathname]);

  const handleStepClick = (key) => {
    setActiveKey(key);
    navigate(`/projects/${id}/${key}`, { replace: true });
  };

  return (
    <>
      {/* 流程步骤导航 */}
      <div className="workflow-steps">
        {workflowSteps.map((step, index) => {
          const status = getStepStatus(step.key);
          const IconComponent = step.component;
          
          return (
            <div
              key={step.key}
              className={`workflow-step step-${status}`}
              onClick={() => handleStepClick(step.key)}
              style={{ '--step-color': step.color }}
            >
              <div className="step-icon-wrapper" style={{ background: `linear-gradient(135deg, ${step.color} 0%, ${step.color}dd 100%)` }}>
                <IconComponent style={{ fontSize: '28px', color: 'white' }} />
              </div>
              <div className="step-title">{step.title}</div>
              <div className="step-description">{step.description}</div>
              {index < workflowSteps.length - 1 && (
                <div 
                  className="step-arrow" 
                  style={{ 
                    borderLeftColor: workflowSteps[index + 1]?.color || step.color 
                  }}
                ></div>
              )}
            </div>
          );
        })}
      </div>

      {/* 内容区 */}
      <div className="workflow-content">
        <Routes>
          <Route index element={<Navigate to="documents" replace />} />
          <Route path="documents" element={<Documents />} />
          <Route path="interfaces" element={<Interfaces />} />
          <Route path="api-dependencies" element={<ApiDependencies />} />
          <Route path="test-cases" element={<TestCases />} />
          <Route path="test-tasks" element={<TestTasks />} />
          <Route path="scenario-suites" element={<ScenarioSuites />} />
          {/* 配置类功能通过测试项目配置菜单访问 */}
          <Route path="database-info" element={<DatabaseInfo />} />
          <Route path="test-environments" element={<TestEnvironments />} />
          <Route path="knowledge-graph" element={<KnowledgeGraph />} />
        </Routes>
      </div>
    </>
  );
};

export default ProjectDetail;
