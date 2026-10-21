'use client';

/** 日报 / 周刊 / 月刊共用的仪器空态（模型没配置 → unplugged + 去配置；其他失败 → 原因 + 重试）。 */
import Link from 'next/link';
import { Loader2, RotateCcw } from 'lucide-react';
import { Button } from './components';
import { EmptyInstrument } from './instrument';

/** 模型没配置 / 生成失败：仪器空态。没配置时不给「重试」（点了也必然失败），只给去配置 */
export const UNPLUGGED = /模型|配置|API ?Key|AI 引擎|未设置|provider/i;

export function ReportEmpty({ message, onRetry, retryLabel, busy, noun = '日报' }: { message: string; onRetry: () => void; retryLabel: string; busy: boolean; noun?: string }) {
  const unplugged = UNPLUGGED.test(message);
  return (
    <EmptyInstrument
      kind={unplugged ? 'unplugged' : 'flat'}
      title={unplugged ? `模型还没配置，${noun}写不出来` : `这一期${noun}没写出来`}
      reason={unplugged ? '日报、选题分析和写稿都要用到语言模型。配好之后回来点「刷新」。' : message}
      actions={
        unplugged ? (
          <Link href="/admin/model-eval" className="cw-btn" data-variant="primary">
            配置模型
          </Link>
        ) : (
          <Button variant="primary" icon={busy ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />} onClick={onRetry} disabled={busy}>
            {retryLabel}
          </Button>
        )
      }
    />
  );
}
