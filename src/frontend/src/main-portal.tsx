import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import AppPortal from './AppPortal'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { initTheme } from './lib/theme'
import './i18n'
import './styles/index.css'

initTheme()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <AppPortal />
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>,
)
