/**
 * @file paper.js
 * @description 论文详情页：首图放大、外链统计、←/→ 切换论文、目录高亮、记录阅读位置与已读状态。
 * （首页的阅读抽屉直接抓取本页正文 HTML，不会运行这个脚本。）
 */
(function(){
  const paperId = document.body.dataset.paperId || '';
  const paperTitle = document.querySelector('.article-title')?.textContent.trim() || document.title;
  const scrollStorageKey = paperId ? `paper-scroll:${paperId}` : '';

  function trackPaperEvent(name, params){
    window.siteAnalytics?.track(name, { paper_id: paperId, paper_title: paperTitle, ...(params || {}) });
  }

  // ---------- 首图放大 / 外链统计 ----------

  document.addEventListener('click', (event) => {
    const zoomEl = event.target.closest('[data-zoom-src]');
    if(zoomEl && window.PaperImageViewer){
      event.preventDefault();
      trackPaperEvent('paper_image_open', { open_mode: 'page' });
      window.PaperImageViewer.open({
        src: zoomEl.dataset.zoomSrc,
        fallbackSrc: zoomEl.dataset.zoomFallback || '',
        alt: paperTitle,
        caption: paperTitle,
        returnFocus: zoomEl
      });
      return;
    }
    const analyticsEl = event.target.closest('[data-analytics-event]');
    if(analyticsEl){
      trackPaperEvent(analyticsEl.dataset.analyticsEvent);
    }
  });

  // ---------- ←/→ 切换论文 ----------

  const prevLinkEl = document.querySelector('.paper-nav-prev');
  const nextLinkEl = document.querySelector('.paper-nav-next');

  document.addEventListener('keydown', (event) => {
    if(event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey){
      return;
    }
    if(window.PaperImageViewer?.isOpen() || event.target.closest('input, textarea, select, [contenteditable="true"]')){
      return;
    }
    const linkEl = event.key === 'ArrowLeft' ? prevLinkEl : event.key === 'ArrowRight' ? nextLinkEl : null;
    if(linkEl){
      event.preventDefault();
      window.location.href = linkEl.href;
    }
  });

  window.paperReadState?.mark(paperId);

  // ---------- 目录高亮（目录由构建脚本生成） ----------

  const tocLinks = new Map();
  document.querySelectorAll('.article-toc a').forEach((linkEl) => {
    tocLinks.set(decodeURIComponent(linkEl.hash.slice(1)), linkEl);
  });

  if(tocLinks.size && 'IntersectionObserver' in window){
    let activeLinkEl = null;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        const linkEl = tocLinks.get(entry.target.id);
        if(!entry.isIntersecting || !linkEl || linkEl === activeLinkEl){
          return;
        }
        activeLinkEl?.classList.remove('is-active');
        activeLinkEl?.removeAttribute('aria-current');
        linkEl.classList.add('is-active');
        linkEl.setAttribute('aria-current', 'true');
        activeLinkEl = linkEl;
      });
    }, { rootMargin: '-15% 0px -60% 0px' });

    tocLinks.forEach((linkEl, sectionId) => {
      const sectionEl = document.getElementById(sectionId);
      if(sectionEl){
        observer.observe(sectionEl);
      }
    });
  }

  // ---------- 阅读位置（按论文记录，下次打开回到上次位置） ----------

  function saveScroll(){
    if(!scrollStorageKey){
      return;
    }
    try {
      const scrollY = Math.round(window.scrollY || 0);
      if(scrollY > 0){
        window.localStorage.setItem(scrollStorageKey, String(scrollY));
      } else {
        window.localStorage.removeItem(scrollStorageKey);
      }
    } catch (error) {
      // 存储不可用时忽略
    }
  }

  let saveScrollTimerId = null;
  window.addEventListener('scroll', () => {
    window.clearTimeout(saveScrollTimerId);
    saveScrollTimerId = window.setTimeout(saveScroll, 250);
  }, { passive: true });
  window.addEventListener('pagehide', saveScroll);

  if(scrollStorageKey && !window.location.hash){
    try {
      const scrollY = Number(window.localStorage.getItem(scrollStorageKey));
      if(Number.isFinite(scrollY) && scrollY > 0){
        window.scrollTo({ top: scrollY, behavior: 'instant' });
      }
    } catch (error) {
      console.warn('恢复阅读位置失败', error);
    }
  }
})();
