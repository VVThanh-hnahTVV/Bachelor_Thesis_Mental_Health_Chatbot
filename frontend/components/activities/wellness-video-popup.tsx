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
  title?: string;
  videoSource?: VideoSourceCredit | null;
}

export function WellnessVideoPopup({
  videoUrl,
  youtubeId,
  title,
  videoSource,
}: WellnessVideoPopupProps) {
  const ytId = extractYoutubeId(youtubeId, videoUrl);
  const directSrc = !ytId && videoUrl?.trim() && isDirectVideoUrl(videoUrl.trim())
    ? videoUrl.trim()
    : null;

  return (
    <div className="space-y-3">
      {title ? (
        <p className="text-sm text-muted-foreground">{title}</p>
      ) : null}

      {ytId ? (
        <div className="relative w-full overflow-hidden rounded-lg bg-black pt-[56.25%]">
          <iframe
            className="absolute inset-0 h-full w-full"
            src={`https://www.youtube.com/embed/${ytId}?rel=0&modestbranding=1`}
            title={title || videoSource?.name || "Wellness video"}
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
          Your browser does not support video playback.
        </video>
      ) : (
        <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          Video is not available. Please try again later.
        </p>
      )}

      <p className="text-xs text-muted-foreground">
        Follow the guided video at your own pace. Pause or stop anytime.
      </p>

      {videoSource ? (
        <div className="rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          {videoSource.attribution ? (
            <p>{videoSource.attribution}</p>
          ) : videoSource.name ? (
            <p>
              Source:{" "}
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
          {videoSource.license ? (
            <p className="mt-1 opacity-80">License: {videoSource.license}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
