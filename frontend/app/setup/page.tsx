"use client";

import { useState, FormEvent, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

type Status = "form" | "loading" | "success" | "error";

export default function SetupPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [status, setStatus] = useState<Status>("form");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setError("유효하지 않은 링크입니다.");
    }
  }, [token]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    if (password.length < 8) {
      setError("비밀번호는 8자 이상이어야 합니다.");
      return;
    }

    if (password !== confirmPassword) {
      setError("비밀번호가 일치하지 않습니다.");
      return;
    }

    setStatus("loading");

    try {
      const res = await fetch("/api/auth/setup-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.detail || "비밀번호 설정에 실패했습니다.");
        setStatus("form");
        return;
      }

      setStatus("success");
    } catch {
      setError("서버에 연결할 수 없습니다.");
      setStatus("form");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 dark:from-zinc-950 dark:to-zinc-900 px-4">
      <div className="w-full max-w-[400px]">
        <div className="rounded-2xl border border-border/60 bg-card px-8 py-10 shadow-xl shadow-black/5 dark:shadow-black/20">
          {/* 로고 */}
          <div className="flex flex-col items-center gap-4 mb-8">
            <img
              src="/logo.png"
              alt="Lucid AI"
              width={56}
              height={56}
              className="rounded-xl"
            />
            <div className="text-center">
              <h1 className="text-xl font-semibold tracking-tight text-foreground">
                비밀번호 설정
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Lucid AI에서 사용할 비밀번호를 설정하세요
              </p>
            </div>
          </div>

          {/* ── 비밀번호 설정 폼 ── */}
          {(status === "form" || status === "loading") && token && (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="space-y-1.5">
                <label
                  htmlFor="password"
                  className="block text-[13px] font-medium text-muted-foreground"
                >
                  새 비밀번호
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="8자 이상"
                  required
                  autoFocus
                  autoComplete="new-password"
                  className="w-full rounded-lg border border-input bg-background px-3.5 py-2.5 text-sm text-foreground transition-colors placeholder:text-muted-foreground/60 hover:border-ring/50 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
                />
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="confirmPassword"
                  className="block text-[13px] font-medium text-muted-foreground"
                >
                  비밀번호 확인
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="비밀번호를 다시 입력하세요"
                  required
                  autoComplete="new-password"
                  className="w-full rounded-lg border border-input bg-background px-3.5 py-2.5 text-sm text-foreground transition-colors placeholder:text-muted-foreground/60 hover:border-ring/50 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
                />
              </div>

              {error && (
                <div className="rounded-lg bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive dark:bg-destructive/20">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={status === "loading" || !password || !confirmPassword}
                className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-sm transition-all hover:bg-primary/90 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50"
              >
                {status === "loading" ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
                      <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                    </svg>
                    설정 중
                  </span>
                ) : (
                  "비밀번호 설정 완료"
                )}
              </button>
            </form>
          )}

          {/* ── 설정 완료 ── */}
          {status === "success" && (
            <div className="text-center space-y-4">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
                <svg className="h-6 w-6 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">비밀번호가 설정되었습니다</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  이제 로그인할 수 있습니다.
                </p>
              </div>
              <button
                type="button"
                onClick={() => router.push("/login")}
                className="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground shadow-sm transition-all hover:bg-primary/90 active:scale-[0.98]"
              >
                로그인하기
              </button>
            </div>
          )}

          {/* ── 에러 (토큰 없음/만료) ── */}
          {status === "error" && !token && (
            <div className="text-center space-y-4">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 dark:bg-destructive/20">
                <svg className="h-6 w-6 text-destructive" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">유효하지 않은 링크</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  링크가 만료되었거나 이미 사용되었습니다.
                </p>
              </div>
              <button
                type="button"
                onClick={() => router.push("/login")}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                로그인으로 돌아가기
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}