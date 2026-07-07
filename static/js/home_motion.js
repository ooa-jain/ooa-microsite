/* ============================================================
   OFFICE OF ACADEMICS — motion layer
   Scroll reveal · count-up · 3D tilt · hero parallax ·
   depth orbs · scroll progress · back-to-top · animated bars.
   All gated on prefers-reduced-motion.
   ============================================================ */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Chrome: scroll progress + back-to-top ---------- */
  function buildChrome() {
    var bar = document.createElement('div');
    bar.className = 'scroll-progress';
    document.body.appendChild(bar);

    var top = document.createElement('button');
    top.className = 'to-top';
    top.setAttribute('aria-label', 'Back to top');
    top.innerHTML = '<i class="fas fa-arrow-up"></i>';
    top.onclick = function () { window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' }); };
    document.body.appendChild(top);

    function onScroll() {
      var h = document.documentElement;
      var scrolled = h.scrollTop;
      var max = h.scrollHeight - h.clientHeight;
      bar.style.width = (max > 0 ? (scrolled / max) * 100 : 0) + '%';
      top.classList.toggle('show', scrolled > 480);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ---------- Hero: depth orbs + mouse parallax ---------- */
  function buildHero() {
    var hero = document.querySelector('.hero-carousel');
    if (!hero) return;
    var orbs = document.createElement('div');
    orbs.className = 'hero-orbs';
    orbs.innerHTML = '<span class="hero-orb o1"></span><span class="hero-orb o2"></span><span class="hero-orb o3"></span>';
    hero.insertBefore(orbs, hero.firstChild);
    if (reduce) return;

    hero.addEventListener('mousemove', function (e) {
      var r = hero.getBoundingClientRect();
      var dx = (e.clientX - r.left) / r.width - 0.5;
      var dy = (e.clientY - r.top) / r.height - 0.5;
      var active = hero.querySelector('.hero-slide');
      var content = active ? active.querySelector('.hero-content') : null;
      if (content) content.style.transform = 'translate(' + (dx * 16) + 'px,' + (dy * 12) + 'px)';
      orbs.querySelectorAll('.hero-orb').forEach(function (o, i) {
        var k = (i + 1) * 9;
        o.style.transform = 'translate(' + (-dx * k) + 'px,' + (-dy * k) + 'px)';
      });
    });
    hero.addEventListener('mouseleave', function () {
      var content = hero.querySelector('.hero-slide .hero-content');
      if (content) content.style.transform = '';
    });
  }

  /* ---------- 3D tilt ---------- */
  function initTilt() {
    if (reduce) return;
    var sel = '.cat-card, .featured-event-card, .mooc-card, .stat-card, .stat-item, .course-detail-card, .key-card';
    document.addEventListener('mousemove', tiltMove, { passive: true });
    document.addEventListener('mouseover', function (e) {
      var card = e.target.closest(sel);
      if (card) card.classList.add('tilt');
    });
    document.addEventListener('mouseout', function (e) {
      var card = e.target.closest(sel);
      if (card && !card.contains(e.relatedTarget)) {
        card.style.transform = '';
      }
    });
    function tiltMove(e) {
      var card = e.target.closest(sel);
      if (!card) return;
      var r = card.getBoundingClientRect();
      var px = (e.clientX - r.left) / r.width - 0.5;
      var py = (e.clientY - r.top) / r.height - 0.5;
      var max = 7;
      card.style.transform = 'perspective(820px) rotateX(' + (-py * max) + 'deg) rotateY(' + (px * max) + 'deg) translateY(-6px) scale(1.015)';
    }
  }

  /* ---------- Scroll reveal (stagger) ---------- */
  var revealSel = [
    '.notice-card-panel', '.cat-card', '.course-detail-card', '.info-card',
    '.guide-item', '.role-card', '.step-row', '.mooc-card', '.manual-card',
    '.key-card', '.step-box', '.mini-card', '.event-item', '.featured-event-card',
    '.stat-card', '.stat-item', '.mentor-coord-card', '.chart-card', '.nep-img-grid > *',
    '.feature-hero', '.tbl-wrap', '.callout', '.fc'
  ].join(',');

  function tagReveal(root) {
    (root || document).querySelectorAll(revealSel).forEach(function (el) {
      if (!el.classList.contains('reveal') && !el.classList.contains('reveal-zoom')) el.classList.add('reveal');
    });
  }

  // Stagger-replay every reveal inside a container (used on tab/subtab switch)
  function replay(container) {
    if (!container) return;
    var items = container.querySelectorAll('.reveal, .reveal-zoom');
    items.forEach(function (el) { el.classList.remove('in'); });
    // group by parent so each grid staggers independently
    var byParent = new Map();
    items.forEach(function (el) {
      var p = el.parentElement;
      if (!byParent.has(p)) byParent.set(p, []);
      byParent.get(p).push(el);
    });
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        byParent.forEach(function (group) {
          group.forEach(function (el, i) {
            el.style.transitionDelay = Math.min(i * 60, 480) + 'ms';
            el.classList.add('in');
          });
        });
      });
    });
  }

  // IntersectionObserver for elements OUTSIDE the horizontal carousel
  function initObserver() {
    if (reduce || !('IntersectionObserver' in window)) {
      document.querySelectorAll('.reveal, .reveal-zoom').forEach(function (el) { el.classList.add('in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          var sibs = Array.prototype.filter.call(en.target.parentElement.children, function (c) {
            return c.classList && (c.classList.contains('reveal') || c.classList.contains('reveal-zoom'));
          });
          var idx = sibs.indexOf(en.target);
          en.target.style.transitionDelay = Math.min(Math.max(idx, 0) * 55, 440) + 'ms';
          en.target.classList.add('in');
          io.unobserve(en.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
    // observe only elements not inside the content carousel (those are replayed on tab switch)
    document.querySelectorAll('.reveal, .reveal-zoom').forEach(function (el) {
      if (!el.closest('.content-carousel')) io.observe(el);
    });
  }

  /* ---------- Count-up ---------- */
  function countUp(el) {
    var raw = el.dataset.countRaw || el.textContent.trim();
    el.dataset.countRaw = raw;
    var m = raw.match(/([^\d]*)([\d,]+(?:\.\d+)?)(.*)/);
    if (!m) return;
    var prefix = m[1], numStr = m[2], suffix = m[3];
    var hasComma = numStr.indexOf(',') !== -1;
    var decimals = (numStr.split('.')[1] || '').length;
    var target = parseFloat(numStr.replace(/,/g, ''));
    if (isNaN(target)) return;
    if (reduce) { el.textContent = raw; return; }
    var dur = 1300, start = null;
    function fmt(v) {
      var s = decimals ? v.toFixed(decimals) : Math.round(v).toString();
      if (hasComma) s = (+s).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
      return prefix + s + suffix;
    }
    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(target * eased);
      if (p < 1) requestAnimationFrame(step); else el.textContent = raw;
    }
    el.classList.add('count');
    requestAnimationFrame(step);
  }

  function initCounters() {
    var nums = document.querySelectorAll('.stat-item .stat-num, .stat-card .sc-num');
    nums.forEach(function (n) { n.dataset.countRaw = n.textContent.trim(); });
    if (!('IntersectionObserver' in window)) { nums.forEach(countUp); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { countUp(en.target); io.unobserve(en.target); }
      });
    }, { threshold: 0.5 });
    nums.forEach(function (n) {
      // LinkedIn stat cards live in a hidden tab: count when their tab opens (handled by replayCounters)
      if (!n.closest('.content-carousel')) io.observe(n);
    });
  }

  function replayCounters(container) {
    if (!container) return;
    container.querySelectorAll('.stat-item .stat-num, .stat-card .sc-num').forEach(countUp);
  }

  /* ---------- Animated department bars (LinkedIn table) ---------- */
  function injectBars() {
    var pills = document.querySelectorAll('.pct-pill');
    pills.forEach(function (p) {
      if (p.dataset.bar) return;
      p.dataset.bar = '1';
      var pct = parseFloat(p.textContent);
      if (isNaN(pct)) return;
      var color = getComputedStyle(p).color;
      var td = p.closest('td');
      if (!td) return;
      var track = document.createElement('div');
      track.className = 'bar-track';
      track.innerHTML = '<div class="bar-fill" style="background:' + color + '"></div>';
      td.appendChild(track);
      p.__fill = track.firstChild;
      p.__pct = Math.min(pct, 100);
    });
  }
  function animateBars(container) {
    (container || document).querySelectorAll('.pct-pill').forEach(function (p) {
      if (p.__fill) requestAnimationFrame(function () { p.__fill.style.width = p.__pct + '%'; });
    });
  }

  /* ---------- Hook tab + subtab switches to replay motion ---------- */
  function hookSwitches() {
    document.querySelectorAll('#tabBar .tab-pill').forEach(function (pill) {
      pill.addEventListener('click', function () {
        var idx = +pill.dataset.tab;
        var slide = document.querySelectorAll('#contentTrack .content-slide')[idx];
        setTimeout(function () {
          replay(slide);
          replayCounters(slide);
          injectBars();
          animateBars(slide);
        }, 60);
      });
    });
    document.querySelectorAll('.subtabs .stab').forEach(function (s) {
      s.addEventListener('click', function () {
        var panel = document.getElementById('panel-' + s.dataset.panel);
        setTimeout(function () { replay(panel); replayCounters(panel); }, 50);
      });
    });
    // platform switch (SWAYAM / LinkedIn)
    document.querySelectorAll('.plat-btn').forEach(function (b) {
      b.addEventListener('click', function () {
        setTimeout(function () {
          var li = document.getElementById('linkedinContent');
          var sw = document.getElementById('swayamContent');
          var c = (li && li.style.display !== 'none') ? li : sw;
          replay(c); replayCounters(c); injectBars(); animateBars(c);
        }, 60);
      });
    });
  }

  /* ---------- Init ---------- */
  function init() {
    buildChrome();
    buildHero();
    tagReveal(document);
    initObserver();
    initTilt();
    initCounters();
    injectBars();
    hookSwitches();
    // first active slide: reveal its content immediately
    var firstActive = document.querySelector('.content-slide.active');
    setTimeout(function () { replay(firstActive); }, 120);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
