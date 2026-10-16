import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import ChromeLogo from './ChromeLogo'

const destinations = [
  ['portfolio', 'Portfolio'], ['strategies', 'Strategies'], ['backtest', 'Research'],
  ['saved', 'Saved experiments'], ['journal', 'Journal'],
] as const
type Destination = typeof destinations[number][0]

export default function WorkspaceLauncher({ selected, onSelect }: { selected: Destination; onSelect: (value: Destination) => void }) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])
  function focusOption(index: number) {
    root.current?.querySelectorAll<HTMLButtonElement>('nav button')[index]?.focus()
  }
  return <div ref={root} className={`workspace-launcher${open ? ' is-open' : ''}`} onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
  }} onKeyDown={event => {
    if (event.key === 'Escape') { setOpen(false); trigger.current?.focus() }
  }}>
    <button ref={trigger} className="logo-orb" aria-label="Workspace navigation" aria-expanded={open} aria-controls="workspace-navigation" onClick={() => setOpen(value => !value)} onKeyDown={event => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
        event.preventDefault(); setOpen(true); requestAnimationFrame(() => focusOption(0))
      }
    }}><ChromeLogo /><span className="launcher-indicator" aria-hidden="true" /></button>
    <nav id="workspace-navigation" className="orb-destinations" aria-label="Workspace" inert={!open} onKeyDown={event => {
      const buttons = [...event.currentTarget.querySelectorAll('button')]
      const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
      if (['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault()
        focusOption(event.key === 'Home' ? 0 : event.key === 'End' ? 4 : (index + (['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : 4)) % 5)
      }
    }}>
      {destinations.map(([name, label], index) => <button key={name} id={`workspace-${name}-tab`} style={{ '--item': index } as CSSProperties} aria-current={selected === name ? 'page' : undefined} onClick={() => {
        onSelect(name); setOpen(false); trigger.current?.focus()
      }}><span className="destination-dot" aria-hidden="true" />{label}</button>)}
    </nav>
  </div>
}
