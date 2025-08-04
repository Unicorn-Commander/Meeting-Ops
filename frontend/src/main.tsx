import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
// import App from './App.tsx'
import AppRoleBased from './AppRoleBased.tsx'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'

// Add global error handler
window.addEventListener('error', (event) => {
  console.error('Global error:', event.error);
});

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled promise rejection:', event.reason);
});

const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <StrictMode>
      <BrowserRouter>
        <ErrorBoundary>
          <AppRoleBased />
        </ErrorBoundary>
      </BrowserRouter>
    </StrictMode>,
  );
} else {
  console.error('Root element not found!');
}
