import {
  ApiError,
  type FlagsResponse,
  type Job,
  type NewProject,
  type Prediction,
  type Project,
  type RenderStatus,
  type Segment,
  type CustomEdit,
  type Explanation,
  type ScoreSet,
  type Simulation,
  type TextFeatures,
  type Transcript,
  type Validation,
} from "./types";

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (body?.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const live = {
  listProjects: () => request<Project[]>("/projects"),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (body: NewProject) => request<Project>("/projects", json(body)),
  uploadVideo: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Project>(`/projects/${id}/video`, { method: "POST", body: form });
  },
  uploadScript: (id: string, input: File | string) => {
    if (typeof input === "string") return request<Project>(`/projects/${id}/script`, json({ text: input }));
    const form = new FormData();
    form.append("file", input);
    return request<Project>(`/projects/${id}/script`, { method: "POST", body: form });
  },
  analyze: (id: string) => request<Job>(`/projects/${id}/analyze`, { method: "POST" }),
  getJob: (jobId: string) => request<Job>(`/jobs/${jobId}`),
  getTranscript: (id: string) => request<Transcript>(`/projects/${id}/transcript`),
  getSegments: (id: string) => request<Segment[]>(`/projects/${id}/segments`),
  getTextFeatures: (id: string) => request<TextFeatures>(`/projects/${id}/features/text`),
  getPrediction: (id: string) => request<Prediction>(`/projects/${id}/prediction`),
  getFlags: (id: string) => request<FlagsResponse>(`/projects/${id}/flags`),
  simulate: (id: string, editIds: string[], custom: CustomEdit[] = []) =>
    request<Simulation>(`/projects/${id}/simulate`, json({ edit_ids: editIds, custom_edits: custom })),
  explain: (id: string, flagId: string, refresh = false) =>
    request<Explanation>(`/projects/${id}/flags/${flagId}/explain${refresh ? "?refresh=true" : ""}`, { method: "POST" }),
  getValidation: () => request<Validation>("/validation"),
  getScores: (id: string) => request<ScoreSet>(`/projects/${id}/scores`),
  render: (id: string, editIds: string[], custom: CustomEdit[] = []) =>
    request<RenderStatus>(`/projects/${id}/render`, json({ edit_ids: editIds, custom_edits: custom })),
  getRender: (id: string, renderId: string) => request<RenderStatus>(`/projects/${id}/renders/${renderId}`),
  renderUrl: (id: string, renderId: string) => `/api/projects/${id}/renders/${renderId}/media`,
  mediaUrl: (id: string) => `/api/projects/${id}/media`,
};

export type Api = typeof live;

type AsyncFn = (...args: unknown[]) => Promise<unknown>;

// Mock mode loads frontend/mock/ lazily, so live builds don't ship the sample JSON.
const mockApi = new Proxy(live, {
  get(target, key: string) {
    if (key === "mediaUrl" || key === "renderUrl") return target[key];
    return (...args: unknown[]) => import("./mock").then((m) => (m.api[key as keyof Api] as unknown as AsyncFn)(...args));
  },
});

export const api: Api = USE_MOCKS ? mockApi : live;
