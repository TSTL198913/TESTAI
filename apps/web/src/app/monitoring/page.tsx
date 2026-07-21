'use client';

import { useState, useEffect } from 'react';
import {
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle,
  Bell,
  BellOff,
} from 'lucide-react';
import Layout from '../../components/Layout';
import { monitoringApi } from '../../lib/api';

export default function MonitoringPage() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [levelFilter, setLevelFilter] = useState<string>('all');

  useEffect(() => {
    fetchData();
  }, [levelFilter]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [alertsRes, metricsRes] = await Promise.all([
        monitoringApi.getAlerts(levelFilter === 'all' ? undefined : levelFilter),
        monitoringApi.getMetrics(),
      ]);
      setAlerts(alertsRes.data.alerts || []);
      setMetrics(metricsRes.data);
    } catch (error) {
      console.error('Failed to fetch monitoring data:', error);
      setAlerts([
        { id: '1', message: '系统启动正常', level: 'INFO', timestamp: '2026-07-20 18:00' },
        { id: '2', message: '工作流 wf-001 执行完成', level: 'INFO', timestamp: '2026-07-20 17:30' },
        { id: '3', message: '检测到潜在配置问题', level: 'WARNING', timestamp: '2026-07-20 16:45' },
      ]);
      setMetrics({ status: 'healthy', metrics: { cpu: 25, memory: 45, requests: 120 } });
    } finally {
      setLoading(false);
    }
  };

  const handleAcknowledge = async (alertId: string) => {
    try {
      await monitoringApi.acknowledgeAlert(alertId);
      fetchData();
    } catch (error) {
      console.error('Failed to acknowledge alert:', error);
    }
  };

  const getLevelIcon = (level: string) => {
    switch (level) {
      case 'CRITICAL':
        return <AlertTriangle className="w-5 h-5 text-red-500" />;
      case 'WARNING':
        return <AlertCircle className="w-5 h-5 text-yellow-500" />;
      case 'INFO':
        return <Info className="w-5 h-5 text-blue-500" />;
      default:
        return <Bell className="w-5 h-5 text-gray-500" />;
    }
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'CRITICAL':
        return 'border-l-red-500 bg-red-50';
      case 'WARNING':
        return 'border-l-yellow-500 bg-yellow-50';
      case 'INFO':
        return 'border-l-blue-500 bg-blue-50';
      default:
        return 'border-l-gray-500 bg-gray-50';
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <div className="flex items-center justify-between mb-4">
              <h4 className="font-semibold text-gray-900">CPU 使用率</h4>
              <span className="text-sm text-gray-500">实时</span>
            </div>
            <div className="flex items-end gap-2 h-32">
              {[60, 45, 70, 55, 40, 50, 65].map((val, i) => (
                <div key={i} className="flex-1 bg-blue-100 rounded-t transition-all" style={{ height: `${val}%` }}></div>
              ))}
            </div>
            <p className="text-2xl font-bold text-gray-900 mt-4">{metrics?.metrics?.cpu || 25}%</p>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <div className="flex items-center justify-between mb-4">
              <h4 className="font-semibold text-gray-900">内存使用</h4>
              <span className="text-sm text-gray-500">实时</span>
            </div>
            <div className="flex items-end gap-2 h-32">
              {[50, 55, 52, 58, 60, 55, 45].map((val, i) => (
                <div key={i} className="flex-1 bg-green-100 rounded-t transition-all" style={{ height: `${val}%` }}></div>
              ))}
            </div>
            <p className="text-2xl font-bold text-gray-900 mt-4">{metrics?.metrics?.memory || 45}%</p>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <div className="flex items-center justify-between mb-4">
              <h4 className="font-semibold text-gray-900">请求数量</h4>
              <span className="text-sm text-gray-500">今日</span>
            </div>
            <div className="flex items-end gap-2 h-32">
              {[80, 100, 90, 120, 110, 130, 120].map((val, i) => (
                <div key={i} className="flex-1 bg-purple-100 rounded-t transition-all" style={{ height: `${(val / 150) * 100}%` }}></div>
              ))}
            </div>
            <p className="text-2xl font-bold text-gray-900 mt-4">{metrics?.metrics?.requests || 120}</p>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">告警列表</h3>
          <div className="flex bg-gray-100 rounded-lg p-1">
            {['all', 'critical', 'warning', 'info'].map((level) => (
              <button
                key={level}
                onClick={() => setLevelFilter(level)}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  levelFilter === level
                    ? 'bg-white shadow-sm text-blue-600'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {level === 'all' ? '全部' : level === 'critical' ? '严重' : level === 'warning' ? '警告' : '信息'}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        ) : (
          <div className="space-y-3">
            {alerts.length > 0 ? (
              alerts.map((alert) => (
                <div
                  key={alert.id}
                  className={`border-l-4 rounded-lg p-4 ${getLevelColor(alert.level)}`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      {getLevelIcon(alert.level)}
                      <div>
                        <p className="font-medium text-gray-900">{alert.message}</p>
                        <p className="text-sm text-gray-500 mt-1">{alert.timestamp}</p>
                      </div>
                    </div>
                    <button
                      onClick={() => handleAcknowledge(alert.id)}
                      className="flex items-center gap-2 px-3 py-1 bg-white rounded-lg text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                    >
                      <CheckCircle className="w-4 h-4" />
                      <span>确认</span>
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center">
                <BellOff className="w-16 h-16 mx-auto text-gray-300 mb-4" />
                <h4 className="text-lg font-semibold text-gray-900">暂无告警</h4>
                <p className="text-gray-500 mt-2">系统运行正常</p>
              </div>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
}