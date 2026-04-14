// State
let currentICP = {};
let companies = [];
let analyses = {};   // company_name -> analysis
let statuses = {};   // company_name -> 'pending' | 'analyzed' | 'approved' | 'rejected'
let selectedCompany = null;
let countdownInterval = null;

// DOM refs
const $ = (sel) => document.querySelector(sel);
const loading = $('#loading');
const loadingText = $('#loading-text');
const loadingCountdown = $('#loading-countdown');

// ── Navigation ──────────────────────────────────────────
function goToStep(n) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.step').forEach(s => {
        s.classList.remove('active', 'done');
    });

    const sectionMap = { 1: 'section-icp', 2: 'section-results', 3: 'section-analysis' };
    $(`#${sectionMap[n]}`).classList.add('active');

    for (let i = 1; i <= 4; i++) {
        const el = $(`#step-${i}`);
        if (i < n) el.classList.add('done');
        else if (i === n) el.classList.add('active');
    }
}

// ── Loading ─────────────────────────────────────────────
function showLoading(text) {
    loadingText.textContent = text;
    loadingCountdown.textContent = '';
    loading.classList.add('active');
}

function hideLoading() {
    loading.classList.remove('active');
    stopCountdown();
}

function startCountdown(seconds) {
    stopCountdown();
    let remaining = seconds;
    loadingCountdown.textContent = `Siguiente en ${remaining}s`;
    countdownInterval = setInterval(() => {
        remaining--;
        if (remaining <= 0) {
            stopCountdown();
        } else {
            loadingCountdown.textContent = `Siguiente en ${remaining}s`;
        }
    }, 1000);
}

function stopCountdown() {
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }
    loadingCountdown.textContent = '';
}

// ── Toast ───────────────────────────────────────────────
function showToast(message, type = 'success') {
    const toast = $('#toast');
    toast.textContent = message;
    toast.className = `toast toast-${type} show`;
    setTimeout(() => toast.classList.remove('show'), 3500);
}

// ── API helpers ─────────────────────────────────────────
async function api(url, data = null) {
    const opts = { headers: { 'Content-Type': 'application/json' } };
    if (data !== null) {
        opts.method = 'POST';
        opts.body = JSON.stringify(data);
    }
    const res = await fetch(url, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Error desconocido' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ── Step 1: Search ──────────────────────────────────────
$('#icp-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    currentICP = {
        company_name: $('#company_name').value.trim(),
        company_url: $('#company_url').value.trim(),
        target_industry: $('#target_industry').value.trim(),
        company_size: $('#company_size').value,
        region: $('#region').value.trim(),
        client_type: $('#client_type').value.trim(),
        buying_signal: $('#buying_signal').value.trim(),
    };

    showLoading('Analizando tu empresa y buscando prospectos con IA...');

    try {
        const data = await api('/api/search', currentICP);
        companies = data.companies;
        companies.forEach(c => { statuses[c.name] = 'pending'; });
        analyses = {};
        renderResults();
        goToStep(2);
    } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
    } finally {
        hideLoading();
    }
});

// ── Step 2: Results ─────────────────────────────────────
function renderResults() {
    $('#results-count').textContent = `${companies.length} empresas encontradas`;
    $('#results-subtitle').textContent =
        `Resultados para: ${currentICP.target_industry} en ${currentICP.region}`;

    const list = $('#companies-list');
    list.innerHTML = companies.map((c, i) => `
        <div class="company-card" onclick="analyzeSingle(${i})">
            <div>
                <div class="company-name">${esc(c.name)}</div>
                <div class="company-meta">
                    <span class="meta-tag">&#127970; ${esc(c.industry)}</span>
                    <span class="meta-tag">&#128205; ${esc(c.city || 'N/A')}</span>
                    <span class="meta-tag">&#128101; ${esc(c.size_estimate || 'N/A')}</span>
                </div>
                ${c.why_matches ? `<div class="company-match">${esc(c.why_matches)}</div>` : ''}
            </div>
            <button class="btn btn-primary analyze-btn" onclick="event.stopPropagation(); analyzeSingle(${i})">
                Analizar
            </button>
        </div>
    `).join('');
}

// ── Step 3: Analyze ─────────────────────────────────────
async function analyzeSingle(index) {
    const company = companies[index];
    showLoading(`Analizando ${company.name} con IA...`);

    try {
        const data = await api(`/api/analyze/${index}`, {});
        analyses[company.name] = data.analysis;
        statuses[company.name] = 'analyzed';
        goToStep(3);
        renderSidebar();
        selectCompany(company.name);
    } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
    } finally {
        hideLoading();
    }
}

