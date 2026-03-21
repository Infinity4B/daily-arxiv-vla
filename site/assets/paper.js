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

  buildDetailToc();
  restoreScroll();
})();