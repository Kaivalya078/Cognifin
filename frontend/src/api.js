/**
 * FinSight AI - API Client
 * ========================
 * Handles communication with the FastAPI backend.
 * All protected requests include the JWT Authorization header.
 * On 401 responses, the token is cleared and the user is redirected to /login.
 */

import { getToken, clearSession } from './utils/auth';

// Base URL from Vite env variable, fallback to localhost
export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

// ── Helpers ──────────────────────────────────────────────────

function authHeaders() {
    const token = getToken();
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
}

/**
 * Global 401 interceptor (addendum §4).
 * Call this after every fetch to protected endpoints.
 */
function handle401(response) {
    if (response.status === 401) {
        clearSession();
        window.location.href = "/login";
    }
    return response;
}

// ── Auth Endpoints (public) ─────────────────────────────────

export async function registerUser(name, email, password) {
    const response = await fetch(`${API_BASE}/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password }),
    });
    if (!response.ok) {
        const err = await response.json().catch(() => null);
        throw new Error(err?.detail || `Registration failed (${response.status})`);
    }
    return response.json();
}

export async function loginUser(email, password) {
    const response = await fetch(`${API_BASE}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
        const err = await response.json().catch(() => null);
        throw new Error(err?.detail || `Login failed (${response.status})`);
    }
    return response.json();
}

// ── Health ───────────────────────────────────────────────────

export async function checkHealth() {
    const response = await fetch(`${API_BASE}/health`);
    if (!response.ok) {
        throw new Error(`Health check failed: ${response.status}`);
    }
    return response.json();
}

// ── Streaming (server-sent events over POST) ────────────────

/**
 * POST and read an event stream (stage / token / final / error frames).
 * Calls onEvent(type, data) per frame; resolves with the final frame's data.
 * Non-OK responses and error frames throw Error(detail) with .status.
 */
export async function streamPost(path, body, onEvent, timeoutMs) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    const isForm = body instanceof FormData;
    const headers = isForm ? {} : authHeaders();
    if (isForm && getToken()) headers["Authorization"] = `Bearer ${getToken()}`;
    try {
        const response = await fetch(`${API_BASE}${path}`, {
            method: "POST",
            headers,
            body: isForm ? body : JSON.stringify(body),
            signal: controller.signal,
        });
        handle401(response);
        if (!response.ok) {
            const errorData = await response.json().catch(() => null);
            const error = new Error(errorData?.detail || `Server error (${response.status})`);
            error.status = response.status;
            throw error;
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        const lost = "Connection lost before the answer finished. Please try again.";
        for (;;) {
            let chunk;
            try {
                chunk = await reader.read();
            } catch (e) {
                if (e.name === "AbortError") throw e;
                throw new Error(lost);
            }
            const { value, done } = chunk;
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let cut;
            while ((cut = buffer.indexOf("\n\n")) !== -1) {
                const frame = buffer.slice(0, cut);
                buffer = buffer.slice(cut + 2);
                let type = "message", data = "";
                for (const line of frame.split("\n")) {
                    if (line.startsWith("event: ")) type = line.slice(7);
                    else if (line.startsWith("data: ")) data += line.slice(6);
                }
                const parsed = JSON.parse(data);
                if (type === "error") {
                    const error = new Error(parsed.detail || "Something went wrong");
                    error.status = parsed.status;
                    throw error;
                }
                onEvent?.(type, parsed);
                if (type === "final") return parsed;
            }
        }
        throw new Error(lost);
    } finally {
        clearTimeout(timeoutId);
    }
}

// ── Chat (protected) ────────────────────────────────────────

export function askQuestionStream(question, sessionId, conversationId, onEvent) {
    const body = { question };
    if (sessionId) body.session_id = sessionId;
    if (conversationId) body.conversation_id = conversationId;
    return streamPost("/chat/stream", body, onEvent, 120000);
}

// ── Upload (protected) ──────────────────────────────────────

export function uploadPdf(file, companyName, year, onEvent) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('company_name', companyName);
    if (year) formData.append('year', year);
    return streamPost("/upload", formData, onEvent, 300000);
}

// ── Conversations (protected) ───────────────────────────────

export async function getConversations(page = 1, limit = 50) {
    const response = await fetch(
        `${API_BASE}/conversations?page=${page}&limit=${limit}`,
        { headers: authHeaders() },
    );
    handle401(response);
    if (!response.ok) {
        const err = await response.json().catch(() => null);
        throw new Error(err?.detail || `Failed to load conversations (${response.status})`);
    }
    return response.json();
}

export async function getConversation(id) {
    const response = await fetch(`${API_BASE}/conversations/${id}`, {
        headers: authHeaders(),
    });
    handle401(response);
    if (!response.ok) {
        const err = await response.json().catch(() => null);
        throw new Error(err?.detail || `Failed to load conversation (${response.status})`);
    }
    return response.json();
}

export async function deleteConversationApi(id) {
    const response = await fetch(`${API_BASE}/conversations/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
    });
    handle401(response);
    if (!response.ok) {
        const err = await response.json().catch(() => null);
        throw new Error(err?.detail || `Failed to delete conversation (${response.status})`);
    }
    return response.json();
}

export async function renameConversationApi(id, title) {
    const response = await fetch(`${API_BASE}/conversations/${id}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify({ title }),
    });
    handle401(response);
    if (!response.ok) {
        const err = await response.json().catch(() => null);
        throw new Error(err?.detail || `Failed to rename conversation (${response.status})`);
    }
    return response.json();
}
