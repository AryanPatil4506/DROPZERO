// Mock API: serves the recorded API responses in frontend/mock/ (VITE_USE_MOCKS=true), so the UI
// runs without the backend. Regenerate them with `python scripts/export_api_samples.py`.
import {
  ApiError,
  type FlagsResponse,
  type Job,
  type NewProject,
  type Prediction,
  type Project,
  type Segment,
  type Simulation,
  type TextFeatures,
  type Transcript,
  type Validation,
} from "./types";

const files = import.meta.glob<unknown>("/mock/**/*.json", { eager: true, import: "default" });
const file = <T,>(path: string): T => {
  const data = files[`/mock/${path}`];
  if (data === undefined) throw new ApiError(404, `Mock file not found: ${path}`);
  return structuredClone(data) as T;
};

const SAMPLES = ["en", "hi", "hinglish"] as const;
type Sample = (typeof SAMPLES)[number];

const sampleProjects = new Map<string, { sample: Sample; project: Project }>(
  SAMPLES.map((s) => {
    const project = file<Project>(`${s}/project.json`);
    return [project.id, { sample: s, project }];
  }),
);

function sampleFor(id: string): Sample {
  const hit = sampleProjects.get(id);
  if (!hit) throw new ApiError(404, "Project not found");
  return hit.sample;
}

/** Per-sample model output; 404 when a sample has no such file (as the live API before analysis). */
function sampleFile<T>(id: string, name: string): T {
  const path = `${sampleFor(id)}/${name}`;
  if (files[`/mock/${path}`] === undefined) throw new ApiError(404, `No ${name.replace(".json", "")} for this project yet`);
  return file<T>(path);
}

const delay = <T,>(value: T, ms = 220) => new Promise<T>((resolve) => setTimeout(() => resolve(value), ms));
const attempt = async <T,>(fn: () => T, ms?: number) => delay(undefined, ms).then(fn);

// In mock mode, new uploads are mapped onto the bundled sample in the chosen language and a fake
// job advances through the stages over a few seconds.
const mockJobs = new Map<string, { job: Job; startedAt: number }>();
const JOB_SECONDS = 4.5;

function sampleIdFor(language: string): string {
  for (const [id, { sample }] of sampleProjects) if (sample === language) return id;
  return [...sampleProjects.keys()][0];
}

export const api = {
  listProjects: () => attempt(() => [...sampleProjects.values()].map(({ project }) => structuredClone(project))),
  getProject: (id: string) =>
    attempt(() => {
      const hit = sampleProjects.get(id);
      if (!hit) throw new ApiError(404, "Project not found");
      return structuredClone(hit.project);
    }),
  createProject: (body: NewProject) =>
    attempt(() => {
      const id = sampleIdFor(body.language);
      return structuredClone(sampleProjects.get(id)!.project);
    }),
  uploadVideo: (id: string, uploaded: File) =>
    attempt(() => {
      if (!/\.(mp4|mov)$/i.test(uploaded.name)) throw new ApiError(422, "Unsupported file type. Upload an MP4 or MOV file.");
      return structuredClone(sampleProjects.get(id)!.project);
    }, 600),
  uploadScript: (id: string, input: File | string) =>
    attempt(() => {
      if (typeof input === "string" && input.trim().length < 20) throw new ApiError(422, "Script is too short to analyse.");
      return structuredClone(sampleProjects.get(id)!.project);
    }, 400),
  analyze: (id: string) =>
    attempt(() => {
      const job: Job = {
        ...file<Job>(`${sampleFor(id)}/job.json`),
        id: `mockjob-${Date.now()}`,
        status: "queued",
        stage: null,
        progress: 0,
        finished_at: null,
      };
      mockJobs.set(job.id, { job, startedAt: Date.now() });
      return structuredClone(job);
    }),
  getJob: (jobId: string) =>
    attempt(() => {
      const entry = mockJobs.get(jobId);
      if (!entry) throw new ApiError(404, "Job not found");
      const { job, startedAt } = entry;
      const progress = Math.min(1, (Date.now() - startedAt) / 1000 / JOB_SECONDS);
      const stageIndex = Math.min(job.stages.length - 1, Math.floor(progress * job.stages.length));
      const done = progress >= 1;
      return {
        ...job,
        status: done ? "done" : "running",
        stage: done ? null : job.stages[stageIndex],
        progress: done ? 1 : Math.floor(progress * job.stages.length) / job.stages.length,
        finished_at: done ? new Date().toISOString() : null,
      } satisfies Job;
    }, 80),
  getTranscript: (id: string) => attempt(() => file<Transcript>(`${sampleFor(id)}/transcript.json`)),
  getSegments: (id: string) => attempt(() => file<Segment[]>(`${sampleFor(id)}/segments.json`)),
  getTextFeatures: (id: string) => attempt(() => file<TextFeatures>(`${sampleFor(id)}/features_text.json`)),
  getPrediction: (id: string) => attempt(() => sampleFile<Prediction>(id, "prediction.json")),
  getFlags: (id: string) => attempt(() => sampleFile<FlagsResponse>(id, "flags.json")),
  simulate: (id: string, editIds: string[]) =>
    attempt(() => {
      // Recorded responses hold one simulation per sample (all suggested edits). Return it only
      // when that exact set is requested, so the UI never shows a curve for different edits.
      const sim = sampleFile<Simulation>(id, "simulate.json");
      const want = [...editIds].sort().join(",");
      const have = [...sim.applied_edit_ids, ...(sim.skipped_edit_ids ?? [])].sort().join(",");
      if (want !== have) throw new ApiError(409, "Mock mode has a recorded simulation only for all suggested edits together. Run the backend to simulate other combinations.");
      return sim;
    }, 500),
  getValidation: () => attempt(() => file<Validation>("validation.json")),
  getScores: () =>
    attempt(() => {
      throw new ApiError(404, "Score lanes need the live backend.");
    }),
  explain: () =>
    attempt(() => {
      throw new ApiError(409, "AI explanations need the live backend (the local LLM runs there).");
    }),
  rewrite: () =>
    attempt(() => {
      throw new ApiError(409, "AI rewrites need the live backend (the local LLM runs there).");
    }),
  render: () =>
    attempt(() => {
      throw new ApiError(409, "Rendering needs the live backend and an uploaded video.");
    }),
  getRender: () =>
    attempt(() => {
      throw new ApiError(404, "No renders in mock mode.");
    }),
  renderUrl: (id: string, renderId: string) => `/api/projects/${id}/renders/${renderId}/media`,
  mediaUrl: (id: string) => `/api/projects/${id}/media`,
};

