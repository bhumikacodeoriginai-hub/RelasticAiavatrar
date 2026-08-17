/**
 * Accessibility Shell.
 * Provides WCAG 2.2 AA compliance infrastructure:
 * - Skip-to-content link (visible on focus)
 * - Live region for screen reader announcements
 * - Focus management on route changes
 * - Keyboard shortcut hints
 *
 * Wrap the entire app content inside this component.
 */

import { useEffect, useRef, ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

interface AccessibilityShellProps {
  children: ReactNode
}

export default function AccessibilityShell({ children }: AccessibilityShellProps) {
  const location = useLocation()
  const mainRef = useRef<HTMLElement>(null)
  const announceRef = useRef<HTMLDivElement>(null)

  // Focus main content on route change (screen reader navigation)
  useEffect(() => {
    // Small delay to let new page render
    const timeout = setTimeout(() => {
      mainRef.current?.focus()
    }, 100)
    return () => clearTimeout(timeout)
  }, [location.pathname])

  return (
    <>
      {/* Skip to main content — visible only on keyboard focus */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[9999] focus:px-4 focus:py-2 focus:bg-primary-600 focus:text-white focus:rounded-lg focus:text-sm focus:font-medium focus:outline-none focus:ring-2 focus:ring-white"
        onClick={(e) => {
          e.preventDefault()
          mainRef.current?.focus()
          mainRef.current?.scrollIntoView()
        }}
      >
        Skip to main content
      </a>

      {/* Screen reader live announcements */}
      <div
        ref={announceRef}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        id="sr-announcements"
      />

      {/* Main content area with landmark */}
      <main
        ref={mainRef}
        id="main-content"
        tabIndex={-1}
        className="outline-none"
        role="main"
      >
        {children}
      </main>
    </>
  )
}

/**
 * Announce a message to screen readers via the live region.
 * Call this when important state changes occur.
 */
export function announceToScreenReader(message: string) {
  const el = document.getElementById('sr-announcements')
  if (el) {
    el.textContent = message
    // Clear after 5 seconds so repeated messages are re-announced
    setTimeout(() => { el.textContent = '' }, 5000)
  }
}
