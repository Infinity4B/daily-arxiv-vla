/**
 * @file theme.js
 * @description 在日间、夜间和跟随设备三种主题偏好间循环切换。
 */
(function(){
  const themeStorageKey = 'color-theme';
  const themePreferences = ['system', 'light', 'dark'];
  const themeLabels = {
    system: '设备',
    light: '日间',
    dark: '夜间'
  };
  const systemThemeQuery = window.matchMedia('(prefers-color-scheme: dark)');

  function normalizeThemePreference(themePreference){
    return themePreferences.includes(themePreference) ? themePreference : 'system';
  }

  function readThemePreference(){
    try {
      return normalizeThemePreference(window.localStorage.getItem(themeStorageKey));
    } catch (error) {
      return 'system';
    }
  }

  function resolveTheme(themePreference){
    if(themePreference === 'system'){
      return systemThemeQuery.matches ? 'dark' : 'light';
    }
    return themePreference;
  }

  function updateThemeToggle(themePreference){
    const themeLabel = themeLabels[themePreference];
    document.querySelectorAll('[data-theme-toggle]').forEach((themeToggleEl) => {
      themeToggleEl.setAttribute('aria-label', `当前主题：${themeLabel}，点击切换主题`);
      themeToggleEl.setAttribute('title', `当前主题：${themeLabel}`);
      const themeToggleLabelEl = themeToggleEl.querySelector('[data-theme-toggle-label]');
      if(themeToggleLabelEl){
        themeToggleLabelEl.textContent = themeLabel;
      }
    });
  }

  function applyThemePreference(themePreference, shouldPersist){
    const normalizedThemePreference = normalizeThemePreference(themePreference);
    const resolvedTheme = resolveTheme(normalizedThemePreference);
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.themePreference = normalizedThemePreference;
    document.documentElement.style.colorScheme = resolvedTheme;
    updateThemeToggle(normalizedThemePreference);

    if(shouldPersist){
      try {
        window.localStorage.setItem(themeStorageKey, normalizedThemePreference);
      } catch (error) {
        console.warn('无法保存主题偏好', error);
      }
    }
  }

  function cycleThemePreference(){
    const currentThemePreference = normalizeThemePreference(
      document.documentElement.dataset.themePreference || readThemePreference()
    );
    const currentThemeIndex = themePreferences.indexOf(currentThemePreference);
    const nextThemePreference = themePreferences[(currentThemeIndex + 1) % themePreferences.length];
    applyThemePreference(nextThemePreference, true);
  }

  document.addEventListener('click', (event) => {
    const themeToggleEl = event.target.closest('[data-theme-toggle]');
    if(themeToggleEl){
      cycleThemePreference();
    }
  });

  systemThemeQuery.addEventListener('change', () => {
    if(readThemePreference() === 'system'){
      applyThemePreference('system', false);
    }
  });

  window.addEventListener('storage', (event) => {
    if(event.key === themeStorageKey){
      applyThemePreference(event.newValue || 'system', false);
    }
  });

  applyThemePreference(readThemePreference(), false);
})();

/**
 * @file analytics.js
 * @description Google Analytics 自定义事件桥接。未配置 GA4 时自动静默。
 */
(function(){
  function normalizeParams(params){
    return Object.entries(params || {}).reduce((result, [key, value]) => {
      if(value === null || value === undefined){
        return result;
      }
      result[key] = typeof value === 'string' ? value.slice(0, 100) : value;
      return result;
    }, {});
  }

  function track(name, params){
    if(typeof window.gtag !== 'function' || !name){
      return;
    }
    window.gtag('event', name, normalizeParams(params));
  }

  window.siteAnalytics = { track };
})();

/**
 * @file read-state.js
 * @description 记录读过的论文（localStorage），首页据此给卡片打上“已读”标记。
 */
