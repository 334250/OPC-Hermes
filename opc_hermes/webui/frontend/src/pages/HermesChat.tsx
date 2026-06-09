import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type ModelDef } from '../lib/api'
import { useI18n } from '../lib/i18n'

interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  images?: string[]
}

function imageSrcFromBase64(value: string) {
  return value.startsWith('data:') ? value : `data:image/png;base64,${value}`
}

function normalizeAssistantContent(value: unknown): { text: string; images: string[] } {
  const images: string[] = []

  const walk = (item: unknown): string => {
    if (item == null) return ''
    if (typeof item === 'string') return item
    if (Array.isArray(item)) {
      return item.map(walk).filter(Boolean).join('\n')
    }
    if (typeof item !== 'object') return String(item)

    const obj = item as Record<string, any>
    if (typeof obj.b64_json === 'string') {
      images.push(imageSrcFromBase64(obj.b64_json))
      return ''
    }
    if (typeof obj.base64 === 'string') {
      images.push(imageSrcFromBase64(obj.base64))
      return ''
    }
    if (typeof obj.url === 'string') {
      images.push(obj.url)
      return ''
    }
    if (obj.image_url) {
      if (typeof obj.image_url === 'string') {
        images.push(obj.image_url)
      } else if (typeof obj.image_url?.url === 'string') {
        images.push(obj.image_url.url)
      }
      return ''
    }
    if (typeof obj.text === 'string') return obj.text
    if (typeof obj.content === 'string' || Array.isArray(obj.content)) return walk(obj.content)
    return ''
  }

  return { text: walk(value).trim(), images }
}

function extractAssistantMessage(data: any): { content: string; images: string[] } {
  const firstChoice = data?.choices?.[0]
  const message = firstChoice?.message ?? firstChoice?.delta ?? data?.message
  const fromMessage = normalizeAssistantContent(message?.content)
  const fromOutput = normalizeAssistantContent(data?.output ?? data?.data)
  const directText = typeof data?.output_text === 'string' ? data.output_text : typeof data?.text === 'string' ? data.text : ''
  const content = [fromMessage.text, directText, fromOutput.text].filter(Boolean).join('\n\n').trim()
  return {
    content,
    images: [...fromMessage.images, ...fromOutput.images],
  }
}

