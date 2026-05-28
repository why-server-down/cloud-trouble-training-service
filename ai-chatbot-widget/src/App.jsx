import { useState, useEffect } from 'react'
import ChatWidget from './components/ChatWidget'
import './App.css'

function App() {
  const [config, setConfig] = useState({
    apiUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
    theme: 'light',
    position: 'bottom-right',
  })

  useEffect(() => {
    // Listen for configuration from parent window
    const handleMessage = (event) => {
      if (event.data.type === 'CHATBOT_CONFIG') {
        setConfig(prev => ({ ...prev, ...event.data.config }))
      }
    }

    window.addEventListener('message', handleMessage)
    
    // Notify parent that chatbot is ready
    window.parent.postMessage({ type: 'CHATBOT_READY' }, '*')

    return () => window.removeEventListener('message', handleMessage)
  }, [])

  return (
    <div className="app">
      <ChatWidget config={config} />
    </div>
  )
}

export default App
