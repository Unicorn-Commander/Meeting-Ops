import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Check,
  Sparkles,
  Users,
  Building2,
  ShieldCheck,
  BrainCircuit,
  Workflow,
  Database,
} from 'lucide-react';

type Plan = {
  name: string;
  price: string;
  priceSuffix?: string;
  note: string;
  features: string[];
  ctaLabel: string;
  ctaHref: string;
  highlight?: boolean;
};

const enterpriseMailto =
  'mailto:enterprise@meeting-ops.unicorncommander.ai?subject=UC-Meeting-Ops%20Enterprise%20inquiry&body=Please%20contact%20me%20about%20Enterprise.';

const plans: Plan[] = [
  {
    name: 'Free',
    price: '$0',
    priceSuffix: 'forever',
    note: 'Browser-only meeting transcription + summaries.',
    features: [
      'Unlimited meetings, no minute caps',
      'Your audio never leaves your device',
      'Local STT (Parakeet 0.6B) + on-device summaries (Qwen 3 0.6B)',
      'Local Sessions storage (IndexedDB)',
      'One-shot upload to a Pro org for shared meetings',
    ],
    ctaLabel: 'Get started',
    ctaHref: '/signup',
  },
  {
    name: 'Pro',
    price: '$12',
    priceSuffix: '/ month',
    note: 'Everything in Free, plus the server completion pass and ecosystem integrations.',
    features: [
      'Higher-accuracy server transcription (Parakeet 1.1B)',
      'Speaker diarization (pyannote 3.1)',
      'Longer-context summaries (Qwen 3.6 35B-A3B-Vision)',
      'Cross-device sync',
      'Brigade knowledge-graph integration',
      'Project-Ops action-items bridge',
      'Bulk import + server live transcription',
      'Speaker library + 4-week retention controls',
      'Per-session privacy toggle (browser-only on demand)',
    ],
    ctaLabel: 'Subscribe',
    ctaHref: '/pricing#subscribe',
    highlight: true,
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    note: 'On-prem appliance, HIPAA perimeter, BYOK, dedicated graph.',
    features: [
      'On-prem appliance build',
      'HIPAA perimeter mode',
      'BYOK provider routing (OpenAI / Anthropic / Azure OpenAI / your LiteLLM)',
      'Dedicated Brigade graph instance',
      'Multi-org admin',
      'SSO via OIDC',
      'Enterprise SLA',
    ],
    ctaLabel: 'Talk to us',
    ctaHref: enterpriseMailto,
  },
];

const iconByPlan = {
  Free: <Sparkles className="h-5 w-5 text-fuchsia-300" />,
  Pro: <BrainCircuit className="h-5 w-5 text-fuchsia-300" />,
  Enterprise: <Building2 className="h-5 w-5 text-fuchsia-300" />,
} as const;

