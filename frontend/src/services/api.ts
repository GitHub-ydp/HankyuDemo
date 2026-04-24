import axios from 'axios';
import type { ApiResponse } from '../types';
import type { BiddingAutoFillResponse } from '../types/bidding';

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
    const raw = error.response?.data ?? {};
    const detail = raw.detail;
    let detailMsg: string | undefined;
    if (Array.isArray(detail)) {
      // FastAPI 422 校验错误：detail 是 [{loc, msg, type}, ...]，取每条 msg 连接
      detailMsg = detail
        .map((e: { msg?: string; loc?: unknown[] }) => {
          if (typeof e?.msg !== 'string') return '';
          const loc = Array.isArray(e.loc) ? e.loc.slice(-1).join('.') : '';
          return loc ? `${loc}: ${e.msg}` : e.msg;
        })
        .filter(Boolean)
        .join('; ');
    } else if (typeof detail === 'string') {
      detailMsg = detail;
    }
    const message = raw.message || detailMsg || error.message || '请求失败';
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
  compare: (params: {
    rateType?: string;
    originPortId?: number;
    destinationPortId?: number;
    originText?: string;
    destinationText?: string;
  }) =>
    api.get<unknown, ApiResponse>('/rates/compare', {
      params: {
        rate_type: params.rateType,
        origin_port_id: params.originPortId,
        destination_port_id: params.destinationPortId,
        origin_text: params.originText,
        destination_text: params.destinationText,
      },
    }),
  updateStatus: (id: number, status: string) =>
    api.put<unknown, ApiResponse>(`/rates/${id}/status`, null, { params: { status } }),
  batchUpdateStatus: (batchId: string, status: string) =>
    api.put<unknown, ApiResponse>(`/rates/batch/${batchId}/status`, null, { params: { status } }),
  delete: (id: number) =>
    api.delete<unknown, ApiResponse>(`/rates/${id}`),

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

// --- 系统设置 · AI 参数（T-ST） ---
export const settingsApi = {
  getAIConfig: () => api.get<unknown, ApiResponse>('/admin/settings/ai'),
  updateAIConfig: (patch: Record<string, unknown>) =>
    api.patch<unknown, ApiResponse>('/admin/settings/ai', patch),
  testConnection: () =>
    api.post<unknown, ApiResponse>('/admin/settings/ai/test-connection', {}),
  resetAIConfig: () =>
    api.post<unknown, ApiResponse>('/admin/settings/ai/reset', {}),
};

// --- Step1 Rate Batches（Air / Ocean / Ocean_NGB 标准模板批次） ---
export const rateBatchApi = {
  upload: (file: File, parserHint?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (parserHint) formData.append('parser_hint', parserHint);
    return api.post<unknown, ApiResponse>('/rate-batches/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
  },
  list: (params?: { page?: number; page_size?: number; batch_status?: string }) =>
    api.get<unknown, ApiResponse>('/rate-batches', { params }),
  detail: (batchId: string) =>
    api.get<unknown, ApiResponse>(`/rate-batches/${batchId}`),
  diff: (batchId: string) =>
    api.get<unknown, ApiResponse>(`/rate-batches/${batchId}/diff`),
  activate: (batchId: string, body: { dry_run: boolean; force?: boolean; selected_row_indices?: number[] | null }) =>
    api.post<unknown, ApiResponse>(`/rate-batches/${batchId}/activate`, body),
  downloadUrl: (batchId: string) =>
    `${api.defaults.baseURL}/rate-batches/${batchId}/download`,
};

// --- Bidding (T-B10 v0.1 入札对应 / PkgAutoFill) ---
export const biddingApi = {
  autoFill: (
    file: File,
    onUploadProgress?: (percent: number) => void
  ): Promise<BiddingAutoFillResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<unknown, BiddingAutoFillResponse>('/bidding/auto-fill', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
      onUploadProgress: (evt) => {
        if (!onUploadProgress) return;
        const total = evt.total || file.size || 1;
        const pct = Math.min(100, Math.round(((evt.loaded || 0) / total) * 100));
        onUploadProgress(pct);
      },
    });
  },
  downloadUrl: (token: string) =>
    `${api.defaults.baseURL}/bidding/download/${token}`,
};

export default api;
