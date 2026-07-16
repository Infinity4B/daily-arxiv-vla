/**
 * @file paper.js
 * @description 论文详情页逻辑：构建目录、标记当前阅读卡，并按 arXiv id 记录滚动进度。
 */
(function(){
  const $ = (selector) => document.querySelector(selector);
  const detailBody = $('#detail-body');
  const detailToc = $('#detail-toc');
  const detailTocNav = $('#detail-toc-nav');
  const paperId = document.body.dataset.paperId || '';
  const isEmbedded = window.parent !== window && new URL(window.location.href).searchParams.get('embed') === '1';

  function getImagePayload(imageEl){
    const figureEl = imageEl.closest('.paper-figure-card');
    const captionEl = figureEl ? figureEl.querySelector('.paper-figure-caption') : null;
    return {
      src: imageEl.currentSrc || imageEl.src,
      alt: imageEl.alt || '论文图片',
      caption: captionEl ? captionEl.textContent.trim() : imageEl.alt || ''
    };
  }

  function openPaperImage(imageEl){
    const payload = getImagePayload(imageEl);
    if(isEmbedded){
      try {
        if(window.parent.PaperImageViewer){
          window.parent.PaperImageViewer.open(payload);
          return;
        }
      } catch (error) {
        console.warn('无法直接调用父页面图片预览，改用消息转发', error);
      }
      window.parent.postMessage({ type: 'paper-image-open', ...payload }, window.location.origin);
      return;
    }

    if(window.PaperImageViewer){
      window.PaperImageViewer.open({ ...payload, returnFocus: imageEl });
    }
  }

  window.openPaperFigureImage = openPaperImage;

  function initializeImageZoom(){
    document.querySelectorAll('.paper-figure-image').forEach((imageEl) => {
      imageEl.dataset.zoomable = 'true';
      imageEl.tabIndex = 0;
      imageEl.setAttribute('role', 'button');
      imageEl.setAttribute('aria-label', `放大查看：${imageEl.alt || '论文图片'}`);
      imageEl.addEventListener('keydown', (event) => {
        if(event.key === 'Enter' || event.key === ' '){
          event.preventDefault();
          openPaperImage(imageEl);
        }
      });
    });
  }

  function initializeEmbeddedMode(){
    if(!isEmbedded){
      return;
    }

    document.body.classList.add('embedded-detail');
    const backLinkEl = document.querySelector('.back-link');
    if(backLinkEl){
      backLinkEl.addEventListener('click', (event) => {
        event.preventDefault();
        window.parent.postMessage({ type: 'paper-modal-close' }, window.location.origin);
      });
    }

    document.querySelectorAll('.paper-nav-link').forEach((linkEl) => {
      linkEl.addEventListener('click', (event) => {
        event.preventDefault();
        const targetURL = new URL(linkEl.href, window.location.href);
        targetURL.searchParams.set('embed', '1');
        window.location.href = targetURL.href;
      });
    });

    const standaloneURL = new URL(window.location.href);
    standaloneURL.searchParams.delete('embed');
    window.parent.postMessage({
      type: 'paper-modal-ready',
      title: document.querySelector('.detail-page-title')?.textContent || document.title,
      url: standaloneURL.href
    }, window.location.origin);

    window.addEventListener('keydown', (event) => {
      if(event.defaultPrevented || event.key !== 'Escape'){
        return;
      }
      event.preventDefault();
      window.parent.postMessage({ type: 'paper-modal-close' }, window.location.origin);
    });
  }

  function slugifyHeading(text, index){
    const slug = (text || '')
      .trim()
      .toLowerCase()
      .replace(/[^\w\u4e00-\u9fff]+/g, '-')
      .replace(/^-+|-+$/g, '');
    return slug ? `section-${index}-${slug}` : `section-${index}`;
  }

  function buildDetailToc(){
    if(!detailBody || !detailToc || !detailTocNav){
      return;
    }

    detailTocNav.innerHTML = '';
    const headings = Array.from(detailBody.querySelectorAll('.reading-card-section h2'));

    if(!headings.length){
      detailToc.classList.add('hidden');
      return;
    }

    const links = new Map();

    headings.forEach((heading, index) => {
      if(!heading.id){
        heading.id = slugifyHeading(heading.textContent, index + 1);
      }

      const link = document.createElement('a');
      link.className = 'detail-toc-link';
      link.href = `#${heading.id}`;
      link.textContent = heading.textContent || `章节 ${index + 1}`;
      detailTocNav.appendChild(link);
      links.set(heading.id, link);
    });

    if('IntersectionObserver' in window){
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          const link = links.get(entry.target.id);
          if(link && entry.isIntersecting){
            detailTocNav.querySelectorAll('.detail-toc-link').forEach((item) => item.classList.remove('is-active'));
            link.classList.add('is-active');
          }
        });
      }, {
        rootMargin: '-18% 0px -58% 0px',
        threshold: 0
      });

      headings.forEach((heading) => observer.observe(heading));
    }

    detailToc.classList.remove('hidden');
  }

  function getStorageKey(){
    return paperId ? `paper-scroll:${paperId}` : '';
  }

  function restoreScroll(){
    if(!paperId || window.location.hash){
      return;
    }

    const storageKey = getStorageKey();
    if(!storageKey){
      return;
    }

    try{
      const saved = window.localStorage.getItem(storageKey);
      if(saved === null){
        return;
      }

      const scrollY = Number(saved);
      if(!Number.isFinite(scrollY) || scrollY <= 0){
        return;
      }

      window.requestAnimationFrame(() => {
        window.scrollTo(0, scrollY);
      });
    } catch (error) {
      console.warn('恢复滚动进度失败', error);
    }
  }

  function saveScroll(){
    const storageKey = getStorageKey();
    if(!storageKey){
      return;
    }

    try{
      window.localStorage.setItem(storageKey, String(window.scrollY || 0));
    } catch (error) {
      console.warn('保存滚动进度失败', error);
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

  initializeEmbeddedMode();
  initializeImageZoom();
  buildDetailToc();
  restoreScroll();
})();