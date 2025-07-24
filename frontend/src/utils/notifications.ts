import { getErrorMessage } from './errorHandling';

/**
 * Display a notification to the user
 * This is a wrapper around alert() that can be replaced with a better notification system later
 */
export function showNotification(message: string, type: 'success' | 'error' | 'info' = 'info'): void {
  // For now, just use alert with proper formatting
  const prefix = type === 'error' ? '❌' : type === 'success' ? '✅' : 'ℹ️';
  alert(`${prefix} ${message}`);
}

/**
 * Display an error notification with proper error handling
 */
export function showError(error: unknown, context?: string): void {
  const message = getErrorMessage(error);
  const fullMessage = context ? `${context}: ${message}` : message;
  showNotification(fullMessage, 'error');
}

/**
 * Display a success notification
 */
export function showSuccess(message: string): void {
  showNotification(message, 'success');
}

/**
 * Display an info notification
 */
export function showInfo(message: string): void {
  showNotification(message, 'info');
}