import React, { useState } from 'react';
import { useAuthentikAuth } from '../contexts/AuthentikAuthContext';
import { UserDashboard } from './UserDashboard';
import { UserDashboardSimple } from './UserDashboardSimple';
import { SystemAdminPanel } from './SystemAdminPanel'; // New system admin panel
import { ApplicationAdminPanel } from './ApplicationAdminPanel'; // New application admin panel
import Dashboard from '../Dashboard'; // Legacy dashboard
import { ImprovedDashboard } from './ImprovedDashboard'; // New improved dashboard

interface DashboardRouterProps {
  defaultView?: 'user' | 'admin' | 'app-admin' | 'legacy' | 'improved';
}

export const DashboardRouter: React.FC<DashboardRouterProps> = ({ defaultView }) => {
  const { user } = useAuthentikAuth();
  const [currentView, setCurrentView] = useState<'user' | 'admin' | 'app-admin' | 'legacy' | 'improved'>(() => {
    if (defaultView) return defaultView;
    
    // Auto-select based on user role and preferences
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    
    // Check if user preference is stored
    const savedView = localStorage.getItem('dashboard-view') as 'user' | 'admin' | 'legacy' | 'improved';
    if (savedView && (savedView !== 'admin' || isAdmin)) {
      return savedView;
    }
    
    // Default to improved dashboard for production release  
    return 'improved';
  });

  const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
  
  // Debug logging
  console.log('DashboardRouter - user:', user);
  console.log('DashboardRouter - user role:', user?.role);
  console.log('DashboardRouter - isAdmin:', isAdmin);
  console.log('DashboardRouter - currentView:', currentView);

  // Save view preference
  const setView = (view: 'user' | 'admin' | 'app-admin' | 'legacy' | 'improved') => {
    setCurrentView(view);
    localStorage.setItem('dashboard-view', view);
  };

  const switchToAdmin = () => {
    console.log('switchToAdmin called - isAdmin:', isAdmin);
    if (isAdmin) {
      setView('admin');
    } else {
      console.warn('Cannot switch to admin - user is not admin');
    }
  };

  const switchToUser = () => {
    setView('user');
  };

  const switchToLegacy = () => {
    setView('legacy');
  };

  const switchToImproved = () => {
    setView('improved');
  };

  const switchToAppAdmin = () => {
    if (isAdmin) {
      setView('app-admin');
    }
  };

  // Dashboard view switcher component
  const ViewSwitcher = () => (
    <div className="fixed top-4 right-4 z-50 bg-gray-800 rounded-lg p-2 shadow-lg">
      <div className="flex space-x-2">
        <button
          onClick={switchToImproved}
          className={`px-3 py-1 rounded text-sm ${
            currentView === 'improved' 
              ? 'bg-purple-600 text-white' 
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          Improved
        </button>
        <button
          onClick={switchToLegacy}
          className={`px-3 py-1 rounded text-sm ${
            currentView === 'legacy' 
              ? 'bg-purple-600 text-white' 
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          Classic
        </button>
        <button
          onClick={switchToUser}
          className={`px-3 py-1 rounded text-sm ${
            currentView === 'user' 
              ? 'bg-purple-600 text-white' 
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          Simple
        </button>
        {isAdmin && (
          <>
            <button
              onClick={switchToAdmin}
              className={`px-3 py-1 rounded text-sm ${
                currentView === 'admin' 
                  ? 'bg-purple-600 text-white' 
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              System
            </button>
            <button
              onClick={switchToAppAdmin}
              className={`px-3 py-1 rounded text-sm ${
                currentView === 'app-admin' 
                  ? 'bg-purple-600 text-white' 
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              App Admin
            </button>
          </>
        )}
      </div>
    </div>
  );

  // Render appropriate dashboard based on current view
  switch (currentView) {
    case 'admin':
      if (!isAdmin) {
        // Fallback to user dashboard if not admin
        setView('user');
        return <UserDashboard onSwitchToAdmin={switchToAdmin} />;
      }
      return (
        <>
          <ViewSwitcher />
          <SystemAdminPanel />
        </>
      );
      
    case 'app-admin':
      if (!isAdmin) {
        // Fallback to user dashboard if not admin
        setView('user');
        return <UserDashboard onSwitchToAdmin={switchToAdmin} />;
      }
      return (
        <>
          <ViewSwitcher />
          <ApplicationAdminPanel />
        </>
      );
      
    case 'legacy':
      return (
        <>
          <ViewSwitcher />
          <Dashboard />
        </>
      );
      
    case 'improved':
      return (
        <>
          <ViewSwitcher />
          <ImprovedDashboard />
        </>
      );
      
    case 'user':
    default:
      return (
        <>
          <ViewSwitcher />
          <UserDashboardSimple 
            onSwitchToAdmin={isAdmin ? switchToAdmin : undefined}
          />
        </>
      );
  }
};