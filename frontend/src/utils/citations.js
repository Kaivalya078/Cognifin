// Turn the model's citation markers ([chunk_12], [fin_3], [chunk_1, chunk_2], (chunk_1),
// bare chunk_1) into markdown links "[p.17](#cite-chunk_12)" that MessageList renders as chips.

const ID = '(?:chunk|fin)_\\d+';
const LIST = `[\\[(]\\s*${ID}(?:\\s*,\\s*${ID})*\\s*[\\])]`;
const GROUP = new RegExp(`(\\s*)(${LIST}(?:\\s*${LIST})*|\\b${ID}\\b)`, 'g');
const ONE = new RegExp(ID, 'g');

export const bare = (id) => (String(id).match(new RegExp(ID)) || [String(id)])[0];

export function linkCitations(text, evidence) {
  if (!text) return '';
  const pages = new Map((evidence || []).map((e) => [bare(e.chunk_id), e.page_number]));
  const known = pages.size > 0;
  return text.replace(GROUP, (_, lead, group) => {
    const ids = [...new Set(group.match(ONE))].filter((id) => !known || pages.has(id));
    if (!ids.length) return '';
    const label = (id) => (pages.get(id) > 0 ? `p.${pages.get(id)}` : id.startsWith('fin_') ? 'table' : 'source');
    return lead + ids.map((id) => `[${label(id)}](#cite-${id})`).join(' ');
  });
}
