import React from 'react';
import { X, Download, Clock, SkipForward } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface UpdateNotificationProps {
  release: {
    tag_name: string;
    name: string;
    published_at: string;
    body: string;
    html_url: string;
  };
  currentVersion: string;
  onClose: () => void;
  onSkip: () => void;
  onRemindLater: () => void;
}

export const UpdateNotification: React.FC<UpdateNotificationProps> = ({
  release,
  currentVersion,
  onClose,
  onSkip,
  onRemindLater,
}) => {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50 backdrop-blur-sm">
      <div className="bg-gray-800 border border-gray-700 rounded-2xl shadow-2xl p-8 max-w-2xl w-full mx-4 max-h-[90vh] flex flex-col text-white">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white">{release.name}</h2>
            <p className="text-sm text-gray-400">
              Version {release.tag_name} &bull; Published{' '}
              {formatDistanceToNow(new Date(release.published_at), { addSuffix: true })}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors rounded-full p-2"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="flex-grow overflow-y-auto pr-4 -mr-4 mb-6">
          <div className="prose prose-invert prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: release.body.replace(/\n/g, '<br />') }} />
        </div>

        <div className="flex-shrink-0">
          <div className="flex justify-between items-center mb-4 text-sm">
            <span className="text-gray-400">Current Version: {currentVersion}</span>
            <span className="text-purple-400 font-semibold">New Version: {release.tag_name}</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <button
              onClick={onSkip}
              className="flex items-center justify-center gap-2 px-4 py-3 bg-gray-700 hover:bg-gray-600 text-white font-medium rounded-lg transition-all"
            >
              <SkipForward className="w-5 h-5" />
              <span>Skip Version</span>
            </button>
            <button
              onClick={onRemindLater}
              className="flex items-center justify-center gap-2 px-4 py-3 bg-gray-700 hover:bg-gray-600 text-white font-medium rounded-lg transition-all"
            >
              <Clock className="w-5 h-5" />
              <span>Remind Me Later</span>
            </button>
            <a
              href={release.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 hover:bg-purple-700 text-white font-bold rounded-lg transition-all col-span-1 md:col-span-1"
            >
              <Download className="w-5 h-5" />
              <span>Download</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};