export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return (await res.json()) as T;
}

export interface Health {
  status: string;
  version: string;
  database: string;
  sources_configured: Record<string, boolean>;
}
