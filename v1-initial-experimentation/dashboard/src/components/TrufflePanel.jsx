import { useState } from 'react'
import { Scan, List, CheckCircle, Rocket, RefreshCw } from 'lucide-react'
import AnsiToHtml from 'ansi-to-html'
import { runTruffile } from '../api'

const ansi = new AnsiToHtml({ fg: '#ccc', bg: 'transparent', newline: true })

const COMMANDS = [
  { id: 'scan', label: 'Scan', icon: Scan },
  { id: 'list-apps', label: 'List Apps', icon: List },
  { id: 'list-devices', label: 'List Devices', icon: List },
  { id: 'validate', label: 'Validate App', icon: CheckCircle },
  { id: 'deploy', label: 'Deploy App', icon: Rocket },
]

export default function TrufflePanel({ token }) {
  const [loading, setLoading] = useState(null)
  const [output, setOutput] = useState(null)

  const run = async (command) => {
    setLoading(command)
    setOutput(null)
    try {
      const result = await runTruffile(command, token)
      setOutput(result)
    } catch (e) {
      setOutput({ stdout: '', stderr: e.message, exit_code: -1 })
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="truffle-panel">
      <h2 className="section-title">Truffle Operations</h2>
      <p className="section-subtitle">Execute truffile commands on big-bertha (3080)</p>
      <div className="truffle-buttons">
        {COMMANDS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className="btn btn-truffle"
            disabled={loading}
            onClick={() => run(id)}
          >
            {loading === id ? <RefreshCw size={16} className="spin" /> : <Icon size={16} />}
            {label}
          </button>
        ))}
      </div>
      {output && (
        <div className="truffle-output">
          <div className="output-header">
            <span>Exit code: </span>
            <span className={output.exit_code === 0 ? 'exit-success' : 'exit-error'}>
              {output.exit_code}
            </span>
          </div>
          {output.stdout && (
            <div className="output-section">
              <div className="output-label">stdout</div>
              <pre dangerouslySetInnerHTML={{ __html: ansi.toHtml(output.stdout) }} />
            </div>
          )}
          {output.stderr && (
            <div className="output-section">
              <div className="output-label">stderr</div>
              <pre className="stderr" dangerouslySetInnerHTML={{ __html: ansi.toHtml(output.stderr) }} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
