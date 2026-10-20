import { describe, expect, it } from 'vitest';
import {
  ADMIN_ONLY_PATHS,
  NAV_SPACES,
  canAccessNavItem,
  canAccessPath,
  isAdmin,
  requiredAccessForPath,
  visibleNavSpaces,
} from '@/lib/navigation';

const user = { id: 1, email: 'a@b.c', role: 'user' } as never;
const admin = { id: 2, email: 'x@b.c', role: 'admin' } as never;

describe('navigation 访问控制', () => {
  it('isAdmin', () => {
    expect(isAdmin(admin)).toBe(true);
    expect(isAdmin(user)).toBe(false);
    expect(isAdmin(null)).toBe(false);
  });
  it('导航项按身份和功能开关过滤', () => {
    const adminItem = NAV_SPACES.flatMap((s) => s.items).find((i) => i.access === 'admin')!;
    const publicItem = NAV_SPACES.flatMap((s) => s.items).find((i) => i.access === 'public')!;
    expect(canAccessNavItem(adminItem, user)).toBe(false);
    expect(canAccessNavItem(adminItem, admin)).toBe(true);
    expect(canAccessNavItem(publicItem, null)).toBe(true);
    expect(canAccessNavItem({ ...publicItem, access: 'user' }, null)).toBe(false);
    expect(canAccessNavItem({ ...publicItem, access: 'user' }, user)).toBe(true);
    expect(canAccessNavItem({ ...publicItem, feature: 'x' }, admin)).toBe(false);
    expect(canAccessNavItem({ ...publicItem, feature: 'x' }, admin, { x: true })).toBe(true);
  });
  it('可见空间：普通用户看不到管理后台，空空间被去掉', () => {
    const forUser = visibleNavSpaces(user).flatMap((s) => s.items.map((i) => i.href));
    const forAdmin = visibleNavSpaces(admin).flatMap((s) => s.items.map((i) => i.href));
    expect(forUser).not.toContain('/admin');
    expect(forAdmin).toContain('/admin');
    expect(visibleNavSpaces(user).every((s) => s.items.length > 0)).toBe(true);
  });
  it('路径访问级别', () => {
    expect(requiredAccessForPath('/')).toBe('public');
    expect(requiredAccessForPath('/admin/sources')).toBe('admin');
    expect(requiredAccessForPath('/no-such')).toBe('public');
    expect(ADMIN_ONLY_PATHS.length).toBeGreaterThan(0);
    expect(canAccessPath('/admin', user)).toBe(false);
    expect(canAccessPath('/admin', admin)).toBe(true);
    expect(canAccessPath('/daily', null)).toBe(true);
  });
});
