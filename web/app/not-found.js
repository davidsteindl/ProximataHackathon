import Link from "next/link";
import { StatePanel, WorkShell } from "./shell";

export default function NotFound() {
  return (
    <WorkShell>
      <section className="panel">
        <StatePanel kind="error" heading="h1" title="This page does not exist" action={<Link className="btn btn-acc" href="/">Back to the overview</Link>}>
          Check the link. Nothing was changed.
        </StatePanel>
      </section>
    </WorkShell>
  );
}
