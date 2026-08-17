import { useState, useRef, useCallback, useEffect } from 'react'

interface UseSpeechRecognitionOptions {
  language?: string
  continuous?: boolean
  interimResults?: boolean
  onResult?: (transcript: string, isFinal: boolean) => void
  onError?: (error: string) => void
}

export function useSpeechRecognition(options: UseSpeechRecognitionOptions = {}) {
  const [isListening, setIsListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [interimTranscript, setInterimTranscript] = useState('')
  const [isSupported, setIsSupported] = useState(false)
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const isListeningRef = useRef(false)
  const onResultRef = useRef(options.onResult)
  const onErrorRef = useRef(options.onError)

  const {
    language = 'en-IN',
    continuous = true,
    interimResults = true,
  } = options

  // Keep callback refs current without re-creating recognition
  useEffect(() => {
    onResultRef.current = options.onResult
  }, [options.onResult])

  useEffect(() => {
    onErrorRef.current = options.onError
  }, [options.onError])

  // Sync ref with state
  useEffect(() => {
    isListeningRef.current = isListening
  }, [isListening])

  // Initialize recognition once
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    setIsSupported(!!SpeechRecognition)

    if (!SpeechRecognition) return

    const recognition = new SpeechRecognition()
    recognition.lang = language
    recognition.continuous = continuous
    recognition.interimResults = interimResults
    recognition.maxAlternatives = 1

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = ''
      let final = ''

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) {
          final += result[0].transcript
          setTranscript(prev => prev + ' ' + final)
          onResultRef.current?.(final.trim(), true)
        } else {
          interim += result[0].transcript
        }
      }
      setInterimTranscript(interim)
    }

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      console.error('Speech recognition error:', event.error)
      onErrorRef.current?.(event.error)

      // Don't stop for transient errors
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        setIsListening(false)
      }
    }

    recognition.onend = () => {
      // Auto-restart if still supposed to be listening (continuous mode)
      if (isListeningRef.current && continuous) {
        try {
          recognition.start()
        } catch {
          // Might fail if already started — ignore
        }
      } else {
        setIsListening(false)
      }
    }

    recognitionRef.current = recognition

    return () => {
      try {
        recognition.stop()
      } catch {
        // Ignore errors on cleanup
      }
    }
  }, [language, continuous, interimResults])

  const startListening = useCallback(() => {
    if (recognitionRef.current && !isListeningRef.current) {
      setTranscript('')
      setInterimTranscript('')
      try {
        recognitionRef.current.start()
        setIsListening(true)
      } catch (error) {
        console.error('Failed to start recognition:', error)
      }
    }
  }, [])

  const stopListening = useCallback(() => {
    if (recognitionRef.current && isListeningRef.current) {
      try {
        recognitionRef.current.stop()
      } catch {
        // Ignore
      }
      setIsListening(false)
    }
  }, [])

  const resetTranscript = useCallback(() => {
    setTranscript('')
    setInterimTranscript('')
  }, [])

  return {
    isListening,
    transcript,
    interimTranscript,
    isSupported,
    startListening,
    stopListening,
    resetTranscript,
  }
}

// Type declarations for Web Speech API
declare global {
  interface Window {
    SpeechRecognition: typeof SpeechRecognition
    webkitSpeechRecognition: typeof SpeechRecognition
  }
}
