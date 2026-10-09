'use client';

import {useEffect, useState} from 'react';
import {Button, Form, Input, Modal, Space, Tag, message} from 'antd';
import {Settings2, Volume2} from 'lucide-react';
import {BASE_URL, formatApiErrorDetail, request} from '@/lib/api/_core';

type VoiceSettings = {
  configured: boolean;
  base_url: string;
  websocket_url: string;
  model: string;
  voice: string;
};

export default function StudioVoice() {
  const [settings, setSettings] = useState<VoiceSettings>();
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState('');
  const [voice, setVoice] = useState('');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState('');
  useEffect(() => {
    let active = true;
    void request<VoiceSettings>('/studio/tts').then((value) => {
      if (active) {setSettings(value); setVoice(value.voice);}
    }).catch(() => {});
    return () => {active = false;};
  }, []);
  useEffect(() => () => {if (preview) URL.revokeObjectURL(preview);}, [preview]);
  const save = async () => {
    setBusy(true);
    try {
      const next = await request<VoiceSettings>('/studio/tts', {
        method: 'PUT', body: JSON.stringify({api_key: key || undefined, voice}),
      });
      setSettings(next); setKey(''); setOpen(false);
      message.success('配音设置已保存');
    } catch (error) {message.error(error instanceof Error ? error.message : '保存失败');}
    finally {setBusy(false);}
  };
  const audition = async () => {
    setBusy(true);
    try {
      const response = await fetch(`${BASE_URL}/studio/tts/preview`, {method: 'POST'});
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || formatApiErrorDetail(error.detail) || '试听失败');
      }
      setPreview(URL.createObjectURL(await response.blob()));
    } catch (error) {message.error(error instanceof Error ? error.message : '试听失败');}
    finally {setBusy(false);}
  };
  return <div className="mb-5 border-y border-gray-100 py-3">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Space wrap><span className="font-semibold">配音</span><Tag>{settings?.model ?? '千问 TTS'}</Tag><span className="text-sm text-gray-500">{settings?.voice || '默认音色'}</span></Space>
      <Space>
        <Button icon={<Volume2 size={15}/>} loading={busy} disabled={!settings?.configured} onClick={() => void audition()}>试听</Button>
        <Button aria-label="配音设置" title="配音设置" icon={<Settings2 size={15}/>} onClick={() => setOpen(true)}/>
      </Space>
    </div>
    {preview && <audio controls autoPlay src={preview} className="mt-3 w-full"/>}
    <Modal title="配音设置" open={open} onCancel={() => {setOpen(false); setKey('');}} onOk={() => void save()} confirmLoading={busy} okText="保存" cancelText="取消">
      <Form layout="vertical">
        <Form.Item label="模型"><Input value={settings?.model ?? 'qwen-audio-3.1-tts-flash'} readOnly/></Form.Item>
        <Form.Item label="接口"><Input value={settings?.base_url} readOnly/></Form.Item>
        <Form.Item label="API Key"><Input.Password value={key} autoComplete="off" placeholder={settings?.configured ? '已配置' : '输入密钥'} onChange={(event) => setKey(event.target.value)}/></Form.Item>
        <Form.Item label="音色 ID"><Input value={voice} placeholder="默认音色" onChange={(event) => setVoice(event.target.value)}/></Form.Item>
      </Form>
    </Modal>
  </div>;
}
