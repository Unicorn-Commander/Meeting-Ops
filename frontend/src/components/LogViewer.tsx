import React, { useState, useEffect, useRef } from 'react';
import { FileText, List, RotateCcw, Trash2, Search, Download } from 'lucide-react';

interface LogFile {
  name: string;
  size: number;
  last_modified: string;
  created_at: string;
}

export const LogViewer: React.FC = () => {
  const [logFiles, setLogFiles] = useState<LogFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [logContent, setLogContent] = useState<string>('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const contentRef = useRef<HTMLPreElement>(null);

  const API_BASE_URL = import.meta.env.VITE_API_URL || '';

  const fetchLogFiles = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/logs/list`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setLogFiles(data);
    } catch (e: any) {
      setError(`Failed to fetch log files: ${e.message}`);
      console.error("Error fetching log files:", e);
    } finally {
      setLoading(false);
    }
  };

  const fetchLogContent = async (filename: string, page: number) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/logs/${filename}?page=${page}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setLogContent(data.content);
      setTotalPages(Math.ceil(data.total_lines / data.page_size));
      setCurrentPage(data.page);
      if (contentRef.current) {
        contentRef.current.scrollTop = contentRef.current.scrollHeight;
      }
    } catch (e: any) {
      setError(`Failed to fetch log content: ${e.message}`);
      console.error("Error fetching log content:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (filename: string) => {
    setSelectedFile(filename);
    setCurrentPage(1);
    fetchLogContent(filename, 1);
  };

  const handlePageChange = (newPage: number) => {
    if (selectedFile) {
      fetchLogContent(selectedFile, newPage);
    }
  };

  const handleRotateLogs = async () => {
    if (window.confirm("Are you sure you want to trigger log rotation? This might create new log files.")) {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/api/logs/rotate`, {
          method: 'POST',
        });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        alert(data.message);
        fetchLogFiles(); // Refresh list after rotation
      } catch (e: any) {
        setError(`Failed to rotate logs: ${e.message}`);
        console.error("Error rotating logs:", e);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleDeleteLog = async (filename: string) => {
    if (window.confirm(`Are you sure you want to delete ${filename}? This action cannot be undone.`)) {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/api/logs/${filename}`, {
          method: 'DELETE',
        });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        alert(data.message);
        setSelectedFile(null);
        setLogContent('');
        fetchLogFiles(); // Refresh list after deletion
      } catch (e: any) {
        setError(`Failed to delete log file: ${e.message}`);
        console.error("Error deleting log file:", e);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleDownloadLog = (filename: string) => {
    // In a real application, you'd likely have a dedicated download endpoint
    // For now, we'll just open the log content in a new tab or trigger a simple download
    const blob = new Blob([logContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  useEffect(() => {
    fetchLogFiles();
  }, []);

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 flex flex-col h-full">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <FileText className="w-6 h-6 text-purple-400" />
          <h3 className="text-xl font-bold">Log Management</h3>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={handleRotateLogs}
            className="bg-gray-700 hover:bg-gray-600 px-3 py-2 rounded-lg text-sm flex items-center space-x-1"
            disabled={loading}
          >
            <RotateCcw className="w-4 h-4" />
            <span>Rotate Logs</span>
          </button>
          <button
            onClick={fetchLogFiles}
            className="bg-gray-700 hover:bg-gray-600 px-3 py-2 rounded-lg text-sm flex items-center space-x-1"
            disabled={loading}
          >
            <List className="w-4 h-4" />
            <span>Refresh List</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/50 text-red-300 border border-red-700 p-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Log File List */}
        <div className="w-1/3 pr-4 border-r border-gray-700 overflow-y-auto">
          <h4 className="font-medium text-gray-300 mb-3">Available Log Files</h4>
          {loading && logFiles.length === 0 ? (
            <p className="text-gray-400">Loading files...</p>
          ) : logFiles.length === 0 ? (
            <p className="text-gray-400">No log files found.</p>
          ) : (
            <ul className="space-y-2">
              {logFiles.map((file) => (
                <li
                  key={file.name}
                  className={`cursor-pointer p-3 rounded-lg transition-colors flex justify-between items-center ${
                    selectedFile === file.name ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'
                  }`}
                  onClick={() => handleFileSelect(file.name)}
                >
                  <div>
                    <p className="font-medium text-sm">{file.name}</p>
                    <p className="text-xs text-gray-400">{(file.size / 1024).toFixed(2)} KB | Last modified: {new Date(file.last_modified).toLocaleString()}</p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation(); // Prevent selecting file when deleting
                      handleDeleteLog(file.name);
                    }}
                    className="text-red-400 hover:text-red-300 ml-2"
                    title="Delete Log File"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Log Content Viewer */}
        <div className="w-2/3 pl-4 flex flex-col">
          <h4 className="font-medium text-gray-300 mb-3">Log Content: {selectedFile || 'Select a file'}</h4>
          {selectedFile ? (
            <>
              <pre
                ref={contentRef}
                className="flex-1 bg-gray-900 text-gray-200 p-4 rounded-lg text-xs overflow-auto font-mono"
              >
                {loading ? 'Loading log content...' : logContent || 'No content to display.'}
              </pre>
              <div className="flex justify-between items-center mt-4">
                <button
                  onClick={() => handlePageChange(currentPage - 1)}
                  disabled={currentPage === 1 || loading}
                  className="bg-gray-700 hover:bg-gray-600 px-3 py-2 rounded-lg text-sm"
                >
                  Previous Page
                </button>
                <span className="text-sm text-gray-400">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  onClick={() => handlePageChange(currentPage + 1)}
                  disabled={currentPage === totalPages || loading}
                  className="bg-gray-700 hover:bg-gray-600 px-3 py-2 rounded-lg text-sm"
                >
                  Next Page
                </button>
                <button
                  onClick={() => selectedFile && handleDownloadLog(selectedFile)}
                  disabled={!selectedFile || loading}
                  className="bg-blue-600 hover:bg-blue-700 px-3 py-2 rounded-lg text-sm flex items-center space-x-1"
                >
                  <Download className="w-4 h-4" />
                  <span>Download</span>
                </button>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-400">
              <p>Select a log file from the left to view its content.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};