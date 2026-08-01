"use client";

import { useState } from "react";
import { track } from "@/lib/track";

interface VideoEmbedProps {
  /** YouTube video ID (e.g. "dQw4w9WgXcQ") */
  id: string;
  /** Accessible title for the iframe */
  title?: string;
}

/**
 * Responsive 16:9 YouTube embed using a click-to-load facade: we show the
 * thumbnail until the visitor clicks play, then swap in the (autoplaying)
 * iframe. This lets us fire a real `doc_video_play` analytics event on play
 * (a cross-origin iframe can't be observed otherwise) and avoids loading the
 * heavy YouTube player until it's actually wanted.
 *
 * Use in MDX as: <VideoEmbed id="YOUTUBE_ID" title="Optional title" />
 */
export default function VideoEmbed({ id, title = "Video walkthrough" }: VideoEmbedProps) {
  const [playing, setPlaying] = useState(false);

  return (
    <div
      style={{
        position: "relative",
        paddingBottom: "56.25%", // 16:9 ratio
        height: 0,
        overflow: "hidden",
        borderRadius: "10px",
        marginBlock: "1.5rem",
        background: "#000",
      }}
    >
      {playing ? (
        <iframe
          src={`https://www.youtube-nocookie.com/embed/${id}?autoplay=1`}
          title={title}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", border: 0 }}
        />
      ) : (
        <button
          type="button"
          aria-label={`Play: ${title}`}
          onClick={() => {
            track("doc_video_play", { id, title });
            setPlaying(true);
          }}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            border: 0,
            padding: 0,
            cursor: "pointer",
            backgroundColor: "#000",
            backgroundImage: `url(https://i.ytimg.com/vi/${id}/hqdefault.jpg)`,
            backgroundSize: "cover",
            backgroundPosition: "center",
            display: "grid",
            placeItems: "center",
          }}
        >
          <span
            aria-hidden
            style={{
              display: "grid",
              placeItems: "center",
              width: 64,
              height: 44,
              borderRadius: 10,
              background: "rgba(0,0,0,0.65)",
              color: "#fff",
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M8 5v14l11-7z" />
            </svg>
          </span>
        </button>
      )}
    </div>
  );
}
