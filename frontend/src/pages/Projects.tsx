import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useProjects } from "../api/hooks";
import type { Project } from "../api/types";
import { IconClose, IconPlus } from "../components/icons";
import { EmptyState, ErrorBox, Spinner } from "../components/ui";
import { CATEGORY_LABEL, LANGUAGE_LABEL, mmss } from "../lib/format";

const STATUS_STYLE: Record<string, string> = {
  ready: "border-sim/40 text-[#7fd8b8]",
  processing: "border-pred/40 text-[#a9c0f2]",
  failed: "border-high/40 text-[#ffb3b4]",
};

export default function Projects() {
  const projects = useProjects();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
  const confirmDelete = (p: Project) => {
    if (window.confirm(`Delete “${p.title}”? Its encrypted media, transcript and analysis are removed from this machine. This cannot be undone.`))
      remove.mutate(p.id);
  };

  return (
    <div className="mx-auto max-w-[1200px] p-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Projects</p>
          <h1 className="mt-1 text-[30px] font-medium tracking-tight">Your analyses</h1>
        </div>
        <Link to="/new" className="pill-accent">
          <IconPlus className="size-4" />
          New analysis
        </Link>
      </header>

      <section className="glass mt-6 overflow-hidden rounded-[26px]">
        {projects.isPending && <div className="p-6"><Spinner label="Loading projects" /></div>}
        {remove.isError && <div className="p-6 pb-0"><ErrorBox error={remove.error} title="Couldn't delete the project" /></div>}
        {projects.isError && <div className="p-6"><ErrorBox error={projects.error} title="Couldn't load projects" /></div>}
        {projects.data?.length === 0 && (
          <div className="p-6">
            <EmptyState title="No projects yet">Upload a video or paste a script to get your first retention report.</EmptyState>
          </div>
        )}
        {!!projects.data?.length && (
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-ink-3">
              <tr className="border-b border-line">
                <th className="px-5 py-3 font-medium">Title</th>
                <th className="px-3 py-3 font-medium">Language</th>
                <th className="px-3 py-3 font-medium">Category</th>
                <th className="px-3 py-3 font-medium">Source</th>
                <th className="px-3 py-3 font-medium">Length</th>
                <th className="px-3 py-3 font-medium">Status</th>
                <th className="px-5 py-3"><span className="sr-only">Delete</span></th>
              </tr>
            </thead>
            <tbody>
              {projects.data.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => navigate(`/projects/${p.id}`)}
                  className="cursor-pointer border-b border-line last:border-0 hover:bg-white/[0.04]"
                >
                  <td className="px-5 py-3.5">
                    <Link to={`/projects/${p.id}`} className="font-medium text-ink hover:underline" onClick={(e) => e.stopPropagation()}>
                      {p.title}
                    </Link>
                  </td>
                  <td className="px-3 py-3.5 text-ink-2">{LANGUAGE_LABEL[p.language] ?? p.language}</td>
                  <td className="px-3 py-3.5 text-ink-2">{CATEGORY_LABEL[p.category] ?? p.category}</td>
                  <td className="px-3 py-3.5 text-ink-2">{p.source_type ? (p.source_type === "script" ? "Script" : "Video") : "—"}</td>
                  <td className="px-3 py-3.5 text-ink-2 tabular-nums">{p.duration_s != null ? mmss(p.duration_s) : "—"}</td>
                  <td className="px-3 py-3.5">
                    <span className={`chip ${STATUS_STYLE[p.status] ?? ""}`}>{p.status}</span>
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <button
                      type="button"
                      aria-label={`Delete ${p.title}`}
                      title="Delete project and its media"
                      disabled={remove.isPending && remove.variables === p.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        confirmDelete(p);
                      }}
                      className="grid size-7 place-items-center rounded-full text-ink-3 hover:bg-high/15 hover:text-[#ffb3b4] disabled:opacity-40"
                    >
                      <IconClose className="size-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
