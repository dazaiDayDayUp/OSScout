/**
 * 应用入口 — 路由配置
 *
 * 使用 React Router v7 配置所有页面路由，包裹在 QueryClientProvider 中。
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './api/queryClient'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'
import ReportPage from './pages/ReportPage'
import ReportListPage from './pages/ReportListPage'

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/reports" element={<ReportListPage />} />
            <Route path="/reports/:id" element={<ReportPage />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
