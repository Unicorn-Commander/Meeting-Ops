import React from 'react';
import { useAuth } from '../contexts/AuthContext';
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
  const { user } = useAuth();

  if (!user) {
    return null;
  }

  // Check if user has one of the allowed roles
  const userRole = user.role || 'viewer';
  const hasPermission = allowedRoles.includes(userRole) || 
                       (user.is_superuser && allowedRoles.includes('superuser'));

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