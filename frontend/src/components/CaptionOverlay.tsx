/**
 * CaptionOverlay — Real-time captions for the avatar's speech.
 *
 * WCAG 2.2 AA compliance:
 * - Captions are visible and legible at all zoom levels
 * - High-contrast text (4.5:1 ratio minimum)
 * - Respects user font size preferences
 * - Can be toggled on/off
 * - Live region for screen reader compatibility
 * - Position doesn't obstruct primary UI
 * - Background has sufficient opacity for readability
 */

import { useState, useEffect, useRef } from 'react'

interface CaptionOverlayProps {
  /** Current text being spoken by the avatar */
  currentText: string | null
  /** Whether captions are enabled */
  enabled: boolean
  /** Toggle captions on/off */
  onToggle: (enabled: boolean) => void
  /** Additional classes for positioning */
  className?: string
  /** High contrast mode */
  highContrast?: boolean
  /** Font size override: 'small' | 'medium' | 'large' */
  fontSize?: 'small' | 'medium' | 'large'
}

const FONT_SIZES = {
  small: 'text-sm',
  medium: 'text-base',
  large: 'text-lg',
}

export default function CaptionOverlay({
  currentText,
  enabled,
  onToggle,
  className = '',
  highContrast = false,
  fontSize = 'medium',
}: CaptionOverlayProps) {
  const [displayText, setDisplayText] = useState<string>('')
  const [isVisible, setIsVisible] = useState(false)
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Update displayed caption text
  useEffect(() => {
    if (!enabled) {
      setIsVisible(false)
      return
    }

    if (currentText && currentText.trim()) {
      setDisplayText(currentText)
      setIsVisible(true)

      // Auto-hide after text finishes (estimate based on word count)
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
      const wordCount = currentText.split(' ').length
      const displayDuration = Math.max(3000, wordCount * 400) // ~400ms per word, min 3s
      hideTimerRef.current = setTimeout(() => {
        setIsVisible(false)
      }, displayDuration)
    } else {
      // Fade out after a short delay
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
      hideTimerRef.current = setTimeout(() => {
        setIsVisible(false)
      }, 1500)
    }

    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
    }
  }, [currentText, enabled])

  const bgClass = highContrast
    ? 'bg-black/95 border-white/50'
    : 'bg-gray-900/85 border-white/20'

  const textClass = highContrast
    ? 'text-white font-bold'
    : 'text-white font-medium'

  if (!enabled) return null

  return (
    <div
      className={`absolute z-40 pointer-events-none transition-opacity duration-300 ${
        isVisible ? 'opacity-100' : 'opacity-0'
      } ${className}`}
      aria-live="polite"
      aria-atomic="true"
      role="region"
      aria-label="Live captions"
    >
      {displayText && (
        <div
          className={`mx-auto max-w-lg px-5 py-3 rounded-xl backdrop-blur-md border shadow-2xl ${bgClass}`}
        >
          <p className={`${textClass} ${FONT_SIZES[fontSize]} leading-relaxed text-center`}>
            {displayText}
          </p>
        </div>
      )}

      {/* Caption toggle button (pointer-events enabled) */}
      <div className="flex justify-center mt-2 pointer-events-auto">
        <button
          onClick={() => onToggle(!enabled)}
          className="px-3 py-1 rounded-full bg-white/10 hover:bg-white/20 border border-white/20 text-white/70 text-xs font-medium transition-all"
          aria-label={enabled ? 'Disable captions' : 'Enable captions'}
          title="Toggle captions (CC)"
        >
          CC {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
    </div>
  )
}

/**
 * CaptionSettings — Accessible settings panel for caption preferences.
 */
export function CaptionSettings({
  fontSize,
  onFontSizeChange,
  highContrast,
  onHighContrastChange,
}: {
  fontSize: 'small' | 'medium' | 'large'
  onFontSizeChange: (size: 'small' | 'medium' | 'large') => void
  highContrast: boolean
  onHighContrastChange: (hc: boolean) => void
}) {
  return (
    <div className="p-4 bg-gray-800 rounded-xl border border-white/10" role="group" aria-label="Caption settings">
      <h4 className="text-white font-medium text-sm mb-3">Caption Settings</h4>

      {/* Font size */}
      <div className="mb-3">
        <label className="text-white/70 text-xs block mb-1">Text Size</label>
        <div className="flex gap-2">
          {(['small', 'medium', 'large'] as const).map((size) => (
            <button
              key={size}
              onClick={() => onFontSizeChange(size)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                fontSize === size
                  ? 'bg-blue-600 text-white'
                  : 'bg-white/10 text-white/60 hover:bg-white/20'
              }`}
              aria-pressed={fontSize === size}
            >
              {size.charAt(0).toUpperCase() + size.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* High contrast */}
      <div className="flex items-center justify-between">
        <label htmlFor="caption-contrast" className="text-white/70 text-xs">
          High Contrast
        </label>
        <button
          id="caption-contrast"
          role="switch"
          aria-checked={highContrast}
          onClick={() => onHighContrastChange(!highContrast)}
          className={`relative w-10 h-5 rounded-full transition-colors ${
            highContrast ? 'bg-blue-600' : 'bg-gray-600'
          }`}
        >
          <span
            className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
              highContrast ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      </div>
    </div>
  )
}
