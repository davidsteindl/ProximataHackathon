import Link from "next/link";
import { StatePanel, WorkShell } from "../shell";

export const metadata = { title: "Chat" };

export default function ChatPage() {
  return (
    <WorkShell current="chat">
      <div className="page-head"><h1>Ask GroundIQ</h1></div>
      <section className="panel">
        <StatePanel kind="unavailable" title="Chat is not available yet" action={<Link className="btn" href="/flags">Open the flag inbox</Link>}>
          The read-only chat agent arrives with #19. It will answer from the site record through the same MCP tools as any external agent, and it cannot confirm Evidence, approve Proposals or close Flags.
        </StatePanel>
      </section>
    </WorkShell>
  );
}
