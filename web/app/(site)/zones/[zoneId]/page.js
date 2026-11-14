export async function generateMetadata({ params }) {
  const { zoneId } = await params;
  return { title: `${decodeURIComponent(zoneId)} · Site model · SiteMind` };
}

// Rendered by the (site) layout, which derives isolation, camera and highlight from this URL.
export default function ZonePage() {
  return null;
}
