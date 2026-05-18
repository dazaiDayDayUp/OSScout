/**
 * TanStack Query Hooks 封装
 *
 * 将后端 API 封装为 React Hooks，自动管理 loading / error / 缓存。
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import client from './client'
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  CompareRequest,
  CompareResponse,
  ReportListResponse,
  ReportResponse,
  RepoHistoryResponse,
  TaskResponse,
} from '@/types/api'

// ═══════════════════════════════════════════════════════════════
// 分析任务
// ═══════════════════════════════════════════════════════════════

/** 提交分析任务 */
export function useSubmitAnalysis() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: AnalyzeRequest): Promise<AnalyzeResponse> => {
      const res = await client.post('/analyze', data)
      return res.data
    },
    onSuccess: () => {
      // 提交成功后，使报告列表缓存失效
      queryClient.invalidateQueries({ queryKey: ['reports'] })
    },
  })
}

/** 查询任务状态（支持轮询） */
export function useTaskStatus(taskId: number | null, options?: { enabled?: boolean }) {
  return useQuery<TaskResponse>({
    queryKey: ['task', taskId],
    queryFn: async () => {
      const res = await client.get(`/tasks/${taskId}`)
      return res.data
    },
    // 仅在 taskId 有效时启用
    enabled: !!taskId && (options?.enabled !== false),
    // 任务未完成时，每 2 秒轮询一次
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 2000 : false
    },
    // 轮询任务的数据不需要长期缓存
    staleTime: 0,
  })
}

// ═══════════════════════════════════════════════════════════════
// 报告
// ═══════════════════════════════════════════════════════════════

/** 获取报告详情 */
export function useReport(reportId: number | null) {
  return useQuery<ReportResponse>({
    queryKey: ['report', reportId],
    queryFn: async () => {
      const res = await client.get(`/reports/${reportId}`)
      return res.data
    },
    enabled: !!reportId,
  })
}

/** 获取报告列表（分页） */
export function useReportList(page: number = 1, pageSize: number = 20) {
  return useQuery<ReportListResponse>({
    queryKey: ['reports', page, pageSize],
    queryFn: async () => {
      const res = await client.get('/reports', {
        params: { page, page_size: pageSize },
      })
      return res.data
    },
  })
}

// ═══════════════════════════════════════════════════════════════
// 仓库
// ═══════════════════════════════════════════════════════════════

/** 获取仓库历史趋势 */
export function useRepoHistory(repoId: number | null) {
  return useQuery<RepoHistoryResponse>({
    queryKey: ['repo-history', repoId],
    queryFn: async () => {
      const res = await client.get(`/repos/${repoId}/history`)
      return res.data
    },
    enabled: !!repoId,
  })
}

// ═══════════════════════════════════════════════════════════════
// 对比
// ═══════════════════════════════════════════════════════════════

/** 多仓库对比分析 */
export function useCompareRepositories() {
  return useMutation({
    mutationFn: async (data: CompareRequest): Promise<CompareResponse> => {
      // 对比接口是同步等待多个 Celery 任务完成的，耗时较长
      // 2 个仓库约 60-90 秒，3 个仓库约 90-120 秒，将超时设为 120 秒
      const res = await client.post('/compare', data, { timeout: 120000 })
      return res.data
    },
  })
}
