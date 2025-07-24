import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { UserDashboard } from './UserDashboard';
import { AdminPanel } from './AdminPanel';
import Dashboard from '../Dashboard'; // Legacy dashboard

interface DashboardRouterProps {
  defaultView?: 'user' | 'admin' | 'legacy';
}

export const DashboardRouter: React.FC<DashboardRouterProps> = ({ defaultView }) => {
  const { user } = useAuth();
  const [currentView, setCurrentView] = useState<'user' | 'admin' | 'legacy'>(() => {
    if (defaultView) return defaultView;
    
    // Auto-select based on user role and preferences
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    
    // Check if user preference is stored
    const savedView = localStorage.getItem('dashboard-view') as 'user' | 'admin' | 'legacy';
    if (savedView && (savedView !== 'admin' || isAdmin)) {
      return savedView;
    }
    
    // Default to user dashboard for regular users, admin for admins
    return isAdmin ? 'admin' : 'user';
  });

  const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

  // Save view preference
  const setView = (view: 'user' | 'admin' | 'legacy') => {
    setCurrentView(view);
    localStorage.setItem('dashboard-view', view);
  };

  const switchToAdmin = () => {
    if (isAdmin) {
      setView('admin');
    }
  };

  const switchToUser = () => {
    setView('user');
  };

  const switchToLegacy = () => {
    setView('legacy');
  };

  // Render appropriate dashboard based on current view
  switch (currentView) {
    case 'admin':
      if (!isAdmin) {
        // Fallback to user dashboard if not admin
        setView('user');
        return <UserDashboard onSwitchToAdmin={switchToAdmin} />;
      }
      return (
        <AdminPanel 
          onClose={() => setView('user')}
        />
      );
      
    case 'legacy':
      return <Dashboard />;
      
    case 'user':
    default:
      return (
        <UserDashboard 
          onSwitchToAdmin={isAdmin ? switchToAdmin : undefined}
        />
      );
  }
};