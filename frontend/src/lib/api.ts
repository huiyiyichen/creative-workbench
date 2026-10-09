/**
 * Creative Workbench API Client
 * Backend API wrapper using fetch
 */

import type {
  Source,
  CreateSourceRequest,
  UpdateSourceRequest,
  ContentItem,
  ContentAnalysis,
  TopicFilterParams,
  ContentFilterParams,
  PaginatedResponse,
  SyncResult,
  TopicInfo,
  FavoriteItem,
  FavoriteStatus,
  FavoriteTargetType,
  MonthlyDigest,
  MonthlyDigestListResponse,
  MonthlyDigestMonthsResponse,
  WeeklyDigest,
  WeeklyDigestListResponse,
  WeeklyDigestWeeksResponse,
  AuthUser,
  NotificationListResponse,
} from '@/types';
import type { FavoriteCreatePayload, FavoriteTargetState } from '@/lib/favorites';
import type {
  RSSHubInstance,
  StatsOverview,
  StatsSourceItem,
  StatsCategoryItem,
  StatsTrendItem,
  StatsDashboard,
  JobStatsByStatus,
  JobStatsByJobKey,
  JobStatsRecentFailure,
  JobStatsResponse,
} from '@/types/stats';
import type {
  ContentCategoryItem,
  ScoringFlowStage,
  ScoringFlowSample,
  ScoringFlowDiagnostics,
  ScoringFlowConfig,
  ScoringFlowResponse,
  TopicGroupResponse,
} from '@/types/contents';
import type {
  TrendEvidenceCalculation,
  TrendEvidenceDailyCount,
  TrendEvidenceFilter,
  TrendEvidenceItem,
  TrendEvidenceRequest,
  TrendEvidenceResponse,
  TrendEvidenceScope,
  TrendEvidenceSummary,
  TrendKeywordItem,
  TrendPoint,
  TrendProvenanceStatus,
} from '@/types/trends';
import type {
  IssueFeedbackSeverity,
  IssueFeedbackStatus,
  ProductUpdateKind,
  ProductUpdateStatus,
  IssueFeedbackItem,
  IssueFeedbackListResponse,
  ProductUpdateEntry,
  ProductUpdateItem,
  ProductUpdateListResponse,
} from '@/types/product-feedback';
import type {
  TrendingItem,
  TrendingSource,
  TrendingAngleRecommendation,
  PersistentTopic,
  CrossPlatformSourceItem,
  CrossPlatformCluster,
  MotherTopic,
  MotherTopicMutation,
  ContentScoringResult,
} from '@/types/trending';
import type {
  LlmModelItem,
  LlmModelPresetItem,
  LlmModelPresetCatalog,
  LlmModelCreatePayload,
  EvalRun,
  EvalResult,
  ModelUsageBucket,
  ModelUsageByModel,
  ModelUsageByPrompt,
  ModelUsageSummary,
  ModelCatalogProviderItem,
  ModelCatalogProvidersResponse,
  ModelCatalogModelItem,
  ModelCatalogModelsResponse,
  ModelCatalogRefreshResponse,
} from '@/types/models';

export type { ContentItem, CreateSourceRequest, UpdateSourceRequest };
export type FeedbackType = 'like' | 'dislike' | 'skip' | 'not_relevant' | 'outdated' | 'great_pick';
// 统计类型 re-export 保持向后兼容（外部通过 @/lib/api 导入）
export type {
  RSSHubInstance,
  StatsOverview,
  StatsSourceItem,
  StatsCategoryItem,
  StatsTrendItem,
  StatsDashboard,
  JobStatsByStatus,
  JobStatsByJobKey,
  JobStatsRecentFailure,
  JobStatsResponse,
  ContentCategoryItem,
  ScoringFlowStage,
  ScoringFlowSample,
  ScoringFlowDiagnostics,
  ScoringFlowConfig,
  ScoringFlowResponse,
  TopicGroupResponse,
  TrendPoint,
  TrendKeywordItem,
  TrendProvenanceStatus,
  TrendEvidenceFilter,
  TrendEvidenceRequest,
  TrendEvidenceScope,
  TrendEvidenceSummary,
  TrendEvidenceCalculation,
  TrendEvidenceDailyCount,
  TrendEvidenceItem,
  TrendEvidenceResponse,
  IssueFeedbackSeverity,
  IssueFeedbackStatus,
  ProductUpdateKind,
  ProductUpdateStatus,
  IssueFeedbackItem,
  IssueFeedbackListResponse,
  ProductUpdateEntry,
  ProductUpdateItem,
  ProductUpdateListResponse,
  TrendingItem,
  TrendingSource,
  TrendingAngleRecommendation,
  PersistentTopic,
  CrossPlatformSourceItem,
  CrossPlatformCluster,
  MotherTopic,
  MotherTopicMutation,
  ContentScoringResult,
  LlmModelItem,
  LlmModelPresetItem,
  LlmModelPresetCatalog,
  LlmModelCreatePayload,
  EvalRun,
  EvalResult,
  ModelUsageBucket,
  ModelUsageByModel,
  ModelUsageByPrompt,
  ModelUsageSummary,
  ModelCatalogProviderItem,
  ModelCatalogProvidersResponse,
  ModelCatalogModelItem,
  ModelCatalogModelsResponse,
  ModelCatalogRefreshResponse,
};

