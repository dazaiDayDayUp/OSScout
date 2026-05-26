/**
 * 首页 — 提交分析表单 + 任务状态轮询
 *
 * 用户输入 GitHub 仓库地址，提交分析任务后自动轮询任务状态，
 * 完成后自动跳转到报告详情页。
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSubmitAnalysis, useTaskStatus } from '@/api/hooks'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { GitBranch, Loader2, CheckCircle, AlertCircle, ArrowRight, Mail } from 'lucide-react'

/** 示例仓库 */
const EXAMPLE_REPOS = [
  'https://github.com/vercel/next.js',
  'https://github.com/python-poetry/poetry',
  'https://github.com/microsoft/vscode',
  'https://github.com/facebook/react',
]

export default function HomePage() {
  const navigate = useNavigate()
  const [repoUrl, setRepoUrl] = useState('')
  const [notifyEmail, setNotifyEmail] = useState('')
  const [taskId, setTaskId] = useState<number | null>(null)
  const [submittedUrl, setSubmittedUrl] = useState('')

  // 提交分析任务 mutation
  const submitMutation = useSubmitAnalysis()

  // 任务状态查询（自动轮询）
  const { data: task } = useTaskStatus(taskId)

  // 任务完成后自动跳转报告页
  useEffect(() => {
    if (task?.status === 'completed' && task.report_id) {
      const timer = setTimeout(() => {
        navigate(`/reports/${task.report_id}`)
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [task, navigate])

  // 提交表单
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!repoUrl.trim()) return

    setSubmittedUrl(repoUrl.trim())
    try {
      const payload: { repo_url: string; notify_email?: string } = {
        repo_url: repoUrl.trim(),
      }
      // 仅在填写了有效邮箱时才带上 notify_email
      const email = notifyEmail.trim()
      if (email && email.includes('@')) {
        payload.notify_email = email
      }
      const result = await submitMutation.mutateAsync(payload)
      setTaskId(result.task_id)
    } catch {
      // 错误已在 mutation 中处理，此处只需让 UI 展示错误状态
    }
  }

  // 任务状态对应的颜色和图标
  const getStatusDisplay = (status: string) => {
    switch (status) {
      case 'pending':
        return { label: '排队中', color: 'bg-yellow-100 text-yellow-800', icon: Loader2 }
      case 'running':
        return { label: '分析中', color: 'bg-blue-100 text-blue-800', icon: Loader2 }
      case 'completed':
        return { label: '已完成', color: 'bg-green-100 text-green-800', icon: CheckCircle }
      case 'failed':
        return { label: '失败', color: 'bg-red-100 text-red-800', icon: AlertCircle }
      default:
        return { label: status, color: 'bg-gray-100 text-gray-800', icon: Loader2 }
    }
  }

  const isSubmitting = submitMutation.isPending
  const isPolling = !!taskId && task?.status !== 'completed' && task?.status !== 'failed'

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      {/* 页面标题 */}
      <div className="text-center">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">
          开源项目尽调分析
        </h1>
        <p className="mt-2 text-gray-500">
          输入 GitHub 仓库地址，自动生成社区健康、代码质量、安全、技术演进四维评估报告
        </p>
      </div>

      {/* 提交表单 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitBranch className="h-5 w-5" />
            提交分析任务
          </CardTitle>
          <CardDescription>
            支持任何公开的 GitHub 仓库，分析耗时约 1-3 分钟
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex gap-2">
              <Input
                type="url"
                placeholder="https://github.com/owner/repo"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                disabled={isSubmitting || isPolling}
                className="flex-1"
                required
              />
              <Button
                type="submit"
                disabled={isSubmitting || isPolling || !repoUrl.trim()}
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    提交中
                  </>
                ) : (
                  <>
                    开始分析
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </>
                )}
              </Button>
            </div>

            {/* 邮箱通知（可选） */}
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-gray-400" />
              <Input
                type="email"
                placeholder="分析完成后邮件通知我（可选）"
                value={notifyEmail}
                onChange={(e) => setNotifyEmail(e.target.value)}
                disabled={isSubmitting || isPolling}
                className="flex-1 text-sm"
              />
            </div>

            {/* 提交错误提示 */}
            {submitMutation.isError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  {submitMutation.error instanceof Error
                    ? submitMutation.error.message
                    : '提交失败'}
                </AlertDescription>
              </Alert>
            )}
          </form>

          {/* 任务状态展示 */}
          {task && (
            <div className="mt-6 rounded-lg border bg-gray-50/50 p-4">
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-gray-900">
                    {submittedUrl}
                  </p>
                  <p className="text-xs text-gray-500">
                    任务 ID: {task.task_id}
                  </p>
                  {notifyEmail.trim() && (
                    <p className="flex items-center gap-1 text-xs text-blue-600">
                      <Mail className="h-3 w-3" />
                      分析完成后将邮件通知: {notifyEmail.trim()}
                    </p>
                  )}
                </div>
                {(() => {
                  const { label, color, icon: StatusIcon } = getStatusDisplay(task.status)
                  return (
                    <Badge className={color}>
                      <StatusIcon className="mr-1 h-3 w-3" />
                      {label}
                    </Badge>
                  )
                })()}
              </div>

              {/* 进度条动画 */}
              {(task.status === 'pending' || task.status === 'running') && (
                <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
                  <div
                    className="h-full animate-pulse rounded-full bg-blue-500"
                    style={{ width: task.status === 'running' ? '60%' : '20%' }}
                  />
                </div>
              )}

              {/* 完成提示 */}
              {task.status === 'completed' && task.report_id && (
                <p className="mt-2 text-sm text-green-600">
                  分析完成，正在跳转报告页...
                </p>
              )}

              {/* 失败提示 */}
              {task.status === 'failed' && task.error_message && (
                <p className="mt-2 text-sm text-red-600">
                  错误：{task.error_message}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 示例仓库 */}
      <div className="space-y-3">
        <p className="text-sm font-medium text-gray-700">快速体验 — 示例仓库</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {EXAMPLE_REPOS.map((url) => (
            <button
              key={url}
              onClick={() => setRepoUrl(url)}
              className="rounded-lg border bg-white px-4 py-3 text-left text-sm text-gray-700 transition-colors hover:border-primary-300 hover:bg-primary-50"
            >
              {url.replace('https://github.com/', '')}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
