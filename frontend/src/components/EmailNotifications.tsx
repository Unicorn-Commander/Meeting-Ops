import React, { useState, useEffect } from 'react';
import { Mail, Send, Settings, Check, AlertCircle } from 'lucide-react';

interface EmailSettings {
  enabled: boolean;
  autoSend: boolean;
  recipients: string[];
  includeTranscript: boolean;
  includeAudio: boolean;
  weeklyDigest: boolean;
  digestDay: string;
  smtpHost: string;
  smtpPort: number;
  smtpUsername: string;
  smtpPassword: string;
}

interface EmailNotificationsProps {
  sessionId?: string;
  sessionName?: string;
  // onClose?: () => void;
}

export const EmailNotifications: React.FC<EmailNotificationsProps> = ({
  sessionId,
  sessionName,
  // onClose
}) => {
  const [settings, setSettings] = useState<EmailSettings>({
    enabled: true,
    autoSend: false,
    recipients: [],
    includeTranscript: true,
    includeAudio: false,
    weeklyDigest: true,
    digestDay: 'monday',
    smtpHost: '',
    smtpPort: 587,
    smtpUsername: '',
    smtpPassword: '',
  });
  
  const [newRecipient, setNewRecipient] = useState('');
  const [sending, setSending] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    // Load saved settings
    const savedSettings = localStorage.getItem('emailSettings');
    if (savedSettings) {
      setSettings(prev => ({
        ...prev,
        ...JSON.parse(savedSettings)
      }));
    }

    // Fetch SMTP settings from backend on component mount
    fetch('/api/email/get-smtp-config')
      .then(response => response.json())
      .then(data => {
        if (data.smtp_host) {
          setSettings(prev => ({
            ...prev,
            smtpHost: data.smtp_host,
            smtpPort: data.smtp_port,
            smtpUsername: data.smtp_username,
            smtpPassword: data.smtp_password || '', // Password might not be returned for security
          }));
        }
      })
      .catch(error => console.error('Error fetching SMTP config:', error));
  }, []);

  const saveSettings = () => {
    localStorage.setItem('emailSettings', JSON.stringify(settings));
    // Also send SMTP settings to backend to persist them
    fetch('/api/email/configure-smtp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        smtp_host: settings.smtpHost,
        smtp_port: settings.smtpPort,
        smtp_username: settings.smtpUsername,
        smtp_password: settings.smtpPassword,
      }),
    }).then(response => {
      if (!response.ok) {
        console.error('Failed to save SMTP settings to backend');
      }
    }).catch(error => {
      console.error('Error saving SMTP settings to backend:', error);
    });
  };

  const addRecipient = () => {
    if (newRecipient && newRecipient.includes('@')) {
      setSettings(prev => ({
        ...prev,
        recipients: [...prev.recipients, newRecipient]
      }));
      setNewRecipient('');
    }
  };

  const removeRecipient = (email: string) => {
    setSettings(prev => ({
      ...prev,
      recipients: prev.recipients.filter(r => r !== email)
    }));
  };

  const testEmailConfig = async () => {
    setTestResult(null);
    setSending(true);
    try {
      const response = await fetch('/api/email/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          smtp_host: settings.smtpHost,
          smtp_port: settings.smtpPort,
          smtp_username: settings.smtpUsername,
          smtp_password: settings.smtpPassword,
        }),
      });
      const result = await response.json();
      setTestResult(result);
    } catch (error) {
      setTestResult({ status: 'error', message: 'Failed to connect to backend for email configuration test' });
    } finally {
      setSending(false);
    }
  };

  const sendSummaryEmail = async () => {
    if (settings.recipients.length === 0) {
      alert('Please add at least one recipient');
      return;
    }

    setSending(true);
    try {
      const response = await fetch('/api/email/send-summary', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          recipients: settings.recipients,
          session_id: sessionId,
          include_transcript: settings.includeTranscript,
          include_audio: settings.includeAudio
        })
      });

      if (response.ok) {
        const result = await response.json();
        alert(`Email queued for ${result.recipients} recipients`);
        saveSettings();
      } else {
        alert('Failed to send email');
      }
    } catch (error) {
      console.error('Email send error:', error);
      alert('Failed to send email');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <Mail className="w-6 h-6 text-blue-400" />
          <h3 className="text-xl font-bold">Email Notifications</h3>
        </div>
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="text-gray-400 hover:text-white"
        >
          <Settings className="w-5 h-5" />
        </button>
      </div>

      {/* Quick Send Section */}
      {sessionId && !showSettings && (
        <div className="space-y-4">
          <div className="bg-gray-700 rounded-lg p-4">
            <p className="text-sm text-gray-300 mb-2">Send summary for:</p>
            <p className="font-medium">{sessionName || `Session ${sessionId}`}</p>
          </div>

          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium mb-2">Recipients</label>
              <div className="flex space-x-2">
                <input
                  type="email"
                  value={newRecipient}
                  onChange={(e) => setNewRecipient(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && addRecipient()}
                  placeholder="Enter email address"
                  className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
                <button
                  onClick={addRecipient}
                  className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg"
                >
                  Add
                </button>
              </div>
            </div>

            {settings.recipients.length > 0 && (
              <div className="space-y-2">
                {settings.recipients.map((email) => (
                  <div key={email} className="flex items-center justify-between bg-gray-700 rounded px-3 py-2">
                    <span className="text-sm">{email}</span>
                    <button
                      onClick={() => removeRecipient(email)}
                      className="text-red-400 hover:text-red-300 text-sm"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-2">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={settings.includeTranscript}
                  onChange={(e) => setSettings(prev => ({ ...prev, includeTranscript: e.target.checked }))}
                  className="rounded"
                />
                <span className="text-sm">Include full transcript</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={settings.includeAudio}
                  onChange={(e) => setSettings(prev => ({ ...prev, includeAudio: e.target.checked }))}
                  className="rounded"
                />
                <span className="text-sm">Attach audio file</span>
              </label>
            </div>

            <button
              onClick={sendSummaryEmail}
              disabled={sending || settings.recipients.length === 0}
              className={`w-full flex items-center justify-center space-x-2 py-3 rounded-lg font-medium transition-colors ${
                sending || settings.recipients.length === 0
                  ? 'bg-gray-600 text-gray-400 cursor-not-allowed'
                  : 'bg-green-600 hover:bg-green-700 text-white'
              }`}
            >
              {sending ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                  <span>Sending...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Send Summary Email</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Settings Section */}
      {showSettings && (
        <div className="space-y-6">
          <div className="space-y-4">
            <h4 className="font-medium text-gray-300">Email Configuration</h4>
            
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium mb-1">SMTP Host</label>
                <input
                  type="text"
                  value={settings.smtpHost}
                  onChange={(e) => setSettings(prev => ({ ...prev, smtpHost: e.target.value }))}
                  placeholder="smtp.example.com"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">SMTP Port</label>
                <input
                  type="number"
                  value={settings.smtpPort}
                  onChange={(e) => setSettings(prev => ({ ...prev, smtpPort: parseInt(e.target.value) }))}
                  placeholder="587"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">SMTP Username</label>
                <input
                  type="text"
                  value={settings.smtpUsername}
                  onChange={(e) => setSettings(prev => ({ ...prev, smtpUsername: e.target.value }))}
                  placeholder="your-email@example.com"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">SMTP Password</label>
                <input
                  type="password"
                  value={settings.smtpPassword}
                  onChange={(e) => setSettings(prev => ({ ...prev, smtpPassword: e.target.value }))}
                  placeholder="Your SMTP password"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
              </div>
            </div>
            
            <button
              onClick={testEmailConfig}
              className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded-lg text-sm"
            >
              Test Email Configuration
            </button>

            {sending && (
              <div className="flex items-center space-x-2 text-blue-400">
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-blue-400 border-t-transparent"></div>
                <span>Testing configuration...</span>
              </div>
            )}

            {testResult && !sending && (
              <div className={`p-3 rounded-lg text-sm ${
                testResult.status === 'configured' 
                  ? 'bg-green-900/50 text-green-300 border border-green-700'
                  : 'bg-red-900/50 text-red-300 border border-red-700'
              }`}>
                {testResult.status === 'configured' ? (
                  <div className="flex items-start space-x-2">
                    <Check className="w-4 h-4 mt-0.5" />
                    <div>
                      <p className="font-medium">Email service configured</p>
                      <p className="text-xs opacity-75 mt-1">
                        SMTP: {testResult.smtp_host}:{testResult.smtp_port}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start space-x-2">
                    <AlertCircle className="w-4 h-4 mt-0.5" />
                    <div>
                      <p className="font-medium">{testResult.message}</p>
                      {testResult.required_env_vars && (
                        <div className="mt-2 text-xs">
                          <p>Required environment variables:</p>
                          <ul className="list-disc list-inside ml-2">
                            {testResult.required_env_vars.map((v: string) => (
                              <li key={v}>{v}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="space-y-4">
            <h4 className="font-medium text-gray-300">Notification Preferences</h4>
            
            <label className="flex items-center justify-between">
              <span className="text-sm">Email notifications enabled</span>
              <button
                onClick={() => setSettings(prev => ({ ...prev, enabled: !prev.enabled }))}
                className={`w-12 h-6 rounded-full relative transition-colors ${
                  settings.enabled ? 'bg-green-600' : 'bg-gray-600'
                }`}
              >
                <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${
                  settings.enabled ? 'left-6' : 'left-0.5'
                }`} />
              </button>
            </label>

            <label className="flex items-center justify-between">
              <span className="text-sm">Auto-send after meeting ends</span>
              <button
                onClick={() => setSettings(prev => ({ ...prev, autoSend: !prev.autoSend }))}
                className={`w-12 h-6 rounded-full relative transition-colors ${
                  settings.autoSend ? 'bg-green-600' : 'bg-gray-600'
                }`}
              >
                <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${
                  settings.autoSend ? 'left-6' : 'left-0.5'
                }`} />
              </button>
            </label>

            <label className="flex items-center justify-between">
              <span className="text-sm">Weekly digest emails</span>
              <button
                onClick={() => setSettings(prev => ({ ...prev, weeklyDigest: !prev.weeklyDigest }))}
                className={`w-12 h-6 rounded-full relative transition-colors ${
                  settings.weeklyDigest ? 'bg-green-600' : 'bg-gray-600'
                }`}
              >
                <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${
                  settings.weeklyDigest ? 'left-6' : 'left-0.5'
                }`} />
              </button>
            </label>

            {settings.weeklyDigest && (
              <div>
                <label className="block text-sm mb-2">Send digest on</label>
                <select
                  value={settings.digestDay}
                  onChange={(e) => setSettings(prev => ({ ...prev, digestDay: e.target.value }))}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2"
                >
                  <option value="monday">Monday</option>
                  <option value="tuesday">Tuesday</option>
                  <option value="wednesday">Wednesday</option>
                  <option value="thursday">Thursday</option>
                  <option value="friday">Friday</option>
                  <option value="saturday">Saturday</option>
                  <option value="sunday">Sunday</option>
                </select>
              </div>
            )}
          </div>

          <div className="flex justify-end space-x-3">
            <button
              onClick={() => setShowSettings(false)}
              className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded-lg"
            >
              Cancel
            </button>
            <button
              onClick={() => {
                saveSettings();
                setShowSettings(false);
              }}
              className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg"
            >
              Save Settings
            </button>
          </div>
        </div>
      )}
    </div>
  );
};