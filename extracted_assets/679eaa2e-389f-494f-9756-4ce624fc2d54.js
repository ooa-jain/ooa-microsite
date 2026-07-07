/* ============================================================
   OFFICE OF ACADEMICS — interactions
   ============================================================ */
(function () {
  'use strict';

  /* ---------- Mobile nav ---------- */
  window.toggleMobileNav = function () {
    document.getElementById('mainNav').classList.toggle('show');
  };

  /* ---------- User dropdown ---------- */
  window.toggleDropdown = function (e) {
    e.stopPropagation();
    var dd = document.getElementById('userDropdown');
    var btn = document.getElementById('userBtn');
    if (!dd) return;
    dd.classList.toggle('show');
    btn.classList.toggle('open');
  };
  document.addEventListener('click', function (e) {
    var dd = document.getElementById('userDropdown');
    var btn = document.getElementById('userBtn');
    if (dd && dd.classList.contains('show') && !e.target.closest('.user-dropdown')) {
      dd.classList.remove('show');
      if (btn) btn.classList.remove('open');
    }
  });

  /* ---------- Toast ---------- */
  var toastTimer;
  window.showToast = function (msg, type) {
    type = type || 'info';
    var t = document.getElementById('toast');
    if (!t) return;
    var icon = type === 'success' ? 'fa-circle-check' : type === 'error' ? 'fa-circle-xmark' : 'fa-circle-info';
    t.className = 'toast ' + type + ' show';
    t.innerHTML = '<i class="fas ' + icon + '"></i><span>' + msg + '</span>';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('show'); }, 3200);
  };

  /* ---------- Hero carousel ---------- */
  var heroIdx = 0, heroTimer;
  function heroCount() {
    var tr = document.getElementById('heroTrack');
    return tr ? tr.children.length : 0;
  }
  function heroRender() {
    var tr = document.getElementById('heroTrack');
    if (!tr) return;
    tr.style.transform = 'translateX(-' + heroIdx * 100 + '%)';
    var dots = document.querySelectorAll('#heroDots .hero-dot');
    dots.forEach(function (d, i) { d.classList.toggle('active', i === heroIdx); });
  }
  window.heroSlide = function (dir) {
    var n = heroCount(); if (!n) return;
    heroIdx = (heroIdx + dir + n) % n;
    heroRender(); restartHero();
  };
  window.heroGoto = function (i) { heroIdx = i; heroRender(); restartHero(); };
  function restartHero() {
    clearInterval(heroTimer);
    heroTimer = setInterval(function () { window.heroSlide(1); }, 5500);
  }

  /* ---------- Top tabs (content carousel) ---------- */
  function initTabs() {
    var pills = document.querySelectorAll('#tabBar .tab-pill');
    var slides = document.querySelectorAll('#contentTrack .content-slide');
    var track = document.getElementById('contentTrack');
    pills.forEach(function (p) {
      p.addEventListener('click', function () {
        var idx = +p.dataset.tab;
        pills.forEach(function (x) { x.classList.remove('active'); });
        p.classList.add('active');
        slides.forEach(function (s, i) { s.classList.toggle('active', i === idx); });
        if (track) track.style.transform = 'translateX(-' + idx * 25 + '%)';
        if (idx === 1) renderCalendar();
        if (idx === 2 && typeof Chart !== 'undefined') buildLiChart();
      });
    });
  }

  /* ---------- Notice modal ---------- */
  window.openNoticeModal = function (text, date, urls, files, link) {
    var box = document.getElementById('noticeModal');
    if (!box) return;
    document.getElementById('nmDate').textContent = date || '';
    document.getElementById('nmDesc').textContent = text || '';
    var pdfWrap = document.getElementById('nmPdfs');
    pdfWrap.innerHTML = '';
    files = files || []; urls = urls || [];
    if (files.length) {
      document.getElementById('nmPdfSection').style.display = 'block';
      files.forEach(function (f, i) {
        var url = urls[i] || '#';
        var b = document.createElement('button');
        b.className = 'pdf-btn';
        b.innerHTML = '<i class="fas fa-file-pdf pdf-icon"></i><div class="pdf-info"><div class="pdf-name">' + f +
          '</div><div class="pdf-hint">Click to preview in viewer</div></div><span class="pdf-cta">Open</span>';
        b.onclick = function () { openPdf(url, f); };
        pdfWrap.appendChild(b);
      });
    } else {
      document.getElementById('nmPdfSection').style.display = 'none';
    }
    var linkWrap = document.getElementById('nmLink');
    if (link) {
      linkWrap.style.display = 'block';
      linkWrap.querySelector('a').href = link;
    } else { linkWrap.style.display = 'none'; }
    box.classList.add('show');
  };
  window.closeNoticeModal = function () { document.getElementById('noticeModal').classList.remove('show'); };

  /* ---------- PDF viewer ---------- */
  window.openPdf = function (url, name) {
    var ov = document.getElementById('pdfModal');
    document.getElementById('pdfTitle').textContent = name || 'Document';
    document.getElementById('pdfFrame').src = url;
    document.getElementById('pdfDownload').onclick = function () { window.open(url, '_blank'); };
    ov.classList.add('show');
  };
  window.closePdf = function () {
    document.getElementById('pdfModal').classList.remove('show');
    document.getElementById('pdfFrame').src = '';
  };

  /* ---------- Reminder modal ---------- */
  window.openReminderModal = function (id, name, date, time, venue) {
    var ov = document.getElementById('reminderModal');
    if (!ov) return;
    document.getElementById('rmTitle').textContent = name || '';
    document.getElementById('rmMeta').innerHTML =
      '<span><i class="far fa-calendar"></i>' + (date || '') + '</span>' +
      '<span><i class="far fa-clock"></i>' + (time || '') + '</span>' +
      '<span><i class="fas fa-location-dot"></i>' + (venue || '') + '</span>';
    document.getElementById('rmEventId').value = id || '';
    ov.classList.add('show');
  };
  window.closeReminderModal = function () { document.getElementById('reminderModal').classList.remove('show'); };
  window.submitReminder = function (e) {
    e.preventDefault();
    var btn = document.getElementById('rmSubmit');
    btn.classList.add('loading');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Setting reminder…';
    setTimeout(function () {
      btn.classList.remove('loading');
      btn.innerHTML = '<i class="fas fa-bell"></i> Set Reminder';
      window.closeReminderModal();
      window.showToast('Reminder set! You will be notified before the event.', 'success');
      e.target.reset();
    }, 1100);
    return false;
  };

  /* Close overlays on backdrop / Esc */
  document.addEventListener('click', function (e) {
    if (e.target.classList && e.target.classList.contains('modal-overlay')) e.target.classList.remove('show');
    if (e.target.classList && e.target.classList.contains('reminder-overlay')) e.target.classList.remove('show');
    if (e.target.id === 'pdfModal') window.closePdf();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay.show, .reminder-overlay.show').forEach(function (m) { m.classList.remove('show'); });
      var pdf = document.getElementById('pdfModal');
      if (pdf && pdf.classList.contains('show')) window.closePdf();
    }
  });

  /* ---------- Calendar ---------- */
  var calDate = new Date();
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  // Event days for current view come from window.CAL_EVENTS (set per-page), default sample set
  window.CAL_EVENTS = window.CAL_EVENTS || {};
  window.changeMonth = function (dir) { calDate.setMonth(calDate.getMonth() + dir); renderCalendar(); };
  function renderCalendar() {
    var grid = document.getElementById('calGrid');
    var label = document.getElementById('calMonthYear');
    if (!grid) return;
    var y = calDate.getFullYear(), m = calDate.getMonth();
    label.textContent = MONTHS[m] + ' ' + y;
    var first = new Date(y, m, 1).getDay();
    var days = new Date(y, m + 1, 0).getDate();
    var today = new Date();
    var key = y + '-' + (m + 1);
    var evDays = window.CAL_EVENTS[key] || [];
    var html = '';
    ['S', 'M', 'T', 'W', 'T', 'F', 'S'].forEach(function (d) { html += '<div class="cal-day-hdr">' + d + '</div>'; });
    for (var i = 0; i < first; i++) html += '<div class="cal-day empty"></div>';
    for (var d = 1; d <= days; d++) {
      var cls = 'cal-day';
      if (d === today.getDate() && m === today.getMonth() && y === today.getFullYear()) cls += ' today';
      if (evDays.indexOf(d) !== -1) cls += ' has-event';
      html += '<div class="' + cls + '" onclick="selectDay(this)">' + d + '</div>';
    }
    grid.innerHTML = html;
  }
  window.selectDay = function (el) {
    document.querySelectorAll('.cal-day.selected').forEach(function (x) { x.classList.remove('selected'); });
    el.classList.add('selected');
  };

  /* ---------- Digital Innovation: platform switch ---------- */
  window.switchPlat = function (which) {
    document.querySelectorAll('.plat-btn').forEach(function (b) { b.classList.remove('active'); });
    document.querySelector('.plat-btn.' + which).classList.add('active');
    document.getElementById('swayamContent').style.display = which === 'swayam' ? 'block' : 'none';
    document.getElementById('linkedinContent').style.display = which === 'linkedin' ? 'block' : 'none';
    if (which === 'linkedin' && typeof Chart !== 'undefined') buildLiChart();
  };

  /* ---------- Category detail ---------- */
  window.showCatDetail = function (cat) {
    document.querySelectorAll('.cat-detail').forEach(function (d) { d.classList.remove('open'); });
    var el = document.getElementById('detail-' + cat);
    if (el) { el.classList.add('open'); }
  };
  window.hideCatDetail = function (cat) {
    var el = document.getElementById('detail-' + cat);
    if (el) el.classList.remove('open');
  };

  /* ---------- Capacity sub-tabs ---------- */
  function initSubtabs() {
    var stabs = document.querySelectorAll('.subtabs .stab');
    stabs.forEach(function (s) {
      s.addEventListener('click', function () {
        var panel = s.dataset.panel;
        stabs.forEach(function (x) { x.classList.remove('active'); });
        s.classList.add('active');
        document.querySelectorAll('.cap-panel').forEach(function (p) { p.classList.remove('active'); });
        var target = document.getElementById('panel-' + panel);
        if (target) target.classList.add('active');
      });
    });
  }

  /* ---------- LinkedIn chart ---------- */
  var liChartDone = false;
  function buildLiChart() {
    if (liChartDone) return;
    var ctx = document.getElementById('liChart');
    if (!ctx || typeof Chart === 'undefined') return;
    liChartDone = true;
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Management', 'CS & IT', 'Commerce', 'Humanities', 'Animation', 'Journalism'],
        datasets: [{
          label: 'Course Completions',
          data: [39020, 8169, 7736, 652, 568, 93],
          backgroundColor: '#0f1b35',
          hoverBackgroundColor: '#e09a1f',
          borderRadius: 8,
          maxBarThickness: 64
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { backgroundColor: '#0f1b35', padding: 12, cornerRadius: 8 } },
        scales: {
          y: { beginAtZero: true, grid: { color: '#eef0f4' }, ticks: { color: '#5b6680', font: { family: 'DM Sans' } } },
          x: { grid: { display: false }, ticks: { color: '#5b6680', font: { family: 'DM Sans', weight: '600' } } }
        }
      }
    });
  }

  /* ---------- Init ---------- */
  document.addEventListener('DOMContentLoaded', function () {
    initTabs();
    initSubtabs();
    renderCalendar();
    heroRender();
    restartHero();
  });
})();
