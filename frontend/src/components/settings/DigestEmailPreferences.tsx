import { useEffect, useState } from 'react';
import { useOrg } from '../../contexts/OrgContext';
import { config } from '../../config';

interface Preferences {
  email_daily_digest: boolean;
  email_weekly_digest: boolean;
  weekly_digest_email: boolean;
  organization_email_enabled: boolean;
}

export default function DigestEmailPreferences() {
  const { activeOrganization } = useOrg();
  // Remount on workspace changes so responses from an old org cannot replace this view.
  return <PreferenceForm key={activeOrganization?.slug || ''} slug={activeOrganization?.slug} />;
}

function PreferenceForm({ slug }: { slug?: string }) {
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!slug) return;
    const controller = new AbortController();
    setError('');
    fetch(`${config.apiBaseUrl}/api/digests/preferences`, {
      headers: { 'X-MeetingOps-Org': slug }, signal: controller.signal,
    }).then(async response => {
      if (!response.ok) throw new Error();
      const data: Preferences = await response.json();
      if (!controller.signal.aborted) setPreferences(data);
    }).catch(() => {
      if (!controller.signal.aborted) setError('Could not load email preferences.');
    });
    return () => controller.abort();
  }, [slug, attempt]);

  async function update(field: 'email_daily_digest' | 'email_weekly_digest', checked: boolean) {
    if (!slug) return;
    setSaving(true);
    setSaved(false);
    setError('');
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/digests/preferences`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-MeetingOps-Org': slug },
        body: JSON.stringify({ [field]: checked }),
      });
      if (!response.ok) throw new Error();
      setPreferences(await response.json());
      setSaved(true);
    } catch {
      setError('Could not save email preferences. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-label="Digest email preferences" className="rounded-lg border border-zinc-700 bg-zinc-900 p-4 text-zinc-200 space-y-3">
      <h2 className="font-semibold">Digest email preferences</h2>
      <p className="text-sm text-zinc-400">Digests live in Meeting-Ops. Email is optional. These preferences follow your account across workspaces.</p>
      {!preferences && !error && <p role="status">Loading email preferences…</p>}
      {preferences && <>
        {(['daily', 'weekly'] as const).map(cadence => (
          <label key={cadence} className="flex items-center gap-3 min-h-11 cursor-pointer text-sm">
            <input type="checkbox" className="h-5 w-5 accent-fuchsia-500" disabled={saving}
              checked={preferences[`email_${cadence}_digest`]}
              onChange={event => update(`email_${cadence}_digest`, event.target.checked)} />
            Email me the {cadence} digest
          </label>
        ))}
        {!preferences.organization_email_enabled && <p className="text-sm text-amber-300">Digest email is disabled for this workspace. Your preferences are saved, but no email will be sent here until an admin enables it.</p>}
      </>}
      {error && <div role="alert" className="text-sm text-red-300">{error} {!preferences && <button className="underline" onClick={() => setAttempt(value => value + 1)}>Retry preferences</button>}</div>}
      <p role="status" className="text-sm text-zinc-400">{saving ? 'Saving…' : saved ? 'Email preferences saved.' : ''}</p>
    </section>
  );
}
