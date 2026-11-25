/**
 * ChatInput Component
 * ====================
 * Bottom input area for sending messages.
 * Includes PDF upload button that opens an inline form.
 */

import { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, X, Upload } from 'lucide-react';

// showUploadForm lives in ChatPage so a "Not available" answer's card can open it too.
export default function ChatInput({ onSend, onUpload, isLoading, uploadedFile, onClearUpload,
                                    showUploadForm, setShowUploadForm }) {
    const [question, setQuestion] = useState('');
    const [selectedFile, setSelectedFile] = useState(null);
    const [companyName, setCompanyName] = useState('');
    const [year, setYear] = useState(String(new Date().getFullYear()));
    const textareaRef = useRef(null);
    const fileInputRef = useRef(null);

    // Auto-resize textarea
    useEffect(() => {
        const el = textareaRef.current;
        if (el) {
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 160) + 'px';
        }
    }, [question]);

    const handleSubmit = (e) => {
        e.preventDefault();
        const trimmed = question.trim();
        if (!trimmed || isLoading) return;
        onSend(trimmed);
        setQuestion('');
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
        }
    };

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        setSelectedFile(file);
        // Auto-fill company name from filename (remove year/ext)
        const name = file.name.replace(/\.[^.]+$/, '').replace(/[\d_-]+/g, ' ').trim();
        if (!companyName) setCompanyName(name);
    };

    const handleUploadSubmit = (e) => {
        e.preventDefault();
        if (!selectedFile || !companyName.trim()) return;
        onUpload(selectedFile, companyName.trim(), year);
        setShowUploadForm(false);
        setSelectedFile(null);
        setCompanyName('');
    };

    const cancelUploadForm = () => {
        setShowUploadForm(false);
        setSelectedFile(null);
        setCompanyName('');
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    return (
        <div className="cx-input-area">
            <div className="cx-input-inner">
                {uploadedFile && (
                    <div className="cx-pill">
                        <Paperclip size={12} aria-hidden="true" />
                        <span>Asking about {uploadedFile} in this chat</span>
                        <button type="button" className="cx-icon-btn is-small" onClick={onClearUpload}
                            aria-label="Remove the uploaded PDF from this chat">
                            <X size={12} />
                        </button>
                    </div>
                )}

                {showUploadForm && (
                    <div className="cx-upload">
                        <div className="cx-upload-head">
                            <span>Upload a PDF for this chat</span>
                            <button type="button" className="cx-icon-btn is-small" onClick={cancelUploadForm} aria-label="Close upload">
                                <X size={14} />
                            </button>
                        </div>
                        <form onSubmit={handleUploadSubmit} className="cx-upload-body">
                            <button type="button" className={`cx-drop${selectedFile ? ' has-file' : ''}`}
                                onClick={() => fileInputRef.current?.click()}>
                                <Upload size={16} aria-hidden="true" />
                                {selectedFile
                                    ? <span>{selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(1)} MB)</span>
                                    : <span>Choose a PDF</span>}
                            </button>
                            <input ref={fileInputRef} type="file" accept=".pdf" hidden onChange={handleFileChange} />
                            <div className="cx-upload-fields">
                                <input className="cx-field" type="text" placeholder="Company name" aria-label="Company name"
                                    value={companyName} onChange={(e) => setCompanyName(e.target.value)} required />
                                <input className="cx-field is-year" type="text" placeholder="Year" aria-label="Year"
                                    value={year} onChange={(e) => setYear(e.target.value)} maxLength={4} />
                            </div>
                            <button type="submit" className="cx-btn" disabled={!selectedFile || !companyName.trim()}>
                                Process PDF
                            </button>
                        </form>
                    </div>
                )}

                <form className="cx-input" onSubmit={handleSubmit}>
                    <button type="button" className={`cx-icon-btn${uploadedFile ? ' is-on' : ''}`}
                        onClick={() => setShowUploadForm((v) => !v)} disabled={isLoading}
                        aria-label="Upload a PDF for this chat" aria-expanded={showUploadForm}>
                        <Paperclip size={16} />
                    </button>
                    <textarea
                        ref={textareaRef}
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={uploadedFile ? `Ask about ${uploadedFile} or any covered company` : "Ask about a company's filings"}
                        aria-label="Question"
                        disabled={isLoading}
                        rows={1}
                    />
                    <button type="submit" className="cx-send" disabled={isLoading || !question.trim()} aria-label="Send">
                        <Send size={16} />
                    </button>
                </form>
                <p className="cx-input-hint">Enter to send, Shift+Enter for a new line</p>
            </div>
        </div>
    );
}
