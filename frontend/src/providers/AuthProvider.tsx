'use client';

import React, { createContext, useContext, useEffect, useRef } from 'react';
import { useStore } from 'zustand';
import type { AuthUser } from '@/types';
import { createAuthStore, type AuthStore, type AuthState, type AuthContextType } from '@/stores/authStore';

// ── Context: holds the per-instance store ─────────────────────

const AuthStoreContext = createContext<AuthStore | null>(null);
const FALLBACK_LOCAL_USER: AuthUser = {
  id: 0,
  email: 'local@topiceye.local',
  display_name: '本地创作者',
  plan: 'local',
  role: 'admin',
  is_active: true,
  created_at: new Date(0).toISOString(),
};

// ── Hooks ─────────────────────────────────────────────────────

/**
 * 细粒度 selector hook（新代码推荐使用）。
 * 只在选中的 state slice 变化时 re-render。
 *
 * @example
 * const currentUser = useAuthStore(s => s.currentUser);
 * const logout = useAuthStore(s => s.logout);
 */
export function useAuthStore<T>(selector: (s: AuthState) => T): T {
  const store = useContext(AuthStoreContext);
  if (!store) throw new Error('useAuthStore must be used within AuthProvider');
  return useStore(store, selector);
}

/**
 * 向后兼容 hook：订阅整个 auth store（与原 useContext(AuthContext) 行为一致）。
 * 38 个现有消费者通过 useAppContext() 间接使用，无需改动。
 */
export function useAuthContext(): AuthContextType {
  const store = useContext(AuthStoreContext);
  if (!store) throw new Error('useAuthContext must be used within AuthProvider');
  return useStore(store);
}

/**
 * 获取 AuthStore 实例（非响应式，用于跨 store 依赖注入）。
 * 仅在 Provider 内部使用。
 */
export function useAuthStoreApi(): AuthStore {
  const store = useContext(AuthStoreContext);
  if (!store) throw new Error('useAuthStoreApi must be used within AuthProvider');
  return store;
}

// ── Provider ──────────────────────────────────────────────────

export function AuthProvider({
  children,
  initialUser = null,
  initialFeatureFlags,
}: {
  children: React.ReactNode;
  initialUser?: AuthUser | null;
  initialFeatureFlags?: Record<string, boolean>;
}) {
  const localUser = initialUser ?? FALLBACK_LOCAL_USER;

  // per-instance store（useRef 保证 SSR 安全：每个请求/组件实例独立 store）
  const storeRef = useRef<AuthStore | null>(null);
  if (!storeRef.current) {
    storeRef.current = createAuthStore({
      user: localUser,
      featureFlags: initialFeatureFlags,
    });
  }
  const store = storeRef.current;

  // 读取响应式 state（用于路由守卫 effect）
  const authLoading = useStore(store, (s) => s.authLoading);
  const featuresLoading = useStore(store, (s) => s.featuresLoading);
  const currentUser = useStore(store, (s) => s.currentUser);
  const enabledFeatures = useStore(store, (s) => s.enabledFeatures);

  useEffect(() => {
    store.setState({
      currentUser: localUser,
      authLoading: false,
      featuresLoading: false,
      enabledFeatures: initialFeatureFlags ?? {},
    });
  }, [store, localUser, initialFeatureFlags]);

  return <AuthStoreContext.Provider value={store}>{children}</AuthStoreContext.Provider>;
}

// Re-export types for backward compat
export type { AuthContextType };
