"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

type View = "login" | "setup-request" | "setup-sent";

export default function LoginPage() {
  const router = useRouter();
  const [view, setView] = useState<View>("login");

  // 로그인 상태
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // 이메일 인증 상태
  const [email, setEmail] = useState("");
  const [setupError, setSetupError] = useState("");
  const [setupLoading, setSetupLoading] = useState(false);

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login_id: loginId, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.detail || "로그인에 실패했습니다.");
        return;
      }

      router.push("/");
      router.refresh();
    } catch {
      setError("서버에 연결할 수 없습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleRequestSetup = async (e: FormEvent) => {
    e.preventDefault();
    setSetupError("");
    setSetupLoading(true);

    try {
      const res = await fetch("/api/auth/request-setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      const data = await res.json();

      if (!res.ok) {
        setSetupError(data.detail || "요청에 실패했습니다.");
        return;
      }

      setView("setup-sent");
    } catch {
      setSetupError("서버에 연결할 수 없습니다.");
    } finally {
      setSetupLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 dark:from-zinc-950 dark:to-zinc-900 px-4">
      <div className="w-full max-w-[400px]">
        {/* 카드 */}
        <div className="rounded-2xl border border-border/60 bg-card px-8 py-10 shadow-xl shadow-black/5 dark:shadow-black/20">
          {/* 로고 + 타이틀 */}
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
                Lucid AI
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                사내 AI 어시스턴트
              </p>
            </div>
          </div>

          {/* ── 로그인 뷰 ── */}
          {view === "login" && (
            <>
              <form onSubmit={handleLogin} className="space-y-5">
                <div className="space-y-1.5">
                  <label
                    htmlFor="loginId"
                    className="block text-[13px] font-medium text-muted-foreground"
                  >
                    아이디
                  </label>
                  <input
                    id="loginId"
                    type="text"
                    value={loginId}
                    onChange={(e) => setLoginId(e.target.value)}
                    placeholder="그룹웨어 ID"
                    required
                    autoFocus
                    autoComplete="username"
                    className="w-full rounded-lg border border-input bg-background px-3.5 py-2.5 text-sm text-foreground transition-colors placeholder:text-muted-foreground/60 hover:border-ring/50 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
                  />
                </div>

                <div className="space-y-1.5">
                  <label
                    htmlFor="password"
                    className="block text-[13px] font-medium text-muted-foreground"
                  >
                    비밀번호
                  </label>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="비밀번호를 입력하세요"
                    required
                    autoComplete="current-password"
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
                  disabled={isLoading || !loginId || !password}
                  className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-sm transition-all hover:bg-primary/90 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50"
                >
                  {isLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
                        <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                      </svg>
                      로그인 중
                    </span>
                  ) : (
                    "로그인"
                  )}
                </button>
              </form>

              {/* 구분선 */}
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-border" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-card px-3 text-muted-foreground/60">또는</span>
                </div>
              </div>

              {/* 첫 로그인 버튼 */}
              <button
                type="button"
                onClick={() => { setView("setup-request"); setSetupError(""); setEmail(""); }}
                className="w-full rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                처음이시거나 비밀번호 초기화가 필요하신가요?
              </button>
            </>
          )}

          {/* ── 이메일 인증 요청 뷰 ── */}
          {view === "setup-request" && (
            <>
              <div className="mb-5 text-center">
                <p className="text-sm text-muted-foreground leading-relaxed">
                  사내 이메일 주소를 입력하시면<br />
                  비밀번호 설정 링크를 보내드립니다.
                </p>
              </div>

              <form onSubmit={handleRequestSetup} className="space-y-5">
                <div className="space-y-1.5">
                  <label
                    htmlFor="email"
                    className="block text-[13px] font-medium text-muted-foreground"
                  >
                    사내 이메일
                  </label>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="hong@landf.co.kr"
                    required
                    autoFocus
                    autoComplete="email"
                    className="w-full rounded-lg border border-input bg-background px-3.5 py-2.5 text-sm text-foreground transition-colors placeholder:text-muted-foreground/60 hover:border-ring/50 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
                  />
                </div>

                {setupError && (
                  <div className="rounded-lg bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive dark:bg-destructive/20">
                    {setupError}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={setupLoading || !email}
                  className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-sm transition-all hover:bg-primary/90 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50"
                >
                  {setupLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
                        <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                      </svg>
                      전송 중
                    </span>
                  ) : (
                    "인증 메일 받기"
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => setView("login")}
                  className="w-full text-center text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  로그인으로 돌아가기
                </button>
              </form>
            </>
          )}

          {/* ── 이메일 전송 완료 뷰 ── */}
          {view === "setup-sent" && (
            <div className="text-center space-y-4">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
                <svg className="h-6 w-6 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">메일이 발송되었습니다</p>
                <p className="mt-1 text-sm text-muted-foreground leading-relaxed">
                  <strong className="text-foreground">{email}</strong>으로<br />
                  비밀번호 설정 링크를 보냈습니다.<br />
                  메일함을 확인해주세요.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setView("login")}
                className="mt-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                로그인으로 돌아가기
              </button>
            </div>
          )}
        </div>

        {/* 하단 안내 */}
        <p className="mt-6 text-center text-xs text-muted-foreground/70">
          계정 문의 · IT운영팀 / DA파트
        </p>
      </div>
    </div>
  );
}