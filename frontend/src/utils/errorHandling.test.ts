import { getErrorMessage } from './errorHandling';

describe('getErrorMessage', () => {
  it('should handle Error instances', () => {
    const error = new Error('Test error message');
    expect(getErrorMessage(error)).toBe('Test error message');
  });

  it('should handle string errors', () => {
    expect(getErrorMessage('String error')).toBe('String error');
  });

  it('should handle objects with message property', () => {
    const error = { message: 'Object with message' };
    expect(getErrorMessage(error)).toBe('Object with message');
  });

  it('should handle objects with detail property', () => {
    const error = { detail: 'API error detail' };
    expect(getErrorMessage(error)).toBe('API error detail');
  });

  it('should handle objects with error property', () => {
    const error = { error: 'Error property' };
    expect(getErrorMessage(error)).toBe('Error property');
  });

  it('should handle plain objects by stringifying', () => {
    const error = { code: 'ERR_001', status: 400 };
    expect(getErrorMessage(error)).toBe('{"code":"ERR_001","status":400}');
  });

  it('should handle null and undefined', () => {
    expect(getErrorMessage(null)).toBe('An unknown error occurred');
    expect(getErrorMessage(undefined)).toBe('An unknown error occurred');
  });

  it('should handle empty objects', () => {
    expect(getErrorMessage({})).toBe('An unknown error occurred');
  });

  it('should handle non-serializable objects', () => {
    const circular: any = { prop: 'value' };
    circular.self = circular;
    expect(getErrorMessage(circular)).toBe('An unknown error occurred');
  });

  it('should use custom default message', () => {
    expect(getErrorMessage(null, 'Custom default')).toBe('Custom default');
  });
});