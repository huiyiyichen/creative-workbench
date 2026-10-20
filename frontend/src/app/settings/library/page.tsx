'use client';

/** 设置 · 灵感库：素材收件箱（6.2）、旧收藏夹迁移、浏览器扩展说明（6.3）。 */

import { Input, message } from 'antd';
import { useEffect, useState } from 'react';
import { Button, Card } from '@/design/components';
import { libraryApi } from '@/lib/api/_library';

const MIGRATE_LABEL: Record<string, string> = {
  library: '灵感库条目',
  dossiers: '专题',
  templates: '内容模板',
  styles: '视觉风格',
  sources: '信源',
  skipped: '跳过',
};

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

export default function LibrarySettingsPage() {
  const [path, setPath] = useState('');
  const [importedDir, setImportedDir] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [migrated, setMigrated] = useState<Record<string, number> | null>(null);
  const [ping, setPing] = useState<'ok' | 'bad' | null>(null);

  useEffect(() => {
    libraryApi
      .inbox()
      .then((r) => {
        setPath(r.path || '');
        setImportedDir(r.imported_dir);
      })
      .catch((err) => message.error(errText(err)));
    libraryApi
      .extensionPing()
      .then(() => setPing('ok'))
      .catch(() => setPing('bad'));
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
      <Card title="素材收件箱">
        <p className="cw-muted">把文件丢进这个文件夹，每 2 分钟自动导入灵感库，导入后移到「{importedDir || '已导入'}」子文件夹。留空表示不启用。</p>
        <div className="cw-row">
          <Input value={path} onChange={(e) => setPath(e.target.value)} placeholder="例如 D:\素材收件箱" style={{ maxWidth: 420 }} aria-label="收件箱路径" />
          <Button
            variant="primary"
            disabled={busy !== null}
            onClick={() =>
              run('save', async () => {
                const r = await libraryApi.setInbox(path.trim() || null);
                setPath(r.path || '');
                message.success(r.path ? '已保存' : '已停用收件箱');
              })
            }
          >
            保存
          </Button>
          <Button
            disabled={busy !== null || !path}
            onClick={() =>
              run('scan', async () => {
                const r = await libraryApi.scanInbox();
                message.success(`导入 ${r.imported} 个${r.failed ? `，失败 ${r.failed} 个` : ''}`);
              })
            }
          >
            立即扫描
          </Button>
        </div>
      </Card>

      <Card title="浏览器扩展">
        <p className="cw-muted">
          Edge / Chrome 扩展在网页右键「存到灵感库」，可存整页、链接、图片或选中文字。扩展在仓库的 <code>extension/</code> 目录：
          打开 edge://extensions，开启开发人员模式，选「加载解压缩的扩展」并选择该目录。
        </p>
        <p>
          本机服务：{ping === null ? '检测中…' : ping === 'ok' ? <span className="cw-ok">可连接</span> : <span className="cw-error">连不上，请确认后端已启动</span>}
        </p>
      </Card>

      <Card title="旧收藏夹迁移">
        <p className="cw-muted">把旧收藏夹里的条目搬进灵感库，模板和风格进「风格与模板」，专题和信源归位。可以重复运行，已搬过的会跳过。</p>
        <Button
          disabled={busy !== null}
          onClick={() =>
            run('migrate', async () => {
              setMigrated(await libraryApi.migrateFavorites());
            })
          }
        >
          {busy === 'migrate' ? '迁移中…' : '开始迁移'}
        </Button>
        {migrated ? (
          <p>
            {Object.entries(migrated)
              .map(([k, v]) => `${MIGRATE_LABEL[k] || k} ${v}`)
              .join(' · ')}
          </p>
        ) : null}
      </Card>
    </div>
  );
}
