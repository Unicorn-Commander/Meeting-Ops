import React, { useState, useEffect, useRef } from 'react';
import {
  Plus, Trash2, Edit2, Save, X, Upload, Download,
  Search, Filter, ToggleLeft, ToggleRight, Book,
  Shield, Heart, DollarSign, Cpu, Check, AlertCircle
} from 'lucide-react';

interface VocabularyTerm {
  id: string;
  term: string;
  expansion: string;
  category: string;
  priority: number;
  contextHints: string[];
  isActive: boolean;
}

interface VocabularySet {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  termCount: number;
  isActive: boolean;
  terms: VocabularyTerm[];
}

const defaultVocabularySets: VocabularySet[] = [
  {
    id: 'defense',
    name: 'Defense & Military',
    description: 'Military acronyms and defense terminology',
    icon: <Shield className="w-5 h-5" />,
    termCount: 150,
    isActive: false,
    terms: [
      { id: 'd1', term: 'CONOPS', expansion: 'Concept of Operations', category: 'defense', priority: 10, contextHints: ['planning', 'strategy'], isActive: true },
      { id: 'd2', term: 'ROE', expansion: 'Rules of Engagement', category: 'defense', priority: 10, contextHints: ['combat', 'engagement'], isActive: true },
      { id: 'd3', term: 'ISR', expansion: 'Intelligence, Surveillance, and Reconnaissance', category: 'defense', priority: 9, contextHints: ['intel', 'recon'], isActive: true },
      { id: 'd4', term: 'C4ISR', expansion: 'Command, Control, Communications, Computers, Intelligence, Surveillance, and Reconnaissance', category: 'defense', priority: 8, contextHints: ['command', 'systems'], isActive: true },
      { id: 'd5', term: 'SIGINT', expansion: 'Signals Intelligence', category: 'defense', priority: 9, contextHints: ['signals', 'intelligence'], isActive: true },
    ]
  },
  {
    id: 'medical',
    name: 'Medical & Healthcare',
    description: 'Medical terminology and healthcare acronyms',
    icon: <Heart className="w-5 h-5" />,
    termCount: 200,
    isActive: false,
    terms: [
      { id: 'm1', term: 'EHR', expansion: 'Electronic Health Record', category: 'medical', priority: 10, contextHints: ['record', 'patient'], isActive: true },
      { id: 'm2', term: 'HIPAA', expansion: 'Health Insurance Portability and Accountability Act', category: 'medical', priority: 10, contextHints: ['privacy', 'compliance'], isActive: true },
      { id: 'm3', term: 'MRI', expansion: 'Magnetic Resonance Imaging', category: 'medical', priority: 9, contextHints: ['scan', 'imaging'], isActive: true },
      { id: 'm4', term: 'ICU', expansion: 'Intensive Care Unit', category: 'medical', priority: 9, contextHints: ['critical', 'care'], isActive: true },
      { id: 'm5', term: 'EMR', expansion: 'Electronic Medical Record', category: 'medical', priority: 8, contextHints: ['medical', 'record'], isActive: true },
    ]
  },
  {
    id: 'finance',
    name: 'Finance & Banking',
    description: 'Financial terms and banking acronyms',
    icon: <DollarSign className="w-5 h-5" />,
    termCount: 175,
    isActive: false,
    terms: [
      { id: 'f1', term: 'ROI', expansion: 'Return on Investment', category: 'finance', priority: 10, contextHints: ['return', 'investment'], isActive: true },
      { id: 'f2', term: 'P&L', expansion: 'Profit and Loss', category: 'finance', priority: 10, contextHints: ['profit', 'loss'], isActive: true },
      { id: 'f3', term: 'EBITDA', expansion: 'Earnings Before Interest, Taxes, Depreciation, and Amortization', category: 'finance', priority: 9, contextHints: ['earnings', 'profit'], isActive: true },
      { id: 'f4', term: 'IPO', expansion: 'Initial Public Offering', category: 'finance', priority: 8, contextHints: ['public', 'offering'], isActive: true },
      { id: 'f5', term: 'KPI', expansion: 'Key Performance Indicator', category: 'finance', priority: 9, contextHints: ['performance', 'metric'], isActive: true },
    ]
  },
  {
    id: 'technology',
    name: 'Technology & IT',
    description: 'Technical terms and IT acronyms',
    icon: <Cpu className="w-5 h-5" />,
    termCount: 250,
    isActive: false,
    terms: [
      { id: 't1', term: 'API', expansion: 'Application Programming Interface', category: 'technology', priority: 10, contextHints: ['interface', 'programming'], isActive: true },
      { id: 't2', term: 'CI/CD', expansion: 'Continuous Integration/Continuous Deployment', category: 'technology', priority: 9, contextHints: ['deployment', 'pipeline'], isActive: true },
      { id: 't3', term: 'K8s', expansion: 'Kubernetes', category: 'technology', priority: 8, contextHints: ['container', 'orchestration'], isActive: true },
      { id: 't4', term: 'ML', expansion: 'Machine Learning', category: 'technology', priority: 9, contextHints: ['learning', 'model'], isActive: true },
      { id: 't5', term: 'SaaS', expansion: 'Software as a Service', category: 'technology', priority: 8, contextHints: ['software', 'service'], isActive: true },
    ]
  }
];

