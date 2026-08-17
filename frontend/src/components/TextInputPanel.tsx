/**
 * Text Input Panel — Accessible alternative to speech.
 * Touch-friendly text input for visitors who:
 * - Cannot use speech recognition (browser unsupported)
 * - Prefer typing (noisy environment, hearing impaired)
 * - Need to enter invitation codes
 *
 * Accessibility:
 * - Large touch targets (44px minimum)
 * - High contrast text
 * - ARIA labels on all controls
 * - Keyboard navigable (Enter to submit)
 * - Auto-focus on mount
 */

import { useState, useRef, FormEvent, KeyboardEvent } from 'react'

interface TextInputPanelProps {
  onSubmit: (text: string) => void
  onInvitationCode?: (code: string) => void
  isDisabled?: boolean
  placeholder?: string
  sessionActive?: boolean
}

export default function TextInputPanel({
  onSubmit,
  onInvitationCode,
  isDisabled = false,
  placeholder = 'Type your message here...',
  sessionActive = false,
}: TextInputPanelProps) {
  const [text, setText] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [mode, setMode] = useState<'chat' | 'invite'>('chat')
  const inputRef = useRef<HTMLInputElement>(null)
  const inviteRef = useRef<HTMLInputElement>(null)

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim() && !isDisabled) {
      onSubmit(text.trim())
      setText('')
      inputRef.current?.focus()
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e as unknown as FormEvent)
    }
  }

  const handleInviteSubmit = (e: FormEvent) => {
    e.preventDefault()
    const code = inviteCode.trim().toUpperCase()
    if (code && onInvitationCode) {
      onInvitationCode(code)
      setInviteCode('')
    }
  }

  const formatInviteCode = (value: string) => {
    // Auto-format: remove non-alphanumeric, add dash after 4 chars
    const clean = value.replace(/[^A-Za-z0-9]/g, '').toUpperCase()
    if (clean.length > 4) {
      return `${clean.slice(0, 4)}-${clean.slice(4, 8)}`
    }
    return clean
  }

  return (
    <div className="glass-panel p-4" role="region" aria-label="Text input area">
      {/* Mode toggle */}
      <div className="flex gap-2 mb-3" role="tablist" aria-label="Input mode">
        <button
          role="tab"
          aria-selected={mode === 'chat'}
          onClick={() => setMode('chat')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all min-h-[44px] ${
            mode === 'chat'
              ? 'bg-primary-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          💬 Chat
        </button>
        {onInvitationCode && (
          <button
            role="tab"
            aria-selected={mode === 'invite'}
            onClick={() => setMode('invite')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all min-h-[44px] ${
              mode === 'invite'
                ? 'bg-primary-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            🎫 Invitation Code
          </button>
        )}
      </div>

      {/* Chat input */}
      {mode === 'chat' && (
        <form onSubmit={handleSubmit} className="flex gap-2" role="search" aria-label="Send message">
          <input
            ref={inputRef}
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isDisabled || !sessionActive}
            placeholder={sessionActive ? placeholder : 'Start a session to type...'}
            aria-label="Type your message"
            autoComplete="off"
            className="flex-1 px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-white placeholder-gray-500 text-base focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:opacity-50 min-h-[48px]"
          />
          <button
            type="submit"
            disabled={isDisabled || !text.trim() || !sessionActive}
            aria-label="Send message"
            className="px-5 py-3 rounded-xl bg-primary-600 hover:bg-primary-700 text-white font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed min-h-[48px] min-w-[48px]"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </form>
      )}

      {/* Invitation code input */}
      {mode === 'invite' && (
        <form onSubmit={handleInviteSubmit} className="flex gap-2" aria-label="Enter invitation code">
          <input
            ref={inviteRef}
            type="text"
            value={inviteCode}
            onChange={(e) => setInviteCode(formatInviteCode(e.target.value))}
            placeholder="XXXX-XXXX"
            maxLength={9}
            aria-label="Invitation code"
            autoComplete="off"
            autoFocus
            className="flex-1 px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-white placeholder-gray-500 text-center text-xl font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent min-h-[48px]"
          />
          <button
            type="submit"
            disabled={inviteCode.replace('-', '').length < 8}
            aria-label="Validate invitation code"
            className="px-5 py-3 rounded-xl bg-green-600 hover:bg-green-700 text-white font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed min-h-[48px]"
          >
            Check In
          </button>
        </form>
      )}

      {/* Helper text */}
      <p className="text-xs text-gray-500 mt-2 text-center" aria-live="polite">
        {mode === 'chat'
          ? 'Type your response or use the microphone above'
          : 'Enter the 8-character code from your invitation email'
        }
      </p>
    </div>
  )
}
