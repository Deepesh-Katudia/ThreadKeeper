"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, type ReactNode } from "react";

import { LogoMark, MoonIcon, PlusIcon } from "@/components/icons";
import { api } from "@/lib/api";
import { useLoader } from "@/lib/useLoader";

const THEME_STORAGE = "threadkeeper-theme";

/** Sidebar on the left (stories and theme), the current page on the right. */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col">{children}</main>
    </div>
  );
}

function Sidebar() {
  const pathname = usePathname();
  // Re-fetch whenever the page changes, so a newly created story shows up right away.
  const fetchStories = useCallback(() => api.listStories(), [pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  const { data: stories } = useLoader(fetchStories);
  const activeId = pathname.match(/^\/stories\/(\d+)/)?.[1];

  useEffect(() => {
    applyStoredTheme();
  }, []);

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-panel md:flex">
      <div className="flex min-h-[41px] items-center justify-between border-b border-line px-3">
        <Link href="/" className="flex items-center gap-2 text-fg" title="Threadkeeper">
          <LogoMark />
          <span className="text-sm font-semibold">Threadkeeper</span>
        </Link>
        <Link href="/" className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs hover:bg-subtle">
          New <PlusIcon className="h-3.5 w-3.5" />
        </Link>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        <p className="px-2 pt-2 pb-1 text-[11px] tracking-wide text-faint uppercase">Serials</p>
        {stories?.length === 0 && <p className="px-2 py-1 text-xs text-faint">Nothing yet.</p>}
        {stories?.map((story) => (
          <Link
            key={story.id}
            href={`/stories/${story.id}`}
            className={`mb-0.5 block rounded-md px-2 py-2 text-sm transition ${
              String(story.id) === activeId ? "bg-subtle text-fg" : "text-muted hover:bg-subtle hover:text-fg"
            }`}
          >
            <span className="block break-words">{story.title || "Planning…"}</span>
            <span className="mt-0.5 block text-[11px] text-faint">
              {story.approved_episodes}/{story.total_episodes} episodes · {story.status.replace("_", " ")}
            </span>
          </Link>
        ))}
      </div>

      <SidebarFooter />
    </aside>
  );
}

function SidebarFooter() {
  return (
    <div className="flex gap-1.5 border-t border-line p-2">
      <IconButton title="Toggle light / dark" onClick={toggleTheme}><MoonIcon /></IconButton>
    </div>
  );
}

function IconButton({ children, title, onClick }: { children: ReactNode; title: string; onClick: () => void }) {
  return (
    <button onClick={onClick} title={title} aria-label={title} className="rounded-md border border-line p-2 text-muted hover:bg-subtle hover:text-fg">
      {children}
    </button>
  );
}

function applyStoredTheme() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE);
    if (stored === "light" || stored === "dark") document.documentElement.dataset.theme = stored;
  } catch {
    // Storage blocked: stay on the default dark theme.
  }
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem(THEME_STORAGE, next);
  } catch {
    // Not remembered, but still switched for this visit.
  }
}
