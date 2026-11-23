// The maker's AI research channels, shown once in the app and listed on the
// website's Resources page. Plain links only: nothing is fetched from these
// sites, so the app makes no new network calls.

export type ResearchChannel = {
  name: string;
  platform: "YouTube" | "Instagram";
  url: string;
  summary: string;
};

export const RESEARCH_CHANNELS: ResearchChannel[] = [
  {
    name: "Hemanth with AI",
    platform: "YouTube",
    url: "https://www.youtube.com/@hemanth_with_ai/shorts",
    summary: "AI research explained in short videos.",
  },
  {
    name: "@hemanth.with.ai",
    platform: "Instagram",
    url: "https://www.instagram.com/hemanth.with.ai/",
    summary: "The same AI research, as reels.",
  },
  {
    name: "FasterFold AI",
    platform: "YouTube",
    url: "https://www.youtube.com/@fasterfold-ai",
    summary: "AI news and new techniques.",
  },
];

export const RESOURCES_URL = "https://tokentelemetry.com/resources";
