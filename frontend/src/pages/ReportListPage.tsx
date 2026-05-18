/**
 * 报告列表页
 *
 * 分页展示所有历史尽调报告，点击可跳转到报告详情。
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
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { FileText, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react'

/** 评级对应的颜色 */
const RATING_COLORS: Record<string, string> = {
  'A+': 'bg-green-100 text-green-800',
  'A': 'bg-green-100 text-green-800',
  'B+': 'bg-lime-100 text-lime-800',
  'B': 'bg-yellow-100 text-yellow-800',
  'C': 'bg-orange-100 text-orange-800',
  'D': 'bg-red-100 text-red-800',
}

export default function ReportListPage() {
  const [page, setPage] = useState(1)
  const pageSize = 20

  const { data, isLoading, isError, error } = useReportList(page, pageSize)

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">报告列表</h1>
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
                    <TableHead>评分</TableHead>
                    <TableHead>评级</TableHead>
                    <TableHead>分析时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((item) => (
                    <TableRow key={item.report_id}>
                      <TableCell>
                        <Link
                          to={`/reports/${item.report_id}`}
                          className="font-medium text-primary-600 hover:underline"
                        >
                          {item.repo_owner}/{item.repo_name}
                        </Link>
                        <p className="text-xs text-gray-400">
                          {item.repo_url}
                        </p>
                      </TableCell>
                      <TableCell className="font-mono text-lg font-semibold">
                        {item.overall_score}
                      </TableCell>
                      <TableCell>
                        <Badge
                          className={
                            RATING_COLORS[item.overall_rating] ||
                            'bg-gray-100 text-gray-800'
                          }
                        >
                          {item.overall_rating}
                        </Badge>
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
                    共 {data.pagination.total} 条，第 {page} /{' '}
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
