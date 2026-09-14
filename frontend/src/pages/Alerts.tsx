import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAlerts, sendFollowup } from '../api'
import type { Alerts } from '../types'

type Kind = 'expiring' | 'expired' | 'capa' | 'hse'

interface Draft {
  vendor_code: string; vendor_name: string; alert_type: Kind; record_id: string
  to: string; subject: string; body: string
}

function slug(name: string) {
  return name.toLowerCase().replace(/&/g, 'and').replace(/[^a-z0-9]+/g, '').slice(0, 20) || 'vendor'
}

function buildDraft(kind: Kind, it: any): Draft {
  const name = it.name as string
  const to = `Quality Manager, ${name} <qa@${slug(name)}.com>`
  const sign = '\n\nKind regards,\nSupplier Performance Team\nABC — VendorLens'
  let record_id = '', subject = '', body = ''
  if (kind === 'expiring') {
    record_id = it.doc_id
    subject = `Action required: ${it.doc_type} expiring in ${it.days_left} day${it.days_left === 1 ? '' : 's'}`
    body = `Dear ${name} team,\n\nOur supplier records show that your ${it.doc_type} (document ${it.doc_id}) is due to expire on ${it.expiry_date} — ${it.days_left} day(s) from today.${it.mandatory ? ' This is a mandatory certification for continued supply under our FSSC 22000 / ISO 22000 programme.' : ''}\n\nPlease share a renewed, valid copy before the expiry date. If the document lapses, our system will automatically flag your account as High Risk and place a hold on new business until a valid certificate is on file.${sign}`
  } else if (kind === 'expired') {
    record_id = it.doc_id
    subject = `Urgent: expired mandatory ${it.doc_type}`
    body = `Dear ${name} team,\n\nYour ${it.doc_type} (document ${it.doc_id}) expired on ${it.expiry_date}. As this is a mandatory certification, your account is currently classified as High Risk and new business has been restricted.\n\nPlease provide a valid, renewed certificate within 5 business days so we can lift the restriction and restore your standing.${sign}`
  } else if (kind === 'capa') {
    record_id = it.record_id
    subject = `Overdue ${it.type} ${it.record_id} — ${it.days_overdue} days past due`
    body = `Dear ${name} team,\n\nCorrective action ${it.record_id} (${it.severity}) was due on ${it.due_date} and is now ${it.days_overdue} days overdue. This has triggered a High-Risk status on your account.\n\nPlease submit your closure evidence and root-cause documentation as a priority. Continued delay will be escalated to management review.${sign}`
  } else {
    record_id = it.incident_id
    subject = `HSE incident ${it.incident_id} — corrective action required`
    body = `Dear ${name} team,\n\nAn HSE incident (${it.incident_id}, ${it.severity}) was recorded on ${it.incident_date}: ${it.description}\n\nPer ISO 45001 requirements, please provide your incident investigation report, root-cause analysis and corrective action plan within 10 business days. This incident has triggered an automatic escalation on your account.${sign}`
  }
  return { vendor_code: it.vendor_code, vendor_name: name, alert_type: kind, record_id, to, subject, body }
}

