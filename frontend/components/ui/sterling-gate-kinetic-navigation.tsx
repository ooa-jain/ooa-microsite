/**
 * Sterling Gate kinetic navigation: a full-screen menu whose backdrop panels slide in,
 * links rise into place and abstract shapes bloom behind the hovered link (GSAP + CustomEase).
 *
 * Adapted for the JAIN Office of Academics portal:
 *  - links, a footer row and the brand come from props (the original had placeholder links)
 *  - `showTrigger: false` hides the component's own "Menu" button: the page's header burger
 *    opens it through `open` / `onOpenChange` (see src/kinetic-nav.tsx)
 *  - focus moves into the menu on open and back on close; Escape and the overlay close it
 * Styles: src/kinetic-nav.css (the original shipped without its stylesheet).
 */
import React, { useEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { CustomEase } from 'gsap/CustomEase'

if (typeof window !== 'undefined') {
  gsap.registerPlugin(CustomEase)
}

export interface KineticLink {
  label: string
  href: string
  /** small line under the label */
  note?: string
  /** open in a new tab */
  external?: boolean
}

export interface KineticNavProps {
  links?: KineticLink[]
  /** secondary links shown at the foot of the menu (e.g. platforms, sign out) */
  footer?: KineticLink[]
  /** text in the menu's top-left corner */
  brand?: string
  showTrigger?: boolean
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

const DEFAULT_LINKS: KineticLink[] = [
  { label: 'About us', href: '#' },
  { label: 'Our work', href: '#' },
  { label: 'Services', href: '#' },
  { label: 'Blog', href: '#' },
  { label: 'Contact us', href: '#' }
]

export function Component({ links = DEFAULT_LINKS, footer = [], brand = '', showTrigger = true, open, onOpenChange }: KineticNavProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [innerOpen, setInnerOpen] = useState(false)
  const isMenuOpen = open ?? innerOpen
  const setIsMenuOpen = (v: boolean | ((p: boolean) => boolean)) => {
    const next = typeof v === 'function' ? v(isMenuOpen) : v
    if (open === undefined) setInnerOpen(next)
    onOpenChange?.(next)
  }
  const lastFocus = useRef<Element | null>(null)
  const firstRender = useRef(true)

  // Initial setup & hover shapes
  useEffect(() => {
    if (!containerRef.current) return

    try {
      if (!gsap.parseEase('main')) {
        CustomEase.create('main', '0.65, 0.01, 0.05, 0.99')
        gsap.defaults({ ease: 'main', duration: 0.7 })
      }
    } catch (e) {
      gsap.defaults({ ease: 'power2.out', duration: 0.7 })
    }

    const ctx = gsap.context(() => {
      const menuItems = containerRef.current!.querySelectorAll('.menu-list-item[data-shape]')
      const shapesContainer = containerRef.current!.querySelector('.ambient-background-shapes')

      menuItems.forEach(item => {
        const shapeIndex = item.getAttribute('data-shape')
        const shape = shapesContainer ? shapesContainer.querySelector(`.bg-shape-${shapeIndex}`) : null
        if (!shape) return
        const shapeEls = shape.querySelectorAll('.shape-element')

        const onEnter = () => {
          shapesContainer?.querySelectorAll('.bg-shape').forEach(s => s.classList.remove('active'))
          shape.classList.add('active')
          gsap.fromTo(shapeEls, { scale: 0.5, opacity: 0, rotation: -10 },
            { scale: 1, opacity: 1, rotation: 0, duration: 0.6, stagger: 0.08, ease: 'back.out(1.7)', overwrite: 'auto' })
        }
        const onLeave = () => {
          gsap.to(shapeEls, { scale: 0.8, opacity: 0, duration: 0.3, ease: 'power2.in',
            onComplete: () => shape.classList.remove('active'), overwrite: 'auto' })
        }
        item.addEventListener('mouseenter', onEnter)
        item.addEventListener('mouseleave', onLeave)
        item.addEventListener('focusin', onEnter)
        item.addEventListener('focusout', onLeave)
        ;(item as any)._cleanup = () => {
          item.removeEventListener('mouseenter', onEnter)
          item.removeEventListener('mouseleave', onLeave)
          item.removeEventListener('focusin', onEnter)
          item.removeEventListener('focusout', onLeave)
        }
      })
    }, containerRef)

    return () => {
      ctx.revert()
      containerRef.current?.querySelectorAll('.menu-list-item[data-shape]').forEach((item: any) => item._cleanup && item._cleanup())
    }
  }, [links.length])

  // Open / close animation
  useEffect(() => {
    if (!containerRef.current) return
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

    const ctx = gsap.context(() => {
      const root = containerRef.current!
      const navWrap = root.querySelector('.nav-overlay-wrapper')
      const menu = root.querySelector('.menu-content')
      const overlay = root.querySelector('.overlay')
      const bgPanels = root.querySelectorAll('.backdrop-layer')
      const menuLinks = root.querySelectorAll('.nav-link')
      const fadeTargets = root.querySelectorAll('[data-menu-fade]')
      const menuButton = root.querySelector('.nav-close-btn')
      const menuButtonTexts = menuButton?.querySelectorAll('p')
      const menuButtonIcon = menuButton?.querySelector('.menu-button-icon')
      const tl = gsap.timeline()
      if (reduce) tl.timeScale(20)

      if (isMenuOpen) {
        navWrap?.setAttribute('data-nav', 'open')
        tl.set(navWrap, { display: 'block' })
          .set(menu, { xPercent: 0 }, '<')
        if (menuButtonTexts?.length) tl.fromTo(menuButtonTexts, { yPercent: 0 }, { yPercent: -100, stagger: 0.2 })
        if (menuButtonIcon) tl.fromTo(menuButtonIcon, { rotate: 0 }, { rotate: 315 }, '<')
        tl.fromTo(overlay, { autoAlpha: 0 }, { autoAlpha: 1 }, '<')
          .fromTo(bgPanels, { xPercent: 101 }, { xPercent: 0, stagger: 0.12, duration: 0.575 }, '<')
          .fromTo(menuLinks, { yPercent: 140, rotate: 10 }, { yPercent: 0, rotate: 0, stagger: 0.05 }, '<+=0.35')
        if (fadeTargets.length) {
          tl.fromTo(fadeTargets, { autoAlpha: 0, yPercent: 50 }, { autoAlpha: 1, yPercent: 0, stagger: 0.04, clearProps: 'all' }, '<+=0.2')
        }
        lastFocus.current = document.activeElement
        tl.call(() => (root.querySelector('.menu-close-x') as HTMLElement | null)?.focus({ preventScroll: true }))
        document.documentElement.classList.add('kn-lock')
      } else {
        navWrap?.setAttribute('data-nav', 'closed')
        if (firstRender.current) {
          gsap.set(navWrap, { display: 'none' })
        } else {
          tl.to(overlay, { autoAlpha: 0 })
            .to(menu, { xPercent: 120 }, '<')
          if (menuButtonTexts?.length) tl.to(menuButtonTexts, { yPercent: 0 }, '<')
          if (menuButtonIcon) tl.to(menuButtonIcon, { rotate: 0 }, '<')
          tl.set(navWrap, { display: 'none' })
          ;(lastFocus.current as HTMLElement | null)?.focus?.({ preventScroll: true })
        }
        document.documentElement.classList.remove('kn-lock')
      }
      firstRender.current = false
    }, containerRef)

    return () => ctx.revert()
  }, [isMenuOpen])

  // Escape closes
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isMenuOpen) setIsMenuOpen(false)
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [isMenuOpen])

  const toggleMenu = () => setIsMenuOpen(prev => !prev)
  const closeMenu = () => setIsMenuOpen(false)

  return (
    <div ref={containerRef} className='kinetic-nav'>
      {showTrigger && (
        <div className='site-header-wrapper'>
          <header className='header'>
            <div className='container is--full'>
              <nav className='nav-row'>
                <a href='#' aria-label='home' className='nav-logo-row w-inline-block'></a>
                <div className='nav-row__right'>
                  <button type='button' className='nav-close-btn' onClick={toggleMenu} aria-expanded={isMenuOpen} aria-controls='kinetic-menu'>
                    <div className='menu-button-text'>
                      <p className='p-large'>Menu</p>
                      <p className='p-large'>Close</p>
                    </div>
                    <div className='icon-wrap'>
                      <svg xmlns='http://www.w3.org/2000/svg' width='100%' viewBox='0 0 16 16' fill='none' className='menu-button-icon'>
                        <path d='M7.33333 16L7.33333 -3.2055e-07L8.66667 -3.78832e-07L8.66667 16L7.33333 16Z' fill='currentColor'></path>
                        <path d='M16 8.66667L-2.62269e-07 8.66667L-3.78832e-07 7.33333L16 7.33333L16 8.66667Z' fill='currentColor'></path>
                      </svg>
                    </div>
                  </button>
                </div>
              </nav>
            </div>
          </header>
        </div>
      )}

      <section className='fullscreen-menu-container'>
        <div data-nav='closed' className='nav-overlay-wrapper' id='kinetic-menu' role='dialog' aria-modal='true' aria-label='Menu'>
          <div className='overlay' onClick={closeMenu}></div>
          <nav className='menu-content'>
            <div className='menu-bg'>
              <div className='backdrop-layer first'></div>
              <div className='backdrop-layer second'></div>
              <div className='backdrop-layer'></div>

              <div className='ambient-background-shapes'>
                <svg className='bg-shape bg-shape-1' viewBox='0 0 400 400' fill='none'>
                  <circle className='shape-element' cx='80' cy='120' r='40' fill='rgba(99,102,241,0.15)' />
                  <circle className='shape-element' cx='300' cy='80' r='60' fill='rgba(139,92,246,0.12)' />
                  <circle className='shape-element' cx='200' cy='300' r='80' fill='rgba(236,72,153,0.1)' />
                  <circle className='shape-element' cx='350' cy='280' r='30' fill='rgba(99,102,241,0.15)' />
                </svg>
                <svg className='bg-shape bg-shape-2' viewBox='0 0 400 400' fill='none'>
                  <path className='shape-element' d='M0 200 Q100 100, 200 200 T 400 200' stroke='rgba(99,102,241,0.2)' strokeWidth='60' fill='none' />
                  <path className='shape-element' d='M0 280 Q100 180, 200 280 T 400 280' stroke='rgba(139,92,246,0.15)' strokeWidth='40' fill='none' />
                </svg>
                <svg className='bg-shape bg-shape-3' viewBox='0 0 400 400' fill='none'>
                  {[[50, 50, 8], [150, 50, 8], [250, 50, 8], [350, 50, 8], [100, 150, 12], [200, 150, 12], [300, 150, 12],
                    [50, 250, 10], [150, 250, 10], [250, 250, 10], [350, 250, 10], [100, 350, 6], [200, 350, 6], [300, 350, 6]].map(([cx, cy, r], i) => (
                    <circle key={i} className='shape-element' cx={cx} cy={cy} r={r}
                      fill={['rgba(99,102,241,0.3)', 'rgba(139,92,246,0.3)', 'rgba(236,72,153,0.3)'][i % 3]} />
                  ))}
                </svg>
                <svg className='bg-shape bg-shape-4' viewBox='0 0 400 400' fill='none'>
                  <path className='shape-element' d='M100 100 Q150 50, 200 100 Q250 150, 200 200 Q150 250, 100 200 Q50 150, 100 100' fill='rgba(99,102,241,0.12)' />
                  <path className='shape-element' d='M250 200 Q300 150, 350 200 Q400 250, 350 300 Q300 350, 250 300 Q200 250, 250 200' fill='rgba(236,72,153,0.1)' />
                </svg>
                <svg className='bg-shape bg-shape-5' viewBox='0 0 400 400' fill='none'>
                  <line className='shape-element' x1='0' y1='100' x2='300' y2='400' stroke='rgba(99,102,241,0.15)' strokeWidth='30' />
                  <line className='shape-element' x1='100' y1='0' x2='400' y2='300' stroke='rgba(139,92,246,0.12)' strokeWidth='25' />
                  <line className='shape-element' x1='200' y1='0' x2='400' y2='200' stroke='rgba(236,72,153,0.1)' strokeWidth='20' />
                </svg>
              </div>
            </div>

            <div className='menu-content-wrapper'>
              <div className='menu-top'>
                <span className='menu-brand'>{brand}</span>
                <button type='button' className='menu-close-x' onClick={closeMenu} aria-label='Close menu'>
                  <span>Close</span>
                  <svg viewBox='0 0 16 16' width='16' height='16' fill='none' aria-hidden='true'>
                    <path d='M3 3 13 13M13 3 3 13' stroke='currentColor' strokeWidth='1.6' strokeLinecap='round' />
                  </svg>
                </button>
              </div>
              <ul className='menu-list'>
                {links.map((l, i) => (
                  <li key={l.href + l.label} className='menu-list-item' data-shape={(i % 5) + 1}>
                    <a href={l.href} className='nav-link w-inline-block' onClick={closeMenu}
                      {...(l.external ? { target: '_blank', rel: 'noopener' } : {})}>
                      <p className='nav-link-text'>{l.label}</p>
                      {l.note && <span className='nav-link-note' data-menu-fade>{l.note}</span>}
                      <div className='nav-link-hover-bg'></div>
                    </a>
                  </li>
                ))}
              </ul>
              {footer.length > 0 && (
                <ul className='menu-footer' data-menu-fade>
                  {footer.map(f => (
                    <li key={f.href + f.label}>
                      <a href={f.href} {...(f.external ? { target: '_blank', rel: 'noopener' } : {})}>{f.label}</a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </nav>
        </div>
      </section>
    </div>
  )
}

export default Component
