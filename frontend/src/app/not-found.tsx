import Link from 'next/link';
import { Fallback, HomeLink } from '@/design/fallback';

export default function NotFound() {
  return (
    <div className="cw-page">
      <Fallback
        code="404"
        title="没有这个页面"
        actions={
          <>
            <Link className="cw-btn" data-variant="primary" href="/search">
              去搜索
            </Link>
            <HomeLink />
          </>
        }
      >
        <p>链接可能过期了，或者内容已经删除。可以搜一下标题或关键词。</p>
      </Fallback>
    </div>
  );
}
