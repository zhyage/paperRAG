/**
 * Paper RAG — Web UI logic
 */

const API = '/api';

// ── Navigation ────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', (e) => {
        e.preventDefault();
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        el.classList.add('active');
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        const viewId = 'view-' + el.dataset.view;
        document.getElementById(viewId).classList.add('active');
        if (el.dataset.view === 'library') loadLibrary();
        if (el.dataset.view === 'status') loadStatus();
    });
});

// ── Search ────────────────────────────────────────────────
document.getElementById('search-btn').addEventListener('click', doSearch);
document.getElementById('ask-btn').addEventListener('click', doAsk);
document.getElementById('search-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doSearch();
});

async function doSearch() {
    const query = document.getElementById('search-input').value.trim();
    if (!query) return;

    const topK = parseInt(document.getElementById('top-k').value) || 10;
    const section = document.getElementById('section-filter').value;

    const res = await fetch(`${API}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: topK, section_filter: section || null }),
    });

    const data = await res.json();
    renderSearchResults(data);
    document.getElementById('ask-answer').style.display = 'none';
}

async function doAsk() {
    const query = document.getElementById('search-input').value.trim();
    if (!query) return;

    const topK = parseInt(document.getElementById('top-k').value) || 10;
    const section = document.getElementById('section-filter').value;

    document.getElementById('ask-answer').style.display = 'block';
    document.getElementById('answer-content').textContent = 'Thinking...';

    const res = await fetch(`${API}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query, top_k: topK, section_filter: section || null }),
    });

    const data = await res.json();
    document.getElementById('answer-content').textContent = data.answer;

    if (data.sources && data.sources.length) {
        document.getElementById('answer-sources').innerHTML =
            '<strong>Sources:</strong><br>' +
            data.sources.map(s => `• ${s.paper_title} (${s.section}) - score: ${s.score?.toFixed(3)}`).join('<br>');
    }
}

function renderSearchResults(data) {
    const container = document.getElementById('search-results');
    if (!data.results || !data.results.length) {
        container.innerHTML = '<p>No results found.</p>';
        return;
    }
    container.innerHTML = data.results.map(r => `
        <div class="result-item">
            <span class="result-score">${r.score?.toFixed(3) || ''}</span>
            <div class="result-title">${esc(r.paper_title)}</div>
            <div class="result-meta">
                ${r.section_title || r.section_category} · ${(r.authors || []).slice(0, 3).join(', ')}
            </div>
            <div class="result-text">${esc(r.text?.substring(0, 500) || '')}</div>
        </div>
    `).join('');
}

// ── Library ───────────────────────────────────────────────
let libPage = 1;

async function loadLibrary(page = 1) {
    libPage = page;
    const search = document.getElementById('lib-search')?.value || '';
    const params = new URLSearchParams({ page, page_size: 50 });
    if (search) params.set('search', search);

    const res = await fetch(`${API}/papers?${params}`);
    const data = await res.json();
    renderLibrary(data);
}

function renderLibrary(data) {
    const tbody = document.querySelector('#papers-table tbody');
    tbody.innerHTML = (data.papers || []).map(p => `
        <tr>
            <td class="title-cell" title="${esc(p.title)}">${esc(p.title)}</td>
            <td>${(p.authors || []).slice(0, 3).join(', ')}</td>
            <td>${p.year || '-'}</td>
            <td>${(p.tags || []).join(', ')}</td>
            <td>
                <button class="action-btn dl" onclick="downloadOriginal('${p.id}')">PDF</button> <button class="action-btn dl" onclick="downloadMarkdownZip('${p.id}')">ZIP</button> <button class="action-btn view" onclick="viewPaper('${p.id}')">View</button>
                <button class="action-btn delete" onclick="deletePaper('${p.id}')">Del</button>
            </td>
        </tr>
    `).join('');

    const totalPages = Math.ceil(data.total / data.page_size);
    const renderPagination = (container) => {
        container.innerHTML = '';
        for (let i = 1; i <= Math.min(totalPages, 20); i++) {
            const btn = document.createElement('button');
            btn.textContent = i;
            if (i === libPage) btn.classList.add('active');
            btn.addEventListener('click', () => loadLibrary(i));
            container.appendChild(btn);
        }
    };
    renderPagination(document.getElementById('lib-pagination'));
    renderPagination(document.getElementById('lib-pagination-bottom'));
}

