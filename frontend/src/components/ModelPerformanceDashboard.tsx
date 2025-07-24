import React, { useState, useEffect } from 'react';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';

interface ModelMetrics {
  model_id: string;
  model_name: string;
  statistics: {
    total_audio_hours: number;
    average_rtf: number;
    speedup_factor: number;
    average_confidence: number;
    invocation_count: number;
  };
}

interface BenchmarkSample {
  id: string;
  name: string;
  duration: number;
  difficulty_level: string;
  audio_quality: string;
  description: string;
}

interface BenchmarkResult {
  model_id: string;
  model_name: string;
  grade: string;
  score: number;
  samples_tested: number;
  average_metrics: {
    word_accuracy: number;
    confidence: number;
    rtf: number;
    speedup_factor: number;
  };
  npu_accelerated: boolean;
}

interface LeaderboardEntry {
  rank: number;
  model_id: string;
  model_name: string;
  grade: string;
  overall_score: number;
  metrics: {
    word_accuracy: number;
    confidence: number;
    rtf: number;
    speedup_factor: number;
  };
  npu_accelerated: boolean;
}

const ModelPerformanceDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'overview' | 'benchmarks' | 'leaderboard' | 'compare'>('overview');
  const [modelMetrics, setModelMetrics] = useState<Record<string, ModelMetrics>>({});
  const [benchmarkSamples, setBenchmarkSamples] = useState<BenchmarkSample[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [comparisonResults, setComparisonResults] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch performance data
  useEffect(() => {
    fetchPerformanceData();
    fetchBenchmarkSamples();
    fetchLeaderboard();
  }, []);

  const fetchPerformanceData = async () => {
    try {
      const response = await fetch('/api/performance/models', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setModelMetrics(data.models || {});
      }
    } catch (err) {
      console.error('Error fetching performance data:', err);
    }
  };

  const fetchBenchmarkSamples = async () => {
    try {
      const response = await fetch('/api/benchmarks/samples', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setBenchmarkSamples(data);
      }
    } catch (err) {
      console.error('Error fetching benchmark samples:', err);
    }
  };

  const fetchLeaderboard = async () => {
    try {
      const response = await fetch('/api/benchmarks/leaderboard', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setLeaderboard(data.leaderboard || []);
      }
    } catch (err) {
      console.error('Error fetching leaderboard:', err);
    }
  };

  const runBenchmark = async (modelId: string) => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`/api/benchmarks/models/${modelId}/benchmark`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      if (response.ok) {
        const result = await response.json();
        console.log('Benchmark completed:', result);
        // Refresh data
        fetchPerformanceData();
        fetchLeaderboard();
      } else {
        const errorData = await response.json();
        setError(`Benchmark failed: ${errorData.detail}`);
      }
    } catch (err) {
      setError(`Benchmark error: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const compareModels = async () => {
    if (selectedModels.length < 2) {
      setError('Please select at least 2 models to compare');
      return;
    }

    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch('/api/benchmarks/compare', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({ model_ids: selectedModels })
      });
      
      if (response.ok) {
        const result = await response.json();
        setComparisonResults(result);
        setActiveTab('compare');
      } else {
        const errorData = await response.json();
        setError(`Comparison failed: ${errorData.detail}`);
      }
    } catch (err) {
      setError(`Comparison error: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const getGradeColor = (grade: string) => {
    switch (grade) {
      case 'A+': return 'bg-green-100 text-green-800';
      case 'A': return 'bg-green-100 text-green-700';
      case 'B+': return 'bg-blue-100 text-blue-800';
      case 'B': return 'bg-blue-100 text-blue-700';
      case 'C+': return 'bg-yellow-100 text-yellow-800';
      case 'C': return 'bg-yellow-100 text-yellow-700';
      case 'D': return 'bg-orange-100 text-orange-700';
      case 'F': return 'bg-red-100 text-red-700';
      default: return 'bg-gray-100 text-gray-700';
    }
  };

  const formatPercentage = (value: number) => `${(value * 100).toFixed(1)}%`;
  const formatNumber = (value: number, decimals = 1) => value.toFixed(decimals);

  return (
    <div className="w-full max-w-7xl mx-auto p-6 space-y-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Model Performance Dashboard</h1>
        <p className="text-gray-600">Comprehensive analysis of STT model performance and benchmarks</p>
      </div>

      {/* Tab Navigation */}
      <div className="flex space-x-1 bg-gray-100 p-1 rounded-lg">
        {[
          { id: 'overview', label: 'Performance Overview' },
          { id: 'benchmarks', label: 'Benchmarks' },
          { id: 'leaderboard', label: 'Leaderboard' },
          { id: 'compare', label: 'Model Comparison' }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-4 py-2 rounded-md font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4 text-red-700">
          {error}
        </div>
      )}

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {Object.entries(modelMetrics).map(([modelId, metrics]) => (
              <Card key={modelId} className="p-6">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-semibold text-lg">{metrics.model_name}</h3>
                    <p className="text-sm text-gray-600 mb-4">{modelId}</p>
                  </div>
                  {modelId.includes('npu') && (
                    <Badge className="bg-purple-100 text-purple-800">NPU</Badge>
                  )}
                </div>
                
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">Speedup Factor:</span>
                    <span className="font-medium">{formatNumber(metrics.statistics.speedup_factor)}x</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">Average Confidence:</span>
                    <span className="font-medium">{formatPercentage(metrics.statistics.average_confidence)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">RTF:</span>
                    <span className="font-medium">{formatNumber(metrics.statistics.average_rtf, 4)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">Total Operations:</span>
                    <span className="font-medium">{metrics.statistics.invocation_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">Audio Processed:</span>
                    <span className="font-medium">{formatNumber(metrics.statistics.total_audio_hours)} hrs</span>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t">
                  <Button
                    onClick={() => runBenchmark(modelId)}
                    disabled={loading}
                    className="w-full"
                    variant="outline"
                  >
                    {loading ? 'Running...' : 'Run Benchmark'}
                  </Button>
                </div>
              </Card>
            ))}
          </div>

          {Object.keys(modelMetrics).length === 0 && (
            <Card className="p-8 text-center">
              <h3 className="text-lg font-medium text-gray-900 mb-2">No Performance Data Available</h3>
              <p className="text-gray-600 mb-4">Run some transcriptions or benchmarks to see performance metrics.</p>
            </Card>
          )}
        </div>
      )}

      {/* Benchmarks Tab */}
      {activeTab === 'benchmarks' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-semibold">Benchmark Samples</h2>
            <div className="text-sm text-gray-600">
              {benchmarkSamples.length} samples available
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {benchmarkSamples.map(sample => (
              <Card key={sample.id} className="p-6">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="font-semibold">{sample.name}</h3>
                  <div className="flex space-x-2">
                    <Badge variant={sample.difficulty_level === 'easy' ? 'default' : 
                                  sample.difficulty_level === 'medium' ? 'secondary' : 'destructive'}>
                      {sample.difficulty_level}
                    </Badge>
                    <Badge variant="outline">{sample.audio_quality}</Badge>
                  </div>
                </div>
                
                <p className="text-sm text-gray-600 mb-3">{sample.description}</p>
                
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Duration:</span>
                  <span className="font-medium">{sample.duration}s</span>
                </div>
              </Card>
            ))}
          </div>

          {benchmarkSamples.length === 0 && (
            <Card className="p-8 text-center">
              <h3 className="text-lg font-medium text-gray-900 mb-2">No Benchmark Samples</h3>
              <p className="text-gray-600">Upload audio samples to start benchmarking models.</p>
            </Card>
          )}
        </div>
      )}

      {/* Leaderboard Tab */}
      {activeTab === 'leaderboard' && (
        <div className="space-y-6">
          <h2 className="text-xl font-semibold">Model Performance Leaderboard</h2>
          
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Rank</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Model</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Grade</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Score</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Accuracy</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Speedup</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {leaderboard.map((entry) => (
                    <tr key={entry.model_id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          <span className="text-2xl font-bold text-gray-900">#{entry.rank}</span>
                          {entry.rank === 1 && <span className="ml-2 text-yellow-500">🏆</span>}
                          {entry.rank === 2 && <span className="ml-2 text-gray-400">🥈</span>}
                          {entry.rank === 3 && <span className="ml-2 text-orange-600">🥉</span>}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div>
                          <div className="text-sm font-medium text-gray-900">{entry.model_name}</div>
                          <div className="text-sm text-gray-500">{entry.model_id}</div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Badge className={getGradeColor(entry.grade)}>
                          {entry.grade}
                        </Badge>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {formatNumber(entry.overall_score, 3)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {formatPercentage(entry.metrics.word_accuracy)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {formatNumber(entry.metrics.speedup_factor)}x
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {entry.npu_accelerated ? (
                          <Badge className="bg-purple-100 text-purple-800">NPU</Badge>
                        ) : (
                          <Badge variant="outline">CPU</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {leaderboard.length === 0 && (
            <Card className="p-8 text-center">
              <h3 className="text-lg font-medium text-gray-900 mb-2">No Leaderboard Data</h3>
              <p className="text-gray-600">Run benchmarks to populate the leaderboard.</p>
            </Card>
          )}
        </div>
      )}

      {/* Comparison Tab */}
      {activeTab === 'compare' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-semibold">Model Comparison</h2>
            <Button
              onClick={compareModels}
              disabled={loading || selectedModels.length < 2}
            >
              {loading ? 'Comparing...' : 'Compare Selected Models'}
            </Button>
          </div>

          {/* Model Selection */}
          <Card className="p-6">
            <h3 className="font-medium mb-4">Select Models to Compare</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {Object.keys(modelMetrics).map(modelId => (
                <label key={modelId} className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedModels.includes(modelId)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedModels([...selectedModels, modelId]);
                      } else {
                        setSelectedModels(selectedModels.filter(id => id !== modelId));
                      }
                    }}
                    className="rounded border-gray-300"
                  />
                  <span className="text-sm">{modelMetrics[modelId]?.model_name || modelId}</span>
                </label>
              ))}
            </div>
          </Card>

          {/* Comparison Results */}
          {comparisonResults && (
            <Card className="p-6">
              <h3 className="font-medium mb-4">Comparison Results</h3>
              
              {/* Winners */}
              {comparisonResults.comparison?.winners && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                  <div className="bg-yellow-50 p-4 rounded-lg">
                    <div className="text-sm font-medium text-yellow-800">🏆 Fastest</div>
                    <div className="text-lg font-bold text-yellow-900">
                      {comparisonResults.comparison.winners.fastest?.model_id}
                    </div>
                  </div>
                  <div className="bg-green-50 p-4 rounded-lg">
                    <div className="text-sm font-medium text-green-800">🎯 Most Accurate</div>
                    <div className="text-lg font-bold text-green-900">
                      {comparisonResults.comparison.winners.most_accurate?.model_id}
                    </div>
                  </div>
                  <div className="bg-blue-50 p-4 rounded-lg">
                    <div className="text-sm font-medium text-blue-800">💎 Highest Confidence</div>
                    <div className="text-lg font-bold text-blue-900">
                      {comparisonResults.comparison.winners.highest_confidence?.model_id}
                    </div>
                  </div>
                  <div className="bg-purple-50 p-4 rounded-lg">
                    <div className="text-sm font-medium text-purple-800">🌟 Best Overall</div>
                    <div className="text-lg font-bold text-purple-900">
                      {comparisonResults.comparison.winners.best_overall?.model_id}
                    </div>
                  </div>
                </div>
              )}

              {/* Model Rankings */}
              {comparisonResults.comparison?.model_rankings && (
                <div className="space-y-4">
                  <h4 className="font-medium">Model Rankings</h4>
                  {comparisonResults.comparison.model_rankings.map((model: any, index: number) => (
                    <div key={model.model_id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                      <div className="flex items-center space-x-4">
                        <span className="text-2xl font-bold text-gray-600">#{index + 1}</span>
                        <div>
                          <div className="font-medium">{model.model_name}</div>
                          <div className="text-sm text-gray-600">{model.model_id}</div>
                        </div>
                      </div>
                      <div className="flex items-center space-x-4">
                        <Badge className={getGradeColor(model.grade)}>{model.grade}</Badge>
                        <div className="text-right">
                          <div className="text-sm font-medium">Score: {formatNumber(model.score, 3)}</div>
                          <div className="text-sm text-gray-600">
                            {formatNumber(model.speedup)}x speedup
                          </div>
                        </div>
                        {model.npu_accelerated && (
                          <Badge className="bg-purple-100 text-purple-800">NPU</Badge>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}
        </div>
      )}
    </div>
  );
};

export default ModelPerformanceDashboard;