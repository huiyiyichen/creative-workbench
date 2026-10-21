/** 路由切换时的占位：只有页头一行，不猜版式（各页数据加载时自己画按版式的骨架）。 */
export default function Loading() {
  return (
    <div className="cw-page cw-skeleton" aria-busy="true" aria-live="polite">
      <span className="cw-sr-only">加载中</span>
      <div className="cw-skel cw-skel-title" />
    </div>
  );
}
