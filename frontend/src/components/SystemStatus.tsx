import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Cpu, HardDrive, Activity, Zap } from 'lucide-react';

interface SystemStatusProps {
  token: string;
  apiBaseUrl: string;
}

export const SystemStatus: React.FC<SystemStatusProps> = ({ token, apiBaseUrl }) => {
  const [status, setStatus] = React.useState({
    cpu: 0,
    memory: 0,
    disk: 0,
    npu: 'idle'
  });

  React.useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/api/system/status`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        if (response.ok) {
          const data = await response.json();
          setStatus(data);
        }
      } catch (error) {
        console.error('Failed to fetch system status:', error);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [token, apiBaseUrl]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="w-5 h-5" />
          System Status
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="flex items-center gap-2">
              <Cpu className="w-4 h-4" />
              CPU
            </span>
            <span>{status.cpu}%</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div 
              className="bg-gradient-to-r from-purple-500 to-pink-500 h-2 rounded-full"
              style={{ width: `${status.cpu}%` }}
            />
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="flex items-center gap-2">
              <HardDrive className="w-4 h-4" />
              Memory
            </span>
            <span>{status.memory}%</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div 
              className="bg-gradient-to-r from-purple-500 to-pink-500 h-2 rounded-full"
              style={{ width: `${status.memory}%` }}
            />
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="flex items-center gap-2">
              <Zap className="w-4 h-4" />
              NPU Status
            </span>
            <Badge variant={status.npu === 'active' ? 'default' : 'secondary'}>
              {status.npu}
            </Badge>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};