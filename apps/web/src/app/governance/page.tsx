'use client';

import { useState, useEffect } from 'react';
import {
  GitBranch,
  CheckCircle,
  XCircle,
  Clock,
  Play,
  Eye,
} from 'lucide-react';
import Layout from '../../components/Layout';
import { governanceApi } from '../../lib/api';

export default function GovernancePage() {
  const [approvals, setApprovals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');

  useEffect(() => {
    fetchApprovals();
  }, [statusFilter]);

  const fetchApprovals = async () => {
    setLoading(true);
    try {
      const res = await governanceApi.listApprovals(statusFilter === 'all' ? undefined : statusFilter);
      setApprovals(res.data.approvals || []);
    } catch (error) {
      console.error('Failed to fetch approvals:', error);
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
      await governanceApi.approve(txId, 'admin', '自动审批');
      fetchApprovals();
    } catch (error) {
      console.error('Failed to approve:', error);
    }
  };

  const handleReject = async (txId: string) => {
    try {
      await governanceApi.reject(txId, 'admin', '拒绝审批');
      fetchApprovals();
    } catch (error) {
      console.error('Failed to reject:', error);
    }
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
          <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
            <Play className="w-4 h-4" />
            <span>执行治理</span>
          </button>
        </div>

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
                    <tr key={approval.tx_id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 text-sm font-mono text-gray-900">{approval.tx_id}</td>
                      <td className="px-6 py-4 text-sm text-gray-600">{approval.component_name}</td>
                      <td className="px-6 py-4">
                        <span className="flex items-center gap-2 text-sm">
                          {getStatusIcon(approval.status)}
                          <span className="text-gray-900">{getStatusText(approval.status)}</span>
                        </span>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{approval.created_at}</td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <button className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
                            <Eye className="w-4 h-4" />
                          </button>
                          {approval.status === 'PENDING' && (
                            <>
                              <button
                                onClick={() => handleApprove(approval.tx_id)}
                                className="p-2 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                              >
                                <CheckCircle className="w-4 h-4" />
                              </button>
                              <button
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
      </div>
    </Layout>
  );
}