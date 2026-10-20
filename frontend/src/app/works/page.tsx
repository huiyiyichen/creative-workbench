"use client";

/** 作品库（改造方案 9）：按项目归档产出物，可预览、下载、复制；完成 / 已导出 / 已发布自动收录，草稿可在产出页手动加入。 */

import Link from "next/link";
import { Input, Segmented, message } from "antd";
import { Copy, Download, ExternalLink } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { CwPage, TopBar } from "@/design/components";
import { OUTPUT_LABEL, OUTPUT_STATUS } from "@/design/studio";
import { PerformancePanel, PublishWeek } from "@/design/publishing";
import { compactNum } from "@/lib/publishing";
import { fmtHM, cnParts } from "@/lib/time-cn";
import {
  projectsApi,
  type WorkItem,
  type WorksView,
} from "@/lib/api/_projects";

const KINDS = [
  { value: "", label: "全部" },
  { value: "video", label: "讲解视频" },
  { value: "mv", label: "MV" },
  { value: "xhs", label: "小红书" },
  { value: "zhihu", label: "知乎" },
  { value: "wechat", label: "公众号" },
  { value: "prompt_bundle", label: "提示词包" },
];

function WorkCard({
  item,
  onChanged,
}: {
  item: WorkItem;
  onChanged: () => void;
}) {
  const [label, tone] = OUTPUT_STATUS[item.status] || [
    item.status,
    "var(--cw-dim)",
  ];
  const copy = async () => {
    if (!item.copy_text) return;
    try {
      await navigator.clipboard.writeText(item.copy_text);
      message.success("已复制");
    } catch {
      message.error("复制失败，浏览器不允许访问剪贴板");
    }
  };
  const remove = async () => {
    try {
      await projectsApi.setInWorks(item.id, false);
      onChanged();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "操作失败");
    }
  };
  return (
    <article className="cw-work">
      {item.preview_path ? (
        <video
          className="cw-work-media"
          src={item.preview_path}
          controls
          preload="metadata"
        />
      ) : item.cover ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="cw-work-media" src={item.cover} alt="" />
      ) : (
        <p className="cw-work-excerpt">
          {item.excerpt ||
            (["video", "mv"].includes(item.kind)
              ? "（成片文件不在本机）"
              : "（没有文字内容）")}
        </p>
      )}
      <div className="cw-work-body">
        <Link href={item.href} className="cw-work-title">
          {item.title}
        </Link>
        <div className="cw-work-meta">
          <span>
            {item.type === "legacy"
              ? "旧工作台"
              : OUTPUT_LABEL[item.kind as keyof typeof OUTPUT_LABEL] ||
                item.kind}
          </span>
          <span style={{ color: tone }}>{label}</span>
          {item.based_on_version ? (
            <span className="cw-num">v{item.based_on_version}</span>
          ) : null}
          {item.chars ? <span className="cw-num">{item.chars} 字</span> : null}
          {item.metrics && item.metrics.views !== undefined ? (
            <span className="cw-num">
              {compactNum(item.metrics.views)} 播放
            </span>
          ) : null}
          {item.schedule && item.status !== "published" ? (
            <span className="cw-num" style={{ color: "var(--cw-cy)" }}>
              排在 {cnParts(item.schedule.at).mo}/{cnParts(item.schedule.at).d}{" "}
              {fmtHM(item.schedule.at)}
            </span>
          ) : null}
        </div>
        <div className="cw-work-acts">
          {item.copy_text ? (
            <button type="button" className="cw-link-btn" onClick={copy}>
              <Copy size={13} /> 复制
            </button>
          ) : null}
          {item.download_path ? (
            <a className="cw-link-btn" href={item.download_path} download>
              <Download size={13} /> 下载
            </a>
          ) : null}
          {item.published_url ? (
            <a
              className="cw-link-btn"
              href={item.published_url}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={13} /> 已发布
            </a>
          ) : null}
          {item.type === "output" ? (
            <button
              type="button"
              className="cw-link-btn cw-muted"
              onClick={remove}
            >
              移出
            </button>
          ) : null}
        </div>
      </div>
    </article>
  );
}

const VIEWS = [
  { value: "works", label: "作品" },
  { value: "calendar", label: "发布日历" },
  { value: "performance", label: "效果" },
];

export default function WorksPage() {
  const [view, setView] = useState("works");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [data, setData] = useState<WorksView | null>(null);
  const load = useCallback(() => {
    projectsApi
      .works({ kind: kind || undefined, q: q.trim() || undefined })
      .then(setData)
      .catch((err) => {
        message.error(err instanceof Error ? err.message : "加载失败");
        setData({ groups: [], total: 0 });
      });
  }, [kind, q]);
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);
  return (
    <CwPage>
      <TopBar
        title="作品"
        sub={data ? <span className="cw-num">{data.total} 件</span> : undefined}
      >
        <Segmented
          value={view}
          onChange={(v) => setView(String(v))}
          options={VIEWS}
        />
      </TopBar>
      {view === "calendar" ? <PublishWeek /> : null}
      {view === "performance" ? <PerformancePanel /> : null}
      {view === "works" ? (
        <>
          <div className="cw-row cw-task-filters">
            <Segmented
              value={kind}
              onChange={(v) => setKind(String(v))}
              options={KINDS}
            />
            <Input.Search
              allowClear
              placeholder="搜项目或作品"
              style={{ maxWidth: 260 }}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          {data === null ? <p className="cw-muted">加载中…</p> : null}
          {data && !data.total ? (
            <p className="cw-empty" data-block="true">
              还没有作品。产出物完成、导出或发布后会自动收进来；草稿可以在产出页点「加入作品库」。
            </p>
          ) : null}
          {data?.groups.map((g) => (
            <section key={g.project.id} className="cw-works-group">
              <h2>
                <Link href={`/projects/${g.project.id}/outputs`}>
                  {g.project.title}
                </Link>
                <span className="cw-num cw-muted">{g.items.length}</span>
              </h2>
              <div className="cw-works-grid">
                {g.items.map((i) => (
                  <WorkCard key={i.key} item={i} onChanged={load} />
                ))}
              </div>
            </section>
          ))}
        </>
      ) : null}
    </CwPage>
  );
}
