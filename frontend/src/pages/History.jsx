import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import {
  ErrorBox,
  Loading,
  formatProbability,
  formatTime,
} from '../components/Feedback.jsx'

export default function History() {
  const [batches, setBatches] = useState(null)
  const [logs, setLogs] = useState(null)
  const [selected, setSelected] = useState(null)
  const [onlyMine, setOnlyMine] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const params = onlyMine ? { mine: 'true' } : {}
      const [batchList, logList] = await Promise.all([
        api.batches(params),
        api.logs({ ...params, limit: 50 }),
      ])
      setBatches(batchList)
      setLogs(logList)
    } catch (err) {
      setError(err)
      setBatches([])
      setLogs([])
    }
  }, [onlyMine])

  useEffect(() => {
    load()
  }, [load])

  async function openBatch(id) {
    setSelected('loading')
    try {
      setSelected(await api.batch(id))
    } catch (err) {
      setError(err)
      setSelected(null)
    }
  }

  return (
    <>
      <h1>History</h1>
      <p className="subtitle">Everything submitted through this service, read back from the database.</p>

      <ErrorBox error={error} />

      <div className="actions" style={{ marginTop: 0, marginBottom: 12 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="checkbox"
            checked={onlyMine}
            onChange={(e) => setOnlyMine(e.target.checked)}
          />
          Only my submissions
        </label>
        <button className="secondary" onClick={load}>
          Refresh
        </button>
      </div>

      <div className="panel">
        <h2>Uploaded batches</h2>
        {batches === null ? (
          <Loading />
        ) : batches.length === 0 ? (
          <p className="muted">No batches yet. Upload a CSV on the Batch page.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>File</th>
                  <th>Source</th>
                  <th>By</th>
                  <th>Model</th>
                  <th>Rows</th>
                  <th>Scored</th>
                  <th>Rejected</th>
                  <th>When</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {batches.map((batch) => (
                  <tr key={batch.id}>
                    <td>{batch.id}</td>
                    <td>{batch.filename}</td>
                    <td>{batch.source}</td>
                    <td>{batch.uploaded_by}</td>
                    <td>{batch.model_version}</td>
                    <td>{batch.row_count}</td>
                    <td>{batch.success_count}</td>
                    <td>{batch.error_count}</td>
                    <td>{formatTime(batch.created_at)}</td>
                    <td>
                      <button className="secondary" onClick={() => openBatch(batch.id)}>
                        View rows
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected === 'loading' && <Loading>Loading batch...</Loading>}
      {selected && selected !== 'loading' && (
        <div className="panel">
          <h2>
            Batch #{selected.id} - {selected.filename}{' '}
            <button
              className="secondary"
              style={{ float: 'right' }}
              onClick={() => setSelected(null)}
            >
              Close
            </button>
          </h2>
          <LogTable logs={selected.logs} showRow />
        </div>
      )}

      <div className="panel">
        <h2>Recent inferences</h2>
        {logs === null ? (
          <Loading />
        ) : logs.length === 0 ? (
          <p className="muted">Nothing logged yet.</p>
        ) : (
          <LogTable logs={logs} />
        )}
      </div>
    </>
  )
}

function LogTable({ logs, showRow = false }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            {showRow && <th>Row</th>}
            <th>Status</th>
            <th>Prediction</th>
            <th>Confidence</th>
            <th>Model</th>
            <th>Type</th>
            <th>By</th>
            <th>Latency</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id}>
              <td>{log.id}</td>
              {showRow && <td>{log.row_index}</td>}
              <td>
                <span className={`badge ${log.status}`}>{log.status}</span>
              </td>
              <td>
                {log.status === 'error' ? (
                  <span className="muted" title={log.error_message}>
                    {truncate(log.error_message)}
                  </span>
                ) : log.predicted_class === 1 ? (
                  'Diabetes or prediabetes'
                ) : (
                  'No diabetes'
                )}
              </td>
              <td>{formatProbability(log.probability)}</td>
              <td>{log.model_version}</td>
              <td>{log.request_type}</td>
              <td>{log.requested_by}</td>
              <td>{log.latency_ms ? `${log.latency_ms.toFixed(1)} ms` : '-'}</td>
              <td>{formatTime(log.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function truncate(text, length = 48) {
  if (!text) return '-'
  return text.length > length ? `${text.slice(0, length)}...` : text
}
