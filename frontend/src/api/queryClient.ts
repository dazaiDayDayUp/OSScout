/**
 * TanStack Query 客户端配置
 *
 * 管理全局缓存策略、重试逻辑、数据刷新行为。
 */

import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 数据默认缓存 5 分钟
      staleTime: 1000 * 60 * 5,
      // 失败时重试 1 次
      retry: 1,
      // 窗口重新聚焦时自动刷新（适合报告列表）
      refetchOnWindowFocus: true,
    },
    mutations: {
      //  mutation 失败不重试，由用户手动触发更合理
      retry: false,
    },
  },
})
