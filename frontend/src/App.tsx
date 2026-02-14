import React from 'react'
import Terminal from './components/Terminal/Terminal'
import './App.css'

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>☁️ K8s Survival Camp - Terminal</h1>
        <div className="header-info">
          <span className="namespace-badge">Namespace: user-demo</span>
        </div>
      </header>
      <main className="app-main">
        <Terminal />
      </main>
    </div>
  )
}

export default App
