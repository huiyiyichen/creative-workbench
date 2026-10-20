'use client';

import { createContext, useContext } from 'react';
import type { OutputView } from '@/lib/api/_projects';

interface OutputsCtx {
  items: OutputView[];
  reload: () => Promise<void>;
}

export const OutputsContext = createContext<OutputsCtx>({ items: [], reload: async () => {} });
export const useOutputs = () => useContext(OutputsContext);