// Core API infrastructure (request / token / error helpers) extracted to _core.ts
import {
  request,
  getAuthToken,
  setAuthToken,
  getAuthTokenExpiresAt,
  setAuthTokenExpiresAt,
  formatApiErrorDetail,
  assertUniqueIds,
  chunkArray,
  FAVORITE_STATE_BATCH_SIZE,
} from './api/_core';
export { getAuthToken, setAuthToken, getAuthTokenExpiresAt, setAuthTokenExpiresAt, formatApiErrorDetail, FAVORITE_STATE_BATCH_SIZE };

// ─── Auth API ───

export const authApi = {
  me(): Promise<AuthUser> {
    return request('/auth/me');
  },
};

// ─── Notifications API ───

export const notificationsApi = {
  unreadCount(): Promise<{ count: number }> {
    return request('/notifications/unread-count');
  },

  list(params?: { unread?: boolean; limit?: number; offset?: number }): Promise<NotificationListResponse> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/notifications${query}`);
  },

  markRead(id: number): Promise<{ success: boolean }> {
    return request(`/notifications/${id}/read`, { method: 'POST' });
  },

  markAllRead(): Promise<{ marked: number }> {
    return request('/notifications/read-all', { method: 'POST' });
  },

  delete(id: number): Promise<{ success: boolean }> {
    return request(`/notifications/${id}`, { method: 'DELETE' });
  },
};



// Domain API objects extracted to lib/api/ submodules for module size.
// Re-export for backward compat — `import { sourcesApi } from '@/lib/api'` still works.
export {
  sourcesApi,
  contentsApi,
  contentCategoriesApi,
  favoritesApi,
  topicsApi,
  analysesApi,
  dailyReportApi,
  studioApi,
  evidenceApi,
  contentEventsAdminApi,
} from './api/_domains';
export type {
  SourceBatchImportItem,
  EvidenceStats,
  EvidenceEffectStats,
  ContentEventRelation,
  ContentEventReviewStatus,
  ContentEventNormalizationMode,
  ContentEventNormalizationScope,
  ContentEventReviewItem,
  ContentEventReviewListResponse,
  ContentEventMutationResponse,
  ContentEventNormalizeRequest,
  ContentEventNormalizeResponse,
  StudioCatalog,
  StudioBrief,
  StudioDraft,
  StudioProject,
  StudioShot,
  StudioCue,
  StudioArtifact,
} from './api/_domains';
export { settingsApi, statsApi, statsJobsApi, trendsApi, feedbackApi, productFeedbackApi, adminPromptsApi, scoringDashboardApi } from './api/_analytics';
export type { PromptRegistryItem, PromptRegistryListResponse, PromptDetailResponse, ScoringDashboardSummary, ScoringDashboardResponse } from './api/_analytics';
export { weeklyDigestApi, monthlyDigestApi } from './api/_digests';
export { readRecordApi } from './api/_read-records';
export type { ReadTargetType, ReadRecordReportPayload, ReadRecordResponse } from './api/_read-records';
export { trendingApi } from './api/_trending';
export { motherTopicsApi } from './api/_mother-topics';
export { modelsApi } from './api/_models';
