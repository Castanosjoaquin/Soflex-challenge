import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import Despacho from './Despacho.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {window.location.pathname.startsWith('/despacho') ? <Despacho /> : <App />}
  </StrictMode>,
)
