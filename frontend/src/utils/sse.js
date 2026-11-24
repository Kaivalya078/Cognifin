/**
 * Split complete server-sent-event frames off a text buffer.
 * Returns { frames: [{ type, data }], rest } where rest is the unfinished tail.
 * Accepts \r\n line endings; skips comment and data-less frames.
 */
export function takeFrames(buffer) {
    const text = buffer.replace(/\r\n/g, '\n');
    const parts = text.split('\n\n');
    const rest = parts.pop();
    const frames = [];
    for (const part of parts) {
        let type = 'message', data = '';
        for (const line of part.split('\n')) {
            if (line.startsWith('event: ')) type = line.slice(7);
            else if (line.startsWith('data: ')) data += line.slice(6);
        }
        if (data) frames.push({ type, data: JSON.parse(data) });
    }
    return { frames, rest };
}
