import { Cpu, TrendingDown, FlaskConical } from 'lucide-react'

const MACHINE_ORDER = ['4090', '3080']
const MACHINE_CONFIG = {
  '4090': { label: 'RTX 4090', colorClass: 'machine-4090', icon: Cpu },
  '3080': { label: 'RTX 3080', colorClass: 'machine-3080', icon: Cpu },
}

export default function FleetStatusCards({ status }) {
  return (
    <div className="fleet-cards">
      {MACHINE_ORDER.map((id) => {
        const config = MACHINE_CONFIG[id]
        const data = status?.[id]
        const hasError = data?.error
        const Icon = config.icon

        return (
          <div key={id} className={`card ${config.colorClass}`}>
            <div className="card-header">
              <Icon size={20} />
              <span className="card-machine-name">{config.label}</span>
              <span className="card-machine-id">({id})</span>
            </div>
            {hasError ? (
              <div className="card-error">{data.error}</div>
            ) : (
              <div className="card-stats">
                <div className="stat">
                  <FlaskConical size={16} />
                  <span className="stat-value">{data?.experiment_count ?? '—'}</span>
                  <span className="stat-label">experiments</span>
                </div>
                <div className="stat">
                  <TrendingDown size={16} />
                  <span className="stat-value">
                    {data?.best_val_bpb != null ? data.best_val_bpb.toFixed(6) : '—'}
                  </span>
                  <span className="stat-label">best val_bpb</span>
                </div>
                <div className="stat">
                  <div className={`researcher-dot ${data?.researcher_running ? 'running' : 'stopped'}`} />
                  <span className="stat-value">
                    {data?.researcher_running ? 'Running' : 'Stopped'}
                  </span>
                  <span className="stat-label">researcher</span>
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
