import { ApiError } from "./types";

export const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404;
