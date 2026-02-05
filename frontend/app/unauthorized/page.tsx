export default function UnauthorizedPage() {
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="text-center space-y-4 px-4">
        <h1 className="text-3xl font-bold text-foreground">접근 권한 없음</h1>
        <p className="text-lg text-muted-foreground">
          정상적인 접근이 아닙니다. IT운영팀에 문의하세요!
        </p>
      </div>
    </div>
  )
}
