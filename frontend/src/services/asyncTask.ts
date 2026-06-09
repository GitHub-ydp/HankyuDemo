import api from './api';
import type { ApiResponse } from '../types';

interface TaskState {
  task_id: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed';
  result: unknown;
  error: string | null;
}

/**
 * 轮询异步任务直到终态。
 * @returns 成功时返回后台任务的 result（= 原 HTTP 响应 data）。
 */
export async function pollTask(
  taskId: string,
  opts?: { interval?: number; timeout?: number }
): Promise<unknown> {
  const interval = opts?.interval ?? 1500;
  const timeout = opts?.timeout ?? 300000;
  const start = Date.now();

  for (;;) {
    const resp = (await api.get<unknown, ApiResponse>(`/tasks/${taskId}`)) as ApiResponse;
    const state = resp.data as TaskState;
    if (state.status === 'succeeded') return state.result;
    if (state.status === 'failed') throw new Error(state.error || 'AI 处理失败');
    if (Date.now() - start > timeout) throw new Error('AI 处理超时，请稍后重试');
    await new Promise((r) => setTimeout(r, interval));
  }
}
