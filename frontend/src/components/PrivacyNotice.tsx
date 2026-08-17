/**
 * Privacy Notice & Media Controls.
 * Displays a visible disclosure that AI, camera, and microphone are active.
 * Provides controls to:
 * - Mute/unmute avatar speech (TTS output)
 * - Toggle live captions (show/hide text transcripts)
 * - See privacy mode indicator
 *
 * REGULATORY: This notice satisfies the requirement to inform visitors
 * that AI processing, camera capture, and audio recording are in use.
 * Must be visible at all times on the kiosk screen.
 */

import { useState } from 'react'

interface PrivacyNoticeProps {
  isCameraActive: boolean
  isMicActive: boolean
  isSpeaking: boolean
  onMuteToggle: (muted: boolean) => void
  onCaptionsToggle: (enabled: boolean) => void
  captionsEnabled: boolean
  isMuted: boolean
}

export default function PrivacyNotice({
  isCameraActive,
  isMicActive,
  isSpeaking,
  onMuteToggle,
  onCaptionsToggle,
  captionsEnabled,
  isMuted,
}: PrivacyNoticeProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className="fixed bottom-4 left-4 z-50 max-w-sm"
      role="complementary"
      aria-label="Privacy notice and media controls"
    >
      {/* Collapsed: Compact privacy indicator */}
      <div className="glass-panel p-3 rounded-xl shadow-lg">
        {/* Privacy badge row */}
        <div className="flex items-center justify-between gap-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-2 text-xs text-gray-300 hover:text-white transition-colors"
            aria-expanded={expanded}
            aria-controls="privacy-details"
          >
            {/* AI indicator */}
            <span className="flex items-center gap-1">
              <svg className="w-3.5 h-3.5 text-blue-400" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 11H9v-2h2v2zm0-4H9V5h2v4z" />
              </svg>
              <span>AI Active</span>
            </span>

            {/* Camera indicator */}
            {isCameraActive && (
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" aria-hidden="true" />
                <span>Cam</span>
              </span>
            )}

            {/* Mic indicator */}
            {isMicActive && (
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" aria-hidden="true" />
                <span>Mic</span>
              </span>
            )}
          </button>

          {/* Quick controls */}
          <div className="flex items-center gap-1">
            {/* Mute button */}
            <button
              onClick={() => onMuteToggle(!isMuted)}
              className={`p-1.5 rounded-lg transition-colors ${
                isMuted ? 'bg-red-600/30 text-red-400' : 'bg-gray-700/50 text-gray-400 hover:text-white'
              }`}
              aria-label={isMuted ? 'Unmute avatar speech' : 'Mute avatar speech'}
              aria-pressed={isMuted}
              title={isMuted ? 'Unmute' : 'Mute'}
            >
              {isMuted ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                </svg>
              )}
            </button>

            {/* Captions toggle */}
            <button
              onClick={() => onCaptionsToggle(!captionsEnabled)}
              className={`p-1.5 rounded-lg transition-colors ${
                captionsEnabled ? 'bg-primary-600/30 text-primary-400' : 'bg-gray-700/50 text-gray-400 hover:text-white'
              }`}
              aria-label={captionsEnabled ? 'Hide captions' : 'Show captions'}
              aria-pressed={captionsEnabled}
              title={captionsEnabled ? 'Hide captions' : 'Show captions'}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
              </svg>
            </button>
          </div>
        </div>

        {/* Expanded: Full privacy disclosure */}
        {expanded && (
          <div id="privacy-details" className="mt-3 pt-3 border-t border-gray-700/50">
            <p className="text-xs text-gray-400 leading-relaxed">
              <strong className="text-gray-300">Privacy Notice:</strong> This receptionist uses
              artificial intelligence to assist visitors. {isCameraActive && 'The camera is active for person detection. '}
              {isMicActive && 'The microphone captures speech for conversation. '}
              No biometric data is stored without your explicit consent.
              Audio is not recorded or stored.
            </p>
            <p className="text-xs text-gray-500 mt-2">
              You may type instead of speaking. Ask to speak with a human at any time.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
