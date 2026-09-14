import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getVendors } from '../api'
import { ClassBadge, RiskBadge, RiskMap } from '../components'
import type { VendorsResponse } from '../types'

export default function Dashboard() {
  const [data, setData] = useState<VendorsResponse | null>(null)
  const [type, setType] = useState('')
  const [risk, setRisk] = useState('')
  const [cls, setCls] = useState('')
  const [q, setQ] = useState('')
  const nav = useNavigate()

  useEffect(() => { getVendors().then(setData) }, [])

  const rows = useMemo(() => {
    if (!data) return []
    return data.vendors.filter((v) =>
      (!type || v.type === type) &&
      (!risk || v.risk === risk) &&
      (!cls || v.classification === cls) &&
      (!q || v.name.toLowerCase().includes(q.toLowerCase())))
  }, [data, type, risk, cls, q])

  if (!data) return <div className="loading">Loading portfolio…</div>
  const s = data.summary

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Vendor Portfolio</h1>
          <div className="sub">{data.summary.total} suppliers &amp; service providers · scored by the rules engine</div>
        </div>
      </div>

      <div className="grid tiles" style={{ marginBottom: 20 }}>
        <div className="tile"><div className="k">Vendors</div><div className="v">{s.total}</div></div>
        <div className="tile"><div className="k">Preferred</div><div className="v sm" style={{ color: 'var(--good)' }}>{s.classification['Preferred'] || 0}</div></div>
        <div className="tile"><div className="k">Conditional</div><div className="v sm" style={{ color: 'var(--warn)' }}>{s.classification['Conditional'] || 0}</div></div>
        <div className="tile"><div className="k">Reassessment</div><div className="v sm" style={{ color: 'var(--bad)' }}>{s.classification['Reassessment Required'] || 0}</div></div>
        <div className="tile"><div className="k">High Risk</div><div className="v sm" style={{ color: 'var(--bad)' }}>{s.risk['High'] || 0}</div></div>
      </div>

      <div className="panel panel-pad" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 10, marginBottom: 6 }}>
          <div>
            <div style={{ fontWeight: 700 }}>Portfolio Risk Map</div>
            <div className="muted" style={{ fontSize: 12 }}>
              Performance score vs risk. Dots in the red band carry a critical trigger — regardless of score. Click any vendor.
            </div>
          </div>
          <div className="quad-legend">
            {[['Preferred', '#059669'], ['Approved', '#2563eb'], ['Conditional', '#b45309'], ['Reassessment Required', '#dc2626']].map(([l, c]) => (
              <span className="lg" key={l}><span className="sw" style={{ background: c }} />{l}</span>
            ))}
          </div>
        </div>
        <RiskMap vendors={data.vendors} onSelect={(code) => nav(`/vendors/${code}`)} />
      </div>

      <div className="filters">
        <input className="search" placeholder="Search vendor…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">All types</option>
          <option value="supplier">Suppliers</option>
          <option value="service_provider">Service providers</option>
        </select>
        <select value={cls} onChange={(e) => setCls(e.target.value)}>
          <option value="">All classifications</option>
          {['Preferred', 'Approved', 'Conditional', 'Reassessment Required'].map((c) => <option key={c}>{c}</option>)}
        </select>
        <select value={risk} onChange={(e) => setRisk(e.target.value)}>
          <option value="">All risk</option>
          {['Low', 'Medium', 'Moderate', 'High'].map((r) => <option key={r}>{r}</option>)}
        </select>
      </div>

      <div className="panel table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Vendor</th><th>Type</th><th>Score</th><th>Classification</th><th>Risk</th><th>Recommended control</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((v) => (
              <tr key={v.vendor_code} className={v.risk === 'High' ? 'high-row' : ''} onClick={() => nav(`/vendors/${v.vendor_code}`)}>
                <td>
                  <div className="vname">{v.name}</div>
                  <div className="vsub mono">{v.vendor_code} · {v.country}</div>
                </td>
                <td><span className="badge b-neutral">{v.type === 'supplier' ? 'Supplier' : 'Service'}</span></td>
                <td className="score-cell">{v.final_score}</td>
                <td><ClassBadge value={v.classification} /></td>
                <td><RiskBadge value={v.risk} /></td>
                <td className="muted" style={{ fontSize: 12, maxWidth: 260 }}>{v.next_action.system_control}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
