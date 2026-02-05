import Image from "next/image";
import type { Attachment } from "@/lib/types";
import { Loader } from "./elements/loader";
import { CrossSmallIcon } from "./icons";
import { Button } from "./ui/button";

export const PreviewAttachment = ({
  attachment,
  isUploading = false,
  onRemove,
}: {
  attachment: Attachment;
  isUploading?: boolean;
  onRemove?: () => void;
}) => {
  const { name, url, contentType, status, error } = attachment;
  const isProcessing = isUploading || status === 'uploading' || status === 'processing';
  const hasError = status === 'error';

  return (
    <div
      className={`group relative size-16 overflow-hidden rounded-lg border ${
        hasError ? 'border-red-500 bg-red-50 dark:bg-red-950' : 'bg-muted'
      }`}
      data-testid="input-attachment-preview"
      title={hasError ? error : undefined}
    >
      {contentType?.startsWith("image") && url && !url.startsWith('uploading-') ? (
        <Image
          alt={name ?? "An image attachment"}
          className="size-full object-cover"
          height={64}
          src={url}
          width={64}
        />
      ) : (
        <div className="flex size-full items-center justify-center text-muted-foreground text-xs">
          {hasError ? '!' : 'File'}
        </div>
      )}

      {isProcessing && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-black/50"
          data-testid="input-attachment-loader"
        >
          <Loader size={16} />
        </div>
      )}

      {hasError && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-red-500/20"
          data-testid="input-attachment-error"
        >
          <span className="text-red-600 dark:text-red-400 text-2xl font-bold">!</span>
        </div>
      )}

      {onRemove && !isProcessing && (
        <Button
          className="absolute top-0.5 right-0.5 size-4 rounded-full p-0 opacity-0 transition-opacity group-hover:opacity-100"
          onClick={onRemove}
          size="sm"
          variant="destructive"
        >
          <CrossSmallIcon size={8} />
        </Button>
      )}

      <div className="absolute inset-x-0 bottom-0 truncate bg-linear-to-t from-black/80 to-transparent px-1 py-0.5 text-[10px] text-white">
        {name}
      </div>
    </div>
  );
};
