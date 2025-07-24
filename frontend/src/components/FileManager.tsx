import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';

interface AudioFile {
  id: number;
  file_id: string;
  session_id: string;
  filename: string;
  file_size: number;
  file_format: string;
  mime_type: string;
  duration_seconds?: number;
  created_at: string;
  status: string;
  tags?: string[];
}

interface FileManagerProps {
  sessionId?: string;
  onFileSelect?: (file: AudioFile) => void;
}

export const FileManager: React.FC<FileManagerProps> = ({ sessionId, onFileSelect }) => {
  const [files, setFiles] = useState<AudioFile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [sortBy, setSortBy] = useState<'created_at' | 'filename' | 'file_size'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [searchTerm, setSearchTerm] = useState('');
  const { token } = useAuth();

  useEffect(() => {
    fetchFiles();
  }, [sessionId, sortBy, sortOrder]);

  const fetchFiles = async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams({
        sort_by: sortBy,
        order: sortOrder,
        limit: '100',
      });
      
      if (sessionId) {
        params.append('session_id', sessionId);
      }

      const response = await fetch(`/api/files?${params}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setFiles(data.files || []);
      }
    } catch (error) {
      console.error('Error fetching files:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDuration = (seconds?: number): string => {
    if (!seconds) return '-';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  const handleDownload = async (file: AudioFile) => {
    try {
      const response = await fetch(`/api/files/${file.file_id}/download`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = file.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Error downloading file:', error);
    }
  };

  const handleBulkDownload = async () => {
    for (const fileId of selectedFiles) {
      const file = files.find(f => f.file_id === fileId);
      if (file) {
        await handleDownload(file);
        // Add small delay between downloads
        await new Promise(resolve => setTimeout(resolve, 500));
      }
    }
    setSelectedFiles(new Set());
  };

  const handleDelete = async (file: AudioFile) => {
    if (!confirm(`Are you sure you want to delete ${file.filename}?`)) {
      return;
    }

    try {
      const response = await fetch(`/api/files/${file.file_id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        fetchFiles();
      }
    } catch (error) {
      console.error('Error deleting file:', error);
    }
  };

  const toggleFileSelection = (fileId: string) => {
    const newSelection = new Set(selectedFiles);
    if (newSelection.has(fileId)) {
      newSelection.delete(fileId);
    } else {
      newSelection.add(fileId);
    }
    setSelectedFiles(newSelection);
  };

  const toggleAllSelection = () => {
    if (selectedFiles.size === files.length) {
      setSelectedFiles(new Set());
    } else {
      setSelectedFiles(new Set(files.map(f => f.file_id)));
    }
  };

  const filteredFiles = files.filter(file =>
    file.filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
    file.tags?.some(tag => tag.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  const toggleSort = (field: typeof sortBy) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-xl font-bold">Audio Files</h3>
        <div className="flex items-center space-x-4">
          {selectedFiles.size > 0 && (
            <button
              onClick={handleBulkDownload}
              className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium transition-all"
            >
              Download Selected ({selectedFiles.size})
            </button>
          )}
          <input
            type="text"
            placeholder="Search files..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm w-64"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
        </div>
      ) : filteredFiles.length === 0 ? (
        <div className="text-center py-12">
          <div className="w-16 h-16 bg-gray-700 rounded-full mx-auto mb-4 flex items-center justify-center">
            <svg className="w-8 h-8 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <p className="text-gray-400">No audio files found</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left border-b border-gray-700">
                <th className="pb-3 pr-4">
                  <input
                    type="checkbox"
                    checked={selectedFiles.size === files.length && files.length > 0}
                    onChange={toggleAllSelection}
                    className="rounded border-gray-600"
                  />
                </th>
                <th 
                  className="pb-3 pr-4 cursor-pointer hover:text-blue-400"
                  onClick={() => toggleSort('filename')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Filename</span>
                    {sortBy === 'filename' && (
                      <span className="text-xs">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                    )}
                  </div>
                </th>
                <th className="pb-3 pr-4">Format</th>
                <th 
                  className="pb-3 pr-4 cursor-pointer hover:text-blue-400"
                  onClick={() => toggleSort('file_size')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Size</span>
                    {sortBy === 'file_size' && (
                      <span className="text-xs">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                    )}
                  </div>
                </th>
                <th className="pb-3 pr-4">Duration</th>
                <th 
                  className="pb-3 pr-4 cursor-pointer hover:text-blue-400"
                  onClick={() => toggleSort('created_at')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Created</span>
                    {sortBy === 'created_at' && (
                      <span className="text-xs">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                    )}
                  </div>
                </th>
                <th className="pb-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredFiles.map((file) => (
                <tr key={file.file_id} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                  <td className="py-3 pr-4">
                    <input
                      type="checkbox"
                      checked={selectedFiles.has(file.file_id)}
                      onChange={() => toggleFileSelection(file.file_id)}
                      className="rounded border-gray-600"
                    />
                  </td>
                  <td className="py-3 pr-4">
                    <div className="flex items-center space-x-2">
                      <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                      </svg>
                      <div>
                        <div 
                          className="font-medium cursor-pointer hover:text-blue-400"
                          onClick={() => onFileSelect?.(file)}
                        >
                          {file.filename}
                        </div>
                        {file.tags && file.tags.length > 0 && (
                          <div className="flex items-center space-x-1 mt-1">
                            {file.tags.map((tag, idx) => (
                              <span key={idx} className="bg-gray-700 px-2 py-0.5 rounded text-xs">
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="py-3 pr-4">
                    <span className="text-sm text-gray-400 uppercase">{file.file_format}</span>
                  </td>
                  <td className="py-3 pr-4">
                    <span className="text-sm text-gray-300">{formatFileSize(file.file_size)}</span>
                  </td>
                  <td className="py-3 pr-4">
                    <span className="text-sm text-gray-300">{formatDuration(file.duration_seconds)}</span>
                  </td>
                  <td className="py-3 pr-4">
                    <span className="text-sm text-gray-400">
                      {new Date(file.created_at).toLocaleDateString()}
                    </span>
                  </td>
                  <td className="py-3">
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => onFileSelect?.(file)}
                        className="text-blue-400 hover:text-blue-300"
                        title="Play"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </button>
                      <button
                        onClick={() => handleDownload(file)}
                        className="text-green-400 hover:text-green-300"
                        title="Download"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" />
                        </svg>
                      </button>
                      <button
                        onClick={() => handleDelete(file)}
                        className="text-red-400 hover:text-red-300"
                        title="Delete"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};