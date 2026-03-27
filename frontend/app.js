document.addEventListener("DOMContentLoaded", () => {
    fetchBriefing();
    fetchStatus();
    fetchSignals();
    fetchTasks();
    fetchExams();
    fetchStreak();
    fetchHistory();
});

// ── Briefing ──────────────────────────────────────────────────────────────

async function fetchBriefing() {
    const loading = document.getElementById('loading');
    const dashboard = document.getElementById('dashboard');
    const emptyState = document.getElementById('empty-state');

    try {
        const response = await fetch('/api/briefing/latest');
        const data = await response.json();

        loading.classList.add('hidden');

        if (data.error || !data.hook) {
            emptyState.classList.remove('hidden');
            return;
        }

        renderBriefing(data);
        dashboard.classList.remove('hidden');

    } catch (err) {
        console.error("Failed to load briefing:", err);
        loading.innerHTML = "<p>Network error accessing SAGE core.</p>";
    }
}

function renderBriefing(data) {
    document.getElementById('date').textContent = data.date || "Today";
    document.getElementById('signal_count').textContent = `${data.signal_count || 0} signals processed`;
    document.getElementById('hook').innerHTML = data.hook || "";
    document.getElementById('situation').innerHTML = data.situation || "";
    document.getElementById('financial').innerHTML = data.financial || "No financial alerts.";
    document.getElementById('close').innerHTML = data.close || "";

    // Show mood badge
    const existing = document.querySelector('.mood-badge');
    if (existing) existing.remove();
    if (data.mood) {
        const moodEmoji = { stressful: '🔴 stressful', busy: '🟡 busy', calm: '🟢 calm' }[data.mood] || '';
        const moodEl = document.createElement('span');
        moodEl.className = 'mood-badge';
        moodEl.textContent = moodEmoji;
        document.getElementById('signal_count').insertAdjacentElement('afterend', moodEl);
    }

    // Render action items with feedback buttons
    // LEARN: Each action item gets a signal_id stored as a data attribute.
    // When you click 👍/👎 it sends that ID to /api/feedback so the scorer
    // can learn which types of signals you actually act on.
    const actionsUl = document.getElementById('actions');
    actionsUl.innerHTML = '';

    if (data.actions) {
        const lines = data.actions.split('\n');
        lines.forEach((line, idx) => {
            const trimmed = line.trim().replace(/^[\-\*\•]\s*/, "");
            if (!trimmed) return;

            const li = document.createElement('li');
            li.className = 'action-item';

            const text = document.createElement('span');
            text.textContent = trimmed;

            const fbDiv = document.createElement('div');
            fbDiv.className = 'feedback-btns';

            // We use the index as a proxy signal_id here
            // In a full version you'd pass real signal IDs from the briefing
            const signalId = `action_${idx}_${Date.now()}`;

            fbDiv.innerHTML = `
                <button class="fb-btn" title="Useful" onclick="sendFeedback('${signalId}', true, this)">👍</button>
                <button class="fb-btn" title="Not useful" onclick="sendFeedback('${signalId}', false, this)">👎</button>
            `;

            li.appendChild(text);
            li.appendChild(fbDiv);
            actionsUl.appendChild(li);
        });
    }

    // Audio exists — just show the player directly, no need to check
    document.getElementById('audio-section').classList.remove('hidden');
}

// ── Status Bar ────────────────────────────────────────────────────────────
// LEARN: This polls /api/status and renders a small health bar at the top.
// Green dot = ok, red dot = failed. You can see at a glance if Gmail
// auth expired or voice generation broke without reading any logs.

