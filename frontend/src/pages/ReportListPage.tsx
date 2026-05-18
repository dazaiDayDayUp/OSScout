/**
 * 报告列表页
 *
 * 分页展示所有历史尽调报告，点击可跳转到报告详情。
 * 列表中展示迷你评分条，让评分一目了然。
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useReportList } from '@/api/hooks'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import ScoreBadge from '@/components/ScoreBadge'
import MiniScoreBar from '@/components/MiniScoreBar'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { FileText, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react'

export default function ReportListPage() {
  const [page, setPage] = useState(1)
  const pageSize = 20

  const { data, isLoading, isError, error } = useReportList(page, pageSize)

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">
          报告列表
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          查看所有历史尽调分析报告
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            历史报告
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <ListSkeleton />}

          {isError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                {error instanceof Error ? error.message : '加载失败'}
              </AlertDescription>
            </Alert>
          )}

          {data && data.items.length === 0 && (
            <div className="py-12 text-center text-gray-400">
              暂无报告，先去首页提交分析任务吧
            </div>
          )}

          {data && data.items.length > 0 && (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>仓库</TableHead>
                    <TableHead className="w-32">评分</TableHead>
                    <TableHead className="w-20">评级</TableHead>
                    <TableHead className="w-32">分析时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((item) => (
                    <TableRow key={item.report_id}>
                      <TableCell>
                        <Link
                          to={`/reports/${item.report_id}`}
                          className="font-medium text-gray-900 hover:text-primary-600 hover:underline"
                        >
                          {item.repo_owner}/{item.repo_name}
                        </Link>
                        <p className="text-xs text-gray-400">
                          {item.repo_url}
                        </p>
                      </TableCell>
                      <TableCell>
                        <MiniScoreBar
                          score={item.overall_score}
                          maxScore={100}
                          rating={item.overall_rating}
                        />
                      </TableCell>
                      <TableCell>
                        <ScoreBadge rating={item.overall_rating} />
                      </TableCell>
                      <TableCell className="text-sm text-gray-500">
                        {item.created_at
                          ? new Date(item.created_at).toLocaleDateString('zh-CN')
                          : '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* 分页 */}
              {data.pagination.total_pages > 1 && (
                <div className="mt-4 flex items-center justify-between">
                  <span className="text-sm text-gray-500">
                    共 {data.pagination.total} 条，第 {page} /
                    {data.pagination.total_pages} 页
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page <= 1}
                      className="flex items-center rounded-lg border px-3 py-1.5 text-sm transition-colors hover:bg-gray-50 disabled:opacity-40"
                    >
                      <ChevronLeft className="mr-1 h-4 w-4" /> 上一页
                    </button>
                    <button
                      onClick={() =>
                        setPage((p) =>
                          Math.min(data.pagination.total_pages, p + 1),
                        )
                      }
                      disabled={page >= data.pagination.total_pages}
                      className="flex items-center rounded-lg border px-3 py-1.5 text-sm transition-colors hover:bg-gray-50 disabled:opacity-40"
                    >
                      下一页 <ChevronRight className="ml-1 h-4 w-4" />
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

/** 列表加载骨架屏 */
function ListSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  )
}
