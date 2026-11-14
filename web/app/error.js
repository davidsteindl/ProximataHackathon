"use client";

import { StatePanel, WorkShell } from "./shell";

export default function Error({ reset }) {
  return (
    <WorkShell>
      <section className="panel">
        <StatePanel kind="error" heading="h1" title="This view could not be shown"
          action={<button type="button" className="btn btn-acc" onClick={() => reset()}>Retry</button>}>
          The data may be stale or the API unreachable. No decision was recorded by this error.
        </StatePanel>
      </section>
    </WorkShell>
  );
}
