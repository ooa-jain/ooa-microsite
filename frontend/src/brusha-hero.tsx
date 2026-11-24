import { createRoot } from 'react-dom/client'
import Brusha from '@/components/ui/brusha-illustration-studio-hero'
import type { BrushaProps } from '@/components/ui/brusha-illustration-studio-hero'

/**
 * Mounts the Brusha hero into #brusha-root with the JSON props in #brusha-props (built by Flask).
 * Used by the login page (with its own navbar and logo intro) and by Jain Hub (showNav: false).
 * When props carry `greet`, the headline greets the signed-in user for the time of day here.
 */
type PageProps = BrushaProps & { greet?: { name: string; fallback?: string } }

const mount = document.getElementById('brusha-root')
const data = document.getElementById('brusha-props')

if (mount && data) {
  const props = JSON.parse(data.textContent || '{}') as PageProps
  const capture = /[?&](capture|nointro)=1/.test(location.search)

  if (props.greet && props.copy) {
    const h = new Date().getHours()
    const part = h < 12 ? 'Good morning,' : h < 17 ? 'Good afternoon,' : 'Good evening,'
    // the headline is set very large: a long name would run off the screen, so it falls back to a short line
    const name = props.greet.name.trim()
    props.copy = { ...props.copy, headline: [part, name && name.length <= 11 ? name : props.greet.fallback || 'welcome back'] }
  }

  createRoot(mount).render(<Brusha {...props} reducedMotion={capture ? true : undefined} />)
}
