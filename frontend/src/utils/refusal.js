// The exact reply every prompt mandates when the filings don't cover a question:
// backend/generation/prompt_builder.py:31-32 and generation/intent_prompts.py:77,167.
// Keep in sync if that sentence changes.
const REFUSAL = 'not available in the provided documents';

/** True when the whole reply is the "not in the filings" refusal. */
export function isRefusal(text) {
    return (text || '').trim().replace(/\.$/, '').toLowerCase() === REFUSAL;
}
