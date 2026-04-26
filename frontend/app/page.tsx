import { getValueToday, getMeetingsToday } from "@/lib/api";
import DashboardClient from "@/components/DashboardClient";

export const revalidate = 60;

export default async function DashboardPage() {
  let valueData = { opportunities: [] as Awaited<ReturnType<typeof getValueToday>>["opportunities"], count: 0 };
  let meetingsData = { meetings: [] as Awaited<ReturnType<typeof getMeetingsToday>>["meetings"], date: "" };

  try {
    [valueData, meetingsData] = await Promise.all([getValueToday(), getMeetingsToday()]);
  } catch {
    // API not running yet — render with empty data
  }

  return <DashboardClient initialValue={valueData} initialMeetings={meetingsData} />;
}
