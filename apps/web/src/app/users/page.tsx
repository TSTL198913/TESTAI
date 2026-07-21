'use client';

import { useState, useEffect, FormEvent } from 'react';
import {
  Users as UsersIcon,
  Plus,
  Pencil,
  Trash2,
  Power,
  PowerOff,
  CheckCircle,
  XCircle,
  Mail,
  Search,
  Loader2,
  AlertCircle,
  X,
} from 'lucide-react';
import Layout from '../../components/Layout';
import { userApi } from '../../lib/api';

interface User {
  id: string;
  username: string;
  email: string;
  role: string;
  status?: string;
  department?: string;
}

const ROLE_OPTIONS = ['admin', 'manager', 'tester', 'viewer'];
const STATUS_ACTIVE = 'active';

const roleText = (role: string) => {
  switch (role) {
    case 'admin':
      return '管理员';
    case 'manager':
      return '经理';
    case 'tester':
      return '测试人员';
    case 'viewer':
      return '访客';
    default:
      return role;
  }
};

const statusText = (status?: string) => {
  switch (status) {
    case 'active':
      return '已激活';
    case 'suspended':
      return '已停用';
    case 'inactive':
      return '未激活';
    default:
      return status || '未知';
  }
};

export default function UsersPage() {
  const [token, setToken] = useState<string>('');
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [keyword, setKeyword] = useState('');

  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
    role: 'tester',
    department: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string>('');

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    if (!stored) {
      setError('未检测到登录凭证，请先登录');
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) fetchUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const fetchUsers = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await userApi.list(token);
      const list = res.data?.users || res.data?.items || res.data || [];
      setUsers(Array.isArray(list) ? list : []);
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `加载用户失败: ${detail}` : '加载用户失败，请稍后重试');
      setUsers([]);
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingUser(null);
    setForm({ username: '', email: '', password: '', role: 'tester', department: '' });
    setFormError('');
    setModalOpen(true);
  };

  const openEdit = (user: User) => {
    setEditingUser(user);
    setForm({
      username: user.username || '',
      email: user.email || '',
      password: '',
      role: user.role || 'tester',
      department: user.department || '',
    });
    setFormError('');
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingUser(null);
    setFormError('');
  };

  const submitForm = async (e: FormEvent) => {
    e.preventDefault();
    setFormError('');

    if (!form.username.trim() || !form.email.trim()) {
      setFormError('用户名和邮箱不能为空');
      return;
    }
    if (!editingUser && !form.password) {
      setFormError('创建用户时必须设置密码');
      return;
    }

    setSubmitting(true);
    try {
      const payload: any = {
        username: form.username.trim(),
        email: form.email.trim(),
        role: form.role,
      };
      if (form.department.trim()) payload.department = form.department.trim();
      if (form.password) payload.password = form.password;

      if (editingUser) {
        await userApi.update(token, editingUser.id, payload);
      } else {
        await userApi.create(token, payload);
      }
      closeModal();
      await fetchUsers();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setFormError(detail ? `保存失败: ${detail}` : '保存失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (user: User) => {
    if (!confirm(`确认删除用户 ${user.username}？此操作不可恢复。`)) return;
    try {
      await userApi.delete(token, user.id);
      await fetchUsers();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `删除失败: ${detail}` : '删除失败');
    }
  };

  const handleActivate = async (user: User) => {
    try {
      await userApi.activate(token, user.id);
      await fetchUsers();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `激活失败: ${detail}` : '激活失败');
    }
  };

  const handleSuspend = async (user: User) => {
    if (!confirm(`确认停用用户 ${user.username}？`)) return;
    try {
      await userApi.suspend(token, user.id);
      await fetchUsers();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `停用失败: ${detail}` : '停用失败');
    }
  };

  const filtered = users.filter((u) => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return true;
    return (
      (u.username || '').toLowerCase().includes(kw) ||
      (u.email || '').toLowerCase().includes(kw) ||
      (u.department || '').toLowerCase().includes(kw)
    );
  });

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="搜索用户名 / 邮箱 / 部门"
                className="pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-72"
              />
            </div>
          </div>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>创建用户</span>
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
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">用户名</th>
                    <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">邮箱</th>
                    <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">角色</th>
                    <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">状态</th>
                    <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">部门</th>
                    <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filtered.length > 0 ? (
                    filtered.map((user) => {
                      const isActive = (user.status || STATUS_ACTIVE) === STATUS_ACTIVE;
                      return (
                        <tr key={user.id} className="hover:bg-gray-50">
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-3">
                              <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                                <span className="text-blue-600 font-semibold text-sm">
                                  {(user.username || '?').charAt(0).toUpperCase()}
                                </span>
                              </div>
                              <span className="text-sm font-medium text-gray-900">{user.username}</span>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-2 text-sm text-gray-600">
                              <Mail className="w-4 h-4 text-gray-400" />
                              <span>{user.email}</span>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <span className="inline-flex px-2.5 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                              {roleText(user.role)}
                            </span>
                          </td>
                          <td className="px-6 py-4">
                            <span className="flex items-center gap-2 text-sm">
                              {isActive ? (
                                <CheckCircle className="w-4 h-4 text-green-500" />
                              ) : (
                                <XCircle className="w-4 h-4 text-red-500" />
                              )}
                              <span className={isActive ? 'text-gray-900' : 'text-red-600'}>
                                {statusText(user.status)}
                              </span>
                            </span>
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-600">
                            {user.department || '-'}
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => openEdit(user)}
                                title="编辑用户"
                                className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                              {isActive ? (
                                <button
                                  onClick={() => handleSuspend(user)}
                                  title="停用用户"
                                  className="p-2 text-yellow-600 hover:bg-yellow-50 rounded-lg transition-colors"
                                >
                                  <PowerOff className="w-4 h-4" />
                                </button>
                              ) : (
                                <button
                                  onClick={() => handleActivate(user)}
                                  title="激活用户"
                                  className="p-2 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                                >
                                  <Power className="w-4 h-4" />
                                </button>
                              )}
                              <button
                                onClick={() => handleDelete(user)}
                                title="删除用户"
                                className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={6} className="px-6 py-12 text-center text-gray-500">
                        <UsersIcon className="w-12 h-12 mx-auto text-gray-300 mb-3" />
                        <p>暂无用户数据</p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">
                {editingUser ? '编辑用户' : '创建用户'}
              </h3>
              <button
                onClick={closeModal}
                className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={submitForm} className="p-6 space-y-4">
              {formError && (
                <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-red-700">{formError}</p>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">用户名</label>
                <input
                  type="text"
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  placeholder="请输入用户名"
                  disabled={submitting}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">邮箱</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  placeholder="请输入邮箱"
                  disabled={submitting}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  密码{editingUser ? '（留空表示不修改）' : ''}
                </label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder={editingUser ? '留空表示不修改' : '请输入密码'}
                  disabled={submitting}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">角色</label>
                <select
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  disabled={submitting}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                >
                  {ROLE_OPTIONS.map((r) => (
                    <option key={r} value={r}>
                      {roleText(r)}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">部门</label>
                <input
                  type="text"
                  value={form.department}
                  onChange={(e) => setForm({ ...form, department: e.target.value })}
                  placeholder="请输入部门（可选）"
                  disabled={submitting}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  disabled={submitting}
                  className="px-4 py-2 text-sm text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-60"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-60"
                >
                  {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
                  <span>{editingUser ? '保存' : '创建'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </Layout>
  );
}
