// Small shared pieces for the three states every page has to handle:
// loading, error, and data.

export function ErrorBox({ error }) {
  if (!error) return null

  // Validation errors carry a per-field list; show it so the user knows what
  // to fix rather than just "request failed".
  const details = error.details || []

  return (
    <div className="alert error">
      <strong>{error.message}</strong>
      {details.length > 0 && (
        <ul>
          {details.slice(0, 12).map((detail, index) => (
            <li key={index}>
              {detail.field ? <code>{detail.field}</code> : null} {detail.message}
            </li>
          ))}
          {details.length > 12 && <li>...and {details.length - 12} more</li>}
        </ul>
      )}
    </div>
  )
}

export function Loading({ children = 'Loading...' }) {
  return <div className="loading">{children}</div>
}

export function StatusBadge({ status }) {
  return <span className={`badge ${status}`}>{status}</span>
}

export function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export function formatProbability(value) {
  return value === null || value === undefined ? '-' : `${(value * 100).toFixed(1)}%`
}
