import React, { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Mail,
  Sparkles,
  UserRoundPlus,
} from 'lucide-react';
import { config } from '../config';

function extractApiError(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          const message = (item as { msg?: unknown; message?: unknown }).msg ?? (item as { msg?: unknown; message?: unknown }).message;
          if (typeof message === 'string') return message;
        }
        return JSON.stringify(item);
      })
      .join(' ');
  }
  return fallback;
}

export const Signup: React.FC = () => {
  const location = useLocation();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  // v3.21.0: when ALLOW_REGISTRATION=false the backend returns
  // 403 "Registration is disabled" on /api/auth/register. The Landing
  // CTA always lands us here, so we detect that case and switch to a
  // friendly "thanks, we got your interest" surface instead of an
  // error toast — the email was already captured by the Landing form
  // posting to /api/landing/invite-request before redirecting.
  const [registrationClosed, setRegistrationClosed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pre-fill email from `?email=` query (set by Landing CTA).
  useEffect(() => {
    const params = new URLSearchParams(location.search || '');
    const fromQuery = params.get('email');
    if (fromQuery) {
      setEmail(fromQuery.trim());
    }
  }, [location.search]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch(`${config.apiUrl}/api/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          email: email.trim(),
          username: username.trim(),
          password,
          ...(fullName.trim() ? { full_name: fullName.trim() } : {}),
        }),
      });

      if (response.status === 403) {
        // Registration is closed (invite-only beta). Pivot to the
        // friendly invite-confirmation surface — the Landing form has
        // already logged the email server-side. Best-effort re-log
        // here too in case the user typed a fresh email on the form.
        try {
          await fetch(`${config.apiUrl}/api/landing/invite-request`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email.trim() }),
          });
        } catch {
          /* soft-fail — the user-facing message is the same either way */
        }
        setRegistrationClosed(true);
        return;
      }

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(extractApiError(payload, `Signup failed (${response.status})`));
      }

      setSuccess(true);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Signup failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 py-6 lg:px-8">
        <header className="flex items-center justify-between border-b border-white/10 pb-4">
          <Link to="/pricing" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-fuchsia-500 to-violet-500 shadow-lg shadow-fuchsia-500/20">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight text-white">Meeting-Ops</div>
              <div className="text-xs text-zinc-400">Create a consumer account</div>
            </div>
          </Link>
          <Link to="/login" className="rounded-full border border-white/10 px-3 py-2 text-sm text-zinc-300 transition hover:border-fuchsia-400/40 hover:text-white">
            Sign in
          </Link>
        </header>

        <main className="grid flex-1 items-center gap-10 py-10 lg:grid-cols-[1.05fr_0.95fr]">
          <section className="max-w-2xl space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-fuchsia-500/30 bg-fuchsia-500/10 px-3 py-1 text-xs font-medium text-fuchsia-200">
              <UserRoundPlus className="h-3.5 w-3.5" />
              Self-serve signup
            </div>
            <div className="space-y-4">
              <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
                Create a private workspace in a few minutes.
              </h1>
              <p className="max-w-xl text-base leading-7 text-zinc-300">
                Sign up with email, verify the account, and start with the free tier immediately.
                The backend creates a private personal organization automatically.
              </p>
            </div>
            <div className="grid gap-3 text-sm text-zinc-300 sm:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-center gap-2 font-medium text-white">
                  <CheckCircle2 className="h-4 w-4 text-fuchsia-300" />
                  Free account
                </div>
                <p className="mt-2 leading-6">Local transcription, summaries, and session history without a subscription.</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-center gap-2 font-medium text-white">
                  <Mail className="h-4 w-4 text-fuchsia-300" />
                  Verification email
                </div>
                <p className="mt-2 leading-6">Registration sends a verification link automatically, so the login page can confirm the account.</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-center gap-2 font-medium text-white">
                  <CheckCircle2 className="h-4 w-4 text-fuchsia-300" />
                  Password policy
                </div>
                <p className="mt-2 leading-6">Minimum 8 characters with upper case, lower case, and a number.</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-center gap-2 font-medium text-white">
                  <CircleAlert className="h-4 w-4 text-fuchsia-300" />
                  Username rules
                </div>
                <p className="mt-2 leading-6">Use 3-30 characters made of letters, numbers, or underscores.</p>
              </div>
            </div>
          </section>

          <section className="rounded-3xl border border-white/10 bg-zinc-900/80 p-6 shadow-2xl shadow-black/30 backdrop-blur">
            {registrationClosed ? (
              <div className="space-y-5 rounded-2xl border border-fuchsia-500/30 bg-fuchsia-500/10 p-5 text-fuchsia-50">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
                  <div>
                    <h2 className="text-xl font-semibold text-white">Thanks — we got your invite request.</h2>
                    <p className="mt-2 text-sm leading-6 text-fuchsia-100/90">
                      Meeting-Ops is in private beta. We've logged your email
                      {email.trim() ? <> (<span className="font-medium">{email.trim()}</span>)</> : null}
                      {' '}and will reach out as slots open.
                    </p>
                    <p className="mt-3 text-sm leading-6 text-fuchsia-100/90">
                      Already have an account? You can{' '}
                      <Link to="/login" className="font-medium underline-offset-4 hover:underline">
                        sign in here
                      </Link>
                      .
                    </p>
                  </div>
                </div>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <Link
                    to="/pricing"
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-zinc-100 transition hover:bg-white/10"
                  >
                    View pricing
                  </Link>
                </div>
              </div>
            ) : success ? (
              <div className="space-y-5 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-5 text-emerald-100">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
                  <div>
                    <h2 className="text-xl font-semibold text-white">Check your email to verify your account.</h2>
                    <p className="mt-2 text-sm leading-6 text-emerald-100/90">
                      We sent a verification link to <span className="font-medium">{email.trim()}</span>. Once it is confirmed, sign in and you will land in the app.
                    </p>
                  </div>
                </div>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <Link
                    to="/login"
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-zinc-100"
                  >
                    <ArrowRight className="h-4 w-4" />
                    Go to sign in
                  </Link>
                  <Link
                    to="/pricing"
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-zinc-100 transition hover:bg-white/10"
                  >
                    View pricing
                  </Link>
                </div>
              </div>
            ) : (
              <>
                <div className="mb-6 flex items-center justify-between">
                  <div>
                    <h2 className="text-2xl font-semibold tracking-tight text-white">Create account</h2>
                    <p className="mt-1 text-sm text-zinc-400">Register with an email address and username for the consumer backend.</p>
                  </div>
                  <UserRoundPlus className="h-5 w-5 text-fuchsia-300" />
                </div>

                {error && (
                  <div className="mb-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100" role="alert">
                    <div className="flex items-start gap-2">
                      <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>{error}</span>
                    </div>
                  </div>
                )}

                <form className="space-y-4" onSubmit={handleSubmit}>
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-zinc-200">Full name</span>
                    <input
                      type="text"
                      autoComplete="name"
                      value={fullName}
                      onChange={(event) => setFullName(event.target.value)}
                      className="w-full rounded-xl border border-white/10 bg-zinc-950 px-4 py-3 text-white outline-none transition placeholder:text-zinc-500 focus:border-fuchsia-500/60"
                      placeholder="Optional"
                    />
                  </label>

                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-zinc-200">Email</span>
                    <input
                      type="email"
                      autoComplete="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      required
                      className="w-full rounded-xl border border-white/10 bg-zinc-950 px-4 py-3 text-white outline-none transition placeholder:text-zinc-500 focus:border-fuchsia-500/60"
                      placeholder="you@example.com"
                    />
                  </label>

                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-zinc-200">Username</span>
                    <input
                      type="text"
                      autoComplete="username"
                      value={username}
                      onChange={(event) => setUsername(event.target.value)}
                      required
                      minLength={3}
                      maxLength={30}
                      pattern="[A-Za-z0-9_]+"
                      className="w-full rounded-xl border border-white/10 bg-zinc-950 px-4 py-3 text-white outline-none transition placeholder:text-zinc-500 focus:border-fuchsia-500/60"
                      placeholder="username_123"
                    />
                  </label>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <span className="mb-2 block text-sm font-medium text-zinc-200">Password</span>
                      <input
                        type="password"
                        autoComplete="new-password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        required
                        minLength={8}
                        className="w-full rounded-xl border border-white/10 bg-zinc-950 px-4 py-3 text-white outline-none transition placeholder:text-zinc-500 focus:border-fuchsia-500/60"
                        placeholder="Minimum 8 characters"
                      />
                    </label>
                    <label className="block">
                      <span className="mb-2 block text-sm font-medium text-zinc-200">Confirm password</span>
                      <input
                        type="password"
                        autoComplete="new-password"
                        value={confirmPassword}
                        onChange={(event) => setConfirmPassword(event.target.value)}
                        required
                        minLength={8}
                        className="w-full rounded-xl border border-white/10 bg-zinc-950 px-4 py-3 text-white outline-none transition placeholder:text-zinc-500 focus:border-fuchsia-500/60"
                        placeholder="Repeat password"
                      />
                    </label>
                  </div>

                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-fuchsia-500 to-violet-500 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-fuchsia-500/20 transition hover:from-fuchsia-400 hover:to-violet-400 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <ArrowRight className="h-4 w-4" />
                    {isSubmitting ? 'Creating account...' : 'Create account'}
                  </button>
                </form>

                <div className="mt-5 flex items-center justify-between border-t border-white/10 pt-5 text-sm text-zinc-400">
                  <span>Already have an account?</span>
                  <Link to="/login" className="font-medium text-fuchsia-200 hover:text-fuchsia-100">
                    Sign in
                  </Link>
                </div>
              </>
            )}
          </section>
        </main>
      </div>
    </div>
  );
};

export default Signup;
