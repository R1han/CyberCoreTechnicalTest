import React from 'react';
import ReactDOM from 'react-dom/client';
import { AskDocsWidget } from './components/AskDocsWidget';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <div style={{ maxWidth: 700, margin: '40px auto', padding: '0 16px' }}>
      <AskDocsWidget title="Ask Docs" topK={5} />
    </div>
  </React.StrictMode>,
);
