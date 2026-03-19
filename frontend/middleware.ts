import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export default async function proxy(request: NextRequest) {
  const { searchParams, pathname } = request.url.includes('?')
    ? new URL(request.url)
    : { searchParams: new URLSearchParams(), pathname: new URL(request.url).pathname }

  const encryptedEmpno = searchParams.get('empno')

  // 1. URL 파라미터에 empno가 있으면 복호화 후 쿠키에 저장
  if (encryptedEmpno) {
    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/decrypt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ encrypted_empno: encryptedEmpno })
      })

      if (!response.ok) {
        throw new Error('복호화 실패')
      }

      const { decrypted_empno } = await response.json()

      // 쿠키에 저장하고 URL 파라미터 제거하여 리다이렉트
      const newUrl = new URL(pathname, request.url)
      const redirectResponse = NextResponse.redirect(newUrl)

      redirectResponse.cookies.set('empno', decrypted_empno, {
        httpOnly: false,
        secure: false,
        sameSite: 'lax',
        path: '/',
        maxAge: 60 * 60 * 24 // 24시간
      })

      return redirectResponse
    } catch (error) {
      // 복호화 실패 시 unauthorized로 리다이렉트
      return NextResponse.redirect(new URL('/unauthorized', request.url))
    }
  }

  // 2. 쿠키 검증 (unauthorized 페이지는 제외)
  if (pathname !== '/unauthorized') {
    const empno = request.cookies.get('empno')?.value

    if (!empno) {
      // embed 경로에서는 리다이렉트 대신 401 (iframe 깨짐 방지)
      if (pathname.startsWith('/embed')) {
        return new NextResponse('Unauthorized', { status: 401 })
      }
      return NextResponse.redirect(new URL('/unauthorized', request.url))
    }

    // 3. Admin 페이지 권한 체크
    const adminUsers = (process.env.NEXT_PUBLIC_ADMIN_USERS || '').split(',').map(s => s.trim()).filter(Boolean);
    if (pathname.startsWith('/admin') && !adminUsers.includes(empno)) {
      return NextResponse.redirect(new URL('/unauthorized', request.url))
    }
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    /*
     * 다음 경로를 제외한 모든 경로에 적용:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!api|_next/static|_next/image|favicon.ico|embed).*)',
  ],
}
