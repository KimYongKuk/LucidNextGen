"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Bot, Lock, Globe, Code2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TooltipProvider, Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { getUserId, isOperatorUser } from "@/lib/utils";

type PlatformOption = {
  key: "miso" | "runner" | "webhook";
  label: string;
  Icon: typeof Bot;
  color: string;
  description: string;
  persona: string;
  requiresOperator: boolean;
};

const PLATFORMS: PlatformOption[] = [
  {
    key: "miso",
    label: "MISO Agent / Workflow",
    Icon: Bot,
    color: "text-blue-600 bg-blue-50 dark:bg-blue-950 dark:text-blue-300",
    description: "MISO 빌더에서 만든 에이전트/워크플로우를 카탈로그에 등록합니다.",
    persona: "모든 사용자",
    requiresOperator: false,
  },
  {
    key: "runner",
    label: "Runner 매크로",
    Icon: Lock,
    color: "text-amber-600 bg-amber-50 dark:bg-amber-950 dark:text-amber-300",
    description: "EC2 Runner에서 실행되는 PAD/Python/VBS 매크로를 등록합니다.",
    persona: "관리자 전용",
    requiresOperator: true,
  },
  {
    key: "webhook",
    label: "Webhook",
    Icon: Globe,
    color: "text-emerald-600 bg-emerald-50 dark:bg-emerald-950 dark:text-emerald-300",
    description: "외부 REST API(Slack, n8n, Zapier 등)를 등록합니다.",
    persona: "관리자 전용",
    requiresOperator: true,
  },
];

export default function NewAgentEntryPage() {
  const router = useRouter();
  const [isOperator, setIsOperator] = useState(false);

  useEffect(() => {
    const uid = getUserId();
    setIsOperator(isOperatorUser(uid));
  }, []);

  const handleSelect = (key: PlatformOption["key"], requiresOperator: boolean) => {
    if (requiresOperator && !isOperator) return;
    router.push(`/agent-store/new/${key}`);
  };

  return (
    <TooltipProvider delayDuration={150}>
      <div className="min-h-screen bg-background text-foreground">
        <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
          <div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/agent-store">
                <ArrowLeft className="mr-1 h-4 w-4" />
                Agent Store로
              </Link>
            </Button>
          </div>

          <div>
            <h1 className="text-2xl font-bold sm:text-3xl">에이전트 등록</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Agent/Runner를 등록하기 위한 화면입니다. 등록된 Agent는 자동 검증 단계 및 관리자 승인을 거쳐 카탈로그에 노출됩니다.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              ※ Native Agent는 코드 배포로만 등록됩니다. (문의사항: 김용국 파트장)
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {PLATFORMS.map((p) => {
              const disabled = p.requiresOperator && !isOperator;
              const card = (
                <button
                  key={p.key}
                  type="button"
                  onClick={() => handleSelect(p.key, p.requiresOperator)}
                  disabled={disabled}
                  className={[
                    "group flex flex-col items-start gap-3 rounded-xl border bg-card p-5 text-left transition-all",
                    disabled
                      ? "cursor-not-allowed opacity-50"
                      : "hover:-translate-y-0.5 hover:border-primary hover:shadow-md",
                  ].join(" ")}
                >
                  <div
                    className={[
                      "flex h-11 w-11 items-center justify-center rounded-xl",
                      p.color,
                    ].join(" ")}
                  >
                    <p.Icon className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-semibold">{p.label}</h3>
                    <p className="mt-1 text-xs text-muted-foreground">{p.description}</p>
                  </div>
                  <div className="mt-auto rounded-md bg-muted px-2 py-1 text-[11px] text-muted-foreground">
                    {p.persona}
                  </div>
                </button>
              );

              if (disabled) {
                return (
                  <Tooltip key={p.key}>
                    <TooltipTrigger asChild>
                      <div>{card}</div>
                    </TooltipTrigger>
                    <TooltipContent>관리자 권한이 필요합니다.</TooltipContent>
                  </Tooltip>
                );
              }
              return card;
            })}
          </div>

          <div className="rounded-lg border border-dashed bg-muted/40 p-4 text-xs text-muted-foreground">
            <div className="flex items-start gap-2">
              <Code2 className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-medium text-foreground">등록 후 자동 검증 + 관리자 승인</p>
                <p className="mt-1">
                  등록 시 매니페스트 형식 / 보안 패턴(SSRF, 명령어 주입, Secret Leak)을 자동 검증합니다.
                  검증 통과 시 관리자가 검토하여 승인하면 카탈로그에 노출됩니다.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
