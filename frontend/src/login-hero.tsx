import { createRoot } from 'react-dom/client'
import Brusha from '@/components/ui/brusha-illustration-studio-hero'
import type { BrushaProps } from '@/components/ui/brusha-illustration-studio-hero'

// The page passes its links and copy as JSON (Flask builds the URLs with url_for)
const mount = document.getElementById('brusha-root')
const data = document.getElementById('brusha-props')

if (mount && data) {
  const props = JSON.parse(data.textContent || '{}') as BrushaProps
  const capture = /[?&](capture|nointro)=1/.test(location.search)

  createRoot(mount).render(<Brusha {...props} reducedMotion={capture ? true : undefined} />)
}
