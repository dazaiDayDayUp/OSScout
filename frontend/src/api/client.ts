/**
 * Axios HTTP 客户端封装
 *
 * 统一配置 baseURL、请求/响应拦截器、错误处理。
 * 上层使用 TanStack Query 管理状态，不直接在此处理 loading。
 */

import axios, { AxiosError, AxiosInstance } from 'axios'

// 创建 axios 实例
// baseURL 用相对路径 /api/v1，Vite dev server 会通过 proxy 转发到后端
const client: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器：可在此添加认证 token 等
client.interceptors.request.use(
  (config) => {
    // 未来如需 JWT 认证，在此注入 Authorization header
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器：统一错误格式化
client.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // 将后端返回的错误信息包装为统一格式
    const message = extractErrorMessage(error)
    const customError = new Error(message)
    // 保留原始 error 以便调试
    ;(customError as Error & { original: AxiosError }).original = error
    throw customError
  },
)

/**
 * 从 AxiosError 中提取人类可读的错误信息
 */
function extractErrorMessage(error: AxiosError): string {
  if (error.response) {
    // 后端返回了错误响应
    const data = error.response.data as { detail?: string; message?: string }
    if (data?.detail) return data.detail
    if (data?.message) return data.message
    return `请求失败 (${error.response.status})`
  }
  if (error.request) {
    // 请求已发出但没有收到响应
    return '无法连接到服务器，请检查后端服务是否启动'
  }
  return error.message || '未知错误'
}

export default client
