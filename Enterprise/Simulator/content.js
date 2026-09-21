const sessionId = crypto.randomUUID();
const activityStatus = document.querySelector('#activity-status');
const startedAt = performance.now();
let exitRecorded = false;

function activity(eventType, aggregateType, aggregateId, payload = {}) {
  return fetch('/events/api/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    keepalive: true,
    body: JSON.stringify({
      source_service: 'content-site',
      event_type: eventType,
      aggregate_type: aggregateType,
      aggregate_id: aggregateId,
      payload: { ...payload, session_id: sessionId },
      correlation_id: sessionId,
      idempotency_key: `${sessionId}:${eventType}:${aggregateId}:${payload.occurred_at || ''}`,
      schema_version: 1,
    }),
  }).catch(() => {
    activityStatus.textContent = 'Activity service unavailable';
  });
}

function contentIdentity(element) {
  return {
    contentId: element.dataset.contentId || window.location.pathname,
    title: element.dataset.contentTitle || document.title,
  };
}

function recordPageVisit() {
  activity('PageVisit', 'content_session', sessionId, {
    path: window.location.pathname,
    title: document.title,
    referrer: document.referrer || null,
  });
}

function recordContentView(element) {
  const content = contentIdentity(element);
  activity('ContentView', 'content_page', content.contentId, {
    title: content.title,
    path: window.location.pathname,
  });
}

function recordSearch(query) {
  const normalized = query.trim();
  if (!normalized) return;
  activity('Search', 'content_session', sessionId, {
    query: normalized,
    path: window.location.pathname,
  });
}

function recordTimeOnPage() {
  if (exitRecorded) return;
  const durationSeconds = Math.max(0, Math.round((performance.now() - startedAt) / 1000));
  activity('TimeOnPage', 'content_session', sessionId, {
    path: window.location.pathname,
    duration_seconds: durationSeconds,
  });
}

function recordExit() {
  if (exitRecorded) return;
  exitRecorded = true;
  const durationSeconds = Math.max(0, Math.round((performance.now() - startedAt) / 1000));
  activity('Exit', 'content_session', sessionId, {
    path: window.location.pathname,
    duration_seconds: durationSeconds,
  });
}

recordPageVisit();

document.querySelectorAll('[data-content-id]').forEach((element) => {
  const observer = new IntersectionObserver((entries, currentObserver) => {
    if (!entries[0].isIntersecting) return;
    recordContentView(element);
    currentObserver.disconnect();
  }, { threshold: 0.45 });
  observer.observe(element);
});

document.querySelectorAll('.content-action').forEach((button) => {
  button.addEventListener('click', () => {
    const section = button.closest('[data-content-id]');
    if (!section) return;
    recordContentView(section);
    const dialog = document.querySelector('#content-dialog');
    document.querySelector('#dialog-title').textContent = section.dataset.contentTitle;
    document.querySelector('#dialog-copy').textContent = `${section.dataset.contentTitle} is part of the Northstar content library. This interaction is captured as a content view for the simulation.`;
    dialog.showModal();
  });
});

document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener('click', () => {
    const target = document.querySelector(link.getAttribute('href'));
    if (target) recordContentView(target);
  });
});

const search = document.createElement('form');
search.className = 'search';
search.innerHTML = '<label for="content-search">Search the journal</label><input id="content-search" type="search" placeholder="Try repair, design, materials"><button type="submit">Search</button>';
document.querySelector('.masthead').append(search);
search.addEventListener('submit', (event) => {
  event.preventDefault();
  recordSearch(search.querySelector('input').value);
});

document.querySelector('.dialog-close').addEventListener('click', () => document.querySelector('#content-dialog').close());
window.addEventListener('pagehide', () => {
  recordTimeOnPage();
  recordExit();
});
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') recordTimeOnPage();
});
