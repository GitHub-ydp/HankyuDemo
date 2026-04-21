import api from './api';
import type {
  EmailAnalyzeResponse,
  EmailIndexResponse,
  EmailSearchResponse,
} from '../types/email';

export const emailApi = {
  indexFromImap: (params: {
    force?: boolean;
    limit?: number;
    since_date?: string;
  }) =>
    api.post<unknown, EmailIndexResponse>('/emails/index/imap', null, {
      params,
      timeout: 300000,
    }),

  search: (q: string, top_k = 10) =>
    api.get<unknown, EmailSearchResponse>('/emails/search', {
      params: { q, top_k },
    }),

  analyze: (q: string, top_k = 15) =>
    api.get<unknown, EmailAnalyzeResponse>('/emails/analyze', {
      params: { q, top_k },
      timeout: 60000,
    }),

  // 生成并下载 HTML 脉络报告：直接请求后端并触发浏览器下载
  downloadReport: async (q: string, top_k = 15) => {
    const baseURL = api.defaults.baseURL || '';
    const url = `${baseURL}/emails/report?q=${encodeURIComponent(q)}&top_k=${top_k}`;

    const response = await fetch(url, { method: 'GET' });
    if (!response.ok) {
      throw new Error(`生成报告失败 (HTTP ${response.status})`);
    }

    // 从 Content-Disposition 中解析文件名
    const disposition = response.headers.get('content-disposition') || '';
    let filename = 'email_report.html';
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8Match) {
      filename = decodeURIComponent(utf8Match[1]);
    } else {
      const asciiMatch = disposition.match(/filename="?([^";]+)"?/i);
      if (asciiMatch) filename = asciiMatch[1];
    }

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(objectUrl);

    return { filename, count: Number(response.headers.get('x-email-count') || 0) };
  },
};
