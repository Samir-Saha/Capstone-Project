import {
  Award,
  CheckCheck,
  Code2,
  Crown,
  EyeOff,
  Flame,
  Gauge,
  Hash,
  Heart,
  Hourglass,
  ListChecks,
  Mic,
  Repeat,
  Shield,
  Star,
  Sword,
  Swords,
  Trophy,
  Users,
  Zap,
  type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  CheckCheck,
  Code2,
  Crown,
  EyeOff,
  Flame,
  Gauge,
  Hash,
  Heart,
  Hourglass,
  ListChecks,
  Mic,
  Repeat,
  Shield,
  Star,
  Sword,
  Swords,
  Trophy,
  Users,
  Zap,
};

export function AchievementIcon({ name, size = 20, className = "" }: { name: string; size?: number; className?: string }) {
  const Icon = ICONS[name] ?? Award;
  return <Icon size={size} className={className} aria-hidden />;
}
