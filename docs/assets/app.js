/* livewallpaper4phone — 主 JS (i18n + 壁纸浏览 + 教程页) */
(async function() {
  // ========== i18n 引擎 ==========
  const i18n = { lang: 'zh', data: null };

  function detectLang() {
    const nav = (navigator.language || '').toLowerCase();
    return nav.startsWith('zh') ? 'zh' : 'en';
  }

  async function loadI18n(lang) {
    try {
      const resp = await fetch(`assets/i18n/${lang}.json`);
      i18n.data = await resp.json();
      i18n.lang = lang;
      localStorage.setItem('lw4p_lang', lang);
      return true;
    } catch(e) {
      // fallback to zh
      if (lang !== 'zh') return loadI18n('zh');
      return false;
    }
  }

  function t(key, vars) {
    let val = i18n.data ? i18n.data[key] : key;
    if (!val) return key;
    if (vars) {
      Object.keys(vars).forEach(k => {
        val = String(val).replace(`{${k}}`, vars[k]);
      });
    }
    return val;
  }

  function switchLang(lang) {
    loadI18n(lang).then(() => {
      applyI18nToDOM();
      if (isTutorialsPage) renderTutorials();
      else applyFilters();
    });
  }

  // ========== 页面检测 ==========
  const isTutorialsPage = document.body.querySelector('.tutorial-page');
  const DATA_URL = 'assets/data/wallpapers.json';

  // ========== DOM 引用 ==========
  const grid = document.getElementById('grid');
  const loading = document.getElementById('loading');
  const stats = document.getElementById('stats');
  const resultCount = document.getElementById('result-count');
  const modal = document.getElementById('modal');
  const modalVideo = document.getElementById('modal-video');
  const modalBody = document.getElementById('modal-body');
  const searchInput = document.getElementById('search');
  const headerNav = document.querySelector('header nav');

  // ========== 语言切换按钮 ==========
  function addLangSwitcher() {
    const header = document.querySelector('header');
    if (!header) return;
    const switcher = document.createElement('div');
    switcher.className = 'lang-switcher';
    switcher.innerHTML = `
      <button class="lang-btn ${i18n.lang === 'zh' ? 'active' : ''}" data-lang="zh">中文</button>
      <button class="lang-btn ${i18n.lang === 'en' ? 'active' : ''}" data-lang="en">EN</button>
    `;
    switcher.addEventListener('click', e => {
      const btn = e.target.closest('.lang-btn');
      if (!btn) return;
      const lang = btn.dataset.lang;
      if (lang === i18n.lang) return;
      switcher.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      switchLang(lang);
    });
    // Insert after h1
    const h1 = header.querySelector('h1');
    if (h1) h1.after(switcher);
  }

  // ========== DOM i18n 更新 ==========
  function applyI18nToDOM() {
    // Header
    document.title = `Live Wallpaper 4 Phone — ${t('site_subtitle')}`;
    document.querySelector('html').lang = i18n.lang === 'zh' ? 'zh-CN' : 'en';

    // Nav
    if (headerNav) {
      const links = headerNav.querySelectorAll('a');
      if (links[0]) links[0].textContent = t('nav_wallpapers');
      if (links[1]) links[1].textContent = t('nav_tutorials');
    }

    if (isTutorialsPage) return;

    // Stats
    if (stats) stats.textContent = t('stats_template', { count: getPrimaries().length });

    // Filter labels
    const filterLabels = document.querySelectorAll('#filters label');
    const labels = [t('filter_ar'), t('filter_quality'), t('filter_style'), t('filter_source')];
    filterLabels.forEach((label, i) => { if (labels[i]) label.textContent = labels[i]; });

    // Filter options
    document.querySelectorAll('#filters select option[value=""]').forEach(opt => {
      opt.textContent = t('filter_all');
    });

    // Search placeholder
    if (searchInput) searchInput.placeholder = t('search_placeholder');

    // Clear button
    const clearBtn = document.getElementById('clear-all');
    if (clearBtn) clearBtn.textContent = t('clear_filters');

    // Loading
    if (loading) loading.innerHTML = `<div class="spinner"></div>${t('loading')}`;

    // Submit modal
    applySubmitI18n();
  }

  // ========== 数据加载 ==========
  let wallpapers = [];
  let filtered = [];

  if (!isTutorialsPage) {
    // 加载 i18n
    const savedLang = localStorage.getItem('lw4p_lang') || detectLang();
    await loadI18n(savedLang);
    addLangSwitcher();
    applyI18nToDOM();

    try {
      const resp = await fetch(DATA_URL);
      wallpapers = await resp.json();
      if (loading) loading.style.display = 'none';
      initFilters();
      applyFilters();
      if (stats) stats.textContent = t('stats_template', { count: getPrimaries().length });
    } catch(e) {
      if (loading) loading.innerHTML = t('load_error');
      console.error(e);
    }
  } else {
    // 教程页
    const savedLang = localStorage.getItem('lw4p_lang') || detectLang();
    await loadI18n(savedLang);
    addLangSwitcher();
    applyI18nToDOM();
    renderTutorials();
  }

  // ========== 筛选器初始化 ==========
  function getPrimaries() {
    return wallpapers.filter(w => w.is_primary);
  }

  function initFilters() {
    const primaries = getPrimaries();
    const ars = new Set, quals = new Set, styles = new Set, sources = new Set;
    primaries.forEach(w => {
      ars.add(w.aspect_ratio);
      quals.add(w.quality);
      (w.tags || []).forEach(t => styles.add(t));
      sources.add(w.source);
    });
    fillSelect(document.getElementById('filter-ar'), ars, t('filter_ar'));
    fillSelect(document.getElementById('filter-quality'), quals, t('filter_quality'));
    fillSelect(document.getElementById('filter-style'), styles, t('filter_style'));
    fillSelect(document.getElementById('filter-source'), sources, t('filter_source'));

    Object.values({
      ar: document.getElementById('filter-ar'),
      quality: document.getElementById('filter-quality'),
      style: document.getElementById('filter-style'),
      source: document.getElementById('filter-source')
    }).forEach(el => el.addEventListener('change', applyFilters));
    if (searchInput) searchInput.addEventListener('input', applyFilters);
    const clearBtn = document.getElementById('clear-all');
    if (clearBtn) clearBtn.addEventListener('click', clearFilters);
  }

  function fillSelect(sel, values, label) {
    const sorted = [...values].filter(v => v).sort();
    sorted.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    });
  }

  function clearFilters() {
    document.querySelectorAll('#filters select').forEach(el => el.value = '');
    if (searchInput) searchInput.value = '';
    applyFilters();
  }

  // ========== 筛选逻辑 ==========
  function applyFilters() {
    const ar = document.getElementById('filter-ar').value;
    const quality = document.getElementById('filter-quality').value;
    const style = document.getElementById('filter-style').value;
    const source = document.getElementById('filter-source').value;
    const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    const primaries = getPrimaries();

    filtered = primaries.filter(w => {
      if (ar && w.aspect_ratio !== ar) return false;
      if (quality && w.quality !== quality) return false;
      if (style && !(w.tags || []).includes(style)) return false;
      if (source && w.source !== source) return false;
      if (query) {
        const inTitle = (w.title || '').toLowerCase().includes(query);
        const inTags = (w.tags || []).join(' ').toLowerCase().includes(query);
        const inPrompt = (w.prompt || '').toLowerCase().includes(query);
        const inAuthor = (w.author || '').toLowerCase().includes(query);
        if (!inTitle && !inTags && !inPrompt && !inAuthor) return false;
      }
      return true;
    });
    renderGrid();
    if (resultCount) resultCount.textContent = t('result_count', { filtered: filtered.length, total: primaries.length });
  }

  // ========== 视频加载（fetch→blob，绕过 Referer 限制）==========
  const videoBlobCache = new Map(); // url -> blobUrl
  async function loadVideoBlob(url) {
    if (videoBlobCache.has(url)) return videoBlobCache.get(url);
    try {
      const resp = await fetch(url, { referrerPolicy: 'no-referrer' });
      if (!resp.ok) return null;
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      videoBlobCache.set(url, blobUrl);
      return blobUrl;
    } catch(e) { return null; }
  }

  // ========== 渲染网格 ==========
  function renderGrid() {
    if (!grid) return;
    if (filtered.length === 0) {
      grid.innerHTML = `<div class="no-results"><p>${t('no_results_title')}</p><p>${t('no_results_hint')}</p></div>`;
      return;
    }
    // 组内视频数（用于角标）
    const groupSize = {};
    filtered.forEach(w => { groupSize[w.group] = (groupSize[w.group] || 0) + 1; });

    grid.innerHTML = filtered.map((w, i) => `
      <div class="wallpaper-card" data-idx="${i}" onclick="window.openModal(${i})" data-id="${w.id}">
        <div class="video-placeholder" style="width:100%;height:100%;background:#000;position:relative;">
          ${w.thumb ? `<img class="thumb" src="${w.thumb}" alt="" loading="lazy">` : ''}
          <div class="quality-badge">${w.quality||'HD'}</div>
          ${groupSize[w.group] > 1 ? `<div class="multi-badge">▤ ${groupSize[w.group]}</div>` : ''}
          <div class="loading-icon">▶</div>
        </div>
        <div class="overlay">
          <div class="tags">
            ${(w.tags||[]).slice(0,3).map(t => `<span class="tag">${t}</span>`).join('')}
          </div>
          <div class="author">@${w.author} <span>${w.aspect_ratio}</span></div>
        </div>
      </div>
    `).join('');

    // Hover 时 fetch blob 并播放
    const cards = grid.querySelectorAll('.wallpaper-card');
    let currentHover = null;
    let prevBlobUrl = null;
    cards.forEach(card => {
      card.addEventListener('mouseenter', async () => {
        if (currentHover) return;
        currentHover = card;
        const idx = parseInt(card.dataset.idx);
        const w = filtered[idx];
        if (!w.video_url) return;
        const placeholder = card.querySelector('.video-placeholder');
        const blobUrl = await loadVideoBlob(w.video_url);
        if (!blobUrl) { card.querySelector('.loading-icon').textContent = '✗'; return; }
        // Replace placeholder with video
        const vid = document.createElement('video');
        vid.src = blobUrl;
        vid.autoplay = true;
        vid.loop = true;
        vid.muted = true;
        vid.playsInline = true;
        vid.style.cssText = 'width:100%;height:100%;object-fit:cover;position:absolute;top:0;left:0;';
        placeholder.innerHTML = '';
        placeholder.appendChild(vid);
        card.querySelector('.loading-icon')?.remove();
      });
      card.addEventListener('mouseleave', () => {
        if (currentHover === card) {
          const vid = card.querySelector('video');
          if (vid) vid.pause();
          currentHover = null;
        }
      });
    });
  }

  // ========== 详情弹窗（组内可切换视频）==========
  let modalSiblings = [];
  let modalPos = 0;

  window.openModal = async function(idx) {
    const w = filtered[idx];
    if (!w) return;
    modalSiblings = wallpapers.filter(x => x.group === w.group);
    modalPos = Math.max(0, modalSiblings.findIndex(x => x.id === w.id));
    renderModal();
    modal.style.display = 'flex';
  };

  function renderModal() {
    const w = modalSiblings[modalPos];
    if (!w) return;
    const multi = modalSiblings.length > 1;

    modalVideo.innerHTML = `
      ${multi ? `<button class="modal-nav prev" onclick="window.modalNav(-1)">‹</button>` : ''}
      <div class="modal-video-loading"><div class="spinner"></div></div>
      ${multi ? `<button class="modal-nav next" onclick="window.modalNav(1)">›</button>` : ''}
      <div class="modal-counter">${multi ? `${modalPos + 1} / ${modalSiblings.length}` : ''}</div>
    `;
    loadModalVideo(w);

    const downloadUrl = w.tweet_url || '#';
    const videoUrl = w.video_url || '';
    modalBody.innerHTML = `
      <h2>${escapeHtml(w.title || '')}</h2>
      <div class="meta">
        <span class="accent">${w.quality || 'HD'}</span>
        <span>${w.width}×${w.height}</span>
        <span>${w.aspect_ratio}</span>
        <span>${w.duration ? w.duration.toFixed(1) + 's' : ''}</span>
        <span>@${w.author}</span>
      </div>
      ${w.prompt ? `
        <div class="prompt-box">
          <div class="prompt-label">${t('modal_prompt_label')}</div>
          <code>${escapeHtml(w.prompt)}</code>
        </div>
      ` : `
        <div class="prompt-box" style="opacity:0.5">
          <div class="prompt-label">${t('modal_prompt_label')}</div>
          <code>${t('modal_prompt_missing')}</code>
        </div>
      `}
      <div class="phone-types">
        <h4>${t('modal_phone_types')}</h4>
        <div class="chips">${(w.phone_types||[t('modal_generic')]).map(p => `<span class="chip">${p}</span>`).join('')}</div>
      </div>
      <button class="download-btn" onclick="window.open('${videoUrl}', '_blank', 'noopener,noreferrer')">${t('modal_download_btn')}</button>
      <div class="download-hint">${t('modal_download_hint')}</div>
      <a class="download-btn" style="background:var(--border);margin-top:6px;font-size:12px" href="${downloadUrl}" target="_blank" rel="noopener">${t('modal_view_x')}</a>
    `;
  }

  async function loadModalVideo(w) {
    const videoUrl = w.video_url || '';
    if (!videoUrl) {
      modalVideo.innerHTML = `<div style="color:red;padding:20px;text-align:center">视频加载失败</div>`;
      return;
    }
    const blobUrl = await loadVideoBlob(videoUrl);
    // 切换后可能已不是当前应显示的视频
    if (modalSiblings[modalPos] && modalSiblings[modalPos].id !== w.id) return;
    if (blobUrl) {
      const old = modalVideo.querySelector('video');
      if (old) old.remove();
      const vid = document.createElement('video');
      vid.src = blobUrl;
      vid.autoplay = true;
      vid.loop = true;
      vid.muted = true;
      vid.playsInline = true;
      vid.controls = true;
      if (w.thumb) vid.poster = w.thumb;
      modalVideo.appendChild(vid);
      modalVideo.querySelector('.modal-video-loading')?.remove();
    } else {
      modalVideo.querySelector('.modal-video-loading')?.remove();
      const err = document.createElement('div');
      err.style.cssText = 'color:red;padding:20px;text-align:center';
      err.textContent = '视频加载失败';
      modalVideo.appendChild(err);
    }
  }

  window.modalNav = function(dir) {
    if (modalSiblings.length < 2) return;
    modalPos = (modalPos + dir + modalSiblings.length) % modalSiblings.length;
    renderModal();
  };

  window.closeModal = function(e) {
    if (e && e.target !== e.currentTarget) return;
    modal.style.display = 'none';
    modalVideo.innerHTML = '';
    modalBody.innerHTML = '';
    modalSiblings = [];
  };

  window.closeModal = function(e) {
    if (e && e.target !== e.currentTarget) return;
    modal.style.display = 'none';
    modalVideo.innerHTML = '';
  };

  document.addEventListener('keydown', e => { if (e.key === 'Escape') window.closeModal(); });

  // ========== 上报入口 ==========
  const SUBMIT_PASSWORD_SHA256 = '969c77b705da7377517482ffdb1b68fd0f5a90dfd55f282b8f65aa73733484c8';
  const SUBMIT_URL_RE = /^https?:\/\/(www\.)?(x|twitter)\.com\/[A-Za-z0-9_]{1,15}\/status\/(\d+)/;

  async function sha256Hex(s) {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
    return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
  }

  function applySubmitI18n() {
    const set = (id, key) => { const el = document.getElementById(id); if (el) el.textContent = t(key); };
    const ph = (id, key) => { const el = document.getElementById(id); if (el) el.placeholder = t(key); };
    set('submit-title', 'submit_title'); set('label-pw', 'submit_pw'); set('label-url', 'submit_url');
    set('label-note', 'submit_note'); set('submit-go', 'submit_go'); set('submit-hint', 'submit_hint');
    ph('submit-pw', 'submit_pw_ph'); ph('submit-url', 'submit_url_ph'); ph('submit-note', 'submit_note_ph');
  }

  window.openSubmit = function() {
    applySubmitI18n();
    document.getElementById('submit-error').textContent = '';
    const authed = localStorage.getItem('lw4p_submit_ok') === '1';
    document.getElementById('pw-row').style.display = authed ? 'none' : 'block';
    document.getElementById('submit-modal').style.display = 'flex';
  };

  window.closeSubmit = function(e) {
    if (e && e.target !== e.currentTarget) return;
    document.getElementById('submit-modal').style.display = 'none';
  };

  async function doSubmit() {
    const err = document.getElementById('submit-error');
    err.textContent = '';
    const pwEl = document.getElementById('submit-pw');
    if (localStorage.getItem('lw4p_submit_ok') !== '1') {
      if (!pwEl.value) { err.textContent = t('submit_err_pw'); return; }
      const hex = await sha256Hex(pwEl.value);
      if (hex !== SUBMIT_PASSWORD_SHA256) { err.textContent = t('submit_err_pw'); return; }
      localStorage.setItem('lw4p_submit_ok', '1');
      document.getElementById('pw-row').style.display = 'none';
    }
    const url = document.getElementById('submit-url').value.trim();
    const m = url.match(SUBMIT_URL_RE);
    if (!m) { err.textContent = t('submit_err_url'); return; }
    const note = document.getElementById('submit-note').value.trim();
    const title = `[壁纸上报] status_${m[3]}`;
    const body = `链接: ${url}\n备注: ${note || '-'}\n时间: ${new Date().toISOString()}\n来源: ${location.href}\n`;
    window.open(
      `https://github.com/t-bites/livewallpaper4phone/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`,
      '_blank', 'noopener'
    );
    window.closeSubmit();
  }

  const navSubmit = document.getElementById('nav-submit');
  if (navSubmit) navSubmit.addEventListener('click', e => { e.preventDefault(); window.openSubmit(); });
  const submitGo = document.getElementById('submit-go');
  if (submitGo) submitGo.addEventListener('click', doSubmit);

  // ========== 教程页渲染 ==========
  function renderTutorials() {
    const container = document.querySelector('.tutorial-page');
    if (!container) return;

    container.innerHTML = `
      <a href="index.html" class="back-link">${t('tutorial_back')}</a>
      <h1>${t('tutorial_title')}</h1>
      <div class="tip">${t('tutorial_general_tip')}</div>

      <h2>${t('tutorial_iphone')}</h2>

      <h3>${t('tutorial_ios18')}</h3>
      <ol>${t('tutorial_ios18_steps').map(s => `<li>${s}</li>`).join('')}</ol>

      <h3>${t('tutorial_ios16')}</h3>
      <ol>${t('tutorial_ios16_steps').map(s => `<li>${s}</li>`).join('')}</ol>

      <div class="app-card">
        <h4>${t('tutorial_app_intolive')}</h4>
        <p>${t('tutorial_app_intolive_desc')}</p>
      </div>
      <div class="app-card">
        <h4>${t('tutorial_app_wallpaper_engine')}</h4>
        <p>${t('tutorial_app_wallpaper_engine_desc')}</p>
      </div>

      <hr>
      <h2>${t('tutorial_android')}</h2>

      <h3>${t('tutorial_android_generic')}</h3>
      <ol>${t('tutorial_android_steps').map(s => `<li>${s}</li>`).join('')}</ol>

      <h3>${t('tutorial_samsung')}</h3>
      <ol>${t('tutorial_samsung_steps').map(s => `<li>${s}</li>`).join('')}</ol>
      <div class="tip">${t('tutorial_tip_samsung')}</div>

      <h3>${t('tutorial_huawei')}</h3>
      <ol>${t('tutorial_huawei_steps').map(s => `<li>${s}</li>`).join('')}</ol>
      <div class="tip">${t('tutorial_tip_huawei')}</div>

      <h3>${t('tutorial_xiaomi')}</h3>
      <ol>${t('tutorial_xiaomi_steps').map(s => `<li>${s}</li>`).join('')}</ol>
      <div class="tip">${t('tutorial_tip_xiaomi')}</div>

      <h3>${t('tutorial_oppo')}</h3>
      <ol>${t('tutorial_oppo_steps').map(s => `<li>${s}</li>`).join('')}</ol>

      <h3>${t('tutorial_vivo')}</h3>
      <ol>${t('tutorial_vivo_steps').map(s => `<li>${s}</li>`).join('')}</ol>

      <h3>${t('tutorial_pixel')}</h3>
      <ol>${t('tutorial_pixel_steps').map(s => `<li>${s}</li>`).join('')}</ol>

      <hr>
      <h2>${t('tutorial_faq')}</h2>
      <div class="warning">${t('tutorial_warning_ratio')}</div>
      <div class="warning">${t('tutorial_warning_sound')}</div>
      <div class="tip">${t('tutorial_tip_duration')}</div>

      <hr>
      <p style="text-align:center;color:var(--text-muted);font-size:12px;padding:20px 0">
        ${t('tutorial_footer').replace('\n', '<br>')}
      </p>
    `;
  }

  // ========== 工具 ==========
  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }
})();