async function analyzeAll() {
    goToStep(3);
    renderSidebar();

    const DELAY = 8000;
    const pending = companies.filter(c => !analyses[c.name]);
    const total = pending.length;

    for (let i = 0; i < pending.length; i++) {
        const company = pending[i];
        const companyIndex = companies.indexOf(company);

        showLoading(`Analizando empresa ${i + 1} de ${total}: ${company.name}`);

        try {
            const data = await api(`/api/analyze/${companyIndex}`, {});
            analyses[company.name] = data.analysis;
            statuses[company.name] = 'analyzed';
            renderSidebar();
            if (i === 0) selectCompany(company.name);
        } catch (err) {
            showToast(`Error en ${company.name}: ${err.message}`, 'error');
        }

        // Countdown delay between requests
        if (i < pending.length - 1) {
            loadingText.textContent = `Analizado ${i + 1} de ${total}. Esperando para evitar rate limit...`;
            startCountdown(DELAY / 1000);
            await sleep(DELAY);
        }
    }

    hideLoading();
    showToast(`Analisis completado: ${Object.keys(analyses).length} empresas`);
}

// ── Deep analysis (FODA + benchmark on demand) ──────────
async function loadDeepAnalysis(companyName) {
    const index = companies.findIndex(c => c.name === companyName);
    const container = $('#deep-analysis-container');
    if (!container) return;

    container.innerHTML = `
        <div class="deep-loading">
            <div class="mini-spinner"></div>
            Generando analisis FODA y benchmark...
        </div>
    `;

    try {
        const data = await api(`/api/analyze-deep/${index}`, {});
        analyses[companyName] = data.analysis;
        // Re-render with full data
        selectCompany(companyName);
    } catch (err) {
        container.innerHTML = `<p style="color:var(--red);">Error: ${esc(err.message)}</p>`;
    }
}

// ── Sidebar ─────────────────────────────────────────────
function renderSidebar() {
    const list = $('#sidebar-list');
    list.innerHTML = companies.map(c => {
        const status = statuses[c.name] || 'pending';
        const badgeClass = {
            pending: 'badge-pending',
            analyzed: 'badge-analyzed',
            approved: 'badge-approved',
            rejected: 'badge-rejected',
        }[status];
        const badgeText = {
            pending: 'Pendiente',
            analyzed: 'Analizado',
            approved: 'Aprobado',
            rejected: 'Rechazado',
        }[status];
        const active = selectedCompany === c.name ? 'active' : '';

        return `
            <div class="sidebar-item ${active}" onclick="selectCompany('${escAttr(c.name)}')">
                <span class="name">${esc(c.name)}</span>
                <span class="status-badge ${badgeClass}">${badgeText}</span>
            </div>
        `;
    }).join('');
}

