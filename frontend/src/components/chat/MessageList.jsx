/**
 * MessageList Component
 * ======================
 * Premium bubble layout:
 *   - USER  → right-aligned gold bubble
 *   - AI    → left-aligned navy card with gold left-border
 * The answer in progress streams in LoadingIndicator; finished messages
 * render here as markdown.
 *
 * Includes: MetadataBar, PipelinePanel, FollowUpChips
 */

import { createContext, useContext, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, Check, ChevronDown, ChevronUp, FileText } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { isRefusal } from '../../utils/refusal';
import { bare, linkCitations } from '../../utils/citations';
import FinancialChart from './FinancialChart';
import LoadingIndicator from './LoadingIndicator';
import { STAGE_LABELS } from './stageLabels';
import { pdfUrlOf } from '../../utils/sources';

// Stable markdown link: an inline component here would be a new type every render,
// remounting every chip (and losing the one focus should return to).
const CiteContext = createContext(null);
function MdLink({ href, children, node, ...rest }) {
    const cite = useContext(CiteContext);
    void node;
    if (!href?.startsWith('#cite-') || !cite) return <a href={href} {...rest}>{children}</a>;
    const id = href.slice(6);
    const active = cite.activeSourceId === id;
    return (
        <button type="button" className={`cite-chip cx-chip${active ? ' is-active' : ''}`}
            aria-pressed={active} onClick={(e) => cite.open(id, e.currentTarget)}
            aria-label={`Open source: ${children}`}>{children}</button>
    );
}
const MD_COMPONENTS = { a: MdLink };

