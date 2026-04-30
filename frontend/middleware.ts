import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { jwtVerify, SignJWT } from 'jose'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'
const SECRET_KEY = new TextEncoder().encode(
  process.env.SECRET_KEY || 'landf01234567890_fastapi_secret_key_change_in_production'
)
const JWT_ALGORITHM = 'HS256'

/**
 * JWT 토큰에서 empno 추출
 */
async function getEmpnoFromToken(token: string): Promise<string | null> {
  try {
    const { payload } = await jwtVerify(token, SECRET_KEY, {
      algorithms: [JWT_ALGORITHM],
    })
    return (payload.empno as string) || null
  } catch {
    return null
  }
}

/**
 * SSO 복호화된 empno로 JWT auth_token 생성
 * 백엔드의 auth.py::_create_token()과 동일한 payload 구조 (HS256, 24h)
 */
async function createAuthToken(empno: string): Promise<string> {
  return await new SignJWT({ empno })
    .setProtectedHeader({ alg: JWT_ALGORITHM })
    .setIssuedAt()
    .setExpirationTime('24h')
    .sign(SECRET_KEY)
}

export default async function proxy(request: NextRequest) {
  const { searchParams, pathname } = request.url.includes('?')
    ? new URL(request.url)
    : { searchParams: new URLSearchParams(), pathname: new URL(request.url).pathname }

  const encryptedEmpno = searchParams.get('empno')

  // 1. SSO: URL 파라미터에 empno가 있으면 복호화 후 쿠키에 저장
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

      // auth_token JWT 발급 — 백엔드 채팅 엔드포인트가 이 쿠키로 인증
      const authToken = await createAuthToken(decrypted_empno)
      redirectResponse.cookies.set('auth_token', authToken, {
        httpOnly: true,
        secure: false,
        sameSite: 'lax',
        path: '/',
        maxAge: 60 * 60 * 24
      })

      // gosso 파라미터: GOSSOcookie 평문 전달 → 그대로 쿠키 저장
      const gossoValue = searchParams.get('gosso')
      if (gossoValue) {
        redirectResponse.cookies.set('gosso', gossoValue, {
          httpOnly: false,
          secure: false,
          sameSite: 'lax',
          path: '/',
          maxAge: 60 * 60 * 24 // empno와 동일 24시간 (실제 만료는 LFON 세션에 의존)
        })
      }

      return redirectResponse
    } catch (error) {
      // 복호화 실패 시 로그인 페이지로 리다이렉트
      return NextResponse.redirect(new URL('/login', request.url))
    }
  }

  // 2. 로그인/설정 페이지는 인증 체크 스킵
  if (pathname === '/login' || pathname === '/unauthorized' || pathname === '/setup') {
    // 이미 인증된 사용자가 로그인 페이지 접근 시 홈으로
    const empno = request.cookies.get('empno')?.value
    const authToken = request.cookies.get('auth_token')?.value

    if (empno || authToken) {
      // JWT 토큰이 있으면 유효한지 확인
      if (authToken) {
        const tokenEmpno = await getEmpnoFromToken(authToken)
        if (tokenEmpno && pathname === '/login') {
          return NextResponse.redirect(new URL('/', request.url))
        }
      } else if (empno && pathname === '/login') {
        return NextResponse.redirect(new URL('/', request.url))
      }
    }

    return NextResponse.next()
  }

  // 3. 인증 확인: auth_token (JWT) → empno (SSO 쿠키) 순서
  let empno = request.cookies.get('empno')?.value || null
  const authToken = request.cookies.get('auth_token')?.value

  // JWT 토큰이 있으면 검증하고 empno 추출
  if (authToken) {
    const tokenEmpno = await getEmpnoFromToken(authToken)
    if (tokenEmpno) {
      empno = tokenEmpno
    } else {
      // JWT가 만료/무효 → 쿠키 삭제하고 로그인으로
      const loginRedirect = NextResponse.redirect(new URL('/login', request.url))
      loginRedirect.cookies.delete('auth_token')
      loginRedirect.cookies.delete('empno')
      return loginRedirect
    }
  }

  if (!empno) {
    // embed 경로에서는 리다이렉트 대신 401 (iframe 깨짐 방지)
    if (pathname.startsWith('/embed')) {
      return new NextResponse('Unauthorized', { status: 401 })
    }
    return NextResponse.redirect(new URL('/login', request.url))
  }

  // 4. Admin 페이지 권한 체크
  const adminUsers = (process.env.NEXT_PUBLIC_ADMIN_USERS || '').split(',').map(s => s.trim()).filter(Boolean);
  if (pathname.startsWith('/admin') && !adminUsers.includes(empno)) {
    return NextResponse.redirect(new URL('/unauthorized', request.url))
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
    '/((?!api|_next/static|_next/image|favicon.ico|logo\\.png|logo\\.svg|manifest\\.json|embed).*)',
  ],
}
