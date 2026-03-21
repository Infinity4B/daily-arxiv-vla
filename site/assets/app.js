/**
 * @file app.js
 * @description 首页逻辑：加载 data.json，渲染信息流卡片与搜索。
 */
(function(){
  /** @type {Array<{date:string,title:string,link:string,arxiv_id:string,detail_path:string,cover_path:string,paper_image_path:string,preview_text:string,research_unit:string,hook_text:string,key_points:string[],reading_minutes:number,section_count:number,cover_theme:Record<string,string>}>} */
  let DATA = [];

  const $ = (selector) => document.querySelector(selector);
  const statusEl = $('#status');
  const groupsEl = $('#groups');
  const searchEl = $('#search');
  const homeScrollKey = 'home-scroll:index';
  let restoredScroll = false;

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
    const keyword = (query || '').trim().toLowerCase();
    if(!keyword){
      return items;
    }
    return items.filter((item) => buildSearchText(item).includes(keyword));
  }

  function createFeedCard(item){
    const cardLink = document.createElement('a');
    cardLink.className = 'feed-card-link';
    cardLink.href = item.detail_path;
    cardLink.setAttribute('aria-label', `查看论文：${item.title}`);

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

  function renderGroups(items){
    if(!items.length){
      groupsEl.innerHTML = '';
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
    groupsEl.innerHTML = '';

    dates.forEach((date) => {
      const section = document.createElement('section');
      section.className = 'group';

      const heading = document.createElement('div');
      heading.className = 'group-heading';

      const h2 = document.createElement('h2');
      h2.textContent = date;

      const count = document.createElement('div');
      count.className = 'group-count';
      count.textContent = `${grouped.get(date).length} 篇`;

      const grid = document.createElement('div');
      grid.className = 'grid';

      grouped.get(date).forEach((item) => {
        grid.appendChild(createFeedCard(item));
      });

      heading.appendChild(h2);
      heading.appendChild(count);
      section.appendChild(heading);
      section.appendChild(grid);
      groupsEl.appendChild(section);
    });
  }

  function sync(){
    const items = filterItems(DATA, searchEl.value);

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

  searchEl.addEventListener('input', sync);

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

  async function loadData(){
    renderStatus('loading', '正在加载论文卡片', '页面正在读取静态数据并搭建阅读流，你可以稍后直接开始搜索。');

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
        '论文卡片加载失败',
        '无法读取 data.json。你可以刷新页面重试，或者重新运行构建脚本。',
        { label: '重新加载', onClick: loadData }
      );
    }
  }

  loadData();
})();