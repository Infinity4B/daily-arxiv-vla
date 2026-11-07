/**
 * @file app.js
 * @description 首页：加载 data.json，按日期分组渲染论文条目；搜索（关键词高亮、按需加载全文索引）、
 * 已读标记，以及页内阅读抽屉（标题/导读/首图即时显示，正文从详情页 HTML 抓取并缓存）。
 */
(function(){
  const pageData = document.body.dataset;
  const DATA_URL = pageData.dataUrl || 'assets/data.json';
  const SEARCH_INDEX_URL = pageData.searchIndexUrl || 'assets/search-index.json';
  const MIN_ENTRIES_PER_BATCH = 24;
  const EAGER_IMAGE_COUNT = 4;
  const SEARCH_DEBOUNCE_MS = 120;
  const SEARCH_ANALYTICS_DELAY_MS = 800;
  const PREFETCH_DELAY_MS = 80;
  const HOME_SCROLL_KEY = 'home-scroll:index';
  const PAPER_QUERY_KEY = 'paper';
  const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const ZOOM_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  const statusEl = document.getElementById('status');
  const groupsEl = document.getElementById('groups');
  const searchEl = document.getElementById('search');
  const searchBoxEl = searchEl.closest('.masthead-search');
  const searchClearEl = document.querySelector('[data-search-clear]');
  const statsEl = document.getElementById('paper-count');
  const backToTopEl = document.querySelector('[data-back-to-top]');
  const introEl = document.querySelector('.intro');
  const readState = window.paperReadState;
  const track = (name, params) => window.siteAnalytics?.track(name, params);

  /** @type {Array<{date:string,title:string,arxiv_id:string,detail_path:string,paper_image_path:string,paper_image_full_path:string,research_unit:string,hook_text:string,reading_minutes:number,section_count:number,cover_theme?:Record<string,string>,haystack:string}>} */
  let papers = [];
  /** 当前搜索结果（阅读抽屉的上一篇/下一篇按它的顺序切换） */
  let currentResults = [];
  const paperById = new Map();
  let latestDate = '';
  let searchIndexState = 'idle';

  function getPaperId(paper){
    return paper.arxiv_id || paper.detail_path;
  }

  function createElement(tagName, className, text){
    const element = document.createElement(tagName);
    if(className){
      element.className = className;
    }
    if(text !== undefined){
      element.textContent = text;
    }
    return element;
  }

  function isEditableTarget(target){
    return Boolean(target && target.closest && target.closest('input, textarea, select, [contenteditable="true"]'));
  }

  function hasModifierKey(event){
    return event.metaKey || event.ctrlKey || event.altKey || event.shiftKey;
  }

  function describeDate(dateText){
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateText || '');
    if(!match){
      return { day: '', month: dateText || '未知日期', weekday: '', label: dateText || '未知日期' };
    }
    const [, year, month, day] = match;
    const date = new Date(Number(year), Number(month) - 1, Number(day));
    const yearPrefix = latestDate.slice(0, 4) === year ? '' : `${year}年`;
    return {
      day,
      month: `${yearPrefix}${Number(month)}月`,
      weekday: WEEKDAYS[date.getDay()],
      label: `${yearPrefix}${Number(month)}月${Number(day)}日`
    };
  }

  function applyCoverTheme(element, theme){
    Object.entries(theme || {}).forEach(([key, value]) => {
      element.style.setProperty(`--cover-${key}`, value);
    });
  }

  function createNoteCover(paper){
    const coverEl = createElement('div', 'note-cover');
    coverEl.setAttribute('aria-hidden', 'true');
    applyCoverTheme(coverEl, paper.cover_theme);
    coverEl.appendChild(createElement('p', 'note-cover-title', paper.title));
    return coverEl;
  }

  // ---------- 搜索 ----------

  function normalizeForSearch(text){
    return String(text || '').toLowerCase().replace(/[-_]/g, '');
  }

  function buildHaystack(paper, extraText){
    return normalizeForSearch([paper.title, paper.research_unit, paper.arxiv_id, paper.hook_text, extraText || ''].join(' '));
  }

  function getSearchTokens(){
    return (searchEl.value || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
  }

  function filterPapers(tokens){
    const needles = tokens.map(normalizeForSearch).filter(Boolean);
    if(!needles.length){
      return papers;
    }
    return papers.filter((paper) => needles.every((needle) => paper.haystack.includes(needle)));
  }

  function buildHighlightPattern(tokens){
    if(!tokens.length){
      return null;
    }
    const escapedTokens = tokens
      .map((token) => token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
      .sort((a, b) => b.length - a.length);
    return new RegExp(`(${escapedTokens.join('|')})`, 'gi');
  }

  function appendHighlightedText(parentEl, text, pattern){
    const value = String(text || '');
    if(!pattern){
      parentEl.textContent = value;
      return;
    }
    let lastIndex = 0;
    for(const match of value.matchAll(pattern)){
      if(match.index > lastIndex){
        parentEl.appendChild(document.createTextNode(value.slice(lastIndex, match.index)));
      }
      parentEl.appendChild(createElement('mark', '', match[0]));
      lastIndex = match.index + match[0].length;
    }
    if(lastIndex < value.length){
      parentEl.appendChild(document.createTextNode(value.slice(lastIndex)));
    }
  }

  /** 全文索引（概述与要点）体积较大，只在用户准备搜索时才加载。 */
  function ensureSearchIndex(){
    if(searchIndexState !== 'idle' || !papers.length){
      return;
    }
    searchIndexState = 'loading';
    fetch(SEARCH_INDEX_URL)
      .then((response) => {
        if(!response.ok){
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((searchIndex) => {
        papers.forEach((paper) => {
          const extraText = searchIndex[getPaperId(paper)];
          if(extraText){
            paper.haystack = buildHaystack(paper, extraText);
          }
        });
        searchIndexState = 'ready';
        if(getSearchTokens().length){
          render();
        }
      })
      .catch((error) => {
        searchIndexState = 'failed';
        console.warn('全文检索索引加载失败，仅检索标题、机构与导读', error);
        updateStats(filterPapers(getSearchTokens()).length);
      });
  }

  let searchTimerId = null;
  let searchAnalyticsTimerId = null;
  let lastTrackedSearchTerm = '';

  function updateSearchChrome(){
    searchBoxEl.classList.toggle('has-value', Boolean(searchEl.value));
  }

  function syncSearchURL(){
    const query = (searchEl.value || '').trim();
    const url = new URL(window.location.href);
    if(query){
      url.searchParams.set('q', query);
    } else {
      url.searchParams.delete('q');
    }
    window.history.replaceState(window.history.state, '', url);
  }

  function scheduleSearchAnalytics(){
    window.clearTimeout(searchAnalyticsTimerId);
    const searchTerm = (searchEl.value || '').trim();
    if(!searchTerm){
      lastTrackedSearchTerm = '';
      return;
    }
    searchAnalyticsTimerId = window.setTimeout(() => {
      const currentTerm = (searchEl.value || '').trim();
      if(!currentTerm || currentTerm === lastTrackedSearchTerm){
        return;
      }
      track('paper_search', { search_term: currentTerm, result_count: filterPapers(getSearchTokens()).length });
      lastTrackedSearchTerm = currentTerm;
    }, SEARCH_ANALYTICS_DELAY_MS);
  }

  function applySearch(){
    window.clearTimeout(searchTimerId);
    syncSearchURL();
    render();
    scheduleSearchAnalytics();
  }

  function setSearchQuery(query){
    searchEl.value = query;
    updateSearchChrome();
    applySearch();
  }

  searchEl.addEventListener('focus', ensureSearchIndex);
  searchEl.addEventListener('input', () => {
    updateSearchChrome();
    ensureSearchIndex();
    window.clearTimeout(searchTimerId);
    searchTimerId = window.setTimeout(() => {
      applySearch();
      // 刊头吸顶，结果列表就在下方；滚动过深时回到列表开头
      if(introEl && window.scrollY > introEl.offsetTop + introEl.offsetHeight){
        window.scrollTo({ top: introEl.offsetTop + introEl.offsetHeight - 8, behavior: 'instant' });
      }
    }, SEARCH_DEBOUNCE_MS);
  });

  searchClearEl?.addEventListener('click', () => {
    setSearchQuery('');
    searchEl.focus();
  });

  // ---------- 统计与状态 ----------

  function updateStats(visibleCount){
    if(!statsEl){
      return;
    }
    statsEl.replaceChildren();
    if(!papers.length){
      statsEl.textContent = '暂无论文';
      return;
    }

    const addItem = (prefix, strongText, suffix) => {
      const itemEl = createElement('span');
      if(prefix){
        itemEl.append(prefix);
      }
      itemEl.appendChild(createElement('strong', '', strongText));
      if(suffix){
        itemEl.append(suffix);
      }
      statsEl.appendChild(itemEl);
    };

    if(getSearchTokens().length){
      addItem('找到 ', String(visibleCount), ` / ${papers.length} 篇`);
      if(searchIndexState === 'loading'){
        statsEl.appendChild(createElement('span', '', '正在加载全文索引…'));
      }
      return;
    }

    const updateEl = createElement('span');
    updateEl.appendChild(createElement('span', 'live-dot'));
    updateEl.append(`更新至 ${describeDate(latestDate).label}`);
    statsEl.appendChild(updateEl);
    addItem('共收录 ', String(papers.length), ' 篇');
    statsEl.appendChild(createElement('span', 'intro-stats-extra', '每日自动抓取 · 中文精读'));
  }

  function clearStatus(){
    statusEl.replaceChildren();
    statusEl.classList.add('hidden');
  }

  function renderStatus(title, text, action){
    const cardEl = createElement('div', 'status-card');
    cardEl.append(createElement('div', 'status-title', title), createElement('div', 'status-text', text));
    if(action){
      const buttonEl = createElement('button', 'status-action', action.label);
      buttonEl.type = 'button';
      buttonEl.addEventListener('click', action.onClick);
      cardEl.appendChild(buttonEl);
    }
    statusEl.replaceChildren(cardEl);
    statusEl.classList.remove('hidden');
  }

  // ---------- 条目渲染 ----------

  function createEntryFigure(paper, eagerImage){
    const figureEl = createElement('div', 'entry-figure');
    if(!paper.paper_image_path){
      figureEl.appendChild(createNoteCover(paper));
      return figureEl;
    }

    const imageEl = createElement('img');
    imageEl.src = paper.paper_image_path;
    imageEl.alt = '';
    imageEl.decoding = 'async';
    imageEl.loading = eagerImage ? 'eager' : 'lazy';
    if(eagerImage){
      imageEl.fetchPriority = 'high';
    }

    const zoomEl = createElement('button', 'entry-zoom');
    zoomEl.type = 'button';
    zoomEl.dataset.action = 'zoom';
    zoomEl.title = '放大首图';
    zoomEl.setAttribute('aria-label', `放大查看首图：${paper.title}`);
    zoomEl.innerHTML = ZOOM_ICON;

    figureEl.append(imageEl, zoomEl);
    return figureEl;
  }

  function createEntry(paper, highlightPattern, eagerImage){
    const paperId = getPaperId(paper);
    const entryEl = createElement('article', 'entry');
    entryEl.dataset.paperId = paperId;
    if(readState?.has(paperId)){
      entryEl.classList.add('is-read');
    }

    const bodyEl = createElement('div', 'entry-body');
    const metaEl = createElement('p', 'entry-meta');
    if(paper.research_unit){
      const unitEl = createElement('span', 'entry-unit');
      unitEl.title = paper.research_unit;
      appendHighlightedText(unitEl, paper.research_unit, highlightPattern);
      metaEl.appendChild(unitEl);
    }
    if(paper.arxiv_id){
      const idEl = createElement('span', 'entry-id');
      appendHighlightedText(idEl, paper.arxiv_id, highlightPattern);
      metaEl.appendChild(idEl);
    }
    metaEl.appendChild(createElement('span', 'entry-read', '已读'));

    const titleEl = createElement('h3', 'entry-title');
    const linkEl = createElement('a', 'entry-link');
    linkEl.href = paper.detail_path;
    linkEl.setAttribute('aria-haspopup', 'dialog');
    appendHighlightedText(linkEl, paper.title || '未命名论文', highlightPattern);
    titleEl.appendChild(linkEl);

    const hookEl = createElement('p', 'entry-hook');
    appendHighlightedText(hookEl, paper.hook_text || '摘要还在生成中', highlightPattern);

    const footEl = createElement('p', 'entry-foot', `${paper.section_count || 0} 节精读 · 约 ${paper.reading_minutes || 1} 分钟`);

    bodyEl.append(metaEl, titleEl, hookEl, footEl);
    entryEl.append(bodyEl, createEntryFigure(paper, eagerImage));
    return entryEl;
  }

  function createDaySection(date, dayPapers, context){
    const { day, month, weekday } = describeDate(date);
    const sectionEl = createElement('section', 'day');
    sectionEl.setAttribute('aria-label', `${month}${Number(day) || ''}日 ${weekday}`);

    const railEl = createElement('header', 'day-rail');
    const timeEl = createElement('time');
    timeEl.dateTime = date;
    timeEl.append(createElement('span', 'day-num', day || date), createElement('span', 'day-month', `${month} · ${weekday}`));
    const metaEl = createElement('div', 'day-meta');
    metaEl.appendChild(createElement('span', '', `${dayPapers.length} 篇`));
    if(date === latestDate && !context.highlightPattern){
      metaEl.appendChild(createElement('span', 'day-latest', '最新'));
    }
    railEl.append(timeEl, metaEl);

    const listEl = createElement('ol', 'day-list');
    dayPapers.forEach((paper) => {
      const eagerImage = context.eagerImagesLeft > 0 && Boolean(paper.paper_image_path);
      if(eagerImage){
        context.eagerImagesLeft -= 1;
      }
      const itemEl = createElement('li');
      itemEl.appendChild(createEntry(paper, context.highlightPattern, eagerImage));
      listEl.appendChild(itemEl);
    });

    sectionEl.append(railEl, listEl);
    return sectionEl;
  }

  // ---------- 分批渲染（滚动到底部时追加） ----------

  let pendingGroups = [];
  let renderContext = { highlightPattern: null, eagerImagesLeft: 0 };
  let sentinelEl = null;
  const lazyObserver = 'IntersectionObserver' in window
    ? new IntersectionObserver((entries) => {
      if(entries.some((entry) => entry.isIntersecting)){
        appendNextBatch();
      }
    }, { rootMargin: '900px 0px' })
    : null;

  function removeSentinel(){
    if(sentinelEl){
      lazyObserver?.unobserve(sentinelEl);
      sentinelEl.remove();
      sentinelEl = null;
    }
  }

  function appendNextBatch(){
    removeSentinel();
    const fragment = document.createDocumentFragment();
    let entryCount = 0;
    while(pendingGroups.length && (entryCount < MIN_ENTRIES_PER_BATCH || !lazyObserver)){
      const [date, dayPapers] = pendingGroups.shift();
      fragment.appendChild(createDaySection(date, dayPapers, renderContext));
      entryCount += dayPapers.length;
    }
    groupsEl.appendChild(fragment);

    if(pendingGroups.length && lazyObserver){
      sentinelEl = createElement('div', 'lazy-sentinel');
      sentinelEl.setAttribute('aria-hidden', 'true');
      groupsEl.appendChild(sentinelEl);
      lazyObserver.observe(sentinelEl);
    }
  }

  function groupByDate(list){
    const groups = new Map();
    list.forEach((paper) => {
      if(!groups.has(paper.date)){
        groups.set(paper.date, []);
      }
      groups.get(paper.date).push(paper);
    });
    return Array.from(groups.entries()).sort((a, b) => b[0].localeCompare(a[0]));
  }

  function renderList(list, tokens){
    removeSentinel();
    groupsEl.replaceChildren();
    const groups = groupByDate(list);
    // 阅读抽屉的上一篇/下一篇与页面上的显示顺序保持一致
    currentResults = groups.flatMap(([, dayPapers]) => dayPapers);
    pendingGroups = groups;
    renderContext = { highlightPattern: buildHighlightPattern(tokens), eagerImagesLeft: EAGER_IMAGE_COUNT };
    appendNextBatch();
  }

  function render(){
    const tokens = getSearchTokens();
    const results = filterPapers(tokens);
    updateStats(results.length);

    if(!papers.length){
      renderList([], []);
      renderStatus('还没有论文', '当前还没有可展示的数据，等抓取和摘要生成完成后，这里会自动出现。');
      return;
    }

    if(!results.length){
      renderList([], []);
      const stillLoading = searchIndexState === 'loading';
      renderStatus(
        stillLoading ? '正在加载全文索引…' : '没有找到匹配的论文',
        stillLoading
          ? '标题和导读中暂无匹配，正在加载论文概述以扩大检索范围。'
          : `试试更短或更通用的关键词。当前共收录 ${papers.length} 篇论文。`,
        { label: '清空搜索', onClick: () => { setSearchQuery(''); searchEl.focus(); } }
      );
      return;
    }

    clearStatus();
    renderList(results, tokens);
  }

  // ---------- 首页滚动位置（仅当前标签页会话内恢复，次日打开总是从最新开始） ----------

  if('scrollRestoration' in window.history){
    window.history.scrollRestoration = 'manual';
  }

  function saveScroll(){
    try {
      window.sessionStorage.setItem(HOME_SCROLL_KEY, String(Math.round(window.scrollY || 0)));
    } catch (error) {
      // sessionStorage 不可用时忽略
    }
  }

  function restoreScroll(){
    let scrollY = 0;
    try {
      scrollY = Number(window.sessionStorage.getItem(HOME_SCROLL_KEY)) || 0;
    } catch (error) {
      return;
    }
    if(window.location.hash || scrollY <= 0){
      return;
    }
    while(pendingGroups.length && document.documentElement.scrollHeight < scrollY + window.innerHeight){
      appendNextBatch();
    }
    window.scrollTo({ top: scrollY, behavior: 'instant' });
  }

  let saveScrollTimerId = null;
  window.addEventListener('scroll', () => {
    window.clearTimeout(saveScrollTimerId);
    saveScrollTimerId = window.setTimeout(saveScroll, 200);
  }, { passive: true });
  window.addEventListener('pagehide', saveScroll);

  // ---------- 返回顶部 ----------

  if(backToTopEl && introEl && 'IntersectionObserver' in window){
    new IntersectionObserver(([entry]) => {
      backToTopEl.classList.toggle('is-visible', !entry.isIntersecting);
    }).observe(introEl);
    backToTopEl.addEventListener('click', () => window.scrollTo({ top: 0 }));
  }

  // ---------- 已读标记 ----------

  function markPaperRead(paperId){
    if(!readState || !paperId){
      return;
    }
    readState.mark(paperId);
    groupsEl.querySelectorAll('.entry').forEach((entryEl) => {
      if(entryEl.dataset.paperId === paperId){
        entryEl.classList.add('is-read');
      }
    });
  }

  // ---------- 阅读抽屉 ----------

  /** paperId -> Promise<string>：详情页中 .article-sections 的 HTML */
  const sectionCache = new Map();

  function loadSections(paper){
    const paperId = getPaperId(paper);
    if(!sectionCache.has(paperId)){
      const request = fetch(paper.detail_path)
        .then((response) => {
          if(!response.ok){
            throw new Error(`HTTP ${response.status}`);
          }
          return response.text();
        })
        .then((html) => {
          // DOMParser 解析出的文档不会加载其中的图片和脚本
          const sectionsEl = new DOMParser().parseFromString(html, 'text/html').querySelector('.article-sections');
          if(!sectionsEl){
            throw new Error('详情页缺少正文');
          }
          return sectionsEl.innerHTML;
        });
      request.catch(() => sectionCache.delete(paperId));
      sectionCache.set(paperId, request);
    }
    return sectionCache.get(paperId);
  }

  function prefetchSections(paper){
    if(paper && !(navigator.connection && navigator.connection.saveData)){
      loadSections(paper).catch(() => {});
    }
  }

  let readerEl = null;
  let readerScrollEl = null;
  let readerArticleEl = null;
  let readerPrevEl = null;
  let readerNextEl = null;
  let readerPositionEl = null;
  let readerOpenLinkEl = null;
  let readerList = [];
  let readerIndex = -1;
  let readerRenderToken = 0;
  let readerReturnFocusEl = null;
  const backgroundEls = [document.querySelector('.masthead'), document.querySelector('main'), document.querySelector('.footer'), backToTopEl]
    .filter(Boolean);

  function isReaderOpen(){
    return Boolean(readerEl && readerEl.classList.contains('is-open'));
  }

  function getCurrentReaderPaper(){
    return readerList[readerIndex] || null;
  }

  function ensureReader(){
    if(readerEl){
      return;
    }
    readerEl = createElement('div', 'reader');
    readerEl.setAttribute('aria-hidden', 'true');
    readerEl.innerHTML = `
      <div class="reader-backdrop" data-reader-close></div>
      <section class="reader-panel" role="dialog" aria-modal="true" aria-labelledby="reader-title">
        <header class="reader-toolbar">
          <div class="reader-nav">
            <button class="icon-button" type="button" data-reader-step="-1" aria-label="上一篇（←）" title="上一篇（←）">‹</button>
            <span class="reader-position" aria-live="polite"></span>
            <button class="icon-button" type="button" data-reader-step="1" aria-label="下一篇（→）" title="下一篇（→）">›</button>
          </div>
          <div class="reader-actions">
            <a class="pill-link reader-open-link" href="#" target="_blank" rel="noopener">新页面打开 ↗</a>
            <button class="icon-button" type="button" data-reader-close aria-label="关闭（Esc）" title="关闭（Esc）">×</button>
          </div>
        </header>
        <div class="reader-scroll" tabindex="-1">
          <article class="reader-article"></article>
        </div>
      </section>
    `;
    document.body.appendChild(readerEl);
    readerScrollEl = readerEl.querySelector('.reader-scroll');
    readerArticleEl = readerEl.querySelector('.reader-article');
    readerPrevEl = readerEl.querySelector('[data-reader-step="-1"]');
    readerNextEl = readerEl.querySelector('[data-reader-step="1"]');
    readerPositionEl = readerEl.querySelector('.reader-position');
    readerOpenLinkEl = readerEl.querySelector('.reader-open-link');

    readerEl.addEventListener('click', (event) => {
      const paper = getCurrentReaderPaper();
      if(event.target.closest('[data-reader-close]')){
        requestCloseReader();
        return;
      }
      const stepEl = event.target.closest('[data-reader-step]');
      if(stepEl){
        stepReader(Number(stepEl.dataset.readerStep));
        return;
      }
      const zoomEl = event.target.closest('[data-zoom-src]');
      if(zoomEl && paper){
        openPaperImage(paper, zoomEl, 'modal');
        return;
      }
      const analyticsEl = event.target.closest('[data-analytics-event]');
      if(analyticsEl && paper){
        track(analyticsEl.dataset.analyticsEvent, { paper_id: getPaperId(paper), paper_title: paper.title || '' });
      }
      if(event.target.closest('.reader-open-link') && paper){
        track('paper_open', { paper_id: getPaperId(paper), paper_title: paper.title || '', open_mode: 'new_tab' });
      }
    });
  }

  function createSkeleton(){
    const skeletonEl = createElement('div', 'article-skeleton');
    skeletonEl.setAttribute('aria-label', '正在加载正文');
    for(let index = 0; index < 5; index += 1){
      skeletonEl.appendChild(createElement('span'));
    }
    return skeletonEl;
  }

  function createPillLink(href, text, analyticsEvent){
    const linkEl = createElement('a', 'pill-link', text);
    linkEl.href = href;
    linkEl.target = '_blank';
    linkEl.rel = 'noopener noreferrer';
    linkEl.dataset.analyticsEvent = analyticsEvent;
    return linkEl;
  }

  /** 先用列表数据即时渲染文章头部，正文异步填充。 */
  function renderReaderArticle(paper){
    const renderToken = ++readerRenderToken;
    const { label, weekday } = describeDate(paper.date);

    const kickerEl = createElement('p', 'article-kicker');
    kickerEl.append(createElement('strong', '', '论文精读'), createElement('span', '', `${label} ${weekday}`));

    const titleEl = createElement('h2', 'article-title', paper.title || '未命名论文');
    titleEl.id = 'reader-title';

    const linksEl = createElement('div', 'article-links');
    if(paper.arxiv_id){
      linksEl.append(
        createPillLink(`https://arxiv.org/abs/${paper.arxiv_id}`, 'arXiv 原文 ↗', 'paper_source_click'),
        createPillLink(`https://hjfy.top/arxiv/${paper.arxiv_id}`, '中文翻译 ↗', 'paper_translation_click')
      );
    }

    const leadEl = createElement('p', 'article-lead', paper.hook_text || '摘要还在生成中');

    const figureEl = createElement('figure', 'article-figure');
    if(paper.paper_image_path){
      const zoomEl = createElement('button', 'article-figure-zoom');
      zoomEl.type = 'button';
      zoomEl.dataset.zoomSrc = paper.paper_image_full_path || paper.paper_image_path;
      zoomEl.dataset.zoomFallback = paper.paper_image_path;
      zoomEl.setAttribute('aria-label', '放大查看论文首图');
      const imageEl = createElement('img');
      // 列表缩略图已在浏览器缓存中，立即可见；全尺寸图在放大时再加载
      imageEl.src = paper.paper_image_path;
      imageEl.alt = `${paper.title} 论文首图`;
      zoomEl.append(imageEl, createElement('span', 'article-figure-hint', '点击放大'));
      figureEl.appendChild(zoomEl);
    } else {
      figureEl.appendChild(createNoteCover(paper));
    }

    const unitEl = createElement('p', 'article-unit', paper.research_unit || '');
    unitEl.hidden = !paper.research_unit;

    const factsEl = createElement('ul', 'article-facts');
    [
      paper.arxiv_id ? `arXiv ${paper.arxiv_id}` : '',
      `${paper.section_count || 0} 节精读`,
      `约 ${paper.reading_minutes || 1} 分钟`
    ].filter(Boolean).forEach((fact) => factsEl.appendChild(createElement('li', '', fact)));

    const sectionsEl = createElement('div', 'article-sections');
    sectionsEl.appendChild(createSkeleton());

    const hintEl = createElement('p', 'reader-hint');
    hintEl.innerHTML = '<kbd>←</kbd> <kbd>→</kbd> 切换论文 · <kbd>Esc</kbd> 关闭';

    readerArticleEl.replaceChildren(kickerEl, titleEl, linksEl, leadEl, figureEl, unitEl, factsEl, sectionsEl, hintEl);

    loadSections(paper)
      .then((sectionsHTML) => {
        if(renderToken === readerRenderToken){
          sectionsEl.innerHTML = sectionsHTML;
        }
      })
      .catch((error) => {
        if(renderToken !== readerRenderToken){
          return;
        }
        console.warn('加载论文正文失败', error);
        const errorEl = createElement('p', 'article-error', '正文加载失败，');
        const linkEl = createElement('a', '', '在新页面打开');
        linkEl.href = paper.detail_path;
        errorEl.appendChild(linkEl);
        sectionsEl.replaceChildren(errorEl);
      });
  }

  function showReaderPaper(index){
    const paper = readerList[index];
    if(!paper){
      return;
    }
    readerIndex = index;
    renderReaderArticle(paper);
    readerScrollEl.scrollTop = 0;
    readerPrevEl.disabled = index <= 0;
    readerNextEl.disabled = index >= readerList.length - 1;
    readerPositionEl.textContent = `${index + 1} / ${readerList.length}`;
    readerOpenLinkEl.href = new URL(paper.detail_path, window.location.href).href;

    const paperId = getPaperId(paper);
    markPaperRead(paperId);
    track('paper_open', { paper_id: paperId, paper_title: paper.title || '', open_mode: 'modal' });
    // 预取相邻论文，翻页时正文立即可见
    prefetchSections(readerList[index + 1]);
    prefetchSections(readerList[index - 1]);
  }

  function setReaderURL(paperId, mode){
    const url = new URL(window.location.href);
    url.searchParams.set(PAPER_QUERY_KEY, paperId);
    const state = { ...(window.history.state || {}), reader: paperId };
    if(mode === 'push'){
      // readerPushed 标记这条历史记录由抽屉创建，关闭时可以安全地 history.back()
      window.history.pushState({ ...state, readerPushed: true }, '', url);
    } else {
      window.history.replaceState(state, '', url);
    }
  }

  function openReader(paper, options){
    const settings = options || {};
    ensureReader();
    readerList = currentResults.includes(paper) ? currentResults : papers;
    showReaderPaper(readerList.indexOf(paper));

    if(!isReaderOpen()){
      readerReturnFocusEl = settings.returnFocus || document.activeElement;
      readerEl.classList.add('is-open');
      readerEl.setAttribute('aria-hidden', 'false');
      document.body.classList.add('has-reader');
      backgroundEls.forEach((element) => { element.inert = true; });
      // 焦点放在正文滚动区：空格 / ↑↓ / PageDown 直接滚动文章
      readerScrollEl.focus({ preventScroll: true });
    }

    if(settings.updateHistory){
      setReaderURL(getPaperId(paper), 'push');
    }
  }

  function stepReader(delta){
    const nextIndex = readerIndex + delta;
    if(!isReaderOpen() || nextIndex < 0 || nextIndex >= readerList.length){
      return;
    }
    showReaderPaper(nextIndex);
    if(new URL(window.location.href).searchParams.has(PAPER_QUERY_KEY)){
      setReaderURL(getPaperId(readerList[nextIndex]), 'replace');
    }
  }

  function hideReader(){
    if(!isReaderOpen()){
      return;
    }
    readerRenderToken += 1;
    readerEl.classList.remove('is-open');
    readerEl.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('has-reader');
    backgroundEls.forEach((element) => { element.inert = false; });

    // 回到当前读到的那篇（翻页后可能已不是最初点开的条目）
    const paper = getCurrentReaderPaper();
    const entryLinkEl = paper
      ? Array.from(groupsEl.querySelectorAll('.entry')).find((entryEl) => entryEl.dataset.paperId === getPaperId(paper))?.querySelector('.entry-link')
      : null;
    const focusTarget = entryLinkEl || readerReturnFocusEl;
    if(focusTarget && typeof focusTarget.focus === 'function'){
      focusTarget.focus({ preventScroll: !entryLinkEl });
    }
    readerReturnFocusEl = null;
  }

  function requestCloseReader(){
    if(window.PaperImageViewer?.isOpen()){
      window.PaperImageViewer.close();
      return;
    }
    const url = new URL(window.location.href);
    const urlPaperId = url.searchParams.get(PAPER_QUERY_KEY);
    const historyState = window.history.state || {};
    hideReader();

    // 抽屉是本页 pushState 打开的：直接后退，避免历史记录越积越多
    if(urlPaperId && historyState.readerPushed){
      window.history.back();
      return;
    }
    url.searchParams.delete(PAPER_QUERY_KEY);
    const { reader, readerPushed, ...restState } = historyState;
    window.history.replaceState(restState, '', url);
  }

  function syncReaderWithURL(){
    const paperId = new URL(window.location.href).searchParams.get(PAPER_QUERY_KEY);
    const paper = paperId ? paperById.get(paperId) : null;
    if(paper){
      openReader(paper, { updateHistory: false });
    } else {
      hideReader();
    }
  }

  window.addEventListener('popstate', syncReaderWithURL);

  // ---------- 首图放大 ----------

  function openPaperImage(paper, triggerEl, openMode){
    if(!window.PaperImageViewer){
      return;
    }
    track('paper_image_open', { paper_id: getPaperId(paper), paper_title: paper.title || '', open_mode: openMode });
    window.PaperImageViewer.open({
      src: paper.paper_image_full_path || paper.paper_image_path,
      fallbackSrc: paper.paper_image_path,
      alt: paper.title,
      caption: paper.title || '',
      returnFocus: triggerEl
    });
  }

  // ---------- 条目交互（事件委托） ----------

  function getEntryPaper(target){
    const entryEl = target.closest('.entry');
    return entryEl ? paperById.get(entryEl.dataset.paperId) : null;
  }

  groupsEl.addEventListener('click', (event) => {
    const paper = getEntryPaper(event.target);
    if(!paper){
      return;
    }
    const zoomEl = event.target.closest('[data-action="zoom"]');
    if(zoomEl){
      event.preventDefault();
      openPaperImage(paper, zoomEl, 'home');
      return;
    }
    const linkEl = event.target.closest('.entry-link');
    if(!linkEl){
      return;
    }
    if(event.button !== 0 || hasModifierKey(event)){
      markPaperRead(getPaperId(paper));
      return;
    }
    event.preventDefault();
    openReader(paper, { updateHistory: true, returnFocus: linkEl });
  });

  // 悬停 / 聚焦 / 触摸时预取正文，点开时通常已在缓存中
  let prefetchTimerId = null;
  groupsEl.addEventListener('pointerover', (event) => {
    const paper = getEntryPaper(event.target);
    if(!paper || sectionCache.has(getPaperId(paper))){
      return;
    }
    window.clearTimeout(prefetchTimerId);
    prefetchTimerId = window.setTimeout(() => prefetchSections(paper), PREFETCH_DELAY_MS);
  });
  groupsEl.addEventListener('touchstart', (event) => prefetchSections(getEntryPaper(event.target)), { passive: true });
  groupsEl.addEventListener('focusin', (event) => prefetchSections(getEntryPaper(event.target)));

  // ---------- 键盘快捷键 ----------

  document.addEventListener('keydown', (event) => {
    if(event.defaultPrevented){
      return;
    }
    const imageViewerOpen = window.PaperImageViewer?.isOpen();

    if(isReaderOpen()){
      if(imageViewerOpen){
        return; // 交给灯箱处理
      }
      if(event.key === 'Escape'){
        event.preventDefault();
        requestCloseReader();
      } else if(!hasModifierKey(event) && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')){
        event.preventDefault();
        stepReader(event.key === 'ArrowLeft' ? -1 : 1);
      }
      return;
    }

    if(event.key === 'Escape' && event.target === searchEl && searchEl.value){
      event.preventDefault();
      setSearchQuery('');
      return;
    }

    if(event.key === '/' && !hasModifierKey(event) && !imageViewerOpen && !isEditableTarget(event.target)){
      event.preventDefault();
      searchEl.focus();
      searchEl.select();
    }
  });

  // ---------- 数据加载 ----------

  async function loadData(){
    renderStatus('正在加载论文…', '马上就好。');
    try {
      const response = await fetch(DATA_URL);
      if(!response.ok){
        throw new Error(`HTTP ${response.status}`);
      }
      papers = await response.json();
      paperById.clear();
      latestDate = '';
      papers.forEach((paper) => {
        paper.haystack = buildHaystack(paper);
        paperById.set(getPaperId(paper), paper);
        if(paper.date > latestDate){
          latestDate = paper.date;
        }
      });

      if(getSearchTokens().length){
        ensureSearchIndex();
      }
      render();
      restoreScroll();
      syncReaderWithURL();
    } catch (error) {
      console.error(error);
      renderList([], []);
      renderStatus('论文加载失败', '无法读取论文数据，请检查网络后重试。', { label: '重新加载', onClick: loadData });
    }
  }

  const initialQuery = new URL(window.location.href).searchParams.get('q') || '';
  if(initialQuery){
    searchEl.value = initialQuery;
  }
  updateSearchChrome();
  loadData();
})();
