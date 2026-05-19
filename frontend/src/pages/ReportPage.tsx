/**
 * 报告详情页（Phase 3 增强版）
 *
 * 展示单个尽调报告的完整内容：
 * - 综合评分仪表盘
 * - 各维度条形图 + 详情卡片（含 reasoning 折叠面板）
 * - RAG 知识库校准引用
 * - 维度间冲突检测
 * - 综合报告（Synthesis Agent）
 *
 * 采用卡片式布局，信息密度高，配色克制专业。
 */

import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useReport } from '@/api/hooks'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import ScoreGauge from '@/components/ScoreGauge'
import ScoreBadge from '@/components/ScoreBadge'
import DimensionBarChart from '@/components/DimensionBarChart'
import {
  FileText,
  AlertCircle,
  Users,
  Code2,
  Shield,
  TrendingUp,
  Lightbulb,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  BrainCircuit,
  BookOpen,
  Zap,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'

/** 维度配置 */
const DIMENSION_CONFIG: Record<string, { label: string; icon: typeof Users; max: number }> = {
  community: { label: '社区健康度', icon: Users, max: 30 },
  quality: { label: '代码质量', icon: Code2, max: 25 },
  security: { label: '安全评分', icon: Shield, max: 25 },
  evolution: { label: '技术演进', icon: TrendingUp, max: 20 },
}

/** 维度配色 — 用于卡片边框和图标 */
const DIMENSION_ACCENT: Record<string, string> = {
  community: 'border-l-teal-500',
  quality: 'border-l-blue-500',
  security: 'border-l-slate-500',
  evolution: 'border-l-amber-500',
}

/** 风险等级颜色 */
const RISK_LEVEL_COLORS: Record<string, string> = {
  high: 'bg-red-50 text-red-700 border-red-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  low: 'bg-gray-50 text-gray-600 border-gray-200',
}

export default function ReportPage() {
  const { id } = useParams<{ id: string }>()
  const reportId = id ? parseInt(id, 10) : null

  const { data: report, isLoading, isError, error } = useReport(reportId)

  if (isLoading) {
    return <ReportSkeleton />
  }

  if (isError || !report) {
    return (
      <div className="mx-auto max-w-5xl">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {error instanceof Error ? error.message : '报告加载失败'}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  const {
    overall,
    dimensions,
    repo,
    key_findings,
    recommendations,
    calibrations,
    conflicts,
    react_summary,
    synthesis,
  } = report

  // 构建条形图数据
  const barChartData = Object.entries(DIMENSION_CONFIG).map(([key, config]) => {
    const dim = dimensions[key]
    return {
      name: config.label,
      key,
      score: dim?.score ?? 0,
      max: config.max,
      percentage: dim?.percentage ?? 0,
    }
  })

  // 综合报告数据
  const hasSynthesis = synthesis && 'executive_summary' in synthesis && synthesis.executive_summary

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      {/* 页面标题区 */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            {repo.name || '未知仓库'}
          </h1>
          <a
            href={repo.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
          >
            {repo.owner}/{repo.name}
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
        <ScoreBadge rating={overall.rating} />
      </div>

      {/* 综合评分区 — 仪表盘 + 元信息 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {/* 环形图 */}
        <Card className="md:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-gray-600">
              <FileText className="h-4 w-4" />
              综合评分
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-center py-4">
            <ScoreGauge
              score={overall.score}
              maxScore={overall.max_score}
              rating={overall.rating}
              size={140}
              strokeWidth={10}
            />
            <div className="mt-3 text-center">
              <span className="text-sm text-gray-500">
                得分率 {Math.round(overall.percentage)}%
              </span>
            </div>
          </CardContent>
        </Card>

        {/* 仓库元信息 + ReAct 总结 */}
        <Card className="md:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600">
              仓库概览
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              {repo.star_count !== undefined && (
                <div className="space-y-1">
                  <p className="text-xs text-gray-400">Stars</p>
                  <p className="text-lg font-semibold tabular-nums text-gray-900">
                    {repo.star_count.toLocaleString()}
                  </p>
                </div>
              )}
              {repo.fork_count !== undefined && (
                <div className="space-y-1">
                  <p className="text-xs text-gray-400">Forks</p>
                  <p className="text-lg font-semibold tabular-nums text-gray-900">
                    {repo.fork_count.toLocaleString()}
                  </p>
                </div>
              )}
              {repo.primary_language && (
                <div className="space-y-1">
                  <p className="text-xs text-gray-400">主要语言</p>
                  <p className="text-lg font-semibold text-gray-900">
                    {repo.primary_language}
                  </p>
                </div>
              )}
              {report.created_at && (
                <div className="space-y-1">
                  <p className="text-xs text-gray-400">分析时间</p>
                  <p className="text-sm font-medium text-gray-900">
                    {new Date(report.created_at).toLocaleDateString('zh-CN')}
                  </p>
                </div>
              )}
            </div>

            {/* ReAct 总结 */}
            {react_summary && (
              <div className="mt-4 rounded-lg bg-gray-50 px-4 py-3">
                <p className="flex items-start gap-2 text-sm text-gray-700">
                  <Zap className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                  <span className="leading-relaxed">{react_summary}</span>
                </p>
              </div>
            )}

            {repo.description && (
              <p className="mt-3 text-sm text-gray-600 leading-relaxed">
                {repo.description}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 冲突检测提示 */}
      {conflicts.length > 0 && (
        <Alert className="border-amber-200 bg-amber-50">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <AlertDescription className="text-amber-800">
            <p className="mb-1 font-medium">检测到维度间冲突</p>
            <ul className="space-y-1">
              {conflicts.map((c, i) => (
                <li key={i} className="text-sm">{c}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {/* 各维度评分条形图 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base font-semibold text-gray-900">
            <TrendingUp className="h-4 w-4 text-gray-500" />
            维度评分对比
          </CardTitle>
        </CardHeader>
        <CardContent>
          <DimensionBarChart data={barChartData} height={220} />
        </CardContent>
      </Card>

      {/* 各维度详情卡片 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {Object.entries(DIMENSION_CONFIG).map(([key, config]) => {
          const dim = dimensions[key]
          if (!dim) return null
          return (
            <DimensionCard
              key={key}
              dimKey={key}
              config={config}
              dim={dim}
              calibrations={calibrations[key] || []}
            />
          )
        })}
      </div>

      {/* 综合报告（Synthesis Agent） */}
      {hasSynthesis && (
        <SynthesisSection synthesis={synthesis} />
      )}

      {/* 关键发现 */}
      {key_findings.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base font-semibold">
              <Lightbulb className="h-4 w-4 text-gray-500" />
              关键发现
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {key_findings.map((finding, i) => (
                <li key={i} className="flex items-start gap-3 text-sm text-gray-700">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-gray-100 text-xs font-medium text-gray-500">
                    {i + 1}
                  </span>
                  <span className="leading-relaxed">{finding}</span>
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
            <CardTitle className="flex items-center gap-2 text-base font-semibold">
              <CheckCircle2 className="h-4 w-4 text-gray-500" />
              评估建议
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {recommendations.map((rec, i) => (
                <li key={i} className="flex items-start gap-3 text-sm text-gray-700">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-teal-50 text-xs font-medium text-teal-600">
                    {i + 1}
                  </span>
                  <span className="leading-relaxed">{rec}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// 子组件
// ═══════════════════════════════════════════════════════════════

/** 单个维度详情卡片（含 reasoning 折叠面板和 RAG 校准） */
function DimensionCard({
  dimKey,
  config,
  dim,
  calibrations,
}: {
  dimKey: string
  config: { label: string; icon: typeof Users; max: number }
  dim: import('@/types/api').DimensionScore
  calibrations: import('@/types/api').CalibrationItem[]
}) {
  const [showReasoning, setShowReasoning] = useState(false)
  const Icon = config.icon
  const accentClass = DIMENSION_ACCENT[dimKey] || 'border-l-gray-300'

  const hasReasoning = dim.reasoning && !dim.reasoning.startsWith('[LLM')
  const hasCalibrations = calibrations.length > 0

  return (
    <Card className={`border-l-4 ${accentClass}`}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="h-4 w-4 text-gray-500" />
          {config.label}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* 分数 */}
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-bold tabular-nums">{dim.score}</span>
          <span className="text-sm text-gray-400">/ {config.max}</span>
          <span className="ml-auto text-sm font-medium text-gray-500">
            {Math.round(dim.percentage)}%
          </span>
        </div>

        {/* 进度条 */}
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
          <div
            className="h-full rounded-full bg-gray-800 transition-all"
            style={{ width: `${dim.percentage}%` }}
          />
        </div>

        {/* 关键发现 */}
        {dim.findings.length > 0 && (
          <div className="space-y-1.5 pt-1">
            {dim.findings.map((finding, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-gray-600">
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gray-400" />
                <span>{finding}</span>
              </div>
            ))}
          </div>
        )}

        {/* 风险 */}
        {dim.risks.length > 0 && (
          <div className="space-y-1.5">
            {dim.risks.map((risk, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-amber-700">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                <span>{risk}</span>
              </div>
            ))}
          </div>
        )}

        {/* LLM 推理（可折叠） */}
        {hasReasoning && (
          <div className="pt-1">
            <button
              onClick={() => setShowReasoning(!showReasoning)}
              className="flex items-center gap-1.5 text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors"
            >
              <BrainCircuit className="h-3.5 w-3.5" />
              LLM 推理
              {showReasoning ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </button>
            {showReasoning && (
              <div className="mt-2 rounded-md bg-gray-50 px-3 py-2 text-xs text-gray-600 leading-relaxed">
                {dim.reasoning}
              </div>
            )}
          </div>
        )}

        {/* RAG 校准引用 */}
        {hasCalibrations && (
          <div className="pt-1">
            <div className="flex items-center gap-1.5 text-xs font-medium text-gray-400">
              <BookOpen className="h-3.5 w-3.5" />
              知识库引用
            </div>
            <div className="mt-1.5 space-y-1">
              {calibrations.slice(0, 2).map((cal, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded-md bg-gray-50 px-2.5 py-1.5"
                >
                  <span className="text-xs text-gray-500">
                    {cal.metadata?.topic || cal.id}
                  </span>
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">
                    相关度 {(cal.distance * 100).toFixed(0)}%
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/** 综合报告区块 */
function SynthesisSection({
  synthesis,
}: {
  synthesis: import('@/types/api').SynthesisReport
}) {
  return (
    <Card className="border-l-4 border-l-indigo-400">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-gray-900">
          <BrainCircuit className="h-4 w-4 text-indigo-500" />
          综合报告（Synthesis Agent）
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* 执行摘要 */}
        {synthesis.executive_summary && (
          <div className="rounded-lg bg-indigo-50 px-4 py-3">
            <p className="text-sm font-medium text-indigo-900 mb-1">执行摘要</p>
            <p className="text-sm text-indigo-800 leading-relaxed">
              {synthesis.executive_summary}
            </p>
          </div>
        )}

        {/* 各维度一句话总结 */}
        {synthesis.dimension_summaries?.length > 0 && (
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">各维度评估</p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {synthesis.dimension_summaries.map((ds, i) => (
                <div
                  key={i}
                  className="rounded-md border border-gray-100 bg-white px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-500">
                      {ds.name}
                    </span>
                    <span className="text-xs tabular-nums text-gray-400">
                      {Math.round(ds.percentage)}%
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-600 leading-relaxed">
                    {ds.assessment}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 风险矩阵 */}
        {synthesis.risk_matrix?.length > 0 && (
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">风险矩阵</p>
            <div className="space-y-2">
              {synthesis.risk_matrix.map((risk, i) => (
                <div
                  key={i}
                  className={`rounded-md border px-3 py-2 ${
                    RISK_LEVEL_COLORS[risk.level] || 'bg-gray-50 border-gray-200'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Badge
                      variant="outline"
                      className="text-[10px] px-1.5 py-0 h-5 font-medium uppercase"
                    >
                      {risk.level}
                    </Badge>
                    <span className="text-xs font-medium">{risk.category}</span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed">{risk.description}</p>
                  <p className="mt-0.5 text-[10px] text-gray-400">
                    来源: {risk.source}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 明确建议 */}
        {synthesis.top_recommendations?.length > 0 && (
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">明确建议</p>
            <ol className="space-y-2">
              {synthesis.top_recommendations.map((rec, i) => (
                <li
                  key={i}
                  className="flex items-start gap-3 text-sm text-gray-700"
                >
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-xs font-medium text-indigo-600">
                    {i + 1}
                  </span>
                  <span className="leading-relaxed">{rec}</span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {/* 数据来源 */}
        {synthesis.data_source_summary && (
          <p className="text-xs text-gray-400 border-t pt-3">
            {synthesis.data_source_summary}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

/** 报告加载骨架屏 */
function ReportSkeleton() {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-32" />
        </div>
        <Skeleton className="h-7 w-12" />
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Skeleton className="h-[260px]" />
        <Skeleton className="h-[260px] md:col-span-2" />
      </div>
      <Skeleton className="h-[280px]" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-56" />
        ))}
      </div>
    </div>
  )
}
