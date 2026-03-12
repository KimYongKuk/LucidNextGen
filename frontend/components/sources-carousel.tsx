'use client';

import { Card, CardContent } from '@/components/ui/card';
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from '@/components/ui/carousel';

export interface Source {
  url: string;
  title: string;
  score?: number;
}

interface SourcesCarouselProps {
  sources: Source[];
}

export function SourcesCarousel({ sources }: SourcesCarouselProps) {
  if (!sources || sources.length === 0) {
    return null;
  }

  // Filter out invalid URLs (not starting with http:// or https://)
  const validSources = sources.filter(source => {
    const url = source.url;
    return url && (url.startsWith('http://') || url.startsWith('https://'));
  });

  if (validSources.length === 0) {
    return null;
  }

  return (
    <div className="mb-4 w-full">
      {/* Border line 추가 */}
      <div className="border-t border-border my-6"></div>
      <div className="flex items-center gap-2 mb-2 text-sm font-medium text-muted-foreground">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
        </svg>
        참고 자료 (References) ({validSources.length})
      </div>
      <Carousel
        opts={{
          align: 'start',
          loop: false,
        }}
        className="w-full"
      >
        <CarouselContent className="-ml-2 md:-ml-4">
          {validSources.map((source, index) => (
            <CarouselItem key={index} className="pl-2 md:pl-4 basis-full sm:basis-1/2 lg:basis-1/3">
              <Card className="overflow-hidden hover:shadow-md transition-shadow h-full">
                <CardContent className="p-4">
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-start gap-3 group h-full"
                  >
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#FF4000]/10 flex items-center justify-center text-sm font-medium text-[#FF4000]">
                      {index + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-foreground group-hover:text-primary transition-colors line-clamp-2 mb-1">
                        {source.title}
                      </div>
                      <div className="text-xs text-muted-foreground line-clamp-1">
                        {source.url}
                      </div>
                    </div>
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="flex-shrink-0 text-muted-foreground group-hover:text-primary transition-colors mt-0.5"
                    >
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" x2="21" y1="14" y2="3" />
                    </svg>
                  </a>
                </CardContent>
              </Card>
            </CarouselItem>
          ))}
        </CarouselContent>
        <CarouselPrevious />
        <CarouselNext />
      </Carousel>
    </div>
  );
}
