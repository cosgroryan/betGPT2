import { getTrackerHistory } from "@/lib/api";
import TrackerClient from "@/components/TrackerClient";

export const revalidate = 60;

export default async function TrackerPage() {
  let data = { bets: [], summary: null };
  try {
    data = await getTrackerHistory(100) as typeof data;
  } catch {
    // API offline
  }

  return <TrackerClient data={data} />;
}
