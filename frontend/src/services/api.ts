import axios from 'axios';
import type { ApiResponse } from '../types';

const resolveApiBaseUrl = () => {
  const envBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
  if (envBaseUrl) {
    return envBaseUrl;
  }

  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname || 'localhost';
    return `${protocol}//${hostname}:8000/api/v1`;
  }

  return 'http://localhost:8000/api/v1';
};

const api = axios.create({
  baseURL: resolveApiBaseUrl(),
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
});

// 响应拦截器
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.message || error.response?.data?.detail || error.message || '请求失败';
    return Promise.reject(new Error(message));
  }
);

// --- 港口 ---
export const portApi = {
  list: (params?: Record<string, unknown>) =>
    api.get<unknown, ApiResponse>('/ports', { params }),
  regions: () =>
    api.get<unknown, ApiResponse>('/ports/regions'),
  get: (id: number) =>
    api.get<unknown, ApiResponse>(`/ports/${id}`),
};

// --- 船司 ---
export const carrierApi = {
  list: (params?: Record<string, unknown>) =>
    api.get<unknown, ApiResponse>('/carriers', { params }),
  get: (id: number) => api.get<unknown, ApiResponse>(`/carriers/${id}`),
  create: (data: Record<string, unknown>) => api.post<unknown, ApiResponse>('/carriers', data),
  update: (id: number, data: Record<string, unknown>) => api.put<unknown, ApiResponse>(`/carriers/${id}`, data),
  delete: (id: number) => api.delete<unknown, ApiResponse>(`/carriers/${id}`),
};

// --- 费率 ---
export const rateApi = {
  list: (params?: Record<string, unknown>) =>
    api.get<unknown, ApiResponse>('/rates', { params }),
  get: (id: number) =>
    api.get<unknown, ApiResponse>(`/rates/${id}`),
  stats: () =>
    api.get<unknown, ApiResponse>('/rates/stats'),
  compare: (originPortId: number, destinationPortId: number) =>
    api.get<unknown, ApiResponse>('/rates/compare', {
      params: { origin_port_id: originPortId, destination_port_id: destinationPortId },
    }),
  updateStatus: (id: number, status: string) =>
    api.put<unknown, ApiResponse>(`/rates/${id}/status`, null, { params: { status } }),
  batchUpdateStatus: (batchId: string, status: string) =>
    api.put<unknown, ApiResponse>(`/rates/batch/${batchId}/status`, null, { params: { status } }),
  delete: (id: number) =>
    api.delete<unknown, ApiResponse>(`/rates/${id}`),

  // 上传与解析
  uploadAndParse: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<unknown, ApiResponse>('/rates/upload/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
  },
  confirmImport: (batchId: string) =>
    api.post<unknown, ApiResponse>(`/rates/upload/confirm`, null, {
      params: { batch_id: batchId },
    }),
};

// --- AI 解析 ---
export const aiParseApi = {
  parseEmailText: (text: string) => {
    const formData = new FormData();
    formData.append('text', text);
    return api.post<unknown, ApiResponse>('/ai/parse-email-text', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
  },
  parseWechatImage: (file: File, context?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (context) formData.append('context', context);
    return api.post<unknown, ApiResponse>('/ai/parse-wechat-image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
  },
  // 拉取邮箱最近邮件列表（IMAP 直连）
  listInboxEmails: (params?: { limit?: number; since_date?: string }) =>
    api.get<unknown, ApiResponse>('/ai/inbox-emails', {
      params,
      timeout: 120000,
    }),
  // 对邮箱列表中选定的某封邮件进行 AI 费率识别
  parseInboxEmail: (cacheKey: string) => {
    const formData = new FormData();
    formData.append('cache_key', cacheKey);
    return api.post<unknown, ApiResponse>('/ai/parse-inbox-email', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000,
    });
  },
  // 对邮件中的某张图片附件进行 AI 视觉识别
  parseInboxAttachment: (cacheKey: string, attachmentIndex: number) => {
    const formData = new FormData();
    formData.append('cache_key', cacheKey);
    formData.append('attachment_index', String(attachmentIndex));
    return api.post<unknown, ApiResponse>('/ai/parse-inbox-attachment', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000,
    });
  },
  // 上传本地 Outlook .msg 文件，落到 inbox 缓存（后续复用 parseInboxEmail / parseInboxAttachment）
  uploadMsgFile: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<unknown, ApiResponse>('/ai/upload-msg-file', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
  },
  confirmImport: (batchId: string) =>
    api.post<unknown, ApiResponse>('/ai/confirm', null, {
      params: { batch_id: batchId },
    }),
};

// --- 管理员（演示用） ---
export const adminApi = {
  resetRates: () =>
    api.post<unknown, ApiResponse>('/admin/reset-rates'),
};

// --- PKG 入札包 ---
export const pkgApi = {
  upload: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<unknown, ApiResponse>('/pkg/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    });
  },
  fill: (sessionId: string, overwrite = false) =>
    api.post<unknown, ApiResponse>(`/pkg/fill/${sessionId}`, null, {
      params: { overwrite },
    }),
  downloadUrl: (sessionId: string) =>
    `${api.defaults.baseURL}/pkg/download/${sessionId}`,
  rates: () =>
    api.get<unknown, ApiResponse>('/pkg/rates'),
};

export default api;
