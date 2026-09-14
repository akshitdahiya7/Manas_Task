import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { ErrorBox, formatProbability } from '../components/Feedback.jsx'

export default function Batch() {
  const [file, setFile] = useState(null)
  const [versions, setVersions] = useState([])
  const [version, setVersion] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.models().then(setVersions).catch(() => setVersions([]))
  }, [])

  async function handleSubmit(event) {
    event.preventDefault()
    if (!file) return

    setError(null)
    setResult(null)
    setBusy(true)
    try {
      setResult(await api.predictCsv(file, version || undefined))
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1>Batch prediction</h1>
      <p className="subtitle">
        Upload a CSV with the 21 feature columns. Rows are validated individually - invalid rows
        are reported without failing the whole file.
      </p>

      <ErrorBox error={error} />

      <form className="panel" onSubmit={handleSubmit}>
        <div className="field" style={{ marginBottom: 12 }}>
          <label htmlFor="csv">CSV file</label>
          <input
            id="csv"
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <span className="help">
            No file handy? <a href="/sample_batch.csv" download>Download a 20-row sample</a>.
          </span>
        </div>

        <div className="field" style={{ maxWidth: 320 }}>
          <label htmlFor="batch-version">Model version</label>
          <select
            id="batch-version"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
          >
            <option value="">Active model (default)</option>
            {versions.map((model) => (
              <option key={model.version} value={model.version}>
                {model.version} - {model.display_name} ({model.status})
              </option>
            ))}
          </select>
        </div>

        <div className="actions">
          <button type="submit" disabled={busy || !file}>
            {busy ? 'Scoring...' : 'Run batch inference'}
          </button>
        </div>
      </form>

      {result && <BatchResult result={result} />}
    </>
  )
}

function BatchResult({ result }) {
  return (
    <div className="panel">
      <h2>
        Batch #{result.batch_id} &middot; {result.model_version}
      </h2>

      <div className="tiles" style={{ marginBottom: 16 }}>
        <div className="tile">
          <div className="value">{result.row_count}</div>
          <div className="label">rows</div>
        </div>
        <div className="tile">
          <div className="value" style={{ color: 'var(--ok)' }}>{result.success_count}</div>
          <div className="label">scored</div>
        </div>
        <div className="tile">
          <div className="value" style={{ color: result.error_count ? 'var(--err)' : undefined }}>
            {result.error_count}
          </div>
          <div className="label">rejected</div>
        </div>
      </div>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Row</th>
              <th>Status</th>
              <th>Prediction</th>
              <th>Confidence</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {result.results.map((row) => (
              <tr key={row.row_index}>
                <td>{row.row_index}</td>
                <td>
                  <span className={`badge ${row.status}`}>{row.status}</span>
                </td>
                <td>{row.status === 'success' ? row.predicted_label : '-'}</td>
                <td>{row.status === 'success' ? formatProbability(row.probability) : '-'}</td>
                <td style={{ whiteSpace: 'normal' }}>
                  {row.status === 'error' ? (
                    <span className="muted">
                      {row.errors.map((e) => `${e.field}: ${e.message}`).join('; ')}
                    </span>
                  ) : (
                    <span className="muted mono">{row.input_hash?.slice(0, 12)}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
