import axios, { AxiosRequestConfig } from 'axios';

declare module 'axios' {
  interface AxiosRequestConfig {
    _skipRefresh?: boolean;
    _retry?: boolean;
  }
}

const api = axios.create({
  baseURL: '/api',
  // P0-6 修复:开启 withCredentials,让浏览器自动发送 HttpOnly cookie(access_token/refresh_token)
  // cookie 不暴露给 JavaScript,XSS 攻击无法窃取 token
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  // P0-6 修复:cookie 优先(withCredentials 自动发送),localStorage token 仅作兼容期回退
  // 新前端不再将 token 写入 localStorage,旧客户端在过渡期仍可工作
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 方案C：响应归一化拦截器
// 后端统一返回 ApiResponse 格式: {success, data, message, error_code}
// 归一化后：response.data 直接就是业务数据 (原 response.data.data)
// 这样前端各页面统一用 res.data 即可，无需 res.data.data
api.interceptors.response.use(
  (response) => {
    // 只对后端 ApiResponse 格式进行归一化
    const body = response.data;
    if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
      // 业务失败：转换为 axios 错误，进入错误处理流程
      if (body.success === false) {
        const err: any = new Error(body.message || 'Business error');
        err.response = {
          status: body.error_code || 400,
          data: body,
          statusText: body.message || 'Business error',
        };
        return Promise.reject(err);
      }
      // 业务成功：将 data 提升到 response.data，保留原始 body 在 _raw
      response.data = body.data;
      (response as any)._raw = body;
    }
    return response;
  },
  (error) => Promise.reject(error)
);

let isRefreshing = false;
let failedQueue: { resolve: (token: string) => void; reject: (error: any) => void }[] = [];

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry && !originalRequest._skipRefresh) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        });
      }
      isRefreshing = true;
      originalRequest._retry = true;
      try {
        // P0-6 修复:withCredentials 已让浏览器自动发送 refresh_token cookie
        // localStorage refresh_token 仅作兼容期回退(无 cookie 场景)
        const refreshToken = localStorage.getItem('refresh_token');
        const headers: Record<string, string> = {};
        if (refreshToken) {
          headers.Authorization = `Bearer ${refreshToken}`;
        }
        // withCredentials=true 会自动带上 refresh_token cookie
        const response = await axios.post('/api/auth/refresh', null, {
          headers,
          withCredentials: true,
        });
        // 后端返回 ApiResponse 格式: {success, data: {access_token, ...}, message}
        const newToken = response.data?.data?.access_token || response.data?.access_token;
        if (!newToken) {
          throw new Error('Refresh token response missing access_token');
        }
        // P0-6 修复:不再将新 token 写入 localStorage,后端会通过 Set-Cookie 更新 access_token cookie
        // 兼容期:旧客户端仍可写入(已被 withCredentials + cookie 替代)
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        failedQueue.forEach(({ resolve }) => resolve(newToken));
        failedQueue = [];
        return api(originalRequest);
      } catch (refreshError) {
        failedQueue.forEach(({ reject }) => reject(refreshError));
        failedQueue = [];
        // P0-6 修复:清除 localStorage 中可能残留的 token(兼容期数据)
        localStorage.removeItem('token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  }
);

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
  // P0-2 修复:移除 approver 参数,后端从认证用户(JWT/Cookie)获取
  approve: (tx_id: string, reason?: string) =>
    api.post(`/governance/approvals/${tx_id}/approve`, null, { params: { reason } }),
  reject: (tx_id: string, reason: string) =>
    api.post(`/governance/approvals/${tx_id}/reject`, null, { params: { reason } }),
};

export const monitoringApi = {
  getAlerts: (level?: string) => api.get('/monitoring/alerts', { params: { level } }),
  acknowledgeAlert: (alert_id: string) => api.post(`/monitoring/alerts/${alert_id}/acknowledge`),
  getMetrics: () => api.get('/monitoring/metrics'),
};

export const workflowApi = {
  list: () => api.get('/workflow'),
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
  login: (username: string, password: string) => api.post('/auth/login', { username, password }, { _skipRefresh: true }),
  refresh: (token: string) => api.post('/auth/refresh', null, { headers: { Authorization: `Bearer ${token}` }, _skipRefresh: true }),
  me: (token: string) => api.get('/auth/me', { headers: { Authorization: `Bearer ${token}` } }),
};

export const userApi = {
  list: (params?: { role?: string; status?: string; department?: string }) => api.get('/users', { params }),
  create: (data: { username: string; email: string; role?: string; full_name?: string; department?: string }) => api.post('/users', data),
  get: (userId: string) => api.get(`/users/${userId}`),
  update: (userId: string, data: { username?: string; email?: string; role?: string; status?: string; full_name?: string; department?: string }) => api.put(`/users/${userId}`, data),
  delete: (userId: string) => api.delete(`/users/${userId}`),
  activate: (userId: string) => api.post(`/users/${userId}/activate`),
  suspend: (userId: string) => api.post(`/users/${userId}/suspend`),
};

export const teamApi = {
  list: () => api.get('/teams'),
  create: (data: { name: string; description?: string }) => api.post('/teams', data),
  get: (teamId: string) => api.get(`/teams/${teamId}`),
  update: (teamId: string, data: { name?: string; description?: string }) => api.put(`/teams/${teamId}`, data),
  delete: (teamId: string) => api.delete(`/teams/${teamId}`),
  addMember: (teamId: string, data: { user_id: string; username: string; role?: string }) => api.post(`/teams/${teamId}/members`, data),
  removeMember: (teamId: string, userId: string) => api.delete(`/teams/${teamId}/members/${userId}`),
  getMembers: (teamId: string) => api.get(`/teams/${teamId}/members`),
};

export const testApi = {
  execute: (testCases: Array<{
    name: string;
    protocol?: string;
    method?: string;
    url?: string;
    headers?: Record<string, string>;
    body?: Record<string, any>;
    params?: Record<string, any>;
    service?: string;
    grpc_method?: string;
  }>) => api.post('/test/execute', { test_cases: testCases }),
  generate: (spec: Record<string, any>) => api.post('/test/generate', spec),
  getWorkflowTestCases: (workflowId: string) => api.get(`/test/workflow/${workflowId}`),
};

export const diagnoseApi = {
  workflow: (workflowId: string, code?: string, testResults?: Record<string, any>) =>
    api.post('/diagnose/workflow', { workflow_id: workflowId, code, test_results: testResults }),
};

export default api;