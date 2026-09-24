import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Contact, Plus, RefreshCw, Search, UserX } from 'lucide-react';

/**
 * SpeakerCombobox — the search-first speaker picker (2026-09-24).
 *
 * Replaces the native <select> that listed EVERY speaker profile in the
 * workspace (139 on dogfood, 118 of them lookalike "Speaker XXXX" handles),
 * where one slip picked the wrong person and kicked off a re-summary.
 *
 * - Nothing is picked by hovering or by an empty Enter: the user types, then
 *   clicks or presses Enter on a highlighted row.
 * - Unnamed auto voiceprints are hidden unless the search matches them.
 * - With `searchContacts`, Contact-Ops people appear in the same list, so
 *   naming a voice and linking it to a contact is one pick.
 */

export interface PickerSpeaker {
  id: number;
  display_name: string;
  has_centroid?: boolean;
  auto_generated?: boolean;
  contact_id?: string | null;
  email?: string | null;
  company?: string | null;
  updated_at?: string | null;
}

export interface PickerContact {
  person_id: string;
  display_name: string;
  email?: string | null;
}

export type PickerChoice =
  | { kind: 'speaker'; speaker: PickerSpeaker }
  /** `speaker` = an existing profile to reuse (already linked to this
   *  contact, or the same name with no contact yet). */
  | { kind: 'contact'; contact: PickerContact; speaker?: PickerSpeaker }
  | { kind: 'create'; name: string }
  | { kind: 'clear' };

interface Option {
  key: string;
  group: string;
  choice: PickerChoice;
  primary: string;
  secondary?: string;
  badge?: string;
}

interface Props {
  /** Accessible name, e.g. "Speaker for SPEAKER_01". */
  label: string;
  speakers: PickerSpeaker[];
  /** Currently assigned profile id (null = unknown). */
  value: number | null;
  /** Self-introduction names heard in this voice ("Hi, I'm Dana"). */
  suggestions?: string[];
  /** Contact-Ops people search; omit to hide the Contacts section. */
  searchContacts?: (q: string) => Promise<PickerContact[]>;
  onPick: (choice: PickerChoice) => void;
  disabled?: boolean;
  busy?: boolean;
  /** Render the search box and list in place (inside an existing popover)
   *  instead of behind a trigger button. */
  inline?: boolean;
  /** Rows shown before the user types. */
  idleLimit?: number;
}

const norm = (s: string | null | undefined) => (s || '').trim().toLocaleLowerCase();

/** 0 = name starts with q, 1 = a word in the name does, 2 = contains, 3 = other field. */
const score = (s: PickerSpeaker, q: string): number | null => {
  const name = norm(s.display_name);
  if (name.startsWith(q)) return 0;
  if (name.split(/\s+/).some(w => w.startsWith(q))) return 1;
  if (name.includes(q)) return 2;
  if (norm(s.email).includes(q) || norm(s.company).includes(q)) return 3;
  return null;
};

const CONTACT_DEBOUNCE_MS = 250;

