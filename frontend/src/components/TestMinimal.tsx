import React from 'react';

export const TestMinimal: React.FC = () => {
  console.log('TestMinimal: Component function called');
  
  // Test if React hooks work
  const [count, setCount] = React.useState(0);
  console.log('TestMinimal: useState initialized with count:', count);
  
  // Test if useEffect runs
  React.useEffect(() => {
    console.log('TestMinimal: useEffect mounted');
    return () => {
      console.log('TestMinimal: useEffect cleanup');
    };
  }, []);
  
  console.log('TestMinimal: About to return JSX');
  
  return (
    <div style={{ 
      minHeight: '100vh', 
      backgroundColor: '#1a1a1a', 
      color: 'white',
      padding: '20px'
    }}>
      <h1 style={{ fontSize: '24px', marginBottom: '16px' }}>Test Minimal Component</h1>
      <p>This is a test component with inline styles.</p>
      <p>Count: {count}</p>
      <button 
        onClick={() => {
          console.log('Button clicked');
          setCount(count + 1);
        }}
        style={{
          padding: '8px 16px',
          backgroundColor: '#8b5cf6',
          border: 'none',
          borderRadius: '4px',
          color: 'white',
          cursor: 'pointer'
        }}
      >
        Increment
      </button>
    </div>
  );
};