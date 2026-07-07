/* =========================================================================
   Global "loading button" behaviour.
   - Any <button> or <input type="submit"> shows a spinner + becomes disabled
     while the form is submitting or the button is being processed.
   - The "Save as Draft" / multi-action buttons restore themselves after the
     network call resolves (success or error) — no more stuck buttons.
   - Works for plain form submissions AND fetch() / async handlers: any element
     with [data-loading-text] will swap to that text while busy.
   - Includes a page-level overlay spinner for full-page navigations / heavy
     actions (add data-page-loading to a <form> or <a> to trigger it).
   ========================================================================= */

(function () {
  'use strict';

  // --- Spinner SVG (inline so no extra request) ---
  const SPINNER_SVG =
    '<svg class="lb-spinner" viewBox="0 0 24 24" width="18" height="18" ' +
    'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
    '<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" ' +
    'fill="none" stroke-linecap="round" stroke-dasharray="40 60"></circle></svg>';

  // --- Inject the spinner stylesheet once ---
  const STYLE_ID = 'loading-button-styles';
  if (!document.getElementById(STYLE_ID)) {
    const css =
      '.lb-spinner{display:inline-block;vertical-align:-3px;margin-right:8px;' +
      'animation:lb-spin 0.8s linear infinite;color:inherit}' +
      '@keyframes lb-spin{to{transform:rotate(360deg)}}' +
      '.lb-busy{position:relative !important;pointer-events:none !important;' +
      'opacity:0.75 !important;cursor:wait !important}' +
      '.lb-busy > *{visibility:hidden}' +
      '.lb-busy .lb-spinner,.lb-busy .lb-label{visibility:visible !important;' +
      'display:inline-flex;align-items:center}' +
      'body.lb-page-loading{cursor:wait}' +
      '#lb-page-overlay{position:fixed;inset:0;background:rgba(15,23,42,0.35);' +
      'display:none;align-items:center;justify-content:center;z-index:99999;' +
      'backdrop-filter:blur(2px)}' +
      '#lb-page-overlay.lb-show{display:flex}' +
      '#lb-page-overlay .lb-box{background:#fff;padding:18px 26px;border-radius:12px;' +
      'box-shadow:0 10px 30px rgba(0,0,0,0.18);display:flex;align-items:center;' +
      'gap:12px;font-family:inherit;font-weight:600;color:#0a2558}' +
      '#lb-page-overlay .lb-spinner{width:22px;height:22px}';
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = css;
    document.head.appendChild(style);
  }

  // --- Page-level overlay element ---
  let overlay = null;
  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'lb-page-overlay';
    overlay.innerHTML = '<div class="lb-box">' + SPINNER_SVG + '<span>Please wait…</span></div>';
    document.body.appendChild(overlay);
    return overlay;
  }
  function showPageOverlay() {
    ensureOverlay().classList.add('lb-show');
    document.body.classList.add('lb-page-loading');
  }
  function hidePageOverlay() {
    if (overlay) overlay.classList.remove('lb-show');
    document.body.classList.remove('lb-page-loading');
  }

  // --- Per-button busy state ---
  function busyOn(btn) {
    if (!btn || btn.dataset.lbBusy === '1') return;
    btn.dataset.lbBusy = '1';
    btn.dataset.lbPrevDisabled = btn.disabled ? '1' : '0';
    btn.disabled = true;
    btn.classList.add('lb-busy');
    if (!btn.querySelector('.lb-spinner')) {
      btn.insertAdjacentHTML('afterbegin', SPINNER_SVG);
    }
  }
  function busyOff(btn) {
    if (!btn || btn.dataset.lbBusy !== '1') return;
    btn.dataset.lbBusy = '0';
    btn.disabled = btn.dataset.lbPrevDisabled === '1';
    btn.classList.remove('lb-busy');
    const sp = btn.querySelector('.lb-spinner');
    if (sp) sp.remove();
  }

  // Public API: window.LoadingButton
  window.LoadingButton = {
    on:  busyOn,
    off: busyOff,
    pageOn:  showPageOverlay,
    pageOff: hidePageOverlay,
    // fetch() helper that automatically spins the calling button and unwraps
    // the JSON response, restoring the button on success OR error.
    //   const data = await LoadingButton.fetch(btn, '/api/login', {method:'POST', body:...});
    //   if (data.ok) ...
    fetch: async function (btn, url, options) {
      busyOn(btn);
      try {
        const r = await fetch(url, options);
        let data = null;
        try { data = await r.json(); } catch (_) { data = { ok: false, error: 'Server returned an invalid response (HTTP ' + r.status + ').' }; }
        if (!r.ok && (!data || !data.error)) {
          data = data || {};
          data.ok = false;
          data.error = data.error || ('Request failed (HTTP ' + r.status + ').');
        }
        return data;
      } catch (e) {
        return { ok: false, error: 'Network error: ' + (e && e.message ? e.message : 'unreachable') };
      } finally {
        busyOff(btn);
      }
    },
  };

  // ---------------------------------------------------------------------
  // AUTO-HOOK: forms
  // Mark their submit button busy on submit, and on any form with
  // data-page-loading also show the full-page overlay.
  // ---------------------------------------------------------------------
  document.addEventListener('submit', function (e) {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    const submitter = e.submitter; // the button that triggered the submit
    if (submitter && (submitter.tagName === 'BUTTON' || submitter.type === 'submit')) {
      busyOn(submitter);
    } else {
      // No submitter (Enter key on input) — find the primary submit button
      const primary = form.querySelector('button[type="submit"], input[type="submit"]');
      busyOn(primary);
    }
    if (form.hasAttribute('data-page-loading')) showPageOverlay();
  }, true);

  // Safety net: when the page finally finishes loading (e.g. coming back from
  // a redirect) re-enable any button that might still be marked busy.
  window.addEventListener('pageshow', function () {
    document.querySelectorAll('[data-lb-busy="1"]').forEach(busyOff);
    hidePageOverlay();
  });

  // ---------------------------------------------------------------------
  // AUTO-HOOK: any element with data-loading-text="..." swaps to that text
  // for the duration of the click handler. Use this on JS-bound buttons
  // that do fetch() work and call LoadingButton.off(btn) when done.
  // ---------------------------------------------------------------------
  document.addEventListener('click', function (e) {
    const el = e.target.closest('[data-loading-text]');
    if (!el) return;
    if (el.dataset.lbBusy === '1') { e.preventDefault(); return; }
    if (!el.dataset.lbOrigText) el.dataset.lbOrigText = el.textContent.trim();
    busyOn(el);
    el.innerHTML = SPINNER_SVG + '<span class="lb-label">' + el.dataset.loadingText + '</span>';
    // Auto-revert after 30s in case the dev forgot to call .off()
    setTimeout(function () { busyOff(el); el.textContent = el.dataset.lbOrigText; }, 30000);
  }, true);

  // ---------------------------------------------------------------------
  // AUTO-HOOK: any element with data-page-loading (e.g. heavy nav links)
  // ---------------------------------------------------------------------
  document.addEventListener('click', function (e) {
    const el = e.target.closest('[data-page-loading]');
    if (!el) return;
    showPageOverlay();
  }, true);

})();
