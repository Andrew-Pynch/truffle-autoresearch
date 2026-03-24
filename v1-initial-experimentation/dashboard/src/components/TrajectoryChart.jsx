import { useEffect, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Scatter, ComposedChart, ScatterChart,
} from 'recharts'
import { getTrajectory } from '../api'

const COLORS = {
  '4090': '#22d3ee',
  '3080': '#34d399',
}

function TooltipEntry({ d, label }) {
  if (!d) return null
  return (
    <div className="tooltip-entry">
      <div className="tooltip-machine">{label} — Experiment #{d.experiment_num}</div>
      <div className="tooltip-row"><span>commit:</span> <code>{d.commit}</code></div>
      <div className="tooltip-row"><span>val_bpb:</span> {d.val_bpb?.toFixed(6) ?? '—'}</div>
      <div className="tooltip-row"><span>memory:</span> {d.memory_gb} GB</div>
      <div className="tooltip-row"><span>status:</span> <span className={`status-${d.status}`}>{d.status}</span></div>
      <div className="tooltip-desc">{d.description}</div>
    </div>
  )
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const merged = payload[0].payload
  return (
    <div className="chart-tooltip">
      <TooltipEntry d={merged.data_4090} label="RTX 4090" />
      <TooltipEntry d={merged.data_3080} label="RTX 3080" />
    </div>
  )
}

function CustomDot(props) {
  const { cx, cy, payload } = props
  if (!cx || !cy) return null
  const isKeep = payload.status === 'keep'
  const color = COLORS[payload.machine] || '#888'
  return (
    <circle
      cx={cx}
      cy={cy}
      r={isKeep ? 6 : 3}
      fill={isKeep ? color : 'transparent'}
      stroke={color}
      strokeWidth={isKeep ? 2 : 1}
      opacity={isKeep ? 1 : 0.4}
    />
  )
}

export default function TrajectoryChart({ token }) {
  const [data4090, setData4090] = useState([])
  const [data3080, setData3080] = useState([])

  useEffect(() => {
    if (!token) return
    const load = async () => {
      try {
        const [t4090, t3080] = await Promise.all([
          getTrajectory('4090', token),
          getTrajectory('3080', token),
        ])
        setData4090(t4090.filter(d => d.val_bpb > 0).map(d => ({ ...d, machine: '4090' })))
        setData3080(t3080.filter(d => d.val_bpb > 0).map(d => ({ ...d, machine: '3080' })))
      } catch (e) {
        console.error('Failed to load trajectory:', e)
      }
    }
    load()
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [token])

  // Merge data for dual-line chart by experiment_num
  const maxLen = Math.max(data4090.length, data3080.length)
  const merged = []
  for (let i = 0; i < maxLen; i++) {
    const entry = { experiment_num: i + 1 }
    if (data4090[i]) {
      entry.val_bpb_4090 = data4090[i].val_bpb
      entry.data_4090 = data4090[i]
    }
    if (data3080[i]) {
      entry.val_bpb_3080 = data3080[i].val_bpb
      entry.data_3080 = data3080[i]
    }
    merged.push(entry)
  }

  const allVals = [...data4090, ...data3080].map(d => d.val_bpb).filter(v => v > 0).sort((a, b) => a - b)
  const yMin = allVals.length ? Math.floor(Math.min(...allVals) * 1000) / 1000 : 1.08
  // Cap at baseline + 15% to keep the interesting convergence zone prominent
  const baseline = allVals.length ? allVals[0] : 1.08
  const yMax = Math.ceil((baseline * 1.15) * 100) / 100

  return (
    <div className="trajectory-section">
      <h2 className="section-title">Optimization Trajectory</h2>
      <p className="section-subtitle">val_bpb over experiments — lower is better</p>
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={420}>
          <LineChart data={merged} margin={{ top: 10, right: 30, left: 20, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
            <XAxis
              dataKey="experiment_num"
              stroke="#8b949e"
              label={{ value: 'Experiment #', position: 'insideBottom', offset: -5, fill: '#8b949e' }}
            />
            <YAxis
              stroke="#8b949e"
              domain={[yMin, yMax]}
              allowDataOverflow
              tickFormatter={(v) => v.toFixed(3)}
              label={{ value: 'val_bpb (lower is better)', angle: -90, position: 'insideLeft', offset: 10, fill: '#8b949e' }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            <Line
              type="monotone"
              dataKey="val_bpb_4090"
              name="RTX 4090"
              stroke={COLORS['4090']}
              strokeWidth={2}
              dot={(props) => {
                const d = merged[props.index]?.data_4090
                if (!d) return null
                return <CustomDot {...props} payload={d} />
              }}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="val_bpb_3080"
              name="RTX 3080"
              stroke={COLORS['3080']}
              strokeWidth={2}
              dot={(props) => {
                const d = merged[props.index]?.data_3080
                if (!d) return null
                return <CustomDot {...props} payload={d} />
              }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
