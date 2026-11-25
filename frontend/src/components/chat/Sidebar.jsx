/**
 * Sidebar — the chat list. A smoked glass column; collapsed, a thin rail
 * (on narrow screens it hides and the header's menu button opens it as an overlay).
 * Right-click (or double-click) a chat to rename it.
 */

import { useState, useEffect, useRef } from 'react';
import { Trash2, LogOut, LogIn, PanelLeftClose, PanelLeftOpen, Pencil, Search, X, SquarePen } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Wordmark } from '../landing/Navbar';

export default function Sidebar({
    conversations,
    activeId,
    onSelect,
    onNewChat,
    onDelete,
    onRename,
    isCollapsed,
    onToggleCollapse,
}) {
    const { user, logout, isAuthenticated } = useAuth();
    const navigate = useNavigate();
    const [query, setQuery] = useState('');

    const handleLogout = () => { logout(); navigate('/'); };

    const today = new Date();
    const todayStr = today.toDateString();
    const yestStr = new Date(today - 86400000).toDateString();
    const grouped = { today: [], yesterday: [], older: [] };

    const filtered = query.trim()
        ? conversations.filter((c) => c.title.toLowerCase().includes(query.toLowerCase()))
        : conversations;

    filtered.forEach((conv) => {
        const d = new Date(conv.updatedAt).toDateString();
        if (d === todayStr) grouped.today.push(conv);
        else if (d === yestStr) grouped.yesterday.push(conv);
        else grouped.older.push(conv);
    });

    if (isCollapsed) {
        return (
            <aside className="cx-side is-collapsed" aria-label="Chats">
                <button type="button" className="cx-icon-btn" onClick={onToggleCollapse} aria-label="Show chat list">
                    <PanelLeftOpen size={18} />
                </button>
                <button type="button" className="cx-icon-btn" onClick={onNewChat} aria-label="New chat">
                    <SquarePen size={18} />
                </button>
                <span className="cx-side-spacer" />
                {isAuthenticated ? (
                    <button type="button" className="cx-icon-btn" onClick={handleLogout} aria-label="Sign out">
                        <LogOut size={18} />
                    </button>
                ) : (
                    <button type="button" className="cx-icon-btn" onClick={() => navigate('/login')} aria-label="Sign in">
                        <LogIn size={18} />
                    </button>
                )}
            </aside>
        );
    }

    return (
        <aside className="cx-side" aria-label="Chats">
            <div className="cx-side-head">
                <Wordmark />
                <button type="button" className="cx-icon-btn" onClick={onToggleCollapse} aria-label="Hide chat list">
                    <PanelLeftClose size={18} />
                </button>
            </div>

            <button type="button" className="cx-side-new" onClick={onNewChat}>
                <SquarePen size={16} />
                <span>New chat</span>
            </button>

            <div className="cx-side-search">
                <Search size={14} aria-hidden="true" />
                <input
                    type="search"
                    placeholder="Search chats"
                    aria-label="Search chats"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                />
                {query && (
                    <button type="button" className="cx-icon-btn is-small" onClick={() => setQuery('')} aria-label="Clear search">
                        <X size={12} />
                    </button>
                )}
            </div>

            <nav className="cx-side-list" aria-label="Chat history">
                {filtered.length === 0 && (
                    <p className="cx-side-empty">
                        {query ? <>No chats match &ldquo;{query}&rdquo;.</> : isAuthenticated
                            ? 'Your chats will appear here.' : 'Sign in to keep your chats.'}
                    </p>
                )}
                {[
                    { label: 'Today', items: grouped.today },
                    { label: 'Yesterday', items: grouped.yesterday },
                    { label: 'Older', items: grouped.older },
                ].map(({ label, items }) => items.length > 0 && (
                    <div className="cx-side-group" key={label}>
                        <h2 className="cx-side-group-label">{label}</h2>
                        <ul>
                            {items.map((conv) => (
                                <ConversationItem
                                    key={conv.id}
                                    conv={conv}
                                    isActive={conv.id === activeId}
                                    onSelect={() => onSelect(conv.id)}
                                    onDelete={() => onDelete(conv.id)}
                                    onRename={(title) => onRename(conv.id, title)}
                                />
                            ))}
                        </ul>
                    </div>
                ))}
            </nav>

            <div className="cx-side-user">
                {isAuthenticated ? (
                    <>
                        <div className="cx-side-user-text">
                            <span className="cx-side-user-name">{user?.name || 'Signed in'}</span>
                            {user?.email && <span className="cx-side-user-sub">{user.email}</span>}
                        </div>
                        <button type="button" className="cx-icon-btn" onClick={handleLogout} aria-label="Sign out">
                            <LogOut size={16} />
                        </button>
                    </>
                ) : (
                    <>
                        <div className="cx-side-user-text">
                            <span className="cx-side-user-name">Guest</span>
                            <span className="cx-side-user-sub">Sign in to save your chats</span>
                        </div>
                        <button type="button" className="cx-icon-btn" onClick={() => navigate('/login')} aria-label="Sign in">
                            <LogIn size={16} />
                        </button>
                    </>
                )}
            </div>
        </aside>
    );
}

function ConversationItem({ conv, isActive, onSelect, onDelete, onRename }) {
    const [menu, setMenu] = useState(null);   // {x, y}
    const [renaming, setRenaming] = useState(false);
    const [draft, setDraft] = useState(conv.title);
    const inputRef = useRef(null);
    const menuRef = useRef(null);

    useEffect(() => {
        if (renaming) setTimeout(() => inputRef.current?.select(), 0);
    }, [renaming]);

    useEffect(() => {
        if (!menu) return;
        const close = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenu(null); };
        const esc = (e) => { if (e.key === 'Escape') setMenu(null); };
        document.addEventListener('mousedown', close);
        document.addEventListener('keydown', esc);
        return () => {
            document.removeEventListener('mousedown', close);
            document.removeEventListener('keydown', esc);
        };
    }, [menu]);

    const startRename = () => { setDraft(conv.title); setRenaming(true); setMenu(null); };
    const commitRename = () => {
        const t = draft.trim();
        if (t && t !== conv.title) onRename(t);
        setRenaming(false);
    };
    const handleKeyDown = (e) => {
        if (e.key === 'Enter') { e.preventDefault(); commitRename(); }
        if (e.key === 'Escape') { setRenaming(false); setDraft(conv.title); }
    };

    return (
        <li className={`cx-conv${isActive ? ' is-active' : ''}`}
            onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }); }}>
            {renaming ? (
                <input
                    ref={inputRef}
                    className="cx-conv-rename"
                    aria-label="Chat name"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={handleKeyDown}
                    onBlur={commitRename}
                />
            ) : (
                <>
                    <button type="button" className="cx-conv-title" onClick={onSelect} onDoubleClick={startRename}
                        aria-current={isActive ? 'page' : undefined}>
                        {conv.title}
                    </button>
                    <button type="button" className="cx-icon-btn is-small cx-conv-del" onClick={onDelete}
                        aria-label={`Delete ${conv.title}`}>
                        <Trash2 size={13} />
                    </button>
                </>
            )}

            {menu && (
                <div ref={menuRef} className="cx-menu" role="menu" style={{ top: menu.y, left: menu.x }}>
                    <button type="button" role="menuitem" onClick={startRename}><Pencil size={13} /> Rename</button>
                    <button type="button" role="menuitem" className="is-danger"
                        onClick={() => { setMenu(null); onDelete(); }}><Trash2 size={13} /> Delete</button>
                </div>
            )}
        </li>
    );
}
