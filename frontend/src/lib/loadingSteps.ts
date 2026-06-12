export const LOADING_STEPS = [
  'Parsing preferences…',
  'Searching town dataset…',
  'Ranking matches…',
  'Generating explanation…',
] as const

/** Milliseconds before advancing to each step (cosmetic — not tied to backend). */
export const LOADING_STEP_DELAYS_MS = [0, 1800, 3800, 6200] as const
