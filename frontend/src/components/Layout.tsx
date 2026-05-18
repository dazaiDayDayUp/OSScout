/**
 * 全局布局组件
 *
 * 包含顶部导航栏和页面内容区，所有页面共享此布局。
 */

import { Link, useLocation } from 'react-router-dom'
import { GitBranch, BarChart3, FileText } from 'lucide-react'

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()

  const navItems = [
    { path: '/', label: '新建分析', icon: GitBranch },
    { path: '/reports', label: '报告列表', icon: FileText },
    { path: '/compare', label: '对比分析', icon: BarChart3 },
  ]

  return (
    <div className="min-h-screen bg-background">
      {/* 顶部导航栏 */}
      <header className="sticky top-0 z-50 border-b bg-white/80 backdrop-blur-sm">
        <div className="mx-auto flex h-16 max-w-7xl items-center px-4 sm:px-6">
          {/* Logo */}
          <Link to="/" className="mr-8 flex items-center gap-2">
            <GitBranch className="h-6 w-6 text-primary-600" />
            <span className="text-xl font-bold text-gray-900">OSScout</span>
          </Link>

          {/* 导航链接 */}
          <nav className="flex items-center gap-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-primary-50 text-primary-700'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              )
            })}
          </nav>
        </div>
      </header>

      {/* 页面内容 */}
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        {children}
      </main>
    </div>
  )
}
