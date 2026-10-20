/** 花费总览（后端 /costs/summary）。 */
import { request } from './_core';

export interface CostBucket {
  key: string;
  label: string;
  cost: number;
  count: number;
  group?: string;
  tokens_in?: number;
  tokens_out?: number;
}

export interface CostProject {
  id: number;
  title: string;
  cost: number;
  llm: number;
  generation: number;
}

export interface CostDay {
  date: string;
  total: number;
  [group: string]: number | string;
}

export interface CostSummary {
  days: number;
  start: string;
  end: string;
  total: number;
  llm: number;
  generation: number;
  today: number;
  avg_7d: number | null;
  calls: number;
  jobs: number;
  failed: number;
  unpriced_jobs: number;
  tokens_in: number;
  tokens_out: number;
  analysis_budget: { budget: number; spent: number; remaining: number };
  series: CostDay[];
  groups: CostBucket[];
  scenes: CostBucket[];
  models: CostBucket[];
  projects: CostProject[];
}

export const costsApi = {
  summary(days = 30): Promise<CostSummary> {
    return request(`/costs/summary?days=${days}`);
  },
};
