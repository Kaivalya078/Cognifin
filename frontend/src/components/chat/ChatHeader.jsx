/**
 * ChatHeader — narrow screens only (CSS hides it from 900px up, where the rail does this job):
 * the menu button that opens the chat list, and the wordmark.
 */
import { PanelLeftOpen } from 'lucide-react';
import { Wordmark } from '../landing/Navbar';

export default function ChatHeader({ onToggleSidebar }) {
    return (
        <header className="cx-header">
            <button type="button" className="cx-icon-btn" onClick={onToggleSidebar} aria-label="Show chat list">
                <PanelLeftOpen size={18} />
            </button>
            <Wordmark />
        </header>
    );
}