function FollowUpModal({ draft, onClose, onSent }: { draft: Draft; onClose: () => void; onSent: (id: string) => void }) {
  const [subject, setSubject] = useState(draft.subject)
  const [body, setBody] = useState(draft.body)
  const [state, setState] = useState<'edit' | 'sending' | 'sent'>('edit')
  const [ref, setRef] = useState('')

  async function send() {
    setState('sending')
    try {
      const r = await sendFollowup({ ...draft, subject, body })
      setRef(r.reference)
      setState('sent')
      setTimeout(() => { onSent(draft.record_id); onClose() }, 1600)
    } catch {
      setState('edit')
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        {state === 'sent' ? (
          <div className="modal-sent">
            <div className="sent-check">✓</div>
            <div className="sent-title">Follow-up queued</div>
            <div className="muted">Reference <b>{ref}</b> · sent to {draft.vendor_name}</div>
          </div>
        ) : (
          <>
            <div className="modal-head">
              <div>
                <div className="modal-title">Send follow-up</div>
                <div className="muted" style={{ fontSize: 12 }}>{draft.vendor_name} · re: <span className="mono">{draft.record_id}</span></div>
              </div>
              <button className="modal-x" onClick={onClose}>✕</button>
            </div>
            <label className="fld"><span>To</span><input value={draft.to} readOnly className="ro" /></label>
            <label className="fld"><span>Subject</span><input value={subject} onChange={(e) => setSubject(e.target.value)} /></label>
            <label className="fld"><span>Message</span><textarea rows={11} value={body} onChange={(e) => setBody(e.target.value)} /></label>
            <div className="modal-actions">
              <button className="btn-ghost2" onClick={onClose} disabled={state === 'sending'}>Cancel</button>
              <button className="btn" onClick={send} disabled={state === 'sending'}>
                {state === 'sending' ? 'Sending…' : '➤ Send follow-up'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default function AlertsPage() {
  const [a, setA] = useState<Alerts | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [sent, setSent] = useState<Set<string>>(new Set())
  useEffect(() => { getAlerts().then(setA) }, [])
  if (!a) return <div className="loading">Loading alerts…</div>

  const link = (code: string, label: string) => <Link to={`/vendors/${code}`} className="vname" style={{ color: 'var(--accent)' }}>{label}</Link>

  const action = (kind: Kind, it: any, id: string) => (
    sent.has(id)
      ? <span className="badge b-good" style={{ marginTop: 6 }}>✓ Follow-up sent</span>
      : <button className="followup-btn" onClick={() => setDraft(buildDraft(kind, it))}>✉ Send follow-up</button>
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Alerts &amp; Watchlist</h1>
          <div className="sub">Proactive triggers computed from source records · as of {a.as_of}</div>
        </div>
      </div>

      <div className="two-col">
        <div className="panel panel-pad">
          <div className="section-title" style={{ marginTop: 0 }}>⚠ HSE incidents ({a.hse_incidents.length})</div>
          {a.hse_incidents.length === 0 && <div className="muted">None.</div>}
          {a.hse_incidents.map((h) => (
            <div className="alert-item" key={h.incident_id}>
              <div>{link(h.vendor_code, h.name)}<div className="muted" style={{ fontSize: 12 }}>{h.severity} · {h.description}</div></div>
              <div className="alert-right"><span className="muted mono">{h.incident_date}</span>{action('hse', h, h.incident_id)}</div>
            </div>
          ))}
        </div>

        <div className="panel panel-pad">
          <div className="section-title" style={{ marginTop: 0 }}>⏰ Overdue CAPAs ({a.overdue_capa.length})</div>
          {a.overdue_capa.length === 0 && <div className="muted">None.</div>}
          {a.overdue_capa.map((c) => (
            <div className="alert-item" key={c.record_id}>
              <div>{link(c.vendor_code, c.name)}<div className="muted" style={{ fontSize: 12 }}><span className="mono">{c.record_id}</span> · {c.severity}</div></div>
              <div className="alert-right"><span className="badge b-bad">{c.days_overdue}d overdue</span>{action('capa', c, c.record_id)}</div>
            </div>
          ))}
        </div>

        <div className="panel panel-pad">
          <div className="section-title" style={{ marginTop: 0 }}>📄 Documents expiring ≤ 30 days ({a.expiring_documents.length})</div>
          {a.expiring_documents.length === 0 && <div className="muted">None.</div>}
          {a.expiring_documents.map((d) => (
            <div className="alert-item" key={d.doc_id}>
              <div>{link(d.vendor_code, d.name)}<div className="muted" style={{ fontSize: 12 }}>{d.doc_type}{d.mandatory ? ' · mandatory' : ''}</div></div>
              <div className="alert-right"><span className={`badge ${d.days_left <= 14 ? 'b-warn' : 'b-neutral'}`}>{d.days_left}d left</span>{action('expiring', d, d.doc_id)}</div>
            </div>
          ))}
        </div>

        <div className="panel panel-pad">
          <div className="section-title" style={{ marginTop: 0 }}>🎯 Boundary cases ({a.boundary_cases.length})</div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>Vendors within 1.0 point of a classification threshold.</div>
          {a.boundary_cases.map((b) => (
            <div className="alert-item" key={b.vendor_code}>
              <div>{link(b.vendor_code, b.name)}<div className="muted" style={{ fontSize: 12 }}>{b.classification} · {b.gap} below {b.threshold}</div></div>
              <div className="score-cell">{b.final_score}</div>
            </div>
          ))}
        </div>
      </div>

      {a.expired_mandatory_documents.length > 0 && (
        <div className="panel panel-pad" style={{ marginTop: 16 }}>
          <div className="section-title" style={{ marginTop: 0 }}>⛔ Expired mandatory documents ({a.expired_mandatory_documents.length})</div>
          {a.expired_mandatory_documents.map((d) => (
            <div className="alert-item" key={d.doc_id}>
              <div>{link(d.vendor_code, d.name)}<div className="muted" style={{ fontSize: 12 }}>{d.doc_type}</div></div>
              <div className="alert-right"><span className="badge b-bad">expired {d.expiry_date}</span>{action('expired', d, d.doc_id)}</div>
            </div>
          ))}
        </div>
      )}

      {draft && <FollowUpModal draft={draft} onClose={() => setDraft(null)} onSent={(id) => setSent((s) => new Set(s).add(id))} />}
    </>
  )
}
