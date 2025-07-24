import React, { useState, useEffect, useCallback } from 'react';
import { Search, Filter, BarChart3, Network, Clock, User, FileText, Lightbulb } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Badge } from './ui/badge';

interface SearchResult {
  session_id: string;
  text?: string;
  chunk_id?: string;
  node_id?: string;
  node_type?: string;
  name?: string;
  speaker_id?: string;
  start_time?: number;
  end_time?: number;
  similarity?: number;
  score: number;
  search_method?: string;
  search_methods?: string[];
  snippet?: string;
  properties?: any;
}

interface SearchResponse {
  results?: SearchResult[];
  semantic?: SearchResult[];
  keyword?: SearchResult[];
  graph?: {
    results: SearchResult[];
    context: string;
    nodes: any[];
    edges: any[];
  };
  combined?: SearchResult[];
  query: string;
  search_type: string;
  accessible_sessions?: number;
  total_sessions?: number;
}

interface SearchStats {
  accessible_sessions: number;
  indexed_sessions: number;
  total_chunks: number;
  graph_nodes: number;
  graph_edges: number;
}

export const UnifiedSearchInterface: React.FC = () => {
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState<'hybrid' | 'semantic' | 'keyword' | 'graph'>('hybrid');
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<SearchStats | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [selectedSpeakers, setSelectedSpeakers] = useState<string[]>([]);

  // Load stats on mount
  useEffect(() => {
    loadStats();
  }, []);

  // Load suggestions when query changes
  useEffect(() => {
    if (query.length >= 2) {
      loadSuggestions();
    } else {
      setSuggestions([]);
    }
  }, [query]);

  const loadStats = async () => {
    try {
      const response = await fetch('/api/search/stats', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (error) {
      console.error('Failed to load stats:', error);
    }
  };

  const loadSuggestions = useCallback(async () => {
    if (query.length < 2) return;

    try {
      const response = await fetch(`/api/search/suggestions?q=${encodeURIComponent(query)}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setSuggestions(data.suggestions || []);
      }
    } catch (error) {
      console.error('Failed to load suggestions:', error);
    }
  }, [query]);

  const handleSearch = async () => {
    if (!query.trim()) return;

    setLoading(true);
    try {
      const params = new URLSearchParams({
        q: query,
        search_type: searchType,
        limit: '20'
      });

      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);
      selectedSpeakers.forEach(speaker => params.append('speakers', speaker));

      const response = await fetch(`/api/search/?${params}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setResults(data);
      } else {
        console.error('Search failed:', response.statusText);
      }
    } catch (error) {
      console.error('Search error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const formatTime = (timestamp: number) => {
    const minutes = Math.floor(timestamp / 60);
    const seconds = Math.floor(timestamp % 60);
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  const getSearchMethodIcon = (method: string) => {
    switch (method) {
      case 'semantic': return <Lightbulb className="w-4 h-4" />;
      case 'keyword': return <Search className="w-4 h-4" />;
      case 'graph': return <Network className="w-4 h-4" />;
      default: return <FileText className="w-4 h-4" />;
    }
  };

  const getSearchMethodColor = (method: string) => {
    switch (method) {
      case 'semantic': return 'bg-blue-100 text-blue-800';
      case 'keyword': return 'bg-green-100 text-green-800';
      case 'graph': return 'bg-purple-100 text-purple-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const renderResults = () => {
    if (!results) return null;

    const displayResults = results.combined || results.results || 
                           results.semantic || results.keyword || 
                           results.graph?.results || [];

    if (displayResults.length === 0) {
      return (
        <Card className="bg-gray-50">
          <CardContent className="p-6 text-center">
            <Search className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-600">No results found for "{results.query}"</p>
            <p className="text-sm text-gray-500 mt-2">
              Try adjusting your search terms or search type
            </p>
          </CardContent>
        </Card>
      );
    }

    return (
      <div className="space-y-4">
        {displayResults.map((result, index) => (
          <Card key={index} className="hover:shadow-md transition-shadow">
            <CardContent className="p-4">
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  {result.search_methods ? (
                    result.search_methods.map((method, i) => (
                      <Badge 
                        key={i}
                        variant="outline" 
                        className={`text-xs ${getSearchMethodColor(method)}`}
                      >
                        {getSearchMethodIcon(method)}
                        <span className="ml-1">{method}</span>
                      </Badge>
                    ))
                  ) : result.search_method && (
                    <Badge 
                      variant="outline" 
                      className={`text-xs ${getSearchMethodColor(result.search_method)}`}
                    >
                      {getSearchMethodIcon(result.search_method)}
                      <span className="ml-1">{result.search_method}</span>
                    </Badge>
                  )}
                  
                  <Badge variant="secondary" className="text-xs">
                    Score: {(result.score * 100).toFixed(1)}%
                  </Badge>
                </div>

                {result.session_id && (
                  <Badge variant="outline" className="text-xs">
                    Session: {result.session_id.slice(-8)}
                  </Badge>
                )}
              </div>

              <div className="mb-2">
                {result.node_type && (
                  <div className="flex items-center gap-2 mb-2">
                    <Badge className="text-xs capitalize">
                      {result.node_type.replace('_', ' ')}
                    </Badge>
                    {result.name && (
                      <span className="font-medium">{result.name}</span>
                    )}
                  </div>
                )}

                <p className="text-gray-800">
                  {result.snippet ? (
                    <span dangerouslySetInnerHTML={{ __html: result.snippet }} />
                  ) : (
                    result.text || result.name || 'No content available'
                  )}
                </p>
              </div>

              <div className="flex items-center gap-4 text-sm text-gray-500">
                {result.speaker_id && (
                  <div className="flex items-center gap-1">
                    <User className="w-4 h-4" />
                    <span>{result.speaker_id}</span>
                  </div>
                )}

                {result.start_time !== undefined && (
                  <div className="flex items-center gap-1">
                    <Clock className="w-4 h-4" />
                    <span>{formatTime(result.start_time)}</span>
                    {result.end_time && (
                      <span> - {formatTime(result.end_time)}</span>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header with stats */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Meeting Intelligence Search</h2>
        {stats && (
          <div className="flex items-center gap-4 text-sm text-gray-300">
            <span>{stats.indexed_sessions} / {stats.accessible_sessions} sessions indexed</span>
            <span>{stats.total_chunks} chunks</span>
            <span>{stats.graph_nodes} entities</span>
          </div>
        )}
      </div>

      {/* Search interface */}
      <Card className="bg-gray-800 border-gray-700">
        <CardContent className="p-6">
          <div className="space-y-4">
            {/* Main search bar */}
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Search meetings, decisions, topics, people..."
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />

                {/* Suggestions dropdown */}
                {suggestions.length > 0 && (
                  <div className="absolute top-full left-0 right-0 mt-1 bg-gray-700 border border-gray-600 rounded-lg shadow-lg z-10">
                    {suggestions.map((suggestion, index) => (
                      <button
                        key={index}
                        onClick={() => setQuery(suggestion)}
                        className="block w-full px-4 py-2 text-left text-white hover:bg-gray-600 first:rounded-t-lg last:rounded-b-lg"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <select
                value={searchType}
                onChange={(e) => setSearchType(e.target.value as any)}
                className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="hybrid">Hybrid</option>
                <option value="semantic">Semantic</option>
                <option value="keyword">Keyword</option>
                <option value="graph">Graph</option>
              </select>

              <button
                onClick={() => setShowFilters(!showFilters)}
                className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white hover:bg-gray-600 transition-colors"
              >
                <Filter className="w-4 h-4" />
              </button>

              <button
                onClick={handleSearch}
                disabled={loading || !query.trim()}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? 'Searching...' : 'Search'}
              </button>
            </div>

            {/* Filters */}
            {showFilters && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-gray-600">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    From Date
                  </label>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    To Date
                  </label>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Speakers
                  </label>
                  <input
                    type="text"
                    placeholder="Enter speaker names..."
                    onChange={(e) => setSelectedSpeakers(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Search type explanation */}
      <Card className="bg-gray-800 border-gray-700">
        <CardContent className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-sm">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-blue-400" />
              <div>
                <div className="font-medium text-white">Hybrid</div>
                <div className="text-gray-400">Combines all methods</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Lightbulb className="w-4 h-4 text-blue-400" />
              <div>
                <div className="font-medium text-white">Semantic</div>
                <div className="text-gray-400">AI-powered similarity</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Search className="w-4 h-4 text-green-400" />
              <div>
                <div className="font-medium text-white">Keyword</div>
                <div className="text-gray-400">Traditional text search</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Network className="w-4 h-4 text-purple-400" />
              <div>
                <div className="font-medium text-white">Graph</div>
                <div className="text-gray-400">Relationship-based</div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {results && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-white">
              Search Results for "{results.query}"
            </h3>
            <div className="text-sm text-gray-400">
              {results.accessible_sessions && (
                <span>Searching {results.accessible_sessions} accessible sessions</span>
              )}
            </div>
          </div>

          {/* Graph context for graph search */}
          {results.graph?.context && searchType === 'graph' && (
            <Card className="bg-blue-50 border-blue-200 mb-4">
              <CardContent className="p-4">
                <h4 className="font-medium text-blue-800 mb-2">Knowledge Graph Context</h4>
                <p className="text-blue-700 text-sm whitespace-pre-line">
                  {results.graph.context}
                </p>
              </CardContent>
            </Card>
          )}

          {renderResults()}
        </div>
      )}
    </div>
  );
};