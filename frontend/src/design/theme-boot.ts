/** 主题首屏脚本（服务端组件可用，不能放进 'use client' 文件） */
export const THEME_KEY = 'cw-theme';

/** 放进 <head> 的内联脚本：页面渲染前读出主题，避免先闪一下暗色 */
export const THEME_BOOT_SCRIPT = `try{if(localStorage.getItem('${THEME_KEY}')==='light'){document.documentElement.dataset.theme='light'}}catch(e){}`;
