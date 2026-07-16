/**
 * @file app.js
 * @description 首页逻辑：加载 data.json，渲染信息流卡片与搜索。
 */
(function(){
  /** @type {Array<{date:string,title:string,link:string,arxiv_id:string,detail_path:string,cover_path:string,paper_image_path:string,paper_image_full_path:string,preview_text:string,research_unit:string,hook_text:string,key_points:string[],reading_minutes:number,section_count:number,cover_theme:Record<string,string>}>} */
  let DATA = [];

  const $ = (selector) => document.querySelector(selector);
  const statusEl = $('#status');
  const groupsEl = $('#groups');
  const searchEl = $('#search');
  const paperCountEl = $('#paper-count');
  const homeScrollKey = 'home-scroll:index';
  const paperModalQueryKey = 'paper';
  let restoredScroll = false;
  let paperModalEl = null;
  let paperModalFrameEl = null;
  let paperModalTitleEl = null;
  let paperModalOpenLinkEl = null;
  let paperModalLoaderEl = null;
  let modalReturnFocusEl = null;
  let modalCleanupTimerId = null;
  let modalSessionId = 0;

  function getPaperIdentifier(item){
    return item.arxiv_id || item.detail_path;
  }

  function getStandalonePaperURL(detailPath){
    return new URL(detailPath, window.location.href).href;
  }

  function getEmbeddedPaperURL(detailPath){
    const embeddedURL = new URL(detailPath, window.location.href);
    embeddedURL.searchParams.set('embed', '1');
    return embeddedURL.href;
  }

  function replacePaperModalFrameLocation(frameURL){
    if(!paperModalFrameEl){
      return;
    }

    try {
      if(paperModalFrameEl.contentWindow){
        paperModalFrameEl.contentWindow.location.replace(frameURL);
        return;
      }
    } catch (error) {
      console.warn('无法替换论文浮窗地址，改用 iframe src 导航', error);
    }

    paperModalFrameEl.src = frameURL;
  }

  function ensurePaperModal(){
    if(paperModalEl){
      return;
    }

    paperModalEl = document.createElement('div');
    paperModalEl.className = 'paper-modal';
    paperModalEl.setAttribute('aria-hidden', 'true');
    paperModalEl.innerHTML = `
      <div class="paper-modal-backdrop" data-paper-modal-close></div>
      <section class="paper-modal-panel" role="dialog" aria-modal="true" aria-labelledby="paper-modal-title">
        <header class="paper-modal-toolbar">
          <div class="paper-modal-heading">
            <span class="paper-modal-kicker">论文阅读</span>
            <span id="paper-modal-title" class="paper-modal-title"></span>
          </div>
          <div class="paper-modal-actions">
            <a class="paper-modal-open-link" href="#" target="_blank" rel="noopener noreferrer">新页面打开 ↗</a>
            <button class="paper-modal-close" type="button" aria-label="关闭论文浮窗">×</button>
          </div>
        </header>
        <div class="paper-modal-content">
          <div class="paper-modal-loader" aria-hidden="true">
            <span class="paper-modal-spinner"></span>
            <span>正在打开论文阅读卡</span>
          </div>
          <iframe class="paper-modal-frame" title="论文详情" loading="eager"></iframe>
        </div>
      </section>
    `;

    document.body.appendChild(paperModalEl);
    paperModalFrameEl = paperModalEl.querySelector('.paper-modal-frame');
    paperModalTitleEl = paperModalEl.querySelector('.paper-modal-title');
    paperModalOpenLinkEl = paperModalEl.querySelector('.paper-modal-open-link');
    paperModalLoaderEl = paperModalEl.querySelector('.paper-modal-loader');

    paperModalEl.querySelector('[data-paper-modal-close]').addEventListener('click', requestClosePaperModal);
    paperModalEl.querySelector('.paper-modal-close').addEventListener('click', requestClosePaperModal);
    paperModalFrameEl.addEventListener('load', () => {
      connectPaperModalImageZoom();
      paperModalLoaderEl.classList.add('hidden');
      paperModalFrameEl.classList.add('is-ready');
    });
  }

  function connectPaperModalImageZoom(){
    if(!paperModalFrameEl || !window.PaperImageViewer){
      return;
    }

    let frameDocument = null;
    try {
      frameDocument = paperModalFrameEl.contentDocument;
    } catch (error) {
      console.warn('无法访问论文浮窗内容，保留嵌入页自身的图片预览逻辑', error);
      return;
    }

    if(!frameDocument){
      return;
    }

    frameDocument.querySelectorAll('.paper-figure-image').forEach((imageEl) => {
      if(imageEl.dataset.parentZoomBound === 'true'){
        return;
      }
      imageEl.dataset.parentZoomBound = 'true';

      const openImage = (event) => {
        event.preventDefault();
        event.stopPropagation();
        const figureEl = imageEl.closest('.paper-figure-card');
        const captionEl = figureEl ? figureEl.querySelector('.paper-figure-caption') : null;
        window.PaperImageViewer.open({
          src: imageEl.currentSrc || imageEl.src,
          alt: imageEl.alt || '论文图片',
          caption: captionEl ? captionEl.textContent.trim() : imageEl.alt || ''
        });
      };

      imageEl.addEventListener('click', openImage, true);
      imageEl.addEventListener('keydown', (event) => {
        if(event.key === 'Enter' || event.key === ' '){
          openImage(event);
        }
      }, true);
    });
  }

  function openPaperModal(item, options){
    if(!item){
      return;
    }

    const settings = options || {};
    ensurePaperModal();
    modalSessionId += 1;
    if(modalCleanupTimerId !== null){
      window.clearTimeout(modalCleanupTimerId);
      modalCleanupTimerId = null;
    }
    modalReturnFocusEl = settings.returnFocus || modalReturnFocusEl || document.activeElement;
    paperModalTitleEl.textContent = item.title || '论文详情';
    paperModalOpenLinkEl.href = getStandalonePaperURL(item.detail_path);
    paperModalFrameEl.title = `论文详情：${item.title || ''}`;
    paperModalFrameEl.classList.remove('is-ready');
    paperModalLoaderEl.classList.remove('hidden');
    replacePaperModalFrameLocation(getEmbeddedPaperURL(item.detail_path));
    paperModalEl.classList.add('is-open');
    paperModalEl.setAttribute('aria-hidden', 'false');
    document.body.classList.add('has-paper-modal');

    if(settings.updateHistory){
      const modalURL = new URL(window.location.href);
      const paperIdentifier = getPaperIdentifier(item);
      const currentHistoryState = window.history.state && typeof window.history.state === 'object'
        ? window.history.state
        : {};
      modalURL.searchParams.set(paperModalQueryKey, paperIdentifier);
      window.history.pushState(
        { ...currentHistoryState, paperModal: paperIdentifier },
        '',
        modalURL
      );
    }

    window.requestAnimationFrame(() => {
      paperModalEl.querySelector('.paper-modal-close').focus();
    });
  }

  function hidePaperModal(){
    if(!paperModalEl || !paperModalEl.classList.contains('is-open')){
      return;
    }

    const closingSessionId = modalSessionId;
    paperModalEl.classList.remove('is-open');
    paperModalEl.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('has-paper-modal');
    if(modalCleanupTimerId !== null){
      window.clearTimeout(modalCleanupTimerId);
    }
    modalCleanupTimerId = window.setTimeout(() => {
      modalCleanupTimerId = null;
      const modalWasNotReopened = modalSessionId === closingSessionId;
      if(modalWasNotReopened && !paperModalEl.classList.contains('is-open')){
        replacePaperModalFrameLocation('about:blank');
      }
    }, 220);

    if(modalReturnFocusEl && typeof modalReturnFocusEl.focus === 'function'){
      modalReturnFocusEl.focus({ preventScroll: true });
    }
    modalReturnFocusEl = null;
  }

  function requestClosePaperModal(){
    if(window.PaperImageViewer && window.PaperImageViewer.isOpen()){
      window.PaperImageViewer.close();
      return;
    }

    const modalURL = new URL(window.location.href);
    const paperIdentifier = modalURL.searchParams.get(paperModalQueryKey);
    const historyPaperIdentifier = window.history.state && typeof window.history.state === 'object'
      ? window.history.state.paperModal
      : null;
    const canReturnToPreviousHistoryEntry = Boolean(
      paperIdentifier && historyPaperIdentifier === paperIdentifier
    );

    hidePaperModal();

    if(canReturnToPreviousHistoryEntry){
      window.history.back();
      return;
    }

    modalURL.searchParams.delete(paperModalQueryKey);
    const replacementHistoryState = window.history.state && typeof window.history.state === 'object'
      ? { ...window.history.state }
      : null;
    if(replacementHistoryState){
      delete replacementHistoryState.paperModal;
    }
    window.history.replaceState(replacementHistoryState, '', modalURL);
  }

  function openPaperModalFromURL(){
    const paperIdentifier = new URL(window.location.href).searchParams.get(paperModalQueryKey);
    if(!paperIdentifier){
      hidePaperModal();
      return;
    }

    const item = DATA.find((candidate) => getPaperIdentifier(candidate) === paperIdentifier);
    if(item){
      openPaperModal(item, { updateHistory: false });
    }
  }

  function openPaperImage(item, imageEl){
    if(!window.PaperImageViewer){
      return;
    }

    window.PaperImageViewer.open({
      src: item.paper_image_full_path || item.paper_image_path,
      alt: item.title || imageEl.alt,
      caption: item.title || '',
      returnFocus: imageEl
    });
  }

  function updatePaperCount(visibleCount){
    if(!paperCountEl){
      return;
    }

    const hasQuery = Boolean((searchEl.value || '').trim());
    paperCountEl.textContent = hasQuery
      ? `${visibleCount} / ${DATA.length} 篇`
      : `${DATA.length} 篇已收录`;
  }

  function applyCoverTheme(el, theme){
    if(!el || !theme){
      return;
    }

    const vars = {
      from: '--cover-from',
      to: '--cover-to',
      spot: '--cover-spot',
      ink: '--cover-ink',
      muted: '--cover-muted',
      chip: '--cover-chip',
      stroke: '--cover-stroke'
    };

    Object.entries(vars).forEach(([key, cssVar]) => {
      if(theme[key]){
        el.style.setProperty(cssVar, theme[key]);
      }
    });
  }

  function clearStatus(){
    statusEl.innerHTML = '';
    statusEl.classList.add('hidden');
  }

  function renderStatus(state, title, text, action){
    statusEl.classList.remove('hidden');
    statusEl.innerHTML = '';

    const card = document.createElement('div');
    card.className = 'status-card';
    card.dataset.state = state;

    const titleEl = document.createElement('div');
    titleEl.className = 'status-title';
    titleEl.textContent = title;

    const textEl = document.createElement('div');
    textEl.className = 'status-text';
    textEl.textContent = text;

    card.appendChild(titleEl);
    card.appendChild(textEl);

    if(action){
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'status-action';
      button.textContent = action.label;
      button.addEventListener('click', action.onClick);
      card.appendChild(button);
    }

    statusEl.appendChild(card);
  }

  function buildSearchText(item){
    return [
      item.title || '',
      item.preview_text || '',
      item.research_unit || '',
      item.arxiv_id || '',
      item.hook_text || '',
      ...(item.key_points || [])
    ].join(' ').toLowerCase();
  }

  function filterItems(items, query){
    const raw = (query || '').trim().toLowerCase();
    if(!raw){
      return items;
    }
    const tokens = raw.split(/\s+/).filter(Boolean);
    if(!tokens.length){
      return items;
    }
    return items.filter((item) => {
      const hay = buildSearchText(item).replace(/[-_]/g, '');
      return tokens.every((t) => hay.includes(t.replace(/[-_]/g, '')));
    });
  }

  function createFeedCard(item){
    const cardLink = document.createElement('a');
    cardLink.className = 'feed-card-link';
    cardLink.href = item.detail_path;
    cardLink.setAttribute('aria-label', `查看论文：${item.title}`);
    cardLink.setAttribute('aria-haspopup', 'dialog');
    cardLink.addEventListener('click', (event) => {
      const shouldUseNormalNavigation = event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
      if(shouldUseNormalNavigation){
        return;
      }
      event.preventDefault();
      openPaperModal(item, { updateHistory: true, returnFocus: cardLink });
    });

    const card = document.createElement('article');
    card.className = 'feed-card';

    const coverWrap = document.createElement('div');
    coverWrap.className = 'feed-card-cover';
    if(item.paper_image_path){
      const figure = document.createElement('figure');
      figure.className = 'feed-card-figure';

      const image = document.createElement('img');
      image.className = 'paper-figure-image';
      image.src = item.paper_image_path;
      image.alt = item.title || '论文首图';
      image.loading = 'lazy';
      image.dataset.zoomable = 'true';
      image.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        openPaperImage(item, image);
      });

      figure.appendChild(image);
      coverWrap.appendChild(figure);
    } else {
      const cover = document.createElement('div');
      cover.className = 'note-cover note-cover-feed note-cover-title-only';
      applyCoverTheme(cover, item.cover_theme);

      const mesh = document.createElement('div');
      mesh.className = 'note-cover-mesh';
      cover.appendChild(mesh);

      const titleShell = document.createElement('div');
      titleShell.className = 'note-cover-title-shell';

      const title = document.createElement('h3');
      title.className = 'note-cover-title';
      title.textContent = item.title;
      titleShell.appendChild(title);
      cover.appendChild(titleShell);
      coverWrap.appendChild(cover);
    }

    const cardBody = document.createElement('div');
    cardBody.className = 'feed-card-body';

    const meta = document.createElement('div');
    meta.className = 'feed-card-meta';

    if(item.research_unit){
      const org = document.createElement('span');
      org.className = 'feed-chip';
      org.textContent = item.research_unit;
      meta.appendChild(org);
    }

    if(item.arxiv_id){
      const id = document.createElement('span');
      id.className = 'feed-chip subtle';
      id.textContent = item.arxiv_id;
      meta.appendChild(id);
    }

    const bodyTitle = document.createElement('div');
    bodyTitle.className = 'feed-card-title';
    bodyTitle.textContent = item.title || '未命名论文';

    const preview = document.createElement('div');
    preview.className = 'feed-card-preview';
    preview.textContent = item.hook_text || item.preview_text || '摘要还在生成中';

    const footer = document.createElement('div');
    footer.className = 'feed-card-footer';

    const action = document.createElement('div');
    action.className = 'feed-card-action';
    action.textContent = '打开阅读卡';

    const stats = document.createElement('div');
    stats.className = 'feed-card-stats';
    stats.textContent = `${item.section_count || 0} 张卡 · ${item.reading_minutes || 1} 分钟`;

    footer.appendChild(action);
    footer.appendChild(stats);

    if(meta.childNodes.length){
      cardBody.appendChild(meta);
    }
    cardBody.appendChild(bodyTitle);
    cardBody.appendChild(preview);
    cardBody.appendChild(footer);

    card.appendChild(coverWrap);
    card.appendChild(cardBody);
    cardLink.appendChild(card);
    return cardLink;
  }

  const GROUPS_PER_BATCH = 3;
  let pendingDates = [];
  let pendingGrouped = new Map();
  let sentinelEl = null;
  let lazyObserver = null;

  function createGroupSection(date, items){
    const section = document.createElement('section');
    section.className = 'group';

    const heading = document.createElement('div');
    heading.className = 'group-heading';

    const h2 = document.createElement('h2');
    h2.textContent = date;

    const count = document.createElement('div');
    count.className = 'group-count';
    count.textContent = `${items.length} 篇`;

    const grid = document.createElement('div');
    grid.className = 'grid';

    items.forEach((item) => {
      grid.appendChild(createFeedCard(item));
    });

    heading.appendChild(h2);
    heading.appendChild(count);
    section.appendChild(heading);
    section.appendChild(grid);
    return section;
  }

  function removeSentinel(){
    if(sentinelEl && sentinelEl.parentNode){
      sentinelEl.parentNode.removeChild(sentinelEl);
    }
    sentinelEl = null;
  }

  function destroyLazyObserver(){
    if(lazyObserver){
      lazyObserver.disconnect();
      lazyObserver = null;
    }
    removeSentinel();
  }

  function loadNextBatch(){
    if(!pendingDates.length){
      removeSentinel();
      return;
    }

    const batch = pendingDates.splice(0, GROUPS_PER_BATCH);
    removeSentinel();

    batch.forEach((date) => {
      groupsEl.appendChild(createGroupSection(date, pendingGrouped.get(date)));
    });

    if(pendingDates.length){
      sentinelEl = document.createElement('div');
      sentinelEl.className = 'lazy-sentinel';
      sentinelEl.setAttribute('aria-hidden', 'true');
      groupsEl.appendChild(sentinelEl);
      if(lazyObserver){
        lazyObserver.observe(sentinelEl);
      }
    }
  }

  function renderGroups(items){
    destroyLazyObserver();
    groupsEl.innerHTML = '';

    if(!items.length){
      return;
    }

    const grouped = new Map();
    items.forEach((item) => {
      if(!grouped.has(item.date)){
        grouped.set(item.date, []);
      }
      grouped.get(item.date).push(item);
    });

    const dates = Array.from(grouped.keys()).sort((a, b) => b.localeCompare(a));

    pendingGrouped = grouped;
    pendingDates = dates.slice(GROUPS_PER_BATCH);

    dates.slice(0, GROUPS_PER_BATCH).forEach((date) => {
      groupsEl.appendChild(createGroupSection(date, grouped.get(date)));
    });

    if(pendingDates.length){
      lazyObserver = new IntersectionObserver((entries) => {
        if(entries.some((e) => e.isIntersecting)){
          loadNextBatch();
        }
      }, { rootMargin: '400px' });

      sentinelEl = document.createElement('div');
      sentinelEl.className = 'lazy-sentinel';
      sentinelEl.setAttribute('aria-hidden', 'true');
      groupsEl.appendChild(sentinelEl);
      lazyObserver.observe(sentinelEl);
    }
  }

  function sync(){
    const items = filterItems(DATA, searchEl.value);
    updatePaperCount(items.length);

    if(!DATA.length){
      renderGroups([]);
      renderStatus('empty', '还没有论文卡片', '当前还没有可展示的数据，等抓取和摘要生成完成后，这里会自动出现。');
      return;
    }

    if(!items.length){
      renderGroups([]);
      renderStatus(
        'empty',
        '没有找到匹配卡片',
        `换个关键词试试，当前一共收录了 ${DATA.length} 篇论文。`,
        {
          label: '清空搜索',
          onClick: () => {
            searchEl.value = '';
            syncSearchURL();
            sync();
            searchEl.focus();
          }
        }
      );
      return;
    }

    clearStatus();
    renderGroups(items);
    restoreScroll();
  }

  function syncSearchURL(){
    const q = (searchEl.value || '').trim();
    const url = new URL(window.location);
    if(q){
      url.searchParams.set('q', q);
    } else {
      url.searchParams.delete('q');
    }
    window.history.replaceState(null, '', url);
  }

  searchEl.addEventListener('input', () => {
    syncSearchURL();
    sync();
  });

  function restoreScroll(){
    if(restoredScroll || window.location.hash){
      return;
    }

    try{
      const saved = window.localStorage.getItem(homeScrollKey);
      if(saved === null){
        restoredScroll = true;
        return;
      }

      const scrollY = Number(saved);
      restoredScroll = true;
      if(!Number.isFinite(scrollY) || scrollY <= 0){
        return;
      }

      while(pendingDates.length && document.documentElement.scrollHeight < scrollY + window.innerHeight){
        loadNextBatch();
      }

      window.requestAnimationFrame(() => {
        window.scrollTo(0, scrollY);
      });
    } catch (error) {
      restoredScroll = true;
      console.warn('恢复首页滚动进度失败', error);
    }
  }

  function saveScroll(){
    try{
      window.localStorage.setItem(homeScrollKey, String(window.scrollY || 0));
    } catch (error) {
      console.warn('保存首页滚动进度失败', error);
    }
  }

  let ticking = false;
  window.addEventListener('scroll', () => {
    if(ticking){
      return;
    }

    ticking = true;
    window.requestAnimationFrame(() => {
      saveScroll();
      ticking = false;
    });
  }, { passive: true });

  window.addEventListener('pagehide', saveScroll);

  window.addEventListener('popstate', openPaperModalFromURL);

  window.addEventListener('message', (event) => {
    if(event.origin !== window.location.origin || !paperModalFrameEl || event.source !== paperModalFrameEl.contentWindow){
      return;
    }

    const message = event.data || {};
    if(message.type === 'paper-modal-close'){
      requestClosePaperModal();
      return;
    }

    if(message.type === 'paper-modal-ready'){
      if(message.title){
        paperModalTitleEl.textContent = message.title;
      }
      if(message.url){
        const standaloneURL = new URL(message.url, window.location.href);
        standaloneURL.searchParams.delete('embed');
        paperModalOpenLinkEl.href = standaloneURL.href;
      }
      return;
    }

    if(message.type === 'paper-image-open' && window.PaperImageViewer){
      window.PaperImageViewer.open({
        src: message.src,
        alt: message.alt || '论文图片',
        caption: message.caption || message.alt || ''
      });
    }
  });

  window.addEventListener('keydown', (event) => {
    if(event.defaultPrevented || event.key !== 'Escape'){
      return;
    }
    if(paperModalEl && paperModalEl.classList.contains('is-open')){
      event.preventDefault();
      requestClosePaperModal();
    }
  });

  async function loadData(){
    renderStatus('loading', '正在加载论文卡片', '页面正在读取静态数据并搭建阅读流，你可以稍后直接开始搜索。');

    try{
      const response = await fetch('assets/data.json');
      if(!response.ok){
        throw new Error(`HTTP ${response.status}`);
      }

      DATA = await response.json();
      sync();
      openPaperModalFromURL();
    } catch (error) {
      console.error(error);
      renderGroups([]);
      renderStatus(
        'error',
        '论文卡片加载失败',
        '无法读取 data.json。你可以刷新页面重试，或者重新运行构建脚本。',
        { label: '重新加载', onClick: loadData }
      );
    }
  }

  const initialQuery = new URL(window.location).searchParams.get('q') || '';
  if(initialQuery){
    searchEl.value = initialQuery;
  }

  loadData();
})();