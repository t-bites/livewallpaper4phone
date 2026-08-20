/* livewallpaper4phone — 主 JS */
(async function() {
  const DATA_URL = 'assets/data/wallpapers.json';
  let wallpapers = [];
  let filtered = [];

  // DOM 引用
  const grid = document.getElementById('grid');
  const loading = document.getElementById('loading');
  const stats = document.getElementById('stats');
  const resultCount = document.getElementById('result-count');
  const modal = document.getElementById('modal');
  const modalVideo = document.getElementById('modal-video');
  const modalBody = document.getElementById('modal-body');
  const searchInput = document.getElementById('search');

  // 筛选器引用
  const filters = {
    ar: document.getElementById('filter-ar'),
    quality: document.getElementById('filter-quality'),
    style: document.getElementById('filter-style'),
    source: document.getElementById('filter-source'),
    prompt: document.getElementById('filter-prompt'),
  };

  // ========== 数据加载 ==========
  try {
    const resp = await fetch(DATA_URL);
    wallpapers = await resp.json();
    loading.style.display = 'none';
    initFilters();
    applyFilters();
    stats.textContent = `${wallpapers.length} 个壁纸`;
  } catch(e) {
    loading.innerHTML = '❌ 加载失败，请刷新重试';
    console.error(e);
  }

  // ========== 筛选器初始化 ==========
  function initFilters() {
    // 从数据提取唯一值
    const ars = new Set, quals = new Set, styles = new Set, sources = new Set;
    wallpapers.forEach(w => {
      ars.add(w.aspect_ratio);
      quals.add(w.quality);
      (w.tags || []).forEach(t => styles.add(t));
      sources.add(w.source);
    });
    fillSelect(filters.ar, ars, '比例');
    fillSelect(filters.quality, quals, '清晰度');
    fillSelect(filters.style, styles, '风格');
    fillSelect(filters.source, sources, '来源');

    // 筛选事件
    Object.values(filters).forEach(el => el.addEventListener('change', applyFilters));
    searchInput.addEventListener('input', applyFilters);
    document.getElementById('clear-all').addEventListener('click', clearFilters);
  }

  function fillSelect(sel, values, label) {
    // 去除空值，排序
    const sorted = [...values].filter(v => v).sort();
    sorted.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    });
  }

  function clearFilters() {
    Object.values(filters).forEach(el => el.value = '');
    searchInput.value = '';
    applyFilters();
  }

  // ========== 筛选逻辑 ==========
  function applyFilters() {
    const ar = filters.ar.value;
    const quality = filters.quality.value;
    const style = filters.style.value;
    const source = filters.source.value;
    const prompt = filters.prompt.value;
    const query = searchInput.value.trim().toLowerCase();

    filtered = wallpapers.filter(w => {
      if (ar && w.aspect_ratio !== ar) return false;
      if (quality && w.quality !== quality) return false;
      if (style && !(w.tags || []).includes(style)) return false;
      if (source && w.source !== source) return false;
      if (prompt === 'yes' && !w.prompt) return false;
      if (prompt === 'no' && w.prompt) return false;
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
    resultCount.textContent = `${filtered.length} / ${wallpapers.length}`;
  }

  // ========== 渲染网格 ==========
  function renderGrid() {
    if (filtered.length === 0) {
      grid.innerHTML = '<div class="no-results"><p>📭 没有匹配的壁纸</p><p>试试调整筛选条件</p></div>';
      return;
    }
    grid.innerHTML = filtered.map((w, i) => `
      <div class="wallpaper-card" data-idx="${i}" onclick="window.openModal(${i})" data-id="${w.id}">
        <video
          src="${w.video_url || ''}"
          muted
          loop
          playsinline
          preload="metadata"
          poster=""
          loading="lazy"
          onmouseover="this.play()"
          onmouseout="this.pause()"
          onerror="this.style.display='none'"
          referrerpolicy="no-referrer"
        ></video>
        <div class="overlay">
          <div class="quality-badge">${w.quality||'HD'}</div>
          <div class="tags">
            ${(w.tags||[]).slice(0,3).map(t => `<span class="tag">${t}</span>`).join('')}
          </div>
          <div class="author">@${w.author} <span>${w.aspect_ratio}</span></div>
        </div>
      </div>
    `).join('');

    // 视口内自动播放（IntersectionObserver）
    const videos = grid.querySelectorAll('video');
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.play().catch(() => {});
        } else {
          entry.target.pause();
        }
      });
    }, { threshold: 0.3 });
    videos.forEach(v => observer.observe(v));
  }

  // ========== 详情弹窗 ==========
  window.openModal = function(idx) {
    const w = filtered[idx];
    if (!w) return;

    // 构建下载链接
    const downloadUrl = w.tweet_url || '#';
    const videoUrl = w.video_url || '';

    modalVideo.innerHTML = `<video src="${videoUrl}" autoplay loop muted playsinline controls referrerpolicy="no-referrer"></video>`;
    modalBody.innerHTML = `
      <h2>${escapeHtml(w.title || '动态壁纸')}</h2>
      <div class="meta">
        <span class="accent">${w.quality || 'HD'}</span>
        <span>${w.width}×${w.height}</span>
        <span>${w.aspect_ratio}</span>
        <span>${w.duration ? w.duration.toFixed(1) + 's' : ''}</span>
        <span>@${w.author}</span>
      </div>
      ${w.prompt ? `
        <div class="prompt-box">
          <div class="prompt-label">📝 AI 提示词</div>
          <code>${escapeHtml(w.prompt)}</code>
        </div>
      ` : `
        <div class="prompt-box" style="opacity:0.5">
          <div class="prompt-label">📝 AI 提示词</div>
          <code>暂未收录（提示词通常在评论区）</code>
        </div>
      `}
      <div class="phone-types">
        <h4>📱 推荐机型</h4>
        <div class="chips">${(w.phone_types||['通用']).map(p => `<span class="chip">${p}</span>`).join('')}</div>
      </div>
      <button class="download-btn" onclick="window.open('${videoUrl}', '_blank', 'noopener,noreferrer')" referrerpolicy="no-referrer">💾 直接下载视频</button>
      <div class="download-hint">新窗口打开视频 → 右键另存为（.mp4），保存到相册后设置为壁纸</div>
      <a class="download-btn" style="background:var(--border);margin-top:6px;font-size:12px" href="${downloadUrl}" target="_blank" rel="noopener">🔗 跳转 X 查看原帖</a>
    `;
    modal.style.display = 'flex';
  };

  window.closeModal = function(e) {
    if (e && e.target !== e.currentTarget) return;
    modal.style.display = 'none';
    modalVideo.innerHTML = '';
  };

  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

  // ========== 工具 ==========
  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }
})();