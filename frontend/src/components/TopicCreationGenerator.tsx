'use client';

import React from 'react';
import { ArrowRight, Film, PenLine } from 'lucide-react';
import SectionTitle from '@/components/SectionTitle';
import { Button, Panel } from '@/components/ui';

interface TopicCreationGeneratorProps {
  contentId: number;
}

export default function TopicCreationGenerator({ contentId }: TopicCreationGeneratorProps) {
  return (
    <Panel className="mb-5 p-7">
      <SectionTitle>
        <span className="inline-flex items-center gap-2">
          <PenLine size={15} strokeWidth={2} />
          生成创作方案
        </span>
      </SectionTitle>
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <Film size={16} />
          选择模板、视觉风格与输出媒介，生成分镜提示词或 MV 编排。
        </div>
        <Button
          type="button"
          variant="primary"
          onClick={() => { window.location.href = `/studio?content_id=${contentId}`; }}
        >
          打开工作台
          <ArrowRight size={14} />
        </Button>
      </div>
    </Panel>
  );
}
