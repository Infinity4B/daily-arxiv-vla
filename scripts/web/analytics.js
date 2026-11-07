/**
 * @file analytics.js
 * @description Google Analytics 自定义事件桥接。未配置 GA4 时自动静默。
 */
(function(){
  function normalizeParams(params){
    return Object.entries(params || {}).reduce((result, [key, value]) => {
      if(value === null || value === undefined){
        return result;
      }
      result[key] = typeof value === 'string' ? value.slice(0, 100) : value;
      return result;
    }, {});
  }

  function track(name, params){
    if(typeof window.gtag !== 'function' || !name){
      return;
    }
    window.gtag('event', name, normalizeParams(params));
  }

  window.siteAnalytics = { track };
})();