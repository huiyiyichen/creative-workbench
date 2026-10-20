/** 站内通知：按类别推导跳转目标与颜色（纯函数，便于测试）。 */

export interface NotifyLike {
  type: string;
  category: string;
  title: string;
  message: string;
}

/** 通知正文里带了 /runs/123 这类路径就直接用；否则按类别跳到对应页面。 */
export function notifyHref(n: NotifyLike): string | null {
  const m = /\/(runs|projects|items)\/\d+/.exec(n.message);
  if (m) return m[0];
  switch (n.category) {
    case 'daily_report':
      return '/daily';
    case 'weekly_digest':
    case 'weekly':
      return '/weekly';
    case 'monthly_digest':
    case 'monthly':
      return '/monthly';
    case 'collection':
      return '/sources';
    case 'flow':
      return '/tasks';
    case 'project':
      return '/projects';
    default:
      return null;
  }
}

export function notifyColor(type: string): string {
  if (type === 'error') return 'var(--cw-rd)';
  if (type === 'warning' || type === 'auto_action') return 'var(--cw-yl)';
  if (type === 'success') return 'var(--cw-gr)';
  return 'var(--cw-cy)';
}
