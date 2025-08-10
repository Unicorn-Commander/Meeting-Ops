import React, { useState, useEffect } from 'react';
import { 
  Book, Plus, Edit, Trash2, Upload, Download, Search,
  Tag, Check, X, AlertCircle, Volume2, Settings,
  FileText, Globe, Building, Users, Zap, RefreshCw
} from 'lucide-react';
import { toast } from 'react-toastify';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface VocabularyTerm {
  id: string;
  term: string;
  pronunciation?: string;
  phonetic?: string;
  category: string;
  definition?: string;
  alternatives: string[];
  confidence: number;
  usageCount: number;
  lastUsed?: string;
  createdAt: string;
  isActive: boolean;
  priority: 'high' | 'medium' | 'low';
}

interface VocabularyCategory {
  id: string;
  name: string;
  description: string;
  termCount: number;
  color: string;
  isDefault: boolean;
}

interface ImportResult {
  imported: number;
  skipped: number;
  errors: number;
  details: string[];
}

export const CustomVocabulary: React.FC = () => {
  const [terms, setTerms] = useState<VocabularyTerm[]>([]);
  const [categories, setCategories] = useState<VocabularyCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [editingTerm, setEditingTerm] = useState<VocabularyTerm | null>(null);
  const [newTerm, setNewTerm] = useState({
    term: '',
    pronunciation: '',
    category: 'general',
    definition: '',
    alternatives: [] as string[],
    priority: 'medium' as 'high' | 'medium' | 'low'
  });
  const [importData, setImportData] = useState('');
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  useEffect(() => {
    loadVocabularyData();
  }, []);

  const loadVocabularyData = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const headers = { 'Authorization': `Bearer ${token}` };

      // Load vocabulary terms
      const termsResponse = await fetch(`${API_BASE_URL}/api/vocabulary/terms`, { headers });
      if (termsResponse.ok) {
        const termsData = await termsResponse.json();
        setTerms(termsData);
      } else {
        // Mock data for demonstration
        setTerms([
          {
            id: 'term-1',
            term: 'API Gateway',
            pronunciation: 'A-P-I Gateway',
            phonetic: '/ˌeɪ piː ˈaɪ ˈɡeɪtˌweɪ/',
            category: 'technology',
            definition: 'A server that acts as a single entry point for multiple microservices',
            alternatives: ['API Gateway', 'Gateway API', 'Service Gateway'],
            confidence: 95,
            usageCount: 47,
            lastUsed: '2025-01-09T15:30:00Z',
            createdAt: '2024-12-01T10:00:00Z',
            isActive: true,
            priority: 'high'
          },
          {
            id: 'term-2',
            term: 'Kubernetes',
            pronunciation: 'koo-ber-NEH-teez',
            phonetic: '/ˌkuːbərˈnɛtiːz/',
            category: 'technology',
            definition: 'Open-source container orchestration platform',
            alternatives: ['K8s', 'Kubernetes', 'Kube'],
            confidence: 98,
            usageCount: 23,
            lastUsed: '2025-01-08T11:20:00Z',
            createdAt: '2024-11-15T09:30:00Z',
            isActive: true,
            priority: 'high'
          },
          {
            id: 'term-3',
            term: 'Syncify',
            pronunciation: 'SINK-ify',
            category: 'company',
            definition: 'Our proprietary data synchronization product',
            alternatives: ['Syncify', 'Sync-ify', 'SynciFy'],
            confidence: 92,
            usageCount: 156,
            lastUsed: '2025-01-09T16:45:00Z',
            createdAt: '2024-10-01T14:00:00Z',
            isActive: true,
            priority: 'high'
          },
          {
            id: 'term-4',
            term: 'CAGR',
            pronunciation: 'KAY-ger',
            phonetic: '/ˈkeɪɡər/',
            category: 'finance',
            definition: 'Compound Annual Growth Rate',
            alternatives: ['CAGR', 'Compound Annual Growth Rate'],
            confidence: 88,
            usageCount: 12,
            lastUsed: '2025-01-05T09:15:00Z',
            createdAt: '2024-12-10T16:20:00Z',
            isActive: true,
            priority: 'medium'
          }
        ]);
      }

      // Load categories
      const categoriesResponse = await fetch(`${API_BASE_URL}/api/vocabulary/categories`, { headers });
      if (categoriesResponse.ok) {
        const categoriesData = await categoriesResponse.json();
        setCategories(categoriesData);
      } else {
        // Mock data
        setCategories([
          {
            id: 'general',
            name: 'General',
            description: 'General business terms',
            termCount: 0,
            color: 'bg-gray-500',
            isDefault: true
          },
          {
            id: 'technology',
            name: 'Technology',
            description: 'Technical terms and acronyms',
            termCount: 2,
            color: 'bg-blue-500',
            isDefault: false
          },
          {
            id: 'company',
            name: 'Company Terms',
            description: 'Company-specific terms and products',
            termCount: 1,
            color: 'bg-purple-500',
            isDefault: false
          },
          {
            id: 'finance',
            name: 'Finance',
            description: 'Financial and business metrics',
            termCount: 1,
            color: 'bg-green-500',
            isDefault: false
          }
        ]);
      }
    } catch (error) {
      console.error('Failed to load vocabulary data:', error);
    } finally {
      setLoading(false);
    }
  };

  const createTerm = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const termData = {
        ...newTerm,
        alternatives: newTerm.alternatives.length > 0 ? newTerm.alternatives : [newTerm.term]
      };

      const response = await fetch(`${API_BASE_URL}/api/vocabulary/terms`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(termData)
      });

      if (response.ok) {
        const createdTerm = await response.json();
        setTerms([createdTerm, ...terms]);
        setShowAddModal(false);
        resetNewTerm();
        toast.success('Vocabulary term added successfully');
      } else {
        // Demo mode
        const mockTerm: VocabularyTerm = {
          id: `term-${Date.now()}`,
          ...termData,
          confidence: 85,
          usageCount: 0,
          createdAt: new Date().toISOString(),
          isActive: true
        };
        setTerms([mockTerm, ...terms]);
        setShowAddModal(false);
        resetNewTerm();
        toast.success('Vocabulary term added (demo mode)');
      }
    } catch (error) {
      console.error('Failed to create term:', error);
      toast.error('Failed to create vocabulary term');
    }
  };

  const updateTerm = async (term: VocabularyTerm) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/vocabulary/terms/${term.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(term)
      });

      if (response.ok) {
        setTerms(terms.map(t => t.id === term.id ? term : t));
        setEditingTerm(null);
        toast.success('Term updated successfully');
      } else {
        // Demo mode
        setTerms(terms.map(t => t.id === term.id ? term : t));
        setEditingTerm(null);
        toast.success('Term updated (demo mode)');
      }
    } catch (error) {
      console.error('Failed to update term:', error);
      toast.error('Failed to update term');
    }
  };

  const deleteTerm = async (termId: string) => {
    if (!confirm('Are you sure you want to delete this term?')) return;

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/vocabulary/terms/${termId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        setTerms(terms.filter(t => t.id !== termId));
        toast.success('Term deleted successfully');
      } else {
        // Demo mode
        setTerms(terms.filter(t => t.id !== termId));
        toast.success('Term deleted (demo mode)');
      }
    } catch (error) {
      console.error('Failed to delete term:', error);
      toast.error('Failed to delete term');
    }
  };

  const toggleTermStatus = async (termId: string) => {
    const term = terms.find(t => t.id === termId);
    if (!term) return;

    const updatedTerm = { ...term, isActive: !term.isActive };
    await updateTerm(updatedTerm);
  };

  const importVocabulary = async () => {
    try {
      const lines = importData.trim().split('\n').filter(line => line.trim());
      const imported: VocabularyTerm[] = [];
      const errors: string[] = [];

      for (const line of lines) {
        try {
          const parts = line.split(',').map(p => p.trim());
          if (parts.length < 2) {
            errors.push(`Invalid format: ${line}`);
            continue;
          }

          const [term, pronunciation, category, definition] = parts;
          const mockTerm: VocabularyTerm = {
            id: `imported-${Date.now()}-${Math.random()}`,
            term,
            pronunciation: pronunciation || '',
            category: category || 'general',
            definition: definition || '',
            alternatives: [term],
            confidence: 80,
            usageCount: 0,
            createdAt: new Date().toISOString(),
            isActive: true,
            priority: 'medium'
          };
          imported.push(mockTerm);
        } catch (error) {
          errors.push(`Error processing: ${line}`);
        }
      }

      setTerms([...imported, ...terms]);
      setImportResult({
        imported: imported.length,
        skipped: 0,
        errors: errors.length,
        details: errors
      });

      toast.success(`Imported ${imported.length} terms successfully`);
    } catch (error) {
      console.error('Import failed:', error);
      toast.error('Import failed');
    }
  };

  const exportVocabulary = () => {
    const csvContent = terms.map(term => 
      `${term.term},${term.pronunciation || ''},${term.category},${term.definition || ''}`
    ).join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'vocabulary_export.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const resetNewTerm = () => {
    setNewTerm({
      term: '',
      pronunciation: '',
      category: 'general',
      definition: '',
      alternatives: [],
      priority: 'medium'
    });
  };

  const filteredTerms = terms.filter(term => {
    const matchesSearch = term.term.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         term.definition?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         term.alternatives.some(alt => alt.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesCategory = selectedCategory === 'all' || term.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return 'text-red-400 bg-red-400/20';
      case 'medium': return 'text-yellow-400 bg-yellow-400/20';
      case 'low': return 'text-green-400 bg-green-400/20';
      default: return 'text-gray-400 bg-gray-400/20';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold flex items-center">
            <Book className="w-8 h-8 text-blue-400 mr-3" />
            Custom Vocabulary
          </h2>
          <p className="text-gray-400 mt-1">
            Manage industry terms, company jargon, and acronyms for better transcription accuracy
          </p>
        </div>
        
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setShowImportModal(true)}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors flex items-center"
          >
            <Upload className="w-4 h-4 mr-2" />
            Import
          </button>
          <button
            onClick={exportVocabulary}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors flex items-center"
          >
            <Download className="w-4 h-4 mr-2" />
            Export
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center"
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Term
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm">Total Terms</p>
              <p className="text-2xl font-bold">{terms.length}</p>
            </div>
            <Book className="w-8 h-8 text-blue-400" />
          </div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm">Active Terms</p>
              <p className="text-2xl font-bold">{terms.filter(t => t.isActive).length}</p>
            </div>
            <Check className="w-8 h-8 text-green-400" />
          </div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm">Categories</p>
              <p className="text-2xl font-bold">{categories.length}</p>
            </div>
            <Tag className="w-8 h-8 text-purple-400" />
          </div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm">Avg Confidence</p>
              <p className="text-2xl font-bold">
                {Math.round(terms.reduce((sum, t) => sum + t.confidence, 0) / terms.length)}%
              </p>
            </div>
            <Zap className="w-8 h-8 text-yellow-400" />
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center space-x-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search vocabulary terms..."
            className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
          />
        </div>
        
        <select
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          className="px-4 py-2 bg-gray-800 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
        >
          <option value="all">All Categories</option>
          {categories.map(category => (
            <option key={category.id} value={category.id}>
              {category.name} ({category.termCount})
            </option>
          ))}
        </select>
        
        <button
          onClick={loadVocabularyData}
          className="p-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Terms List */}
      <div className="space-y-4">
        {filteredTerms.map(term => (
          <div key={term.id} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center space-x-3 mb-2">
                  <h3 className="text-xl font-semibold">{term.term}</h3>
                  <div className={`px-2 py-1 rounded-full text-xs font-medium ${getPriorityColor(term.priority)}`}>
                    {term.priority}
                  </div>
                  <div className={`w-3 h-3 rounded-full ${term.isActive ? 'bg-green-400' : 'bg-gray-400'}`} />
                </div>
                
                {term.pronunciation && (
                  <div className="flex items-center space-x-2 mb-2">
                    <Volume2 className="w-4 h-4 text-gray-400" />
                    <span className="text-sm text-gray-300 font-mono">{term.pronunciation}</span>
                    {term.phonetic && (
                      <span className="text-sm text-gray-400">{term.phonetic}</span>
                    )}
                  </div>
                )}
                
                {term.definition && (
                  <p className="text-gray-300 mb-2">{term.definition}</p>
                )}
                
                <div className="flex items-center space-x-4 text-sm text-gray-400">
                  <span className="flex items-center">
                    <Tag className="w-4 h-4 mr-1" />
                    {categories.find(c => c.id === term.category)?.name || term.category}
                  </span>
                  <span>Used {term.usageCount} times</span>
                  <span>Confidence: {term.confidence}%</span>
                  {term.lastUsed && (
                    <span>Last used: {new Date(term.lastUsed).toLocaleDateString()}</span>
                  )}
                </div>
                
                {term.alternatives.length > 1 && (
                  <div className="mt-3">
                    <label className="text-sm text-gray-400">Alternatives:</label>
                    <div className="flex flex-wrap gap-2 mt-1">
                      {term.alternatives.slice(1).map((alt, index) => (
                        <span key={index} className="px-2 py-1 bg-gray-700 rounded text-sm">
                          {alt}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => toggleTermStatus(term.id)}
                  className={`p-2 rounded transition-colors ${
                    term.isActive 
                      ? 'text-green-400 hover:bg-green-400/20' 
                      : 'text-gray-400 hover:bg-gray-700'
                  }`}
                  title={term.isActive ? 'Disable term' : 'Enable term'}
                >
                  {term.isActive ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                </button>
                <button
                  onClick={() => setEditingTerm(term)}
                  className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
                  title="Edit term"
                >
                  <Edit className="w-4 h-4" />
                </button>
                <button
                  onClick={() => deleteTerm(term.id)}
                  className="p-2 text-red-400 hover:bg-red-400/20 rounded transition-colors"
                  title="Delete term"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        ))}
        
        {filteredTerms.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            <Book className="w-16 h-16 mx-auto mb-4 opacity-50" />
            <p>No vocabulary terms found</p>
            <p className="text-sm mt-2">Add your first term to improve transcription accuracy</p>
          </div>
        )}
      </div>

      {/* Add/Edit Term Modal */}
      {(showAddModal || editingTerm) && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-2xl m-4">
            <h3 className="text-xl font-bold mb-4">
              {editingTerm ? 'Edit Term' : 'Add New Term'}
            </h3>
            
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Term *</label>
                  <input
                    type="text"
                    value={editingTerm ? editingTerm.term : newTerm.term}
                    onChange={(e) => {
                      if (editingTerm) {
                        setEditingTerm({...editingTerm, term: e.target.value});
                      } else {
                        setNewTerm({...newTerm, term: e.target.value});
                      }
                    }}
                    placeholder="API Gateway"
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">Pronunciation</label>
                  <input
                    type="text"
                    value={editingTerm ? editingTerm.pronunciation || '' : newTerm.pronunciation}
                    onChange={(e) => {
                      if (editingTerm) {
                        setEditingTerm({...editingTerm, pronunciation: e.target.value});
                      } else {
                        setNewTerm({...newTerm, pronunciation: e.target.value});
                      }
                    }}
                    placeholder="A-P-I Gateway"
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Category</label>
                  <select
                    value={editingTerm ? editingTerm.category : newTerm.category}
                    onChange={(e) => {
                      if (editingTerm) {
                        setEditingTerm({...editingTerm, category: e.target.value});
                      } else {
                        setNewTerm({...newTerm, category: e.target.value});
                      }
                    }}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  >
                    {categories.map(category => (
                      <option key={category.id} value={category.id}>{category.name}</option>
                    ))}
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">Priority</label>
                  <select
                    value={editingTerm ? editingTerm.priority : newTerm.priority}
                    onChange={(e) => {
                      if (editingTerm) {
                        setEditingTerm({...editingTerm, priority: e.target.value as any});
                      } else {
                        setNewTerm({...newTerm, priority: e.target.value as any});
                      }
                    }}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  >
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">Definition</label>
                <textarea
                  value={editingTerm ? editingTerm.definition || '' : newTerm.definition}
                  onChange={(e) => {
                    if (editingTerm) {
                      setEditingTerm({...editingTerm, definition: e.target.value});
                    } else {
                      setNewTerm({...newTerm, definition: e.target.value});
                    }
                  }}
                  placeholder="Brief definition or description"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  rows={2}
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">Alternative Spellings (comma-separated)</label>
                <input
                  type="text"
                  value={editingTerm ? editingTerm.alternatives.join(', ') : newTerm.alternatives.join(', ')}
                  onChange={(e) => {
                    const alternatives = e.target.value.split(',').map(s => s.trim()).filter(s => s);
                    if (editingTerm) {
                      setEditingTerm({...editingTerm, alternatives});
                    } else {
                      setNewTerm({...newTerm, alternatives});
                    }
                  }}
                  placeholder="K8s, Kubernetes, Kube"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                />
              </div>
            </div>
            
            <div className="flex items-center justify-end space-x-4 mt-6">
              <button
                onClick={() => {
                  setShowAddModal(false);
                  setEditingTerm(null);
                  resetNewTerm();
                }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={editingTerm ? () => updateTerm(editingTerm) : createTerm}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors"
              >
                {editingTerm ? 'Update' : 'Add'} Term
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-2xl m-4">
            <h3 className="text-xl font-bold mb-4">Import Vocabulary</h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">CSV Data</label>
                <textarea
                  value={importData}
                  onChange={(e) => setImportData(e.target.value)}
                  placeholder="term, pronunciation, category, definition&#10;API Gateway, A-P-I Gateway, technology, Server that acts as entry point&#10;Kubernetes, koo-ber-NEH-teez, technology, Container orchestration platform"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  rows={6}
                />
                <p className="text-xs text-gray-400 mt-1">
                  Format: term, pronunciation, category, definition (one per line)
                </p>
              </div>
              
              {importResult && (
                <div className="bg-gray-700 rounded-lg p-4">
                  <h4 className="font-medium mb-2">Import Results:</h4>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <span className="text-green-400">Imported: {importResult.imported}</span>
                    </div>
                    <div>
                      <span className="text-yellow-400">Skipped: {importResult.skipped}</span>
                    </div>
                    <div>
                      <span className="text-red-400">Errors: {importResult.errors}</span>
                    </div>
                  </div>
                  {importResult.details.length > 0 && (
                    <div className="mt-2">
                      <p className="text-xs text-gray-400">Error details:</p>
                      <ul className="text-xs text-red-400 mt-1">
                        {importResult.details.slice(0, 5).map((detail, index) => (
                          <li key={index}>• {detail}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
            
            <div className="flex items-center justify-end space-x-4 mt-6">
              <button
                onClick={() => {
                  setShowImportModal(false);
                  setImportData('');
                  setImportResult(null);
                }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={importVocabulary}
                disabled={!importData.trim()}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded-lg transition-colors"
              >
                Import Terms
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};