async function fetchStatus() {
    try {
        const r = await fetch('/api/status');
        const data = await r.json();

        if (data.status === 'no_runs') return;

        const bar = document.getElementById('status-bar');
        const timeEl = document.getElementById('status-time');
        const modsEl = document.getElementById('status-modules');

        const ranAt = new Date(data.ran_at);
        timeEl.textContent = ranAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            + ' · ' + ranAt.toLocaleDateString([], { day: 'numeric', month: 'short' });

        const modules = data.modules || {};
        const dots = Object.entries(modules)
            .filter(([k]) => k !== 'signal_count')
            .map(([key, val]) => {
                const ok = val === 'ok';
                const color = ok ? '#4ade80' : '#f87171';
                const tip = ok ? key : `${key}: ${val}`;
                return `<span class="mod-dot" style="background:${color}" title="${tip}"></span><span class="mod-name">${key}</span>`;
            }).join('');

        modsEl.innerHTML = dots;
        bar.classList.remove('hidden');

    } catch (e) {
        // Status bar is non-critical, fail silently
    }
}

// ── Feedback ──────────────────────────────────────────────────────────────

async function sendFeedback(signalId, actedOn, btn) {
    try {
        await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ signal_id: signalId, acted_on: actedOn }),
        });
        // Dim the sibling button to show choice was recorded
        const parent = btn.parentElement;
        parent.querySelectorAll('.fb-btn').forEach(b => b.style.opacity = '0.3');
        btn.style.opacity = '1';
        btn.style.transform = 'scale(1.3)';
    } catch (e) {
        console.error('Feedback failed', e);
    }
}

// ── Audio Player ──────────────────────────────────────────────────────────

function toggleAudio() {
    const audio = document.getElementById('briefing-audio');
    const playIcon = document.getElementById('play-icon');
    const pauseIcon = document.getElementById('pause-icon');
    const label = document.getElementById('audio-label');

    if (audio.paused) {
        audio.play();
        playIcon.classList.add('hidden');
        pauseIcon.classList.remove('hidden');
        label.textContent = 'Pause';
    } else {
        audio.pause();
        playIcon.classList.remove('hidden');
        pauseIcon.classList.add('hidden');
        label.textContent = 'Listen to Briefing';
    }

    audio.onended = () => {
        playIcon.classList.remove('hidden');
        pauseIcon.classList.add('hidden');
        label.textContent = 'Listen to Briefing';
    };
}

// ── Streak ────────────────────────────────────────────────────────────────

async function fetchStreak() {
    try {
        const r = await fetch('/api/streak');
        const data = await r.json();
        if (data.streak_days === 0 && !data.today_done) return;

        const bar = document.getElementById('status-bar');
        if (!bar) return;

        const fire = data.streak_days >= 7 ? '🔥' : data.streak_days >= 3 ? '⚡' : '✦';
        const label = document.createElement('span');
        label.className = 'streak-badge';
        label.textContent = `${fire} ${data.streak_days}d streak`;
        bar.appendChild(label);
    } catch (e) { }
}

// ── Exam Countdown ────────────────────────────────────────────────────────
// LEARN: We fetch exam data from /api/exams and render a row of cards.
// Color changes based on days left — green > 14 days, yellow 7-14, red < 7.
// This is pure frontend logic — no backend changes needed per render.

async function fetchExams() {
    try {
        const r = await fetch('/api/exams');
        const exams = await r.json();
        if (!exams.length) return;

        const container = document.getElementById('exam-countdown');
        container.innerHTML = '';

        exams.forEach(ex => {
            const d = ex.days_left;
            const color = d <= 7 ? '#f87171' : d <= 14 ? '#fbbf24' : '#4ade80';
            const urgency = d <= 3 ? '🔴' : d <= 7 ? '🟡' : '🟢';

            const card = document.createElement('div');
            card.className = 'exam-card';
            card.innerHTML = `
                <div class="exam-days" style="color:${color}">${d}</div>
                <div class="exam-info">
                    <span class="exam-subject">${ex.subject}</span>
                    <span class="exam-code">${ex.code} · ${new Date(ex.date + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</span>
                </div>
                <span class="exam-urgency">${urgency}</span>
            `;
            container.appendChild(card);
        });

        container.classList.remove('hidden');
    } catch (e) {
        console.error('Exams fetch failed', e);
    }
}

// ── Tasks ─────────────────────────────────────────────────────────────────
// LEARN: Standard CRUD pattern.
// fetchTasks() loads from DB and renders the list.
// addTask() POSTs a new one, then re-fetches.
// completeTask() PATCHes done=true, then re-fetches.
// deleteTask() DELETEs, then re-fetches.
// Always re-fetch after mutations — keeps UI in sync with DB.

