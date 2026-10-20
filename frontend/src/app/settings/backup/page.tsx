'use client';

/** 设置 · 备份：一键备份数据库与素材目录、下载、删除；每周日 03:30 自动备份，保留最近 10 份。 */

import { Switch } from 'antd';
import { Download, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card } from '@/design/components';
import { confirmAction, toast } from '@/design/feedback';
import { backupsApi, fmtBytes, type BackupItem } from '@/lib/api/_backups';
import { fmtDay, fmtHM } from '@/lib/time-cn';

const FILE_LABEL: Record<string, string> = { library: '灵感库', favorites: '收藏媒体', generations: '生成结果', studio: '项目媒体', traces: '运行追踪' };

export default function BackupSettingsPage() {
  const [items, setItems] = useState<BackupItem[] | null>(null);
  const [keep, setKeep] = useState(10);
  const [root, setRoot] = useState('');
  const [files, setFiles] = useState(true);
  const load = useCallback(() => {
    backupsApi
      .list()
      .then((r) => {
        setItems(r.items);
        setKeep(r.keep);
        setRoot(r.root);
      })
      .catch((err) => toast.error(err));
  }, []);
  useEffect(load, [load]);
  const running = items?.some((b) => b.status === 'running');
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [running, load]);
  return (
    <div className="cw-stack">
      <Card title="一键备份" extra={<small className="cw-muted">每周日 03:30 自动备份 · 保留最近 {keep} 份</small>}>
        <div className="cw-row">
          <Button
            variant="primary"
            disabled={Boolean(running)}
            onClick={async () => {
              try {
                await backupsApi.create(files);
                load();
              } catch (err) {
                toast.error(err, '备份失败');
              }
            }}
          >
            {running ? '备份中…' : '现在备份'}
          </Button>
          <label className="cw-inline">
            <Switch size="small" checked={files} onChange={setFiles} /> 连同素材文件（灵感库、生成结果、项目媒体）
          </label>
        </div>
        <p className="cw-muted" style={{ fontSize: 12 }}>
          备份存在本机 <code>{root}</code>。还原要先停掉后端，再在 backend 目录运行 <code>uv run python scripts/restore_backup.py 备份文件 --files</code>。
        </p>
      </Card>
      <Card title="备份记录">
        {items === null ? (
          <p className="cw-muted">加载中…</p>
        ) : items.length === 0 ? (
          <p className="cw-muted">还没有备份。</p>
        ) : (
          <table className="cw-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>状态</th>
                <th>内容</th>
                <th className="cw-num-col">大小</th>
                <th className="cw-num-col">耗时</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((b) => (
                <tr key={b.name}>
                  <td className="cw-num">
                    {fmtDay(b.created_at)} {fmtHM(b.created_at)}
                  </td>
                  <td>
                    <i className="cw-dot" data-tone={b.status === 'done' ? 'ok' : b.status === 'failed' ? 'bad' : 'warn'} style={{ marginRight: 6 }} />
                    {b.status === 'done' ? '完成' : b.status === 'failed' ? <span title={b.error}>失败：{b.error}</span> : '进行中'}
                  </td>
                  <td className="cw-muted">
                    {b.db_format === 'pg_dump' ? '数据库（pg_dump）' : b.db_format === 'jsonl' ? '数据库（逐表导出）' : '数据库'}
                    {b.files && b.files.length ? ` + ${b.files.map((f) => FILE_LABEL[f] || f).join('、')}` : ''}
                  </td>
                  <td className="cw-num cw-num-col">{fmtBytes(b.size)}</td>
                  <td className="cw-num cw-num-col">{b.seconds !== undefined ? `${b.seconds} 秒` : '—'}</td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    {b.status === 'done' ? (
                      <a className="cw-btn" data-size="icon" href={backupsApi.downloadUrl(b.name)} aria-label="下载" title="下载">
                        <Download size={14} />
                      </a>
                    ) : null}
                    {b.status !== 'running' ? (
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="删除"
                        title="删除"
                        onClick={async () => {
                          if (!(await confirmAction({ title: '删除这份备份？', content: b.name, okText: '删除', danger: true }))) return;
                          try {
                            await backupsApi.remove(b.name);
                            load();
                          } catch (err) {
                            toast.error(err);
                          }
                        }}
                      >
                        <Trash2 size={14} />
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
