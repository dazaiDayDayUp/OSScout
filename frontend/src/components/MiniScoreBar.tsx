/**
 * 迷你评分进度条
 *
 * 用于列表页等紧凑场景，展示评分百分比。
 * 配色低饱和度，避免 AI 味。
 */

interface MiniScoreBarProps {
  score: number
  maxScore: number
  rating: string
}

/** 评级颜色映射 */
const RATING_BAR_COLORS: Record<string, string> = {
  'A+': '#059669',
  'A': '#059669',
  'B+': '#ca8a04',
  'B': '#ca8a04',
  'C': '#ea580c',
  'D': '#b91c1c',
}

export default function MiniScoreBar({ score, maxScore, rating }: MiniScoreBarProps) {
  const percentage = Math.min((score / maxScore) * 100, 100)
  const color = RATING_BAR_COLORS[rating] || '#64748b'

  return (
    <div className="w-full">
      <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
        <span className="font-semibold tabular-nums">{score}</span>
        <span className="tabular-nums">/ {maxScore}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{
            width: `${percentage}%`,
            backgroundColor: color,
          }}
        />
      </div>
    </div>
  )
}
