import { Skeleton, WorkShell } from "./shell";

export default function Loading() {
  return (
    <WorkShell>
      <div className="grid-4">{[0, 1, 2, 3].map((i) => <div key={i} className="panel"><Skeleton rows={2} /></div>)}</div>
      <section className="panel" aria-label="Loading"><Skeleton label="Loading site data" /></section>
    </WorkShell>
  );
}
