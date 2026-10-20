'use client';

/**
 * 统一的提示与确认：
 * - 静态 message / Modal / notification 统一套上调色台主题（useStaticTheme，在 AppShell 里调用一次）；
 * - confirmAction 代替 window.confirm，toast 代替 alert；
 * - toastUndo：先执行、给几秒撤销（删除类操作优先用它，而不是先弹确认）。
 */

import { ConfigProvider, Modal, message } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useEffect, type ReactNode } from 'react';
import { cwAntdThemeFor } from './antd-theme';
import type { CwTheme } from './tokens';

export function useStaticTheme(mode: CwTheme) {
  useEffect(() => {
    ConfigProvider.config({
      holderRender: (children) => (
        <ConfigProvider theme={cwAntdThemeFor(mode)} locale={zhCN} button={{ autoInsertSpace: false }}>
          {children}
        </ConfigProvider>
      ),
    });
  }, [mode]);
}

export function confirmAction(opts: {
  title: ReactNode;
  content?: ReactNode;
  okText?: string;
  cancelText?: string;
  danger?: boolean;
}): Promise<boolean> {
  return new Promise((resolve) => {
    Modal.confirm({
      title: opts.title,
      content: opts.content,
      okText: opts.okText ?? (opts.danger ? '删除' : '确定'),
      cancelText: opts.cancelText ?? '取消',
      okButtonProps: opts.danger ? { danger: true } : undefined,
      className: 'cw-confirm',
      centered: true,
      autoFocusButton: opts.danger ? 'cancel' : 'ok',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    });
  });
}

export function errorText(err: unknown, fallback = '操作失败'): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === 'string' && err) return err;
  return fallback;
}

export const toast = {
  success: (text: ReactNode) => message.success(text),
  info: (text: ReactNode) => message.info(text),
  warning: (text: ReactNode) => message.warning(text),
  error: (err: unknown, prefix?: string) => message.error(prefix ? `${prefix}：${errorText(err)}` : errorText(err)),
};

/** 先做、后悔可撤：返回 Promise，在提示消失前点「撤销」会调用 undo。 */
export function toastUndo(text: ReactNode, undo: () => void | Promise<void>, seconds = 6) {
  const key = `undo-${Date.now()}`;
  message.open({
    key,
    type: 'success',
    duration: seconds,
    content: (
      <span className="cw-undo">
        {text}
        <button
          type="button"
          className="cw-link-btn"
          onClick={async () => {
            message.destroy(key);
            try {
              await undo();
              message.info('已撤销');
            } catch (err) {
              message.error(errorText(err, '撤销失败'));
            }
          }}
        >
          撤销
        </button>
      </span>
    ),
  });
}
