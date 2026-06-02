import Image from "next/image";
import { cn } from "@/lib/utils";

interface LunaLogoProps {
  className?: string;
  priority?: boolean;
}

export function LunaLogo({
  className = "h-14 w-14",
  priority = false,
}: LunaLogoProps) {
  return (
    <span
      className={cn("relative inline-flex shrink-0 overflow-hidden", className)}
    >
      <Image
        src="/logo.png"
        alt="Luna & Helios"
        width={56}
        height={56}
        priority={priority}
        className="h-full w-full object-contain"
      />
    </span>
  );
}
