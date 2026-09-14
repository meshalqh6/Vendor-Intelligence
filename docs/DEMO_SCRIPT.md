# VendorLens — Demo Script

All figures below are produced by the deterministic rules engine from the seeded
database (`data/vendorlens.db`, identical every run, reference date **2026-08-01**).
The LLM (Claude, Opus 4.8) only retrieves and explains them.

## The one-sentence pitch
> Ask questions in natural language about risk-scored supplier and service-provider
> performance, and get answers traceable back to source records — because the
> scores are computed by an auditable rules engine, not the language model.

## Planted scenarios

| Vendor | Code | What it demonstrates | Engine result |
|--------|------|----------------------|---------------|
| **Al Wajba Packaging** | `SUP-1001` | Scores **96%** but an **expired mandatory ISO 22000 certificate** forces High Risk (hard override). | **96.0 → Preferred / High Risk** |
| **Almarai Trading Est.** | `SUP-1002` | Perfect scorer with an **open critical NCR** — second Preferred / High-Risk case. | **100.0 → Preferred / High Risk** |
| **Bayara Foods** | `SUP-1003` | Sits at exactly **74.6%**, 0.4 under the Conditional cutoff — the classification boundary. | **74.6 → Reassessment Required / Moderate** |
| **Gulf Dairy Feeds** | `SUP-1004` | Quality fell sharply over the **last two quarters**; inspection lots are the audit trail. | Declining quality trend |
| **Doha Calibration Services** | `SRV-2003` | An **overdue CAPA** forces High Risk and holds it in Conditional. Closing it this week → **Approved** and the risk clears. | **84.8 → Conditional / High** |
| **Emirates Facilities Management** | `SRV-2001` | A recorded **HSE incident** auto-escalates a service provider regardless of score. | High Risk (HSE trigger) |
| **Nadec Logistics** | `SRV-2002` | **Three documents expiring within 30 days** (incl. a mandatory ISO 45001). | On the Alerts watchlist |

## The six pre-built questions (buttons on the Ask page)

1. **"Which of our suppliers are high risk right now, and what's driving it?"**
   → lists the high-risk suppliers (Al Wajba, Almarai, plus any with expired mandatory
   docs / blocked status) with the trigger + cited record for each.
2. **"Al Wajba Packaging scores 96% but you've flagged them high risk — why?"**
   → the money shot. Surfaces the expired-certificate hard override cleanly, cites the `DOC…` id.
3. **"Show me exactly which inspection lots produced Gulf Dairy Feeds' quality score."**
   → the audit-trail moment. Pulls the inspection-lot rows with lot numbers, accepted/rejected qty and usage decisions.
4. **"What changes if Doha Calibration Services closes its overdue CAPA this week?"**
   → before/after. Conditional / High → Approved, and the next action flips from
   "escalate + restrict new business" to standard monitoring.
5. **"Which vendors have mandatory documents expiring in the next 30 days?"**
   → the proactive watchlist, mandatory documents highlighted.
6. **"Generate the Q2 evaluation report for all transport and logistics providers."**
   → filters to Logistics-category providers and produces a scored evaluation summary.

## The point to land
Every number on every screen traces to a source row and a config threshold. The
weights live in `config/scoring.yaml`. The language model never produces a number;
it only fetches and explains them — which is exactly what "KPI calculations are
fully automated and traceable" demands.
