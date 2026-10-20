// 右键「存到灵感库」：图片 / 链接 / 选中文字 / 整页 → POST /api/v1/library/extension/save
const DEFAULT_API = 'http://localhost:8000/api/v1';

async function apiBase() {
  const { api } = await chrome.storage.sync.get('api');
  return (api || DEFAULT_API).replace(/\/+$/, '');
}

function notify(title, message) {
  chrome.notifications.create({ type: 'basic', iconUrl: 'icon.png', title, message });
}

export function payloadFor(info, tab) {
  const page = { page_url: tab?.url || info.pageUrl || null, page_title: tab?.title || null };
  if (info.menuItemId === 'cw-image' && info.srcUrl) return { type: 'image', url: info.srcUrl, ...page };
  if (info.menuItemId === 'cw-link' && info.linkUrl) return { type: 'link', url: info.linkUrl, ...page };
  if (info.menuItemId === 'cw-text' && info.selectionText) return { type: 'text', text: info.selectionText, ...page };
  return { type: 'link', url: page.page_url, ...page };
}

async function save(body) {
  try {
    const res = await fetch(`${await apiBase()}/library/extension/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    notify('已存到灵感库', data.item?.title || body.page_title || '');
  } catch (err) {
    notify('没存上', `${err.message || err}。请确认创意工作台已启动，或在扩展选项里改服务地址。`);
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: 'cw-page', title: '存这一页到灵感库', contexts: ['page'] });
    chrome.contextMenus.create({ id: 'cw-image', title: '存图片到灵感库', contexts: ['image'] });
    chrome.contextMenus.create({ id: 'cw-link', title: '存链接到灵感库', contexts: ['link'] });
    chrome.contextMenus.create({ id: 'cw-text', title: '存选中文字到灵感库', contexts: ['selection'] });
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => save(payloadFor(info, tab)));
chrome.action.onClicked.addListener((tab) => save(payloadFor({ menuItemId: 'cw-page' }, tab)));