// ── Analysis detail ─────────────────────────────────────
function selectCompany(name) {
    selectedCompany = name;
    renderSidebar();

    const company = companies.find(c => c.name === name);
    const analysis = analyses[name];
    const detail = $('#analysis-detail');

    if (!analysis) {
        const idx = companies.indexOf(company);
        detail.innerHTML = `
            <div class="empty-state">
                <div class="icon">&#128270;</div>
                <p>Esta empresa aun no ha sido analizada</p>
                <button class="btn btn-primary" onclick="analyzeSingle(${idx})">Analizar ahora</button>
            </div>
        `;
        return;
    }

    const score = analysis.score || 0;
    const scoreClass = score >= 75 ? 'score-high' : score >= 50 ? 'score-mid' : 'score-low';
    const contacto = analysis.contacto_ideal || {};
    const status = statuses[name];
    const hasFoda = analysis.foda;

    // Deep analysis section: FODA + modelo + benchmark
    let deepSection = '';
    if (hasFoda) {
        const foda = analysis.foda;
        deepSection = `
            <div class="analysis-section">
                <h3>Analisis FODA</h3>
                <div class="foda-grid">
                    <div class="foda-box f">
                        <h4>Fortalezas</h4>
                        <ul>${(foda.fortalezas || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
                    </div>
                    <div class="foda-box o">
                        <h4>Oportunidades</h4>
                        <ul>${(foda.oportunidades || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
                    </div>
                    <div class="foda-box d">
                        <h4>Debilidades</h4>
                        <ul>${(foda.debilidades || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
                    </div>
                    <div class="foda-box a">
                        <h4>Amenazas</h4>
                        <ul>${(foda.amenazas || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
                    </div>
                </div>
            </div>

            <div class="analysis-section">
                <h3>Modelo de Negocio</h3>
                <p class="info-text">${esc(analysis.modelo_negocio || 'No disponible')}</p>
            </div>

            <div class="analysis-section">
                <h3>Benchmark</h3>
                <p class="info-text">${esc(analysis.benchmark || 'No disponible')}</p>
            </div>
        `;
    }

    detail.innerHTML = `
        <div class="analysis-header">
            <div>
                <h2>${esc(company.name)}</h2>
                <div class="company-meta" style="margin-top:0.4rem;">
                    <span class="meta-tag">&#127970; ${esc(company.industry)}</span>
                    <span class="meta-tag">&#128205; ${esc(company.city || 'N/A')}</span>
                    ${company.website ? `<span class="meta-tag">&#127760; <a href="${esc(company.website)}" target="_blank" style="color:var(--accent)">${esc(company.website)}</a></span>` : ''}
                </div>
            </div>
            <div class="score-circle ${scoreClass}">${score}</div>
        </div>

        ${analysis.resumen_ejecutivo ? `
        <div class="analysis-section">
            <h3>Resumen Ejecutivo</h3>
            <p class="info-text">${esc(analysis.resumen_ejecutivo)}</p>
        </div>
        ` : ''}

        ${analysis.score_justification ? `<p class="info-text" style="margin-bottom:1.5rem;font-style:italic;">${esc(analysis.score_justification)}</p>` : ''}

        <div class="analysis-section">
            <h3>Senales de Compra Detectadas</h3>
            <div class="tags">
                ${(analysis.senales_compra || []).map(s => `<span class="tag">${esc(s)}</span>`).join('')}
            </div>
        </div>

        <div class="analysis-section">
            <h3>Contacto Ideal</h3>
            <div class="contact-info">
                <div class="contact-row">
                    <span class="contact-label">Cargo:</span>
                    <span>${esc(contacto.cargo || 'N/A')}</span>
                </div>
                <div class="contact-row">
                    <span class="contact-label">Nombre sugerido:</span>
                    <span>${esc(contacto.nombre_sugerido || 'Por investigar')}</span>
                </div>
                <div class="contact-row">
                    <span class="contact-label">LinkedIn hint:</span>
                    <span>${esc(contacto.linkedin_hint || 'N/A')}</span>
                </div>
            </div>
        </div>

        <div class="analysis-section">
            <h3>Mensaje de Outreach</h3>
            <div class="outreach-box">${esc(analysis.mensaje_outreach || 'No disponible')}</div>
        </div>

        <div id="deep-analysis-container">
            ${hasFoda ? deepSection : `
                <button class="btn btn-outline-accent" onclick="loadDeepAnalysis('${escAttr(name)}')">
                    &#128200; Ver analisis completo (FODA + Benchmark)
                </button>
            `}
        </div>

        ${status !== 'approved' && status !== 'rejected' ? `
        <div class="approval-actions">
            <button class="btn btn-success" onclick="approveCompany('${escAttr(name)}')">
                &#10003; Aprobar y guardar en Sheets
            </button>
            <button class="btn btn-danger" onclick="rejectCompany('${escAttr(name)}')">
                &#10007; Rechazar
            </button>
        </div>
        ` : `
        <div class="approval-actions">
            <span class="status-badge ${status === 'approved' ? 'badge-approved' : 'badge-rejected'}" style="font-size:0.9rem;padding:0.4rem 1rem;">
                ${status === 'approved' ? '&#10003; Aprobado y guardado en Sheets' : '&#10007; Rechazado'}
            </span>
        </div>
        `}
    `;
}

// ── Approve / Reject ────────────────────────────────────
async function approveCompany(name) {
    showLoading('Guardando en Google Sheets...');
    try {
        const data = await api('/api/approve', { company_name: name });
        statuses[name] = 'approved';
        renderSidebar();
        selectCompany(name);
        showToast(`${name} aprobado y guardado en Sheets`);
    } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
    } finally {
        hideLoading();
    }
}

async function rejectCompany(name) {
    try {
        await api('/api/reject', { company_name: name });
        statuses[name] = 'rejected';
        renderSidebar();
        selectCompany(name);
        showToast(`${name} rechazado`, 'error');
    } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
    }
}

// ── Utils ───────────────────────────────────────────────
function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function escAttr(str) {
    return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}
