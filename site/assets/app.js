/**
 * @file app.js
 * @description 首页逻辑：加载轻量 data.json，渲染卡片与搜索。
 */
(function(){
  /** @type {Array<{date:string,title:string,link:string,arxiv_id:string,detail_path:string,preview_text:string,research_unit:string}>} */
  let DATA = [];

  const $ = (sel) => document.querySelector(sel);
  const statusEl = $('#status');
  const groupsEl = $('#groups');
  const searchEl = $('#search');

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
      item.arxiv_id || ''
    ].join(' ').toLowerCase();
  }

  function filterItems(items, query){
    const keyword = (query || '').trim().toLowerCase();
    if(!keyword){
      return items;
    }
    return items.filter((item) => buildSearchText(item).includes(keyword));
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
      const group = document.createElement('section');
      group.className = 'group';

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
        const cardLink = document.createElement('a');
        cardLink.className = 'card-link';
        cardLink.href = item.detail_path;
        cardLink.setAttribute('aria-label', `查看论文：${item.title}`);

        const card = document.createElement('article');
        card.className = 'card';

        const tags = document.createElement('div');
        tags.className = 'card-tags';

        if(item.research_unit){
          const orgTag = document.createElement('div');
          orgTag.className = 'card-tag primary';
          orgTag.textContent = item.research_unit;
          tags.appendChild(orgTag);
        }

        if(item.arxiv_id){
          const idTag = document.createElement('div');
          idTag.className = 'card-tag';
          idTag.textContent = item.arxiv_id;
          tags.appendChild(idTag);
        }

        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = item.title;

        const preview = document.createElement('div');
        preview.className = 'summary-preview';
        preview.textContent = item.preview_text || '暂无摘要预览';

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
        cardLink.appendChild(card);
        grid.appendChild(cardLink);
      });

      heading.appendChild(h2);
      heading.appendChild(count);
      group.appendChild(heading);
      group.appendChild(grid);
      groupsEl.appendChild(group);
    });
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