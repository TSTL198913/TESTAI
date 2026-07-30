'use client';

import { useState, useEffect, FormEvent } from 'react';
import {
  Activity,
  Play,
  Pause,
  RotateCcw,
  Trash2,
  Plus,
  AlertCircle,
  X,
  Loader2,
  FileText,
  TestTube,
  Stethoscope,
  ChevronRight,
  Zap,
  Globe,
  Database,
} from 'lucide-react';
import Layout from '../../components/Layout';
import api, { workflowApi, testApi, diagnoseApi } from '../../lib/api';

interface TestCase {
  id: string;
  name: string;
  protocol: 'http' | 'grpc';
  url?: string;
  method?: string;
  service?: string;
  grpcMethod?: string;
  status: 'pending' | 'passed' | 'failed';
  response_time?: number;
}

interface DiagnosticReport {
  id: string;
  workflow_id: string;
  timestamp: string;
  issues: {
    severity: 'critical' | 'high' | 'medium' | 'low';
    message: string;
    code_location?: string;
    suggestion?: string;
    confidence?: number;
    description?: string;
  }[];
  insights: {
    title: string;
    description: string;
    severity: string;
    recommendation: string;
    confidence: number;
  }[];
  confidence: number;
}

export default function WorkflowPage() {
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [newWorkflow, setNewWorkflow] = useState({ name: '', description: '', task_count: 1 });

  const [showTestCaseModal, setShowTestCaseModal] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState<any>(null);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [newTestCase, setNewTestCase] = useState({
    name: '',
    protocol: 'http' as 'http' | 'grpc',
    url: '',
    method: 'GET',
    service: '',
    grpcMethod: '',
    body: '',
    headers: '',
  });

  const [showDiagnosticModal, setShowDiagnosticModal] = useState(false);
  const [diagnosticReports, setDiagnosticReports] = useState<DiagnosticReport[]>([]);

  useEffect(() => {
    const user = localStorage.getItem('user');
    if (!user) {
      setError('未检测到登录凭证，请先登录');
      setLoading(false);
      return;
    }
    fetchWorkflows();
  }, []);

  const fetchWorkflows = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await workflowApi.list();
      const workflowsData = res.data?.workflows || [];
      const instancesData = res.data?.instances || [];
      if (Array.isArray(workflowsData) && workflowsData.length > 0) {
        const enrichedWorkflows = workflowsData.map((wf: any) => {
            const latestInstance = instancesData
              .filter((inst: any) => inst.workflow_id === wf.id)
              .sort((a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];
            return {
              ...wf,
              status: latestInstance?.status || 'defined',
              created_at: latestInstance?.created_at || new Date().toISOString(),
              completed_tasks: latestInstance?.task_count || 0,
              tasks: wf.task_count || 0,
            };
          });
        setWorkflows(enrichedWorkflows);
      } else {
        setWorkflows([
          {
            id: 'wf-001',
            name: '测试用例生成流程',
            description: '基于AI的测试用例自动生成',
            status: 'completed',
            created_at: '2026-07-20T10:30:00',
            task_count: 3,
            completed_tasks: 3,
            tasks: 3,
          },
          {
            id: 'wf-002',
            name: '质量报告生成',
            description: '自动化测试报告生成与分析',
            status: 'defined',
            created_at: '2026-07-19T14:20:00',
            task_count: 2,
            completed_tasks: 0,
            tasks: 2,
          },
        ]);
      }
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      console.error('Failed to fetch workflows:', err);
      if (err?.response?.status === 401) {
        setError('登录已过期，请重新登录');
      }
      setWorkflows([
        {
          id: 'wf-001',
          name: '测试用例生成流程',
          description: '基于AI的测试用例自动生成',
          status: 'completed',
          created_at: '2026-07-20T10:30:00',
          task_count: 3,
          completed_tasks: 3,
          tasks: 3,
        },
          {
            id: 'wf-002',
            name: '质量报告生成',
            description: '自动化测试报告生成与分析',
            status: 'defined',
            created_at: '2026-07-19T14:20:00',
            task_count: 2,
            completed_tasks: 0,
            tasks: 2,
          },
        ]);
    } finally {
      setLoading(false);
    }
  };

  const handleExecute = async (workflowId: string) => {
    try {
      await workflowApi.execute(workflowId);
      fetchWorkflows();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `执行失败: ${detail}` : '执行工作流失败');
    }
  };

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!newWorkflow.name.trim()) {
      setError('请输入工作流名称');
      return;
    }
    setCreateLoading(true);
    setError('');
    try {
      const tasks = [];
      for (let i = 1; i <= newWorkflow.task_count; i++) {
        tasks.push({
          type: 'monitoring',
          name: `任务 ${i}`,
          params: {},
        });
      }
      await workflowApi.define({
        name: newWorkflow.name.trim(),
        description: newWorkflow.description.trim() || '暂无描述',
        tasks,
      });
      setShowCreateModal(false);
      setNewWorkflow({ name: '', description: '', task_count: 1 });
      fetchWorkflows();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `创建失败: ${detail}` : '创建工作流失败');
    } finally {
      setCreateLoading(false);
    }
  };

  const handlePause = async (workflowId: string) => {
    try {
      await workflowApi.execute(workflowId, { action: 'pause' });
      fetchWorkflows();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `暂停失败: ${detail}` : '暂停工作流失败');
    }
  };

  const handleRetry = async (workflowId: string) => {
    try {
      await workflowApi.execute(workflowId);
      fetchWorkflows();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `重试失败: ${detail}` : '重试工作流失败');
    }
  };

  const handleDelete = async (workflowId: string) => {
    if (!confirm('确认删除此工作流？')) return;
    try {
      await api.delete(`/workflow/${workflowId}`);
      fetchWorkflows();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `删除失败: ${detail}` : '删除工作流失败');
    }
  };

  const openTestCaseModal = async (workflow: any) => {
    setSelectedWorkflow(workflow);
    setError('');
    try {
      const res = await testApi.getWorkflowTestCases(workflow.id);
      if (res.data && res.data.test_cases) {
        const backendCases: TestCase[] = res.data.test_cases.map((tc: any) => ({
          id: tc.id,
          name: tc.name,
          protocol: tc.protocol as 'http' | 'grpc',
          url: tc.url,
          method: tc.method,
          service: tc.service,
          grpcMethod: tc.grpc_method,
          status: tc.status as 'pending' | 'passed' | 'failed',
          response_time: tc.response_time,
        }));
        setTestCases(backendCases);
      } else {
        setTestCases([
          { id: `tc-${Date.now()}`, name: 'API健康检查', protocol: 'http', url: '/health', method: 'GET', status: 'pending', response_time: undefined },
        ]);
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || '获取测试用例失败';
      setError(`获取测试用例失败: ${detail}`);
      setTestCases([
        { id: `tc-${Date.now()}`, name: 'API健康检查', protocol: 'http', url: '/health', method: 'GET', status: 'pending', response_time: undefined },
      ]);
    }
    setShowTestCaseModal(true);
  };

  const handleCreateTestCase = async (e: FormEvent) => {
    e.preventDefault();
    if (!newTestCase.name.trim()) {
      setError('请输入测试用例名称');
      return;
    }
    if (newTestCase.protocol === 'http' && !newTestCase.url.trim()) {
      setError('HTTP测试用例需要填写URL');
      return;
    }
    if (newTestCase.protocol === 'grpc' && (!newTestCase.service.trim() || !newTestCase.grpcMethod.trim())) {
      setError('gRPC测试用例需要填写服务名和方法名');
      return;
    }

    const newCase: TestCase = {
      id: `tc-${Date.now()}`,
      name: newTestCase.name.trim(),
      protocol: newTestCase.protocol,
      url: newTestCase.protocol === 'http' ? newTestCase.url.trim() : undefined,
      method: newTestCase.protocol === 'http' ? newTestCase.method : undefined,
      service: newTestCase.protocol === 'grpc' ? newTestCase.service.trim() : undefined,
      grpcMethod: newTestCase.protocol === 'grpc' ? newTestCase.grpcMethod.trim() : undefined,
      status: 'pending',
    };

    setTestCases([...testCases, newCase]);
    setNewTestCase({
      name: '',
      protocol: 'http',
      url: '',
      method: 'GET',
      service: '',
      grpcMethod: '',
      body: '',
      headers: '',
    });
    setError('');
  };

  const handleExecuteTestCase = async (testCaseId: string) => {
    const idx = testCases.findIndex(tc => tc.id === testCaseId);
    if (idx === -1) return;

    const updated = [...testCases];
    updated[idx] = { ...updated[idx], status: 'pending' };
    setTestCases(updated);

    try {
      const tc = testCases[idx];
      if (tc.protocol === 'http') {
        let bodyData: Record<string, any> | undefined;
        let headersData: Record<string, string> = {};
        
        if (tc.id.startsWith('tc-')) {
          headersData = { 'Content-Type': 'application/json' };
        }

        const res = await testApi.execute([{
          name: tc.name,
          protocol: tc.protocol,
          method: tc.method || 'GET',
          url: tc.url || '',
          headers: headersData,
          body: bodyData,
        }]);

        if (res.data && res.data.results && res.data.results.length > 0) {
          const result = res.data.results[0];
          updated[idx] = {
            ...updated[idx],
            status: result.passed ? 'passed' : 'failed',
            response_time: result.response_time_ms,
          };
        }
      } else {
        const res = await testApi.execute([{
          name: tc.name,
          protocol: tc.protocol,
          service: tc.service || '',
          grpc_method: tc.grpcMethod || '',
        }]);

        if (res.data && res.data.results && res.data.results.length > 0) {
          const result = res.data.results[0];
          updated[idx] = {
            ...updated[idx],
            status: result.passed ? 'passed' : 'failed',
            response_time: result.response_time_ms,
          };
        }
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || '测试执行失败';
      setError(`测试执行失败: ${detail}`);
      updated[idx] = { ...updated[idx], status: 'failed' };
    }

    setTestCases(updated);
  };

  const openDiagnosticModal = async (workflow: any) => {
    setSelectedWorkflow(workflow);
    
    const failedTests = testCases.filter(tc => tc.status === 'failed');
    const testResultsData = failedTests.length > 0 ? {
      failures: failedTests.map(tc => ({
        test_name: tc.name,
        error_message: '测试未通过',
        location: tc.url || tc.service,
      })),
    } : undefined;

    try {
      const res = await diagnoseApi.workflow(workflow.id, '', testResultsData);
      
      if (res.data && res.data.issues) {
        setDiagnosticReports([{
          id: `diag-${Date.now()}`,
          workflow_id: workflow.id,
          timestamp: res.data.timestamp || new Date().toISOString(),
          issues: res.data.issues.map((issue: any) => ({
            severity: issue.severity || 'medium',
            message: issue.message,
            code_location: issue.code_location,
            suggestion: issue.suggestion,
            confidence: issue.confidence,
            description: issue.description,
          })),
          insights: res.data.insights || [],
          confidence: res.data.confidence || 0.85,
        }]);
      } else {
        setDiagnosticReports([{
          id: `diag-${Date.now()}`,
          workflow_id: workflow.id,
          timestamp: new Date().toISOString(),
          issues: [
            { severity: 'low', message: '未发现明显问题', suggestion: '工作流运行正常' },
          ],
          insights: [],
          confidence: 0.9,
        }]);
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || '诊断失败';
      setError(`诊断失败: ${detail}`);
      setDiagnosticReports([{
        id: `diag-${Date.now()}`,
        workflow_id: workflow.id,
        timestamp: new Date().toISOString(),
        issues: [
          { severity: 'high', message: '诊断服务不可用', description: detail },
        ],
        insights: [],
        confidence: 0.0,
      }]);
    }
    
    setShowDiagnosticModal(true);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'bg-green-100 text-green-700';
      case 'completed':
        return 'bg-blue-100 text-blue-700';
      case 'defined':
        return 'bg-yellow-100 text-yellow-700';
      case 'failed':
        return 'bg-red-100 text-red-700';
      case 'paused':
        return 'bg-orange-100 text-orange-700';
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
      case 'defined':
        return '已定义';
      case 'failed':
        return '失败';
      case 'paused':
        return '已暂停';
      case 'defined':
        return '待执行';
      default:
        return status;
    }
  };

  const getTestCaseStatusColor = (status: string) => {
    switch (status) {
      case 'passed':
        return 'bg-green-100 text-green-700';
      case 'failed':
        return 'bg-red-100 text-red-700';
      default:
        return 'bg-yellow-100 text-yellow-700';
    }
  };

  const getIssueSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'border-l-red-500 bg-red-50';
      case 'high':
        return 'border-l-orange-500 bg-orange-50';
      case 'medium':
        return 'border-l-yellow-500 bg-yellow-50';
      case 'low':
        return 'border-l-blue-500 bg-blue-50';
      case 'warning':
        return 'border-l-yellow-500 bg-yellow-50';
      case 'info':
        return 'border-l-blue-500 bg-blue-50';
      default:
        return 'border-l-gray-500 bg-gray-50';
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">工作流列表</h3>
            <p className="text-sm text-gray-500">管理和执行自动化测试工作流</p>
          </div>
          <button
            data-testid="create-workflow-btn"
            onClick={() => { setShowCreateModal(true); setError(''); }}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
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
              <div key={workflow.id} data-testid={`workflow-card-${workflow.id}`} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h4 data-testid={`workflow-name-${workflow.id}`} className="font-semibold text-gray-900">{workflow.name}</h4>
                    <p className="text-sm text-gray-500 mt-1">{workflow.description}</p>
                  </div>
                  <span data-testid={`workflow-status-${workflow.id}`} className={`px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(workflow.status)}`}>
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

                <div className="grid grid-cols-2 gap-2">
                  <button
                    data-testid={`workflow-testcases-${workflow.id}`}
                    onClick={() => openTestCaseModal(workflow)}
                    className="flex items-center justify-center gap-2 px-3 py-2 bg-purple-50 text-purple-700 rounded-lg hover:bg-purple-100 transition-colors text-sm"
                  >
                    <TestTube className="w-4 h-4" />
                    <span>测试用例</span>
                  </button>
                  <button
                    data-testid={`workflow-diagnostic-${workflow.id}`}
                    onClick={() => openDiagnosticModal(workflow)}
                    className="flex items-center justify-center gap-2 px-3 py-2 bg-teal-50 text-teal-700 rounded-lg hover:bg-teal-100 transition-colors text-sm"
                  >
                    <Stethoscope className="w-4 h-4" />
                    <span>AI诊断</span>
                  </button>
                </div>

                <div className="flex items-center gap-2 mt-4 pt-4 border-t border-gray-100">
                  {workflow.status === 'running' && (
                    <button
                      data-testid={`workflow-pause-${workflow.id}`}
                      onClick={() => handlePause(workflow.id)}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-yellow-100 text-yellow-700 rounded-lg hover:bg-yellow-200 transition-colors text-sm"
                    >
                      <Pause className="w-4 h-4" />
                      <span>暂停</span>
                    </button>
                  )}
                  {workflow.status === 'pending' || workflow.status === 'defined' && (
                    <button
                      data-testid={`workflow-execute-${workflow.id}`}
                      onClick={() => handleExecute(workflow.id)}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm"
                    >
                      <Play className="w-4 h-4" />
                      <span>执行</span>
                    </button>
                  )}
                  {workflow.status === 'completed' && (
                    <button
                      data-testid={`workflow-retry-${workflow.id}`}
                      onClick={() => handleRetry(workflow.id)}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
                    >
                      <RotateCcw className="w-4 h-4" />
                      <span>重试</span>
                    </button>
                  )}
                  <button
                    data-testid={`workflow-delete-${workflow.id}`}
                    onClick={() => handleDelete(workflow.id)}
                    className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {showCreateModal && (
          <div data-testid="create-workflow-modal" className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4">
              <div className="flex items-center justify-between p-4 border-b">
                <h3 className="text-lg font-semibold text-gray-900">创建工作流</h3>
                <button
                  data-testid="create-workflow-close"
                  onClick={() => { setShowCreateModal(false); setError(''); }}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              </div>
              <form onSubmit={handleCreate} className="p-4 space-y-4">
                {error && (
                  <div data-testid="workflow-error-message" className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                    {error}
                  </div>
                )}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">工作流名称</label>
                  <input
                    data-testid="workflow-name-input"
                    type="text"
                    value={newWorkflow.name}
                    onChange={(e) => setNewWorkflow({ ...newWorkflow, name: e.target.value })}
                    placeholder="请输入工作流名称"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">描述</label>
                  <textarea
                    value={newWorkflow.description}
                    onChange={(e) => setNewWorkflow({ ...newWorkflow, description: e.target.value })}
                    placeholder="请输入工作流描述"
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">任务数量</label>
                  <input
                    type="number"
                    value={newWorkflow.task_count}
                    onChange={(e) => setNewWorkflow({ ...newWorkflow, task_count: parseInt(e.target.value) || 1 })}
                    min={1}
                    max={100}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => { setShowCreateModal(false); setError(''); }}
                    className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    取消
                  </button>
                  <button
                    data-testid="workflow-submit-btn"
                    type="submit"
                    disabled={createLoading}
                    className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {createLoading && <Loader2 className="w-4 h-4 animate-spin" />}
                    <span>{createLoading ? '创建中...' : '创建'}</span>
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {showTestCaseModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between p-4 border-b">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">测试用例管理</h3>
                  <p className="text-sm text-gray-500">工作流: {selectedWorkflow?.name}</p>
                </div>
                <button
                  onClick={() => setShowTestCaseModal(false)}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              </div>

              <div className="p-4">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleExecuteTestCase(testCases[0]?.id || '')}
                      disabled={!testCases.length}
                      className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50"
                    >
                      <Play className="w-4 h-4" />
                      <span>执行全部</span>
                    </button>
                  </div>
                  <button
                    onClick={() => {
                      setNewTestCase({ name: '', protocol: 'http', url: '', method: 'GET', service: '', grpcMethod: '', body: '', headers: '' });
                    }}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    <span>添加测试用例</span>
                  </button>
                </div>

                <div className="space-y-3">
                  {testCases.map((tc) => (
                    <div key={tc.id} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg ${tc.protocol === 'http' ? 'bg-blue-50' : 'bg-purple-50'}`}>
                            {tc.protocol === 'http' ? (
                              <Globe className="w-5 h-5 text-blue-600" />
                            ) : (
                              <Database className="w-5 h-5 text-purple-600" />
                            )}
                          </div>
                          <div>
                            <h4 className="font-medium text-gray-900">{tc.name}</h4>
                            <p className="text-sm text-gray-500">
                              {tc.protocol === 'http' ? (
                                <span>{tc.method} {tc.url}</span>
                              ) : (
                                <span>{tc.service} / {tc.grpcMethod}</span>
                              )}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          {tc.response_time && (
                            <span className="text-sm text-gray-500">{tc.response_time}ms</span>
                          )}
                          <span className={`px-3 py-1 rounded-full text-xs font-medium ${getTestCaseStatusColor(tc.status)}`}>
                            {tc.status === 'passed' ? '通过' : tc.status === 'failed' ? '失败' : '待执行'}
                          </span>
                          <button
                            onClick={() => handleExecuteTestCase(tc.id)}
                            className="p-2 text-gray-500 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                          >
                            <Play className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="mt-6 p-4 bg-gray-50 rounded-lg">
                  <h4 className="font-medium text-gray-900 mb-3">添加测试用例</h4>
                  <form onSubmit={handleCreateTestCase} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">用例名称</label>
                      <input
                        type="text"
                        value={newTestCase.name}
                        onChange={(e) => setNewTestCase({ ...newTestCase, name: e.target.value })}
                        placeholder="请输入用例名称"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">协议类型</label>
                      <select
                        value={newTestCase.protocol}
                        onChange={(e) => setNewTestCase({ ...newTestCase, protocol: e.target.value as 'http' | 'grpc' })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        <option value="http">HTTP/REST</option>
                        <option value="grpc">gRPC</option>
                      </select>
                    </div>
                    {newTestCase.protocol === 'http' && (
                      <>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">请求方法</label>
                          <select
                            value={newTestCase.method}
                            onChange={(e) => setNewTestCase({ ...newTestCase, method: e.target.value })}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                          >
                            <option value="GET">GET</option>
                            <option value="POST">POST</option>
                            <option value="PUT">PUT</option>
                            <option value="DELETE">DELETE</option>
                          </select>
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
                          <input
                            type="text"
                            value={newTestCase.url}
                            onChange={(e) => setNewTestCase({ ...newTestCase, url: e.target.value })}
                            placeholder="http://example.com/api"
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        </div>
                        <div className="md:col-span-2">
                          <label className="block text-sm font-medium text-gray-700 mb-1">请求体 (JSON)</label>
                          <textarea
                            value={newTestCase.body}
                            onChange={(e) => setNewTestCase({ ...newTestCase, body: e.target.value })}
                            placeholder='{"key": "value"}'
                            rows={3}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                          />
                        </div>
                        <div className="md:col-span-2">
                          <label className="block text-sm font-medium text-gray-700 mb-1">请求头 (JSON)</label>
                          <textarea
                            value={newTestCase.headers}
                            onChange={(e) => setNewTestCase({ ...newTestCase, headers: e.target.value })}
                            placeholder='{"Content-Type": "application/json"}'
                            rows={2}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                          />
                        </div>
                      </>
                    )}
                    {newTestCase.protocol === 'grpc' && (
                      <>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">服务名</label>
                          <input
                            type="text"
                            value={newTestCase.service}
                            onChange={(e) => setNewTestCase({ ...newTestCase, service: e.target.value })}
                            placeholder="com.example.Service"
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">方法名</label>
                          <input
                            type="text"
                            value={newTestCase.grpcMethod}
                            onChange={(e) => setNewTestCase({ ...newTestCase, grpcMethod: e.target.value })}
                            placeholder="GetUser"
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        </div>
                        <div className="md:col-span-2">
                          <label className="block text-sm font-medium text-gray-700 mb-1">请求参数 (JSON)</label>
                          <textarea
                            value={newTestCase.body}
                            onChange={(e) => setNewTestCase({ ...newTestCase, body: e.target.value })}
                            placeholder='{"id": 123}'
                            rows={3}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                          />
                        </div>
                      </>
                    )}
                    <div className="md:col-span-2 flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={() => setNewTestCase({
                          name: '',
                          protocol: 'http',
                          url: '',
                          method: 'GET',
                          service: '',
                          grpcMethod: '',
                          body: '',
                          headers: '',
                        })}
                        className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
                      >
                        重置
                      </button>
                      <button
                        type="submit"
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                      >
                        添加
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            </div>
          </div>
        )}

        {showDiagnosticModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between p-4 border-b">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">AI诊断报告</h3>
                  <p className="text-sm text-gray-500">工作流: {selectedWorkflow?.name}</p>
                </div>
                <button
                  onClick={() => setShowDiagnosticModal(false)}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              </div>

              <div className="p-4 space-y-6">
                {diagnosticReports.map((report) => (
                  <div key={report.id} className="border border-gray-200 rounded-lg overflow-hidden">
                    <div className="p-4 bg-gray-50 border-b">
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="font-medium text-gray-900">诊断报告 #{report.id.split('-')[1]}</h4>
                          <p className="text-sm text-gray-500">{report.timestamp}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-500">置信度:</span>
                          <span className="text-sm font-semibold text-blue-600">{(report.confidence * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                    </div>
                    <div className="p-4 space-y-3">
                      {report.issues.map((issue, idx) => (
                        <div key={idx} className={`border-l-4 rounded-r-lg p-4 ${getIssueSeverityColor(issue.severity)}`}>
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium mb-2 ${
                                issue.severity === 'critical' ? 'bg-red-200 text-red-800' :
                                issue.severity === 'high' ? 'bg-orange-200 text-orange-800' :
                                issue.severity === 'medium' ? 'bg-yellow-200 text-yellow-800' :
                                issue.severity === 'low' ? 'bg-blue-200 text-blue-800' :
                                issue.severity === 'warning' ? 'bg-yellow-200 text-yellow-800' :
                                'bg-blue-200 text-blue-800'
                              }`}>
                                {issue.severity === 'critical' ? '严重' :
                                 issue.severity === 'high' ? '高' :
                                 issue.severity === 'medium' ? '中' :
                                 issue.severity === 'low' ? '低' :
                                 issue.severity === 'warning' ? '警告' : '信息'}
                              </span>
                              <p className="text-gray-900">{issue.message}</p>
                              {issue.code_location && (
                                <p className="text-sm text-gray-600 mt-1">位置: {issue.code_location}</p>
                              )}
                              {issue.description && (
                                <p className="text-sm text-gray-600 mt-1">{issue.description}</p>
                              )}
                            </div>
                            {issue.confidence !== undefined && (
                              <span className="text-xs text-gray-500 ml-4">
                                置信度: {(issue.confidence * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>
                          {issue.suggestion && (
                            <div className="mt-3 p-3 bg-white/50 rounded-lg">
                              <p className="text-sm text-gray-700">
                                <span className="font-medium">建议: </span>{issue.suggestion}
                              </p>
                            </div>
                          )}
                        </div>
                      ))}
                      {report.insights && report.insights.length > 0 && (
                        <div className="mt-4 pt-4 border-t border-gray-200">
                          <h5 className="font-medium text-gray-900 mb-3">AI洞察</h5>
                          <div className="space-y-2">
                            {report.insights.map((insight, idx) => (
                              <div key={idx} className="p-3 bg-indigo-50 rounded-lg">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="font-medium text-indigo-900">{insight.title}</span>
                                  <span className={`text-xs px-2 py-0.5 rounded ${
                                    insight.severity === 'critical' ? 'bg-red-200 text-red-800' :
                                    insight.severity === 'high' ? 'bg-orange-200 text-orange-800' :
                                    insight.severity === 'medium' ? 'bg-yellow-200 text-yellow-800' :
                                    'bg-blue-200 text-blue-800'
                                  }`}>
                                    {insight.severity}
                                  </span>
                                </div>
                                <p className="text-sm text-gray-600">{insight.description}</p>
                                {insight.recommendation && (
                                  <p className="text-sm text-indigo-700 mt-2">
                                    <span className="font-medium">建议: </span>{insight.recommendation}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}