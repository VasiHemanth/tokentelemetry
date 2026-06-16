interface VideoEmbedProps {
  /** YouTube video ID (e.g. "dQw4w9WgXcQ") */
  id: string;
  /** Accessible title for the iframe */
  title?: string;
}

/**
 * Renders a responsive 16:9 YouTube embed.
 * Use in MDX as: <VideoEmbed id="YOUTUBE_ID" title="Optional title" />
 */
export default function VideoEmbed({ id, title = "Video walkthrough" }: VideoEmbedProps) {
  return (
    <div
      style={{
        position: "relative",
        paddingBottom: "56.25%", // 16:9 ratio
        height: 0,
        overflow: "hidden",
        borderRadius: "10px",
        marginBlock: "1.5rem",
      }}
    >
      <iframe
        src={`https://www.youtube.com/embed/${id}`}
        title={title}
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          border: 0,
        }}
      />
    </div>
  );
}
