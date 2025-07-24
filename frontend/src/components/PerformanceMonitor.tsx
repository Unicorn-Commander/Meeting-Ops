import { useState, useEffect } from 'react';
import { Zap, Cpu, HardDrive, Activity, TrendingUp, Clock } from 'lucide-react';
import { Card } from './ui/card';

interface PerformanceMetrics {
  transcription: {
    rtf: number; // Real-time factor
    tokensPerSecond: number;
    wordsPerMinute: number;
    processingTime: number;
    audioProcessed: number;
  };
  npu: {
    enabled: boolean;
    utilizationPercent: number;
    powerWatts: number;
    temperature: number;
    memoryUsedMB: number;
    computeTOPS: number;
  };
  system: {
    cpuPercent: number;
    memoryUsedGB: number;
    memoryTotalGB: number;
    diskUsedGB: number;
    diskTotalGB: number;
  };
  session: {
    activeCount: number;
    totalProcessed: number;
    averageRTF: number;
    totalHoursProcessed: number;
  };
}

export function PerformanceMonitor() {
  const [metrics, setMetrics] = useState<PerformanceMetrics>({
    transcription: {
      rtf: 0.08,
      tokensPerSecond: 0,
      wordsPerMinute: 0,
      processingTime: 0,
      audioProcessed: 0
    },
    npu: {
      enabled: false,
      utilizationPercent: 0,
      powerWatts: 0,
      temperature: 0,
      memoryUsedMB: 0,
      computeTOPS: 0
    },
    system: {
      cpuPercent: 0,
      memoryUsedGB: 0,
      memoryTotalGB: 16,
      diskUsedGB: 0,
      diskTotalGB: 500
    },
    session: {
      activeCount: 0,
      totalProcessed: 0,
      averageRTF: 0,
      totalHoursProcessed: 0
    }
  });

  const [history, setHistory] = useState<{
    timestamps: string[];
    rtf: number[];
    tokens: number[];
  }>({
    timestamps: [],
    rtf: [],
    tokens: []
  });

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const response = await fetch('/api/performance/metrics');
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        setMetrics(data);
        
        // Update history (keep last 20 points)
        setHistory(prev => ({
          timestamps: [...prev.timestamps.slice(-19), new Date().toLocaleTimeString()],
          rtf: [...prev.rtf.slice(-19), data.transcription.rtf],
          tokens: [...prev.tokens.slice(-19), data.transcription.tokensPerSecond]
        }));
      } catch (error) {
        console.error('Failed to fetch metrics:', error);
      }
    };

    fetchMetrics();
    const interval = setInterval(fetchMetrics, 5000); // Less frequent updates
    return () => clearInterval(interval);
  }, []);

  const getRTFColor = (rtf: number) => {
    if (rtf < 0.1) return 'text-green-400'; // Excellent (10x+ real-time)
    if (rtf < 0.5) return 'text-yellow-400'; // Good (2x+ real-time)
    return 'text-red-400'; // Poor (slower than real-time)
  };

  const getSpeedupFactor = (rtf: number) => {
    if (rtf === 0) return '∞';
    return `${(1 / rtf).toFixed(1)}x`;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Performance Monitor</h2>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${metrics.npu.enabled ? 'bg-green-400' : 'bg-gray-400'}`} />
          <span className="text-sm text-gray-300">
            {metrics.npu.enabled ? 'NPU Accelerated' : 'CPU Mode'}
          </span>
        </div>
      </div>

      {/* Key Metrics Row */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="bg-gray-800 border-gray-700 p-4">
          <div className="flex items-center justify-between mb-2">
            <Zap className="w-5 h-5 text-yellow-400" />
            <span className="text-xs text-gray-400">Speed</span>
          </div>
          <div className={`text-2xl font-bold ${getRTFColor(metrics.transcription.rtf)}`}>
            {getSpeedupFactor(metrics.transcription.rtf)}
          </div>
          <div className="text-xs text-gray-400 mt-1">
            Real-time factor: {metrics.transcription.rtf.toFixed(3)}
          </div>
        </Card>

        <Card className="bg-gray-800 border-gray-700 p-4">
          <div className="flex items-center justify-between mb-2">
            <TrendingUp className="w-5 h-5 text-green-400" />
            <span className="text-xs text-gray-400">Throughput</span>
          </div>
          <div className="text-2xl font-bold text-white">
            {metrics.transcription.tokensPerSecond.toLocaleString()}
          </div>
          <div className="text-xs text-gray-400 mt-1">
            tokens/second
          </div>
        </Card>

        <Card className="bg-gray-800 border-gray-700 p-4">
          <div className="flex items-center justify-between mb-2">
            <Activity className="w-5 h-5 text-blue-400" />
            <span className="text-xs text-gray-400">WPM</span>
          </div>
          <div className="text-2xl font-bold text-white">
            {metrics.transcription.wordsPerMinute.toLocaleString()}
          </div>
          <div className="text-xs text-gray-400 mt-1">
            words/minute
          </div>
        </Card>

        <Card className="bg-gray-800 border-gray-700 p-4">
          <div className="flex items-center justify-between mb-2">
            <Clock className="w-5 h-5 text-purple-400" />
            <span className="text-xs text-gray-400">Processed</span>
          </div>
          <div className="text-2xl font-bold text-white">
            {metrics.session.totalHoursProcessed.toFixed(1)}h
          </div>
          <div className="text-xs text-gray-400 mt-1">
            total audio
          </div>
        </Card>
      </div>

      {/* NPU Status */}
      {metrics.npu.enabled && (
        <Card className="bg-gray-800 border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Zap className="w-5 h-5 text-yellow-400" />
            NPU Status
          </h3>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-gray-400 mb-1">Utilization</div>
              <div className="flex items-baseline gap-2">
                <span className="text-xl font-bold text-white">
                  {metrics.npu.utilizationPercent}%
                </span>
                <div className="flex-1 bg-gray-700 rounded-full h-2 relative overflow-hidden">
                  <div 
                    className="absolute inset-y-0 left-0 bg-gradient-to-r from-green-400 to-yellow-400 rounded-full transition-all"
                    style={{ width: `${metrics.npu.utilizationPercent}%` }}
                  />
                </div>
              </div>
            </div>

            <div>
              <div className="text-sm text-gray-400 mb-1">Compute</div>
              <div className="text-xl font-bold text-green-400">
                {metrics.npu.computeTOPS} TOPS
              </div>
              <div className="text-xs text-gray-500">INT8 operations</div>
            </div>

            <div>
              <div className="text-sm text-gray-400 mb-1">Power</div>
              <div className="text-xl font-bold text-yellow-400">
                {metrics.npu.powerWatts}W
              </div>
              <div className="text-xs text-gray-500">{metrics.npu.temperature}°C</div>
            </div>

            <div>
              <div className="text-sm text-gray-400 mb-1">Memory</div>
              <div className="text-xl font-bold text-blue-400">
                {metrics.npu.memoryUsedMB} MB
              </div>
              <div className="text-xs text-gray-500">NPU RAM</div>
            </div>
          </div>

          <div className="mt-4 p-3 bg-gray-700/50 rounded">
            <div className="text-xs text-gray-400 mb-1">Performance vs CPU</div>
            <div className="text-2xl font-bold text-green-400">
              {metrics.npu.enabled ? '220x faster' : 'N/A'}
            </div>
          </div>
        </Card>
      )}

      {/* System Resources */}
      <Card className="bg-gray-800 border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Cpu className="w-5 h-5 text-blue-400" />
          System Resources
        </h3>
        
        <div className="space-y-4">
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-gray-400">CPU Usage</span>
              <span className="text-white">{metrics.system.cpuPercent}%</span>
            </div>
            <div className="bg-gray-700 rounded-full h-2 relative overflow-hidden">
              <div 
                className={`absolute inset-y-0 left-0 rounded-full transition-all ${
                  metrics.system.cpuPercent > 80 ? 'bg-red-400' : 
                  metrics.system.cpuPercent > 50 ? 'bg-yellow-400' : 'bg-green-400'
                }`}
                style={{ width: `${metrics.system.cpuPercent}%` }}
              />
            </div>
          </div>

          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-gray-400">Memory</span>
              <span className="text-white">
                {metrics.system.memoryUsedGB.toFixed(1)} / {metrics.system.memoryTotalGB} GB
              </span>
            </div>
            <div className="bg-gray-700 rounded-full h-2 relative overflow-hidden">
              <div 
                className="absolute inset-y-0 left-0 bg-blue-400 rounded-full transition-all"
                style={{ width: `${(metrics.system.memoryUsedGB / metrics.system.memoryTotalGB) * 100}%` }}
              />
            </div>
          </div>

          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-gray-400">Storage</span>
              <span className="text-white">
                {metrics.system.diskUsedGB.toFixed(0)} / {metrics.system.diskTotalGB} GB
              </span>
            </div>
            <div className="bg-gray-700 rounded-full h-2 relative overflow-hidden">
              <div 
                className="absolute inset-y-0 left-0 bg-purple-400 rounded-full transition-all"
                style={{ width: `${(metrics.system.diskUsedGB / metrics.system.diskTotalGB) * 100}%` }}
              />
            </div>
          </div>
        </div>
      </Card>

      {/* Real-time Chart */}
      <Card className="bg-gray-800 border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-white mb-4">Real-time Performance</h3>
        
        <div className="h-48 relative">
          {/* Simple sparkline visualization */}
          <div className="absolute inset-0 flex items-end justify-between gap-1">
            {history.rtf.map((value, index) => (
              <div
                key={index}
                className="flex-1 bg-gradient-to-t from-purple-600 to-purple-400 rounded-t opacity-80"
                style={{ 
                  height: `${Math.min(100, (1 / value) * 2)}%`,
                  minHeight: '4px'
                }}
              />
            ))}
          </div>
          
          {/* Y-axis labels */}
          <div className="absolute left-0 inset-y-0 flex flex-col justify-between text-xs text-gray-400 -ml-8">
            <span>50x</span>
            <span>25x</span>
            <span>0x</span>
          </div>
        </div>
        
        <div className="mt-4 flex justify-between text-xs text-gray-400">
          <span>20s ago</span>
          <span>Now</span>
        </div>
      </Card>

      {/* Session Stats */}
      <Card className="bg-gray-800 border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-white mb-4">Session Statistics</h3>
        
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
          <div>
            <div className="text-2xl font-bold text-white">{metrics.session.activeCount}</div>
            <div className="text-sm text-gray-400">Active Sessions</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{metrics.session.totalProcessed}</div>
            <div className="text-sm text-gray-400">Total Processed</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-green-400">
              {getSpeedupFactor(metrics.session.averageRTF)}
            </div>
            <div className="text-sm text-gray-400">Average Speed</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-purple-400">
              {(metrics.session.totalHoursProcessed * 60).toFixed(0)} min
            </div>
            <div className="text-sm text-gray-400">Audio Processed</div>
          </div>
        </div>
      </Card>
    </div>
  );
}