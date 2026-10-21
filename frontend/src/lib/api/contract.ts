/**
 * 前端手写类型与后端 OpenAPI 生成类型（schema.d.ts）的对账。
 *
 * 只在编译期起作用：手写接口里出现后端响应 / 请求模型没有的字段时，
 * `npx tsc --noEmit` 会在这里报错，提示字段被后端改名或删掉了。
 * 后端改了接口后：`npm run gen:api:all` 重新生成，再跑 tsc。
 *
 * 新代码优先直接用 `Schema<'名字'>`；这里只对账还在用手写类型的老接口。
 */
import type { components } from './schema';
import type {
  ArticleReaderBlock,
  ArticleReaderSnapshot,
  AuthUser,
  ContentAnalysis,
  ContentItem,
  ContentNormalizationMember,
  ContentNormalizationSummary,
  CreateSourceRequest,
  EvidenceMark,
  FavoriteItem,
  MonthlyDigest,
  MonthlyDigestListResponse,
  MonthlyDigestMonthSummary,
  ScoreBreakdown,
  Source,
  SyncResult,
  TopicInfo,
  UpdateSourceRequest,
  WeeklyDigest,
  WeeklyDigestListResponse,
  WeeklyDigestWeekSummary,
} from '@/types';
import type { TopicGroupResponse } from '@/types/contents';
import type { RSSHubInstance } from '@/types/stats';
import type {
  ContentScoringResult,
  MotherTopic,
  TrendingAngleRecommendation,
  TrendingItem,
  TrendingSource,
} from '@/types/trending';
import type {
  TrendEvidenceCalculation,
  TrendEvidenceDailyCount,
  TrendEvidenceItem,
  TrendEvidenceResponse,
  TrendEvidenceScope,
  TrendEvidenceSummary,
} from '@/types/trends';
import type { WebhookItem, WebhookItemUpdate } from './_analytics';
import type { CopyBrief, Draft, Shot } from './_projects';
import type { ReadRecordReportPayload, ReadRecordResponse } from './_read-records';

/** 后端模型，按 OpenAPI 里的名字取。 */
export type Schema<K extends keyof components['schemas']> = components['schemas'][K];

/** 手写类型里多出、后端模型没有的字段（Extra 是确认过可以多的）。 */
type Missing<Hand, K extends keyof components['schemas'], Extra extends PropertyKey = never> = Exclude<
  keyof Hand,
  keyof Schema<K> | Extra
>;
/** 只接受 never：有多余字段时这里编译报错，错误信息会列出字段名。 */
type Ok<T extends never> = T;

export type ContractChecks = [
  Ok<Missing<AuthUser, 'UserResponse'>>,
  Ok<Missing<Source, 'SourceResponse'>>,
  Ok<Missing<CreateSourceRequest, 'SourceCreate'>>,
  Ok<Missing<UpdateSourceRequest, 'SourceUpdate'>>,
  Ok<Missing<SyncResult, 'SyncResultResponse'>>,
  Ok<Missing<ContentItem, 'ContentResponse'>>,
  Ok<Missing<ContentAnalysis, 'AiAnalysisResponse'>>,
  Ok<Missing<ScoreBreakdown, 'ScoreBreakdownResponse'>>,
  Ok<Missing<ContentNormalizationSummary, 'ContentEventResponse'>>,
  Ok<Missing<ContentNormalizationMember, 'ContentEventMemberResponse'>>,
  Ok<Missing<TopicInfo, 'TopicResponse'>>,
  Ok<Missing<TopicGroupResponse, 'TopicResponse'>>,
  Ok<Missing<ArticleReaderBlock, 'ArticleReaderBlock'>>,
  Ok<Missing<ArticleReaderSnapshot, 'ArticleReaderResponse'>>,
  Ok<Missing<EvidenceMark, 'TrendEvidenceMarkResponse'>>,
  Ok<Missing<FavoriteItem, 'FavoriteResponse'>>,
  Ok<Missing<WeeklyDigest, 'WeeklyDigestResponse'>>,
  Ok<Missing<WeeklyDigestWeekSummary, 'WeeklyDigestWeekSummary'>>,
  Ok<Missing<WeeklyDigestListResponse, 'WeeklyDigestListResponse'>>,
  Ok<Missing<MonthlyDigest, 'MonthlyDigestResponse'>>,
  Ok<Missing<MonthlyDigestMonthSummary, 'MonthlyDigestMonthSummary'>>,
  Ok<Missing<MonthlyDigestListResponse, 'MonthlyDigestListResponse'>>,
  Ok<Missing<RSSHubInstance, 'RSSHubInstanceItem'>>,
  Ok<Missing<TrendingItem, 'TrendingItemOut'>>,
  Ok<Missing<TrendingSource, 'TrendingSourceInfo'>>,
  Ok<Missing<TrendingAngleRecommendation, 'AngleRecommendOut'>>,
  Ok<Missing<MotherTopic, 'MotherTopicOut'>>,
  Ok<Missing<ContentScoringResult, 'ContentScoringResult'>>,
  Ok<Missing<TrendEvidenceScope, 'TrendEvidenceScopeResponse'>>,
  Ok<Missing<TrendEvidenceSummary, 'TrendEvidenceSummaryResponse'>>,
  Ok<Missing<TrendEvidenceCalculation, 'TrendEvidenceCalculationResponse'>>,
  Ok<Missing<TrendEvidenceDailyCount, 'TrendEvidenceDailyCountResponse'>>,
  Ok<Missing<TrendEvidenceItem, 'TrendEvidenceItemResponse'>>,
  Ok<Missing<TrendEvidenceResponse, 'TrendEvidenceResponse'>>,
  Ok<Missing<WebhookItem, 'WebhookItemResponse'>>,
  Ok<Missing<WebhookItemUpdate, 'WebhookItemUpdateRequest'>>,
  Ok<Missing<CopyBrief, 'CopyBrief'>>,
  Ok<Missing<Shot, 'StudioShot'>>,
  Ok<Missing<Draft, 'StudioDraft'>>,
  Ok<Missing<ReadRecordReportPayload, 'ReadRecordReport'>>,
  Ok<Missing<ReadRecordResponse, 'ReadRecordResponse'>>,
];
