import MarketSnapshot from './MarketSnapshot'
import { JournalIcon, PencilIcon } from './WorkspaceIcons'

type Props = { running: boolean; onConfigure: () => void; onSaved: () => void; onJournal: () => void }

export default function StartScreen({ running, onConfigure, onSaved, onJournal }: Props) {
  return <section className="start-screen" aria-label="Backtest workspace">
    <div className="start-main">
      <div className="start-copy">
        <h2>{running ? 'Running your backtest.' : <>Start with<br /><em>a question.</em></>}</h2>
        <p>{running ? 'Fetching prices and calculating results.' : 'Turn a strategy idea into a backtest.'}</p>
        <button className="start-button" onClick={onConfigure}><PencilIcon />{running ? 'View progress' : 'Set up backtest'}<span aria-hidden="true">↗</span></button>
      </div>
      <MarketSnapshot />
    </div>
    <div className="start-shortcuts">
      <button onClick={onSaved}><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true"><rect x="4" y="8" width="16" height="12" rx="2" /><path d="M3 4h18v4H3zM9 12h6" /></svg><span><strong>Saved runs</strong><small>Open a previous result.</small></span><span className="shortcut-arrow" aria-hidden="true">↗</span></button>
      <button onClick={onJournal}><JournalIcon /><span><strong>Journal</strong><small>Read or write an idea.</small></span><span className="shortcut-arrow" aria-hidden="true">↗</span></button>
    </div>
  </section>
}