async function viewPaper(id) {
    const res = await fetch(`${API}/papers/${id}`);
    const paper = await res.json();
    const mdRes = await fetch(`${API}/papers/${id}/markdown`);
    const md = await mdRes.text();

    const win = window.open('', '_blank', 'width=800,height=600');
    win.document.write(`<!DOCTYPE html><html><head><title>${esc(paper.title)}</title><style>
        body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.8; }
        h1 { margin-bottom: 4px; } .meta { color: #666; font-size: 14px; margin-bottom: 24px; }
        pre { background: #f4f4f4; padding: 12px; border-radius: 6px; overflow-x: auto; white-space: pre-wrap; }
        </style></head><body>
        <h1>${esc(paper.title)}</h1>
        <div class="meta">${(paper.authors || []).join(', ')} · ${paper.year || ''}</div>
        <pre>${esc(md.substring(0, 100000))}</pre>
    </body></html>`);
}

async function deletePaper(id) {
    if (!confirm('Delete this paper and its index?')) return;
    await fetch(`${API}/papers/${id}`, { method: 'DELETE' });
    loadLibrary(libPage);
}

async function downloadOriginal(id) {
    window.open("/api/papers/" + id + "/original");
}
async function downloadMarkdownZip(id) {
    window.open("/api/papers/" + id + "/markdown-zip");
}

document.getElementById('lib-search')?.addEventListener('input', () => loadLibrary(1));
document.getElementById('lib-refresh')?.addEventListener('click', () => loadLibrary(libPage));

// ── Upload ────────────────────────────────────────────────
document.getElementById('upload-btn').addEventListener('click', () => {
    document.getElementById('file-input').click();
});

document.getElementById('file-input').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    await uploadFiles(Array.from(e.target.files));
});

document.getElementById('upload-drop').addEventListener('click', () => {
    document.getElementById('file-input').click();
});

document.getElementById('upload-drop').addEventListener('dragover', (e) => {
    e.preventDefault();
    e.currentTarget.style.borderColor = '#4c6ef5';
});
document.getElementById('upload-drop').addEventListener('dragleave', (e) => {
    e.currentTarget.style.borderColor = '';
});
document.getElementById('upload-drop').addEventListener('drop', async (e) => {
    e.preventDefault();
    e.currentTarget.style.borderColor = '';
    const file = e.dataTransfer.files[0];
    if (file) await uploadFiles(Array.from(e.target.files));
});

async function uploadFiles(files) {
    const status = document.getElementById('upload-status');
    const progress = document.getElementById('upload-progress');

    status.textContent = `Uploading ${files.length} file(s)...`;
    progress.style.display = 'block';

    const form = new FormData();
    for (const file of files) {
        form.append('files', file);
    }
    if (document.getElementById('opt-force-ocr').checked) form.append('force_ocr', 'true');
    if (document.getElementById('opt-use-llm').checked) form.append('use_llm', 'true');
    if (document.getElementById('opt-no-images').checked) form.append('disable_image_extraction', 'true');
    const pr = document.getElementById('opt-page-range').value.trim();
    if (pr) form.append('page_range', pr);

    try {
        const res = await fetch(`${API}/papers/upload`, { method: 'POST', body: form });
        const data = await res.json();
        progress.style.display = 'none';
        if (res.ok) {
            status.innerHTML = `✅ Indexed! <b>${esc(data.title)}</b> — ${data.chunks} chunks.`;
        } else {
            status.textContent = `❌ Failed: ${data.detail || 'Unknown error'}`;
        }
    } catch (err) {
        progress.style.display = 'none';
        status.textContent = `❌ Network error: ${err.message}`;
    }
}

// ── Status ────────────────────────────────────────────────
async function loadStatus() {
    const res = await fetch(`${API}/index/status`);
    const data = await res.json();
    document.getElementById('status-content').innerHTML = `
        <p><strong>Papers indexed:</strong> ${data.paper_count}</p>
        <p><strong>Qdrant collection:</strong> ${data.qdrant_collection}</p>
        <p><strong>Vectors:</strong> ${data.vector_store?.vectors_count || 0}</p>
        <p><strong>Points:</strong> ${data.vector_store?.points_count || 0}</p>
        <p><strong>Database:</strong> ${data.db_path}</p>
    `;
}

document.getElementById('rebuild-btn')?.addEventListener('click', async () => {
    if (!confirm('This will delete and recreate the entire vector index. Continue?')) return;
    const res = await fetch(`${API}/index/rebuild`, { method: 'POST' });
    const data = await res.json();
    alert(`Index rebuilt: ${data.papers_indexed} papers re-indexed.`);
    loadStatus();
});

// ── Helpers ───────────────────────────────────────────────
function esc(s) {
    if (!s) return '';
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}
