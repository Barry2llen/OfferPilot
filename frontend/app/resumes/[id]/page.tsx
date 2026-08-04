import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { resumesApi } from "@/app/lib/api/resumes";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useToast } from "@/app/components/ui/toast";
import Button, { buttonClassName } from "@/app/components/ui/button";
import Badge from "@/app/components/ui/badge";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import Spinner from "@/app/components/ui/spinner";
import ResumeUploader from "@/app/components/resumes/resume-uploader";
import type {
  ResumeDetail,
  ResumeFact,
  ResumeSection,
} from "@/app/lib/api/types";

type DetailTab = "analysis" | "source";

export default function ResumeDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const id = Number(params.id);
  const { addToast } = useToast();

  const { data: resume, loading, error, refetch } = useAsyncData(
    () => resumesApi.get(id),
    [id]
  );

  const [activeTab, setActiveTab] = useState<DetailTab>("analysis");
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [operating, setOperating] = useState(false);

  const derived = useMemo(() => {
    if (!resume) return null;
    return deriveResumeView(resume);
  }, [resume]);

  const handleReplace = useCallback(async () => {
    setReplaceOpen(false);
    setActiveTab("analysis");
    refetch();
    addToast("文件已替换", "success");
  }, [refetch, addToast]);

  const handleCopyRawText = async () => {
    if (!resume?.raw_text) return;
    try {
      await navigator.clipboard.writeText(resume.raw_text);
      addToast("解析文本已复制", "success");
    } catch {
      addToast("复制失败", "error");
    }
  };

  const handleDelete = async () => {
    setOperating(true);
    try {
      await resumesApi.delete(id);
      addToast("简历已删除", "success");
      navigate("/resumes");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "删除失败";
      addToast(msg, "error");
    } finally {
      setOperating(false);
    }
  };

  const toggleReplace = () => {
    setReplaceOpen((open) => {
      const next = !open;
      if (next) setActiveTab("source");
      return next;
    });
  };

  if (loading) {
    return (
      <PageCanvas>
        <div className="flex items-center justify-center py-24">
          <Spinner size="lg" />
        </div>
      </PageCanvas>
    );
  }

  if (error) {
    return (
      <PageCanvas>
        <div className="rounded-[20px] border border-border-light bg-white px-6 py-16 text-center shadow-card">
          <p className="mb-4 text-sm text-error-text">{error}</p>
          <div className="flex justify-center gap-3">
            <Button variant="secondary" size="sm" onClick={refetch}>
              重试
            </Button>
            <Link
              to="/resumes"
              className={buttonClassName({ variant: "ghost", size: "sm" })}
            >
              返回列表
            </Link>
          </div>
        </div>
      </PageCanvas>
    );
  }

  if (!resume || !derived) return null;

  return (
    <PageCanvas>
      <header className="mb-4 flex items-center justify-between gap-4">
        <Link
          to="/resumes"
          className="inline-flex items-center gap-2 rounded-full px-2 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-secondary hover:text-text-primary"
        >
          <ArrowLeftIcon className="h-5 w-5" />
          返回简历库
        </Link>
        <Button variant="ghost" size="sm" aria-label="更多操作">
          <DotsIcon className="h-5 w-5" />
        </Button>
      </header>

      <section className="flex min-h-[680px] flex-col bg-white lg:min-h-[calc(100vh-7.5rem)]">
        <div className="flex flex-col gap-4 border-b border-border-light py-5 sm:py-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <h1 className="truncate font-display text-2xl font-semibold leading-tight text-text-primary">
              {derived.title}
            </h1>
            <p className="mt-2 text-sm leading-6 text-text-secondary">
              {derived.subtitle}
            </p>
          </div>

          <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center lg:shrink-0">
            <Badge
              variant={parseVariant(resume.parse_status)}
              className="rounded-full px-3 py-1 font-mono text-[11px] font-bold"
            >
              {parseLabel(resume.parse_status)}
            </Badge>
            <TabSwitch activeTab={activeTab} onChange={setActiveTab} />
          </div>
        </div>

        <div className="flex-1">
          {activeTab === "analysis" ? (
            <AnalysisContent resume={resume} derived={derived} />
          ) : (
            <SourceContent
              resume={resume}
              replaceOpen={replaceOpen}
              onUploaded={handleReplace}
              uploadFile={(file, selectionId, onEvent, onError, signal) =>
                resumesApi.replace(
                  id,
                  file,
                  selectionId,
                  onEvent,
                  onError,
                  signal
                )
              }
            />
          )}
        </div>

        <div className="mt-auto flex flex-col gap-3 border-t border-border-light bg-white/95 py-4 backdrop-blur sm:flex-row sm:items-center sm:justify-between">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirmDelete(true)}
            className="justify-start text-error-text hover:bg-error-bg"
          >
            <TrashIcon className="h-4 w-4" />
            删除
          </Button>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button variant="secondary" size="sm" pill onClick={toggleReplace}>
              <UploadFileIcon className="h-4 w-4" />
              {replaceOpen ? "取消替换" : "替换"}
            </Button>
            <Button
              size="sm"
              disabled={!resume.raw_text}
              onClick={handleCopyRawText}
              className="shadow-sm"
            >
              <CopyIcon className="h-4 w-4" />
              复制解析文本
            </Button>
          </div>
        </div>
      </section>

      <ConfirmDialog
        open={confirmDelete}
        title="删除简历"
        message={`确定要删除「${resume.original_filename || `简历 #${resume.id}`}」吗？此操作会删除数据库记录和原始文件。`}
        confirmLabel="删除"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
        loading={operating}
      />
    </PageCanvas>
  );
}

