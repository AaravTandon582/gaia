import type { StatusEvent } from "@/lib/api";

const SCOUTS = [{ id: "atmosphere", label: "Atmosphere" }, { id: "hydro", label: "Hydrosphere" }, { id: "cryo", label: "Cryosphere" }, { id: "bio", label: "Biosphere" }];
export function AgentStatus({ events, phase }: { events: StatusEvent[]; phase: string }) {
  return <aside className="min-h-0 overflow-auto border-r border-white/10 bg-panel p-4">
    <p className="text-[11px] tracking-[0.22em] text-sky-200/60 uppercase">Scouts</p>
    <h2 className="mt-1 font-medium">Agent status</h2>
    <p role="status" className="my-4 text-sm text-sky-200">{phase}</p>
    <ul className="space-y-3">{SCOUTS.map((scout) => {
      const latest = events.findLast((event) => event.agent.startsWith(`${scout.id}:`));
      return <li key={scout.id} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
        <div className="flex justify-between gap-2 text-sm"><span>{scout.label}</span><span className={latest?.status === "completed" ? "text-emerald-300" : "text-sky-300"}>{latest?.status ?? "idle"}</span></div>
        <p className="mt-2 text-xs text-sky-100/50">{latest?.status === "completed" ? latest.discovery_count ? `${latest.discovery_count} variables screened` : "No cached variables in this region" : latest?.status === "started" ? "Analyzing monthly observations…" : "Waiting for a region"}</p>
      </li>;
    })}</ul>
    <h3 className="mt-6 text-xs uppercase tracking-widest text-sky-100/50">Activity</h3>
    <ol className="mt-2 space-y-2 text-xs text-sky-100/65" aria-label="Scan activity">{events.slice(-12).map((event, i) => <li key={i}>{event.agent.split(":")[0]} · {event.status.replaceAll("_", " ")}</li>)}</ol>
  </aside>;
}