export const Pricing: React.FC = () => {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto w-full max-w-6xl px-4 py-6 lg:px-8">
        <header className="flex items-center justify-between border-b border-white/10 pb-4">
          <Link to="/login" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-fuchsia-500 to-violet-500 shadow-lg shadow-fuchsia-500/20">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight text-white">Meeting-Ops</div>
              <div className="text-xs text-zinc-400">Pricing</div>
            </div>
          </Link>
          <div className="flex items-center gap-2">
            <Link
              to="/login"
              className="rounded-full border border-white/10 px-3 py-2 text-sm text-zinc-300 transition hover:border-fuchsia-400/40 hover:text-white"
            >
              Sign in
            </Link>
            <Link
              to="/signup"
              className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-2 text-sm text-zinc-100 transition hover:bg-white/10"
            >
              <ArrowRight className="h-4 w-4" />
              Sign up
            </Link>
          </div>
        </header>

        <main className="py-10">
          <div className="max-w-3xl space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-fuchsia-500/30 bg-fuchsia-500/10 px-3 py-1 text-xs font-medium text-fuchsia-200">
              <Users className="h-3.5 w-3.5" />
              Free, Pro, and Enterprise
            </div>
            <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Choose the tier that matches how you work.
            </h1>
            <p className="max-w-2xl text-base leading-7 text-zinc-300">
              Free is browser-only and stays that way — your audio never leaves your device,
              and there are no minute caps. Pro adds an optional server completion pass for
              higher-accuracy transcription, speaker diarization, longer-context summaries,
              and the integrations that connect meetings to the rest of your workspace.
              Enterprise is the on-prem path.
            </p>
          </div>

          <div className="mt-10 grid gap-4 lg:grid-cols-3">
            {plans.map((plan) => (
              <article
                key={plan.name}
                className={`rounded-3xl border p-6 shadow-xl shadow-black/20 ${
                  plan.highlight
                    ? 'border-fuchsia-400/40 bg-fuchsia-500/10'
                    : 'border-white/10 bg-zinc-900/70'
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      {iconByPlan[plan.name as keyof typeof iconByPlan]}
                      <h2 className="text-xl font-semibold text-white">{plan.name}</h2>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <div className="text-3xl font-semibold tracking-tight text-white">
                        {plan.price}
                      </div>
                      {plan.priceSuffix && (
                        <div className="text-sm text-zinc-400">{plan.priceSuffix}</div>
                      )}
                    </div>
                    <div className="text-sm text-zinc-400">{plan.note}</div>
                  </div>
                  {plan.highlight && (
                    <span className="rounded-full border border-fuchsia-400/40 bg-fuchsia-400/10 px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-fuchsia-100">
                      Most popular
                    </span>
                  )}
                </div>

                <ul className="mt-6 space-y-3 text-sm text-zinc-300">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-fuchsia-300" />
                      <span className="leading-6">{feature}</span>
                    </li>
                  ))}
                </ul>

                <div className="mt-6">
                  {plan.ctaHref.startsWith('mailto:') ? (
                    <a
                      href={plan.ctaHref}
                      className={`inline-flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold transition ${
                        plan.highlight
                          ? 'bg-white text-zinc-950 hover:bg-zinc-100'
                          : 'border border-white/10 bg-white/5 text-zinc-100 hover:bg-white/10'
                      }`}
                    >
                      {plan.ctaLabel}
                      <ArrowRight className="h-4 w-4" />
                    </a>
                  ) : plan.ctaHref.startsWith('#') || plan.ctaHref.includes('#') ? (
                    <a
                      href={plan.ctaHref}
                      className={`inline-flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold transition ${
                        plan.highlight
                          ? 'bg-white text-zinc-950 hover:bg-zinc-100'
                          : 'border border-white/10 bg-white/5 text-zinc-100 hover:bg-white/10'
                      }`}
                    >
                      {plan.ctaLabel}
                      <ArrowRight className="h-4 w-4" />
                    </a>
                  ) : (
                    <Link
                      to={plan.ctaHref}
                      className={`inline-flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold transition ${
                        plan.highlight
                          ? 'bg-white text-zinc-950 hover:bg-zinc-100'
                          : 'border border-white/10 bg-white/5 text-zinc-100 hover:bg-white/10'
                      }`}
                    >
                      {plan.ctaLabel}
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  )}
                </div>
              </article>
            ))}
          </div>

          <section
            id="subscribe"
            className="mt-8 rounded-3xl border border-white/10 bg-white/5 p-6"
          >
            <div className="grid gap-4 md:grid-cols-3">
              <div className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-fuchsia-300" />
                <div>
                  <h3 className="font-medium text-white">Free stays private.</h3>
                  <p className="mt-1 text-sm leading-6 text-zinc-300">
                    Browser-only, forever. No minute caps. Audio and transcripts stay on
                    your device.
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Workflow className="mt-0.5 h-5 w-5 shrink-0 text-fuchsia-300" />
                <div>
                  <h3 className="font-medium text-white">Pro is the upgrade path.</h3>
                  <p className="mt-1 text-sm leading-6 text-zinc-300">
                    Server completion pass, cross-device sync, knowledge-graph and
                    action-item integrations. Per-session privacy toggle if you want
                    one meeting browser-only.
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Database className="mt-0.5 h-5 w-5 shrink-0 text-fuchsia-300" />
                <div>
                  <h3 className="font-medium text-white">Enterprise is on-prem.</h3>
                  <p className="mt-1 text-sm leading-6 text-zinc-300">
                    HIPAA perimeter, BYOK routing, dedicated Brigade graph, SSO, SLA.
                  </p>
                </div>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
};

export default Pricing;
