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
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-white shadow-sm ring-1 ring-serene-green/15",
        className
      )}
    >
      <Image
        src="/logo.png"
        alt="Luna 2.0"
        width={56}
        height={56}
        priority={priority}
        className="h-[85%] w-[85%] object-contain"
      />
    </span>
  );
}
