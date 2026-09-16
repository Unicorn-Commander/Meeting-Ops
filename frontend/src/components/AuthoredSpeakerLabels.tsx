/** Labels supplied with authored text are not voice identity evidence. */
export default function AuthoredSpeakerLabels({ speakers }: { speakers: string[] }) {
  return <section className="rounded-lg border border-slate-300 bg-slate-50 p-5 text-slate-900">
    <h2 className="text-lg font-semibold">Authored speaker labels</h2>
    <p className="mt-1 text-sm">These labels were supplied by the editor. No audio samples or verified voice identities are available.</p>
    <ul className="mt-3 space-y-1">{speakers.map(speaker => <li key={speaker}>{speaker}</li>)}</ul>
  </section>;
}
