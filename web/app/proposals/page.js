import Link from "next/link";
import { StatePanel, WorkShell } from "../shell";

export const metadata = { title: "Proposals" };

export default function ProposalsPage() {
  return (
    <WorkShell current="flags">
      <div className="page-head"><h1>Proposals</h1><span className="chip t-info">LLM proposal · advisory</span></div>
      <section className="panel">
        <StatePanel kind="unavailable" title="Proposals are not available yet" action={<Link className="btn" href="/flags">Back to the flag inbox</Link>}>
          Advisory LLM proposals and their approve/reject decision arrive with #13. Until then nothing can be approved, and no schedule change or notification happens here.
        </StatePanel>
      </section>
    </WorkShell>
  );
}
