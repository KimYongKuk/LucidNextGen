"use client";

import { type ComponentProps, memo } from "react";
import { Streamdown } from "streamdown";
import { cn } from "@/lib/utils";

type ResponseProps = ComponentProps<typeof Streamdown>;

export const Response = memo(
  ({ className, ...props }: ResponseProps) => (
    <div
      className={cn(
        "size-full whitespace-pre-wrap break-words",
        className
      )}
      {...props}
    >
      {props.children}
    </div>
  ),
  (prevProps, nextProps) => prevProps.children === nextProps.children
);

Response.displayName = "Response";
