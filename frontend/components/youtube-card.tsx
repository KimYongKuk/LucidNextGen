"use client"

import { Card } from "@/components/ui/card"
import { PlayCircle, Calendar, ExternalLink } from "lucide-react"
import { Button } from "@/components/ui/button"

interface YouTubeCardProps {
    title: string
    thumbnailUrl?: string
    publishedAt?: string
    summary?: string
    videoId?: string
    onClick: () => void
}

export function YouTubeCard({
    title,
    thumbnailUrl,
    publishedAt,
    summary,
    videoId,
    onClick
}: YouTubeCardProps) {

    const formatDate = (dateString?: string) => {
        if (!dateString) return "Recently"
        try {
            return new Intl.DateTimeFormat("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
            }).format(new Date(dateString))
        } catch {
            return dateString
        }
    }

    // Construct thumbnail URL if not provided but videoId is available
    const image = thumbnailUrl || (videoId ? `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg` : null)

    return (
        <Card
            className="group relative overflow-hidden border-border bg-card transition-all hover:border-primary/50 hover:shadow-lg hover:shadow-primary/10 cursor-pointer flex flex-col h-full"
            onClick={onClick}
        >
            {/* Thumbnail Section */}
            <div className="relative aspect-video w-full overflow-hidden bg-muted">
                {image ? (
                    <img
                        src={image}
                        alt={title}
                        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                    />
                ) : (
                    <div className="flex h-full w-full items-center justify-center bg-secondary">
                        <PlayCircle className="h-12 w-12 text-muted-foreground/50" />
                    </div>
                )}
                <div className="absolute inset-0 bg-black/20 opacity-0 transition-opacity group-hover:opacity-100 flex items-center justify-center">
                    <PlayCircle className="h-12 w-12 text-white drop-shadow-lg" />
                </div>
            </div>

            <div className="flex flex-col flex-1 p-5">
                {/* Date */}
                <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                    <Calendar className="h-3 w-3" />
                    <span>{formatDate(publishedAt)}</span>
                </div>

                {/* Title */}
                <h3 className="mb-3 text-lg font-semibold leading-snug text-foreground group-hover:text-primary transition-colors line-clamp-2">
                    {title}
                </h3>

                {/* Summary Preview */}
                {summary && (
                    <p className="text-sm text-muted-foreground line-clamp-3 mb-4 flex-1">
                        {summary}
                    </p>
                )}

                {/* Footer */}
                <div className="mt-auto pt-4 border-t border-border/50 flex items-center justify-between">
                    <span className="text-xs font-medium text-primary">View Summary</span>
                    {videoId && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-muted-foreground hover:text-foreground"
                            onClick={(e) => {
                                e.stopPropagation();
                                window.open(`https://www.youtube.com/watch?v=${videoId}`, '_blank');
                            }}
                        >
                            <ExternalLink className="h-4 w-4" />
                        </Button>
                    )}
                </div>
            </div>
        </Card>
    )
}
