import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { MeetingOpsNavigation } from '../components/navigation/MeetingOpsNavigation';
import { useAuth } from '../contexts/AuthContext';

export const MainLayout: React.FC = () => {
  const { user } = useAuth();
  const [navCollapsed, setNavCollapsed] = useState(false);

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* Navigation Sidebar */}
      <MeetingOpsNavigation />
      
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Content */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};