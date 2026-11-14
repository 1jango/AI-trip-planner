import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

const rootElement = document.getElementById('root')
// Jawne sprawdzenie zamiast `!`: jeśli ktoś zmieni id w index.html, dostanie czytelny błąd.
if (rootElement === null) {
  throw new Error('Brak elementu #root w index.html')
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
