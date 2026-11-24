/**
 * LoadingIndicator Component
 * ===========================
 * The in-progress assistant message while /chat/stream runs:
 *   - before the first word: the pipeline stages the server has finished
 *   - after: the answer as it streams in
 */

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { STAGE_LABELS } from './stageLabels';


function StageLine({ stages }) {
    if (stages.length === 0) return <span className="loading-message visible">Searching filings…</span>;
    return (
        <span className="loading-message visible">
            {stages.map((s) => `${(STAGE_LABELS[s.name] || { label: s.name }).label} ✓ ${Math.round(s.ms)} ms`).join(' · ')}
            {' · Writing answer…'}
        </span>
    );
}

export default function LoadingIndicator({ streaming }) {
    const { stages = [], text = '' } = streaming || {};
    return (
        <div className="chat-msg chat-msg-assistant">
            <div className="chat-msg-avatar">
                <span>FA</span>
            </div>
            <div className="chat-msg-content">
                <div className="chat-msg-header">
                    <span className="chat-msg-role">Cognifin · Analyst</span>
                </div>
                {text ? (
                    <div className="chat-msg-text chat-msg-markdown">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
                        <span className="stream-cursor" />
                    </div>
                ) : (
                    <div className="chat-msg-text chat-loading-indicator">
                        <StageLine stages={stages} />
                        <span className="loading-dots">
                            <span className="loading-dot" />
                            <span className="loading-dot" />
                            <span className="loading-dot" />
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
}
