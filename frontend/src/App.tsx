import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { getHealth } from './api'
import Dashboard from './pages/Dashboard'
import VendorDetail from './pages/VendorDetail'
import Ask from './pages/Ask'
import AlertsPage from './pages/Alerts'

export default function App() {
  const [health, setHealth] = useState<any>(null)
  useEffect(() => { getHealth().then(setHealth).catch(() => {}) }, [])

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">V</div>
          <div>
            <b>VendorLens</b>
            <span>Supplier performance</span>
          </div>
        </div>
        <nav className="nav">
          <NavLink to="/" end>◱ Dashboard</NavLink>
          <NavLink to="/ask">✦ Ask VendorLens</NavLink>
          <NavLink to="/alerts">⚑ Alerts</NavLink>
        </nav>
        <div className="foot">
          {health && (
            <>
              <div className="pill-live">
                <span className={`dot ${health.live_llm ? '' : 'mock'}`}></span>
                {health.live_llm ? `Live · ${health.model}` : 'Deterministic mock'}
              </div>
              <div style={{ marginTop: 6 }}>Data as of {health.as_of}</div>
            </>
          )}
          <div style={{ marginTop: 8 }}>Scores by rules engine.<br />LLM retrieves &amp; explains only.</div>
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/vendors/:code" element={<VendorDetail />} />
          <Route path="/ask" element={<Ask />} />
          <Route path="/alerts" element={<AlertsPage />} />
        </Routes>
      </main>
    </div>
  )
}
