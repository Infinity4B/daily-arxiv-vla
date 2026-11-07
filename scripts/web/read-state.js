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
