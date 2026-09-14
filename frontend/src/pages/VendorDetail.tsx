import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getVendor } from '../api'
import { ClassBadge, RecordChips, RiskBadge, TrendChart } from '../components'
import type { Scorecard } from '../types'

export default function VendorDetail() {
  const { code } = useParams()
  const [v, setV] = useState<Scorecard | null>(null)
  useEffect(() => { if (code) getVendor(code).then(setV) }, [code])
  if (!v) return <div className="loading">Loading scorecard…</div>

  return (
    <>
      <Link to="/" className="back">← Portfolio</Link>
      <div className="panel panel-pad" style={{ marginBottom: 18 }}>
        <div className="detail-head">
          <div>
            <h1 style={{ margin: '0 0 6px' }}>{v.name}</h1>
            <div className="muted mono" style={{ marginBottom: 12 }}>
              {v.vendor_code} · {v.type === 'supplier' ? 'Supplier' : 'Service provider'} · {v.category} · {v.country} · {v.status}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <ClassBadge value={v.classification} />
              <RiskBadge value={v.risk} />
            </div>
            <div style={{ marginTop: 14, maxWidth: 560 }}>
              <div className="muted" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.4px' }}>Recommended action</div>
              <div>{v.next_action.recommended_action}</div>
              <div className="muted" style={{ fontSize: 13, marginTop: 4 }}><b>Control:</b> {v.next_action.system_control}</div>
            </div>
          </div>
          <div className="big-score">
            <div className="n">{v.final_score}</div>
            <div className="l">weighted score / 100</div>
          </div>
        </div>
      </div>

      {v.risk_triggers.length > 0 && (
        <>
          <div className="section-title">Risk triggers (override the score)</div>
          {v.risk_triggers.map((t) => (
            <div className="trigger" key={t.code}>
              <div className="ic">⚠</div>
              <div>
                <div className="t">{t.label}</div>
                <div className="d">{t.detail}</div>
                <RecordChips ids={t.source_record_ids} />
              </div>
            </div>
          ))}
        </>
      )}

      <div className="two-col" style={{ marginTop: 22 }}>
        <div className="panel panel-pad">
          <div className="section-title" style={{ marginTop: 0 }}>KPI breakdown (weight × value)</div>
          {v.kpis.map((k) => (
            <div className="kpi" key={k.key}>
              <div className="kpi-top">
                <div className="kpi-name">{k.label}<span className="w">weight {Math.round(k.weight * 100)}%</span></div>
                <div className="kpi-val">{k.value}<span className="contrib">→ {k.contribution}</span></div>
              </div>
              <div className="bar"><span style={{ width: `${k.value}%` }} /></div>
              <div className="kpi-detail">{k.detail}</div>
              <RecordChips ids={k.source_record_ids} />
            </div>
          ))}
        </div>

        <div>
          <div className="panel panel-pad" style={{ marginBottom: 16 }}>
            <div className="section-title" style={{ marginTop: 0 }}>
              {v.type === 'supplier' ? 'Quality trend (quarterly)' : 'Service-quality trend (quarterly)'}
            </div>
            <TrendChart points={v.trend} />
          </div>
          <div className="panel panel-pad">
            <div className="section-title" style={{ marginTop: 0 }}>How this score is computed</div>
            <p className="muted" style={{ fontSize: 13, margin: 0 }}>
              Every KPI above is calculated by the deterministic rules engine from the cited source
              records — accepted vs total inspection-lot quantity, GRN dates vs PO requested dates,
              valid vs required documents, and NCR/CAPA closure banding. Weights and thresholds come
              from <span className="mono">config/scoring.yaml</span>. Risk is evaluated independently and
              can override the classification.
            </p>
          </div>
        </div>
      </div>
    </>
  )
}
