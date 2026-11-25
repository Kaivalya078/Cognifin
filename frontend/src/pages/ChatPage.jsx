/**
 * ChatPage
 * =========
 * Main chat interface with sidebar, header, message area, and keyboard shortcuts.
 * Supports session-scoped PDF upload with a progress overlay.
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Toaster, toast } from 'react-hot-toast';
import { askQuestionStream, checkHealth, uploadPdf } from '../api';
import { useAuth } from '../context/AuthContext';
import useConversations from '../hooks/useConversations';
import Sidebar from '../components/chat/Sidebar';
import ChatHeader from '../components/chat/ChatHeader';
import MessageList from '../components/chat/MessageList';
import ChatInput from '../components/chat/ChatInput';
import SourcePane from '../components/chat/SourcePane';
import ChatErrorBoundary from '../components/chat/ChatErrorBoundary';
import { AlertTriangle, X } from 'lucide-react';
import { pdfUrlOf, openFiling, isFiling, sourceLabel } from '../utils/sources';
import { bare } from '../utils/citations';
import { readQuestionParam } from '../utils/landing';
import '../styles/chat-v2.css';

// Must match SHOWCASE_QUESTIONS in backend/main.py (pre-answered at startup, so instant).
const SUGGESTED = [
    "What was TCS's consolidated revenue from operations in FY2024?",
    'When did the amalgamation of HDFC Limited with HDFC Bank become effective?',
    'Which acquisitions did the Infosys board approve in fiscal 2025?',
    "What was Hindustan Unilever's profit after tax in FY2025?",
];

const NARROW = '(max-width: 899px)';

// ── Upload progress stages, driven by /upload's stream ──────────
// Index = position in the list; the server names map onto it.
const UPLOAD_STAGES = ['Uploading', 'Reading & chunking', 'Embedding', 'Indexing'];
const STAGE_INDEX = { chunking: 1, embedding: 2, indexing: 3 };

function uploadProgress(ev) {
    if (ev.name === 'chunking') return { stage: 1, pct: 10, label: null };
    if (ev.name === 'embedding') {
        return {
            stage: 2,
            pct: Math.round(10 + (80 * ev.done) / ev.total),
            label: `Embedding ${ev.done} / ${ev.total}`,
        };
    }
    return { stage: STAGE_INDEX[ev.name] ?? 3, pct: 95, label: null };
}

// ── Upload Progress Overlay component ────────────────────────────
function UploadProgressOverlay({ fileName, stageIndex, pct, stageLabel, done, error }) {
    return (
        <div className="cx-overlay" role="status" aria-live="polite">
            <div className="cx-overlay-card">
                <p className="cx-overlay-title">{error ? 'Upload failed' : done ? 'Analysis ready' : 'Processing PDF'}</p>
                <p className="cx-overlay-file">{fileName}</p>
                {error ? (
                    <p className="cx-overlay-error">{error}</p>
                ) : (
                    <>
                        <div className="cx-progress" aria-hidden="true">
                            <div className="cx-progress-fill" style={{ width: `${pct}%` }} />
                        </div>
                        <ol className="cx-stages">
                            {UPLOAD_STAGES.map((s, i) => (
                                <li key={s} className={i < stageIndex ? 'is-done' : i === stageIndex ? 'is-active' : ''}>
                                    {i === stageIndex && stageLabel ? stageLabel : s}
                                </li>
                            ))}
                        </ol>
                        {done && <p className="cx-overlay-done">Ask about this PDF in this chat.</p>}
                    </>
                )}
            </div>
        </div>
    );
}

function useMediaQuery(query) {
    const [match, setMatch] = useState(() => window.matchMedia(query).matches);
    useEffect(() => {
        const mq = window.matchMedia(query);
        const on = () => setMatch(mq.matches);
        mq.addEventListener('change', on);
        return () => mq.removeEventListener('change', on);
    }, [query]);
    return match;
}

// The mobile source sheet: a native modal dialog (focus trap, Escape, inert page).
function SourceSheet({ titleId, onClose, children }) {
    const ref = useRef(null);
    useEffect(() => {
        const d = ref.current;
        if (d && !d.open) d.showModal();
        return () => d?.open && d.close();
    }, []);
    return (
        <dialog ref={ref} className="cx-sheet" aria-labelledby={titleId}
            onCancel={(e) => { e.preventDefault(); onClose(); }}
            // A close that skipped cancel (Android back). Ignored when already reopened:
            // the cleanup's close() fires its event after a remount's showModal().
            onClose={(e) => { if (!e.currentTarget.open) onClose(); }}>
            {children}
        </dialog>
    );
}

export default function ChatPage() {
    const {
        conversations,
        activeConversation,
        activeId,
        createConversation,
        addMessage,
        setConversationId,
        selectConversation,
        deleteConversation,
        undoDelete,
        renameConversation,
    } = useConversations();

    const { isAuthenticated } = useAuth();
    const [isLoading, setIsLoading] = useState(false);
    const [streaming, setStreaming] = useState(null); // { stages, text } while answering
    const [showUploadForm, setShowUploadForm] = useState(false);
    const [sidebarCollapsed, setSidebarCollapsed] = useState(() => window.matchMedia(NARROW).matches);
    const [backendDown, setBackendDown] = useState(false);
    const [bannerDismissed, setBannerDismissed] = useState(false);

    // Per-conversation session state (convId → { sessionId, fileName })
    const [sessions, setSessions] = useState({});

    // Upload progress state
    const [uploading, setUploading] = useState(false);
    const [uploadFileName, setUploadFileName] = useState('');
    const [uploadStage, setUploadStage] = useState(0);
    const [uploadPct, setUploadPct] = useState(0);
    const [uploadDone, setUploadDone] = useState(false);
    const [uploadError, setUploadError] = useState(null);
    const [uploadStageLabel, setUploadStageLabel] = useState(null);

    // The cited page open beside the answer: { item, anchor } (anchor gets focus back on close).
    const [source, setSource] = useState(null);
    const listWasCollapsed = useRef(false);
    const isNarrow = useMediaQuery(NARROW);

    // A ref mirror so these callbacks stay stable (the activeId effect must not re-run on open).
    const sourceRef = useRef(null);
    sourceRef.current = source;
    const collapsedRef = useRef(sidebarCollapsed);
    collapsedRef.current = sidebarCollapsed;

    const openSource = useCallback((item, anchor) => {
        if (isFiling(item)) { openFiling(item); return; }
        if (!sourceRef.current) {
            listWasCollapsed.current = collapsedRef.current;
            setSidebarCollapsed(true);
        }
        setSource({ item: { ...item }, anchor }); // fresh object: re-clicking a chip jumps back to its page
    }, []);

    const closeSource = useCallback((refocus = true) => {
        const prev = sourceRef.current;
        if (!prev) return;
        setSidebarCollapsed(listWasCollapsed.current);
        setSource(null);
        if (refocus) setTimeout(() => prev.anchor?.focus?.(), 0);
    }, []);

    // Ctrl+B while a source is open changes what the list returns to on close.
    const toggleSidebar = useCallback(() => {
        setSidebarCollapsed((c) => !c);
        listWasCollapsed.current = !listWasCollapsed.current;
    }, []);

    // A source belongs to the chat it was opened in. Keyed on the conversation itself:
    // guests never get an activeId, but New chat still clears their conversation.
    const convKey = activeConversation?.id ?? null;
    useEffect(() => closeSource(false), [convKey, closeSource]);

    // Escape closes the desktop pane (the mobile dialog handles its own Escape).
    useEffect(() => {
        if (!source || isNarrow) return;
        // Not when Escape is cancelling something in the chat list (rename, menu).
        const onKey = (e) => {
            if (e.key === 'Escape' && !e.defaultPrevented && !e.target.closest?.('.cx-side')) closeSource();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [source, isNarrow, closeSource]);

    // Escape closes the narrow-screen chat list overlay.
    useEffect(() => {
        if (sidebarCollapsed || !isNarrow) return;
        const onKey = (e) => { if (e.key === 'Escape' && !e.defaultPrevented && e.target.tagName !== 'INPUT') toggleSidebar(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [sidebarCollapsed, isNarrow, toggleSidebar]);

    // Active session for current chat
    const activeSession = activeId ? sessions[activeId] : null;

    // The upload panel belongs to the chat it was opened in: close it on New chat / switch.
    useEffect(() => setShowUploadForm(false), [activeId]);

    // --- Health Check on Mount ---
    useEffect(() => {
        checkHealth()
            .then(() => setBackendDown(false))
            .catch(() => {
                setBackendDown(true);
                setBannerDismissed(false);
            });
    }, []);

    // Every delete path: gone from view at once, Undo for 5s, then the server delete.
    const handleDelete = useCallback((id) => {
        deleteConversation(id);
        toast((t) => (
            <span className="cx-toast">
                Chat deleted
                <button type="button" onClick={() => {
                    toast.dismiss(t.id);
                    if (!undoDelete(id)) toast('Already deleted');
                }}>Undo</button>
            </span>
        ), { duration: 5000 });
    }, [deleteConversation, undoDelete]);

    // --- Keyboard Shortcuts ---
    useEffect(() => {
        const handleKeyboard = (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
                e.preventDefault();
                selectConversation(null); // same as handleNewChat (defined below)
                toast('New chat', { duration: 1500 });
            }
            if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
                e.preventDefault();
                toggleSidebar();
            }
            // Not while typing: there Ctrl+Backspace deletes a word.
            const typing = /^(INPUT|TEXTAREA)$/.test(e.target.tagName);
            if ((e.ctrlKey || e.metaKey) && e.key === 'Backspace' && activeId && !typing) {
                e.preventDefault();
                handleDelete(activeId);
            }
        };
        window.addEventListener('keydown', handleKeyboard);
        return () => window.removeEventListener('keydown', handleKeyboard);
    }, [activeId, handleDelete, selectConversation, toggleSidebar]);

    // --- Send Message ---
    const handleSend = useCallback(
        async (question) => {
            // Use existing active conversation id (may be null for first message)
            const convId = activeId;
            const conversationId = activeConversation?.id && activeConversation.id !== 'pending'
                ? activeConversation.id
                : null;

            addMessage(convId, 'user', question);
            setStreaming({ stages: [], text: '' });
            setIsLoading(true);

            // Pass session_id if this chat has one
            const sessionId = sessions[convId]?.sessionId || null;

            try {
                const data = await askQuestionStream(question, sessionId, conversationId, (type, ev) => {
                    if (type === 'stage') setStreaming((s) => ({ ...s, stages: [...s.stages, ev] }));
                    else if (type === 'token') setStreaming((s) => ({ ...s, text: s.text + ev.text }));
                });

                // If backend created a new conversation, store its id
                if (data.conversation_id && data.conversation_id !== conversationId) {
                    // A PDF uploaded before the first answer is keyed by the old (empty) id:
                    // move it, or later questions in this chat silently lose the PDF.
                    setSessions(prev => (prev[convId] && !prev[data.conversation_id])
                        ? { ...prev, [data.conversation_id]: prev[convId] }
                        : prev);
                    setConversationId(data.conversation_id);
                }

                addMessage(data.conversation_id || convId, 'assistant', data.answer, {
                    citations: data.citations || [],
                    evidence: data.evidence || [],
                    pipeline: data.metadata || {},
                    follow_ups: data.follow_ups || [],
                });
            } catch (err) {
                const errorMsg = err.message || 'Something went wrong. Is the backend running?';
                // Anonymous trial used up: offer the way forward, not just an error
                const signIn = err.status === 429 && !isAuthenticated ? ' [Sign in](/login) to keep asking.' : '';
                addMessage(convId, 'assistant', `${errorMsg}${signIn}`, {});
                toast.error(errorMsg, { duration: 4000 });
            } finally {
                setIsLoading(false);
                setStreaming(null);
            }
        },
        [activeId, activeConversation, addMessage, setConversationId, sessions, isAuthenticated]
    );

    // --- Upload PDF ---
    // Opened from the landing page's ask bar as /chat?q=...: send it once, then drop q
    // from the URL so a refresh doesn't resend. The ref guards StrictMode's double effect.
    const location = useLocation();
    const navigate = useNavigate();
    const handedOff = useRef(false);
    useEffect(() => {
        const q = readQuestionParam(location.search);
        if (!q || handedOff.current) return;
        handedOff.current = true;
        navigate('/chat', { replace: true });
        handleSend(q);
    }, [location.search, navigate, handleSend]);

    const handleUpload = useCallback(
        async (file, companyName, year) => {
            // Make sure we have a conversation to attach the session to
            let convId = activeId;
            if (!convId) convId = createConversation();

            // Start progress overlay
            setUploadFileName(file.name);
            setUploadStage(0);
            setUploadPct(0);
            setUploadStageLabel(null);
            setUploadDone(false);
            setUploadError(null);
            setUploading(true);

            try {
                const result = await uploadPdf(file, companyName, year, (type, ev) => {
                    if (type !== 'stage') return;
                    const p = uploadProgress(ev);
                    setUploadStage(p.stage);
                    setUploadPct(p.pct);
                    setUploadStageLabel(p.label);
                });

                // Lock progress at 100% and show done
                setUploadStage(UPLOAD_STAGES.length);
                setUploadPct(100);
                setUploadDone(true);

                // Store session for this conversation only
                setSessions(prev => ({
                    ...prev,
                    [convId]: { sessionId: result.session_id, fileName: file.name },
                }));

                // Add a system message confirming the upload
                addMessage(
                    convId,
                    'assistant',
                    `**${file.name}** is ready: ${result.chunks} passages indexed. Ask about it in this chat.`,
                    {}
                );

                // Auto-close overlay after 2s
                setTimeout(() => setUploading(false), 2000);

            } catch (err) {
                setUploadError(err.message || 'Upload failed. Please try again.');
                setTimeout(() => setUploading(false), 4000);
                toast.error('Upload failed: ' + (err.message || 'Unknown error'), { duration: 4000 });
            }
        },
        [activeId, createConversation, addMessage]
    );

    const handleClearUpload = () => {
        if (!activeId) return;
        setSessions(prev => {
            const next = { ...prev };
            delete next[activeId];
            return next;
        });
        toast('PDF removed from this chat', { duration: 2000 });
    };

    // On narrow screens the list is an overlay: picking a chat closes it.
    const foldIfNarrow = () => { if (window.matchMedia(NARROW).matches) setSidebarCollapsed(true); };
    const handleNewChat = () => { selectConversation(null); foldIfNarrow(); };
    const handleSelect = (id) => { selectConversation(id); foldIfNarrow(); };

    return (
        <div className="cx-page">
            <Toaster
                position="top-center"
                toastOptions={{
                    style: {
                        background: 'var(--cf-glass-strong)',
                        backdropFilter: 'var(--cf-blur)',
                        color: 'var(--cf-ink)',
                        border: '1px solid var(--cf-line)',
                        borderRadius: 'var(--cf-r-md)',
                        fontFamily: 'var(--cf-font-sans)',
                        fontSize: '13px',
                    },
                }}
            />

            {/* Upload Progress Overlay */}
            {uploading && (
                <UploadProgressOverlay
                    fileName={uploadFileName}
                    stageIndex={uploadStage}
                    stageLabel={uploadStageLabel}
                    pct={uploadPct}
                    done={uploadDone}
                    error={uploadError}
                />
            )}

            {/* Sidebar + Main row */}
            <div className="cx-body">
                <Sidebar
                    conversations={conversations}
                    activeId={activeId}
                    onSelect={handleSelect}
                    onNewChat={handleNewChat}
                    onDelete={handleDelete}
                    onRename={renameConversation}
                    isCollapsed={sidebarCollapsed}
                    onToggleCollapse={toggleSidebar}
                />

                {/* Narrow screens: the open list is an overlay; tapping outside closes it */}
                {!sidebarCollapsed && isNarrow && (
                    <button type="button" className="cx-scrim" aria-label="Close chat list" onClick={toggleSidebar} />
                )}

                <main className="cx-main">
                    {sidebarCollapsed && <ChatHeader onToggleSidebar={toggleSidebar} />}
                    {/* A slim row inside the column, so the input never leaves the screen */}
                    {backendDown && !bannerDismissed && (
                        <div className="cx-banner" role="status">
                            <AlertTriangle size={14} aria-hidden="true" />
                            <span>Can&apos;t reach the server. It may still be starting up.</span>
                            <button type="button" className="cx-icon-btn is-small" onClick={() => setBannerDismissed(true)}
                                aria-label="Dismiss">
                                <X size={12} />
                            </button>
                        </div>
                    )}
                    <ChatErrorBoundary key={convKey}>
                    {activeConversation && activeConversation.messages.length > 0 ? (
                        <MessageList
                            messages={activeConversation.messages}
                            isLoading={isLoading}
                            streaming={streaming}
                            onFollowUp={handleSend}
                            // A chat that already has a PDF gets no upload card (it would replace that PDF)
                            onRequestUpload={activeSession ? null : () => setShowUploadForm(true)}
                            onOpenSource={openSource}
                            activeSourceId={source ? bare(source.item.chunk_id) : null}
                        />
                    ) : (
                        <div className="cx-welcome">
                            <h1 className="cx-welcome-title">Ask about any NIFTY 50 company&apos;s filings.</h1>
                            <ul className="cx-suggested" aria-label="Suggested questions">
                                {SUGGESTED.map((text) => (
                                    <li key={text}>
                                        <button type="button" className="cx-followup" onClick={() => handleSend(text)}>{text}</button>
                                    </li>
                                ))}
                            </ul>
                            <p className="cx-shortcuts">
                                Shortcuts: <kbd>Ctrl+N</kbd> new chat, <kbd>Ctrl+B</kbd> chat list
                            </p>
                        </div>
                    )}
                    </ChatErrorBoundary>
                    <ChatInput
                        onSend={handleSend}
                        onUpload={handleUpload}
                        isLoading={isLoading}
                        uploadedFile={activeSession?.fileName || null}
                        onClearUpload={handleClearUpload}
                        showUploadForm={showUploadForm}
                        setShowUploadForm={setShowUploadForm}
                    />
                </main>

                {source && <ChatErrorBoundary>{(() => {
                    const pane = (
                        <SourcePane item={source.item} pdfUrl={pdfUrlOf(source.item)}
                            onClose={() => closeSource()} titleId="cx-source-title" />
                    );
                    return isNarrow
                        ? <SourceSheet titleId="cx-source-title" onClose={() => closeSource()}>{pane}</SourceSheet>
                        : <aside className="cx-source"
                            aria-label={`${sourceLabel(source.item)}, page ${source.item.page_number || 1}`}>{pane}</aside>;
                })()}</ChatErrorBoundary>}
            </div>
        </div>
    );
}
