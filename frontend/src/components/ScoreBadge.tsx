/**
 * 评分徽章组件
 *
 * 统一风格的评分等级徽章，配色低饱和度专业风。
 */

interface ScoreBadgeProps {
  rating: string
  className?: string
}

/** 评级样式映射 — 低饱和度专业风 */
const RATING_STYLES: Record<string, string> = {
  'A+': 'bg-[#ecfdf5] text-[#059669] border border-[#a7f3d0]',
  'A': 'bg-[#ecfdf5] text-[#059669] border border-[#a7f3d0]',
  'B+': 'bg-[#fffbeb] text-[#b45309] border border-[#fcd34d]',
  'B': 'bg-[#fffbeb] text-[#b45309] border border-[#fcd34d]',
  'C': 'bg-[#fff7ed] text-[#c2410c] border border-[#fdba74]',
  'D': 'bg-[#fef2f2] text-[#b91c1c] border border-[#fca5a5]',
}

export default function ScoreBadge({ rating, className = '' }: ScoreBadgeProps) {
  const style = RATING_STYLES[rating] || 'bg-gray-50 text-gray-500 border border-gray-200'

  return (
    <span
      className={`inline-flex items-center rounded-md px-3 py-1 text-base font-bold ${style} ${className}`}
    >
      {rating}
    </span>
  )
}
