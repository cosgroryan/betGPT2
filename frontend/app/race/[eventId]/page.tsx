import { getRaceDetail } from "@/lib/api";
import RaceDetailClient from "@/components/RaceDetailClient";
import { notFound } from "next/navigation";

export const revalidate = 30;

export default async function RacePage({ params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;

  let raceData;
  try {
    raceData = await getRaceDetail(eventId);
  } catch {
    notFound();
  }

  return <RaceDetailClient data={raceData} />;
}
