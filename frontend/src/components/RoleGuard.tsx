import React from 'react';
import { useAuthentikAuth } from '../contexts/AuthentikAuthContext';
import { AlertCircle } from 'lucide-react';

interface RoleGuardProps {
  allowedRoles: string[];
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export const RoleGuard: React.FC<RoleGuardProps> = ({ 
  allowedRoles, 
  children, 
  fallback 
}) => {
  const { user } = useAuthentikAuth();

  if (!user) {
    return null;
  }

  // Check if user has one of the allowed roles (using Authentik groups)
  const userGroups = user.groups || [];
  const hasPermission = allowedRoles.some(role => 
    userGroups.includes(role) || 
    (role === 'admin' && user.is_admin) ||
    (role === 'superuser' && user.is_admin) ||
    (role === 'manager' && (user.is_admin || userGroups.includes('Meeting-Ops-Managers'))) ||
    (role === 'user' && userGroups.includes('Meeting-Ops-Users')) ||
    (role === 'viewer' && userGroups.length > 0) // Any authenticated user can view
  );

  if (!hasPermission) {
    if (fallback) {
      return <>{fallback}</>;
    }

    return (
      <div className="p-8 text-center">
        <AlertCircle className="w-12 h-12 text-yellow-500 mx-auto mb-4" />
        <h3 className="text-lg font-semibold text-gray-300 mb-2">
          Access Restricted
        </h3>
        <p className="text-gray-400">
          You don't have permission to view this content. 
          Required role: {allowedRoles.join(' or ')}
        </p>
      </div>
    );
  }

  return <>{children}</>;
};