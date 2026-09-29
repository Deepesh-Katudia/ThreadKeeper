"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const STATUS_COLOURS: Record<string, string> = {
  planned: "bg-zinc-100 text-zinc-600",
  drafting: "bg-blue-100 text-blue-700",
  in_review: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-700",
  stale: "bg-orange-100 text-orange-800",
  planning: "bg-blue-100 text-blue-700",
  planning_failed: "bg-red-100 text-red-700",
  arc_review: "bg-amber-100 text-amber-800",
  writing: "bg-emerald-100 text-emerald-800",
  finished: "bg-violet-100 text-violet-800",
  alive: "bg-emerald-100 text-emerald-800",
  dead: "bg-zinc-800 text-white",
  missing: "bg-orange-100 text-orange-800",
  open: "bg-amber-100 text-amber-800",
  resolved: "bg-emerald-100 text-emerald-800",
};

export function StatusBadge({ status }: { status: string }) {
  const colour = STATUS_COLOURS[status] ?? "bg-zinc-100 text-zinc-600";
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${colour}`}>{status.replace("_", " ")}</span>;
}

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{message}</div>;
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-zinc-600">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-zinc-400 border-t-transparent" />
      {label}
    </div>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "secondary" | "danger";
  type?: "button" | "submit";
}) {
  const styles = {
    primary: "bg-zinc-900 text-white hover:bg-zinc-700",
    secondary: "border border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-50",
    danger: "bg-red-600 text-white hover:bg-red-500",
  }[variant];
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-40 ${styles}`}
    >
      {children}
    </button>
  );
}

export function StoryNav({ storyId, title }: { storyId: number; title: string }) {
  const pathname = usePathname();
  const tabs = [
    { href: `/stories/${storyId}`, label: "Arc plan" },
    { href: `/stories/${storyId}/episodes`, label: "Episodes" },
    { href: `/stories/${storyId}/memory`, label: "Story memory" },
    { href: `/stories/${storyId}/costs`, label: "Costs & traces" },
  ];
  return (
    <div className="mb-6 border-b border-zinc-200">
      <p className="mb-2 text-sm text-zinc-500">
        <Link href="/" className="hover:underline">All stories</Link> / {title || "Untitled"}
      </p>
      <nav className="flex gap-4">
        {tabs.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            className={`-mb-px border-b-2 pb-2 text-sm ${
              pathname === tab.href ? "border-zinc-900 font-semibold" : "border-transparent text-zinc-500 hover:text-zinc-800"
            }`}
          >
            {tab.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

export function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="mb-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
