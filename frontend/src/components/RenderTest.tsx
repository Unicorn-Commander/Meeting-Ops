import React from 'react';

export const RenderTest: React.FC = () => {
  console.log('=== RenderTest Component ===');
  console.log('1. Component function executing');
  console.log('2. Environment check:');
  console.log('   - Window:', typeof window);
  console.log('   - Document:', typeof document);
  console.log('   - React:', React.version);
  console.log('   - User Agent:', typeof window !== 'undefined' ? navigator.userAgent : 'N/A');
  
  // Test basic DOM manipulation
  React.useEffect(() => {
    console.log('3. useEffect running');
    
    // Try to add a test element directly to body
    const testDiv = document.createElement('div');
    testDiv.id = 'render-test-marker';
    testDiv.textContent = 'RenderTest mounted successfully';
    testDiv.style.position = 'fixed';
    testDiv.style.top = '10px';
    testDiv.style.right = '10px';
    testDiv.style.padding = '10px';
    testDiv.style.backgroundColor = 'green';
    testDiv.style.color = 'white';
    testDiv.style.zIndex = '9999';
    document.body.appendChild(testDiv);
    
    return () => {
      console.log('4. useEffect cleanup');
      const marker = document.getElementById('render-test-marker');
      if (marker) {
        document.body.removeChild(marker);
      }
    };
  }, []);
  
  console.log('5. About to return JSX');
  
  return (
    <div 
      id="render-test-root"
      style={{ 
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'darkblue',
        color: 'white',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '20px',
        fontFamily: 'monospace'
      }}
    >
      <h1 style={{ fontSize: '36px', marginBottom: '20px' }}>Render Test</h1>
      <p>If you can see this, React is rendering correctly!</p>
      <p style={{ marginTop: '20px', fontSize: '14px' }}>
        Time: {new Date().toLocaleTimeString()}
      </p>
      <div style={{ marginTop: '40px', padding: '20px', backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}>
        <p>Debug Info:</p>
        <p style={{ fontSize: '14px' }}>React Version: {React.version}</p>
        <p style={{ fontSize: '14px' }}>User Agent: {navigator.userAgent}</p>
      </div>
    </div>
  );
};