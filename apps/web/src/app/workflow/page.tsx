'use client';

import { useState, useEffect } from 'react';
import {
  Activity,
  Play,
  Pause,
  RotateCcw,
  Trash2,
  Plus,
} from 'lucide-react';
import Layout from '../../components/Layout';
import { workflowApi } from '../../lib/api';

export default function WorkflowPage() {
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchWorkflows();
  }, []);

  const fetchWorkflows = async () => {
    setLoading(true);
    try {
      const mockWorkflows = [
        {
          id: 'wf-001',
          name: '测试用例生成流程',
          description: '基于AI的测试用例自动生成',
          status: 'running',
          created_at: '2026-07-20 10:30',
          tasks: 5,
          completed_tasks: 3,
        },
        {
          id: 'wf-002',
          name: '质量报告生成',
          description: '自动化测试报告生成与分析',
          status: 'completed',
          created_at: '2026-07-19 14:20',
          tasks: 3,
          completed_tasks: 3,
        },
        {
          id: 'wf-003',
          name: '回归测试套件',
          description: '全量回归测试执行',
          status: 'pending',
          created_at: '2026-07-20 16:00',
          tasks: 10,
          completed_tasks: 0,
        },
      ];
      setWorkflows(mockWorkflows);
    } catch (error) {
      console.error('Failed to fetch workflows:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleExecute = async (workflowId: string) => {
    try {
      await workflowApi.execute(workflowId);
      fetchWorkflows();
    } catch (error) {
      console.error('Failed to execute workflow:', error);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'bg-green-100 text-green-700';
      case 'completed':
        return 'bg-blue-100 text-blue-700';
      case 'pending':
        return 'bg-yellow-100 text-yellow-700';
      default:
        return 'bg-gray-100 text-gray-700';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'running':
        return '运行中';
      case 'completed':
        return '已完成';
      case 'pending':
        return '待执行';
      default:
        return status;
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">工作流列表</h3>
          <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
            <Plus className="w-4 h-4" />
            <span>创建工作流</span>
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {workflows.map((workflow) => (
              <div key={workflow.id} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h4 className="font-semibold text-gray-900">{workflow.name}</h4>
                    <p className="text-sm text-gray-500 mt-1">{workflow.description}</p>
                  </div>
                  <span className={`px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(workflow.status)}`}>
                    {getStatusText(workflow.status)}
                  </span>
                </div>

                <div className="mb-4">
                  <div className="flex items-center justify-between text-sm mb-2">
                    <span className="text-gray-500">进度</span>
                    <span className="text-gray-900">{workflow.completed_tasks}/{workflow.tasks}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full transition-all"
                      style={{ width: `${(workflow.completed_tasks / workflow.tasks) * 100}%` }}
                    ></div>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs text-gray-500 mb-4">
                  <span>ID: {workflow.id}</span>
                  <span>{workflow.created_at}</span>
                </div>

                <div className="flex items-center gap-2">
                  {workflow.status === 'running' && (
                    <button className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-yellow-100 text-yellow-700 rounded-lg hover:bg-yellow-200 transition-colors">
                      <Pause className="w-4 h-4" />
                      <span>暂停</span>
                    </button>
                  )}
                  {workflow.status === 'pending' && (
                    <button
                      onClick={() => handleExecute(workflow.id)}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
                    >
                      <Play className="w-4 h-4" />
                      <span>执行</span>
                    </button>
                  )}
                  {workflow.status === 'completed' && (
                    <button className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                      <RotateCcw className="w-4 h-4" />
                      <span>重试</span>
                    </button>
                  )}
                  <button className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}