'use client';

import { useEffect, useState } from 'react';
import { healthApi, dashboardApi } from '../lib/api';
import Layout from '../components/Layout';

export default function Home() {
  const [health, setHealth] = useState<any>(null);
  const [summary, setSummary] = useState<any>(null);
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const user = localStorage.getItem('user');
    if (!user) {
      setError('未检测到登录凭证，请先登录');
      setLoading(false);
      return;
    }
    
    Promise.all([healthApi.check(), dashboardApi.getSummary()])
      .then(([healthRes, summaryRes]) => {
        setHealth(healthRes.data);
        setSummary(summaryRes.data);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Layout>
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
        </div>
      ) : error ? (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-700">{error}</p>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-4 gap-4">
            <div className="p-4 bg-white rounded-lg shadow">
              <div className="text-sm text-gray-600">平台状态</div>
              <div className="text-lg font-semibold text-green-600">{health?.platform || '在线'}</div>
            </div>
            <div className="p-4 bg-white rounded-lg shadow">
              <div className="text-sm text-gray-600">版本</div>
              <div className="text-lg font-semibold">{health?.version || '1.0.0'}</div>
            </div>
            <div className="p-4 bg-white rounded-lg shadow">
              <div className="text-sm text-gray-600">测试用例</div>
              <div className="text-lg font-semibold">{summary?.total_test_cases || 0}</div>
            </div>
            <div className="p-4 bg-white rounded-lg shadow">
              <div className="text-sm text-gray-600">通过率</div>
              <div className="text-lg font-semibold">{summary?.pass_rate || 0}%</div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="p-4 bg-white rounded-lg shadow">
              <h3 className="font-semibold mb-2">最近告警</h3>
              <div className="text-sm text-gray-600">
                {summary?.recent_alerts?.length > 0 ? (
                  <ul className="space-y-2">
                    {summary.recent_alerts.slice(0, 5).map((a: any) => (
                      <li key={a.id} className="flex justify-between">
                        <span>{a.message}</span>
                        <span className={`text-xs px-2 py-0.5 rounded ${a.level === 'critical' ? 'bg-red-100 text-red-600' : 'bg-yellow-100 text-yellow-600'}`}>
                          {a.level}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>暂无告警</p>
                )}
              </div>
            </div>
            <div className="p-4 bg-white rounded-lg shadow">
              <h3 className="font-semibold mb-2">待审批任务</h3>
              <div className="text-sm text-gray-600">
                {summary?.pending_approvals || 0} 项待审批
              </div>
            </div>
            <div className="p-4 bg-white rounded-lg shadow">
              <h3 className="font-semibold mb-2">运行中工作流</h3>
              <div className="text-sm text-gray-600">
                {summary?.running_workflows || 0} 个运行中
              </div>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}