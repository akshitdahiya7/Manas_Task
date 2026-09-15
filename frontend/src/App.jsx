import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { clearSession, getUser } from './api.js'
import Login from './pages/Login.jsx'
import Predict from './pages/Predict.jsx'
import Batch from './pages/Batch.jsx'
import History from './pages/History.jsx'
import Models from './pages/Models.jsx'

export default function App() {
  // Session lives in localStorage; this just mirrors it for rendering.
  const [user, setUser] = useState(getUser())
  const navigate = useNavigate()

  // api.js clears the token on a 401, so re-check when the tab regains focus.
  useEffect(() => {
    const sync = () => setUser(getUser())
    window.addEventListener('focus', sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener('focus', sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  function handleLogout() {
    clearSession()
    setUser(null)
    navigate('/login')
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login onLogin={setUser} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <>
      <nav className="nav">
        <span className="brand">MANAS Inference</span>
        <NavLink to="/predict">Predict</NavLink>
        <NavLink to="/batch">Batch</NavLink>
        <NavLink to="/history">History</NavLink>
        <NavLink to="/models">Models &amp; Dashboard</NavLink>
        <span className="spacer" />
        <span className="who">
          {user.username} ({user.role})
        </span>
        <button className="secondary" onClick={handleLogout}>
          Log out
        </button>
      </nav>

      <div className="container">
        <Routes>
          <Route path="/predict" element={<Predict />} />
          <Route path="/batch" element={<Batch />} />
          <Route path="/history" element={<History />} />
          <Route path="/models" element={<Models user={user} />} />
          <Route path="*" element={<Navigate to="/predict" replace />} />
        </Routes>
      </div>
    </>
  )
}
