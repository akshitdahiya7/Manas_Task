import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setSession } from '../api.js'
import { ErrorBox } from '../components/Feedback.jsx'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const result = await api.login(username, password)
      const user = { username: result.username, role: result.role }
      setSession(result.access_token, user)
      onLogin(user)
      navigate('/predict')
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="panel">
        <h1>MANAS Inference</h1>
        <p className="subtitle">Sign in to run predictions.</p>

        <ErrorBox error={error} />

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" disabled={busy}>
            {busy ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <p className="help muted" style={{ marginTop: 14, fontSize: 12 }}>
          Demo accounts are listed in the README. An <code>admin</code> can promote and roll
          back models; a <code>viewer</code> can only predict and read.
        </p>
      </div>
    </div>
  )
}