export default function HermesChat() {
  const { t, lang } = useI18n()
  const [models, setModels] = useState<ModelDef[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamContent, setStreamContent] = useState('')
  const [error, setError] = useState('')
  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Load configured models
  useEffect(() => {
    api.listModels().then(res => {
      const configured = (res.models ?? []).filter(m => m.api_base && m.api_base.trim())
      setModels(configured)
      if (configured.length > 0 && !selectedModel) {
        setSelectedModel(configured[0].id)
      }
    }).catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamContent])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || streaming || !selectedModel) return
    const selectedModelDef = models.find(m => m.id === selectedModel)
    const useStream = !selectedModelDef?.capabilities?.image_gen

    const userMsg: ChatMessage = { role: 'user', content: text }
    const updatedMessages = [...messages, userMsg]
    setMessages(updatedMessages)
    setInput('')
    setStreaming(true)
    setStreamContent('')
    setError('')

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const payload = {
        model: selectedModel,
        messages: updatedMessages.map(m => ({ role: m.role, content: m.content })),
        stream: useStream,
      }

      const res = await fetch('/api/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      })

      if (!res.ok) {
        const errBody = await res.text()
        let errMsg = `HTTP ${res.status}`
        try {
          const errJson = JSON.parse(errBody)
          errMsg = errJson.error?.message || errJson.detail || errMsg
        } catch {}
        throw new Error(errMsg)
      }

      const contentType = res.headers.get('content-type') || ''
      if (contentType.toLowerCase().startsWith('text/event-stream')) {
        const reader = res.body?.getReader()
        if (!reader) throw new Error('No response body')

        const decoder = new TextDecoder()
        let buffer = ''
        let fullContent = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed || !trimmed.startsWith('data:')) continue
            const data = trimmed.slice(5).trim()
            if (data === '[DONE]') continue

            try {
              const parsed = JSON.parse(data)
              const delta = parsed.choices?.[0]?.delta?.content
              const normalized = normalizeAssistantContent(delta)
              if (normalized.text) {
                fullContent += normalized.text
                setStreamContent(fullContent)
              }
            } catch {
              // skip unparseable chunks
            }
          }
        }

        setMessages(prev => [...prev, { role: 'assistant', content: fullContent || '(empty response)' }])
      } else {
        const data = await res.json()
        const parsed = extractAssistantMessage(data)
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: parsed.content || (parsed.images.length ? '' : '(empty response)'),
          images: parsed.images,
        }])
      }
    } catch (e: any) {
      if (e.name === 'AbortError') return
      setError(e.message || 'Request failed')
    } finally {
      setStreaming(false)
      setStreamContent('')
      abortRef.current = null
    }
  }, [input, streaming, selectedModel, messages, models])

  const handleStop = () => {
    abortRef.current?.abort()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const currentModelName = models.find(m => m.id === selectedModel)?.display_name || selectedModel

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col">
      {/* Header */}
      <div className="mb-3 flex items-center gap-3">
        <h2 className="text-xl font-semibold shrink-0">{lang === 'zh' ? 'Chat' : 'Chat'}</h2>
        <select
          className="input w-56 text-xs"
          value={selectedModel}
          onChange={e => setSelectedModel(e.target.value)}
        >
          {models.length === 0 && <option value="">{lang === 'zh' ? '暂无已配置模型' : 'No models configured'}</option>}
          {models.map(m => (
            <option key={m.id} value={m.id}>{m.display_name || m.id}</option>
          ))}
        </select>
        {streaming && (
          <button className="btn-secondary text-xs" onClick={handleStop}>
            {lang === 'zh' ? '停止' : 'Stop'}
          </button>
        )}
        {error && <span className="text-xs text-red-400 truncate">{error}</span>}
      </div>

      {/* Messages */}
      <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-opc-border bg-opc-surface p-4">
        {messages.length === 0 && !streaming ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <div className="text-4xl mb-4 opacity-30">💬</div>
              <p className="text-sm text-opc-text-2">
                {lang === 'zh'
                  ? `向 ${currentModelName || 'AI'} 发送消息开始对话`
                  : `Send a message to ${currentModelName || 'AI'} to start`}
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-opc-accent text-white'
                      : 'bg-opc-surface-2 text-opc-text'
                  }`}
                >
                  {msg.content && <div className="whitespace-pre-wrap break-words">{msg.content}</div>}
                  {msg.images?.length ? (
                    <div className="mt-3 grid grid-cols-1 gap-2">
                      {msg.images.map((src, imageIndex) => (
                        <a key={`${src}-${imageIndex}`} href={src} target="_blank" rel="noreferrer">
                          <img className="max-h-[420px] rounded-lg border border-opc-border object-contain" src={src} alt={lang === 'zh' ? '生成图片' : 'Generated image'} />
                        </a>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}

            {/* Streaming bubble */}
            {streaming && (
              <div className="flex justify-start">
                <div className="max-w-[80%] rounded-xl bg-opc-surface-2 px-4 py-3 text-sm leading-relaxed text-opc-text">
                  <div className="whitespace-pre-wrap break-words">
                    {streamContent || (
                      <span className="inline-flex items-center gap-1 text-opc-text-2">
                        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-opc-accent" />
                        {lang === 'zh' ? '思考中...' : 'Thinking...'}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="mt-3 flex gap-2">
        <input
          ref={inputRef}
          className="input flex-1"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={lang === 'zh' ? '输入消息，Enter 发送...' : 'Type a message, Enter to send...'}
          disabled={streaming || models.length === 0}
        />
        <button
          className="btn-primary text-sm px-6"
          onClick={handleSend}
          disabled={!input.trim() || streaming || !selectedModel}
        >
          {streaming
            ? '...'
            : lang === 'zh' ? '发送' : 'Send'}
        </button>
      </div>
    </div>
  )
}
