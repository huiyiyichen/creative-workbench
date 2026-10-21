'use client';

/** 设置 · 公众号：AppID / AppSecret、默认作者与原文链接，用于把「公众号版」直接推到草稿箱。 */

import { ScanSkeleton } from '@/design/instrument';
import { Input, Switch } from 'antd';
import { useEffect, useState } from 'react';
import { Button, Card } from '@/design/components';
import { toast } from '@/design/feedback';
import { wechatApi, type WechatSettings } from '@/lib/api/_wechat';
import { fmtDay, fmtHM } from '@/lib/time-cn';

export default function WechatSettingsPage() {
  const [s, setS] = useState<WechatSettings | null>(null);
  const [appId, setAppId] = useState('');
  const [secret, setSecret] = useState('');
  const [author, setAuthor] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const apply = (v: WechatSettings) => {
    setS(v);
    setAppId(v.app_id);
    setAuthor(v.author);
    setSourceUrl(v.source_url);
  };
  useEffect(() => {
    wechatApi
      .settings()
      .then(apply)
      .catch((err) => toast.error(err));
  }, []);
  const save = async (extra: Partial<WechatSettings> = {}) => {
    setBusy('save');
    try {
      apply(await wechatApi.save({ app_id: appId, author, source_url: sourceUrl, ...(secret ? { app_secret: secret } : {}), ...extra }));
      setSecret('');
      toast.success('已保存');
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(null);
    }
  };
  const test = async () => {
    setBusy('test');
    try {
      toast.success((await wechatApi.test()).message);
      wechatApi.settings().then(apply).catch(() => {});
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(null);
    }
  };
  if (!s) return <ScanSkeleton shape="form" height={120} />;
  return (
    <div className="cw-stack">
      <Card
        title="公众号草稿箱"
        extra={
          <small className="cw-muted">
            <i className="cw-dot" data-tone={s.configured ? (s.last_test ? 'ok' : 'warn') : undefined} style={{ marginRight: 6 }} />
            {s.configured ? (s.last_test ? `已连接 · ${fmtDay(s.last_test)} ${fmtHM(s.last_test)} 测过` : '已填写，还没测试') : '未连接'}
          </small>
        }
      >
        <div className="cw-brief">
          <label>
            <span>AppID</span>
            <Input value={appId} onChange={(e) => setAppId(e.target.value)} placeholder="wx…" />
          </label>
          <label>
            <span>AppSecret{s.has_secret ? '（已保存，留空不改）' : ''}</span>
            <Input.Password value={secret} onChange={(e) => setSecret(e.target.value)} autoComplete="off" />
          </label>
          <label>
            <span>默认作者（最多 16 字）</span>
            <Input value={author} maxLength={16} onChange={(e) => setAuthor(e.target.value)} />
          </label>
          <label>
            <span>阅读原文链接（可空）</span>
            <Input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://…" />
          </label>
        </div>
        <div className="cw-row" style={{ marginTop: 12 }}>
          <Button variant="primary" onClick={() => save()} disabled={busy !== null}>
            {busy === 'save' ? '保存中…' : '保存'}
          </Button>
          <Button onClick={test} disabled={busy !== null || !s.configured}>
            {busy === 'test' ? '测试中…' : '测试连接'}
          </Button>
          <span className="cw-grow" />
          <label className="cw-inline">
            <Switch size="small" checked={s.open_comment} onChange={(v) => void save({ open_comment: v })} /> 默认打开留言
          </label>
        </div>
        <p className="cw-muted" style={{ fontSize: 12 }}>
          在公众号后台「设置与开发 → 基本配置」拿 AppID 和 AppSecret，并把这台机器的出口 IP 加进 IP 白名单。草稿箱接口需要认证过的公众号。Secret 加密保存在本机。
        </p>
      </Card>
      <Card title="推送时会做什么">
        <ol className="cw-muted" style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.9 }}>
          <li>正文里的图片逐张传到微信图床，换成微信能显示的链接（读不到的图会跳过并告诉你）。</li>
          <li>封面用项目素材里角色为「封面」的图；没有就按标题生成一张。</li>
          <li>写进草稿箱后，去公众号后台检查排版再群发；产出物状态变为「已导出」。</li>
        </ol>
      </Card>
    </div>
  );
}
