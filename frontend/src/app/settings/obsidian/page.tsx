'use client';

/** 设置 · Obsidian（6.8）：vault 路径、工作台地址（写进笔记的回链）、立即同步。工作台每分钟自动同步一次。 */

import { Input, message } from 'antd';
import { useEffect, useState } from 'react';
import { Button, Card } from '@/design/components';
import { libraryApi, type ObsidianSettings } from '@/lib/api/_library';
import { parseUTC } from '@/lib/datetime';

const STAT_LABEL: Record<string, string> = {
  items: '条目',
  days: '随笔日',
  topics: '主题页',
  reports: '报告',
  written: '写出文件',
  items_read: '读回条目',
  notes_updated: '随笔更新',
  notes_created: '新随笔',
  files_read: '新笔记',
};

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

export default function ObsidianSettingsPage() {
  const [settings, setSettings] = useState<ObsidianSettings | null>(null);
  const [vault, setVault] = useState('');
  const [appUrl, setAppUrl] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [stats, setStats] = useState<Record<string, number | boolean> | null>(null);

  const apply = (s: ObsidianSettings) => {
    setSettings(s);
    setVault(s.vault || '');
    setAppUrl(s.app_url);
  };

  useEffect(() => {
    libraryApi
      .obsidian()
      .then(apply)
      .catch((err) => message.error(errText(err)));
  }, []);

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    try {
      await fn();
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="cw-stack">
      <Card title="Obsidian vault">
        <p className="cw-muted">
          工作台写入 vault 里的「创意工作台/」：收藏、素材、提示词、仓库、随笔、项目、主题、报告。结构化字段、摘要和关联归工作台；「我的笔记」、随笔正文和你手写的双链归你，两边各改各的。每分钟自动同步一次。
        </p>
        <div className="cw-row" style={{ marginBottom: 8 }}>
          <Input value={vault} onChange={(e) => setVault(e.target.value)} placeholder="例如 D:\Obsidian\我的库" style={{ maxWidth: 420 }} aria-label="vault 路径" />
        </div>
        <div className="cw-row">
          <Input value={appUrl} onChange={(e) => setAppUrl(e.target.value)} placeholder="http://localhost:3000" style={{ maxWidth: 420 }} aria-label="工作台地址" />
          <span className="cw-muted">笔记里「工作台」链接用这个地址</span>
        </div>
        <div className="cw-row" style={{ marginTop: 12 }}>
          <Button
            variant="primary"
            disabled={busy !== null}
            onClick={() =>
              run('save', async () => {
                apply(await libraryApi.setObsidian(vault.trim() || null, appUrl));
                message.success(vault.trim() ? '已保存' : '已停用同步');
              })
            }
          >
            保存
          </Button>
          <Button
            disabled={busy !== null || !settings?.vault}
            onClick={() =>
              run('sync', async () => {
                setStats(await libraryApi.obsidianSync());
                apply(await libraryApi.obsidian());
              })
            }
          >
            {busy === 'sync' ? '同步中…' : '立即同步'}
          </Button>
          {settings?.last_sync ? <span className="cw-muted">上次同步 {parseUTC(settings.last_sync).toLocaleString('zh-CN', { hour12: false })}</span> : null}
        </div>
        {stats ? (
          <p className="cw-num" style={{ marginTop: 10 }}>
            {Object.entries(stats)
              .filter(([k]) => k in STAT_LABEL)
              .map(([k, v]) => `${STAT_LABEL[k]} ${v}`)
              .join(' · ')}
          </p>
        ) : null}
      </Card>
      <Card title="在 Obsidian 里">
        <ul className="cw-report-list">
          <li>在条目笔记的「## 我的笔记」下写字、加 [[双链]]，或改 frontmatter 的 tags，会读回工作台</li>
          <li>在「随笔/日期.md」里加一个「## 时:分」小节，会成为一条新随笔</li>
          <li>在「创意工作台/」根目录新建的笔记，会作为随笔进入灵感库</li>
          <li>工作台条目详情里点「在 Obsidian 打开」直接跳到对应笔记</li>
        </ul>
      </Card>
    </div>
  );
}
