// Synthetic interaction state only. No API calls, messages or real decisions.
document.addEventListener('DOMContentLoaded', () => {
  const key = 'groundiq-design-demo-v1';
  let state = {};
  try { state = JSON.parse(sessionStorage.getItem(key) || '{}'); } catch { /* file:// storage may be unavailable */ }
  const notice = document.createElement('p');
  notice.setAttribute('role', 'status');
  notice.style.cssText = 'padding:10px 14px;border:1px solid #8A93A1;border-radius:8px';
  const host = document.querySelector('main') || document.querySelector('.stage');
  if (document.querySelector('[data-action]')) host.append(notice);

  function render() {
    document.querySelectorAll('[data-evidence-state]').forEach(el => {
      el.textContent = state.evidence || 'Unconfirmed';
      el.className = `chip ${state.evidence === 'Confirmed' ? 's-ok' : 's-unk'}`;
    });
    document.querySelectorAll('[data-inspection-state]').forEach(el => {
      el.textContent = state.evidence === 'Confirmed'
        ? 'Satisfied: human-confirmed positive inspection evidence. Flag remains open until separately closed.'
        : 'Unknown: no confirmed positive inspection evidence.';
    });
    document.querySelectorAll('[data-flag-state]').forEach(el => {
      el.textContent = state.closure ? `Closed: ${state.closure.outcome} — ${state.closure.reason}`
        : state.evidence === 'Confirmed' ? 'Open — inspection precondition satisfied; awaiting human closure'
          : state.acknowledged ? 'Acknowledged — open' : 'Notified — open';
    });
    document.querySelectorAll('[data-proposal-state]').forEach(el => {
      el.textContent = state.proposal || 'Awaiting superintendent decision';
    });
    document.querySelectorAll('[data-review-history]').forEach(el => {
      el.textContent = state.review
        ? `Synthetic demo · Superintendent · ${state.review.time} · Gmail D4 09:12 · 3B / INSP-3B-ROUGH · ${state.evidence}`
        : 'D4 09:12 — recorded, unconfirmed; precondition still unknown';
    });
    document.querySelectorAll('[data-audit]').forEach(el => {
      el.textContent = (state.audit || []).join('\n') || 'No human decisions in this demo yet.';
    });
    document.querySelectorAll('[data-action="acknowledge"], [data-action="close"]').forEach(el => {
      el.disabled = Boolean(state.closure);
    });
  }

  function save(action) {
    state.audit = [...(state.audit || []), `${new Date().toISOString()} · Superintendent · dashboard demo · ${action}`];
    try { sessionStorage.setItem(key, JSON.stringify(state)); } catch {
      notice.textContent += ' Browser storage unavailable; changes apply to this page only.';
    }
    render();
  }

  document.querySelectorAll('[data-action]').forEach(button => {
    button.addEventListener('click', () => {
      const action = button.dataset.action;
      if (action === 'reset') {
        state = {};
        try { sessionStorage.removeItem(key); } catch { /* page-local fallback */ }
        notice.textContent = 'Synthetic walkthrough reset.';
        render();
        return;
      }
      if (action === 'confirm' || action === 'reject-evidence') {
        state.evidence = action === 'confirm' ? 'Confirmed' : 'Rejected';
        state.review = { time: new Date().toISOString() };
        notice.textContent = `Demo evidence ${state.evidence.toLowerCase()}. No flag was closed or proposal approved.`;
      } else if (action === 'approve' || action === 'reject-proposal') {
        state.proposal = action === 'approve' ? 'Approved' : 'Rejected';
        notice.textContent = action === 'approve'
          ? 'Demo proposal approved: schedule change and outbox notification simulated. No message sent; flag and evidence unchanged.'
          : 'Demo proposal rejected. Schedule, flag and evidence unchanged.';
      } else if (action === 'acknowledge') {
        state.acknowledged = true;
        notice.textContent = 'Demo warning acknowledged. Evidence and proposal unchanged; flag remains open.';
      } else if (action === 'close') {
        const form = button.closest('form');
        if (!form.reportValidity()) return;
        const outcome = form.querySelector('[name="fb"]:checked').value;
        const reason = form.querySelector('textarea').value.trim();
        if (!reason) { notice.textContent = 'Enter a reason before closing the flag.'; return; }
        state.closure = { outcome, reason };
        notice.textContent = 'Demo flag closed by a human with feedback. Evidence and proposal unchanged.';
      }
      save(notice.textContent);
    });
  });
  render();
});
