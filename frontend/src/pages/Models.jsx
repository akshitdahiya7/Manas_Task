import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { ErrorBox, Loading, formatTime } from '../components/Feedback.jsx'

export default function Models({ user }) {
  const [models, setModels] = useState(null)
  const [promotions, setPromotions] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)

  const isAdmin = user.role === 'admin'

  const load = useCallback(async () => {
    setError(null)
    try {
      const [modelList, history, summary] = await Promise.all([
        api.models(),
        api.promotions(),
        api.metrics(),
      ])
      setModels(modelList)
      setPromotions(history)
      setMetrics(summary)
    } catch (err) {
      setError(err)
      setModels([])
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function act(action, version) {
    const what = action === 'promote' ? `promote ${version} to production` : 'roll back to the previous version'
    const reason = window.prompt(`Reason to ${what}?`, '')
    // null means cancelled; an empty string is a valid reason.
    if (reason === null) return

    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const result =
        action === 'promote' ? await api.promote(version, reason) : await api.rollback(reason)
      setNotice(`${result.version} is now in production.`)
      await load()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const active = models?.find((m) => m.status === 'production')

  return (
    <>
      <h1>Models &amp; dashboard</h1>
      <p className="subtitle">
        Promotion changes which registered version serves traffic. Artifacts are never
        overwritten, so a rollback is always available.
      </p>

      <ErrorBox error={error} />
      {notice && <div className="alert ok">{notice}</div>}

      {metrics && <MetricsPanel metrics={metrics} />}

      <div className="panel">
        <h2>Registered versions</h2>
        {models === null ? (
          <Loading />
        ) : (
          <>
            {active && (
              <p>
                Currently deployed: <strong>{active.version}</strong> ({active.display_name})
              </p>
            )}
            {models.map((model) => (
              <div
                className={`model-card ${model.status === 'production' ? 'active' : ''}`}
                key={model.version}
              >
                <div className="head">
                  <span className="name">{model.version}</span>
                  <span className={`badge ${model.status}`}>{model.status}</span>
                  <span className="muted">{model.display_name}</span>
                  <span className="muted mono">{model.framework}</span>
                  <span className="spacer" style={{ flex: 1 }} />
                  {isAdmin && model.status !== 'production' && (
                    <button disabled={busy} onClick={() => act('promote', model.version)}>
                      Promote
                    </button>
                  )}
                </div>
                {model.metrics && (
                  <div className="muted mono" style={{ marginTop: 6 }}>
                    accuracy {model.metrics.accuracy} &middot; precision {model.metrics.precision}{' '}
                    &middot; recall {model.metrics.recall} &middot; F1 {model.metrics.f1}
                  </div>
                )}
                {model.notes && <div className="muted" style={{ marginTop: 4 }}>{model.notes}</div>}
              </div>
            ))}

            {isAdmin ? (
              <div className="actions">
                <button className="danger" disabled={busy} onClick={() => act('rollback')}>
                  Roll back to previous version
                </button>
              </div>
            ) : (
              <p className="muted" style={{ marginTop: 12 }}>
                Promotion and rollback require the admin role.
              </p>
            )}
          </>
        )}
      </div>

      <div className="panel">
        <h2>Promotion history</h2>
        {promotions.length === 0 ? (
          <p className="muted">No promotions recorded yet.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Version</th>
                  <th>Action</th>
                  <th>From</th>
                  <th>To</th>
                  <th>By</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {promotions.map((event) => (
                  <tr key={event.id}>
                    <td>{formatTime(event.created_at)}</td>
                    <td>{event.version}</td>
                    <td>{event.action}</td>
                    <td>{event.from_status}</td>
                    <td>{event.to_status}</td>
                    <td>{event.performed_by}</td>
                    <td style={{ whiteSpace: 'normal' }}>{event.reason || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}

function MetricsPanel({ metrics }) {
  const latency = metrics.latency_ms || {}
  const distribution = metrics.prediction_distribution || {}
  const drift = metrics.drift || {}

  return (
    <div className="panel">
      <h2>Service monitoring</h2>
      <div className="tiles">
        <Tile value={metrics.total_inferences} label="total inferences" />
        <Tile value={metrics.inferences_last_24h} label="last 24 hours" />
        <Tile
          value={`${(metrics.error_rate * 100).toFixed(1)}%`}
          label="error rate"
          color={metrics.error_rate > 0.05 ? 'var(--err)' : undefined}
        />
        <Tile value={latency.p50 != null ? `${latency.p50} ms` : '-'} label="latency p50" />
        <Tile value={latency.p95 != null ? `${latency.p95} ms` : '-'} label="latency p95" />
        <Tile value={distribution.positive ?? 0} label="predicted positive" />
        <Tile value={distribution.negative ?? 0} label="predicted negative" />
        <Tile
          value={drift.positive_rate != null ? drift.positive_rate.toFixed(2) : '-'}
          label={`positive rate (baseline ${drift.baseline ?? '-'})`}
          color={drift.status === 'alert' ? 'var(--warn)' : undefined}
        />
      </div>

      {drift.status === 'alert' && (
        <p className="muted" style={{ marginTop: 10 }}>
          The recent positive rate differs from the training baseline by{' '}
          {drift.delta?.toFixed(2)} (threshold {drift.threshold}). This watches the model&apos;s
          output, not its inputs - worth investigating, not proof of drift.
        </p>
      )}

      {metrics.by_version?.length > 0 && (
        <p className="muted" style={{ marginTop: 10 }}>
          By version: {metrics.by_version.map((v) => `${v.version} (${v.count})`).join(', ')}
        </p>
      )}
    </div>
  )
}

function Tile({ value, label, color }) {
  return (
    <div className="tile">
      <div className="value" style={color ? { color } : undefined}>
        {value}
      </div>
      <div className="label">{label}</div>
    </div>
  )
}
