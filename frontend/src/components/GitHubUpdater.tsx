import React, { useState, useEffect, useCallback } from 'react';
import { Download, CheckCircle, RefreshCw } from 'lucide-react';
import { UpdateNotification } from './UpdateNotification';
const currentVersion = '1.0.0'; // TODO: Import from package.json when available

interface GitHubRelease {
  tag_name: string;
  name: string;
  published_at: string;
  body: string;
  html_url: string;
  assets: Array<{
    name: string;
    browser_download_url: string;
  }>;
}

const GITHUB_API_URL = 'https://api.github.com/repos/Unicorn-Commander/Meeting-Ops/releases/latest';
const UPDATE_CHECK_INTERVAL = 60 * 60 * 1000; // 1 hour
const REMIND_LATER_DURATION = 24 * 60 * 60 * 1000; // 24 hours

const isNewerVersion = (current: string, latest: string): boolean => {
  const currentParts = current.replace('v', '').split('.').map(Number);
  const latestParts = latest.replace('v', '').split('.').map(Number);
  
  for (let i = 0; i < 3; i++) {
    if (latestParts[i] > currentParts[i]) return true;
    if (latestParts[i] < currentParts[i]) return false;
  }
  return false;
};

export const GitHubUpdater: React.FC = () => {
  const [latestRelease, setLatestRelease] = useState<GitHubRelease | null>(null);
  const [showNotification, setShowNotification] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasUpdate, setHasUpdate] = useState(false);

  const checkForUpdates = useCallback(async (forceCheck = false) => {
    setLoading(true);
    setError(null);

    const lastCheck = localStorage.getItem('meeting-ops-last-update-check');
    if (lastCheck && !forceCheck && Date.now() - parseInt(lastCheck) < UPDATE_CHECK_INTERVAL) {
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(GITHUB_API_URL);
      if (!response.ok) {
        throw new Error(`GitHub API request failed: ${response.statusText}`);
      }
      const release: GitHubRelease = await response.json();
      setLatestRelease(release);
      localStorage.setItem('meeting-ops-last-update-check', Date.now().toString());

      const skippedVersions = JSON.parse(localStorage.getItem('meeting-ops-skipped-versions') || '[]');
      if (isNewerVersion(currentVersion, release.tag_name) && !skippedVersions.includes(release.tag_name)) {
        setHasUpdate(true);
        const remindLaterTimestamp = localStorage.getItem('meeting-ops-remind-later');
        if (!remindLaterTimestamp || Date.now() > parseInt(remindLaterTimestamp)) {
          setShowNotification(true);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkForUpdates();
    const intervalId = setInterval(checkForUpdates, UPDATE_CHECK_INTERVAL);
    return () => clearInterval(intervalId);
  }, [checkForUpdates]);

  const handleSkipVersion = () => {
    if (latestRelease) {
      const skippedVersions = JSON.parse(localStorage.getItem('meeting-ops-skipped-versions') || '[]');
      localStorage.setItem('meeting-ops-skipped-versions', JSON.stringify([...skippedVersions, latestRelease.tag_name]));
      setShowNotification(false);
      setHasUpdate(false);
    }
  };

  const handleRemindLater = () => {
    localStorage.setItem('meeting-ops-remind-later', (Date.now() + REMIND_LATER_DURATION).toString());
    setShowNotification(false);
  };

  return (
    <>
      <div className="fixed bottom-4 right-4 z-50">
        {hasUpdate ? (
          <div 
            className="bg-purple-600 hover:bg-purple-700 text-white rounded-lg p-3 cursor-pointer shadow-lg transition-all animate-pulse"
            onClick={() => setShowNotification(true)}
          >
            <div className="flex items-center gap-2">
              <Download className="w-5 h-5" />
              <span className="text-sm font-medium">Update Available</span>
            </div>
          </div>
        ) : (
          <button 
            className="bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg p-3 transition-all"
            onClick={() => checkForUpdates(true)} disabled={loading}
          >
            {loading ? <RefreshCw className="w-5 h-5 animate-spin" /> : <CheckCircle className="w-5 h-5" />}
          </button>
        )}
        {error && <p className="text-red-500 text-xs mt-2">{error}</p>}
      </div>

      {showNotification && latestRelease && (
        <UpdateNotification
          release={latestRelease}
          currentVersion={currentVersion}
          onClose={() => setShowNotification(false)}
          onSkip={handleSkipVersion}
          onRemindLater={handleRemindLater}
        />
      )}
    </>
  );
};