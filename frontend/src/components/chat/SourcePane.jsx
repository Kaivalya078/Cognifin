/**
 * SourcePane — the cited PDF page beside the answer (a sheet on mobile, see ChatPage).
 * pdf.js renders the page on a canvas and boxes the words of the cited passage.
 * The document loads once per URL; a new chip on the same PDF only changes the page.
 */

import { useEffect, useRef, useState, useMemo } from 'react';
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, ExternalLink } from 'lucide-react';
import * as pdfjsLib from 'pdfjs-dist';
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { sourceLabel } from '../../utils/sources';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

const HIGHLIGHT_COLOR = 'rgba(201, 162, 74, 0.38)';
const MIN_SCALE = 0.6;
const MAX_SCALE = 3.0;
const DEFAULT_SCALE = 1.2;

export default function SourcePane({ item, pdfUrl, onClose, titleId }) {
    const canvasRef = useRef(null);
    const renderTaskRef = useRef(null);
    const [pdfDoc, setPdfDoc] = useState(null);
    const [currentPage, setCurrentPage] = useState(item.page_number || 1);
    const [totalPages, setTotalPages] = useState(0);
    const [scale, setScale] = useState(DEFAULT_SCALE);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    // Memoised: a new array every render would re-render the page every render.
    const highlightWords = useMemo(() => (item.snippet
        ? item.snippet
              .replace(/[^a-zA-Z0-9\s₹%.,]/g, ' ')
              .split(/\s+/)
              .map((w) => w.trim().toLowerCase())
              .filter((w) => w.length > 4)
              .slice(0, 30)
        : []), [item.snippet]);

    // Load the document once per URL.
    useEffect(() => {
        let cancelled = false;
        let loaded = null;
        setPdfDoc(null);
        setLoading(true);
        setError(false);
        pdfjsLib.getDocument({
            url: pdfUrl,
            withCredentials: false,
            rangeChunkSize: 65536,  // byte ranges: fetch only the requested page
            disableFontFace: true,
            isEvalSupported: false,
            enableXfa: false,
        }).promise
            .then((pdf) => {
                if (cancelled) { pdf.destroy(); return; }
                loaded = pdf;
                setPdfDoc(pdf);
                setTotalPages(pdf.numPages);
            })
            .catch(() => { if (!cancelled) { setError(true); setLoading(false); } });
        return () => { cancelled = true; loaded?.destroy(); };
    }, [pdfUrl]);

    // A new item (same or different PDF) jumps to its page.
    useEffect(() => { setCurrentPage(item.page_number || 1); }, [item]);

    useEffect(() => {
        if (!pdfDoc || !canvasRef.current) return;
        let cancelled = false;
        const page = Math.min(Math.max(1, currentPage), pdfDoc.numPages);
        (async () => {
            try { renderTaskRef.current?.cancel(); } catch { /* already done */ }
            setLoading(true);
            setError(false);
            try {
                const pg = await pdfDoc.getPage(page);
                if (cancelled) return;
                const viewport = pg.getViewport({ scale });
                const canvas = canvasRef.current;
                canvas.width = viewport.width;
                canvas.height = viewport.height;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = '#fff';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                const task = pg.render({ canvasContext: ctx, viewport });
                renderTaskRef.current = task;
                await task.promise;
                renderTaskRef.current = null;
                if (cancelled || !highlightWords.length) return;

                const text = await pg.getTextContent();
                if (cancelled) return; // a newer render owns the canvas now
                ctx.save();
                ctx.fillStyle = HIGHLIGHT_COLOR;
                text.items.forEach((t) => {
                    if (!t.str?.trim()) return;
                    const words = t.str.toLowerCase().split(/\s+/);
                    if (!words.some((w) => highlightWords.some((hw) => w.includes(hw) || hw.includes(w)))) return;
                    const [, , , itemScale, tx, ty] = t.transform;
                    const [vA, vB, vC, vD, vE, vF] = viewport.transform;
                    const x = vA * tx + vC * ty + vE;
                    const y = vB * tx + vD * ty + vF;
                    const h = Math.abs(itemScale) * scale * 1.2;
                    ctx.fillRect(x, y - h * 0.85, (t.width || 0) * scale, h);
                });
                ctx.restore();
            } catch (err) {
                if (err?.name !== 'RenderingCancelledException' && !cancelled) setError(true);
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => {
            cancelled = true;
            try { renderTaskRef.current?.cancel(); } catch { /* already done */ }
        };
    }, [pdfDoc, currentPage, scale, highlightWords]);

    const goTo = (p) => setCurrentPage(Math.min(Math.max(1, p), totalPages || 1));
    const label = sourceLabel(item);
    const newTab = `${pdfUrl}#page=${currentPage}`;

    // Arrow keys page only while focus is inside the pane, never while typing in the chat.
    const onKeyDown = (e) => {
        if (e.target.tagName === 'INPUT') return;
        if (e.key === 'ArrowRight') goTo(currentPage + 1);
        if (e.key === 'ArrowLeft') goTo(currentPage - 1);
    };

    return (
        <div className="cx-pane" onKeyDown={onKeyDown}>
            <header className="cx-pane-head">
                <div className="cx-pane-title" id={titleId}>
                    <span className="cx-pane-doc">{label}</span>
                    <span className="cx-pane-page">p.{currentPage}{totalPages ? ` of ${totalPages}` : ''}</span>
                </div>
                <div className="cx-pane-tools">
                    <button type="button" className="cx-icon-btn" onClick={() => goTo(currentPage - 1)}
                        disabled={currentPage <= 1} aria-label="Previous page"><ChevronLeft size={16} /></button>
                    <button type="button" className="cx-icon-btn" onClick={() => goTo(currentPage + 1)}
                        disabled={!totalPages || currentPage >= totalPages} aria-label="Next page"><ChevronRight size={16} /></button>
                    <button type="button" className="cx-icon-btn" aria-label="Zoom out"
                        onClick={() => setScale((s) => Math.max(MIN_SCALE, +(s - 0.2).toFixed(1)))}><ZoomOut size={15} /></button>
                    <button type="button" className="cx-icon-btn" aria-label="Zoom in"
                        onClick={() => setScale((s) => Math.min(MAX_SCALE, +(s + 0.2).toFixed(1)))}><ZoomIn size={15} /></button>
                    <a className="cx-icon-btn" href={newTab} target="_blank" rel="noopener noreferrer"
                        aria-label="Open in new tab"><ExternalLink size={14} /></a>
                    <button type="button" className="cx-icon-btn" onClick={onClose} aria-label="Close source">
                        <X size={16} />
                    </button>
                </div>
            </header>
            <div className="cx-pane-body">
                {error && (
                    <p className="cx-pane-error">
                        Couldn&apos;t load this page. <a href={newTab} target="_blank" rel="noopener noreferrer">Open in new tab</a>
                    </p>
                )}
                {/* Always mounted: the render effect needs the canvas even after an error */}
                <div className={`cx-pane-sheet${loading ? ' is-loading' : ''}`} hidden={error}>
                    <canvas ref={canvasRef} className="cx-pane-canvas" aria-label={`${label}, page ${currentPage}`} />
                </div>
            </div>
        </div>
    );
}
