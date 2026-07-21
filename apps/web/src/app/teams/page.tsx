'use client';

import { useState, useEffect, FormEvent } from 'react';
import {
  UsersRound,
  Plus,
  Pencil,
  Trash2,
  UserPlus,
  UserMinus,
  Eye,
  X,
  Loader2,
  AlertCircle,
  Users,
  Mail,
} from 'lucide-react';
import Layout from '../../components/Layout';
import { teamApi } from '../../lib/api';

interface Team {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
  member_count?: number;
}

interface Member {
  id: string;
  username: string;
  email?: string;
  role?: string;
}

export default function TeamsPage() {
  const [token, setToken] = useState<string>('');
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');

  const [teamModalOpen, setTeamModalOpen] = useState(false);
  const [editingTeam, setEditingTeam] = useState<Team | null>(null);
  const [teamForm, setTeamForm] = useState({ name: '', description: '' });
  const [teamSubmitting, setTeamSubmitting] = useState(false);
  const [teamFormError, setTeamFormError] = useState('');

  const [membersModalOpen, setMembersModalOpen] = useState(false);
  const [currentTeam, setCurrentTeam] = useState<Team | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [memberForm, setMemberForm] = useState({ user_id: '', role: 'member' });
  const [memberSubmitting, setMemberSubmitting] = useState(false);
  const [memberError, setMemberError] = useState('');

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    if (!stored) {
      setError('未检测到登录凭证，请先登录');
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) fetchTeams();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const fetchTeams = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await teamApi.list(token);
      const list = res.data?.teams || res.data?.items || res.data || [];
      setTeams(Array.isArray(list) ? list : []);
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `加载团队失败: ${detail}` : '加载团队失败，请稍后重试');
      setTeams([]);
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingTeam(null);
    setTeamForm({ name: '', description: '' });
    setTeamFormError('');
    setTeamModalOpen(true);
  };

  const openEdit = (team: Team) => {
    setEditingTeam(team);
    setTeamForm({ name: team.name || '', description: team.description || '' });
    setTeamFormError('');
    setTeamModalOpen(true);
  };

  const closeTeamModal = () => {
    setTeamModalOpen(false);
    setEditingTeam(null);
    setTeamFormError('');
  };

  const submitTeamForm = async (e: FormEvent) => {
    e.preventDefault();
    setTeamFormError('');

    if (!teamForm.name.trim()) {
      setTeamFormError('团队名称不能为空');
      return;
    }

    setTeamSubmitting(true);
    try {
      const payload = {
        name: teamForm.name.trim(),
        description: teamForm.description.trim(),
      };
      if (editingTeam) {
        await teamApi.update(token, editingTeam.id, payload);
      } else {
        await teamApi.create(token, payload);
      }
      closeTeamModal();
      await fetchTeams();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setTeamFormError(detail ? `保存失败: ${detail}` : '保存失败，请稍后重试');
    } finally {
      setTeamSubmitting(false);
    }
  };

  const handleDelete = async (team: Team) => {
    if (!confirm(`确认删除团队 ${team.name}？此操作不可恢复。`)) return;
    try {
      await teamApi.delete(token, team.id);
      await fetchTeams();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setError(detail ? `删除失败: ${detail}` : '删除失败');
    }
  };

  const openMembers = async (team: Team) => {
    setCurrentTeam(team);
    setMembersModalOpen(true);
    setMemberForm({ user_id: '', role: 'member' });
    setMemberError('');
    await fetchMembers(team.id);
  };

  const closeMembersModal = () => {
    setMembersModalOpen(false);
    setCurrentTeam(null);
    setMembers([]);
    setMemberError('');
  };

  const fetchMembers = async (teamId: string) => {
    setMembersLoading(true);
    setMemberError('');
    try {
      const res = await teamApi.getMembers(token, teamId);
      const list = res.data?.members || res.data?.items || res.data || [];
      setMembers(Array.isArray(list) ? list : []);
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setMemberError(detail ? `加载成员失败: ${detail}` : '加载成员失败');
      setMembers([]);
    } finally {
      setMembersLoading(false);
    }
  };

  const addMember = async (e: FormEvent) => {
    e.preventDefault();
    setMemberError('');
    if (!memberForm.user_id.trim() || !currentTeam) {
      setMemberError('请输入成员用户 ID');
      return;
    }
    setMemberSubmitting(true);
    try {
      await teamApi.addMember(token, currentTeam.id, {
        user_id: memberForm.user_id.trim(),
        role: memberForm.role,
      });
      setMemberForm({ user_id: '', role: 'member' });
      await fetchMembers(currentTeam.id);
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setMemberError(detail ? `添加失败: ${detail}` : '添加成员失败');
    } finally {
      setMemberSubmitting(false);
    }
  };

  const removeMember = async (member: Member) => {
    if (!currentTeam) return;
    if (!confirm(`确认将成员 ${member.username} 移出团队？`)) return;
    try {
      await teamApi.removeMember(token, currentTeam.id, member.id);
      await fetchMembers(currentTeam.id);
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail || err?.response?.data?.message || err?.message || '';
      setMemberError(detail ? `移除失败: ${detail}` : '移除成员失败');
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">团队列表</h3>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>创建团队</span>
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
        ) : teams.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {teams.map((team) => (
              <div
                key={team.id}
                className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 flex flex-col"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-purple-500 rounded-xl flex items-center justify-center">
                      <UsersRound className="w-6 h-6 text-white" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-900">{team.name}</h4>
                      {team.created_at && (
                        <p className="text-xs text-gray-400 mt-0.5">{team.created_at}</p>
                      )}
                    </div>
                  </div>
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700">
                    <Users className="w-3 h-3" />
                    {team.member_count ?? members.length}
                  </span>
                </div>

                <p className="text-sm text-gray-500 flex-1 line-clamp-2 min-h-[2.5rem]">
                  {team.description || '暂无描述'}
                </p>

                <div className="flex items-center gap-2 mt-4 pt-4 border-t border-gray-100">
                  <button
                    onClick={() => openMembers(team)}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 transition-colors text-sm"
                  >
                    <Eye className="w-4 h-4" />
                    <span>成员</span>
                  </button>
                  <button
                    onClick={() => openEdit(team)}
                    title="编辑团队"
                    className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(team)}
                    title="删除团队"
                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center text-gray-500">
            <UsersRound className="w-12 h-12 mx-auto text-gray-300 mb-3" />
            <p>暂无团队数据</p>
          </div>
        )}
      </div>

      {/* 团队创建/编辑模态框 */}
      {teamModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">
                {editingTeam ? '编辑团队' : '创建团队'}
              </h3>
              <button
                onClick={closeTeamModal}
                className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={submitTeamForm} className="p-6 space-y-4">
              {teamFormError && (
                <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-red-700">{teamFormError}</p>
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">团队名称</label>
                <input
                  type="text"
                  value={teamForm.name}
                  onChange={(e) => setTeamForm({ ...teamForm, name: e.target.value })}
                  placeholder="请输入团队名称"
                  disabled={teamSubmitting}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">团队描述</label>
                <textarea
                  value={teamForm.description}
                  onChange={(e) => setTeamForm({ ...teamForm, description: e.target.value })}
                  placeholder="请输入团队描述（可选）"
                  rows={3}
                  disabled={teamSubmitting}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 resize-none"
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={closeTeamModal}
                  disabled={teamSubmitting}
                  className="px-4 py-2 text-sm text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-60"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={teamSubmitting}
                  className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-60"
                >
                  {teamSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                  <span>{editingTeam ? '保存' : '创建'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 成员管理模态框 */}
      {membersModalOpen && currentTeam && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">{currentTeam.name} · 成员管理</h3>
                {currentTeam.description && (
                  <p className="text-xs text-gray-500 mt-0.5">{currentTeam.description}</p>
                )}
              </div>
              <button
                onClick={closeMembersModal}
                className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              {memberError && (
                <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-red-700">{memberError}</p>
                </div>
              )}

              <form onSubmit={addMember} className="flex items-end gap-2 p-3 bg-gray-50 rounded-lg">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-600 mb-1">用户 ID</label>
                  <input
                    type="text"
                    value={memberForm.user_id}
                    onChange={(e) => setMemberForm({ ...memberForm, user_id: e.target.value })}
                    placeholder="请输入要添加的用户 ID"
                    disabled={memberSubmitting}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 text-sm"
                  />
                </div>
                <div className="w-32">
                  <label className="block text-xs font-medium text-gray-600 mb-1">角色</label>
                  <select
                    value={memberForm.role}
                    onChange={(e) => setMemberForm({ ...memberForm, role: e.target.value })}
                    disabled={memberSubmitting}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 text-sm"
                  >
                    <option value="member">成员</option>
                    <option value="leader">负责人</option>
                    <option value="admin">管理员</option>
                  </select>
                </div>
                <button
                  type="submit"
                  disabled={memberSubmitting}
                  className="flex items-center gap-1 px-3 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-60"
                >
                  {memberSubmitting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <UserPlus className="w-4 h-4" />
                  )}
                  <span>添加</span>
                </button>
              </form>

              {membersLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                </div>
              ) : members.length > 0 ? (
                <div className="space-y-2">
                  {members.map((member) => (
                    <div
                      key={member.id}
                      className="flex items-center justify-between p-3 border border-gray-200 rounded-lg hover:bg-gray-50"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 bg-blue-100 rounded-full flex items-center justify-center">
                          <span className="text-blue-600 font-semibold text-sm">
                            {(member.username || '?').charAt(0).toUpperCase()}
                          </span>
                        </div>
                        <div>
                          <div className="text-sm font-medium text-gray-900">{member.username}</div>
                          {member.email && (
                            <div className="flex items-center gap-1 text-xs text-gray-500">
                              <Mail className="w-3 h-3" />
                              <span>{member.email}</span>
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {member.role && (
                          <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                            {member.role}
                          </span>
                        )}
                        <button
                          onClick={() => removeMember(member)}
                          title="移除成员"
                          className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                        >
                          <UserMinus className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500">
                  <Users className="w-10 h-10 mx-auto text-gray-300 mb-2" />
                  <p className="text-sm">暂无成员</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}