export const VocabularySettings: React.FC = () => {
  const [vocabularySets, setVocabularySets] = useState<VocabularySet[]>(defaultVocabularySets);
  const [customTerms, setCustomTerms] = useState<VocabularyTerm[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [editingTerm, setEditingTerm] = useState<string | null>(null);
  const [newTerm, setNewTerm] = useState<Partial<VocabularyTerm>>({});
  const [showAddForm, setShowAddForm] = useState(false);
  const [testText, setTestText] = useState('');
  const [expandedText, setExpandedText] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Load saved vocabulary settings from localStorage
    const saved = localStorage.getItem('vocabularySettings');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.sets) setVocabularySets(parsed.sets);
        if (parsed.custom) setCustomTerms(parsed.custom);
      } catch (e) {
        console.error('Failed to load vocabulary settings:', e);
      }
    }
  }, []);

  const saveSettings = () => {
    localStorage.setItem('vocabularySettings', JSON.stringify({
      sets: vocabularySets,
      custom: customTerms
    }));
  };

  const toggleSet = (setId: string) => {
    setVocabularySets(prev => {
      const updated = prev.map(set =>
        set.id === setId ? { ...set, isActive: !set.isActive } : set
      );
      localStorage.setItem('vocabularySettings', JSON.stringify({
        sets: updated,
        custom: customTerms
      }));
      return updated;
    });
  };

  const addTerm = () => {
    if (!newTerm.term || !newTerm.expansion) return;
    
    const term: VocabularyTerm = {
      id: `custom-${Date.now()}`,
      term: newTerm.term,
      expansion: newTerm.expansion,
      category: newTerm.category || 'custom',
      priority: newTerm.priority || 5,
      contextHints: newTerm.contextHints || [],
      isActive: true
    };
    
    setCustomTerms(prev => [...prev, term]);
    setNewTerm({});
    setShowAddForm(false);
    saveSettings();
  };

  const updateTerm = (id: string, updates: Partial<VocabularyTerm>) => {
    setCustomTerms(prev => {
      const updated = prev.map(term =>
        term.id === id ? { ...term, ...updates } : term
      );
      localStorage.setItem('vocabularySettings', JSON.stringify({
        sets: vocabularySets,
        custom: updated
      }));
      return updated;
    });
    setEditingTerm(null);
  };

  const deleteTerm = (id: string) => {
    setCustomTerms(prev => {
      const updated = prev.filter(term => term.id !== id);
      localStorage.setItem('vocabularySettings', JSON.stringify({
        sets: vocabularySets,
        custom: updated
      }));
      return updated;
    });
  };

  const handleCSVImport = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const lines = text.split('\n').filter(line => line.trim());
      
      // Skip header if present
      const dataLines = lines[0].toLowerCase().includes('term') ? lines.slice(1) : lines;
      
      const imported: VocabularyTerm[] = dataLines.map((line, idx) => {
        const [term, expansion, category = 'custom', priority = '5'] = line.split(',').map(s => s.trim());
        return {
          id: `import-${Date.now()}-${idx}`,
          term,
          expansion,
          category,
          priority: parseInt(priority) || 5,
          contextHints: [],
          isActive: true
        };
      }).filter(t => t.term && t.expansion);
      
      setCustomTerms(prev => [...prev, ...imported]);
      saveSettings();
    };
    reader.readAsText(file);
    
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const exportToCSV = () => {
    const allTerms = [
      ...customTerms,
      ...vocabularySets.filter(s => s.isActive).flatMap(s => s.terms)
    ];
    
    const csv = [
      'Term,Expansion,Category,Priority',
      ...allTerms.map(t => `${t.term},${t.expansion},${t.category},${t.priority}`)
    ].join('\n');
    
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'vocabulary.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const testExpansion = () => {
    let expanded = testText;
    const allActiveTerms = [
      ...customTerms.filter(t => t.isActive),
      ...vocabularySets.filter(s => s.isActive).flatMap(s => s.terms.filter(t => t.isActive))
    ];
    
    // Sort by priority (higher priority first)
    allActiveTerms.sort((a, b) => b.priority - a.priority);
    
    allActiveTerms.forEach(term => {
      const regex = new RegExp(`\\b${term.term}\\b`, 'gi');
      expanded = expanded.replace(regex, `${term.term} (${term.expansion})`);
    });
    
    setExpandedText(expanded);
  };

  const getAllTerms = () => {
    const terms = [
      ...customTerms,
      ...vocabularySets.flatMap(set => set.terms.map(t => ({ ...t, setName: set.name })))
    ];
    
    return terms.filter(term => {
      const matchesSearch = !searchTerm || 
        term.term.toLowerCase().includes(searchTerm.toLowerCase()) ||
        term.expansion.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesCategory = selectedCategory === 'all' || term.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  };

  return (
    <div className="max-w-7xl mx-auto p-6">
      <div className="bg-white rounded-lg shadow-sm">
        {/* Header */}
        <div className="p-6 border-b">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Book className="w-6 h-6 text-purple-600" />
            Vocabulary Management
          </h1>
          <p className="text-gray-600 mt-2">
            Manage custom terms, acronyms, and industry-specific vocabulary for accurate transcription
          </p>
        </div>

        {/* Vocabulary Sets */}
        <div className="p-6 border-b">
          <h2 className="text-lg font-semibold mb-4">Pre-loaded Vocabulary Sets</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {vocabularySets.map(set => (
              <div
                key={set.id}
                className={`p-4 rounded-lg border-2 transition-all ${
                  set.isActive ? 'border-purple-500 bg-purple-50' : 'border-gray-200'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className={`p-2 rounded-lg ${set.isActive ? 'bg-purple-100' : 'bg-gray-100'}`}>
                    {set.icon}
                  </div>
                  <button
                    onClick={() => toggleSet(set.id)}
                    className="p-1"
                  >
                    {set.isActive ? (
                      <ToggleRight className="w-8 h-8 text-purple-600" />
                    ) : (
                      <ToggleLeft className="w-8 h-8 text-gray-400" />
                    )}
                  </button>
                </div>
                <h3 className="font-semibold text-gray-900">{set.name}</h3>
                <p className="text-sm text-gray-600 mt-1">{set.description}</p>
                <div className="mt-3 flex items-center justify-between">
                  <span className="text-sm text-gray-500">{set.termCount} terms</span>
                  {set.isActive && (
                    <span className="flex items-center gap-1 text-sm text-green-600">
                      <Check className="w-4 h-4" />
                      Active
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Custom Terms Management */}
        <div className="p-6 border-b">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Custom Terms</h2>
            <div className="flex gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={handleCSVImport}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 flex items-center gap-2"
              >
                <Upload className="w-4 h-4" />
                Import CSV
              </button>
              <button
                onClick={exportToCSV}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </button>
              <button
                onClick={() => setShowAddForm(true)}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                Add Term
              </button>
            </div>
          </div>

          {/* Search and Filter */}
          <div className="flex gap-4 mb-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search terms..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="all">All Categories</option>
              <option value="custom">Custom</option>
              <option value="defense">Defense</option>
              <option value="medical">Medical</option>
              <option value="finance">Finance</option>
              <option value="technology">Technology</option>
            </select>
          </div>

          {/* Add Term Form */}
          {showAddForm && (
            <div className="mb-4 p-4 bg-gray-50 rounded-lg">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <input
                  type="text"
                  placeholder="Term/Acronym"
                  value={newTerm.term || ''}
                  onChange={(e) => setNewTerm({ ...newTerm, term: e.target.value })}
                  className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <input
                  type="text"
                  placeholder="Full Expansion"
                  value={newTerm.expansion || ''}
                  onChange={(e) => setNewTerm({ ...newTerm, expansion: e.target.value })}
                  className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <select
                  value={newTerm.category || 'custom'}
                  onChange={(e) => setNewTerm({ ...newTerm, category: e.target.value })}
                  className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  <option value="custom">Custom</option>
                  <option value="defense">Defense</option>
                  <option value="medical">Medical</option>
                  <option value="finance">Finance</option>
                  <option value="technology">Technology</option>
                </select>
                <div className="flex gap-2">
                  <button
                    onClick={addTerm}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-1"
                  >
                    <Save className="w-4 h-4" />
                    Save
                  </button>
                  <button
                    onClick={() => {
                      setShowAddForm(false);
                      setNewTerm({});
                    }}
                    className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Terms Table */}
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 px-4">Term</th>
                  <th className="text-left py-2 px-4">Expansion</th>
                  <th className="text-left py-2 px-4">Category</th>
                  <th className="text-left py-2 px-4">Priority</th>
                  <th className="text-left py-2 px-4">Source</th>
                  <th className="text-right py-2 px-4">Actions</th>
                </tr>
              </thead>
              <tbody>
                {getAllTerms().slice(0, 20).map((term: any) => (
                  <tr key={term.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 px-4 font-mono text-sm">
                      {editingTerm === term.id ? (
                        <input
                          type="text"
                          value={term.term}
                          onChange={(e) => updateTerm(term.id, { term: e.target.value })}
                          className="px-2 py-1 border rounded"
                        />
                      ) : (
                        term.term
                      )}
                    </td>
                    <td className="py-2 px-4 text-sm">
                      {editingTerm === term.id ? (
                        <input
                          type="text"
                          value={term.expansion}
                          onChange={(e) => updateTerm(term.id, { expansion: e.target.value })}
                          className="px-2 py-1 border rounded w-full"
                        />
                      ) : (
                        term.expansion
                      )}
                    </td>
                    <td className="py-2 px-4">
                      <span className={`px-2 py-1 rounded-full text-xs ${
                        term.category === 'custom' ? 'bg-blue-100 text-blue-700' :
                        term.category === 'defense' ? 'bg-gray-100 text-gray-700' :
                        term.category === 'medical' ? 'bg-red-100 text-red-700' :
                        term.category === 'finance' ? 'bg-green-100 text-green-700' :
                        'bg-purple-100 text-purple-700'
                      }`}>
                        {term.category}
                      </span>
                    </td>
                    <td className="py-2 px-4 text-sm">{term.priority}</td>
                    <td className="py-2 px-4 text-sm text-gray-500">
                      {term.setName || 'Custom'}
                    </td>
                    <td className="py-2 px-4 text-right">
                      {term.id.startsWith('custom-') || term.id.startsWith('import-') ? (
                        <div className="flex items-center justify-end gap-2">
                          {editingTerm === term.id ? (
                            <>
                              <button
                                onClick={() => setEditingTerm(null)}
                                className="p-1 hover:bg-gray-100 rounded"
                              >
                                <Check className="w-4 h-4 text-green-600" />
                              </button>
                              <button
                                onClick={() => setEditingTerm(null)}
                                className="p-1 hover:bg-gray-100 rounded"
                              >
                                <X className="w-4 h-4 text-gray-600" />
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                onClick={() => setEditingTerm(term.id)}
                                className="p-1 hover:bg-gray-100 rounded"
                              >
                                <Edit2 className="w-4 h-4 text-gray-600" />
                              </button>
                              <button
                                onClick={() => deleteTerm(term.id)}
                                className="p-1 hover:bg-gray-100 rounded"
                              >
                                <Trash2 className="w-4 h-4 text-red-600" />
                              </button>
                            </>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-gray-400">Pre-loaded</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Test Expansion */}
        <div className="p-6">
          <h2 className="text-lg font-semibold mb-4">Test Vocabulary Expansion</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Input Text (with acronyms)
              </label>
              <textarea
                value={testText}
                onChange={(e) => setTestText(e.target.value)}
                placeholder="Enter text with acronyms like ROI, API, CONOPS..."
                className="w-full h-32 px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <button
                onClick={testExpansion}
                className="mt-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
              >
                Test Expansion
              </button>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Expanded Result
              </label>
              <div className="w-full h-32 px-3 py-2 border rounded-lg bg-gray-50 overflow-auto">
                {expandedText || <span className="text-gray-400">Expanded text will appear here...</span>}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};