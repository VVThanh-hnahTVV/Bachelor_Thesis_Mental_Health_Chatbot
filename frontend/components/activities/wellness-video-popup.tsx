"use client";

export type VideoSourceCredit = {
  name: string;
  url?: string | null;
  license?: string | null;
  attribution?: string | null;
};

const YOUTUBE_ID_RE = /^[\w-]{11}$/;
const YOUTUBE_URL_RE =
  /(?:youtube\.com\/(?:watch\?(?:[^&]+&)*v=|embed\/|shorts\/)|youtu\.be\/)([\w-]{11})/;

export function extractYoutubeId(
  youtubeId?: string | null,
  videoUrl?: string | null
): string | null {
  const idCandidate = youtubeId?.trim();
  if (idCandidate && YOUTUBE_ID_RE.test(idCandidate)) {
    return idCandidate;
  }

  const url = videoUrl?.trim();
  if (!url) return null;
  if (YOUTUBE_ID_RE.test(url)) return url;

  const match = url.match(YOUTUBE_URL_RE);
  return match?.[1] ?? null;
}

function isDirectVideoUrl(url: string): boolean {
  return /\.(mp4|webm|ogg|mov)(\?|$)/i.test(url);
}

interface WellnessVideoPopupProps {
  videoUrl?: string | null;
  youtubeId?: string | null;
  /** Accessible label for the player — not shown as duplicate body text. */
  videoTitle?: string;
  videoSource?: VideoSourceCredit | null;
}

export function WellnessVideoPopup({
  videoUrl,
  youtubeId,
  videoTitle,
  videoSource,
}: WellnessVideoPopupProps) {
  const ytId = extractYoutubeId(youtubeId, videoUrl);
  const directSrc = !ytId && videoUrl?.trim() && isDirectVideoUrl(videoUrl.trim())
    ? videoUrl.trim()
    : null;
  const playerLabel = videoTitle?.trim() || videoSource?.name || "Video thư giãn";

  return (
    <div className="space-y-3">
      {ytId ? (
        <div className="relative w-full overflow-hidden rounded-lg bg-black pt-[56.25%]">
          <iframe
            className="absolute inset-0 h-full w-full"
            src={`https://www.youtube.com/embed/${ytId}?rel=0&modestbranding=1`}
            title={playerLabel}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            referrerPolicy="strict-origin-when-cross-origin"
            allowFullScreen
          />
        </div>
      ) : directSrc ? (
        <video
          className="w-full max-h-[420px] rounded-lg bg-black"
          controls
          playsInline
          preload="metadata"
          src={directSrc}
        >
          Trình duyệt không hỗ trợ phát video.
        </video>
      ) : (
        <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          Video hiện không khả dụng. Vui lòng thử lại sau.
        </p>
      )}

      <p className="text-xs text-muted-foreground">
        Theo video hướng dẫn ở tốc độ phù hợp với bạn. Có thể tạm dừng hoặc dừng bất cứ
        lúc nào.
      </p>

      {videoSource ? (
        <div className="rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          {videoSource.attribution ? (
            <p>{videoSource.attribution}</p>
          ) : videoSource.name ? (
            <p>
              Nguồn:{" "}
              {videoSource.url ? (
                <a
                  href={videoSource.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  {videoSource.name}
                </a>
              ) : (
                videoSource.name
              )}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
