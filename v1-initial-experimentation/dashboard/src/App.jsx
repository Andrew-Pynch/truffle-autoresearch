import { useEffect, useState, useCallback } from 'react'
import Header from './components/Header'
import FleetStatusCards from './components/FleetStatusCards'
import TrajectoryChart from './components/TrajectoryChart'
import ControlPanel from './components/ControlPanel'
import TrufflePanel from './components/TrufflePanel'
import LogViewer from './components/LogViewer'
import { checkHealth, getStatus } from './api'

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('api_token') || 'test')
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState(null)

  useEffect(() => {
    localStorage.setItem('api_token', token)
  }, [token])

  const refreshStatus = useCallback(async () => {
    try {
      const s = await getStatus(token)
      setStatus(s)
    } catch (e) {
      console.error('Status fetch failed:', e)
    }
  }, [token])

  // Health check polling
  useEffect(() => {
    const check = async () => {
      try {
        await checkHealth()
        setConnected(true)
      } catch {
        setConnected(false)
      }
    }
    check()
    const interval = setInterval(check, 10000)
    return () => clearInterval(interval)
  }, [])

  // Status polling
  useEffect(() => {
    if (!token) return
    refreshStatus()
    const interval = setInterval(refreshStatus, 10000)
    return () => clearInterval(interval)
  }, [token, refreshStatus])

  return (
    <div className="app">
      <Header connected={connected} token={token} onTokenChange={setToken} />
      <main className="main">
        <FleetStatusCards status={status} />
        <TrajectoryChart token={token} />
        <div className="bottom-panels">
          <ControlPanel status={status} token={token} onAction={refreshStatus} />
          <TrufflePanel token={token} />
        </div>
        <LogViewer token={token} />
      </main>
    </div>
  )
}
