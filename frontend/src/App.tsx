import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { ToastContainer } from 'react-toastify';
import { Login } from './components/Login';
import { RecordingInterface } from './components/RecordingInterface';
import { SessionList } from './components/SessionList';
import { SessionDetails } from './components/SessionDetails';
import { SystemStatus } from './components/SystemStatus';
import { ProductionDashboard } from './components/ProductionDashboard';
import { LiveTranscription } from './components/LiveTranscription';
import { Settings, LayoutDashboard, FileText, Home } from 'lucide-react';
import { AuthProvider } from './contexts/AuthContext';
import './index.css';

const API_BASE_URL = '';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storedToken = localStorage.getItem('access_token');
    if (storedToken) {
      fetch(`${API_BASE_URL}/api/auth/me`, {
        headers: { Authorization: `Bearer ${storedToken}` },
      })
        .then((res) => {
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
    return <Login onLogin={handleLogin} />;
  }

  return (
    <Router>
      <AuthProvider>
        <div className="min-h-screen bg-gray-900 text-white">
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
              <nav className="mt-4 flex gap-2">
                <Link to="/" className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors`}>
                  <LayoutDashboard className="w-4 h-4" />
                  Dashboard
                </Link>
                <Link to="/sessions" className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors`}>
                  <FileText className="w-4 h-4" />
                  Sessions
                </Link>
                <Link to="/simple" className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors`}>
                  <Home className="w-4 h-4" />
                  Simple View
                </Link>
              </nav>
            </div>
          </header>
          <main className="container mx-auto px-4 py-8">
            <Routes>
              <Route path="/" element={<ProductionDashboard />} />
              <Route path="/sessions" element={<SessionList />} />
              <Route path="/sessions/:sessionId" element={<SessionDetails />} />
              <Route path="/simple" element={
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  <div className="lg:col-span-1">
                    <SystemStatus token={token!} apiBaseUrl={API_BASE_URL} />
                  </div>
                  <div className="lg:col-span-2">
                    <RecordingInterface token={token!} apiBaseUrl={API_BASE_URL} />
                  </div>
                  <div className="lg:col-span-3">
                    <SessionList />
                  </div>
                </div>
              } />
            </Routes>
          </main>
        </div>
      </AuthProvider>
    </Router>
  );
}

export default App;