export const SpeakerCombobox: React.FC<Props> = ({
  label,
  speakers,
  value,
  suggestions = [],
  searchContacts,
  onPick,
  disabled = false,
  busy = false,
  inline = false,
  idleLimit = 8,
}) => {
  const [open, setOpen] = useState(inline);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(-1);
  const [contacts, setContacts] = useState<PickerContact[]>([]);
  const [contactState, setContactState] = useState<'idle' | 'loading' | 'error'>('idle');
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const current = speakers.find(s => s.id === value) || null;
  const q = norm(query);

  // Contact-Ops search, debounced; stale responses are dropped.
  useEffect(() => {
    if (!searchContacts || !open || q.length < 2) {
      setContacts([]);
      setContactState('idle');
      return;
    }
    let cancelled = false;
    setContactState('loading');
    const t = window.setTimeout(() => {
      searchContacts(query.trim())
        .then(found => { if (!cancelled) { setContacts(found); setContactState('idle'); } })
        .catch(() => { if (!cancelled) { setContacts([]); setContactState('error'); } });
    }, CONTACT_DEBOUNCE_MS);
    return () => { cancelled = true; window.clearTimeout(t); };
  }, [q, open, searchContacts]); // eslint-disable-line react-hooks/exhaustive-deps

  const options = useMemo<Option[]>(() => {
    const out: Option[] = [];
    const named = speakers.filter(s => !s.auto_generated);
    const byName = new Map(named.map(s => [norm(s.display_name), s]));
    const byContact = new Map(
      speakers.filter(s => s.contact_id).map(s => [s.contact_id as string, s]),
    );
    const speakerRow = (s: PickerSpeaker, group: string): Option => ({
      key: `s${s.id}`,
      group,
      choice: { kind: 'speaker', speaker: s },
      primary: s.display_name,
      secondary: [s.email, s.company].filter(Boolean).join(' · ') || undefined,
      badge: s.id === value ? 'current' : s.contact_id ? 'contact' : s.auto_generated ? 'unnamed' : undefined,
    });

    if (!q) {
      const seen = new Set<string>();
      for (const name of suggestions) {
        const k = norm(name);
        if (!k || seen.has(k)) continue;
        seen.add(k);
        const hit = byName.get(k);
        out.push(hit ? speakerRow(hit, 'Heard in this meeting') : {
          key: `sug-${k}`,
          group: 'Heard in this meeting',
          choice: { kind: 'create', name: name.trim() },
          primary: `Create “${name.trim()}”`,
          secondary: 'New speaker from their self-introduction',
        });
      }
      const recent = [...named]
        .filter(s => !seen.has(norm(s.display_name)))
        .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '') || a.display_name.localeCompare(b.display_name))
        .slice(0, idleLimit);
      recent.forEach(s => out.push(speakerRow(s, 'Recent people')));
    } else {
      const ranked = (list: PickerSpeaker[]) => list
        .map(s => ({ s, r: score(s, q) }))
        .filter((x): x is { s: PickerSpeaker; r: number } => x.r !== null)
        .sort((a, b) => a.r - b.r || a.s.display_name.localeCompare(b.s.display_name))
        .map(x => x.s);
      ranked(named).slice(0, 30).forEach(s => out.push(speakerRow(s, 'People')));
      ranked(speakers.filter(s => s.auto_generated)).slice(0, 10)
        .forEach(s => out.push(speakerRow(s, 'Unnamed voiceprints')));
      for (const c of contacts) {
        const linked = byContact.get(c.person_id);
        if (linked && out.some(o => o.key === `s${linked.id}`)) continue;
        const sameName = !linked ? byName.get(norm(c.display_name)) : undefined;
        const reuse = linked || (sameName && !sameName.contact_id ? sameName : undefined);
        out.push({
          key: `c${c.person_id}`,
          group: 'Contacts',
          choice: { kind: 'contact', contact: c, speaker: reuse },
          primary: c.display_name,
          secondary: c.email || undefined,
          badge: reuse ? 'link' : 'new',
        });
      }
      if (!byName.has(q)) {
        out.push({
          key: 'create',
          group: '',
          choice: { kind: 'create', name: query.trim() },
          primary: `Create “${query.trim()}”`,
          secondary: 'New speaker',
        });
      }
    }
    if (value !== null) {
      out.push({ key: 'clear', group: '', choice: { kind: 'clear' }, primary: 'Mark as unknown' });
    }
    return out;
  }, [speakers, suggestions, contacts, q, query, value, idleLimit]);

  // Typing highlights the best match; an empty box highlights nothing, so a
  // stray Enter can't assign anyone.
  useEffect(() => { setActive(q ? 0 : -1); }, [q, options.length]);

  useEffect(() => {
    if (!open || inline) return;
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) close();
    };
    document.addEventListener('pointerdown', onDown);
    return () => document.removeEventListener('pointerdown', onDown);
  }, [open, inline]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);

  const close = () => {
    if (inline) return;
    setOpen(false);
    setQuery('');
  };

  const pick = (opt: Option) => {
    onPick(opt.choice);
    setQuery('');
    close();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive(i => (options.length ? (i + 1) % options.length : -1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive(i => (options.length ? (i <= 0 ? options.length - 1 : i - 1) : -1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (active >= 0 && options[active]) pick(options[active]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      if (query) setQuery(''); else close();
    }
  };

  const panel = (
    <div
      className={inline
        ? 'flex flex-col gap-1'
        : 'absolute left-0 right-0 top-full z-30 mt-1 min-w-[18rem] rounded-lg border border-gray-200 bg-white p-2 shadow-lg'}
    >
      <label className="relative block">
        <span className="sr-only">{`Search people for ${label}`}</span>
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-label={`Search people for ${label}`}
          aria-expanded={true}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 && options[active] ? `${listId}-${options[active].key}` : undefined}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled || busy}
          placeholder={searchContacts ? 'Type a name, email or company…' : 'Type a name…'}
          className="w-full rounded-md border border-purple-300 bg-white py-1.5 pl-8 pr-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-200 disabled:opacity-50"
        />
      </label>
      <ul id={listId} role="listbox" aria-label={label} className="mt-1 max-h-72 overflow-y-auto">
        {options.map((opt, i) => {
          const header = opt.group && (i === 0 || options[i - 1].group !== opt.group) ? opt.group : null;
          const isActive = i === active;
          const Icon = opt.choice.kind === 'contact' ? Contact
            : opt.choice.kind === 'create' ? Plus
              : opt.choice.kind === 'clear' ? UserX : null;
          return (
            <React.Fragment key={opt.key}>
              {header && (
                <li role="presentation" className="px-2 pb-0.5 pt-2 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                  {header}
                </li>
              )}
              {!opt.group && i > 0 && options[i - 1].group && (
                <li role="presentation" className="my-1 border-t border-gray-100" />
              )}
              <li
                id={`${listId}-${opt.key}`}
                role="option"
                aria-selected={isActive}
                onMouseDown={e => e.preventDefault()}
                onClick={() => pick(opt)}
                onMouseMove={() => setActive(i)}
                className={`flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm ${
                  isActive ? 'bg-purple-600 text-white' : 'text-gray-800 hover:bg-purple-50'
                }`}
              >
                {Icon ? <Icon className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden="true" />
                  : <span className="h-3.5 w-3.5 shrink-0" aria-hidden="true">
                    {opt.badge === 'current' && <Check className="h-3.5 w-3.5" />}
                  </span>}
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{opt.primary}</span>
                  {opt.secondary && (
                    <span className={`block truncate text-[11px] ${isActive ? 'text-purple-100' : 'text-gray-500'}`}>
                      {opt.secondary}
                    </span>
                  )}
                </span>
                {opt.badge && opt.badge !== 'current' && (
                  <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] ${
                    isActive ? 'bg-white/20 text-white' : 'bg-gray-100 text-gray-600'
                  }`}>
                    {opt.badge === 'contact' ? 'Contact-Ops'
                      : opt.badge === 'link' ? 'link to speaker'
                        : opt.badge === 'new' ? 'new speaker'
                          : opt.badge}
                  </span>
                )}
              </li>
            </React.Fragment>
          );
        })}
        {searchContacts && q.length >= 2 && contactState === 'loading' && (
          <li role="presentation" className="flex items-center gap-1.5 px-2 py-1.5 text-xs text-gray-500">
            <RefreshCw className="h-3 w-3 animate-spin" /> Searching contacts…
          </li>
        )}
        {searchContacts && contactState === 'error' && (
          <li role="presentation" className="px-2 py-1.5 text-xs text-amber-700">
            Contact-Ops search is unavailable right now; people and new names still work.
          </li>
        )}
        {!q && (
          <li role="presentation" className="px-2 pb-1 pt-2 text-[11px] text-gray-500">
            {`Type to search all ${speakers.filter(s => !s.auto_generated).length} people`}
            {searchContacts ? ' and your contacts' : ''}.
          </li>
        )}
      </ul>
    </div>
  );

  if (inline) return <div ref={rootRef}>{panel}</div>;

  return (
    <div ref={rootRef} className="relative min-w-0 flex-1">
      <button
        type="button"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled || busy}
        onClick={() => (open ? close() : setOpen(true))}
        className="flex w-full items-center gap-2 rounded border border-gray-300 bg-white px-2 py-1 text-left text-sm text-gray-900 hover:border-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
      >
        <span className={`min-w-0 flex-1 truncate ${current ? '' : 'text-gray-500'}`}>
          {current ? current.display_name : 'Unknown — choose a person'}
        </span>
        {current?.contact_id && (
          <span className="shrink-0 rounded bg-purple-50 px-1.5 py-0.5 text-[10px] text-purple-700">Contact-Ops</span>
        )}
        {busy ? <RefreshCw className="h-3.5 w-3.5 shrink-0 animate-spin text-gray-400" />
          : <ChevronDown className="h-3.5 w-3.5 shrink-0 text-gray-400" />}
      </button>
      {open && panel}
    </div>
  );
};

export default SpeakerCombobox;
