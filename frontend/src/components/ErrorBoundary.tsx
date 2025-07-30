import React, { Component } from 'react';
import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    console.error('ErrorBoundary caught error:', error);
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary error details:', {
      error: error.toString(),
      stack: error.stack,
      componentStack: errorInfo.componentStack
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          backgroundColor: '#1f2937',
          color: 'white',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '20px'
        }}>
          <div style={{
            backgroundColor: '#374151',
            padding: '40px',
            borderRadius: '8px',
            maxWidth: '600px',
            textAlign: 'center'
          }}>
            <h1 style={{ fontSize: '24px', marginBottom: '16px', color: '#ef4444' }}>
              Application Error
            </h1>
            <p style={{ marginBottom: '20px', color: '#d1d5db' }}>
              Something went wrong while rendering the application.
            </p>
            <pre style={{
              backgroundColor: '#1f2937',
              padding: '16px',
              borderRadius: '4px',
              fontSize: '12px',
              textAlign: 'left',
              overflow: 'auto',
              marginBottom: '20px'
            }}>
              {this.state.error?.toString()}
            </pre>
            <button
              onClick={() => window.location.reload()}
              style={{
                backgroundColor: '#8b5cf6',
                color: 'white',
                padding: '10px 20px',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              Reload Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}