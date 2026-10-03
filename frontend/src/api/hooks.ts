import type { CustomEdit } from "./types";
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { ApiError } from "./types";

const noRetryOn404 = (count: number, error: unknown) =>
  !(error instanceof ApiError && (error.status === 404 || error.status === 422)) && count < 2;

export const useProjects = () => useQuery({ queryKey: ["projects"], queryFn: api.listProjects });

export const useProject = (id: string) => useQuery({ queryKey: ["project", id], queryFn: () => api.getProject(id), retry: noRetryOn404 });

export const useTranscript = (id: string) =>
  useQuery({ queryKey: ["transcript", id], queryFn: () => api.getTranscript(id), retry: noRetryOn404 });

export const useSegments = (id: string) =>
  useQuery({ queryKey: ["segments", id], queryFn: () => api.getSegments(id), retry: noRetryOn404 });

export const useTextFeatures = (id: string) =>
  useQuery({ queryKey: ["features-text", id], queryFn: () => api.getTextFeatures(id), retry: noRetryOn404 });

export const useAvFeatures = (id: string, enabled = true) =>
  useQuery({ queryKey: ["features-av", id], queryFn: () => api.getAvFeatures(id), retry: noRetryOn404, enabled });

export const usePrediction = (id: string) =>
  useQuery({ queryKey: ["prediction", id], queryFn: () => api.getPrediction(id), retry: noRetryOn404 });

export const useFlags = (id: string) => useQuery({ queryKey: ["flags", id], queryFn: () => api.getFlags(id), retry: noRetryOn404 });

export const useScores = (id: string) =>
  useQuery({ queryKey: ["scores", id], queryFn: () => api.getScores(id), retry: noRetryOn404 });

export const useValidation = () => useQuery({ queryKey: ["validation"], queryFn: api.getValidation, retry: noRetryOn404 });

export const useSimulation = (id: string, editIds: string[], custom: CustomEdit[] = []) =>
  useQuery({
    queryKey: ["simulate", id, [...editIds].sort().join(","), JSON.stringify(custom)],
    queryFn: () => api.simulate(id, editIds, custom),
    enabled: editIds.length > 0 || custom.length > 0,
    retry: noRetryOn404,
  });

/** Polls the job every second until it finishes. */
export const useJob = (jobId: string | null) =>
  useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "done" || status === "failed" ? false : 1000;
    },
  });

export function useInvalidateProject() {
  const qc = useQueryClient();
  return useCallback(
    (id: string) => qc.invalidateQueries({ predicate: (q) => q.queryKey.includes(id) || q.queryKey[0] === "projects" }),
    [qc],
  );
}

/** Polls a render every 1.5 s until it finishes. */
export const useRender = (id: string, renderId: string | null) =>
  useQuery({
    queryKey: ["render", id, renderId],
    queryFn: () => api.getRender(id, renderId!),
    enabled: !!renderId,
    retry: noRetryOn404,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "done" || status === "failed" ? false : 1500;
    },
  });
