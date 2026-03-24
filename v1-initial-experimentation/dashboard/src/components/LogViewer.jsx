import { useEffect, useState, useRef } from 'react'
import { ChevronDown, ChevronRight, Terminal } from 'lucide-react'
import { getLogs } from '../api'

export default function LogViewer({ token }) {
  const [expanded, setExpanded] = useState(false)
  const [activeTab, setActiveTab] = useState('3080')
  const [lines, setLines] = useState([])
  const [loading, setLoading] = useState(false)
  const logRef = useRef(null)

  useEffect(() => {
    if (!expanded || !token) return
    const load = async () => {
      setLoading(true)
      try {
        const data = await getLogs(activeTab, token)
        setLines(data.lines || [])
      } catch (e) {
        setLines([`Error loading logs: ${e.message}`])
      } finally {
        setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 15000)
    return () => clearInterval(interval)
  }, [expanded, activeTab, token])

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [lines])

  return (
    <div className="log-viewer">
      <button className="log-toggle" onClick={() => setExpanded(!expanded)}>
        {expanded ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
        <Terminal size={20} />
        <span>Live Logs</span>
        {loading && <span className="log-loading">loading...</span>}
      </button>
      {expanded && (
        <>
          <div className="log-tabs">
            {['3080', '4090'].map((tab) => (
              <button
                key={tab}
                className={`log-tab ${activeTab === tab ? 'active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab === '4090' ? 'RTX 4090' : 'RTX 3080'}
              </button>
            ))}
          </div>
          <div className="log-content" ref={logRef}>
            {lines.map((line, i) => (
              <div key={i} className="log-line">{line}</div>
            ))}
            {lines.length === 0 && <div className="log-empty">No log data available</div>}
          </div>
        </>
      )}
    </div>
  )
}
