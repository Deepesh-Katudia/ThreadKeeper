"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { forwardRef, useLayoutEffect, useRef, type ReactNode, type TextareaHTMLAttributes } from "react";

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

const STATUS_TONES: Record<string, string> = {
  planned: "text-faint",
  drafting: "text-sky-400",
  in_review: "text-amber-400",
  approved: "text-emerald-400",
  failed: "text-red-400",
  stale: "text-orange-400",
  planning: "text-sky-400",
  planning_failed: "text-red-400",
  arc_review: "text-amber-400",
  writing: "text-emerald-400",
  finished: "text-violet-400",
  alive: "text-emerald-400",
  dead: "text-red-400",
  missing: "text-orange-400",
  open: "text-amber-400",
  resolved: "text-emerald-400",
};

export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONES[status] ?? "text-muted";
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded border border-line px-1.5 py-0.5 text-[11px] ${tone}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {status.replace("_", " ")}
    </span>
  );
}

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm break-words text-red-300 dark:text-red-300">
      {message}
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-muted">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-muted border-t-transparent" />
      {label}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Buttons and inputs
// ---------------------------------------------------------------------------

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON_STYLES: Record<ButtonVariant, string> = {
  primary: "bg-accent text-accent-fg hover:opacity-85",
  secondary: "border border-line bg-transparent text-fg hover:bg-subtle",
  ghost: "text-muted hover:bg-subtle hover:text-fg",
  danger: "border border-red-500/40 text-red-400 hover:bg-red-500/10",
};

interface ButtonProps {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: ButtonVariant;
  type?: "button" | "submit";
  title?: string;
}

export function Button({ children, onClick, disabled, variant = "secondary", type = "button", title }: ButtonProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fg disabled:cursor-not-allowed disabled:opacity-40 ${BUTTON_STYLES[variant]}`}
    >
      {children}
    </button>
  );
}

// min-w-0: inside flex rows, a field must never widen past its container (text wraps, height grows instead).
const FIELD = "w-full min-w-0 rounded-md border border-line bg-field px-3 py-2 text-sm text-fg placeholder:text-faint focus:border-line-strong focus:outline-none";

/** A textarea that always grows to show everything typed into it. */
export const AutoTextarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function AutoTextarea({ className = "", value, ...props }, forwardedRef) {
    const innerRef = useRef<HTMLTextAreaElement | null>(null);

    // Fallback for browsers without `field-sizing: content`: size to the scroll height.
    useLayoutEffect(() => {
      const box = innerRef.current;
      if (!box) return;
      box.style.height = "auto";
      box.style.height = `${box.scrollHeight + 2}px`;
    }, [value]);

    return (
      <textarea
        {...props}
        value={value}
        rows={props.rows ?? 1}
        ref={(node) => {
          innerRef.current = node;
          if (typeof forwardedRef === "function") forwardedRef(node);
          else if (forwardedRef) forwardedRef.current = node;
        }}
        className={`auto-grow ${FIELD} ${className}`}
      />
    );
  },
);

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${FIELD} ${props.className ?? ""}`} />;
}

// ---------------------------------------------------------------------------
// Layout pieces
// ---------------------------------------------------------------------------

/** The thin title bar at the top of every pane. */
export function PaneHeader({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex min-h-[41px] flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-1.5">
      <h1 className="text-sm font-semibold break-words">{title}</h1>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

/** Grey pill with the active option in solid black, like a segmented control. */
export function Segmented({ options, active, onChange }: {
  options: { value: string; label: string }[];
  active: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="inline-flex rounded-md bg-subtle p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={`rounded px-3 py-1 text-xs transition ${
            active === option.value ? "bg-bg text-fg shadow-sm" : "text-muted hover:text-fg"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function StoryNav({ storyId, title }: { storyId: number; title: string }) {
  const pathname = usePathname();
  const tabs = [
    { href: `/stories/${storyId}`, label: "Arc" },
    { href: `/stories/${storyId}/episodes`, label: "Episodes" },
    { href: `/stories/${storyId}/memory`, label: "Memory" },
    { href: `/stories/${storyId}/evals`, label: "Evals" },
    { href: `/stories/${storyId}/costs`, label: "Costs" },
  ];
  return (
    <PaneHeader title={title || "Untitled serial"}>
      <nav className="inline-flex rounded-md bg-subtle p-0.5">
        {tabs.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            className={`rounded px-3 py-1 text-xs transition ${
              pathname === tab.href ? "bg-bg text-fg shadow-sm" : "text-muted hover:text-fg"
            }`}
          >
            {tab.label}
          </Link>
        ))}
      </nav>
    </PaneHeader>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-panel ${className}`}>{children}</div>;
}

export function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="mb-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xs font-medium tracking-wide text-muted uppercase">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Scrollable page body under a PaneHeader. */
export function PaneBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-8 ${className}`}>{children}</div>;
}
