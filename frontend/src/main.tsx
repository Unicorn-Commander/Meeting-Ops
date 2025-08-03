import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import NoAuthApp from './NoAuthApp.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <NoAuthApp />
  </StrictMode>,
)
