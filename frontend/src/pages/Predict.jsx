import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { FEATURES, FEATURE_ORDER, SAMPLE_RECORD } from '../features.js'
import { ErrorBox, formatProbability, formatTime } from '../components/Feedback.jsx'

export default function Predict() {
  // Form values are kept as strings so a cleared input stays empty instead of
  // silently becoming 0; they are converted just before submitting.
  const [values, setValues] = useState(() => toStrings(SAMPLE_RECORD))
  const [versions, setVersions] = useState([])
  const [version, setVersion] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.models().then(setVersions).catch(() => setVersions([]))
  }, [])

  function update(name, value) {
    setValues((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setResult(null)
    setBusy(true)

    try {
      const record = {}
      for (const name of FEATURE_ORDER) {
        const raw = (values[name] ?? '').trim()
        // Send empty inputs as null so the backend reports the missing field
        // rather than the browser coercing it to something valid-looking.
        record[name] = raw === '' ? null : Number(raw)
      }
      setResult(await api.predict(record, version || undefined))
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const fieldErrors = error?.fieldErrors || {}

  return (
    <>
      <h1>Single prediction</h1>
      <p className="subtitle">
        The form is pre-filled with a valid sample record, so you can submit it straight away.
      </p>

      <ErrorBox error={error} />

      {result && (
        <div className="panel">
          <div className="result-headline">
            <span className="cls">{result.predicted_label}</span>
            <span className={`badge ${result.predicted_class === 1 ? 'error' : 'success'}`}>
              class {result.predicted_class}
            </span>
            <span>
              confidence <strong>{formatProbability(result.probability)}</strong>
            </span>
          </div>
          <div className="muted mono">
            model {result.model_version} &middot; preprocessing {result.preprocessing_version}{' '}
            &middot; {result.latency_ms.toFixed(1)} ms &middot; {formatTime(result.timestamp)}
          </div>
          <div className="muted mono">input hash {result.input_hash}</div>
        </div>
      )}

      <form className="panel" onSubmit={handleSubmit}>
        <div className="field" style={{ maxWidth: 320, marginBottom: 16 }}>
          <label htmlFor="version">Model version</label>
          <select id="version" value={version} onChange={(e) => setVersion(e.target.value)}>
            <option value="">Active model (default)</option>
            {versions.map((model) => (
              <option key={model.version} value={model.version}>
                {model.version} - {model.display_name} ({model.status})
              </option>
            ))}
          </select>
          <span className="help">Leave on the default to use whatever is in production.</span>
        </div>

        <div className="grid">
          {FEATURE_ORDER.map((name) => {
            const [label, min, max, help] = FEATURES[name]
            const fieldError = fieldErrors[name]
            return (
              <div className={`field ${fieldError ? 'invalid' : ''}`} key={name}>
                <label htmlFor={name}>{label}</label>
                <input
                  id={name}
                  type="number"
                  min={min}
                  max={max}
                  step="1"
                  value={values[name]}
                  onChange={(e) => update(name, e.target.value)}
                />
                <span className="help">{help}</span>
                {fieldError && <span className="field-error">{fieldError}</span>}
              </div>
            )
          })}
        </div>

        <div className="actions">
          <button type="submit" disabled={busy}>
            {busy ? 'Predicting...' : 'Predict'}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setValues(toStrings(SAMPLE_RECORD))
              setError(null)
              setResult(null)
            }}
          >
            Reset to sample
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => update('BMI', '500')}
            title="Sets BMI to an out-of-range value to show backend validation"
          >
            Try an invalid value
          </button>
        </div>
      </form>
    </>
  )
}

function toStrings(record) {
  return Object.fromEntries(Object.entries(record).map(([key, value]) => [key, String(value)]))
}
