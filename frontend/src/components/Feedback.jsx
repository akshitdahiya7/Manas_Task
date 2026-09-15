// Shared bits for the loading / error / data states.

export function ErrorBox({ error }) {
  if (!error) return null

  // Show the per-field list so the user knows what to fix.
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
