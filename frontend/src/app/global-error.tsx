'use client';

/** 根布局本身崩了时的最后兜底：不依赖任何样式文件和组件。 */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="zh-CN">
      <body style={{ margin: 0, minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#111418', color: '#e7e9ec', fontFamily: 'system-ui, sans-serif' }}>
        <div style={{ maxWidth: 480, padding: 24 }}>
          <h1 style={{ fontSize: 22, margin: '0 0 12px' }}>工作台没能打开</h1>
          <p style={{ color: '#9aa3ad', lineHeight: 1.6, margin: '0 0 20px' }}>界面加载时出错了。点重试；还不行就重启工作台。{error.digest ? ` 编号 ${error.digest}` : ''}</p>
          <button type="button" onClick={reset} style={{ background: '#f4f5f6', color: '#111418', border: 0, borderRadius: 8, padding: '8px 18px', fontSize: 14, cursor: 'pointer' }}>
            重试
          </button>
        </div>
      </body>
    </html>
  );
}
