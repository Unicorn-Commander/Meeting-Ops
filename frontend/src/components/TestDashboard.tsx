import React from 'react';
import { useAuth } from '../contexts/AuthContext';

export const TestDashboard: React.FC = () => {
  const { user } = useAuth();
  
  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <h1 className="text-3xl font-bold">Test Dashboard</h1>
      <p className="mt-4">User: {user?.username || 'Not logged in'}</p>
      <p>Role: {user?.role || 'No role'}</p>
      <div className="mt-8 p-4 bg-gray-800 rounded">
        <p>This is a test dashboard to verify rendering.</p>
      </div>
    </div>
  );
};