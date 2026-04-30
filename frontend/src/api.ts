/** Dev: Vite proxies `/api/*` to the FastAPI server. Prod/GitHub Pages: set `VITE_API_BASE_URL` (repo variable) to the public API origin (no trailing slash). */
export function apiUrl(path: string): string {
  const raw = import.meta.env.VITE_API_BASE_URL as string | undefined
  const base = raw?.trim().replace(/\/$/, '') ?? ''
  const p = path.startsWith('/') ? path : `/${path}`
  if (base) return `${base}${p}`
  return `/api${p}`
}
