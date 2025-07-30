import React from 'react';

export const PlainHtmlTest: React.FC = () => {
  React.useEffect(() => {
    console.log('PlainHtmlTest mounted');
    // Add a style tag to ensure our styles work
    const style = document.createElement('style');
    style.textContent = `
      body {
        margin: 0;
        padding: 0;
      }
      #plain-html-test {
        background-color: #2a2a2a;
        color: white;
        min-height: 100vh;
        padding: 40px;
        font-family: Arial, sans-serif;
      }
      #plain-html-test h1 {
        color: #a78bfa;
        margin-bottom: 20px;
      }
      #plain-html-test button {
        background-color: #8b5cf6;
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 4px;
        cursor: pointer;
        margin-top: 20px;
      }
      #plain-html-test button:hover {
        background-color: #7c3aed;
      }
    `;
    document.head.appendChild(style);
    
    return () => {
      document.head.removeChild(style);
    };
  }, []);
  
  return React.createElement(
    'div',
    { id: 'plain-html-test' },
    React.createElement('h1', null, 'Plain HTML Test'),
    React.createElement('p', null, 'This component uses no Tailwind classes, only inline styles and createElement.'),
    React.createElement('p', null, 'Current time: ' + new Date().toLocaleTimeString()),
    React.createElement(
      'button',
      { 
        onClick: () => {
          alert('Button clicked! React is working.');
        }
      },
      'Test Button'
    ),
    React.createElement(
      'div',
      { style: { marginTop: '40px', padding: '20px', backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' } },
      React.createElement('h2', null, 'Debug Info:'),
      React.createElement('p', null, 'React Version: ' + React.version),
      React.createElement('p', null, 'User Agent: ' + navigator.userAgent.substring(0, 50) + '...')
    )
  );
};