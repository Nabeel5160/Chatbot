import { Canvas, useFrame } from '@react-three/fiber'
import { Float, OrbitControls, Sphere, Stars } from '@react-three/drei'
import { motion } from 'framer-motion'
import { useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import type { Mesh } from 'three'
import { apiUrl } from './api'
import './App.css'

type Source = {
  page: number | null
  document: string | null
  section?: string | null
  line_start?: number | null
  line_end?: number | null
}

type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}

function NeuralOrb() {
  const meshRef = useRef<Mesh>(null)

  useFrame((_, delta) => {
    if (!meshRef.current) return
    meshRef.current.rotation.x += delta * 0.25
    meshRef.current.rotation.y += delta * 0.35
  })

  return (
    <Float speed={1.5} rotationIntensity={1.4} floatIntensity={2}>
      <Sphere ref={meshRef} args={[1.35, 128, 128]}>
        <meshStandardMaterial
          color="#5fe2ff"
          emissive="#1c3cff"
          emissiveIntensity={0.8}
          metalness={0.7}
          roughness={0.05}
        />
      </Sphere>
    </Float>
  )
}

function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content:
        'Welcome to the OGDCL assistant. I answer only from the indexed Coca-Cola Company U.S. SEC Form 10-K filing (annual report, fiscal year ended December 31, 2024). Ask about the business, risks, financials, or disclosures in that document.',
    },
  ])
  const [question, setQuestion] = useState('')
  const [sessionId, setSessionId] = useState('ui-session')
  const [uploading, setUploading] = useState(false)
  const [asking, setAsking] = useState(false)
  const [status, setStatus] = useState('Ready')

  const sourceSummary = useMemo(() => {
    const latestAssistant = [...messages].reverse().find((m) => m.role === 'assistant')
    return latestAssistant?.sources ?? []
  }, [messages])

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setUploading(true)
    setStatus('Indexing Coca-Cola 10-K corpus...')
    try {
      const response = await fetch(apiUrl('/upload'), {
        method: 'POST',
        body: form,
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail ?? 'Upload failed')
      setStatus(
        `Indexed ${data.chunks} chunks from ${data.document} in ${data.duration_seconds}s.`,
      )
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Upload failed'
      setStatus(`Upload error: ${message}`)
    } finally {
      setUploading(false)
    }
  }

  const handleAsk = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!question.trim()) return

    const asked = question.trim()
    setQuestion('')
    setAsking(true)
    setStatus('Retrieving context and generating grounded answer...')
    setMessages((prev) => [...prev, { role: 'user', content: asked }])

    try {
      const response = await fetch(apiUrl('/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: asked, session_id: sessionId }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail ?? 'Chat request failed')
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.answer, sources: data.sources ?? [] },
      ])
      setStatus('Answer complete.')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Chat request failed'
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${message}` },
      ])
      setStatus(`Chat error: ${message}`)
    } finally {
      setAsking(false)
    }
  }

  return (
    <main className="app-shell">
      <section className="scene-panel">
        <Canvas camera={{ position: [0, 0, 5], fov: 50 }}>
          <ambientLight intensity={0.5} />
          <pointLight position={[3, 3, 3]} intensity={4} />
          <Stars radius={40} depth={80} count={2500} factor={4} fade speed={1} />
          <NeuralOrb />
          <OrbitControls enablePan={false} enableZoom={false} autoRotate autoRotateSpeed={1.4} />
        </Canvas>
        <div className="scene-overlay">
          <h1>OGDCL · Coca-Cola reference desk</h1>
          <p>
            {'Oil & Gas Development Company Limited'} — internal access to structured answers from The
            Coca-Cola Company Form 10-K (indexed text only).
          </p>
        </div>
      </section>

      <section className="chat-panel">
        <header className="panel-header">
          <h2>{'Coca-Cola 10-K · grounded Q&A'}</h2>
          <span className="status-chip">{status}</span>
        </header>

        <form className="upload-form" onSubmit={handleUpload}>
          <input type="file" name="file" accept=".txt,application/pdf" />
          <input type="hidden" name="document_path" value="./ChatbotDocument.txt" />
          <input type="hidden" name="document_name" value="ChatbotDocument" />
          <small>
            Default corpus: Coca-Cola Form 10-K text (<code>ChatbotDocument.txt</code>). Upload a replacement
            PDF/TXT if needed.
          </small>
          <button type="submit" disabled={uploading}>
            {uploading ? 'Indexing...' : 'Upload & Index'}
          </button>
        </form>

        <label className="session-row">
          Session ID
          <input value={sessionId} onChange={(e) => setSessionId(e.target.value)} />
        </label>

        <div className="messages">
          {messages.map((message, index) => (
            <motion.article
              key={`${message.role}-${index}`}
              className={`bubble ${message.role}`}
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
            >
              <strong>{message.role === 'user' ? 'You' : 'Assistant'}</strong>
              <p>{message.content}</p>
            </motion.article>
          ))}
        </div>

        <form className="ask-form" onSubmit={handleAsk}>
          <textarea
            placeholder="e.g. What is the registrant’s exact legal name and Commission file number? What does Item 1A say about risk factors?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={3}
          />
          <button type="submit" disabled={asking}>
            {asking ? 'Thinking...' : 'Ask'}
          </button>
        </form>

        <div className="source-box">
          <h3>Latest citations (10-K)</h3>
          {sourceSummary.length === 0 ? (
            <p>No citations yet.</p>
          ) : (
            <ul>
              {sourceSummary.map((source, idx) => (
                <li key={`${source.document}-${source.page}-${source.section}-${idx}`}>
                  {source.section ? `${source.section} | ` : ''}
                  {source.line_start && source.line_end
                    ? `Lines ${source.line_start}-${source.line_end}`
                    : `Page ${source.page}`}
                  {' - '}
                  {source.document}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </main>
  )
}

export default App
