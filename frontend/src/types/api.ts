/**
 * OSScout API 类型定义
 *
 * 基于后端 FastAPI 接口手动维护，确保前后端类型一致。
 * 未来可替换为 openapi-typescript 自动生成的类型。
 */

// ═══════════════════════════════════════════════════════════════
// 通用分页类型
// ═══════════════════════════════════════════════════════════════

export interface PaginationMeta {
  total: number
  page: number
  page_size: number
  total_pages: number
}

// ═══════════════════════════════════════════════════════════════
// 分析任务接口
// ═══════════════════════════════════════════════════════════════

/** 提交分析任务请求 */
export interface AnalyzeRequest {
  repo_url: string
  notify_email?: string
}

/** 提交分析任务响应 */
export interface AnalyzeResponse {
  task_id: number
  status: string
  estimated_seconds: number
}

/** 任务状态响应 */
export interface TaskResponse {
  task_id: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  repo_id: number | null
  started_at: string | null
  completed_at: string | null
  report_id: number | null
  error_message: string | null
  duration_seconds: number | null
}

// ═══════════════════════════════════════════════════════════════
// 报告接口
// ═══════════════════════════════════════════════════════════════

/** RAG 校准引用项 */
export interface CalibrationItem {
  id: string
  content: string
  metadata: {
    category: string
    topic: string
    source_file: string
  }
  distance: number
  citation?: Citation
}

/** 引用来源（Phase 4.7） */
export interface Citation {
  source_type: 'kb' | 'web' | 'benchmark'
  document_id: string
  title: string
  category: string | null
  url: string | null
  snippet: string
  confidence: number | null
}

/** 综合报告中的风险项 */
export interface SynthesisRiskItem {
  level: 'high' | 'medium' | 'low'
  category: string
  description: string
  source: string
}

/** 综合报告中的维度总结 */
export interface SynthesisDimensionSummary {
  name: string
  score: number
  max_score: number
  percentage: number
  assessment: string
}

/** 综合报告 */
export interface SynthesisReport {
  executive_summary: string
  overall_rating: string
  overall_score: number
  dimension_summaries: SynthesisDimensionSummary[]
  risk_matrix: SynthesisRiskItem[]
  top_recommendations: string[]
  data_source_summary: string
}

/** 单个维度的评分详情 */
export interface DimensionScore {
  score: number
  max_score: number
  percentage: number
  findings: string[]
  risks: string[]
  reasoning?: string | null
  details: Record<string, unknown>
}

/** 尽调报告响应（Phase 3 增强版） */
export interface ReportResponse {
  report_id: number
  task_id: number
  repo: {
    owner?: string
    name?: string
    url?: string
    description?: string
    primary_language?: string
    star_count?: number
    fork_count?: number
  }
  overall: {
    score: number
    rating: string
    max_score: number
    percentage: number
  }
  dimensions: Record<string, DimensionScore>
  key_findings: string[]
  recommendations: string[]
  // Phase 3.4/3.5 新增字段
  calibrations: Record<string, CalibrationItem[]>
  conflicts: string[]
  react_summary: string
  synthesis: SynthesisReport | Record<string, never>
  // Phase 4.7 新增字段
  citations: Citation[]
  created_at: string | null
}

/** 报告列表单项 */
export interface ReportListItem {
  report_id: number
  task_id: number
  repo_owner: string
  repo_name: string
  repo_url: string
  overall_score: number
  overall_rating: string
  created_at: string | null
}

/** 报告列表响应 */
export interface ReportListResponse {
  items: ReportListItem[]
  pagination: PaginationMeta
}

// ═══════════════════════════════════════════════════════════════
// 仓库历史趋势接口
// ═══════════════════════════════════════════════════════════════

/** 单个指标的时间点数据 */
export interface MetricDataPoint {
  date: string
  value: number
}

/** 各维度趋势数据 */
export interface TrendMetrics {
  overall: MetricDataPoint[]
  community: MetricDataPoint[]
  quality: MetricDataPoint[]
  security: MetricDataPoint[]
  evolution: MetricDataPoint[]
}

/** 仓库历史趋势响应 */
export interface RepoHistoryResponse {
  repo_id: number
  repo_owner: string
  repo_name: string
  total_analyses: number
  trends: TrendMetrics
}

// ═══════════════════════════════════════════════════════════════
// 多仓库对比接口
// ═══════════════════════════════════════════════════════════════

/** 多仓库对比请求 */
export interface CompareRequest {
  repo_urls: string[]
}

/** 对比中的仓库评分概览 */
export interface RepoSummary {
  repo_id: number
  owner: string
  name: string
  url: string
  overall_score: number
  overall_rating: string
  community_score: number
  quality_score: number
  security_score: number
  evolution_score: number
}

/** 单个维度的对比项 */
export interface DimensionCompareItem {
  repo: string
  score: number
}

/** 关键差异项 */
export interface KeyDifference {
  dimension: string
  highest: {
    repo: string
    score: number
  }
  lowest: {
    repo: string
    score: number
  }
  gap: number
}

/** 多仓库对比响应 */
export interface CompareResponse {
  repositories: RepoSummary[]
  ranking: Array<{
    rank: number
    repo: string
    score: number
    rating: string
  }>
  dimension_comparison: Record<string, DimensionCompareItem[]>
  key_differences: KeyDifference[]
  analyzed_at: string
}
