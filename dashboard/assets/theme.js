(() => {
  const root = document.documentElement;
  const storageKey = 'camera-service-theme';

  try {
    if (localStorage.getItem(storageKey) === 'light') root.dataset.theme = 'light';
  } catch {}

  function bindThemeButton() {
    const button = document.getElementById('theme-toggle');
    if (!button) return;

    function updateLabel() {
      const nextTheme = root.dataset.theme === 'light' ? 'dark' : 'light';
      const label = `Switch to ${nextTheme} theme`;
      button.setAttribute('aria-label', label);
      button.title = label;
    }

    button.addEventListener('click', () => {
      const nextTheme = root.dataset.theme === 'light' ? 'dark' : 'light';
      root.dataset.theme = nextTheme;
      try { localStorage.setItem(storageKey, nextTheme); } catch {}
      updateLabel();
      document.dispatchEvent(new Event('camera-theme-change'));
    });
    updateLabel();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindThemeButton, { once: true });
  } else {
    bindThemeButton();
  }
})();
