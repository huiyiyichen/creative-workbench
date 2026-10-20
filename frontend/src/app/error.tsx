'use client';

import { useEffect } from 'react';
import { Fallback, HomeLink, useBackendState } from '@/design/fallback';

export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const [backend, recheck] = useBackendState();
  useEffect(() => {
    console.error(error);
  }, [error]);
  const down = backend === 'down';
  return (
    <div className="cw-page">
      <Fallback
        code={down ? '后端' : '出错'}
        title={down ? '连不上工作台后端' : '这一页出了点问题'}
        actions={
          <>
            <button
              type="button"
              className="cw-btn"
              data-variant="primary"
              onClick={() => {
                recheck();
                reset();
              }}
            >
              重试
            </button>
            <HomeLink />
          </>
        }
      >
        {down ? (
          <p>确认工作台后台在运行（Windows 托盘里有图标；开发时是 8000 端口的 uvicorn），再点重试。已经写好的内容都保存在本机，不会丢。</p>
        ) : (
          <p>
            {backend === 'checking' ? '正在检查后端…' : '后端是通的，可能是这一页的数据格式不对。'}
            {error.message ? <code className="cw-fallback-detail">{error.message.slice(0, 300)}</code> : null}
            {error.digest ? <small className="cw-muted cw-num"> 编号 {error.digest}</small> : null}
          </p>
        )}
      </Fallback>
    </div>
  );
}