async function fetchTasks() {
    try {
        const r = await fetch('/api/tasks');
        const tasks = await r.json();
        renderTasks(tasks);
    } catch (e) { console.error('Tasks fetch failed', e); }
}

function renderTasks(tasks) {
    const ul = document.getElementById('tasks-list');
    ul.innerHTML = '';

    if (!tasks.length) {
        ul.innerHTML = '<li class="task-empty">No pending tasks</li>';
        return;
    }

    const PRIORITY_COLOR = { high: '#f87171', medium: '#fbbf24', low: '#6ee7b7' };

    tasks.forEach(t => {
        const li = document.createElement('li');
        li.className = 'task-item';

        const dueLabel = t.due_date ? formatDueDate(t.due_date) : '';
        const color = PRIORITY_COLOR[t.priority] || '#888';

        li.innerHTML = `
            <div class="task-main">
                <span class="task-dot" style="background:${color}"></span>
                <span class="task-title">${t.title}</span>
            </div>
            <div class="task-meta">
                ${t.subject ? `<span class="task-subject">${t.subject}</span>` : ''}
                ${dueLabel ? `<span class="task-due">${dueLabel}</span>` : ''}
                <button class="task-done-btn" onclick="completeTask(${t.id})" title="Mark done">✓</button>
                <button class="task-del-btn"  onclick="deleteTask(${t.id})"   title="Delete">✕</button>
            </div>
        `;
        ul.appendChild(li);
    });
}

function formatDueDate(iso) {
    const due = new Date(iso + 'T00:00:00');
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const diff = Math.round((due - today) / 86400000);
    if (diff < 0) return `<span style="color:#f87171">overdue</span>`;
    if (diff === 0) return `<span style="color:#f87171">today</span>`;
    if (diff === 1) return `<span style="color:#fbbf24">tomorrow</span>`;
    return `in ${diff}d`;
}

async function addTask(e) {
    e.preventDefault();
    const payload = {
        title: document.getElementById('task-title').value.trim(),
        due_date: document.getElementById('task-due').value || null,
        priority: document.getElementById('task-priority').value,
        subject: document.getElementById('task-subject').value.trim(),
    };
    await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    // Clear form
    document.getElementById('task-title').value = '';
    document.getElementById('task-due').value = '';
    document.getElementById('task-subject').value = '';
    fetchTasks();
}

