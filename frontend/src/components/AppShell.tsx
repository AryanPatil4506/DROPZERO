import type { ReactNode } from "react";
import { Link, NavLink, Outlet, useMatch, useNavigate } from "react-router-dom";
import { USE_MOCKS } from "../api/client";
import { endSession, getSession } from "../lib/session";
import { IconCheck, IconFile, IconGrid, IconHook, IconLogout, IconPlus, IconSim, IconTimeline, LogoMark } from "./icons";

function RailLink({ to, label, end, children }: { to: string; label: string; end?: boolean; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      end={end}
      title={label}
      aria-label={label}
      className={({ isActive }) =>
        `grid size-12 place-items-center rounded-full transition-colors ${
          isActive ? "bg-ink text-[#0a0a0b] shadow-[0_10px_30px_-10px_rgba(255,255,255,0.45)]" : "glass text-ink-2 hover:text-ink"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function AppShell() {
  const navigate = useNavigate();
  const project = useMatch("/projects/:id/*");
  const projectId = project?.params.id;
  const session = getSession();

  return (
    <div className="flex min-h-svh">
      <aside className="sticky top-0 flex h-svh w-[76px] shrink-0 flex-col items-center gap-3 py-5">
        <Link to="/projects" aria-label="DROPZERO projects" className="mb-4">
          <LogoMark className="size-8" />
        </Link>
        <RailLink to="/projects" end label="Projects">
          <IconGrid className="size-5" />
        </RailLink>
        {projectId && (
          <>
            <RailLink to={`/projects/${projectId}`} end label="Dashboard">
              <IconTimeline className="size-5" />
            </RailLink>
            <RailLink to={`/projects/${projectId}/simulate`} label="Simulation">
              <IconSim className="size-5" />
            </RailLink>
            <RailLink to={`/projects/${projectId}/report`} label="Report (PDF)">
              <IconFile className="size-5" />
            </RailLink>
          </>
        )}
        <RailLink to="/ab" label="Hook A/B simulator">
          <IconHook className="size-5" />
        </RailLink>
        <RailLink to="/validation" label="Validation">
          <IconCheck className="size-5" />
        </RailLink>
        <RailLink to="/new" label="New analysis">
          <IconPlus className="size-5" />
        </RailLink>
        <div className="mt-auto flex flex-col items-center gap-3">
          <button
            type="button"
            title={session ? `Sign out ${session.email}` : "Sign out"}
            aria-label="Sign out"
            onClick={() => {
              endSession();
              navigate("/login");
            }}
            className="glass grid size-10 place-items-center rounded-full text-ink-3 hover:text-ink"
          >
            <IconLogout className="size-4" />
          </button>
        </div>
      </aside>

      <div className="flex h-svh min-w-0 flex-1 flex-col">
        {USE_MOCKS && (
          <div role="note" className="mx-3 mt-3 rounded-full border border-med/30 bg-med/10 px-4 py-1.5 text-center text-xs text-[#f6d391]">
            Mock mode: showing recorded API responses from <code className="font-mono">frontend/mock/</code> (no backend running). Uploads map onto the bundled samples.
          </div>
        )}
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
