import React, { useState, useEffect } from 'react';
import { Upload, Download, Trash2, List, PlusCircle, Clock } from 'lucide-react';

interface Backup {
  backup_id: string;
  filename: string;
  size: number;
  created_at: string;
}

export const BackupManager: React.FC = () => {
  const [backups, setBackups] = useState<Backup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const API_BASE_URL = import.meta.env.VITE_API_URL || '';

  const fetchBackups = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/backup/list`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setBackups(data);
    } catch (e: any) {
      setError(`Failed to fetch backups: ${e.message}`);
      console.error("Error fetching backups:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateBackup = async () => {
    if (window.confirm("Are you sure you want to create a new backup? This might take a moment.")) {
      setLoading(true);
      setMessage(null);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/api/backup/create`, {
          method: 'POST',
        });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        setMessage(`Backup created: ${data.backup_id}`);
        fetchBackups();
      } catch (e: any) {
        setError(`Failed to create backup: ${e.message}`);
        console.error("Error creating backup:", e);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleRestoreBackup = async (backupId: string) => {
    if (window.confirm("WARNING: Restoring a backup will overwrite current data. Are you sure you want to proceed? You should stop the application before restoring.")) {
      setLoading(true);
      setMessage(null);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/api/backup/restore/${backupId}`, {
          method: 'POST',
        });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        setMessage(data.message);
        fetchBackups();
      } catch (e: any) {
        setError(`Failed to restore backup: ${e.message}`);
        console.error("Error restoring backup:", e);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleDeleteBackup = async (backupId: string, filename: string) => {
    if (window.confirm(`Are you sure you want to delete backup ${filename}? This action cannot be undone.`)) {
      setLoading(true);
      setMessage(null);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/api/backup/${backupId}`, {
          method: 'DELETE',
        });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        setMessage(data.message);
        fetchBackups();
      } catch (e: any) {
        setError(`Failed to delete backup: ${e.message}`);
        console.error("Error deleting backup:", e);
      } finally {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchBackups();
  }, []);

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 flex flex-col h-full">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <Upload className="w-6 h-6 text-green-400" />
          <h3 className="text-xl font-bold">Backup & Restore</h3>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={handleCreateBackup}
            className="bg-green-600 hover:bg-green-700 px-3 py-2 rounded-lg text-sm flex items-center space-x-1"
            disabled={loading}
          >
            <PlusCircle className="w-4 h-4" />
            <span>Create Backup</span>
          </button>
          <button
            onClick={fetchBackups}
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
      {message && (
        <div className="bg-blue-900/50 text-blue-300 border border-blue-700 p-3 rounded-lg mb-4 text-sm">
          {message}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        <h4 className="font-medium text-gray-300 mb-3">Available Backups</h4>
        {loading && backups.length === 0 ? (
          <p className="text-gray-400">Loading backups...</p>
        ) : backups.length === 0 ? (
          <p className="text-gray-400">No backups found.</p>
        ) : (
          <ul className="space-y-3">
            {backups.map((backup) => (
              <li
                key={backup.backup_id}
                className="bg-gray-700 p-4 rounded-lg flex justify-between items-center"
              >
                <div>
                  <p className="font-medium text-sm">{backup.filename}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {(backup.size / (1024 * 1024)).toFixed(2)} MB | Created: {new Date(backup.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => handleRestoreBackup(backup.backup_id)}
                    className="bg-blue-600 hover:bg-blue-700 px-3 py-2 rounded-lg text-sm flex items-center space-x-1"
                    disabled={loading}
                  >
                    <Download className="w-4 h-4" />
                    <span>Restore</span>
                  </button>
                  <button
                    onClick={() => handleDeleteBackup(backup.backup_id, backup.filename)}
                    className="bg-red-600 hover:bg-red-700 px-3 py-2 rounded-lg text-sm flex items-center space-x-1"
                    disabled={loading}
                  >
                    <Trash2 className="w-4 h-4" />
                    <span>Delete</span>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-6 border-t border-gray-700 pt-6">
        <h4 className="font-medium text-gray-300 mb-3">Backup Schedule (Coming Soon)</h4>
        <div className="flex items-center space-x-2 text-gray-400">
          <Clock className="w-5 h-5" />
          <span>Automated backup scheduling features will be available here.</span>
        </div>
      </div>
    </div>
  );
};