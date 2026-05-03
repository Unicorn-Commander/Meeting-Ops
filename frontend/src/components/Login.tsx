import React, { useEffect } from 'react';

/**
 * SSO-only login. Meeting Ops auth is delegated to the unicorn-commander
 * Keycloak realm via oauth2-proxy. There's no local password form anymore.
 */
export const Login: React.FC = () => {
  useEffect(() => {
    const target = encodeURIComponent('/');
    window.location.replace(`/oauth2/start?rd=${target}`);
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-gray-500">Redirecting to Unicorn Commander sign-in…</div>
    </div>
  );
};

export default Login;
