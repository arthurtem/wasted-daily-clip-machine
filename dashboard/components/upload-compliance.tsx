import { YOUTUBE_COMMUNITY_URL, YOUTUBE_TOS_URL } from "@/lib/links";

const linkClass =
  "text-zinc-300 underline decoration-zinc-600 underline-offset-4";

export default function UploadCompliance({
  channelName,
}: {
  channelName: string;
}) {
  return (
    <div className="space-y-1.5 border-t border-zinc-800 pt-3">
      <p className="text-xs font-semibold text-zinc-300">
        Uploading to: {channelName}
      </p>
      <p className="text-[11px] leading-5 text-zinc-500">
        By submitting your videos to YouTube, you acknowledge that you agree to
        YouTube&apos;s Terms of Service (
        <a
          href={YOUTUBE_TOS_URL}
          target="_blank"
          rel="noreferrer"
          className={linkClass}
        >
          {YOUTUBE_TOS_URL}
        </a>
        ) and Community Guidelines (
        <a
          href={YOUTUBE_COMMUNITY_URL}
          target="_blank"
          rel="noreferrer"
          className={linkClass}
        >
          {YOUTUBE_COMMUNITY_URL}
        </a>
        ).
      </p>
    </div>
  );
}
