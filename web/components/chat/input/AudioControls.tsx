'use client'

import React, { useRef, useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Mic, MicOff } from 'lucide-react'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { getApiBaseUrl } from '@/lib/api'

interface AudioControlsProps {
  onTranscript: (text: string) => void
  disabled?: boolean
}

export function AudioControls({ onTranscript, disabled }: AudioControlsProps) {
  const [isListening, setIsListening] = useState(false)
  const [isProcessingAudio, setIsProcessingAudio] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])

  // Define fallbackToWebSpeech first since it's used by startListening
  const fallbackToWebSpeech = useCallback(() => {
    if (typeof window !== 'undefined' && !('webkitSpeechRecognition' in window)) {
      toast.error('Web Speech API not supported')
      return
    }

    // @ts-ignore - webkitSpeechRecognition is not in TypeScript types
    const SpeechRecognitionClass = window.webkitSpeechRecognition as new () => any
    const recognition = new SpeechRecognitionClass()
    recognition.continuous = false
    recognition.interimResults = true
    recognition.lang = 'en-US'

    recognition.onstart = () => setIsListening(true)
    recognition.onend = () => setIsListening(false)
    recognition.onerror = (event: any) => {
      setIsListening(false)
      console.error('Speech error:', event.error)
    }
    recognition.onresult = (event: any) => {
      let finalTranscript = ''
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript
        }
      }
      if (finalTranscript) {
        onTranscript(finalTranscript)
      }
    }

    recognition.start()
  }, [onTranscript])

  const startListening = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        }
      })

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4'
      })

      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(track => track.stop())

        if (audioChunksRef.current.length === 0) {
          setIsListening(false)
          setIsProcessingAudio(false)
          return
        }

        setIsProcessingAudio(true)

        try {
          const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
          const reader = new FileReader()
          reader.onloadend = async () => {
            const base64Audio = (reader.result as string).split(',')[1]

            const response = await fetch(`${getApiBaseUrl()}/api/asr/recognize`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                audio_data: base64Audio,
                format: 'webm',
                sample_rate: 16000,
                language_hints: ['zh', 'en']
              })
            })

            const result = await response.json()

            if (result.success && result.text) {
              onTranscript(result.text)
              toast.success('Speech recognized')
            } else if (result.error) {
              if (response.status === 503) {
                toast.info('Using browser fallback')
                fallbackToWebSpeech()
              } else {
                toast.error(`ASR Error: ${result.error}`)
              }
            }
          }
          reader.readAsDataURL(audioBlob)
        } catch (error) {
          console.error('ASR error:', error)
          toast.error('Recognition failed')
        } finally {
          setIsProcessingAudio(false)
          setIsListening(false)
        }
      }

      mediaRecorder.start(100)
      setIsListening(true)
      toast.info('Listening... Click to stop')

    } catch (error) {
      console.error('Microphone error:', error)
      toast.error('Microphone access denied')
      setIsListening(false)
    }
  }, [onTranscript, fallbackToWebSpeech])

  const stopListening = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    setIsListening(false)
  }, [])

  const handleClick = useCallback(() => {
    if (isListening) {
      stopListening()
    } else {
      startListening()
    }
  }, [isListening, startListening, stopListening])

  return (
    <Button
      type="button"
      size="icon"
      variant="ghost"
      onClick={handleClick}
      disabled={disabled || isProcessingAudio}
      aria-label={isListening ? 'Stop recording' : 'Start voice input'}
      aria-pressed={isListening}
      className={cn(
        "h-8 w-8 rounded-full hover:bg-muted transition-all duration-300",
        isListening && "bg-red-500/10 text-red-500 animate-pulse hover:bg-red-500/20",
        isProcessingAudio && "bg-blue-500/10 text-blue-500"
      )}
    >
      {isProcessingAudio ? (
        <div className="h-4 w-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
      ) : isListening ? (
        <MicOff className="h-4 w-4" />
      ) : (
        <Mic className="h-4 w-4" />
      )}
    </Button>
  )
}
