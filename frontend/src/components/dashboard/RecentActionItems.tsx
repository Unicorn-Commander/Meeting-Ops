import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { CheckSquare, User } from 'lucide-react';
import type { DashboardSession } from '../../pages/Dashboard';
import { extractActionItems, type NormalizedActionItem } from './actionItems';

interface RecentActionItemsProps {
  sessions: DashboardSession[];
  loading: boolean;
  detailsLoading: boolean;
}

export const RecentActionItems: React.FC<RecentActionItemsProps> = ({
  sessions,
  loading,
  detailsLoading,
}) => {
  const items = useMemo<NormalizedActionItem[]>(() => {
    const all: NormalizedActionItem[] = [];
    for (const session of sessions) {
      const extracted = extractActionItems(session as any);
      all.push(...extracted);
    }
    all.sort((a, b) => {
      const ta = a.sessionCreatedAt ? new Date(a.sessionCreatedAt).getTime() : 0;
      const tb = b.sessionCreatedAt ? new Date(b.sessionCreatedAt).getTime() : 0;
      return tb - ta;
    });
    return all.slice(0, 5);
  }, [sessions]);

  const isLoading = loading || detailsLoading;

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/50">
      <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-300">
          Recent action items
        </h2>
        <Link
          to="/sessions"
          className="text-xs font-medium text-fuchsia-300 transition hover:text-fuchsia-200"
        >
          View all
        </Link>
      </header>

      <div className="divide-y divide-zinc-800/80">
        {isLoading && items.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-zinc-500">Loading action items…</div>
        ) : items.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-zinc-500">
            No action items captured yet. They appear here once a meeting summary completes.
          </div>
        ) : (
          items.map((item, idx) => (
            <div key={`${item.sessionId}-${idx}`} className="px-4 py-3">
              <div className="flex items-start gap-3">
                <CheckSquare className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-300" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-zinc-100">{item.text}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-zinc-500">
                    {item.owner && (
                      <span className="inline-flex items-center gap-1">
                        <User className="h-3 w-3" />
                        {item.owner}
                      </span>
                    )}
                    {item.dueDate && (
                      <span className="text-zinc-400">Due {item.dueDate}</span>
                    )}
                    <Link
                      to={`/sessions/${item.sessionId}`}
                      className="inline-flex max-w-[18ch] items-center gap-1 truncate rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-zinc-300 transition hover:border-fuchsia-500/40 hover:text-fuchsia-200"
                      title={item.sessionTitle}
                    >
                      {item.sessionTitle}
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
};
