'use client';

/** 设置 · 工作台工具（改造方案 2.1 / 2.2）：第一批工具清单；给外部 agent（Claude Code / Codex）发放限定范围的 MCP 令牌。 */

import { Input, InputNumber, Select, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card } from '@/design/components';
import { runsApi, type WorkbenchTool, type WorkbenchToken } from '@/lib/api/_runs';

export default function WorkbenchSettingsPage() {
  const [tools, setTools] = useState<WorkbenchTool[]>([]);
  const [path, setPath] = useState('/api/v1/mcp');
  const [tokens, setTokens] = useState<WorkbenchToken[]>([]);
  const [label, setLabel] = useState('Claude Code');
  const [allowed, setAllowed] = useState<string[]>([]);
  const [ttl, setTtl] = useState<number>(24);
  const [fresh, setFresh] = useState<WorkbenchToken | null>(null);
  const [origin, setOrigin] = useState('');
  const mcpUrl = (p: string) => `${origin}${p}`;

  const load = useCallback(() => {
    runsApi.tokens().then((r) => setTokens(r.items)).catch(() => setTokens([]));
  }, []);
  useEffect(() => {
    runsApi
      .tools()
      .then((r) => {
        setTools(r.items);
        setPath(r.mcp_path);
      })
      .catch(() => setTools([]));
    load();
    // 浏览器里才知道当前地址；放在 effect 里避免服务端渲染不一致
    setOrigin(window.location.origin);
  }, [load]);

  const create = async () => {
    try {
      const t = await runsApi.createToken({ label, tools: allowed.length ? allowed : null, ttl_hours: ttl || null });
      setFresh(t);
      load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '创建失败');
    }
  };
  const revoke = async (id: number) => {
    await runsApi.revokeToken(id);
    load();
  };
  const config = fresh?.token
    ? JSON.stringify(
        { mcpServers: { 'creative-workbench': { type: 'http', url: mcpUrl(path), headers: { Authorization: `Bearer ${fresh.token}` } } } },
        null,
        2,
      )
    : '';

  return (
    <div className="cw-grid-2">
      <Card title="第一批工具">
        <p className="cw-muted" style={{ marginTop: 0 }}>
          内部角色和外部 agent 都只通过这些工具读写工作台；每次调用都记入运行的调用树。
        </p>
        <ul className="cw-toollist">
          {tools.map((t) => (
            <li key={t.name}>
              <b>{t.title}</b> <code className="cw-muted">{t.name}</code>
              {t.writes ? <span className="cw-chip" style={{ marginLeft: 6 }}>写入</span> : null}
              <div className="cw-muted">{t.description}</div>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="MCP 令牌">
        <p className="cw-muted" style={{ marginTop: 0 }}>
          连接地址 <code>{mcpUrl(path)}</code>（Streamable HTTP）。令牌限定可用工具和有效期，可随时吊销。
        </p>
        <div className="cw-runform">
          <label>
            <span>名称</span>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={100} />
          </label>
          <label>
            <span>可用工具</span>
            <Select
              mode="multiple"
              allowClear
              placeholder="不选 = 全部第一批工具"
              value={allowed}
              onChange={setAllowed}
              options={tools.map((t) => ({ value: t.name, label: t.title }))}
            />
          </label>
          <div className="cw-runform-row">
            <label className="cw-inline">
              有效期 <InputNumber size="small" min={0} max={24 * 90} value={ttl} onChange={(v) => setTtl(Number(v) || 0)} /> 小时（0 = 不过期）
            </label>
            <span className="cw-grow" />
            <Button variant="primary" onClick={create}>
              生成令牌
            </Button>
          </div>
        </div>
        {fresh?.token ? (
          <div className="cw-token-fresh" role="status">
            <p>令牌只显示这一次，复制到外部 agent 的 MCP 配置里：</p>
            <pre className="cw-payload">{config}</pre>
            <Button onClick={() => navigator.clipboard?.writeText(config).then(() => message.success('已复制'))}>复制配置</Button>
          </div>
        ) : null}
        <table className="cw-table" style={{ marginTop: 14 }}>
          <thead>
            <tr>
              <th>名称</th>
              <th>工具</th>
              <th>过期</th>
              <th>最近使用</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {tokens.map((t) => (
              <tr key={t.id}>
                <td>{t.label}</td>
                <td className="cw-muted">{t.tools ? t.tools.join('、') : '全部'}</td>
                <td className="cw-num cw-muted">{t.revoked_at ? '已吊销' : t.expires_at ? new Date(t.expires_at).toLocaleString('zh-CN', { hour12: false }) : '不过期'}</td>
                <td className="cw-num cw-muted">{t.last_used_at ? new Date(t.last_used_at).toLocaleString('zh-CN', { hour12: false }) : '—'}</td>
                <td>{t.revoked_at ? null : <button type="button" className="cw-link-btn" onClick={() => revoke(t.id)}>吊销</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