function PageCanvas({ children }: { children: ReactNode }) {
  return (
    <div className="electron-titlebar-safe-top min-h-full bg-white">
      <div className="mx-auto max-w-[1080px] px-5 py-4 sm:px-8 lg:px-10 lg:py-6">
        {children}
      </div>
    </div>
  );
}

function TabSwitch({
  activeTab,
  onChange,
}: {
  activeTab: DetailTab;
  onChange: (tab: DetailTab) => void;
}) {
  return (
    <div className="relative grid w-full grid-cols-2 rounded-full border border-[#e6e1dc] bg-white p-0.5 shadow-[0_1px_8px_rgba(24,24,24,0.06)] sm:w-[188px]">
      <span
        className={`absolute bottom-0.5 top-0.5 w-[calc(50%-2px)] rounded-full bg-[#1b1f24] shadow-sm transition-transform duration-200 ${
          activeTab === "source" ? "translate-x-full" : "translate-x-0"
        }`}
      />
      <button
        type="button"
        onClick={() => onChange("analysis")}
        className={`relative z-10 h-8 rounded-full px-3 text-[11px] font-semibold transition-colors ${
          activeTab === "analysis" ? "text-white" : "text-[#5b5751]"
        }`}
      >
        AI 解析
      </button>
      <button
        type="button"
        onClick={() => onChange("source")}
        className={`relative z-10 h-8 rounded-full px-3 text-[11px] font-semibold transition-colors ${
          activeTab === "source" ? "text-white" : "text-[#5b5751]"
        }`}
      >
        简历原件
      </button>
    </div>
  );
}

