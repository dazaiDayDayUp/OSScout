/**
 * 报告详情页
 *
 * 展示单个尽调报告的完整内容：综合评分、各维度详情、关键发现、建议。
 */

import { useParams } from 'react-router-dom'
import { useReport } from '@/api/hooks'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  FileText,
  AlertCircle,
  Users,
  Code2,
  Shield,
  TrendingUp,
  Star,
  GitFork,
  Calendar,
} from 'lucide-react'

/** 评级对应的颜色 */
const RATING_COLORS: Record<string, string> = {
  'A+': 'bg-green-100 text-green-800',
  'A': 'bg-green-100 text-green-800',
  'B+': 'bg-lime-100 text-lime-800',
  'B': 'bg-yellow-100 text-yellow-800',
  'C': 'bg-orange-100 text-orange-800',
  'D': 'bg-red-100 text-red-800',
}

/** 维度配置 */
const DIMENSION_CONFIG: Record<string, { label: string; icon: typeof Users; max: number }> = {
  community: { label: '社区健康度', icon: Users, max: 30 },
  quality: { label: '代码质量', icon: Code2, max: 25 },
  security: { label: '安全评分', icon: Shield, max: 25 },
  evolution: { label: '技术演进', icon: TrendingUp, max: 20 },
}

export default function ReportPage() {
  const { id } = useParams<{ id: string }>()
  const reportId = id ? parseInt(id, 10) : null

  const { data: report, isLoading, isError, error } = useReport(reportId)

  // 加载中状态
  if (isLoading) {
    return <ReportSkeleton />
  }

  // 错误状态
  if (isError || !report) {
    return (
      <div className="mx-auto max-w-4xl">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {error instanceof Error ? error.message : '报告加载失败'}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  const { overall, dimensions, repo, key_findings, recommendations } = report

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {repo.name || '未知仓库'}
          </h1>
          <p className="text-sm text-gray-500">
            {repo.owner}/{repo.name}
          </p>
        </div>
        <Badge className={RATING_COLORS[overall.rating] || 'bg-gray-100 text-gray-800'}>
          {overall.rating}
        </Badge>
      </div>

      {/* 综合评分卡片 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            综合评分
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-end gap-2">
            <span className="text-5xl font-bold text-gray-900">
              {overall.score}
            </span>
            <span className="mb-1.5 text-lg text-gray-400">
              / {overall.max_score}
            </span>
            <span className="mb-1.5 ml-2 text-sm text-gray-500">
              ({Math.round(overall.percentage)}%)
            </span>
          </div>

          {/* 仓库元信息 */}
          <div className="mt-4 flex flex-wrap gap-4 text-sm text-gray-500">
            {repo.star_count !== undefined && (
              <span className="flex items-center gap-1">
                <Star className="h-4 w-4" /> {repo.star_count.toLocaleString()}
              </span>
            )}
            {repo.fork_count !== undefined && (
              <span className="flex items-center gap-1">
                <GitFork className="h-4 w-4" /> {repo.fork_count.toLocaleString()}
              </span>
            )}
            {repo.primary_language && (
              <span className="rounded bg-gray-100 px-2 py-0.5">
                {repo.primary_language}
              </span>
            )}
            {report.created_at && (
              <span className="flex items-center gap-1">
                <Calendar className="h-4 w-4" />
                {new Date(report.created_at).toLocaleDateString('zh-CN')}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 各维度评分 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {Object.entries(DIMENSION_CONFIG).map(([key, config]) => {
          const dim = dimensions[key]
          if (!dim) return null
          const Icon = config.icon
          return (
            <Card key={key}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Icon className="h-5 w-5 text-primary-500" />
                  {config.label}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* 分数 */}
                <div className="flex items-end gap-1">
                  <span className="text-3xl font-bold">{dim.score}</span>
                  <span className="text-sm text-gray-400">/ {config.max}</span>
                </div>

                {/* 进度条 */}
                <div className="h-2 overflow-hidden rounded-full bg-gray-100">
                  <div
                    className="h-full rounded-full bg-primary-500 transition-all"
                    style={{ width: `${dim.percentage}%` }}
                  />
                </div>

                {/* 关键发现 */}
                {dim.findings.length > 0 && (
                  <ul className="space-y-1">
                    {dim.findings.map((finding, i) => (
                      <li key={i} className="text-sm text-gray-600">
                        • {finding}
                      </li>
                    ))}
                  </ul>
                )}

                {/* 风险 */}
                {dim.risks.length > 0 && (
                  <div className="space-y-1">
                    {dim.risks.map((risk, i) => (
                      <p key={i} className="text-sm text-orange-600">
                        ⚠ {risk}
                      </p>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* 关键发现 */}
      {key_findings.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>关键发现</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {key_findings.map((finding, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <span className="mt-0.5 text-primary-500">•</span>
                  {finding}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* 建议 */}
      {recommendations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>建议</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {recommendations.map((rec, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <span className="mt-0.5 text-green-500">✓</span>
                  {rec}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

/** 报告加载骨架屏 */
function ReportSkeleton() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-32" />
        </div>
        <Skeleton className="h-6 w-12" />
      </div>
      <Skeleton className="h-32 w-full" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-48 w-full" />
        ))}
      </div>
    </div>
  )
}
