import { useState, useEffect } from 'react';
import { Login } from './components/Login';
import { RecordingInterface } from './components/RecordingInterface';
import { SessionList } from './components/SessionList';  // Use full SessionList
import { SystemStatus } from './components/SystemStatus';
import { ProductionDashboard } from './components/ProductionDashboard';
import { LiveTranscription } from './components/LiveTranscription';
import { Settings, LayoutDashboard, FileText, Home } from 'lucide-react';
import { AuthProvider } from './contexts/AuthContext';
import './App.css';

// API configuration - use relative URLs so vite proxy works
const API_BASE_URL = '';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentView, setCurrentView] = useState<'dashboard' | 'simple' | 'sessions'>('dashboard');

  // Check if user is already authenticated
  useEffect(() => {
    const storedToken = localStorage.getItem('access_token');
    if (storedToken) {
      // Verify token is still valid
      fetch(`${API_BASE_URL}/api/auth/me`, {
        headers: {
          'Authorization': `Bearer ${storedToken}`
        }
      })
      .then(res => {
        if (res.ok) {
          setToken(storedToken);
          setIsAuthenticated(true);
        } else {
          localStorage.removeItem('access_token');
        }
      })
      .catch(() => {
        localStorage.removeItem('access_token');
      })
      .finally(() => {
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, []);

  const handleLogin = (accessToken: string) => {
    localStorage.setItem('access_token', accessToken);
    setToken(accessToken);
    setIsAuthenticated(true);
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    setToken(null);
    setIsAuthenticated(false);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-white text-xl">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} apiBaseUrl={API_BASE_URL} />;
  }

  return (
    <AuthProvider>
      <div className="min-h-screen bg-gray-900 text-white">
        {/* Header */}
        <header className="bg-gray-800 shadow-lg">
        <div className="container mx-auto px-4 py-4">
          <div className="flex justify-between items-center">
            <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
              🦄 Meeting-Ops Recording Appliance
            </h1>
            <button
              onClick={handleLogout}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
            >
              Logout
            </button>
          </div>
          
          {/* Navigation Menu */}
          <nav className="mt-4 flex gap-2">
            <button
              onClick={() => setCurrentView('dashboard')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                currentView === 'dashboard' 
                  ? 'bg-purple-600 text-white' 
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              <LayoutDashboard className="w-4 h-4" />
              Dashboard
            </button>
            <button
              onClick={() => setCurrentView('sessions')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                currentView === 'sessions' 
                  ? 'bg-purple-600 text-white' 
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              <FileText className="w-4 h-4" />
              Sessions
            </button>
            <button
              onClick={() => setCurrentView('simple')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                currentView === 'simple' 
                  ? 'bg-purple-600 text-white' 
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              <Home className="w-4 h-4" />
              Simple View
            </button>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        {currentView === 'dashboard' ? (
          <ProductionDashboard />
        ) : currentView === 'sessions' ? (
          <SessionList onSelectSession={(session) => console.log('Selected session:', session)} />
        ) : (
          // Simple view - original layout
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* System Status */}
            <div className="lg:col-span-1">
              <SystemStatus token={token!} apiBaseUrl={API_BASE_URL} />
            </div>

            {/* Recording Interface */}
            <div className="lg:col-span-2">
              <RecordingInterface token={token!} apiBaseUrl={API_BASE_URL} />
            </div>

            {/* Session List */}
            <div className="lg:col-span-3">
              <SessionList onSelectSession={(session) => console.log('Selected session:', session)} />
            </div>
          </div>
        )}
      </main>
    </div>
    </AuthProvider>
  );
}

export default App;