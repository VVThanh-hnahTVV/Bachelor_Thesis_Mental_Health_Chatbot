"use client";

import { BreathingGame } from "@/components/games/breathing-game";
import { OceanWaves } from "@/components/games/ocean-waves";
import { ForestGame } from "@/components/games/forest-game";
import { ZenGarden } from "@/components/games/zen-garden";
import { WellnessVideoPopup } from "@/components/activities/wellness-video-popup";
import type { WellnessActivity } from "@/lib/api/wellness";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ActivityPopupHostProps {
  activity: WellnessActivity | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onComplete?: () => void;
}

function renderInteractive(uiComponent: string, onComplete?: () => void) {
  switch (uiComponent) {
    case "breathing_box":
      return <BreathingGame />;
    case "ocean_sound":
      return <OceanWaves />;
    case "mindful_forest":
      return <ForestGame />;
    case "zen_garden":
      return <ZenGarden />;
    default:
      return (
        <p className="text-sm text-muted-foreground">
          Giao diện bài tập chưa khả dụng cho &quot;{uiComponent}&quot;.
        </p>
      );
  }
}

export function ActivityPopupHost({
  activity,
  open,
  onOpenChange,
  onComplete,
}: ActivityPopupHostProps) {
  if (!activity) return null;

  const isVideo =
    activity.content_type === "video" || activity.ui_component.endsWith("_video");

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) onComplete?.();
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{activity.title}</DialogTitle>
          {activity.description ? (
            <DialogDescription>{activity.description}</DialogDescription>
          ) : null}
        </DialogHeader>
        {isVideo ? (
          <WellnessVideoPopup
            videoUrl={activity.video_url}
            youtubeId={activity.youtube_id}
            videoTitle={activity.title}
            videoSource={activity.video_source}
          />
        ) : (
          renderInteractive(activity.ui_component, onComplete)
        )}
      </DialogContent>
    </Dialog>
  );
}