function AnalysisContent({
  resume,
  derived,
}: {
  resume: ResumeDetail;
  derived: ReturnType<typeof deriveResumeView>;
}) {
  return (
    <div className="mx-auto max-w-[920px] space-y-8 py-7">
      <AnalysisSection icon={<SummaryIcon className="h-5 w-5" />} title="摘要">
        {resume.parse_error ? (
          <p className="rounded-xl bg-error-bg px-4 py-3 text-[15px] leading-7 text-error-text">
            {resume.parse_error}
          </p>
        ) : (
          <p className="text-[15px] leading-8 text-text-secondary">
            {derived.summary}
          </p>
        )}
      </AnalysisSection>

      <AnalysisSection
        icon={<SkillIcon className="h-5 w-5" />}
        title="核心关键词"
      >
        {derived.keywords.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {derived.keywords.map((keyword) => (
              <span
                key={keyword}
                className="rounded-full border border-[#ddd6cf] bg-white px-3 py-1 font-mono text-[11px] font-bold text-[#2f2d29]"
              >
                {keyword}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-[15px] text-text-muted">
            完成解析后会显示技能、经历和事实关键词。
          </p>
        )}
      </AnalysisSection>

      <AnalysisSection
        icon={<BriefcaseIcon className="h-5 w-5" />}
        title="结构化章节"
      >
        {resume.sections.length > 0 ? (
          <div className="space-y-6 border-l-2 border-border-light pl-5">
            {resume.sections.map((section, index) => (
              <TimelineSection
                key={`${section.title}-${index}`}
                section={section}
                index={index}
              />
            ))}
          </div>
        ) : (
          <p className="text-[15px] text-text-muted">
            上传或替换文件后会在这里显示解析文本和结构化章节。
          </p>
        )}
      </AnalysisSection>

      {resume.raw_text && (
        <AnalysisSection
          icon={<TextIcon className="h-5 w-5" />}
          title="完整解析文本"
        >
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl border border-[#eee8e2] bg-[#fbfaf8] p-4 text-[13px] leading-7 text-text-secondary">
            {resume.raw_text}
          </pre>
        </AnalysisSection>
      )}
    </div>
  );
}

function SourceContent({
  resume,
  replaceOpen,
  onUploaded,
  uploadFile,
}: {
  resume: ResumeDetail;
  replaceOpen: boolean;
  onUploaded: () => void;
  uploadFile: typeof resumesApi.upload;
}) {
  return (
    <div className="py-5">
      {replaceOpen ? (
        <div className="mx-auto max-w-xl py-6">
          <ResumeUploader onUploaded={onUploaded} uploadFile={uploadFile} />
        </div>
      ) : (
        <ResumePreview resume={resume} />
      )}
    </div>
  );
}

function deriveResumeView(resume: ResumeDetail) {
  const title = (resume.original_filename || `简历 #${resume.id}`).replace(
    /\.[^/.]+$/,
    ""
  );
  const facts = resume.sections.flatMap((section) => section.facts);
  const keywords = Array.from(
    new Set(facts.flatMap((fact) => fact.keywords).filter(Boolean))
  ).slice(0, 10);
  const subtitle =
    resume.parse_status === "parsed"
      ? `${resume.section_count} 个章节 · ${resume.fact_count} 条事实`
      : resume.parse_status === "processing"
        ? "正在解析候选人简历"
        : resume.parse_status === "failed"
          ? "解析失败，建议替换文件后重试"
          : "等待解析";
  return {
    title,
    subtitle,
    keywords,
    summary:
      resume.summary ||
      (resume.parse_status === "parsed"
        ? "已完成结构化解析，可查看章节、事实和完整文本。"
        : "上传或替换文件后，OfferPilot 会自动提取简历摘要、章节和关键事实。"),
  };
}

function ResumePreview({ resume }: { resume: ResumeDetail }) {
  if (!resume.has_file) {
    return (
      <PreviewEmpty
        title="没有可预览的原文件"
        description="可使用底部操作替换文件。"
      />
    );
  }

  if (resume.media_type?.includes("pdf")) {
    return (
      <div className="mx-auto min-h-[620px] max-w-[820px] overflow-hidden bg-white">
        <iframe
          src={resumesApi.previewUrl(resume.id)}
          className="h-[620px] w-full"
          title="简历预览"
        />
      </div>
    );
  }

  if (resume.media_type?.startsWith("image/")) {
    return (
      <div className="mx-auto flex min-h-[620px] max-w-[820px] items-start justify-center overflow-auto bg-white py-4">
        <img
          src={resumesApi.previewUrl(resume.id)}
          alt={resume.original_filename || ""}
          className="h-auto max-h-[580px] w-auto max-w-full"
        />
      </div>
    );
  }

  return (
    <PreviewEmpty
      title="不支持在线预览此格式"
      description="仍可查看 AI 解析结果和完整文本。"
    />
  );
}

function PreviewEmpty({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="mx-auto flex min-h-[520px] max-w-[820px] flex-col items-center justify-center px-6 text-center">
      <FileIcon className="mb-4 h-10 w-10 text-text-muted" />
      <p className="font-display text-base font-medium text-text-primary">
        {title}
      </p>
      <p className="mt-2 text-sm text-text-muted">{description}</p>
    </div>
  );
}

function AnalysisSection({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <section>
      <h2 className="mb-3 flex items-center gap-2.5 font-display text-lg font-medium text-text-primary">
        <span className="text-text-muted">{icon}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function TimelineSection({
  section,
  index,
}: {
  section: ResumeSection;
  index: number;
}) {
  const facts = section.facts.slice(0, 3);
  return (
    <section className="relative">
      <span
        className={`absolute -left-[33px] top-1 h-4 w-4 rounded-full border-2 bg-white ${
          index === 0 ? "border-[#1b1f24]" : "border-[#e4ded8]"
        }`}
      />
      <h3 className="font-display text-base font-medium text-text-primary">
        {section.title || `章节 ${index + 1}`}
      </h3>
      <p className="mt-2 whitespace-pre-wrap text-[13px] leading-7 text-text-secondary">
        {section.content}
      </p>
      {facts.length > 0 && (
        <div className="mt-3 space-y-2">
          {facts.map((fact, factIndex) => (
            <FactLine key={`${fact.fact_type}-${factIndex}`} fact={fact} />
          ))}
        </div>
      )}
    </section>
  );
}

function FactLine({ fact }: { fact: ResumeFact }) {
  return (
    <div className="rounded-xl border border-[#eee8e2] bg-[#fbfaf8] px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant="neutral"
          className="rounded-full border border-[#e6dfd8] bg-white font-mono text-[11px] text-[#5a544d]"
        >
          {fact.fact_type}
        </Badge>
        <span className="text-[13px] leading-6 text-text-primary">
          {fact.text}
        </span>
      </div>
      {fact.keywords.length > 0 && (
        <p className="mt-1 font-mono text-[13px] text-text-muted">
          {fact.keywords.join("、")}
        </p>
      )}
    </div>
  );
}

function parseLabel(status: ResumeDetail["parse_status"]): string {
  switch (status) {
    case "parsed":
      return "已解析";
    case "processing":
      return "解析中";
    case "failed":
      return "解析失败";
    case "unparsed":
    default:
      return "未解析";
  }
}

function parseVariant(status: ResumeDetail["parse_status"]) {
  if (status === "parsed") return "success";
  if (status === "failed") return "error";
  if (status === "processing") return "warning";
  return "neutral";
}

function ArrowLeftIcon({ className }: { className?: string }) {
  return <BaseIcon className={className} path="M15 19 8 12l7-7" />;
}

function DotsIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path d="M12 8.25a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM12 13.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM12 18.75a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z" />
    </svg>
  );
}

function FileIcon({ className }: { className?: string }) {
  return (
    <BaseIcon
      className={className}
      path="M7 3.75h6l4 4v12.5H7V3.75ZM13 3.75v4h4M9.5 12h5M9.5 15h5M9.5 18h3"
    />
  );
}

function SummaryIcon({ className }: { className?: string }) {
  return (
    <BaseIcon
      className={className}
      path="M8 7h8M8 11h8M8 15h5M5 3.75h14v16.5H5V3.75Z"
    />
  );
}

function SkillIcon({ className }: { className?: string }) {
  return (
    <BaseIcon
      className={className}
      path="M12 3.5a4.5 4.5 0 0 1 2.2 8.43V15h-4.4v-3.07A4.5 4.5 0 0 1 12 3.5ZM10 18h4M10.5 21h3"
    />
  );
}

function BriefcaseIcon({ className }: { className?: string }) {
  return (
    <BaseIcon
      className={className}
      path="M9 6V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1M4 8h16v10.5H4V8ZM4 12h16"
    />
  );
}

function TextIcon({ className }: { className?: string }) {
  return (
    <BaseIcon className={className} path="M5 6h14M5 10h14M5 14h10M5 18h8" />
  );
}

function TrashIcon({ className }: { className?: string }) {
  return (
    <BaseIcon
      className={className}
      path="M5 7h14M10 11v6M14 11v6M8 7l1 13h6l1-13M9.5 7l.75-3h3.5l.75 3"
    />
  );
}

function UploadFileIcon({ className }: { className?: string }) {
  return (
    <BaseIcon
      className={className}
      path="M7 3.75h6l4 4v12.5H7V3.75ZM13 3.75v4h4M12 18v-6M9.5 14.5 12 12l2.5 2.5"
    />
  );
}

function CopyIcon({ className }: { className?: string }) {
  return <BaseIcon className={className} path="M8 8h10v12H8V8ZM6 16H4V4h10v2" />;
}

function BaseIcon({ className, path }: { className?: string; path: string }) {
  return (
    <svg
      className={className}
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.8}
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path d={path} />
    </svg>
  );
}
