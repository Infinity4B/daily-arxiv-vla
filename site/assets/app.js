/**
 * @file app.js
 * @description 前端逻辑：加载 data.json，渲染卡片、搜索、状态反馈、详情目录与键盘交互。
 */
(function(){
  /** @type {Array<{date:string,title:string,link:string,summary_markdown:string,summary_html:string}>} */
  let DATA = [];

  const $ = (sel) => document.querySelector(sel);
  const statusEl = $('#status');
  const groupsEl = $('#groups');
  const searchEl = $('#search');
  const detailView = $('#detail-view');
  const detailTitle = $('#detail-title');
  const detailMeta = $('#detail-meta');
  const detailBody = $('#detail-body');
  const detailToc = $('#detail-toc');
  const detailTocNav = $('#detail-toc-nav');
  const detailBack = $('#detail-back');
  let currentItem = null;
  let lastScrollY = 0;
  let lastFocusedCard = null;

  /**
   * @param {Array} items
   * @param {string} q
   */
  function filterItems(items, q){
    const kw = (q||'').trim().toLowerCase();
    return items.filter(it => {
      if(!kw) return true;
      const hay = (it.title + ' ' + it.summary_markdown).toLowerCase();
      return hay.includes(kw);
    });
  }

  function extractSectionBlock(markdown, title){
    const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const match = markdown.match(new RegExp(`##\\s*${escaped}[\\s\\S]*?(?=##|$)`));
    return match ? match[0] : '';
  }

  function extractResearchUnit(markdown){
    const block = extractSectionBlock(markdown, '研究单位');
    if(!block){
      return '';
    }

    const firstBullet = block
      .split('\n')
      .map((line) => line.trim())
      .find((line) => line.startsWith('- '));

    if(!firstBullet){
      return '';
    }

    return firstBullet
      .replace(/^-\s*/, '')
      .replace(/\*\*/g, '')
      .replace(/`/g, '')
      .replace(/作者主要来自/g, '')
      .replace(/作者来自/g, '')
      .trim();
  }

  function getArxivId(link){
    const match = link.match(/arxiv\.org\/(?:abs|pdf)\/([^/?#]+)/i);
    return match ? match[1] : '';
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

  /**
   * 提取论文概述部分作为预览
   * @param {string} markdown
   * @returns {string}
   */
  function extractOverview(markdown){
    // 尝试提取 "## 论文概述" 部分
    const overviewMatch = markdown.match(/##\s*论文概述[\s\S]*?(?=##|$)/);
    if(overviewMatch){
      // 移除标题行和标记符号，只保留内容
      let content = overviewMatch[0]
        .replace(/##\s*论文概述\s*/, '')
        .replace(/#+\s+/g, '')
        .replace(/\*\*/g, '')
        .replace(/`/g, '')
        .trim();
      return content.substring(0, 200);
    }
    // 回退：如果找不到论文概述，使用原有逻辑
    return markdown.replace(/#+\s+/g, '').replace(/\*\*/g, '').substring(0, 200);
  }

  /**
   * @param {Array} items  已过滤后的项目
   */
  function renderGroups(items){
    if(!items.length){
      groupsEl.innerHTML = '';
      return;
    }

    const map = new Map();
    items.forEach(it=>{ if(!map.has(it.date)) map.set(it.date, []); map.get(it.date).push(it); });
    const dates = Array.from(map.keys()).sort((a,b)=> b.localeCompare(a));

    groupsEl.innerHTML = '';
    dates.forEach(d => {
      const group = document.createElement('section');
      group.className = 'group';

      const heading = document.createElement('div');
      heading.className = 'group-heading';

      const h = document.createElement('h2');
      h.textContent = d;

      const count = document.createElement('div');
      count.className = 'group-count';
      count.textContent = `${map.get(d).length} 篇`;

      const grid = document.createElement('div');
      grid.className = 'grid';

      map.get(d).forEach(it => {
        const card = document.createElement('button');
        card.type = 'button';
        card.className = 'card';
        card.setAttribute('aria-label', `查看论文：${it.title}`);
        card.addEventListener('click', ()=> openDetail(it, card));

        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = it.title;

        const tags = document.createElement('div');
        tags.className = 'card-tags';

        const researchUnit = extractResearchUnit(it.summary_markdown);
        if(researchUnit){
          const orgTag = document.createElement('div');
          orgTag.className = 'card-tag primary';
          orgTag.textContent = researchUnit;
          tags.appendChild(orgTag);
        }

        const arxivId = getArxivId(it.link);
        if(arxivId){
          const idTag = document.createElement('div');
          idTag.className = 'card-tag';
          idTag.textContent = arxivId;
          tags.appendChild(idTag);
        }

        const preview = document.createElement('div');
        preview.className = 'summary-preview';
        preview.textContent = extractOverview(it.summary_markdown);

        const footer = document.createElement('div');
        footer.className = 'card-footer';
        const readMore = document.createElement('div');
        readMore.className = 'read-more';
        readMore.textContent = '阅读详情';

        footer.appendChild(readMore);
        if(tags.childNodes.length){
          card.appendChild(tags);
        }
        card.appendChild(title);
        card.appendChild(preview);
        card.appendChild(footer);
        grid.appendChild(card);
      });
      heading.appendChild(h);
      heading.appendChild(count);
      group.appendChild(heading);
      group.appendChild(grid);
      groupsEl.appendChild(group);
    });
  }

  /**
   * 从 arxiv.org 链接中提取论文 ID，并生成幻觉翻译链接
   * @param {string} link
   * @returns {string|null} 幻觉翻译链接，如果不是 arxiv 链接则返回 null
   */
  function getTranslationLink(link){
    // 匹配 arxiv.org/abs/ 或 arxiv.org/pdf/ 等格式
    const match = link.match(/arxiv\.org\/(?:abs|pdf)\/([\d.]+)/i);
    if(match && match[1]){
      return `https://hjfy.top/arxiv/${match[1]}`;
    }
    return null;
  }

  function renderDetailMeta(it){
    detailMeta.innerHTML = '';
    detailMeta.append(document.createTextNode(it.date));

    const sourceLink = document.createElement('a');
    sourceLink.href = it.link;
    sourceLink.target = '_blank';
    sourceLink.rel = 'noopener noreferrer';
    sourceLink.textContent = '原文链接';

    detailMeta.append(document.createTextNode(' · '));
    detailMeta.appendChild(sourceLink);

    const translationLink = getTranslationLink(it.link);
    if(translationLink){
      const translated = document.createElement('a');
      translated.href = translationLink;
      translated.target = '_blank';
      translated.rel = 'noopener noreferrer';
      translated.textContent = '幻觉翻译';
      detailMeta.append(document.createTextNode(' · '));
      detailMeta.appendChild(translated);
    }
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
    detailTocNav.innerHTML = '';
    const headings = Array.from(detailBody.querySelectorAll('h2'));

    if(!headings.length){
      detailToc.classList.add('hidden');
      return;
    }

    headings.forEach((heading, index) => {
      if(!heading.id){
        heading.id = slugifyHeading(heading.textContent, index + 1);
      }
      const link = document.createElement('a');
      link.className = 'detail-toc-link';
      link.href = `#${heading.id}`;
      link.textContent = heading.textContent || `章节 ${index + 1}`;
      link.addEventListener('click', (event) => {
        event.preventDefault();
        heading.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      detailTocNav.appendChild(link);
    });

    detailToc.classList.remove('hidden');
  }

  function showDetail(it){
    currentItem = it;
    detailTitle.textContent = it.title;
    renderDetailMeta(it);
    detailBody.innerHTML = it.summary_html; // 已在后端修复换行并渲染
    buildDetailToc();
    detailView.classList.remove('hidden');
    document.body.classList.add('detail-open');
    window.scrollTo(0, 0);
    detailBack.focus();
  }

  function openDetail(it, card){
    lastScrollY = window.scrollY || 0;
    lastFocusedCard = card || document.activeElement;
    showDetail(it);
    history.pushState({ view: 'detail', item: it }, '', window.location.href);
  }

  function hideDetail(){
    detailView.classList.add('hidden');
    detailToc.classList.add('hidden');
    detailTocNav.innerHTML = '';
    currentItem = null;
    document.body.classList.remove('detail-open');
  }

  function restoreListState(){
    requestAnimationFrame(() => window.scrollTo(0, lastScrollY));
    if(lastFocusedCard && typeof lastFocusedCard.focus === 'function'){
      lastFocusedCard.focus();
    }
  }

  function closeDetail(){
    if(history.state && history.state.view === 'detail'){
      history.back();
      return;
    }
    hideDetail();
    restoreListState();
  }

  function sync(){
    const items = filterItems(DATA, searchEl.value);

    if(!DATA.length){
      renderGroups([]);
      renderStatus('empty', '还没有论文数据', '当前数据集中没有可展示的论文。等抓取任务跑完后，这里会自动显示。');
      return;
    }

    if(!items.length){
      renderGroups([]);
      renderStatus(
        'empty',
        '没有找到匹配结果',
        `试试换个关键词，当前一共收录了 ${DATA.length} 篇论文。`,
        {
          label: '清空搜索',
          onClick: () => {
            searchEl.value = '';
            sync();
            searchEl.focus();
          }
        }
      );
      return;
    }

    clearStatus();
    renderGroups(items);
  }

  detailBack.addEventListener('click', closeDetail);
  document.addEventListener('keydown', (event) => {
    if(event.key === 'Escape' && !detailView.classList.contains('hidden')){
      event.preventDefault();
      closeDetail();
    }
  });

  window.addEventListener('popstate', (e) => {
    if (e.state && e.state.view === 'detail' && e.state.item) {
      showDetail(e.state.item);
    } else {
      hideDetail();
      restoreListState();
    }
  });

  searchEl.addEventListener('input', sync);

  async function loadData(){
    renderStatus('loading', '正在加载论文列表', '页面正在读取静态数据并构建卡片，你可以稍后直接开始搜索。');
    try{
      const response = await fetch('assets/data.json');
      if(!response.ok){
        throw new Error(`HTTP ${response.status}`);
      }
      DATA = await response.json();
      sync();
    } catch (error) {
      console.error(error);
      renderGroups([]);
      renderStatus(
        'error',
        '论文数据加载失败',
        '无法读取 data.json。你可以刷新页面重试，或者确认静态资源是否已成功构建。',
        { label: '重新加载', onClick: loadData }
      );
    }
  }

  loadData();
})();