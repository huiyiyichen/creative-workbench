const input = document.getElementById('api');
const status = document.getElementById('status');
chrome.storage.sync.get('api').then(({ api }) => { input.value = api || 'http://localhost:8000/api/v1'; });
document.getElementById('save').addEventListener('click', async () => {
  const api = input.value.trim().replace(/\/+$/, '');
  await chrome.storage.sync.set({ api });
  try {
    const r = await fetch(`${api}/library/extension/ping`);
    status.textContent = r.ok ? '已连上' : `连不上（HTTP ${r.status}）`;
  } catch {
    status.textContent = '连不上，请确认创意工作台已启动';
  }
});
