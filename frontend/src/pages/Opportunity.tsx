import { FormEvent, useEffect, useState } from 'react'
import { getVendors, matchVendors } from '../api'
import type { OpportunityMatch, OpportunityMatchResponse, VendorsResponse } from '../types'

const fieldStyle = { width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 9, font: 'inherit' }

export default function Opportunity() {
  const [portfolio, setPortfolio] = useState<VendorsResponse | null>(null)
  const [category, setCategory] = useState('')
  const [capabilities, setCapabilities] = useState('')
  const [maxLead, setMaxLead] = useState('30')
  const [minTerms, setMinTerms] = useState('30')
  const [preferred, setPreferred] = useState('')
  const [result, setResult] = useState<OpportunityMatchResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { getVendors().then(setPortfolio).catch(() => setError('Could not load the vendor portfolio.')) }, [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const response = await matchVendors({
        category: category || undefined,
        required_capabilities: capabilities.split(',').map(x => x.trim()).filter(Boolean),
        preferred_vendor_codes: preferred.split(',').map(x => x.trim()).filter(Boolean),
        max_lead_time_days: Number(maxLead) || undefined,
        minimum_payment_terms_days: Number(minTerms) || undefined,
      })
      setResult(response)
    } catch {
      setError('Matching failed. Confirm that the backend is running.')
    } finally { setBusy(false) }
  }

  const categories = [...new Set(portfolio?.vendors.map(v => v.category) || [])]

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Procurement decision support</div>
          <h1>Opportunity Match</h1>
          <div className="sub">Find the best-fit vendor for a specific request using transparent, weighted criteria.</div>
        </div>
        <div className="source-note">Historical performance stays separate from opportunity fit.</div>
      </div>

      <div className="opportunity-layout">
        <form className="panel panel-pad opportunity-form" onSubmit={submit}>
          <div className="section-title" style={{ marginTop: 0 }}>Define the opportunity</div>
          <label className="fld"><span>Category</span>
            <select style={fieldStyle} value={category} onChange={e => setCategory(e.target.value)}>
              <option value="">All categories</option>
              {categories.map(c => <option key={c}>{c}</option>)}
            </select>
          </label>
          <label className="fld"><span>Required capabilities</span>
            <input style={fieldStyle} value={capabilities} onChange={e => setCapabilities(e.target.value)} placeholder="e.g. cloud, cybersecurity, logistics" />
            <small className="muted">Separate capabilities with commas.</small>
          </label>
          <div className="form-two">
            <label className="fld"><span>Maximum lead time (days)</span><input style={fieldStyle} type="number" min="0" value={maxLead} onChange={e => setMaxLead(e.target.value)} /></label>
            <label className="fld"><span>Minimum payment terms (days)</span><input style={fieldStyle} type="number" min="0" value={minTerms} onChange={e => setMinTerms(e.target.value)} /></label>
          </div>
          <label className="fld"><span>Preferred vendor codes</span>
            <input style={fieldStyle} value={preferred} onChange={e => setPreferred(e.target.value)} placeholder="e.g. SUP-1001, SRV-2001" />
          </label>
          <div className="match-info"><span>ⓘ</span><div>Quote-specific values such as price, lead time, and payment terms can be supplied through the API and are never stored as permanent vendor attributes.</div></div>
          <button className="btn-primary" type="submit" disabled={busy}>{busy ? 'Ranking vendors…' : 'Run opportunity match →'}</button>
          {error && <div className="error-text">{error}</div>}
        </form>

        <div className="panel panel-pad match-results">
          <div className="results-head"><div><div className="section-title" style={{ margin: 0 }}>Recommended vendors</div><div className="muted" style={{ fontSize: 12 }}>Ranked by the configured opportunity weights.</div></div>{result && <span className="badge b-neutral">{result.matches.length} evaluated</span>}</div>
          {!result ? <div className="empty-state"><div className="empty-icon">✦</div><b>Ready to evaluate an opportunity</b><span>Enter the request details and the engine will return an auditable ranking.</span></div> :
            <div className="match-list">{result.matches.map((v, i) => <MatchRow key={v.vendor_code} vendor={v} rank={i + 1} />)}</div>}
        </div>
      </div>

      <div className="panel panel-pad methodology">
        <div className="section-title" style={{ marginTop: 0 }}>How the ranking works</div>
        <div className="weight-grid">{Object.entries(result?.weights || {
          capability_fit: { label: 'Capability Fit', weight: .30 },
          preferred_partner: { label: 'Preferred Partner', weight: .15 },
          supplier_rating: { label: 'Supplier Rating', weight: .15 },
          lead_time: { label: 'Lead Time', weight: .15 },
          payment_terms: { label: 'Payment Terms', weight: .10 },
          spend_balance: { label: 'Spend Balance', weight: .10 },
          opportunity_commercial_value: { label: 'Commercial Value', weight: .05 },
        }).map(([key, item]) => <div className="weight" key={key}><b>{item.label}</b><strong>{Math.round(item.weight * 100)}%</strong></div>)}</div>
      </div>
    </>
  )
}

function MatchRow({ vendor, rank }: { vendor: OpportunityMatch; rank: number }) {
  const [open, setOpen] = useState(false)
  return <div className={`match-row ${vendor.eligible ? '' : 'match-ineligible'}`}>
    <button className="match-summary" onClick={() => setOpen(!open)}>
      <span className="rank">{rank}</span>
      <span className="match-vendor"><b>{vendor.name}</b><small>{vendor.vendor_code} · {vendor.category}</small></span>
      <span className="match-history"><small>Historical</small><b>{vendor.historical_score ?? '—'}</b></span>
      <span className="match-score"><small>Opportunity score</small><b>{vendor.opportunity_score}</b></span>
      <span className="expand">{open ? '−' : '+'}</span>
    </button>
    {open && <div className="match-detail"><div className="component-grid">{vendor.components.map(c => <div key={c.key}><small>{c.label}</small><b>{c.value} <em>+{c.contribution}</em></b></div>)}</div><div className="muted" style={{ fontSize: 12, marginTop: 10 }}>{vendor.eligibility_reason}</div></div>}
  </div>
}
