'use client';

import { useState, useEffect } from 'react';
import {
  GitBranch,
  CheckCircle,
  XCircle,
  Clock,
  Play,
  Eye,
  AlertCircle,
  Loader2,
  X,
} from 'lucide-react';
import Layout from '../../components/Layout';
import { governanceApi } from '../../lib/api';

export default function GovernancePage() {
  const [approvals, setApprovals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [error, setError] = useState<string>('');
  const [executeLoading, setExecuteLoading] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [selectedApproval, setSelectedApproval] = useState<any>(null);

  useEffect(() => {
    const user = localStorage.getItem('user');
    if (!user) {
      setError('未检测到登录凭证，请先登录');
      setLoading(false);
      return;
    }
    fetchApprovals();
  }, [statusFilter]);

  const fetchApprovals = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await governanceApi.listApprovals(statusFilter === 'all' ? undefined : statusFilter);
      setApprovals(res.data.approvals || res.data || []);
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      console.error('Failed to fetch approvals:', error);
      if (detail?.includes('401') || err?.response?.status === 401) {
        setError('登录已过期，请重新登录');
      } else {
        setError(detail ? `加载审批列表失败: ${detail}` : '加载审批列表失败');
      }
      setApprovals([
        { tx_id: 'tx-001', component_name: 'transformer', status: 'PENDING', created_at: '2026-07-20 10:30' },
        { tx_id: 'tx-002', component_name: 'executor', status: 'APPROVED', created_at: '2026-07-19 14:20' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (txId: string) => {
    try {
      // P0-2 修复:移除硬编码 'admin',后端从认证用户获取 approver
      await governanceApi.approve(txId, '自动审批');
      fetchApprovals();
    } catch (error) {
      console.error('Failed to approve:', error);
    }
  };

  const handleReject = async (txId: string) => {
    try {
      // P0-2 修复:移除硬编码 'admin',后端从认证用户获取 approver
      await governanceApi.reject(txId, '拒绝审批');
      fetchApprovals();
    } catch (error) {
      console.error('Failed to reject:', error);
    }
  };

  const handleExecuteGovernance = async () => {
    setExecuteLoading(true);
    setError('');
    try {
      await governanceApi.execute({
        component_name: 'workflow_engine',
        input_data: { action: 'audit' },
      });
      fetchApprovals();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `执行治理失败: ${detail}` : '执行治理失败');
    } finally {
      setExecuteLoading(false);
    }
  };

  const handleViewDetail = (approval: any) => {
    setSelectedApproval(approval);
    setShowDetailModal(true);
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'PENDING':
        return <Clock className="w-4 h-4 text-yellow-500" />;
      case 'APPROVED':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'REJECTED':
        return <XCircle className="w-4 h-4 text-red-500" />;
      default:
        return <Clock className="w-4 h-4 text-gray-500" />;
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'PENDING':
        return '待审批';
      case 'APPROVED':
        return '已批准';
      case 'REJECTED':
        return '已拒绝';
      default:
        return status;
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex bg-gray-100 rounded-lg p-1">
            {['all', 'pending', 'approved', 'rejected'].map((status) => (
              <button
                key={status}
                data-testid={`filter-${status}`}
                onClick={() => setStatusFilter(status)}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  statusFilter === status
                    ? 'bg-white shadow-sm text-blue-600'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {status === 'all' ? '全部' : status === 'pending' ? '待审批' : status === 'approved' ? '已批准' : '已拒绝'}
              </button>
            ))}
          </div>
          </div>
          <button
            data-testid="execute-governance-btn"
            onClick={handleExecuteGovernance}
            disabled={executeLoading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {executeLoading && <Loader2 className="w-4 h-4 animate-spin" />}
            <Play className="w-4 h-4" />
            <span>{executeLoading ? '执行中...' : '执行治理'}</span>
          </button>
        </div>

        {error && (
          <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">事务ID</th>
                  <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">组件</th>
                  <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">状态</th>
                  <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">创建时间</th>
                  <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {approvals.length > 0 ? (
                  approvals.map((approval) => (
                    <tr key={approval.tx_id} data-testid={`approval-row-${approval.tx_id}`} className="hover:bg-gray-50">
                      <td className="px-6 py-4 text-sm font-mono text-gray-900">{approval.tx_id}</td>
                      <td data-testid={`approval-component-${approval.tx_id}`} className="px-6 py-4 text-sm text-gray-600">{approval.component_name}</td>
                      <td data-testid={`approval-status-${approval.tx_id}`} className="px-6 py-4">
                        <span className="flex items-center gap-2 text-sm">
                          {getStatusIcon(approval.status)}
                          <span className="text-gray-900">{getStatusText(approval.status)}</span>
                        </span>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{approval.created_at}</td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <button
                            data-testid={`approval-view-${approval.tx_id}`}
                            onClick={() => handleViewDetail(approval)}
                            className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          {approval.status === 'PENDING' && (
                            <>
                              <button
                                data-testid={`approval-approve-${approval.tx_id}`}
                                onClick={() => handleApprove(approval.tx_id)}
                                className="p-2 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                              >
                                <CheckCircle className="w-4 h-4" />
                              </button>
                              <button
                                data-testid={`approval-reject-${approval.tx_id}`}
                                onClick={() => handleReject(approval.tx_id)}
                                className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                              >
                                <XCircle className="w-4 h-4" />
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center text-gray-500">
                      <GitBranch className="w-12 h-12 mx-auto text-gray-300 mb-3" />
                      <p>暂无审批任务</p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {showDetailModal && selectedApproval && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4">
              <div className="flex items-center justify-between p-4 border-b">
                <h3 className="text-lg font-semibold text-gray-900">审批详情</h3>
                <button
                  onClick={() => setShowDetailModal(false)}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              </div>
              <div className="p-4 space-y-4">
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">事务ID</span>
                  <span className="text-sm font-mono text-gray-900">{selectedApproval.tx_id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">组件名称</span>
                  <span className="text-sm text-gray-900">{selectedApproval.component_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">状态</span>
                  <span className={`text-sm ${selectedApproval.status === 'PENDING' ? 'text-yellow-600' : selectedApproval.status === 'APPROVED' ? 'text-green-600' : 'text-red-600'}`}>
                    {getStatusText(selectedApproval.status)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">创建时间</span>
                  <span className="text-sm text-gray-900">{selectedApproval.created_at}</span>
                </div>
                <button
                  onClick={() => setShowDetailModal(false)}
                  className="w-full px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
                >
                  关闭
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}