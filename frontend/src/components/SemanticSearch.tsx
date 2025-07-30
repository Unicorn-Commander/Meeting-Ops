import React, { useState, useCallback } from 'react';
import { Search, Sparkles, Clock, User, FileText, ChevronRight } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Badge } from './ui/badge';
// Temporary inline components until we have proper UI components
const Input = ({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) => (
  <input className={`px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:border-purple-500 focus:outline-none ${className || ''}`} {...props} />
);

const Select = ({ children, value, onValueChange }: { children: React.ReactNode; value: string; onValueChange: (value: string) => void }) => {
  return (
    <select
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
      className="px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:border-purple-500 focus:outline-none"
    >
      {children}
    </select>
  );
};

const SelectItem = ({ value, children }: { value: string; children: React.ReactNode }) => (
  <option value={value}>{children}</option>
);

const SelectTrigger = ({ children }: { children: React.ReactNode }) => <>{children}</>;
const SelectContent = ({ children }: { children: React.ReactNode }) => <>{children}</>;
const SelectValue = ({ placeholder }: { placeholder?: string }) => <>{placeholder}</>;
import { useDebounce } from '../hooks/useDebounce';
import { format } from 'date-fns';

interface SearchResult {
  score: number;
  segment_id: string;
  session_id: string;
  text: string;
  speaker: string;
  timestamp: string;
  start_time?: number;
  end_time?: number;
  confidence?: number;
}

interface CollectionInfo {
  name: string;
  vector_count: number;
  indexed_vectors: number;
  points_count: number;
  segments_count: number;
  status: string;
  vector_size: number;
  distance: string;
}

export const SemanticSearch: React.FC = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collectionInfo, setCollectionInfo] = useState<CollectionInfo | null>(null);
  
  // Search filters
  const [sessionFilter, setSessionFilter] = useState<string>('');
  const [speakerFilter, setSpeakerFilter] = useState<string>('');
  const [scoreThreshold, setScoreThreshold] = useState<number>(0.5);
  
  const debouncedQuery = useDebounce(query, 300);

  // Fetch collection info on mount
  React.useEffect(() => {
    fetchCollectionInfo();
  }, []);

  const fetchCollectionInfo = async () => {
    try {
      const response = await fetch('/api/search/collection/info', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      if (!response.ok) return;
      
      const data = await response.json();
      setCollectionInfo(data);
    } catch (err) {
      console.error('Failed to fetch collection info:', err);
    }
  };

  const performSearch = useCallback(async () => {
    if (!debouncedQuery.trim()) {
      setResults([]);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload = {
        query: debouncedQuery,
        limit: 20,
        score_threshold: scoreThreshold,
        ...(sessionFilter && { session_id: sessionFilter }),
        ...(speakerFilter && { speaker: speakerFilter })
      };

      const response = await fetch('/api/search/semantic', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error('Search failed');
      }

      const data = await response.json();
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery, sessionFilter, speakerFilter, scoreThreshold]);

  // Perform search when debounced query changes
  React.useEffect(() => {
    performSearch();
  }, [performSearch]);

  const formatTime = (seconds?: number) => {
    if (!seconds) return '';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600';
    if (score >= 0.6) return 'text-yellow-600';
    return 'text-gray-600';
  };

  const navigateToSession = (sessionId: string, startTime?: number) => {
    // Navigate to session with timestamp
    const url = `/sessions/${sessionId}${startTime ? `?t=${startTime}` : ''}`;
    window.location.href = url;
  };

  return (
    <div className="space-y-6">
      {/* Header with Collection Info */}
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-purple-600" />
            Semantic Search
          </h2>
          <p className="text-gray-600 mt-1">
            Search transcriptions by meaning, not just keywords
          </p>
        </div>
        
        {collectionInfo && (
          <Card className="bg-gray-50">
            <CardContent className="p-4">
              <div className="text-sm space-y-1">
                <div className="flex justify-between">
                  <span className="text-gray-600">Indexed:</span>
                  <span className="font-medium">{collectionInfo.points_count.toLocaleString()} segments</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Vectors:</span>
                  <span className="font-medium">{collectionInfo.vector_count.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Model:</span>
                  <span className="font-medium text-xs">MiniLM-L6</span>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Search Controls */}
      <Card>
        <CardContent className="p-6">
          <div className="space-y-4">
            {/* Main Search Input */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
              <Input
                type="text"
                placeholder="Search by meaning... (e.g., 'discussion about deadlines', 'customer feedback')"
                value={query}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setQuery(e.target.value)}
                className="pl-10 pr-4 py-2 text-lg"
              />
            </div>

            {/* Filters */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-sm text-gray-600 mb-1 block">Session Filter</label>
                <Input
                  placeholder="Filter by session ID"
                  value={sessionFilter}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSessionFilter(e.target.value)}
                />
              </div>
              
              <div>
                <label className="text-sm text-gray-600 mb-1 block">Speaker Filter</label>
                <Input
                  placeholder="Filter by speaker"
                  value={speakerFilter}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSpeakerFilter(e.target.value)}
                />
              </div>
              
              <div>
                <label className="text-sm text-gray-600 mb-1 block">Minimum Similarity</label>
                <Select value={scoreThreshold.toString()} onValueChange={(v: string) => setScoreThreshold(parseFloat(v))}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">Any match</SelectItem>
                    <SelectItem value="0.3">Low (30%)</SelectItem>
                    <SelectItem value="0.5">Medium (50%)</SelectItem>
                    <SelectItem value="0.7">High (70%)</SelectItem>
                    <SelectItem value="0.9">Very High (90%)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      <div className="space-y-4">
        {loading && (
          <Card>
            <CardContent className="p-8 text-center">
              <div className="animate-pulse">
                <div className="w-8 h-8 bg-purple-600 rounded-full mx-auto mb-4"></div>
                <p className="text-gray-600">Searching semantically...</p>
              </div>
            </CardContent>
          </Card>
        )}

        {error && (
          <Card className="border-red-200">
            <CardContent className="p-4">
              <p className="text-red-600">{error}</p>
            </CardContent>
          </Card>
        )}

        {!loading && !error && results.length === 0 && debouncedQuery && (
          <Card>
            <CardContent className="p-8 text-center">
              <p className="text-gray-600">No results found. Try a different search query.</p>
            </CardContent>
          </Card>
        )}

        {results.map((result, index) => (
          <Card 
            key={result.segment_id} 
            className="hover:shadow-lg transition-shadow cursor-pointer"
            onClick={() => navigateToSession(result.session_id, result.start_time)}
          >
            <CardContent className="p-6">
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-4">
                  <Badge variant="outline" className="flex items-center gap-1">
                    <FileText className="w-3 h-3" />
                    {result.session_id.slice(0, 12)}...
                  </Badge>
                  
                  <Badge variant="secondary" className="flex items-center gap-1">
                    <User className="w-3 h-3" />
                    {result.speaker}
                  </Badge>
                  
                  {result.start_time !== undefined && (
                    <Badge className="flex items-center gap-1 bg-gray-100 text-gray-700">
                      <Clock className="w-3 h-3" />
                      {formatTime(result.start_time)}
                    </Badge>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <span className={`text-sm font-medium ${getScoreColor(result.score)}`}>
                    {(result.score * 100).toFixed(0)}% match
                  </span>
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                </div>
              </div>

              <p className="text-gray-800 leading-relaxed">{result.text}</p>

              {result.confidence !== undefined && (
                <div className="mt-3 flex items-center gap-4 text-xs text-gray-500">
                  <span>Confidence: {(result.confidence * 100).toFixed(0)}%</span>
                  <span>•</span>
                  <span>{format(new Date(result.timestamp), 'MMM d, yyyy h:mm a')}</span>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};