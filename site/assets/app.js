/**
 * @file app.js
 * @description 前端逻辑：加载 data.json，渲染卡片、搜索、日期筛选、详情弹窗。
 */
(function(){
  /** @type {Array<{date:string,title:string,link:string,summary_markdown:string,summary_html:string}>} */
  let DATA = [];

  const $ = (sel) => document.querySelector(sel);
  const groupsEl = $('#groups');
  const searchEl = $('#search');
  const detailView = $('#detail-view');
  const detailTitle = $('#detail-title');
  const detailMeta = $('#detail-meta');
  const detailBody = $('#detail-body');
  const detailBack = $('#detail-back');
  let currentItem = null;

  /**
   * @param {Array} items
   * @param {string} q
   * @param {string|null} date
   */
  function filterItems(items, q){
    const kw = (q||'').trim().toLowerCase();
    return items.filter(it => {
      if(!kw) return true;
      const hay = (it.title + ' ' + it.summary_markdown).toLowerCase();
      return hay.includes(kw);
    });
  }

  /**
   * @param {Array} items  已过滤后的项目
   */
  function renderGroups(items){
    // 分组：按日期降序
    const map = new Map();
    items.forEach(it=>{ if(!map.has(it.date)) map.set(it.date, []); map.get(it.date).push(it); });
    const dates = Array.from(map.keys()).sort((a,b)=> b.localeCompare(a));

    groupsEl.innerHTML = '';
    dates.forEach(d => {
      const group = document.createElement('section');
      group.className = 'group';
      const h = document.createElement('h2');
      h.textContent = d;
      const grid = document.createElement('div');
      grid.className = 'grid';
      map.get(d).forEach(it => {
        const card = document.createElement('div');
        card.className = 'card';
        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = it.title;
        const btnRow = document.createElement('div');
        btnRow.className = 'btn-row';
        const viewBtn = document.createElement('a');
        viewBtn.className = 'btn';
        viewBtn.href = it.link; viewBtn.target = '_blank'; viewBtn.rel = 'noopener noreferrer';
        viewBtn.textContent = '查看原文';
        const detailBtn = document.createElement('button');
        detailBtn.className = 'btn primary';
        detailBtn.textContent = '详情';
        detailBtn.onclick = ()=> openDetail(it);
        btnRow.appendChild(viewBtn);
        btnRow.appendChild(detailBtn);
        card.appendChild(title);
        card.appendChild(btnRow);
        grid.appendChild(card);
      });
      group.appendChild(h);
      group.appendChild(grid);
      groupsEl.appendChild(group);
    });
  }

  /**
   * @param {title:string,date:string,summary_html:string,link:string} it
   */
  function openDetail(it){
    currentItem = it;
    detailTitle.textContent = it.title;
    detailMeta.innerHTML = `${it.date} · <a href="${it.link}" target="_blank" rel="noopener noreferrer">原文链接</a>`;
    detailBody.innerHTML = it.summary_html; // 已在后端修复换行并渲染
    detailView.classList.remove('hidden');
    // 使用 pushState 添加历史记录，但不改变 URL
    history.pushState({ view: 'detail', item: it }, '', window.location.href);
    // 滚动到顶部
    window.scrollTo(0, 0);
  }

  function closeDetail(){ 
    detailView.classList.add('hidden');
    currentItem = null;
    // 如果当前在详情页面状态，替换为列表状态（不跳转）
    if (history.state && history.state.view === 'detail') {
      history.replaceState({ view: 'list' }, '', window.location.href);
    }
  }

  function sync(){
    const items = filterItems(DATA, searchEl.value);
    renderGroups(items);
  }

  detailBack.addEventListener('click', closeDetail);
  
  // 监听浏览器前进/后退事件
  window.addEventListener('popstate', (e) => {
    if (e.state && e.state.view === 'detail' && e.state.item) {
      // 前进到详情页面（不添加新的历史记录）
      currentItem = e.state.item;
      detailTitle.textContent = e.state.item.title;
      detailMeta.innerHTML = `${e.state.item.date} · <a href="${e.state.item.link}" target="_blank" rel="noopener noreferrer">原文链接</a>`;
      detailBody.innerHTML = e.state.item.summary_html;
      detailView.classList.remove('hidden');
      window.scrollTo(0, 0);
    } else {
      // 返回到列表页面（包括 view 为 'list' 或 null 的情况）
      detailView.classList.add('hidden');
      currentItem = null;
    }
  });

  searchEl.addEventListener('input', sync);

  fetch('assets/data.json').then(r=>r.json()).then(arr=>{ DATA = arr; sync(); });
})();