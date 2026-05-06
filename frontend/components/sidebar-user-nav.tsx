"use client";

import { useEffect, useState } from "react";
import { ChevronUp } from "lucide-react";
import Image from "next/image";

import { useTheme } from "next-themes";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { getUserId, getUserName } from "@/lib/utils";
import { useUserInfo } from "@/hooks/use-user-directory";


export function SidebarUserNav({ user }: { user: any }) {
  const { setTheme, resolvedTheme } = useTheme();
  // AD 인증 쿠키 + 백엔드 디렉토리 lookup (부서 포함). SSR/CSR 일치 위해 useEffect로 set.
  const [userId, setUserId] = useState<string | null>(null);
  const [cookieName, setCookieName] = useState<string | null>(null);
  useEffect(() => {
    setUserId(getUserId());
    setCookieName(getUserName());
  }, []);

  const info = useUserInfo(userId);
  // 표시 우선순위: 디렉토리(부서+이름, found=true) > 쿠키(이름) > email > 사번
  const display = info && info.found && info.name
    ? (info.team ? `${info.team} ${info.name}` : info.name)
    : (cookieName ?? user?.email ?? userId ?? "Guest");

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              className="h-10 bg-background data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
              data-testid="user-nav-button"
            >
              <Image
                alt={user?.email ?? "User Avatar"}
                className="rounded-full"
                height={24}
                src={`https://avatar.vercel.sh/${user?.email ?? "guest"}`}
                width={24}
              />
              <span className="truncate" data-testid="user-email">
                {display}
              </span>
              <ChevronUp className="ml-auto" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-(--radix-popper-anchor-width)"
            data-testid="user-nav-menu"
            side="top"
          >
            <DropdownMenuItem
              className="cursor-pointer"
              data-testid="user-nav-item-theme"
              onSelect={() =>
                setTheme(resolvedTheme === "dark" ? "light" : "dark")
              }
            >
              {`Toggle ${resolvedTheme === "light" ? "dark" : "light"} mode`}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild data-testid="user-nav-item-auth">
              <button
                className="w-full cursor-pointer"
                onClick={async () => {
                  await fetch("/api/auth/logout", { method: "POST" });
                  window.location.href = "/login";
                }}
                type="button"
              >
                로그아웃
              </button>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
