import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const healthApi = {
  check: () => api.get('/health'),
};

export const governanceApi = {
  execute: (data: {
    component_name: string;
    step_id?: string;
    input_data?: Record<string, any>;
    actual_output?: string;
    expected_baseline?: string;
  }) => api.post('/governance/execute', null, { params: data }),
  listApprovals: (status?: string) => api.get('/governance/approvals', { params: { status } }),
  approve: (tx_id: string, approver: string, reason?: string) =>
    api.post(`/governance/approvals/${tx_id}/approve`, null, { params: { approver, reason } }),
  reject: (tx_id: string, approver: string, reason: string) =>
    api.post(`/governance/approvals/${tx_id}/reject`, null, { params: { approver, reason } }),
};

export const monitoringApi = {
  getAlerts: (level?: string) => api.get('/monitoring/alerts', { params: { level } }),
  acknowledgeAlert: (alert_id: string) => api.post(`/monitoring/alerts/${alert_id}/acknowledge`),
  getMetrics: () => api.get('/monitoring/metrics'),
};

export const workflowApi = {
  define: (definition: any) => api.post('/workflow/define', definition),
  execute: (workflow_id: string, params?: Record<string, any>) =>
    api.post(`/workflow/${workflow_id}/execute`, params),
  getStatus: (workflow_id: string) => api.get(`/workflow/${workflow_id}/status`),
};

export const configApi = {
  get: (section?: string) => api.get('/config', { params: { section } }),
  update: (section: string, config: Record<string, any>) => api.put(`/config/${section}`, config),
};

export const dashboardApi = {
  getSummary: () => api.get('/dashboard/summary'),
  getQualityTrend: (days?: number) => api.get('/dashboard/quality-trend', { params: { days } }),
};

export const authApi = {
  login: (username: string, password: string) => api.post('/auth/login', { username, password }),
  refresh: (token: string) => api.post('/auth/refresh', null, { headers: { Authorization: `Bearer ${token}` } }),
  me: (token: string) => api.get('/auth/me', { headers: { Authorization: `Bearer ${token}` } }),
};

export const userApi = {
  list: (token: string) => api.get('/users', { headers: { Authorization: `Bearer ${token}` } }),
  create: (token: string, data: any) => api.post('/users', data, { headers: { Authorization: `Bearer ${token}` } }),
  get: (token: string, userId: string) => api.get(`/users/${userId}`, { headers: { Authorization: `Bearer ${token}` } }),
  update: (token: string, userId: string, data: any) => api.put(`/users/${userId}`, data, { headers: { Authorization: `Bearer ${token}` } }),
  delete: (token: string, userId: string) => api.delete(`/users/${userId}`, { headers: { Authorization: `Bearer ${token}` } }),
  activate: (token: string, userId: string) => api.post(`/users/${userId}/activate`, null, { headers: { Authorization: `Bearer ${token}` } }),
  suspend: (token: string, userId: string) => api.post(`/users/${userId}/suspend`, null, { headers: { Authorization: `Bearer ${token}` } }),
};

export const teamApi = {
  list: (token: string) => api.get('/teams', { headers: { Authorization: `Bearer ${token}` } }),
  create: (token: string, data: any) => api.post('/teams', data, { headers: { Authorization: `Bearer ${token}` } }),
  get: (token: string, teamId: string) => api.get(`/teams/${teamId}`, { headers: { Authorization: `Bearer ${token}` } }),
  update: (token: string, teamId: string, data: any) => api.put(`/teams/${teamId}`, data, { headers: { Authorization: `Bearer ${token}` } }),
  delete: (token: string, teamId: string) => api.delete(`/teams/${teamId}`, { headers: { Authorization: `Bearer ${token}` } }),
  addMember: (token: string, teamId: string, data: any) => api.post(`/teams/${teamId}/members`, data, { headers: { Authorization: `Bearer ${token}` } }),
  removeMember: (token: string, teamId: string, userId: string) => api.delete(`/teams/${teamId}/members/${userId}`, { headers: { Authorization: `Bearer ${token}` } }),
  getMembers: (token: string, teamId: string) => api.get(`/teams/${teamId}/members`, { headers: { Authorization: `Bearer ${token}` } }),
};

export default api;