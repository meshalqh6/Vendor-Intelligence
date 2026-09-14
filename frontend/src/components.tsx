import { useRef, useState } from 'react'
import type { Scorecard, TrendPoint } from './types'

const CLASS_STYLE: Record<string, string> = {
  Preferred: 'b-good',
  Approved: 'b-info',
  Conditional: 'b-warn',
  'Reassessment Required': 'b-bad',
}
const RISK_STYLE: Record<string, string> = {
  Low: 'b-good', Medium: 'b-info', Moderate: 'b-warn', High: 'b-bad',
}

export function ClassBadge({ value }: { value: string }) {
  return <span className={`badge ${CLASS_STYLE[value] || 'b-neutral'}`}>{value}</span>
}

export function RiskBadge({ value }: { value: string }) {
  return (
    <span className={`badge ${RISK_STYLE[value] || 'b-neutral'}`}>
      {value === 'High' && '⚠ '}{value} Risk
    </span>
  )
}

export function RecordChips({ ids }: { ids?: string[] }) {
  const [open, setOpen] = useState(false)
  if (!ids || ids.length === 0) return null
  const shown = open ? ids : ids.slice(0, 6)
  return (
    <div className="chips">
      {shown.map((id) => <span className="chip" key={id}>{id}</span>)}
      {ids.length > 6 && (
        <button className="chip-toggle" onClick={() => setOpen(!open)}>
          {open ? 'show less' : `+${ids.length - 6} more`}
        </button>
      )}
    </div>
  )
}

/** Portfolio risk map: performance score (x) vs risk (y), colour = classification.
 *  The whole pitch in one frame — dots in the red escalation band carry a critical
 *  trigger regardless of how high they score. */
const CLASS_COLOR: Record<string, string> = {
  Preferred: '#059669', Approved: '#2563eb', Conditional: '#b45309', 'Reassessment Required': '#dc2626',
}
const RISK_ORDER = ['High', 'Moderate', 'Medium', 'Low']

function jitter(seed: number, amp: number) {
  const x = Math.sin(seed * 99.13) * 10000
  return (x - Math.floor(x) - 0.5) * 2 * amp
}

export function RiskMap({ vendors, onSelect }: { vendors: Scorecard[]; onSelect: (code: string) => void }) {
  const wrap = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ v: Scorecard; left: number; top: number } | null>(null)

  const W = 920, H = 380, L = 66, R = 902, T = 30, B = 330
  const laneH = (B - T) / 4
  const scores = vendors.map((v) => v.final_score)
  const rawMin = scores.length ? Math.min(...scores) : 70
  const xMin = Math.max(50, Math.floor((rawMin - 2) / 5) * 5)
  const xMax = 100
  const cx = (s: number) => L + (Math.max(xMin, Math.min(xMax, s)) - xMin) / (xMax - xMin) * (R - L)
  const cyLane = (i: number) => T + laneH * (i + 0.5)

  const thresholds = [75, 85, 95].filter((t) => t >= xMin)
  const xticks: number[] = []
  for (let t = xMin; t <= xMax; t += (xMax - xMin) > 30 ? 10 : 5) xticks.push(t)

  function onMove(e: React.MouseEvent, v: Scorecard) {
    const rect = wrap.current?.getBoundingClientRect()
    if (!rect) return
    setHover({ v, left: e.clientX - rect.left, top: e.clientY - rect.top })
  }

  return (
    <div className="quad-wrap" ref={wrap} onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        {/* escalation zone across the High lane */}
        <rect x={L} y={T} width={R - L} height={laneH} fill="#fee2e2" opacity="0.6" />
        <text x={R - 8} y={T + 15} textAnchor="end" fontSize="11" fill="#b91c1c" fontWeight="600">
          Escalation zone — critical trigger overrides score
        </text>

        {/* lane separators + risk labels */}
        {RISK_ORDER.map((r, i) => (
          <g key={r}>
            <line x1={L} y1={T + laneH * i} x2={R} y2={T + laneH * i} stroke="#e2e8f0" strokeWidth="1" />
            <text x={L - 12} y={cyLane(i) + 4} textAnchor="end" fontSize="12" fill="#475569" fontWeight="600">{r}</text>
          </g>
        ))}
        <line x1={L} y1={B} x2={R} y2={B} stroke="#cbd5e1" strokeWidth="1" />

        {/* classification threshold guides */}
        {thresholds.map((t) => (
          <g key={t}>
            <line x1={cx(t)} y1={T} x2={cx(t)} y2={B} stroke="#cbd5e1" strokeWidth="1" strokeDasharray="3 4" />
            <text x={cx(t)} y={B + 30} textAnchor="middle" fontSize="10" fill="#94a3b8">{t}</text>
          </g>
        ))}
        {xticks.map((t) => (
          <text key={t} x={cx(t)} y={B + 16} textAnchor="middle" fontSize="10" fill="#94a3b8">{t}</text>
        ))}
        <text x={(L + R) / 2} y={H - 4} textAnchor="middle" fontSize="11" fill="#64748b">Performance score →</text>

        {/* vendor dots */}
        {vendors.map((v, idx) => {
          const i = RISK_ORDER.indexOf(v.risk)
          if (i < 0) return null
          const x = cx(v.final_score) + jitter(idx + 1, 6)
          const y = cyLane(i) + jitter(idx + 7, laneH * 0.28)
          const color = CLASS_COLOR[v.classification] || '#64748b'
          const active = hover?.v.vendor_code === v.vendor_code
          return (
            <g key={v.vendor_code} style={{ cursor: 'pointer' }}
               onMouseMove={(e) => onMove(e, v)} onClick={() => onSelect(v.vendor_code)}>
              {v.risk === 'High' && <circle cx={x} cy={y} r={11} fill="#dc2626" opacity="0.16" />}
              <circle cx={x} cy={y} r={active ? 8 : 6} fill={color} stroke="#fff" strokeWidth="1.5" />
            </g>
          )
        })}
      </svg>

      {hover && (
        <div className="quad-tip" style={{ left: hover.left, top: hover.top }}>
          <b>{hover.v.name}</b>
          Score {hover.v.final_score} · {hover.v.classification}<br />
          Risk: {hover.v.risk}
          {hover.v.risk_triggers[0] && <> · {hover.v.risk_triggers[0].label}</>}
        </div>
      )}
    </div>
  )
}

/** Minimal dependency-free SVG line chart for the quarterly trend. */
export function TrendChart({ points }: { points: TrendPoint[] }) {
  if (!points || points.length < 2) return <div className="muted">Not enough history for a trend.</div>
  const W = 560, H = 120, padX = 8, padY = 14
  const vals = points.map((p) => p.value)
  const min = Math.min(...vals, 40), max = Math.max(...vals, 100)
  const x = (i: number) => padX + (i * (W - 2 * padX)) / (points.length - 1)
  const y = (v: number) => padY + (H - 2 * padY) * (1 - (v - min) / (max - min || 1))
  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(' ')
  const area = `${d} L ${x(points.length - 1)} ${H - padY} L ${x(0)} ${H - padY} Z`
  return (
    <div className="trend">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="tg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#tg)" />
        <path d={d} fill="none" stroke="#4f46e5" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.value)} r="3" fill="#4f46e5" />
        ))}
      </svg>
      <div className="mono muted" style={{ fontSize: 11, display: 'flex', justifyContent: 'space-between' }}>
        <span>{points[0].period}</span>
        <span>{points[points.length - 1].period}</span>
      </div>
    </div>
  )
}
