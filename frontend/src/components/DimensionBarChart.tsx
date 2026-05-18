/**
 * 各维度评分对比条形图
 *
 * 使用 Recharts 绘制水平条形图，展示四个维度的评分对比。
 * 配色低饱和度，避免 AI 味。
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

/** 维度条形图数据项 */
interface DimensionBarItem {
  name: string
  key: string
  score: number
  max: number
  percentage: number
}

interface DimensionBarChartProps {
  data: DimensionBarItem[]
  height?: number
}

/** 维度配色 — 低饱和度专业风 */
const DIMENSION_COLORS: Record<string, string> = {
  community: '#0d9488',   // teal-600 — 社区健康
  quality: '#2563eb',     // blue-600 — 代码质量
  security: '#475569',    // slate-600 — 安全（沉稳灰色）
  evolution: '#d97706',   // amber-600 — 技术演进
}

/** 维度中文标签 */
const DIMENSION_LABELS: Record<string, string> = {
  community: '社区健康度',
  quality: '代码质量',
  security: '安全评分',
  evolution: '技术演进',
}

export default function DimensionBarChart({
  data,
  height = 200,
}: DimensionBarChartProps) {
  const chartData = data.map((item) => ({
    ...item,
    label: DIMENSION_LABELS[item.key] || item.name,
    fill: DIMENSION_COLORS[item.key] || '#64748b',
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={chartData}
        layout="vertical"
        margin={{ top: 8, right: 40, left: 0, bottom: 8 }}
        barCategoryGap="24%"
      >
        <CartesianGrid horizontal={false} stroke="#f1f5f9" />
        <XAxis
          type="number"
          domain={[0, 'dataMax']}
          tick={{ fontSize: 11, fill: '#94a3b8' }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="label"
          tick={{ fontSize: 12, fill: '#475569', fontWeight: 500 }}
          axisLine={false}
          tickLine={false}
          width={80}
        />
        <Tooltip
          cursor={{ fill: '#f8fafc' }}
          contentStyle={{
            borderRadius: '8px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
            fontSize: '13px',
          }}
          formatter={(value, _name, item) => {
            const payload = item.payload as DimensionBarItem
            return [`${value} / ${payload.max}`, '评分']
          }}
        />
        <Bar
          dataKey="score"
          radius={[0, 4, 4, 0]}
          animationDuration={800}
        >
          {chartData.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.fill} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
