import { useLayoutEffect, useRef, useState } from 'react'
import Journal, { JournalReference } from './components/Journal'
import { JournalIcon, PencilIcon } from './components/WorkspaceIcons'
import PortfolioDashboard from './components/PortfolioDashboard'
import StrategyLibrary from './components/StrategyLibrary'
import StartScreen from './components/StartScreen'
import WorkspaceLauncher from './components/WorkspaceLauncher'
import BacktestForm from './components/BacktestForm'
import PerformanceChart from './components/PerformanceChart'
import TradeTable from './components/TradeTable'
import RunHistory from './components/RunHistory'
import RunSettings from './components/RunSettings'
import { strategyNames } from './types/experiment'
import type { CompletedRun } from './types/experiment'
import { metric, money } from './lib/format'
import './workspace.css'
import './dashboard.css'
export default function App() {
  const drawer = useRef<HTMLDialogElement>(null)
  const editButton = useRef<HTMLButtonElement>(null)
  const closing = useRef(false)
  const [referenceOpen, setReferenceOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const openingAnimations = useRef<Animation[]>([])
  function alignEditorControls() {
    const anchor = editButton.current?.getBoundingClientRect()
    const controls = drawer.current?.querySelector<HTMLElement>('.editor-orbs')
    if (anchor && controls) {
      controls.style.top = `${anchor.top}px`
      controls.style.right = `${window.innerWidth - anchor.right}px`
    }
  }
  useLayoutEffect(() => {
    if (!editing) return
    alignEditorControls()
    window.addEventListener('resize', alignEditorControls)
    return () => window.removeEventListener('resize', alignEditorControls)
  }, [editing])
  function fadeCards(selector: string) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    drawer.current!.querySelectorAll<HTMLElement>(selector).forEach(card => {
      openingAnimations.current.push(card.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 140, easing: 'ease-out' }))
    })
  }
  function openParameters() {
    if (closing.current) return
    openingAnimations.current = []
    setEditing(true); drawer.current?.showModal()
    alignEditorControls()
    fadeCards('.settings-panel')
  }
  useLayoutEffect(() => {
    if (referenceOpen && drawer.current?.open) fadeCards('.journal-reference')
  }, [referenceOpen])
  async function closeParameters() {
    const dialog = drawer.current
    if (!dialog?.open || closing.current) return
    closing.current = true
    openingAnimations.current.forEach(animation => animation.cancel())
    const animations: Animation[] = []
    try {
      if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        dialog.classList.add('is-closing')
        const cards = dialog.querySelectorAll<HTMLElement>('.settings-panel, .journal-reference')
        cards.forEach(card => animations.push(card.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 140, easing: 'ease-out', fill: 'forwards' })))
        await Promise.allSettled(animations.map(animation => animation.finished))
      }
    } finally {
      dialog.close()
      animations.forEach(animation => animation.cancel())
      dialog.classList.remove('is-closing')
      closing.current = false
      setReferenceOpen(false); setEditing(false); editButton.current?.focus()
    }
  }
  const [run, setRun] = useState<CompletedRun | null>(null)
  const [dirty, setDirty] = useState(false)
  const [running, setRunning] = useState(false)
  const [historyWorking, setHistoryWorking] = useState(false)
  const [historyRevision, setHistoryRevision] = useState(0)
  const [formRevision, setFormRevision] = useState(0)
  const [formRequest, setFormRequest] = useState<CompletedRun['request']>()
  const [tab, setTab] = useState<'overview' | 'trades' | 'details'>('overview')
  const [workspaceTab, setWorkspaceTab] = useState<'portfolio' | 'strategies' | 'backtest' | 'saved' | 'journal'>('portfolio')
  const primaryMetrics = ['Total Return', 'Benchmark Return', 'Sharpe Ratio', 'Max Drawdown']
  function receive(completed: CompletedRun) { setRun(completed); setWorkspaceTab('backtest'); closeParameters(); setDirty(false); setHistoryRevision(n => n + 1) }
  function openSaved(saved: CompletedRun) { setRun(saved); setFormRequest(saved.request); setFormRevision(n => n + 1); setDirty(false); setWorkspaceTab('backtest') }
  return <div className="app-shell">
    <a href="#workspace-content" className="skip-link">Skip to content</a>
    <div className="workspace-tools">
      <WorkspaceLauncher selected={workspaceTab} onSelect={setWorkspaceTab} />
      <button ref={editButton} className="edit-parameters parameter-orb" aria-label="Edit parameters" data-tooltip="Edit parameters" aria-haspopup="dialog" aria-expanded={editing} onClick={openParameters}><PencilIcon /></button>
    </div>
    <main id="workspace-content" tabIndex={-1} className="workspace">
      <div className="dashboard-panel" hidden={workspaceTab !== 'portfolio'}><PortfolioDashboard active={workspaceTab === 'portfolio'} /></div>
      <div className="dashboard-panel" hidden={workspaceTab !== 'strategies'}><StrategyLibrary /></div>
      <div id="workspace-journal-panel" role="tabpanel" aria-labelledby="workspace-journal-tab" hidden={workspaceTab !== 'journal'}><Journal /></div>
      <div id="workspace-saved-panel" role="tabpanel" aria-labelledby="workspace-saved-tab" hidden={workspaceTab !== 'saved'}>
        {workspaceTab === 'saved' && <RunHistory key={`history-${historyRevision}`} revision={historyRevision} busy={running} activeId={run?.id} onWorking={setHistoryWorking} onOpen={openSaved} onDelete={id => { if (run?.id === id) setRun(null) }} />}
      </div>
      <div id="workspace-backtest-panel" role="tabpanel" aria-labelledby="workspace-backtest-tab" hidden={workspaceTab !== 'backtest'}>
      <div className="workspace-body">
        <div id="main-content" tabIndex={-1} className="results-panel" aria-label="Backtest results" aria-busy={running}>
          {!run ? workspaceTab === 'backtest' && <StartScreen running={running} onConfigure={openParameters} onSaved={() => setWorkspaceTab('saved')} onJournal={() => setWorkspaceTab('journal')} /> : <>
            <div className="run-heading"><div><span className="eyebrow">PYTHON ENGINE · SIMULATED RESULTS</span><h2>{run.request.symbol} <span> / {strategyNames[run.request.strategy.name]}</span></h2><p>{run.request.start} → {run.request.end} · {money(run.request.initial_cash)} capital · {run.request.cost_bps} bps</p></div><span className="complete-badge">Completed {new Date(run.completedAt).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</span></div>
            {(dirty || running) && <p className="notice" role="status">{running ? 'A new run is in progress. The results below belong to your last successful run.' : 'Settings changed. Run again to update the results below.'}</p>}
            {run.result.data_info && <div className="field-help"><p>{run.result.data_info.source === 'ibkr' ? 'Interactive Brokers' : 'Yahoo Finance'} · {run.result.data_info.price_basis} · {run.result.data_info.bar_count} daily bars · {run.result.data_info.first_date} → {run.result.data_info.last_date}</p>{run.result.data_info.warnings.map(warning => <p className="notice" key={warning}>{warning}</p>)}</div>}
            <dl className="metrics-grid">{primaryMetrics.map(name => <div className="metric-card" key={name}><dt>{name}</dt><dd>{metric(name, run.result.summary[name])}</dd><span>{name === 'Total Return' ? 'After strategy costs' : name === 'Benchmark Return' ? 'Buy-and-hold · before costs' : name === 'Sharpe Ratio' ? 'Risk-adjusted performance' : 'Largest peak-to-trough decline'}</span></div>)}</dl>
            <div className="tabs" role="tablist" aria-label="Backtest results">{(['overview', 'trades', 'details'] as const).map(t => <button id={`${t}-tab`} role="tab" aria-controls={`${t}-panel`} aria-selected={tab === t} tabIndex={tab === t ? 0 : -1} onKeyDown={event => {
              if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
                event.preventDefault()
                const order = ['overview', 'trades', 'details'] as const
                const next = event.key === 'Home' ? 'overview' : event.key === 'End' ? 'details' : order[(order.indexOf(t) + (event.key === 'ArrowRight' ? 1 : 2)) % 3]
                setTab(next)
                document.getElementById(`${next}-tab`)?.focus()
              }
            }} key={t} onClick={() => setTab(t)}>{t === 'overview' ? 'Performance overview' : t === 'details' ? 'Run details' : `Trade ledger (${run.result.trades.length})`}</button>)}</div>
            <div id="overview-panel" role="tabpanel" aria-labelledby="overview-tab" hidden={tab !== 'overview'}>
              {tab === 'overview' && <PerformanceChart key={run.completedAt} equity={run.result.equity} initialCash={run.request.initial_cash} />}

            </div>
            <div id="trades-panel" role="tabpanel" aria-labelledby="trades-tab" hidden={tab !== 'trades'}>{tab === 'trades' && <TradeTable key={run.completedAt} trades={run.result.trades} symbol={run.request.symbol} />}</div>
            <div id="details-panel" role="tabpanel" aria-labelledby="details-tab" hidden={tab !== 'details'}>              <section className="panel secondary-metrics"><h2>Performance details</h2><dl>{Object.entries(run.result.summary).filter(([name]) => !primaryMetrics.includes(name)).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{metric(name, value)}</dd></div>)}</dl></section><RunSettings request={run.request} /></div>
          </>}
        </div>
      </div></div><footer className="workspace-footer">Trading workspace <span>Snapshots & research · Stored locally · No order execution</span></footer>
    </main>
    <dialog ref={drawer} className={`parameter-drawer parameter-popover${referenceOpen ? ' with-journal' : ''}`} aria-label="Edit backtest parameters" onClose={() => setEditing(false)} onCancel={event => { event.preventDefault(); closeParameters() }} onClick={event => { const bounds = event.currentTarget.getBoundingClientRect(); if (event.target === event.currentTarget && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) closeParameters() }}>
      <div className="drawer-heading"><div className="editor-orbs"><button className="parameter-orb" aria-label="Quick journal" aria-expanded={referenceOpen} onClick={() => setReferenceOpen(value => !value)} title="Quick journal"><JournalIcon /></button><button className="parameter-orb close-orb" aria-pressed="true" onClick={closeParameters} aria-label="Close parameters" title="Close parameters"><PencilIcon /></button></div></div>
      <div className="editor-content">{referenceOpen && <JournalReference />}<div>
      <BacktestForm key={`form-${formRevision}`} disabled={historyWorking} initialRequest={formRequest} onResult={receive} onEdit={() => setDirty(true)} onRunning={setRunning} />
      </div></div>
    </dialog>
  </div>
}
