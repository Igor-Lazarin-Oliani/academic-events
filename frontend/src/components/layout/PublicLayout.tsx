import { NavLink, Outlet, useMatch } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { AssistantWidget } from "@/features/assistant/AssistantWidget";
import { LoginButton, Logo, NotificationsBell, ThemeToggle, UserMenu } from "./common";

export function PublicLayout() {
  const { user } = useAuth();
  const eventMatch = useMatch("/eventos/:slug/*");
  const link = ({ isActive }: { isActive: boolean }) => cn("rounded-lg px-3 py-1.5 text-sm font-medium transition", isActive ? "bg-muted text-fg" : "text-subtle hover:text-fg");
  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-30 border-b border-border/70 bg-bg/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4">
          <Logo />
          <nav className="ml-4 hidden items-center gap-1 sm:flex">
            <NavLink to="/" end className={link}>Eventos</NavLink>
            {user && <NavLink to="/meus-ingressos" className={link}>Meus ingressos</NavLink>}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            {user ? <><NotificationsBell /><UserMenu /></> : <LoginButton />}
          </div>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t border-border py-8 text-center text-sm text-subtle">
        academic-events · Técnicas Avançadas em Desenvolvimento de Software (UFMS) · dados fictícios para demonstração
      </footer>
      {user && <AssistantWidget eventSlug={eventMatch?.params.slug} />}
    </div>
  );
}
