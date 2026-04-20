import type { Metadata } from "next";
import { Suspense } from "react";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { ThemeProvider } from "@/components/theme-provider";
import { OnboardingProvider } from "@/components/onboarding/onboarding-provider";
import { WhatsNewProvider } from "@/components/whats-new/whats-new-provider";
import { NoticeToastProvider } from "@/components/notice-toast/notice-toast-provider";
import { NotificationInboxProvider } from "@/components/notification-inbox/notification-inbox-provider";
import { LunchboxRain } from "@/components/easter-egg/lunchbox-rain";

import "./globals.css";


export const metadata: Metadata = {
  // metadataBase: new URL("https://chat.vercel.ai"),
  title: "Lucid AI",
  description: "Chatbot Lucid AI by L&F",
  icons: {
    icon: "/logo.png",
  },
};

export const viewport = {
  maximumScale: 1, // Disable auto-zoom on mobile Safari
};

const geist = Geist({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-geist",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-geist-mono",
});

const LIGHT_THEME_COLOR = "hsl(0 0% 100%)";
const DARK_THEME_COLOR = "hsl(240deg 10% 3.92%)";
const THEME_COLOR_SCRIPT = `\
(function() {
  var html = document.documentElement;
  var meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute('name', 'theme-color');
    document.head.appendChild(meta);
  }
  function updateThemeColor() {
    var isDark = html.classList.contains('dark');
    meta.setAttribute('content', isDark ? '${DARK_THEME_COLOR}' : '${LIGHT_THEME_COLOR}');
  }
  var observer = new MutationObserver(updateThemeColor);
  observer.observe(html, { attributes: true, attributeFilter: ['class'] });
  updateThemeColor();
})();`;

// 복사 시 다크 테마 배경색이 클립보드에 포함되지 않도록 하는 스크립트
const CLEAN_COPY_SCRIPT = `\
(function() {
  document.addEventListener('copy', function(e) {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    var range = sel.getRangeAt(0);
    var container = document.createElement('div');
    container.appendChild(range.cloneContents());
    var els = container.querySelectorAll('*');
    for (var i = 0; i < els.length; i++) {
      var s = els[i].style;
      if (s) {
        s.removeProperty('background-color');
        s.removeProperty('background');
        s.removeProperty('color');
      }
      els[i].removeAttribute('bgcolor');
    }
    var html = container.innerHTML;
    if (html) {
      e.clipboardData.setData('text/html', html);
      e.clipboardData.setData('text/plain', sel.toString());
      e.preventDefault();
    }
  });
})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      className={`${geist.variable} ${geistMono.variable}`}
      // `next-themes` injects an extra classname to the body element to avoid
      // visual flicker before hydration. Hence the `suppressHydrationWarning`
      // prop is necessary to avoid the React hydration mismatch warning.
      // https://github.com/pacocoursey/next-themes?tab=readme-ov-file#with-app
      lang="en"
      suppressHydrationWarning
    >
      <head>
        <link
          rel="stylesheet"
          as="style"
          crossOrigin="anonymous"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
        <script
          // biome-ignore lint/security/noDangerouslySetInnerHtml: "Required"
          dangerouslySetInnerHTML={{
            __html: THEME_COLOR_SCRIPT,
          }}
        />
        <script
          // biome-ignore lint/security/noDangerouslySetInnerHtml: "Required"
          dangerouslySetInnerHTML={{
            __html: CLEAN_COPY_SCRIPT,
          }}
        />
      </head>
      <body className="antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          disableTransitionOnChange
          enableSystem
        >
          <OnboardingProvider>
            <WhatsNewProvider>
              <NotificationInboxProvider>
                <Suspense>
                  <NoticeToastProvider>
                    <Toaster position="top-center" />
                    <LunchboxRain />
                    {children}
                  </NoticeToastProvider>
                </Suspense>
              </NotificationInboxProvider>
            </WhatsNewProvider>
          </OnboardingProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
