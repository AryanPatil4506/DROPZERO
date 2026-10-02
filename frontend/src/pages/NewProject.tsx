import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { useInvalidateProject, useJob } from "../api/hooks";
import type { Category, Language, Project } from "../api/types";
import { IconFile, IconUpload } from "../components/icons";
import { ErrorBox, Segmented } from "../components/ui";
import { STAGE_LABEL } from "../lib/format";

type Source = "video" | "script";
type ScriptInput = "file" | "paste";

const field = "h-11 w-full rounded-full border border-transparent bg-white/[0.06] px-4 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-accent/60 focus:bg-white/[0.09]";

export default function NewProject() {
  const navigate = useNavigate();
  const invalidate = useInvalidateProject();
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<Category>("tech");
  const [language, setLanguage] = useState<Language>("en");
  const [creator, setCreator] = useState("");
  const [audience, setAudience] = useState("");
  const [source, setSource] = useState<Source>("script");
  const [scriptInput, setScriptInput] = useState<ScriptInput>("paste");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [project, setProject] = useState<Project | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);

  const submit = useMutation({
    mutationFn: async () => {
      const p = await api.createProject({
        title: title.trim(),
        category,
        language,
        creator: creator.trim() || undefined,
        target_audience: audience.trim() || undefined,
      });
      const uploaded =
        source === "video"
          ? await api.uploadVideo(p.id, file!)
          : await api.uploadScript(p.id, scriptInput === "paste" ? text : file!);
      setProject(uploaded);
      const j = await api.analyze(uploaded.id);
      setJobId(j.id);
      return uploaded;
    },
  });

  useEffect(() => {
    if (job.data?.status === "done" && project) {
      invalidate(project.id);
      const t = setTimeout(() => navigate(`/projects/${project.id}`), 700);
      return () => clearTimeout(t);
    }
  }, [job.data?.status, project, navigate, invalidate]);

  const ready =
    title.trim().length > 0 && (source === "video" ? !!file : scriptInput === "paste" ? text.trim().length > 0 : !!file);
  const busy = submit.isPending || (!!jobId && job.data?.status !== "done" && job.data?.status !== "failed");

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (ready && !busy) submit.mutate();
  };

  return (
    <div className="mx-auto grid max-w-[1200px] gap-5 p-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <form onSubmit={onSubmit} className="glass space-y-5 rounded-[28px] p-6" aria-label="New analysis">
        <div>
          <p className="eyebrow">New analysis</p>
          <h1 className="mt-1 text-[26px] font-medium tracking-tight">Find the drop-off before you publish</h1>
        </div>

        <label className="block space-y-1.5">
          <span className="text-sm text-ink-2">Title (as it will appear on YouTube)</span>
          <input className={field} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="I Built an AI Agent in 24 Hours" required maxLength={300} />
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <span className="block text-sm text-ink-2">Category</span>
            <Segmented label="Category" value={category} onChange={setCategory} options={[{ value: "tech", label: "Tech" }, { value: "education", label: "Education" }, { value: "vlog", label: "Vlog" }]} />
          </div>
          <div className="space-y-1.5">
            <span className="block text-sm text-ink-2">Language</span>
            <Segmented label="Language" value={language} onChange={setLanguage} options={[{ value: "en", label: "English" }, { value: "hi", label: "Hindi" }, { value: "hinglish", label: "Hinglish" }]} />
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block space-y-1.5">
            <span className="text-sm text-ink-2">Creator <span className="text-ink-3">(optional)</span></span>
            <input className={field} value={creator} onChange={(e) => setCreator(e.target.value)} />
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm text-ink-2">Target audience <span className="text-ink-3">(optional)</span></span>
            <input className={field} value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="Beginners learning to code" />
          </label>
        </div>

        <div className="space-y-3">
          <Segmented label="Source" value={source} onChange={(v) => { setSource(v); setFile(null); }} options={[{ value: "video", label: "Video" }, { value: "script", label: "Script" }]} />
          {source === "script" && (
            <Segmented label="Script input" value={scriptInput} onChange={(v) => { setScriptInput(v); setFile(null); }} options={[{ value: "paste", label: "Paste text" }, { value: "file", label: "TXT / MD file" }]} />
          )}
          {source === "script" && scriptInput === "paste" ? (
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={8}
              placeholder="Paste your script. Timing will be estimated from word counts."
              className="scroll-thin w-full rounded-[20px] border border-transparent bg-white/[0.06] p-4 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-accent/60"
            />
          ) : (
            <label className="flex cursor-pointer items-center gap-4 rounded-[20px] border border-dashed border-line-2 bg-white/[0.03] p-5 hover:bg-white/[0.06]">
              {source === "video" ? <IconUpload className="size-6 text-accent" /> : <IconFile className="size-6 text-accent" />}
              <span className="text-sm">
                <span className="block text-ink">{file ? file.name : source === "video" ? "Choose an MP4 or MOV (5–15 min works best)" : "Choose a .txt or .md script"}</span>
                <span className="text-ink-3">{file ? `${(file.size / 1e6).toFixed(1)} MB` : "Your original file is never modified."}</span>
              </span>
              <input
                type="file"
                className="sr-only"
                accept={source === "video" ? "video/mp4,video/quicktime,.mp4,.mov" : ".txt,.md,text/plain,text/markdown"}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
          )}
        </div>

        {submit.isError && <ErrorBox error={submit.error} title="Upload failed" />}
        <button type="submit" className="pill-accent h-12 w-full text-[15px]" disabled={!ready || busy}>
          {busy ? "Analysing…" : "Analyze"}
        </button>
      </form>

      <section className="glass self-start rounded-[28px] p-6" aria-label="Processing">
        <p className="text-[17px] font-medium">Processing</p>
        {!jobId && !submit.isPending && <p className="mt-2 text-sm text-ink-2">Progress appears here after you press Analyze.</p>}
        {submit.isPending && !jobId && <p className="mt-2 text-sm text-ink-2">Uploading…</p>}
        {project?.warnings.map((w) => (
          <p key={w} className="mt-3 rounded-2xl border border-med/30 bg-med/10 px-3 py-2 text-sm text-[#f6d391]">{w}</p>
        ))}
        {job.data && (
          <>
            <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${Math.round(job.data.progress * 100)}%` }} />
            </div>
            <ol className="mt-4 space-y-2">
              {job.data.stages.map((s, i) => {
                const current = job.data.stage === s;
                const doneIdx = Math.round(job.data.progress * job.data.stages.length);
                const done = job.data.status === "done" || i < doneIdx;
                return (
                  <li key={s} className="flex items-center gap-3 text-sm">
                    <span className={`grid size-6 place-items-center rounded-full text-[11px] font-semibold ${done ? "bg-sim text-[#04130d]" : current ? "bg-accent text-[#160700]" : "bg-white/10 text-ink-3"}`}>
                      {done ? "✓" : i + 1}
                    </span>
                    <span className={done || current ? "text-ink" : "text-ink-3"}>{STAGE_LABEL[s] ?? s}</span>
                    {current && <span className="text-xs text-ink-3">running…</span>}
                  </li>
                );
              })}
            </ol>
            {job.data.status === "failed" && <div className="mt-4"><ErrorBox error={job.data.error ?? "The analysis failed."} title="Analysis failed" /></div>}
            {job.data.status === "done" && <p className="mt-4 text-sm text-[#7fd8b8]">Done. Opening the dashboard…</p>}
          </>
        )}
        {job.isError && <div className="mt-4"><ErrorBox error={job.error} title="Lost track of the job" /></div>}
      </section>
    </div>
  );
}
