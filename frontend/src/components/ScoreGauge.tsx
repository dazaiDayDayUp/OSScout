/**
 * 评分环形图仪表盘
 *
 * 用 SVG 绘制环形进度条，展示综合评分。
 * 配色低饱和度，避免 AI 味。
 */

interface ScoreGaugeProps {
  score: number
  maxScore: number
  rating: string
  size?: number
  strokeWidth?: number
}

/** 维度配色 — 低饱和度专业风 */
const RATING_RING_COLORS: Record<string, { stroke: string; bg: string; text: string }> = {
  'A+': { stroke: '#059669', bg: '#ecfdf5', text: '#059669' },
  'A': { stroke: '#059669', bg: '#ecfdf5', text: '#059669' },
  'B+': { stroke: '#ca8a04', bg: '#fffbeb', text: '#b45309' },
  'B': { stroke: '#ca8a04', bg: '#fffbeb', text: '#b45309' },
  'C': { stroke: '#ea580c', bg: '#fff7ed', text: '#c2410c' },
  'D': { stroke: '#b91c1c', bg: '#fef2f2', text: '#b91c1c' },
}

export default function ScoreGauge({
  score,
  maxScore,
  rating,
  size = 160,
  strokeWidth = 12,
}: ScoreGaugeProps) {
  const percentage = Math.min((score / maxScore) * 100, 100)
  const colors = RATING_RING_COLORS[rating] || RATING_RING_COLORS['B']

  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (percentage / 100) * circumference

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        {/* 背景圆环 */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#f1f5f9"
          strokeWidth={strokeWidth}
        />
        {/* 进度圆环 */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={colors.stroke}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{
            transition: 'stroke-dashoffset 1s ease-out',
          }}
        />
      </svg>
      {/* 中心文字 */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold tabular-nums" style={{ color: colors.text }}>
          {score}
        </span>
        <span className="text-xs text-gray-400">/ {maxScore}</span>
      </div>
    </div>
  )
}
