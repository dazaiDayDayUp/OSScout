/**
 * 多仓库对比页
 *
 * 输入多个 GitHub 仓库地址，并排对比它们的尽调评分。
 * 包含综合评分对比条形图、各维度雷达图、关键差异高亮。
 */

import { useState } from 'react'
import { useCompareRepositories } from '@/api/hooks'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import ScoreBadge from '@/components/ScoreBadge'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import {
  GitCompare,
  Plus,
  X,
  AlertCircle,
  Loader2,
  Trophy,
  ArrowRight,
  TrendingUp,
  AlertTriangle,
} from 'lucide-react'

/** 维度中文名 */
const DIMENSION_NAMES: Record<string, string> = {
  community: '社区健康度',
  quality: '代码质量',
  security: '安全评分',
  evolution: '技术演进',
}

export default function ComparePage() {
  const [urls, setUrls] = useState(['', ''])
  const [submitted, setSubmitted] = useState(false)

  const compareMutation = useCompareRepositories()
  const result = compareMutation.data

  const addUrl = () => {
    if (urls.length < 5) setUrls([...urls, ''])
  }

  const removeUrl = (index: number) => {
    if (urls.length > 2) {
      setUrls(urls.filter((_, i) => i !== index))
    }
  }

  const updateUrl = (index: number, value: string) => {
    const next = [...urls]
    next[index] = value
    setUrls(next)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const validUrls = urls.filter((u) => u.trim()).map((u) => u.trim())
    if (validUrls.length < 2) return

    setSubmitted(true)
    await compareMutation.mutateAsync({ repo_urls: validUrls })
  }

  // 构建综合评分对比数据
  const overallData = result?.repositories.map((repo) => ({
    name: `${repo.owner}/${repo.name}`,
    总分: repo.overall_score,
    社区: repo.community_score,
    质量: repo.quality_score,
    安全: repo.security_score,
    演进: repo.evolution_score,
  })) ?? []

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      {/* 标题 */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">
          多仓库对比分析
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          同时对比 2-5 个开源项目的尽调评分，快速做出选型决策
        </p>
      </div>

      {/* 输入表单 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <GitCompare className="h-5 w-5" />
            选择仓库
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-3">
            {urls.map((url, i) => (
              <div key={i} className="flex gap-2">
                <Input
                  type="url"
                  placeholder={`仓库 ${i + 1}: https://github.com/owner/repo`}
                  value={url}
                  onChange={(e) => updateUrl(i, e.target.value)}
                  className="flex-1"
                  required={i < 2}
                />
                {urls.length > 2 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeUrl(i)}
                    className="shrink-0 text-gray-400 hover:text-gray-600"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
            ))}

            <div className="flex items-center gap-3">
              {urls.length < 5 && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={addUrl}
                  className="text-gray-500"
                >
                  <Plus className="mr-1 h-4 w-4" />
                  添加仓库
                </Button>
              )}
              <Button
                type="submit"
                disabled={compareMutation.isPending}
                className="ml-auto"
              >
                {compareMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    分析中...
                  </>
                ) : (
                  <>
                    开始对比
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </>
                )}
              </Button>
            </div>

            {compareMutation.isError && (
              <Alert variant="destructive" className="mt-3">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  {compareMutation.error instanceof Error
                    ? compareMutation.error.message
                    : '对比分析失败'}
                </AlertDescription>
              </Alert>
            )}
          </form>
        </CardContent>
      </Card>

      {/* 加载骨架 */}
      {compareMutation.isPending && submitted && <CompareSkeleton />}

      {/* 对比结果 */}
      {result && (
        <div className="space-y-6">
          {/* 排名卡片 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Trophy className="h-4 w-4 text-gray-500" />
                综合排名
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {result.ranking.map((item) => (
                  <div
                    key={item.rank}
                    className="flex items-center gap-4 rounded-lg border px-4 py-3"
                  >
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
                        item.rank === 1
                          ? 'bg-amber-50 text-amber-600'
                          : item.rank === 2
                            ? 'bg-gray-50 text-gray-500'
                            : 'bg-gray-50 text-gray-400'
                      }`}
                    >
                      {item.rank}
                    </span>
                    <span className="flex-1 font-medium text-gray-900">{item.repo}</span>
                    <span className="text-lg font-bold tabular-nums text-gray-900">
                      {item.score}
                    </span>
                    <ScoreBadge rating={item.rating} />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* 综合评分对比条形图 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <TrendingUp className="h-4 w-4 text-gray-500" />
                综合评分对比
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart
                  data={overallData}
                  margin={{ top: 8, right: 8, left: 0, bottom: 8 }}
                  barCategoryGap="20%"
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    axisLine={false}
                    tickLine={false}
                    interval={0}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#94a3b8' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: '8px',
                      border: '1px solid #e2e8f0',
                      fontSize: '13px',
                    }}
                  />
                  <Legend
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontSize: '12px' }}
                  />
                  <Bar dataKey="社区" fill="#0d9488" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="质量" fill="#2563eb" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="安全" fill="#475569" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="演进" fill="#d97706" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* 关键差异 */}
          {result.key_differences.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <AlertTriangle className="h-4 w-4 text-gray-500" />
                  关键差异
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {result.key_differences.map((diff, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-4 rounded-lg border px-4 py-3"
                    >
                      {/* 维度名称 */}
                      <span className="w-20 shrink-0 text-sm font-medium text-gray-500">
                        {DIMENSION_NAMES[diff.dimension] || diff.dimension}
                      </span>

                      {/* 最低分 — 左侧 */}
                      <div className="flex flex-1 items-center justify-end gap-2">
                        <span className="text-sm text-gray-500">
                          {diff.lowest.repo}
                        </span>
                        <span className="text-sm font-semibold tabular-nums text-gray-400">
                          {diff.lowest.score}
                        </span>
                      </div>

                      {/* 差距 — 中间醒目 */}
                      <div className="flex shrink-0 items-center gap-1.5 px-3"
                      >
                        <span className="text-xs text-gray-300"
                        >←</span>
                        <span className={`rounded-md px-2 py-0.5 text-sm font-bold tabular-nums ${
                          diff.gap >= 15
                            ? 'bg-[#fef2f2] text-[#b91c1c]'
                            : diff.gap >= 8
                              ? 'bg-[#fff7ed] text-[#c2410c]'
                              : 'bg-gray-50 text-gray-500'
                        }`}
                        >
                          差距 {diff.gap}
                        </span>
                        <span className="text-xs text-gray-300"
                        >→</span>
                      </div>

                      {/* 最高分 — 右侧 */}
                      <div className="flex flex-1 items-center gap-2">
                        <span className="text-sm font-bold tabular-nums text-gray-900">
                          {diff.highest.score}
                        </span>
                        <span className="text-sm text-gray-900">
                          {diff.highest.repo}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* 各仓库详细卡片 */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {result.repositories.map((repo) => (
              <Card key={repo.repo_id}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center justify-between text-base">
                    <span>
                      {repo.owner}/{repo.name}
                    </span>
                    <ScoreBadge rating={repo.overall_rating} />
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <p className="text-xs text-gray-400">社区健康度</p>
                      <p className="text-lg font-semibold tabular-nums">
                        {repo.community_score}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs text-gray-400">代码质量</p>
                      <p className="text-lg font-semibold tabular-nums">
                        {repo.quality_score}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs text-gray-400">安全评分</p>
                      <p className="text-lg font-semibold tabular-nums">
                        {repo.security_score}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs text-gray-400">技术演进</p>
                      <p className="text-lg font-semibold tabular-nums">
                        {repo.evolution_score}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** 对比加载骨架 */
function CompareSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-[200px]" />
      <Skeleton className="h-[320px]" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Skeleton className="h-[200px]" />
        <Skeleton className="h-[200px]" />
      </div>
    </div>
  )
}
