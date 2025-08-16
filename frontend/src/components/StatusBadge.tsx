import React from 'react';
import { CheckCircle, Clock, AlertCircle, Play, Pause } from 'lucide-react';

interface StatusBadgeProps {
  status: 'idle' | 'recording' | 'processing' | 'completed' | 'error';
  className?: string;
  showIcon?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ 
  status, 
  className = '',
  showIcon = true
}) => {
  const statusConfig = {
    idle: {
      color: 'bg-gray-500/10 text-gray-400 border-gray-500',
      icon: Clock,
      label: 'Idle'
    },
    recording: {
      color: 'bg-red-500/10 text-red-400 border-red-500',
      icon: Play,
      label: 'Recording'
    },
    processing: {
      color: 'bg-yellow-500/10 text-yellow-400 border-yellow-500',
      icon: Clock,
      label: 'Processing'
    },
    completed: {
      color: 'bg-green-500/10 text-green-400 border-green-500',
      icon: CheckCircle,
      label: 'Completed'
    },
    error: {
      color: 'bg-red-600/10 text-red-400 border-red-600',
      icon: AlertCircle,
      label: 'Error'
    }
  };

  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs border ${config.color} ${className}`}>
      {showIcon && <Icon className="w-3 h-3" />}
      {config.label}
    </span>
  );
};