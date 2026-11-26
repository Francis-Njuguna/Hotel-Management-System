import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './app/App';
import { SessionProvider } from './services/session';
import './styles/main.css';

const root = document.getElementById('root');
if (!root) throw new Error('The application root is missing.');
// Never include reset/verification URL paths in referrers. Origin-only metadata permits the same-origin Django CSRF check.
const referrer = document.querySelector<HTMLMetaElement>('meta[name="referrer"]') ?? document.createElement('meta');
referrer.name = 'referrer';
referrer.content = 'strict-origin';
if (!referrer.isConnected) document.head.append(referrer);

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <SessionProvider>
        <App />
      </SessionProvider>
    </BrowserRouter>
  </StrictMode>,
);
