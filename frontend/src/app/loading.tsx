/** 路由切换时的骨架：标题 + 几行占位，避免整页白闪。 */
export default function Loading() {
  return (
    <div className="cw-page cw-skeleton" aria-busy="true" aria-live="polite">
      <span className="cw-sr-only">加载中</span>
      <div className="cw-skel cw-skel-title" />
      <div className="cw-skel cw-skel-bar" />
      {[0, 1, 2, 3, 4].map((i) => (
        <div key={i} className="cw-skel cw-skel-row" style={{ width: `${92 - i * 9}%` }} />
      ))}
    </div>
  );
}
