import { useState } from 'react'
import { Play, Square, RefreshCw } from 'lucide-react'
import { startResearcher, stopResearcher, syncResults } from '../api'

function MachineControl({ machineId, label, colorClass, running, token, onAction }) {
  const [loading, setLoading] = useState(null)
  const [feedback, setFeedback] = useState(null)

  const doAction = async (action, fn) => {
    setLoading(action)
    setFeedback(null)
    try {
      await fn(machineId, token)
      setFeedback({ type: 'success', msg: `${action} succeeded` })
      onAction()
    } catch (e) {
      setFeedback({ type: 'error', msg: e.message })
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className={`control-card ${colorClass}`}>
      <h3>{label}</h3>
      <div className="control-buttons">
        {running ? (
          <button
            className="btn btn-danger"
            disabled={loading}
            onClick={() => doAction('Stop', stopResearcher)}
          >
            {loading === 'Stop' ? <RefreshCw size={16} className="spin" /> : <Square size={16} />}
            Stop Researcher
          </button>
        ) : (
          <button
            className="btn btn-success"
            disabled={loading}
            onClick={() => doAction('Start', startResearcher)}
          >
            {loading === 'Start' ? <RefreshCw size={16} className="spin" /> : <Play size={16} />}
            Start Researcher
          </button>
        )}
        <button
          className="btn btn-secondary"
          disabled={loading}
          onClick={() => doAction('Sync', syncResults)}
        >
          {loading === 'Sync' ? <RefreshCw size={16} className="spin" /> : <RefreshCw size={16} />}
          Sync Results
        </button>
      </div>
      {feedback && (
        <div className={`feedback ${feedback.type}`}>{feedback.msg}</div>
      )}
    </div>
  )
}

export default function ControlPanel({ status, token, onAction }) {
  return (
    <div className="control-panel">
      <h2 className="section-title">Fleet Control</h2>
      <div className="control-grid">
        <MachineControl
          machineId="4090"
          label="RTX 4090"
          colorClass="machine-4090"
          running={status?.['4090']?.researcher_running}
          token={token}
          onAction={onAction}
        />
        <MachineControl
          machineId="3080"
          label="RTX 3080"
          colorClass="machine-3080"
          running={status?.['3080']?.researcher_running}
          token={token}
          onAction={onAction}
        />
      </div>
    </div>
  )
}
