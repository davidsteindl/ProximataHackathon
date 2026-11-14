import { getSiteModel, getSiteState } from "../../lib/site-data.mjs";
import SiteView from "../site-view/site-view";

export const dynamic = "force-dynamic";

// The scene lives in this layout so it survives navigation between /site and /zones/<zoneId>.
export default async function SiteLayout({ children }) {
  const [model, state] = await Promise.all([
    getSiteModel(process.env.API_BASE_URL),
    getSiteState(process.env.API_BASE_URL),
  ]);
  return (
    <>
      <SiteView model={model.data} initialState={state.data} error={model.error || state.error} />
      {children}
    </>
  );
}
