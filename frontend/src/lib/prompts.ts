export interface ExamplePrompt {
  label: string
  prompt: string
  /** Refusal / trust-gate demo chip */
  variant?: 'default' | 'demo'
}

export const EXAMPLE_PROMPTS: ExamplePrompt[] = [
  {
    label: 'Good schools under $900k',
    prompt: 'Find safe suburbs under 900k with good schools.',
  },
  {
    label: 'Compare Acton vs Burlington',
    prompt: 'Compare Acton and Burlington.',
  },
  {
    label: 'Commute from Maynard',
    prompt: 'What is the commute from Maynard to Boston?',
  },
  {
    label: 'Open Reading',
    prompt: 'Open Reading.',
  },
  {
    label: 'Live Zillow listings',
    prompt: 'Give me live Zillow listings in Newton.',
    variant: 'demo',
  },
]

export const SEARCH_PLACEHOLDER =
  'Safe towns under $900k with strong schools and <45 min commute'
