import re
with open('templates/home.html', 'r', encoding='utf-8') as f:
    content = f.read()

start_idx = content.find('/* Skeleton Loader Overlay */')
end_idx = content.find('<!-- ============ HEADER ============ -->')

new_skeleton = """/* Skeleton Loader Overlay */
#skeleton-overlay {
  position: fixed; inset: 0; background: var(--bg); z-index: 99999;
  display: flex; flex-direction: column; opacity: 1; transition: opacity 0.5s ease;
  overflow: hidden; pointer-events: none;
}
.skel-shimmer {
  background: #e2e8f0;
  background-image: linear-gradient(90deg, #e2e8f0 0px, #f1f5f9 40px, #e2e8f0 80px);
  background-size: 600px;
  animation: shimmer 1.5s infinite linear;
}
@keyframes shimmer { 0% { background-position: -600px 0; } 100% { background-position: 600px 0; } }

/* Header */
.skel-header-wrap { background: #fff; border-bottom: 1px solid var(--border); }
.skel-header {
  max-width: var(--maxw); margin: 0 auto; height: 74px;
  display: flex; align-items: center; justify-content: space-between; padding: 0 28px;
}
.skel-logo-area { display: flex; align-items: center; gap: 12px; }
.skel-logo-icon { width: 44px; height: 44px; border-radius: 50%; }
.skel-logo-text { width: 160px; height: 28px; border-radius: 4px; }

.skel-nav-area { display: none; align-items: center; gap: 8px; }
@media(min-width: 768px) { .skel-nav-area { display: flex; } }
.skel-pill { width: 110px; height: 34px; border-radius: 100px; }

.skel-user-area { display: flex; align-items: center; }
.skel-user-pill { width: 140px; height: 42px; border-radius: 100px; }

/* Ticker */
.skel-ticker { display: flex; height: 38px; }
.skel-ticker-left { width: 180px; height: 100%; background: #fcd34d; opacity: 0.5; }
.skel-ticker-right { flex: 1; height: 100%; background: #1e3a8a; opacity: 0.1; }

/* Main */
.skel-main { flex: 1; padding: 24px 28px; }
.skel-hero-container { max-width: var(--maxw); margin: 0 auto; }
.skel-hero-card { width: 100%; height: 380px; border-radius: var(--r-lg); }
</style>

</head>
<body>
<!-- ============ SKELETON LOADER ============ -->
<div id="skeleton-overlay">
  <div class="skel-header-wrap">
    <div class="skel-header">
      <div class="skel-logo-area">
        <div class="skel-logo-icon skel-shimmer"></div>
        <div class="skel-logo-text skel-shimmer"></div>
      </div>
      <div class="skel-nav-area">
        <div class="skel-pill skel-shimmer"></div>
        <div class="skel-pill skel-shimmer"></div>
        <div class="skel-pill skel-shimmer"></div>
      </div>
      <div class="skel-user-area">
        <div class="skel-user-pill skel-shimmer"></div>
      </div>
    </div>
  </div>
  
  <div class="skel-ticker">
    <div class="skel-ticker-left skel-shimmer"></div>
    <div class="skel-ticker-right skel-shimmer"></div>
  </div>

  <div class="skel-main">
    <div class="skel-hero-container">
      <div class="skel-hero-card skel-shimmer"></div>
    </div>
  </div>
</div>
<script>
  window.addEventListener('load', function() {
    const skel = document.getElementById('skeleton-overlay');
    if (skel) {
      setTimeout(() => {
        skel.style.opacity = '0';
        setTimeout(() => skel.remove(), 500);
      }, 300);
    }
  });
</script>

"""

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + new_skeleton + content[end_idx:]
    with open('templates/home.html', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Fixed home.html')
else:
    print('Could not find markers')
