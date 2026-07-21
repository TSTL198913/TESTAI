'use client';

import { useState, useEffect } from 'react';
import {
  Cog,
  Save,
  RefreshCw,
  Edit2,
  X,
} from 'lucide-react';
import Layout from '../../components/Layout';
import { configApi } from '../../lib/api';

export default function ConfigPage() {
  const [configs, setConfigs] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [editingSection, setEditingSection] = useState<string | null>(null);
  const [editConfig, setEditConfig] = useState<any>({});

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const res = await configApi.get();
      setConfigs(res.data);
    } catch (error) {
      console.error('Failed to fetch config:', error);
      setConfigs({
        governance: { auto_approval: false, max_retries: 3 },
        monitoring: { alert_level: 'WARNING', enabled: true },
        workflow: { concurrency: 5, timeout: 300 },
        api: { rate_limit: 1000, cors_enabled: true },
      });
    } finally {
      setLoading(false);
    }
  };

  const handleStartEdit = (section: string) => {
    setEditingSection(section);
    setEditConfig({ ...configs[section] });
  };

  const handleSave = async (section: string) => {
    try {
      await configApi.update(section, editConfig);
      setConfigs((prev: any) => ({ ...prev, [section]: editConfig }));
      setEditingSection(null);
    } catch (error) {
      console.error('Failed to save config:', error);
    }
  };

  const getSectionName = (section: string) => {
    switch (section) {
      case 'governance':
        return '治理配置';
      case 'monitoring':
        return '监控配置';
      case 'workflow':
        return '工作流配置';
      case 'api':
        return 'API 配置';
      default:
        return section;
    }
  };

  const renderConfigItem = (key: string, value: any) => (
    <div key={key} className="flex items-center justify-between py-2 border-b border-gray-100">
      <span className="text-sm text-gray-600 capitalize">{key.replace('_', ' ')}</span>
      <span className="text-sm text-gray-900 font-medium">
        {typeof value === 'boolean' ? (value ? '是' : '否') : value}
      </span>
    </div>
  );

  const renderEditConfigItem = (key: string, value: any) => {
    const handleChange = (newValue: any) => {
      setEditConfig((prev: any) => ({ ...prev, [key]: newValue }));
    };

    if (typeof value === 'boolean') {
      return (
        <div key={key} className="flex items-center justify-between py-2 border-b border-gray-100">
          <span className="text-sm text-gray-600 capitalize">{key.replace('_', ' ')}</span>
          <button
            onClick={() => handleChange(!value)}
            className={`relative w-12 h-6 rounded-full transition-colors ${value ? 'bg-blue-600' : 'bg-gray-300'}`}
          >
            <span
              className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${value ? 'translate-x-6' : ''}`}
            ></span>
          </button>
        </div>
      );
    }

    return (
      <div key={key} className="py-2 border-b border-gray-100">
        <span className="text-sm text-gray-600 capitalize">{key.replace('_', ' ')}</span>
        <input
          type="text"
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>
    );
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">系统配置</h3>
          <button
            onClick={fetchConfig}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            <span>刷新</span>
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {Object.entries(configs).map(([section, config]) => (
              <div key={section} className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="flex items-center justify-between px-6 py-4 bg-gray-50 border-b border-gray-200">
                  <div className="flex items-center gap-3">
                    <Cog className="w-5 h-5 text-gray-500" />
                    <h4 className="font-semibold text-gray-900">{getSectionName(section)}</h4>
                  </div>
                  {editingSection === section ? (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleSave(section)}
                        className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                      >
                        <Save className="w-4 h-4" />
                        <span>保存</span>
                      </button>
                      <button
                        onClick={() => setEditingSection(null)}
                        className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded-lg transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => handleStartEdit(section)}
                      className="flex items-center gap-2 px-3 py-1.5 text-gray-600 hover:text-gray-900 hover:bg-gray-200 rounded-lg transition-colors"
                    >
                      <Edit2 className="w-4 h-4" />
                      <span>编辑</span>
                    </button>
                  )}
                </div>
                <div className="p-6">
                  {editingSection === section ? (
                    Object.entries(editConfig as Record<string, unknown>).map(([key, value]) => renderEditConfigItem(key, value))
                  ) : (
                    Object.entries(config as Record<string, unknown>).map(([key, value]) => renderConfigItem(key, value))
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}