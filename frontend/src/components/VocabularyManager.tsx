import React, { useState, useEffect } from 'react';
import {
  Book, Plus, Trash2, Edit3, Save, X, Search,
  Shield, ChevronDown, ChevronUp, Globe, 
  Building, Heart, DollarSign, Briefcase,
  Upload, Download, ToggleLeft, ToggleRight,
  AlertCircle, CheckCircle, Loader2, Tag
} from 'lucide-react';
import { config } from '../config';

interface VocabularyTerm {
  id: string;
  term: string;
  expansion: string;
  category?: string;
  industry?: string;
  priority: number;
  context_hints?: string[];
  case_sensitive: boolean;
  is_active: boolean;
  usage_count: number;
}

interface VocabularySet {
  id: string;
  name: string;
  description?: string;
  is_active: boolean;
  is_default: boolean;
  industry?: string;
  category?: string;
  vocab_ids?: string[];
  terms?: VocabularyTerm[];
}

export const VocabularyManager: React.FC = () => {
  const [terms, setTerms] = useState<VocabularyTerm[]>([]);
  const [sets, setSets] = useState<VocabularySet[]>([]);
  const [selectedSet, setSelectedSet] = useState<VocabularySet | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingTerm, setEditingTerm] = useState<VocabularyTerm | null>(null);
  const [isAddingTerm, setIsAddingTerm] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedIndustry, setSelectedIndustry] = useState<string>('all');
  const [showImportExport, setShowImportExport] = useState(false);

  // Categories and industries
  const categories = ['military', 'medical', 'finance', 'technology', 'legal', 'general'];
  const industries = ['defense', 'healthcare', 'finance', 'tech', 'legal', 'education'];

  const industryIcons = {
    defense: Shield,
    healthcare: Heart,
    finance: DollarSign,
    tech: Globe,
    legal: Briefcase,
    education: Book
  };

  useEffect(() => {
    fetchVocabulary();
    fetchSets();
  }, [selectedCategory, selectedIndustry]);

  const fetchVocabulary = async () => {
    try {
      const params = new URLSearchParams();
      if (selectedCategory !== 'all') params.append('category', selectedCategory);
      if (selectedIndustry !== 'all') params.append('industry', selectedIndustry);
      if (searchQuery) params.append('search', searchQuery);

      const response = await fetch(
        `${config.apiBaseUrl}/api/vocabulary/terms?${params}`,
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setTerms(data.items || []);
      }
    } catch (error) {
      console.error('Failed to fetch vocabulary:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchSets = async () => {
    try {
      const response = await fetch(
        `${config.apiBaseUrl}/api/vocabulary/sets`,
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setSets(data);
        
        // Select default set
        const defaultSet = data.find((s: VocabularySet) => s.is_default);
        if (defaultSet) {
          setSelectedSet(defaultSet);
        }
      }
    } catch (error) {
      console.error('Failed to fetch sets:', error);
    }
  };

  const saveTerm = async (term: Partial<VocabularyTerm>) => {
    try {
      const url = term.id
        ? `${config.apiBaseUrl}/api/vocabulary/terms/${term.id}`
        : `${config.apiBaseUrl}/api/vocabulary/terms`;

      const response = await fetch(url, {
        method: term.id ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify(term)
      });

      if (response.ok) {
        fetchVocabulary();
        setEditingTerm(null);
        setIsAddingTerm(false);
      }
    } catch (error) {
      console.error('Failed to save term:', error);
    }
  };

  const deleteTerm = async (id: string) => {
    if (!confirm('Are you sure you want to delete this term?')) return;

    try {
      const response = await fetch(
        `${config.apiBaseUrl}/api/vocabulary/terms/${id}`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );

      if (response.ok) {
        fetchVocabulary();
      }
    } catch (error) {
      console.error('Failed to delete term:', error);
    }
  };

  const exportVocabulary = async (format: 'json' | 'csv') => {
    try {
      const params = new URLSearchParams({ format });
      if (selectedSet) params.append('set_id', selectedSet.id);

      const response = await fetch(
        `${config.apiBaseUrl}/api/vocabulary/export?${params}`,
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `vocabulary_export.${format}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Failed to export vocabulary:', error);
    }
  };

  const filteredTerms = terms.filter(term => {
    if (searchQuery && !term.term.toLowerCase().includes(searchQuery.toLowerCase()) &&
        !term.expansion.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }
    return true;
  });

  return (
    <div className="bg-gray-950 rounded-xl border border-gray-800">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-900/30 to-pink-900/30 border-b border-gray-800 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-3">
              <Book className="w-6 h-6 text-purple-400" />
              Custom Vocabulary Manager
            </h2>
            <p className="text-gray-400 mt-1">
              Manage acronyms and specialized terms for accurate transcription
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowImportExport(!showImportExport)}
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition-colors flex items-center gap-2"
            >
              <Download className="w-4 h-4" />
              Import/Export
            </button>
            <button
              onClick={() => setIsAddingTerm(true)}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Add Term
            </button>
          </div>
        </div>
      </div>

      {/* Import/Export Panel */}
      {showImportExport && (
        <div className="bg-gray-900/50 border-b border-gray-800 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-400">
              Export vocabulary to share or backup
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => exportVocabulary('json')}
                className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
              >
                Export JSON
              </button>
              <button
                onClick={() => exportVocabulary('csv')}
                className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white rounded text-sm"
              >
                Export CSV
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="p-4 border-b border-gray-800 bg-gray-900/30">
        <div className="flex items-center gap-4">
          {/* Search */}
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search terms or expansions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-purple-500"
            />
          </div>

          {/* Category Filter */}
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
          >
            <option value="all">All Categories</option>
            {categories.map(cat => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>

          {/* Industry Filter */}
          <select
            value={selectedIndustry}
            onChange={(e) => setSelectedIndustry(e.target.value)}
            className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
          >
            <option value="all">All Industries</option>
            {industries.map(ind => (
              <option key={ind} value={ind}>{ind}</option>
            ))}
          </select>

          {/* Vocabulary Set Selector */}
          <select
            value={selectedSet?.id || ''}
            onChange={(e) => setSelectedSet(sets.find(s => s.id === e.target.value) || null)}
            className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
          >
            <option value="">All Sets</option>
            {sets.map(set => (
              <option key={set.id} value={set.id}>
                {set.name} {set.is_default && '(Default)'}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Terms List */}
      <div className="p-6">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
          </div>
        ) : filteredTerms.length === 0 ? (
          <div className="text-center py-12">
            <Book className="w-16 h-16 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400">No vocabulary terms found</p>
            <p className="text-gray-500 text-sm mt-2">Add terms to improve transcription accuracy</p>
          </div>
        ) : (
          <div className="space-y-2">
            {/* Add New Term Form */}
            {isAddingTerm && (
              <div className="bg-gray-900 rounded-lg p-4 border border-purple-500">
                <div className="grid grid-cols-3 gap-4">
                  <input
                    type="text"
                    placeholder="Term/Acronym"
                    className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                    onChange={(e) => setEditingTerm({ ...editingTerm, term: e.target.value } as VocabularyTerm)}
                  />
                  <input
                    type="text"
                    placeholder="Full Expansion"
                    className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                    onChange={(e) => setEditingTerm({ ...editingTerm, expansion: e.target.value } as VocabularyTerm)}
                  />
                  <div className="flex items-center gap-2">
                    <select
                      className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                      onChange={(e) => setEditingTerm({ ...editingTerm, category: e.target.value } as VocabularyTerm)}
                    >
                      <option value="">Category</option>
                      {categories.map(cat => (
                        <option key={cat} value={cat}>{cat}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => saveTerm(editingTerm!)}
                      className="p-2 bg-green-600 hover:bg-green-700 text-white rounded transition-colors"
                    >
                      <Save className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => {
                        setIsAddingTerm(false);
                        setEditingTerm(null);
                      }}
                      className="p-2 bg-gray-600 hover:bg-gray-700 text-white rounded transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Terms Table */}
            <div className="bg-gray-900/50 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-800/50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                      Term
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                      Expansion
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                      Category
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                      Priority
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                      Usage
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {filteredTerms.map((term) => (
                    <tr key={term.id} className="hover:bg-gray-800/30 transition-colors">
                      <td className="px-4 py-3 text-sm font-medium text-white">
                        {term.term}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-300">
                        {term.expansion}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span className="px-2 py-1 bg-purple-500/20 text-purple-300 rounded-full text-xs">
                          {term.category || 'general'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {term.priority}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {term.usage_count}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {term.is_active ? (
                          <span className="flex items-center gap-1 text-green-400">
                            <CheckCircle className="w-3 h-3" />
                            Active
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-gray-500">
                            <AlertCircle className="w-3 h-3" />
                            Inactive
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => setEditingTerm(term)}
                            className="p-1 hover:bg-gray-700 rounded transition-colors text-blue-400"
                          >
                            <Edit3 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => deleteTerm(term.id)}
                            className="p-1 hover:bg-gray-700 rounded transition-colors text-red-400"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};