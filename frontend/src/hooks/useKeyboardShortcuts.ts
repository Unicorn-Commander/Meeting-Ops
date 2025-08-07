import { useEffect, useCallback } from 'react';

export interface KeyboardShortcut {
  key: string;
  ctrlKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
  metaKey?: boolean;
  action: () => void;
  description: string;
}

export const useKeyboardShortcuts = (shortcuts: KeyboardShortcut[]) => {
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    // Don't trigger shortcuts when typing in inputs
    const target = event.target as HTMLElement;
    if (
      target.tagName === 'INPUT' || 
      target.tagName === 'TEXTAREA' || 
      target.contentEditable === 'true'
    ) {
      return;
    }

    for (const shortcut of shortcuts) {
      if (
        event.key.toLowerCase() === shortcut.key.toLowerCase() &&
        !!event.ctrlKey === !!shortcut.ctrlKey &&
        !!event.altKey === !!shortcut.altKey &&
        !!event.shiftKey === !!shortcut.shiftKey &&
        !!event.metaKey === !!shortcut.metaKey
      ) {
        event.preventDefault();
        shortcut.action();
        break;
      }
    }
  }, [shortcuts]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
};

// Predefined shortcuts for Meeting-Ops
export const MEETING_OPS_SHORTCUTS: KeyboardShortcut[] = [
  {
    key: 'r',
    ctrlKey: true,
    action: () => {
      const event = new CustomEvent('meeting-ops:toggle-recording');
      window.dispatchEvent(event);
    },
    description: 'Toggle recording (Ctrl+R)'
  },
  {
    key: 't',
    ctrlKey: true,
    action: () => {
      const event = new CustomEvent('meeting-ops:toggle-transcription');
      window.dispatchEvent(event);
    },
    description: 'Toggle transcription (Ctrl+T)'
  },
  {
    key: 'p',
    ctrlKey: true,
    action: () => {
      const event = new CustomEvent('meeting-ops:pause-recording');
      window.dispatchEvent(event);
    },
    description: 'Pause/Resume recording (Ctrl+P)'
  },
  {
    key: 'f',
    ctrlKey: true,
    action: () => {
      const event = new CustomEvent('meeting-ops:flag-moment');
      window.dispatchEvent(event);
    },
    description: 'Flag current moment (Ctrl+F)'
  },
  {
    key: 's',
    ctrlKey: true,
    action: () => {
      const event = new CustomEvent('meeting-ops:save-session');
      window.dispatchEvent(event);
    },
    description: 'Save session (Ctrl+S)'
  },
  {
    key: 'd',
    ctrlKey: true,
    action: () => {
      const event = new CustomEvent('meeting-ops:toggle-dark-mode');
      window.dispatchEvent(event);
    },
    description: 'Toggle dark mode (Ctrl+D)'
  },
  {
    key: '/',
    action: () => {
      const event = new CustomEvent('meeting-ops:open-search');
      window.dispatchEvent(event);
    },
    description: 'Open search (/)'
  },
  {
    key: 'Escape',
    action: () => {
      const event = new CustomEvent('meeting-ops:close-modal');
      window.dispatchEvent(event);
    },
    description: 'Close modal/dialog (Esc)'
  },
  {
    key: '?',
    shiftKey: true,
    action: () => {
      const event = new CustomEvent('meeting-ops:show-help');
      window.dispatchEvent(event);
    },
    description: 'Show keyboard shortcuts (?)'
  }
];

// Hook for Meeting-Ops specific shortcuts
export const useMeetingOpsShortcuts = () => {
  useKeyboardShortcuts(MEETING_OPS_SHORTCUTS);
};