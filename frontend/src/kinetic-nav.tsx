import { createRoot } from 'react-dom/client'
import { useEffect, useState } from 'react'
import { Component as KineticNav } from '@/components/ui/sterling-gate-kinetic-navigation'
import type { KineticNavProps } from '@/components/ui/sterling-gate-kinetic-navigation'
import './kinetic-nav.css'

/**
 * The portal's phone / tablet menu. The shared header's burger (.pb-burger) opens it below 980px;
 * links come from #kinetic-props (JSON built by Flask from the same navigation as the header).
 */
const BREAK = 980

function App(props: KineticNavProps) {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    // capture phase: runs before the header's own onclick, which opens the old drop-down
    const onClick = (e: MouseEvent) => {
      const burger = (e.target as Element)?.closest?.('.pb-burger')
      if (!burger || window.innerWidth > BREAK) return
      e.preventDefault()
      e.stopPropagation()
      setOpen(o => !o)
    }
    const onResize = () => { if (window.innerWidth > BREAK) setOpen(false) }
    document.addEventListener('click', onClick, true)
    window.addEventListener('resize', onResize)
    ;(window as any).kineticNav = { open: () => setOpen(true), close: () => setOpen(false) }
    return () => {
      document.removeEventListener('click', onClick, true)
      window.removeEventListener('resize', onResize)
    }
  }, [])

  useEffect(() => {
    document.querySelectorAll('.pb-burger').forEach(b => b.setAttribute('aria-expanded', String(open)))
  }, [open])

  return <KineticNav {...props} showTrigger={false} open={open} onOpenChange={setOpen} />
}

const mount = document.getElementById('kinetic-root')
const data = document.getElementById('kinetic-props')
if (mount && data) {
  createRoot(mount).render(<App {...(JSON.parse(data.textContent || '{}') as KineticNavProps)} />)
}
