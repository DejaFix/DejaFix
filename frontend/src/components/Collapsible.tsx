import { useState, type ReactNode } from 'react'
import { Icon } from './Icon'

interface Props {
  title: string
  count?: number
  meta?: string
  defaultOpen?: boolean
  id?: string
  children: ReactNode
}

export function Collapsible({ title, count, meta, defaultOpen = false, id, children }: Props) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={`collapsible ${open ? 'open' : ''}`} id={id}>
      <button className="collapsible-head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className="chev">
          <Icon name="chevron" size={16} />
        </span>
        <span className="collapsible-title">{title}</span>
        {count !== undefined && <span className="collapsible-title">{count}건</span>}
        {meta && <span className="collapsible-meta">{meta}</span>}
      </button>
      {open && <div>{children}</div>}
    </div>
  )
}