async function completeTask(id) {
    await fetch(`/api/tasks/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ done: true }),
    });
    fetchTasks();
}

async function deleteTask(id) {
    await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
    fetchTasks();
}

// ── Signals Panel ─────────────────────────────────────────────────────────
// LEARN: We call /api/signals/today which returns every signal collected
// today, sorted by urr_score. This lets you see exactly what SAGE saw
// and debug why something was included or excluded from the briefing.

const SOURCE_COLORS = {
    gmail: "#6366f1",
    weather: "#38bdf8",
    bank_sms: "#4ade80",
    academic: "#f59e0b",
    whatsapp: "#a78bfa",
};

async function fetchSignals() {
    try {
        const r = await fetch('/api/signals/today');
        const data = await r.json();
        if (!data.length) return;

        document.getElementById('signals-count').textContent = data.length;

        const list = document.getElementById('signals-list');
        list.innerHTML = '';

        data.forEach(s => {
            const color = SOURCE_COLORS[s.source] || "#888";
            const score = (s.urr_score || 0).toFixed(3);
            const time = new Date(s.received_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const preview = s.content.length > 120 ? s.content.slice(0, 120) + '…' : s.content;

            const item = document.createElement('div');
            item.className = 'signal-item';
            item.innerHTML = `
                <div class="signal-header">
                    <span class="signal-source" style="background:${color}22;color:${color}">${s.source}</span>
                    <span class="signal-score">URR ${score}</span>
                    <span class="signal-time">${time}</span>
                </div>
                <p class="signal-content">${preview}</p>
            `;
            list.appendChild(item);
        });

    } catch (e) {
        // non-critical
    }
}

function toggleSignals() {
    const list = document.getElementById('signals-list');
    const chevron = document.getElementById('signals-chevron');
    const isHidden = list.classList.contains('hidden');
    list.classList.toggle('hidden', !isHidden);
    chevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
}

// ── Briefing History ──────────────────────────────────────────────────────

async function fetchHistory() {
    try {
        const r = await fetch('/api/briefing/history');
        const data = await r.json();
        if (!data.length) return;

        const list = document.getElementById('history-list');
        list.innerHTML = '';

        data.forEach(item => {
            const div = document.createElement('div');
            div.className = 'signal-item';
            const d = new Date(item.date + 'T00:00:00');
            const label = d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
            const count = Array.isArray(item.signals) ? item.signals.length : 0;
            div.innerHTML = `
                <div class="signal-header">
                    <span class="signal-source" style="background:rgba(124,106,247,0.15);color:#7c6af7">${label}</span>
                    <span class="signal-score">${count} signals</span>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (e) { }
}

function toggleHistory() {
    const list = document.getElementById('history-list');
    const chevron = document.getElementById('history-chevron');
    const isHidden = list.classList.contains('hidden');
    list.classList.toggle('hidden', !isHidden);
    chevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
}

// ── Profile Editor ────────────────────────────────────────────────────────

async function openSettings() {
    const r = await fetch('/api/profile');
    const profile = await r.json();

    document.getElementById('p-name').value = profile.name || '';
    document.getElementById('p-role').value = profile.role || '';
    document.getElementById('p-tone').value = profile.tone || '';
    document.getElementById('p-goals').value = (profile.goals || []).join('\n');
    document.getElementById('p-exams').value = (profile.exams || [])
        .map(e => `${e.subject} | ${e.code} | ${e.date}`)
        .join('\n');

    document.getElementById('settings-modal').classList.remove('hidden');
}

function closeSettings(e) {
    if (!e || e.target.id === 'settings-modal' || e.currentTarget.tagName === 'BUTTON') {
        document.getElementById('settings-modal').classList.add('hidden');
    }
}

async function saveProfile() {
    const name = document.getElementById('p-name').value.trim();
    const role = document.getElementById('p-role').value.trim();
    const tone = document.getElementById('p-tone').value.trim();
    const goals = document.getElementById('p-goals').value.trim().split('\n').filter(Boolean);
    const exams = document.getElementById('p-exams').value.trim().split('\n')
        .filter(Boolean)
        .map(line => {
            const [subject, code, date] = line.split('|').map(s => s.trim());
            return { subject, code, date };
        })
        .filter(e => e.subject && e.code && e.date);

    // Fetch current profile to preserve class_schedule and other fields
    const r = await fetch('/api/profile');
    const current = await r.json();

    const updated = { ...current, name, role, tone, goals, exams };

    const save = await fetch('/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updated),
    });

    const statusEl = document.getElementById('profile-status');
    if (save.ok) {
        statusEl.textContent = '✓ Saved';
        setTimeout(() => {
            closeSettings();
            statusEl.textContent = '';
        }, 1000);
    } else {
        statusEl.textContent = '✗ Save failed';
    }
}

// ── Pipeline Trigger ──────────────────────────────────────────────────────

async function runPipeline() {
    const btns = document.querySelectorAll('.run-btn');
    const statuses = document.querySelectorAll('.meta-status');

    btns.forEach(b => {
        b.disabled = true;
        const icon = b.querySelector('svg');
        if (icon) icon.classList.add('spinner-rotate');
    });

    statuses.forEach(s => s.textContent = "Pipeline executing... ETA ~15s");

    try {
        const r = await fetch('/api/briefing/run', { method: 'POST' });
        const d = await r.json();
        statuses.forEach(s => s.textContent = "Running — page reloads in 15s");
        setTimeout(() => location.reload(), 15000);
    } catch (err) {
        statuses.forEach(s => s.textContent = "Error triggering pipeline.");
        btns.forEach(b => b.disabled = false);
    }
}
