
import React, { useState, useEffect } from 'react';
import { Activity } from 'lucide-react';

export const NpuStatusIndicator: React.FC = () => {
  const [status, setStatus] = useState('loading');
  const [npuAvailable, setNpuAvailable] = useState(false);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch('http://localhost:9050/api/status');
        const data = await response.json();
        setStatus(data.npu_status);
        setNpuAvailable(data.npu_available);
      } catch (error) {
        setStatus('error');
      }
    };
    
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const getColor = () => {
    if (status === 'ready') return 'bg-green-500';
    if (status === 'loading') return 'bg-yellow-500';
    return 'bg-red-500';
  };

  return (
    <div className="flex items-center gap-2">
      <Activity className="w-5 h-5" />
      <span>NPU: </span>
      <div className="w-3 h-3 rounded-full ${getColor()}"></div>
      <span>{npuAvailable ? 'Hardware Ready' : 'Software Mode'}</span>
    </div>
  );
};
