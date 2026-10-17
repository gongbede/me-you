import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/nunito-sans'
import './index.css'
import './moderation-search.css'
import App from './App.tsx'
import { registerServiceWorker } from './pwa/registerServiceWorker'

registerServiceWorker(import.meta.env.PROD)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
