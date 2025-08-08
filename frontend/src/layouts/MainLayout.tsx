import React, { useState } from 'react';
import { Outlet, useLocation, Link } from 'react-router-dom';
import { MeetingOpsNavigation } from '../components/navigation/MeetingOpsNavigation';
import { useAuth } from '../contexts/AuthContext';
import { ChevronRight, Home } from 'lucide-react';

export const MainLayout: React.FC = () => {
  const { user } = useAuth();
  const [navCollapsed, setNavCollapsed] = useState(false);
  const location = useLocation();
  
  // Generate breadcrumbs from path
  const getBreadcrumbs = () => {
    const paths = location.pathname.split('/').filter(p => p);
    const breadcrumbs: Array<{ label: string; url: string }> = [];
    
    // Build breadcrumb items
    paths.forEach((path, index) => {
      const url = '/' + paths.slice(0, index + 1).join('/');
      const label = path.charAt(0).toUpperCase() + path.slice(1).replace(/-/g, ' ');
      breadcrumbs.push({ label, url });
    });
    
    return breadcrumbs;
  };
  
  const breadcrumbs = getBreadcrumbs();

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* Navigation Sidebar */}
      <MeetingOpsNavigation />
      
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Breadcrumbs */}
        {breadcrumbs.length > 0 && (
          <div className="bg-gray-900 border-b border-gray-800 px-6 py-2">
            <div className="flex items-center gap-2 text-sm">
              <Link to="/dashboard" className="text-gray-400 hover:text-white transition-colors">
                <Home className="w-4 h-4" />
              </Link>
              {breadcrumbs.map((crumb, index) => (
                <React.Fragment key={crumb.url}>
                  <ChevronRight className="w-4 h-4 text-gray-600" />
                  {index === breadcrumbs.length - 1 ? (
                    <span className="text-white font-medium">{crumb.label}</span>
                  ) : (
                    <Link 
                      to={crumb.url} 
                      className="text-gray-400 hover:text-white transition-colors"
                    >
                      {crumb.label}
                    </Link>
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        )}
        
        {/* Content */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};