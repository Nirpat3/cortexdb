'use client';

import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[CortexDB] Global error (layout failure):', error);
  }, [error]);

  return (
    <html lang="en">
      <head>
        <title>CortexDB - Critical Error</title>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body
        style={{
          margin: 0,
          background: '#0A0E1A',
          color: 'white',
          fontFamily: '"Inter", system-ui, sans-serif',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
        }}
      >
        <div
          style={{
            background: 'rgba(15, 20, 40, 0.75)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '16px',
            padding: '40px',
            maxWidth: '440px',
            width: '100%',
            textAlign: 'center',
          }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '12px',
              background: 'rgba(239, 68, 68, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 20px',
              fontSize: '28px',
            }}
          >
            !!
          </div>

          <h1 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '8px' }}>
            Critical Error
          </h1>
          <p style={{ fontSize: '14px', color: 'rgba(255,255,255,0.5)', marginBottom: '24px', lineHeight: 1.6 }}>
            A critical error occurred and the application layout could not be rendered.
            This usually indicates a configuration or build issue.
          </p>

          {error.digest && (
            <p style={{ fontSize: '10px', color: 'rgba(255,255,255,0.2)', fontFamily: 'monospace', marginBottom: '24px' }}>
              Error ID: {error.digest}
            </p>
          )}

          <button
            onClick={() => reset()}
            style={{
              padding: '10px 24px',
              borderRadius: '12px',
              background: 'rgba(46, 134, 193, 0.2)',
              color: '#2E86C1',
              border: 'none',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: 500,
              marginRight: '12px',
            }}
          >
            Try Again
          </button>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '10px 24px',
              borderRadius: '12px',
              background: 'rgba(255, 255, 255, 0.05)',
              color: 'rgba(255, 255, 255, 0.6)',
              border: 'none',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: 500,
            }}
          >
            Reload Page
          </button>
        </div>
      </body>
    </html>
  );
}
