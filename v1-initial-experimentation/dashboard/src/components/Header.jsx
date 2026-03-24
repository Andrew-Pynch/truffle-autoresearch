import { Activity } from 'lucide-react'

export default function Header({ connected, token, onTokenChange }) {
  return (
    <header className="header">
      <div className="header-left">
        <div className="header-title-row">
          <Activity size={28} className="header-icon" />
          <h1>Truffle Autoresearch Fleet Dashboard</h1>
        </div>
        <p className="header-subtitle">Coordinating GPU experiments across personal hardware</p>
      </div>
      <div className="header-right">
        <div className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
        <span className="status-text">{connected ? 'Connected' : 'Disconnected'}</span>
        <input
          type="text"
          className="token-input"
          placeholder="API Token"
          value={token}
          onChange={(e) => onTokenChange(e.target.value)}
        />
      </div>
    </header>
  )
}
