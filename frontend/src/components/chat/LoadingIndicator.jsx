/**
 * LoadingIndicator — the answer in progress while /chat/stream runs:
 * a plain stage line before the first word, then the answer as it streams in.
 * Chips stay inert until the answer is finished (MessageList makes them live).
 */

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { linkCitations } from '../../utils/citations';
import { stageLine } from '../../utils/chatFormat';

const INERT = { a: ({ children }) => <span className="cx-chip is-inert">{children}</span> };

export default function LoadingIndicator({ streaming }) {
    const { stages = [], text = '' } = streaming || {};
    return (
        <article className="cx-a" aria-busy="true">
            {text ? (
                <div className="cx-prose">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={INERT}>{linkCitations(text, null)}</ReactMarkdown>
                    <span className="cx-cursor" aria-hidden="true" />
                </div>
            ) : (
                <p className="cx-stage" role="status">{stageLine(stages)}</p>
            )}
        </article>
    );
}
