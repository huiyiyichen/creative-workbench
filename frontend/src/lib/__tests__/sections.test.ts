import { describe, expect, it } from 'vitest';
import { SETTINGS_TABS, SOURCES_TABS, activeTab, sectionTabsFor } from '@/design/sections';
import { activeNavId } from '@/design/nav';

describe('信源 / 设置分页（11.1）', () => {
  it('路径归到正确的分页组', () => {
    expect(sectionTabsFor('/admin/contents')).toBe(SOURCES_TABS);
    expect(sectionTabsFor('/sources')).toBe(SOURCES_TABS);
    expect(sectionTabsFor('/admin/prompts')).toBe(SETTINGS_TABS);
    expect(sectionTabsFor('/settings/scoring')).toBe(SETTINGS_TABS);
    expect(sectionTabsFor('/hot')).toBeNull();
  });
  it('当前页签取最长匹配', () => {
    expect(activeTab('/admin/sources/12', SOURCES_TABS)).toBe('/admin/sources');
    expect(activeTab('/settings/notify', SETTINGS_TABS)).toBe('/settings/notify');
  });
  it('主导航：发现区四个入口指向新页面，旧路径归入对应入口', () => {
    expect(activeNavId('/')).toBe('today');
    expect(activeNavId('/hot')).toBe('hot');
    expect(activeNavId('/reports/periods/3')).toBe('reports');
    expect(activeNavId('/daily')).toBe('reports');
    expect(activeNavId('/dossiers/2')).toBe('topics');
    expect(activeNavId('/items/9')).toBe('today');
    expect(activeNavId('/admin/contents')).toBe('sources');
    expect(activeNavId('/settings/scoring')).toBe('settings');
    expect(activeNavId('/admin/model-eval')).toBe('settings');
  });
});