(function(){
  const storageKey = 'read-papers';
  const maxEntries = 5000;
  let readIds = null;

  function getReadIds(){
    if(readIds){
      return readIds;
    }
    try {
      const stored = JSON.parse(window.localStorage.getItem(storageKey) || '[]');
      readIds = new Set(Array.isArray(stored) ? stored : []);
    } catch (error) {
      readIds = new Set();
    }
    return readIds;
  }

  function has(paperId){
    return Boolean(paperId) && getReadIds().has(paperId);
  }

  function mark(paperId){
    const ids = getReadIds();
    if(!paperId || ids.has(paperId)){
      return;
    }
    ids.add(paperId);
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(Array.from(ids).slice(-maxEntries)));
    } catch (error) {
      console.warn('无法保存已读记录', error);
    }
  }

  // 多个标签页同时打开时，任意一页写入后让其他页重新读取。
  window.addEventListener('storage', (event) => {
    if(event.key === storageKey){
      readIds = null;
    }
  });

  window.paperReadState = { has, mark };
})();

/**
 * @file media.js
 * @description 通用论文图片灯箱：支持点击放大、滚轮缩放、拖拽查看和键盘关闭。
 */
(function(){
  let lightboxEl = null;
  let imageEl = null;
  let captionEl = null;
  let scaleLabelEl = null;
  let closeButtonEl = null;
  let imageScale = 1;
  let imageOffsetX = 0;
  let imageOffsetY = 0;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragOriginX = 0;
  let dragOriginY = 0;
  let activePointerId = null;
  let returnFocusEl = null;

  function clampScale(value){
    return Math.min(4, Math.max(1, value));
  }

  function renderTransform(){
    if(!imageEl || !scaleLabelEl){
      return;
    }

    imageEl.style.transform = `translate3d(${imageOffsetX}px, ${imageOffsetY}px, 0) scale(${imageScale})`;
    imageEl.classList.toggle('is-zoomed', imageScale > 1);
    scaleLabelEl.textContent = `${Math.round(imageScale * 100)}%`;
  }

  function setScale(nextScale){
    const normalizedScale = clampScale(nextScale);
    if(normalizedScale === 1){
      imageOffsetX = 0;
      imageOffsetY = 0;
    }
    imageScale = normalizedScale;
    renderTransform();
  }

  function resetImagePosition(){
    imageScale = 1;
    imageOffsetX = 0;
    imageOffsetY = 0;
    renderTransform();
  }

  function ensureLightbox(){
    if(lightboxEl){
      return;
    }

    lightboxEl = document.createElement('div');
    lightboxEl.className = 'image-lightbox';
    lightboxEl.setAttribute('role', 'dialog');
    lightboxEl.setAttribute('aria-modal', 'true');
    lightboxEl.setAttribute('aria-label', '论文图片预览');
    lightboxEl.setAttribute('aria-hidden', 'true');
    lightboxEl.innerHTML = `
      <div class="image-lightbox-stage" data-image-lightbox-close>
        <img class="image-lightbox-image" alt="" draggable="false" />
      </div>
      <div class="image-lightbox-topbar">
        <p class="image-lightbox-caption"></p>
        <button class="image-lightbox-close" type="button" aria-label="关闭图片预览">×</button>
      </div>
      <div class="image-lightbox-controls" aria-label="图片缩放控制">
        <button type="button" data-image-zoom-out aria-label="缩小图片">−</button>
        <button class="image-lightbox-scale" type="button" data-image-zoom-reset aria-label="恢复原始缩放">100%</button>
        <button type="button" data-image-zoom-in aria-label="放大图片">+</button>
      </div>
    `;

    document.body.appendChild(lightboxEl);
    imageEl = lightboxEl.querySelector('.image-lightbox-image');
    captionEl = lightboxEl.querySelector('.image-lightbox-caption');
    scaleLabelEl = lightboxEl.querySelector('.image-lightbox-scale');
    closeButtonEl = lightboxEl.querySelector('.image-lightbox-close');
    const stageEl = lightboxEl.querySelector('.image-lightbox-stage');

    lightboxEl.addEventListener('click', (event) => {
      if(event.target.closest('[data-image-lightbox-close]') && event.target !== imageEl){
        close();
      }
    });

    closeButtonEl.addEventListener('click', close);
    lightboxEl.querySelector('[data-image-zoom-out]').addEventListener('click', () => setScale(imageScale - 0.5));
    lightboxEl.querySelector('[data-image-zoom-in]').addEventListener('click', () => setScale(imageScale + 0.5));
    lightboxEl.querySelector('[data-image-zoom-reset]').addEventListener('click', resetImagePosition);

    stageEl.addEventListener('wheel', (event) => {
      if(!lightboxEl.classList.contains('is-open')){
        return;
      }
      event.preventDefault();
      setScale(imageScale + (event.deltaY < 0 ? 0.25 : -0.25));
    }, { passive: false });

    imageEl.addEventListener('dblclick', () => {
      setScale(imageScale > 1 ? 1 : 2);
    });

    imageEl.addEventListener('pointerdown', (event) => {
      if(imageScale <= 1){
        return;
      }
      activePointerId = event.pointerId;
      dragStartX = event.clientX;
      dragStartY = event.clientY;
      dragOriginX = imageOffsetX;
      dragOriginY = imageOffsetY;
      imageEl.setPointerCapture(event.pointerId);
      imageEl.classList.add('is-dragging');
    });

    imageEl.addEventListener('pointermove', (event) => {
      if(activePointerId !== event.pointerId){
        return;
      }
      imageOffsetX = dragOriginX + event.clientX - dragStartX;
      imageOffsetY = dragOriginY + event.clientY - dragStartY;
      renderTransform();
    });

    function stopDragging(event){
      if(activePointerId !== event.pointerId){
        return;
      }
      activePointerId = null;
      imageEl.classList.remove('is-dragging');
    }

    imageEl.addEventListener('pointerup', stopDragging);
    imageEl.addEventListener('pointercancel', stopDragging);

    window.addEventListener('keydown', (event) => {
      if(!lightboxEl.classList.contains('is-open')){
        return;
      }
      if(event.key === 'Escape'){
        event.preventDefault();
        close();
      }
      if(event.key === '+' || event.key === '='){
        setScale(imageScale + 0.5);
      }
      if(event.key === '-'){
        setScale(imageScale - 0.5);
      }
    });
  }

  function open(options){
    if(!options || !options.src){
      return;
    }

    ensureLightbox();
    returnFocusEl = options.returnFocus || document.activeElement;
    // 全尺寸图在外部地址加载失败时（部分网络环境），回退到站内缩略图
    const fallbackSrc = options.fallbackSrc && options.fallbackSrc !== options.src ? options.fallbackSrc : '';
    imageEl.onerror = fallbackSrc
      ? () => {
        imageEl.onerror = null;
        imageEl.src = fallbackSrc;
      }
      : null;
    imageEl.src = options.src;
    imageEl.alt = options.alt || '论文图片放大预览';
    captionEl.textContent = options.caption || options.alt || '';
    resetImagePosition();
    lightboxEl.classList.add('is-open');
    lightboxEl.setAttribute('aria-hidden', 'false');
    document.body.classList.add('has-image-lightbox');
    window.requestAnimationFrame(() => closeButtonEl.focus());
  }

  function close(){
    if(!lightboxEl || !lightboxEl.classList.contains('is-open')){
      return;
    }

    lightboxEl.classList.remove('is-open');
    lightboxEl.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('has-image-lightbox');
    imageEl.onerror = null;
    imageEl.removeAttribute('src');
    if(returnFocusEl && typeof returnFocusEl.focus === 'function'){
      returnFocusEl.focus({ preventScroll: true });
    }
    returnFocusEl = null;
  }

  function isOpen(){
    return Boolean(lightboxEl && lightboxEl.classList.contains('is-open'));
  }

  window.PaperImageViewer = { open, close, isOpen };
})();