function formatTime(timestamp) {
    if (!timestamp) return '';
    const d = new Date(timestamp);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function MessageList({ messages, isLoading, streaming, onFollowUp, onRequestUpload, onOpenSource, activeSourceId }) {
    const bottomRef = useRef(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, [messages, isLoading, streaming?.text, streaming?.stages.length]);

    return (
        <div className="chat-messages">
            {messages.map((msg) => (
                <MessageBubble
                    key={msg.id}
                    message={msg}
                    onFollowUp={onFollowUp}
                    onRequestUpload={onRequestUpload}
                    isLoading={isLoading}
                    onOpenSource={onOpenSource}
                    activeSourceId={activeSourceId}
                />
            ))}

            {/* Loading indicator — appears as assistant message */}
            {isLoading && <LoadingIndicator streaming={streaming} />}

            <div ref={bottomRef} />
        </div>
    );
}

function MessageBubble({ message, onFollowUp, onRequestUpload, isLoading, onOpenSource, activeSourceId }) {
    const isUser = message.role === 'user';
    const { user, isAuthenticated } = useAuth();
    const userName = user?.name || 'You';
    const userAvatar = user?.avatar || 'ME';
    const [copied, setCopied] = useState(false);
    const [showEvidence, setShowEvidence] = useState(false);
    const [showPipeline, setShowPipeline] = useState(false);

    const handleCopy = () => {
        navigator.clipboard.writeText(message.content);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const evidence = message.metadata?.evidence || [];
    const citations = message.metadata?.citations || [];
    const pipeline = message.metadata?.pipeline || {};
    const followUps = message.metadata?.follow_ups || [];

    // Citation chips: [p.17](#cite-chunk_12) links from linkCitations open that page.
    const openCite = (id, el) => {
        const item = evidence.find((e) => bare(e.chunk_id) === id);
        if (item && pdfUrlOf(item)) onOpenSource?.(item, el);
    };

    return (
        <div
            className={`chat-msg ${isUser ? 'chat-msg-user' : 'chat-msg-assistant'}`}
        >
            {/* Avatar */}
            <div className="chat-msg-avatar">
                <span>{isUser ? userAvatar : 'FA'}</span>
            </div>

            {/* Content */}
            <div className="chat-msg-content">
                {/* Name + timestamp */}
                <div className="chat-msg-header">
                    <span className="chat-msg-role">
                        {isUser ? userName : 'Cognifin · Analyst'}
                    </span>
                    <span className="chat-msg-time">{formatTime(message.timestamp)}</span>
                </div>

                {/* Bubble */}
                {isUser ? (
                    <div className="chat-msg-text">{message.content}</div>
                ) : (
                    <div className="chat-msg-text chat-msg-markdown">
                        <CiteContext.Provider value={{ activeSourceId, open: openCite }}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                                {linkCitations(message.content, evidence)}
                            </ReactMarkdown>
                        </CiteContext.Provider>
                    </div>
                )}

                {/* Not in the corpus: offer the existing upload instead of a dead end */}
                {!isUser && onRequestUpload && isRefusal(message.content) && (
                    <div className="chat-upload-card">
                        <p>
                            Cognifin&apos;s filings don&apos;t cover this yet. Have the company&apos;s
                            annual report? Upload the PDF to ask about it in this chat.
                        </p>
                        {isAuthenticated ? (
                            <button type="button" className="follow-up-chip" onClick={onRequestUpload} disabled={isLoading}>
                                Upload a PDF
                            </button>
                        ) : (
                            <Link className="follow-up-chip" to="/login">Sign in to upload</Link>
                        )}
                    </div>
                )}

                {/* Chart of verified figures from the financials table */}
                {!isUser && pipeline.chart && (
                    <FinancialChart chart={pipeline.chart} numbersCheck={pipeline.numbers_check} />
                )}

                {/* Metadata Bar — confidence, latency, sources */}
                {!isUser && pipeline.confidence != null && (
                    <MetadataBar pipeline={pipeline} />
                )}

                {/* Actions — only after streaming done */}
                {!isUser && (
                    <div className="chat-msg-actions">
                        {citations.length > 0 && (
                            <div className="chat-citations">
                                <span className="chat-citations-label">Sources:</span>
                                {/* Deduplicate by document_label */}
                                {(() => {
                                    const seen = new Set();
                                    // Cited first, then dedupe: deduping first let an uncited passage
                                    // of the same document hide the cited one (empty "Sources:" row).
                                    return evidence
                                        .filter(item => citations.includes(item.chunk_id))
                                        .filter(item => {
                                            const key = item.document_label || item.chunk_id;
                                            if (seen.has(key)) return false;
                                            seen.add(key);
                                            return true;
                                        })
                                        .map(item => (
                                            <span key={item.chunk_id} className="chat-citation-badge">
                                                <FileText size={11} />
                                                {item.document_label
                                                    ? `${item.document_label}${item.page_number > 0 ? ` · p.${item.page_number}` : ''}`
                                                    : item.chunk_id
                                                }
                                            </span>
                                        ));
                                })()
                                }
                            </div>
                        )}

                        <div className="chat-msg-btns">
                            <button className="chat-action-btn" onClick={handleCopy}>
                                {copied ? <Check size={13} /> : <Copy size={13} />}
                                <span>{copied ? 'Copied' : 'Copy'}</span>
                            </button>

                            {evidence.length > 0 && (
                                <button
                                    className="chat-action-btn"
                                    onClick={() => setShowEvidence(!showEvidence)}
                                >
                                    {showEvidence ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                                    <span>Evidence ({evidence.length})</span>
                                </button>
                            )}

                            {pipeline.latency_breakdown && (
                                <button
                                    className="chat-action-btn"
                                    onClick={() => setShowPipeline(!showPipeline)}
                                >
                                    {showPipeline ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                                    <span>Pipeline</span>
                                </button>
                            )}
                        </div>

                        {showEvidence && evidence.length > 0 && (
                            <div className="chat-evidence-panel">
                                {evidence.map((item) => (
                                    <EvidenceChunk key={item.chunk_id} item={item} onOpenSource={onOpenSource} />
                                ))}
                            </div>
                        )}

                        {showPipeline && pipeline.latency_breakdown && (
                            <PipelinePanel
                                breakdown={pipeline.latency_breakdown}
                                model={pipeline.model}
                            />
                        )}
                    </div>
                )}

                {/* Follow-up question chips */}
                {!isUser && followUps.length > 0 && onFollowUp && (
                    <div className="chat-follow-ups">
                        {followUps.map((q, i) => (
                            <button
                                key={i}
                                className="follow-up-chip"
                                onClick={() => onFollowUp(q)}
                            >
                                {q}
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

// =============================================================================
// MetadataBar — Confidence badge, latency, sources count
// =============================================================================

function MetadataBar({ pipeline }) {
    const conf = pipeline.confidence || 0;
    const label = conf >= 0.75 ? 'high' : conf >= 0.45 ? 'medium' : 'low';
    const icon = conf >= 0.75 ? '🟢' : conf >= 0.45 ? '🟡' : '🔴';
    const latency = pipeline.latency_ms ? (pipeline.latency_ms / 1000).toFixed(1) : null;
    const sources = pipeline.sources_used || 0;

    return (
        <div className="chat-meta-bar">
            <span className={`meta-badge meta-confidence meta-${label}`}>
                {icon} {Math.round(conf * 100)}% confidence
            </span>
            {latency && (
                <span className="meta-badge meta-latency">⚡ {latency}s</span>
            )}
            <span className="meta-badge meta-sources">📄 {sources} sources</span>
            {pipeline.intent && pipeline.intent !== 'lookup' && (
                <span className="meta-badge meta-intent">{pipeline.intent}</span>
            )}
            {pipeline.cached && (
                <span className="meta-badge meta-cached">⚡ cached</span>
            )}
        </div>
    );
}

// =============================================================================
// PipelinePanel — Step-by-step latency breakdown with bar chart
// =============================================================================

function PipelinePanel({ breakdown, model }) {
    const stages = Object.entries(breakdown)
        .filter(([k]) => k !== 'total')
        .sort((a, b) => b[1] - a[1]); // largest first
    const total = breakdown.total || 1;

    // Generation time = total minus all tracked stages
    const trackedMs = stages.reduce((sum, [, ms]) => sum + ms, 0);
    const genMs = Math.max(0, total - trackedMs);

    return (
        <div className="chat-pipeline-panel">
            <div className="pipeline-header">RAG Pipeline Breakdown</div>

            {stages.map(([stage, ms]) => {
                const info = STAGE_LABELS[stage] || { icon: '⚙️', label: stage };
                const pct = Math.min(100, (ms / total) * 100);
                const color = ms < 100 ? 'var(--pl-fast)' : ms < 500 ? 'var(--pl-mid)' : 'var(--pl-slow)';
                return (
                    <div key={stage} className="pipeline-stage">
                        <span className="pipeline-icon">{info.icon}</span>
                        <span className="pipeline-label">{info.label}</span>
                        <div className="pipeline-bar-wrap">
                            <div
                                className="pipeline-bar"
                                style={{ width: `${pct}%`, background: color }}
                            />
                        </div>
                        <span className="pipeline-ms">{Math.round(ms)}ms</span>
                    </div>
                );
            })}

            {/* Generation stage (computed) */}
            <div className="pipeline-stage">
                <span className="pipeline-icon">🤖</span>
                <span className="pipeline-label">Generation ({model || 'LLM'})</span>
                <div className="pipeline-bar-wrap">
                    <div
                        className="pipeline-bar"
                        style={{
                            width: `${Math.min(100, (genMs / total) * 100)}%`,
                            background: 'linear-gradient(90deg, #fbbf24, #f59e0b)',
                        }}
                    />
                </div>
                <span className="pipeline-ms">{Math.round(genMs)}ms</span>
            </div>

            <div className="pipeline-total">
                Total: <strong>{(total / 1000).toFixed(2)}s</strong>
            </div>
        </div>
    );
}

// =============================================================================
// EvidenceChunk — Expandable evidence item with PDF viewer
// =============================================================================

function EvidenceChunk({ item, onOpenSource }) {
    const [expanded, setExpanded] = useState(false);

    // Build a human-readable label: "DocumentLabel · Page N" or fall back to chunk_id
    const label = item.document_label
        ? `${item.document_label}${item.page_number > 0 ? ` · Page ${item.page_number}` : ''}`
        : item.chunk_id;

    const pdfUrl = pdfUrlOf(item);

    return (
        <>
            <div className={`chat-evidence-item ${expanded ? 'expanded' : ''}`}>
                <button className="chat-evidence-header" onClick={() => setExpanded(!expanded)}>
                    <span className="chat-evidence-id">
                        <FileText size={12} style={{ marginRight: 4, flexShrink: 0 }} />
                        {label}
                    </span>
                    <span className="chat-evidence-preview">
                        {expanded ? '' : item.snippet.slice(0, 80) + '...'}
                    </span>
                    {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                </button>
                {expanded && (
                    <div className="chat-evidence-body">
                        <p>{item.snippet}</p>
                        {pdfUrl && (
                            <button
                                className="chat-evidence-pdf-link"
                                onClick={(e) => onOpenSource?.(item, e.currentTarget)}
                            >
                                <FileText size={12} />
                                Open PDF{item.page_number > 0 ? ` (Page ${item.page_number})` : ''}
                            </button>
                        )}
                    </div>
                )}
            </div>

        </>
    );
}
