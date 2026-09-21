import type { ReactNode } from "react";

import { TopNav } from "@/components/TopNav";
import type { NavSection } from "@/lib/types";

interface AppShellProps {
  active: NavSection;
  eyebrow: string;
  title: string;
  description: string;
  meta?: ReactNode;
  children: ReactNode;
}

export function AppShell({
  active,
  eyebrow,
  title,
  description,
  meta,
  children,
}: AppShellProps) {
  return (
    <div className="app-shell">
      <TopNav active={active} />
      <main className="workspace">
        <header className="page-header">
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h1>{title}</h1>
            <p className="page-header__description">{description}</p>
          </div>
          {meta ? <div className="page-header__meta">{meta}</div> : null}
        </header>
        {children}
      </main>
    </div>
  );
}
