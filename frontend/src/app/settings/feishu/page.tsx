'use client';

/** 设置 · 飞书（改造方案 10.2）：自建应用凭证、多维表格链接、字段映射、自动写入。单向写入，飞书里的修改不回写。 */

import { ScanSkeleton } from '@/design/instrument';
import { AutoComplete, Input, Switch, message } from 'antd';
import { useEffect, useState } from 'react';
import { Button, Card } from '@/design/components';
import { feishuApi, type FeishuSettings } from '@/lib/api/_feishu';

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

export default function FeishuSettingsPage() {
  const [s, setS] = useState<FeishuSettings | null>(null);
  const [appId, setAppId] = useState('');
  const [secret, setSecret] = useState('');
  const [url, setUrl] = useState('');
  const [map, setMap] = useState<Record<string, string>>({});
  const [columns, setColumns] = useState<string[]>([]);
  const [missing, setMissing] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const apply = (v: FeishuSettings) => {
    setS(v);
    setAppId(v.app_id);
    setUrl(v.table_url);
    setMap(v.field_map);
  };
  useEffect(() => {
    feishuApi
      .settings()
      .then(apply)
      .catch((err) => message.error(errText(err)));
  }, []);
  const save = async (extra: Partial<FeishuSettings> = {}) => {
    setBusy('save');
    try {
      apply(await feishuApi.save({ app_id: appId, table_url: url, field_map: map, ...(secret ? { app_secret: secret } : {}), ...extra }));
      setSecret('');
      message.success('已保存');
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(null);
    }
  };
  const test = async () => {
    setBusy('test');
    try {
      const r = await feishuApi.test();
      setColumns(r.fields.map((f) => f.name));
      setMissing(r.missing.map((m) => m.column));
      if (r.missing.length) message.warning(`连接正常，表格里没有这些列：${r.missing.map((m) => m.column).join('、')}`);
      else message.success(`连接正常，表格有 ${r.fields.length} 列，映射都对得上`);
      feishuApi.settings().then(apply).catch(() => {});
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(null);
    }
  };
  const setupColumns = async () => {
    setBusy('setup');
    try {
      const r = await feishuApi.setupColumns();
      const parts = [r.renamed ? `首列已改名（${r.renamed}）` : '', r.created.length ? `新建了 ${r.created.length} 列：${r.created.join('、')}` : ''].filter(Boolean);
      message.success(parts.length ? parts.join('；') : '表格里的列都已经齐了');
      await test();
    } catch (err) {
      message.error(errText(err));
      setBusy(null);
    }
  };
  if (!s) return <ScanSkeleton shape="form" height={120} />;
  return (
    <div className="cw-stack">
      <Card title="飞书多维表格" extra={s.configured ? <small className="cw-muted">已连接 · {s.table_id}</small> : <small className="cw-muted">未连接</small>}>
        <div className="cw-brief">
          <label>
            <span>App ID</span>
            <Input value={appId} onChange={(e) => setAppId(e.target.value)} placeholder="cli_…" />
          </label>
          <label>
            <span>App Secret{s.has_secret ? '（已保存，留空不改）' : ''}</span>
            <Input.Password value={secret} onChange={(e) => setSecret(e.target.value)} autoComplete="off" />
          </label>
          <label className="cw-brief-wide">
            <span>表格链接（打开要写入的数据表后复制浏览器地址）</span>
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://xxx.feishu.cn/base/…?table=tbl…" />
          </label>
        </div>
        <div className="cw-row" style={{ marginTop: 12 }}>
          <Button data-variant="primary" onClick={() => save()} disabled={busy !== null}>
            {busy === 'save' ? '保存中…' : '保存'}
          </Button>
          <Button onClick={test} disabled={busy !== null || !s.configured && !s.table_id}>
            {busy === 'test' ? '测试中…' : '测试连接'}
          </Button>
        </div>
        <p className="cw-muted" style={{ fontSize: 12 }}>
          步骤：① 飞书开放平台 open.feishu.cn →「创建企业自建应用」，在「凭证与基础信息」复制 App ID / App Secret；② 「权限管理」开通「查看、评论、编辑和管理多维表格」（表格在知识库里还要开「查看知识库」），然后「创建版本」并发布；③ 回到这张表格，右上角「…→ 添加文档应用」加上这个应用；④ 这里填好保存，点「测试连接」。Secret 加密保存在本机。
        </p>
      </Card>
      <Card title="字段映射" extra={<small className="cw-muted">左边是工作台的字段，右边填飞书表格里的列名；留空不写</small>}>
        <div className="cw-brief">
          {s.fields.map((f) => (
            <label key={f.key}>
              <span>
                {f.label}
                {map[f.key] && missing.includes(map[f.key]) ? <em style={{ color: 'var(--cw-rd)', fontStyle: 'normal' }}> · 表格里没有</em> : null}
              </span>
              <AutoComplete
                value={map[f.key] ?? ''}
                options={columns.map((c) => ({ value: c }))}
                onChange={(v) => setMap({ ...map, [f.key]: v })}
                placeholder="不写入"
                allowClear
              />
            </label>
          ))}
        </div>
        <div className="cw-row" style={{ marginTop: 12 }}>
          <Button onClick={() => save()} disabled={busy !== null}>
            保存映射
          </Button>
          <Button onClick={setupColumns} disabled={busy !== null || !s.configured}>
            {busy === 'setup' ? '建列中…' : '在表格里建好这些列'}
          </Button>
        </div>
        <p className="cw-muted" style={{ fontSize: 12 }}>
          链接、日期、数字、单选 / 多选列会按列的类型写入；状态列取值为「未开始 / 创作中 / 已产出」，项目阶段变化时自动更新。
        </p>
      </Card>
      <Card title="自动写入">
        <label className="cw-inline">
          <Switch size="small" checked={s.auto_on_worth} onChange={(v) => void save({ auto_on_worth: v })} /> 结论为「值得做」时自动记入
        </label>
        <label className="cw-inline" style={{ marginTop: 10 }}>
          <Switch size="small" checked={s.auto_on_project} onChange={(v) => void save({ auto_on_project: v })} /> 新建项目时自动记入
        </label>
        <p className="cw-muted" style={{ fontSize: 12 }}>
          只从工作台写到飞书，飞书里的修改不回写。写入失败会出现在任务中心，可以重试。
        </p>
      </Card>
    </div>
  );
}
