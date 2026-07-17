/**
 * @file theme.js
 * @description 在日间、夜间和跟随设备三种主题偏好间循环切换。
 */
(function(){
  const themeStorageKey = 'color-theme';
  const themePreferences = ['system', 'light', 'dark'];
  const themeLabels = {
    system: '设备',
    light: '日间',
    dark: '夜间'
  };
  const systemThemeQuery = window.matchMedia('(prefers-color-scheme: dark)');

  function normalizeThemePreference(themePreference){
    return themePreferences.includes(themePreference) ? themePreference : 'system';
  }

  function readThemePreference(){
    try {
      return normalizeThemePreference(window.localStorage.getItem(themeStorageKey));
    } catch (error) {
      return 'system';
    }
  }

  function resolveTheme(themePreference){
    if(themePreference === 'system'){
      return systemThemeQuery.matches ? 'dark' : 'light';
    }
    return themePreference;
  }

  function updateThemeToggle(themePreference){
    const themeLabel = themeLabels[themePreference];
    document.querySelectorAll('[data-theme-toggle]').forEach((themeToggleEl) => {
      themeToggleEl.dataset.themePreference = themePreference;
      themeToggleEl.setAttribute('aria-label', `当前主题：${themeLabel}，点击切换主题`);
      themeToggleEl.setAttribute('title', `当前主题：${themeLabel}`);
      const themeToggleLabelEl = themeToggleEl.querySelector('[data-theme-toggle-label]');
      if(themeToggleLabelEl){
        themeToggleLabelEl.textContent = themeLabel;
      }
    });
  }

  function applyThemePreference(themePreference, shouldPersist){
    const normalizedThemePreference = normalizeThemePreference(themePreference);
    const resolvedTheme = resolveTheme(normalizedThemePreference);
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.themePreference = normalizedThemePreference;
    document.documentElement.style.colorScheme = resolvedTheme;
    updateThemeToggle(normalizedThemePreference);

    if(shouldPersist){
      try {
        window.localStorage.setItem(themeStorageKey, normalizedThemePreference);
      } catch (error) {
        console.warn('无法保存主题偏好', error);
      }
    }
  }

  function cycleThemePreference(){
    const currentThemePreference = normalizeThemePreference(
      document.documentElement.dataset.themePreference || readThemePreference()
    );
    const currentThemeIndex = themePreferences.indexOf(currentThemePreference);
    const nextThemePreference = themePreferences[(currentThemeIndex + 1) % themePreferences.length];
    applyThemePreference(nextThemePreference, true);
  }

  document.addEventListener('click', (event) => {
    const themeToggleEl = event.target.closest('[data-theme-toggle]');
    if(themeToggleEl){
      cycleThemePreference();
    }
  });

  systemThemeQuery.addEventListener('change', () => {
    if(readThemePreference() === 'system'){
      applyThemePreference('system', false);
    }
  });

  window.addEventListener('storage', (event) => {
    if(event.key === themeStorageKey){
      applyThemePreference(event.newValue || 'system', false);
    }
  });

  applyThemePreference(readThemePreference(), false);
})();