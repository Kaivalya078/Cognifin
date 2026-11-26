/**
 * MessageList — the conversation, answer first.
 *   - question: a quiet right-aligned block
 *   - answer: prose with page chips, then Sources, Copy / Details, follow-ups
 * The answer in progress streams in LoadingIndicator; finished messages render here.
 */

import { createContext, useContext, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, Check, ChevronDown, ChevronUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { isRefusal } from '../../utils/refusal';
import { bare, linkCitations } from '../../utils/citations';
import { sourceGroups, detailsItems, docLabel } from '../../utils/chatFormat';
import { pdfUrlOf } from '../../utils/sources';
import FinancialChart from './FinancialChart';
import LoadingIndicator from './LoadingIndicator';

// Stable markdown link: an inline component here would be a new type every render,
// remounting every chip (and losing the one focus should return to).
const CiteContext = createContext(null);
function MdLink({ href, children, node, ...rest }) {
    const cite = useContext(CiteContext);
    void node;
    if (!href?.startsWith('#cite-') || !cite) return <a href={href} {...rest}>{children}</a>;
    const id = href.slice(6);
    return <Chip active={cite.activeSourceId === id} onClick={(e) => cite.open(id, e.currentTarget)}>{children}</Chip>;
}
const MD_COMPONENTS = { a: MdLink };

function Chip({ active, onClick, children }) {
    return (
        <button type="button" className={`cx-chip${active ? ' is-active' : ''}`}
            aria-current={active ? 'true' : undefined} onClick={onClick} aria-label={`Open source: ${children}`}>{children}</button>
    );
}

export default function MessageList({ messages, isLoading, streaming, onFollowUp, onRequestUpload, onOpenSource, activeSourceId }) {
    const bottomRef = useRef(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, [messages, isLoading, streaming?.text, streaming?.stages.length]);

    return (
        <div className="cx-messages">
            <div className="cx-thread">
                {messages.map((msg) => (msg.role === 'user'
                    ? <p key={msg.id} className="cx-q">{msg.content}</p>
                    : (
                        <Answer
                            key={msg.id}
                            message={msg}
                            onFollowUp={onFollowUp}
                            onRequestUpload={onRequestUpload}
                            isLoading={isLoading}
                            onOpenSource={onOpenSource}
                            activeSourceId={activeSourceId}
                        />
                    )))}
                {isLoading && <LoadingIndicator streaming={streaming} />}
                <div ref={bottomRef} />
            </div>
        </div>
    );
}

function Answer({ message, onFollowUp, onRequestUpload, isLoading, onOpenSource, activeSourceId }) {
    const { isAuthenticated } = useAuth();
    const [copied, setCopied] = useState(false);
    const [showDetails, setShowDetails] = useState(false);

    const evidence = message.metadata?.evidence || [];
    const citations = message.metadata?.citations || [];
    const pipeline = message.metadata?.pipeline || {};
    const followUps = message.metadata?.follow_ups || [];
    const groups = sourceGroups(evidence, citations);
    const details = detailsItems(pipeline);

    const handleCopy = () => {
        navigator.clipboard.writeText(message.content);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const open = (item, el) => { if (pdfUrlOf(item)) onOpenSource?.(item, el); };
    const openCite = (id, el) => {
        const item = evidence.find((e) => bare(e.chunk_id) === id);
        if (item) open(item, el);
    };

    return (
        <article className="cx-a">
            <div className="cx-prose">
                <CiteContext.Provider value={{ activeSourceId, open: openCite }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                        {linkCitations(message.content, evidence)}
                    </ReactMarkdown>
                </CiteContext.Provider>
            </div>

            {/* Not in the corpus: offer the existing upload instead of a dead end */}
            {onRequestUpload && isRefusal(message.content) && (
                <div className="cx-upload-card">
                    <p>
                        Cognifin&apos;s filings don&apos;t cover this yet. Have the company&apos;s
                        annual report? Upload the PDF to ask about it in this chat.
                    </p>
                    {isAuthenticated ? (
                        <button type="button" className="cx-btn" onClick={onRequestUpload} disabled={isLoading}>
                            Upload a PDF
                        </button>
                    ) : (
                        <Link className="cx-btn" to="/login">Sign in to upload</Link>
                    )}
                </div>
            )}

            {pipeline.chart && <FinancialChart chart={pipeline.chart} numbersCheck={pipeline.numbers_check} />}
            {/* Single-figure answers have no chart; the mismatch warning must still show. */}
            {!pipeline.chart && pipeline.numbers_check?.unmatched?.length > 0 && (
                <div className="cx-chart-note is-warn">
                    {pipeline.numbers_check.unmatched.length} number{pipeline.numbers_check.unmatched.length > 1 ? 's' : ''} in
                    this answer didn&apos;t match the verified table: {pipeline.numbers_check.unmatched.join(', ')}
                </div>
            )}

            {groups.length > 0 && (
                <p className="cx-sources">
                    <span className="cx-sources-label">Sources:</span>
                    {groups.map((g) => (
                        <span key={g.label} className="cx-source-doc">
                            {(() => {
                                // Only sources we can show get a chip (uploads have no URL).
                                const pages = g.items.filter((i) => i.page_number > 0 && pdfUrlOf(i));
                                const whole = !pages.length && g.items.find((i) => pdfUrlOf(i));
                                if (whole) return (
                                    <Chip active={activeSourceId === bare(whole.chunk_id)}
                                        onClick={(e) => open(whole, e.currentTarget)}>{g.label}</Chip>
                                );
                                return <>
                                    <span>{g.label}</span>
                                    {pages.map((i) => (
                                        <Chip key={i.chunk_id} active={activeSourceId === bare(i.chunk_id)}
                                            onClick={(e) => open(i, e.currentTarget)}>{`p.${i.page_number}`}</Chip>
                                    ))}
                                </>;
                            })()}
                        </span>
                    ))}
                </p>
            )}

            <div className="cx-actions">
                <button type="button" className="cx-text-btn" onClick={handleCopy}>
                    {copied ? <Check size={13} /> : <Copy size={13} />}
                    <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>
                {(details.length > 0 || evidence.length > 0) && (
                    <button type="button" className="cx-text-btn" aria-expanded={showDetails}
                        onClick={() => setShowDetails(!showDetails)}>
                        {showDetails ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                        <span>Details</span>
                    </button>
                )}
            </div>

            {showDetails && (
                <div className="cx-details">
                    {details.length > 0 && (
                        <p className="cx-details-meta">{details.map((d) => <span key={d}>{d}</span>)}</p>
                    )}
                    {evidence.length > 0 && (
                        <ul className="cx-passages">
                            {evidence.map((item) => <Passage key={item.chunk_id} item={item} onOpen={open} />)}
                        </ul>
                    )}
                </div>
            )}

            {followUps.length > 0 && onFollowUp && (
                <div className="cx-followups">
                    {followUps.map((q) => (
                        <button key={q} type="button" className="cx-followup" onClick={() => onFollowUp(q)}>{q}</button>
                    ))}
                </div>
            )}
        </article>
    );
}

function Passage({ item, onOpen }) {
    const [expanded, setExpanded] = useState(false);
    const label = docLabel(item.document_label) || item.chunk_id;
    const page = item.page_number > 0 ? `p.${item.page_number}` : null;
    return (
        <li className="cx-passage">
            <button type="button" className="cx-passage-head" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
                <span className="cx-passage-label">{label}{page && <span className="cx-passage-page">{page}</span>}</span>
                {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
            {expanded && (
                <div className="cx-passage-body">
                    <p>{item.snippet}</p>
                    {pdfUrlOf(item) && (
                        <button type="button" className="cx-text-btn" onClick={(e) => onOpen(item, e.currentTarget)}>
                            Open page
                        </button>
                    )}
                </div>
            )}
        </li>
    );
}
