import Link from "next/link";
import { StatePanel, WorkShell } from "../shell";

export const metadata = { title: "No dashboard chat" };

// Kept only for old links: #19 was rescoped to a Q&A core for Telegram, without a dashboard chat (PLAN §4).
export default function ChatPage() {
  return (
    <WorkShell>
      <section className="panel">
        <StatePanel kind="unavailable" heading="h1" title="There is no chat in the dashboard" action={<Link className="btn" href="/">Back to the overview</Link>}>
          Crews ask questions in Telegram, where answers come from the site record with sources. External agents connect through the MCP endpoint. The room view, Flag details and the activity feed show the same facts here.
        </StatePanel>
      </section>
    </WorkShell>
  );
}
