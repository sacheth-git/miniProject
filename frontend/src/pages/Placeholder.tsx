export function Placeholder({ title, note }: { title: string; note: string }) {
  return (
    <section className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{note}</p>
    </section>
  );
}
