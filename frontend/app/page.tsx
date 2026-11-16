import Link from "next/link";

export default function Home() {
  return (
    <main className="relative flex min-h-dvh flex-col overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(77,163,255,0.2),transparent_58%)]" />
      <header className="relative flex items-center justify-between px-6 py-5 text-[11px] tracking-[0.22em] text-sky-100/60 uppercase">
        <span>NASA Space Apps 2026</span>
        <span>Earth observation</span>
      </header>
      <section className="relative flex flex-1 flex-col items-center justify-center px-6 pb-16 text-center">
        <p className="text-sm tracking-[0.28em] text-sky-300 uppercase">
          Geospatial Autonomous Intelligence
        </p>
        <h1 className="mt-4 text-7xl font-semibold tracking-tight sm:text-8xl">
          GAIA
        </h1>
        <p className="mt-6 max-w-xl text-lg leading-relaxed text-sky-100/75">
          Anomaly and trend discovery for the Earth system. Agents scan NASA
          data, then identify statistical associations between those changes.
        </p>
        <Link
          href="/dashboard"
          className="mt-10 inline-flex h-12 items-center rounded-full bg-accent px-7 text-sm font-semibold text-slate-950 transition-colors hover:bg-sky-300"
        >
          Launch GAIA
        </Link>
      </section>
    </main>
  );
}
