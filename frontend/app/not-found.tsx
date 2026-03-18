export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-950 text-gray-100">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-gray-500">404</h1>
        <p className="mt-4 text-lg text-gray-400">페이지를 찾을 수 없습니다.</p>
        <a href="/" className="mt-6 inline-block text-blue-400 hover:underline">
          홈으로 돌아가기
        </a>
      </div>
    </div>
  );
}
