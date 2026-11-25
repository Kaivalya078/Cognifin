import { API_BASE } from '../api';
import { bare } from './citations';
import { docLabel } from './chatFormat';

// pdf_url is absolute when PDFs live in object storage, or an API path
// (/pdfs/COMPANY/YEAR.pdf) when the backend serves them itself.
export const pdfUrlOf = (item) => !item?.pdf_url ? null
    : /^https?:\/\//.test(item.pdf_url) ? item.pdf_url
    : `${API_BASE}${item.pdf_url}`;

// Verified-figure rows (fin_N) point at BSE/NSE filings we don't serve: open in a new tab.
export const openFiling = (item) => {
    const url = pdfUrlOf(item);
    if (url) window.open(url + (/\.pdf($|\?)/i.test(url) && item.page_number > 0 ? `#page=${item.page_number}` : ''), '_blank', 'noopener');
};

export const isFiling = (item) => bare(item?.chunk_id || '').startsWith('fin_');

export const sourceLabel = (item) => docLabel(item?.document_label
    || item?.pdf_url?.split('/').pop()?.replace(/\.pdf$/i, ''))
    || 'Source';
