import { showToast } from '../components/Toast';
import { getErrorMessage } from './errorHandling';

/**
 * Display a notification to the user via the shared toast system (react-toastify).
 */
export function showNotification(message: string, type: 'success' | 'error' | 'info' = 'info'): void {
  showToast[type](message);
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
