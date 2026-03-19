<%@page import="java.io.*"%>
<%@page import="java.util.*"%>
<%@page import="java.nio.charset.*"%>
<%@page import="java.util.regex.*"%>
<%@ page language="java" contentType="application/json; charset=UTF-8" pageEncoding="UTF-8"%>
<%!
    // ============================================================
    // lucid_mail.jsp - 사용자별 메일함 조회 API v2
    // ============================================================
    // v2 추가: action=detail (메일 전체 본문 조회)
    // 기존 action 변경: folder_no 필드 추가
    // ============================================================
    //
    // 사용법:
    //   action=inbox|sent|search|folders|unread (기존)
    //   action=detail&uid_no=9732&folder_no=1 (신규 - 전체 본문 조회)
    //
    // 인증: api_key 파라미터 필수
    // ============================================================

    private static final String SQLITE3_PATH = "/data/TerraceTims/3rd/sqlite3/bin/sqlite3";
    private static final String API_KEY = "0392d52daf9916ee83bb6b1ebf7e3857171fd6482c427d75ea6f068ce3bbeb73";

    /**
     * SQLite3 명령 실행
     */
    private String executeSqlite(String dbPath, String query) throws Exception {
        // 경로 검증 (path traversal 방지)
        if (dbPath.contains("..") || !dbPath.startsWith("/mindex/")) {
            throw new SecurityException("Invalid path");
        }

        String fullDbPath = dbPath + "/_mcache.db";
        ProcessBuilder pb = new ProcessBuilder(SQLITE3_PATH, "-separator", "|", fullDbPath, query);
        pb.redirectErrorStream(true);
        Process process = pb.start();

        BufferedReader reader = new BufferedReader(
            new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8)
        );
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            sb.append(line).append("\n");
        }
        process.waitFor();
        reader.close();
        return sb.toString().trim();
    }

    /**
     * MIME Base64 디코딩 (=?UTF-8?B?...?= 형식)
     */
    private String decodeMime(String encoded) {
        if (encoded == null || encoded.isEmpty()) return "";
        try {
            StringBuilder decoded = new StringBuilder();
            String remaining = encoded;
            while (remaining.contains("=?")) {
                int start = remaining.indexOf("=?");
                if (start > 0) {
                    decoded.append(remaining.substring(0, start).trim());
                }
                int secondQ = remaining.indexOf("?", start + 2);
                int thirdQ = remaining.indexOf("?", secondQ + 1);
                int end = remaining.indexOf("?=", thirdQ + 1);
                if (secondQ == -1 || thirdQ == -1 || end == -1) {
                    decoded.append(remaining);
                    break;
                }
                String charset = remaining.substring(start + 2, secondQ);
                String encoding = remaining.substring(secondQ + 1, thirdQ);
                String text = remaining.substring(thirdQ + 1, end);

                if (encoding.equalsIgnoreCase("B")) {
                    byte[] bytes = java.util.Base64.getDecoder().decode(text);
                    decoded.append(new String(bytes, Charset.forName(charset)));
                } else if (encoding.equalsIgnoreCase("Q")) {
                    // Quoted-Printable 디코딩
                    text = text.replace("_", " ");
                    StringBuilder qp = new StringBuilder();
                    for (int i = 0; i < text.length(); i++) {
                        if (text.charAt(i) == '=' && i + 2 < text.length()) {
                            int b = Integer.parseInt(text.substring(i + 1, i + 3), 16);
                            qp.append((char) b);
                            i += 2;
                        } else {
                            qp.append(text.charAt(i));
                        }
                    }
                    decoded.append(qp.toString());
                }
                remaining = remaining.substring(end + 2);
            }
            if (!remaining.isEmpty()) {
                decoded.append(remaining.trim());
            }
            return decoded.toString();
        } catch (Exception e) {
            return encoded;
        }
    }

    /**
     * IMAP ENVELOPE에서 주소 파싱 (from, to, cc 등 공통)
     */
    private String parseEnvelopeAddress(String envelope) {
        if (envelope == null || envelope.isEmpty()) return "";
        try {
            String inner = envelope.trim();
            if (inner.startsWith("((")) inner = inner.substring(1);
            if (inner.endsWith("))")) inner = inner.substring(0, inner.length() - 1);

            List<String> addresses = new ArrayList<>();
            int depth = 0;
            int start = -1;
            for (int i = 0; i < inner.length(); i++) {
                if (inner.charAt(i) == '(') {
                    if (depth == 0) start = i;
                    depth++;
                } else if (inner.charAt(i) == ')') {
                    depth--;
                    if (depth == 0 && start != -1) {
                        addresses.add(inner.substring(start + 1, i));
                        start = -1;
                    }
                }
            }

            if (addresses.isEmpty()) {
                addresses.add(inner.replace("(", "").replace(")", ""));
            }

            List<String> results = new ArrayList<>();
            for (String addr : addresses) {
                List<String> tokens = new ArrayList<>();
                int qi = 0;
                while (qi < addr.length()) {
                    if (addr.charAt(qi) == '"') {
                        int closeQ = addr.indexOf('"', qi + 1);
                        if (closeQ != -1) {
                            tokens.add(addr.substring(qi + 1, closeQ));
                            qi = closeQ + 1;
                        } else {
                            qi++;
                        }
                    } else if (addr.substring(qi).startsWith("NIL")) {
                        tokens.add(null);
                        qi += 3;
                    } else {
                        qi++;
                    }
                }

                String name = (tokens.size() > 0 && tokens.get(0) != null) ? decodeMime(tokens.get(0)) : "";
                String mailbox = (tokens.size() > 2 && tokens.get(2) != null) ? tokens.get(2) : "";
                String host = (tokens.size() > 3 && tokens.get(3) != null) ? tokens.get(3) : "";

                String email = mailbox.isEmpty() ? "" : (host.isEmpty() ? mailbox : mailbox + "@" + host);

                if (!name.isEmpty() && !email.isEmpty()) {
                    name = name.replace("'", "").trim();
                    results.add(name + " <" + email + ">");
                } else if (!email.isEmpty()) {
                    results.add(email);
                } else if (!name.isEmpty()) {
                    results.add(name);
                }
            }

            return String.join(", ", results);
        } catch (Exception e) {
            return envelope;
        }
    }

    /**
     * 문자열 앞뒤 따옴표 제거
     */
    private String stripQuotes(String s) {
        if (s == null) return "";
        s = s.trim();
        if (s.startsWith("\"") && s.endsWith("\"") && s.length() >= 2) {
            s = s.substring(1, s.length() - 1);
        }
        return s;
    }

    /**
     * JSON 문자열 이스케이프
     */
    private String jsonEscape(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }

    /**
     * HTML 엔티티 정리 (msg_preview용 - 기존)
     */
    private String cleanHtml(String s) {
        if (s == null) return "";
        return s.replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&#58;", ":")
                .replace("&#40;", "(")
                .replace("&#41;", ")")
                .replaceAll("\\s+", " ")
                .trim();
    }

    // ============================================================
    // v2 추가: .eml 본문 추출 관련 메서드
    // ============================================================

    /**
     * .eml 파일에서 본문 텍스트 추출 (스트리밍 방식)
     * 파일 전체를 메모리에 올리지 않고 헤더+텍스트 파트만 읽어 첨부파일 크기와 무관하게 동작
     */
    private String extractBodyFromEml(String filePath) {
        try {
            File file = new File(filePath);
            if (!file.exists()) return null;

            try (BufferedInputStream bis = new BufferedInputStream(new FileInputStream(file), 16384)) {
                // 1. 헤더 읽기 (빈 줄까지)
                StringBuilder headerSb = new StringBuilder(4096);
                String line;
                boolean headerDone = false;
                while ((line = readStreamLine(bis)) != null) {
                    if (line.isEmpty()) { headerDone = true; break; }
                    headerSb.append(line).append("\n");
                }
                if (!headerDone) return null;

                String headers = headerSb.toString();
                String contentType = getEmlHeaderValue(headers, "Content-Type");
                String cte = getEmlHeaderValue(headers, "Content-Transfer-Encoding");
                if (contentType == null) contentType = "text/plain; charset=utf-8";

                // single-part: 본문 직접 읽기 (최대 200KB)
                if (!contentType.toLowerCase().contains("multipart/")) {
                    byte[] bodyBytes = readStreamLimited(bis, 200 * 1024);
                    String charset = extractCharset(contentType);
                    String bodyText = decodeBodyContent(bodyBytes, cte, charset);
                    if (contentType.toLowerCase().contains("text/html")) {
                        bodyText = stripHtmlFull(bodyText);
                    }
                    return bodyText;
                }

                // multipart: boundary 기반 스트리밍 파싱
                String boundary = extractBoundary(contentType);
                if (boundary == null) return null;
                return scanMultipartStream(bis, boundary);
            }

        } catch (Exception e) {
            return "[본문 파싱 오류: " + e.getMessage() + "]";
        }
    }

    /**
     * 스트림에서 한 줄 읽기 (CRLF/LF 처리, ISO-8859-1)
     * 바이너리 파트 스킵 시에도 메모리 안전하도록 1줄 최대 1MB 제한
     */
    private String readStreamLine(BufferedInputStream bis) throws IOException {
        ByteArrayOutputStream baos = new ByteArrayOutputStream(256);
        int b;
        while ((b = bis.read()) != -1) {
            if (b == '\n') break;
            if (b == '\r') {
                bis.mark(1);
                int next = bis.read();
                if (next != '\n' && next != -1) bis.reset();
                break;
            }
            if (baos.size() < 1024 * 1024) {
                baos.write(b);
            }
        }
        if (b == -1 && baos.size() == 0) return null;
        return baos.toString("ISO-8859-1");
    }

    /**
     * 스트림에서 최대 maxBytes만큼 읽기
     */
    private byte[] readStreamLimited(BufferedInputStream bis, int maxBytes) throws IOException {
        ByteArrayOutputStream baos = new ByteArrayOutputStream(Math.min(maxBytes, 8192));
        byte[] buf = new byte[8192];
        int total = 0;
        int n;
        while (total < maxBytes && (n = bis.read(buf, 0, Math.min(buf.length, maxBytes - total))) != -1) {
            baos.write(buf, 0, n);
            total += n;
        }
        return baos.toByteArray();
    }

    /**
     * multipart 본문을 스트리밍으로 파싱 — text 파트만 버퍼링, 첨부는 스킵
     */
    private String scanMultipartStream(BufferedInputStream bis, String boundary) throws IOException {
        String textPlain = null;
        String textHtml = null;
        String delimiter = "--" + boundary;
        String endDelimiter = "--" + boundary + "--";

        // preamble 스킵, 첫 boundary 탐색
        String line;
        while ((line = readStreamLine(bis)) != null) {
            if (line.trim().equals(delimiter)) break;
            if (line.trim().equals(endDelimiter)) return null;
        }
        if (line == null) return null;

        // 파트 순회
        while (true) {
            // 파트 헤더 읽기
            StringBuilder partHeaderSb = new StringBuilder();
            while ((line = readStreamLine(bis)) != null) {
                if (line.trim().isEmpty()) break;
                partHeaderSb.append(line).append("\n");
            }
            if (line == null) break;

            String partHeaders = partHeaderSb.toString();
            String partCT = getEmlHeaderValue(partHeaders, "Content-Type");
            String partCTE = getEmlHeaderValue(partHeaders, "Content-Transfer-Encoding");
            if (partCT == null) partCT = "text/plain";
            String partCTLower = partCT.toLowerCase();

            String disposition = getEmlHeaderValue(partHeaders, "Content-Disposition");
            boolean isAttachment = disposition != null && disposition.toLowerCase().contains("attachment");

            // 중첩 multipart (재귀)
            if (partCTLower.contains("multipart/")) {
                String nestedBoundary = extractBoundary(partCT);
                if (nestedBoundary != null) {
                    String nested = scanMultipartStream(bis, nestedBoundary);
                    if (nested != null && !nested.trim().isEmpty()) return nested;
                }
                // 남은 내용을 부모 boundary까지 스킵
                while ((line = readStreamLine(bis)) != null) {
                    String t = line.trim();
                    if (t.equals(delimiter) || t.equals(endDelimiter)) break;
                }
                if (line == null || line.trim().equals(endDelimiter)) break;
                continue;
            }

            // 텍스트 파트인지 판별
            boolean isTextPart = !isAttachment &&
                (partCTLower.contains("text/plain") || partCTLower.contains("text/html"));

            // 파트 본문 읽기 (다음 boundary까지)
            ByteArrayOutputStream partBody = isTextPart ? new ByteArrayOutputStream(8192) : null;
            boolean hitEnd = false;

            while ((line = readStreamLine(bis)) != null) {
                String t = line.trim();
                if (t.equals(delimiter) || t.equals(endDelimiter)) {
                    hitEnd = t.equals(endDelimiter);
                    break;
                }
                // 텍스트 파트만 버퍼링 (최대 500KB), 나머지는 읽고 버림
                if (isTextPart && partBody.size() < 500 * 1024) {
                    partBody.write(line.getBytes(StandardCharsets.ISO_8859_1));
                    partBody.write('\n');
                }
            }

            if (isTextPart && partBody != null && partBody.size() > 0) {
                byte[] partBytes = partBody.toByteArray();
                String cs = extractCharset(partCT);
                String decoded = decodeBodyContent(partBytes, partCTE, cs);
                if (partCTLower.contains("text/plain")) {
                    textPlain = decoded;
                } else if (partCTLower.contains("text/html")) {
                    textHtml = stripHtmlFull(decoded);
                }
            }

            if (line == null || hitEnd) break;
        }

        if (textPlain != null && !textPlain.trim().isEmpty()) return textPlain;
        if (textHtml != null && !textHtml.trim().isEmpty()) return textHtml;
        return null;
    }

    /**
     * 이메일 헤더에서 특정 필드 값 추출 (multi-line folding 처리)
     */
    private String getEmlHeaderValue(String headers, String name) {
        String[] lines = headers.split("\r?\n");
        String lowerName = name.toLowerCase() + ":";
        StringBuilder value = null;

        for (String line : lines) {
            if (value != null) {
                if (line.startsWith(" ") || line.startsWith("\t")) {
                    value.append(" ").append(line.trim());
                } else {
                    break;
                }
            } else if (line.toLowerCase().startsWith(lowerName)) {
                value = new StringBuilder(line.substring(lowerName.length()).trim());
            }
        }

        return value != null ? value.toString() : null;
    }

    /**
     * Content-Type에서 charset 추출
     */
    private String extractCharset(String contentType) {
        if (contentType == null) return "UTF-8";
        String lower = contentType.toLowerCase();
        int idx = lower.indexOf("charset=");
        if (idx == -1) return "UTF-8";
        String cs = contentType.substring(idx + 8).trim();
        if (cs.startsWith("\"")) cs = cs.substring(1);
        int end = cs.indexOf(';');
        if (end != -1) cs = cs.substring(0, end);
        end = cs.indexOf('"');
        if (end != -1) cs = cs.substring(0, end);
        cs = cs.trim();
        // 한국어 charset 별칭
        if (cs.equalsIgnoreCase("ks_c_5601-1987") || cs.equalsIgnoreCase("ks_c_5601")) {
            cs = "EUC-KR";
        }
        return cs.isEmpty() ? "UTF-8" : cs;
    }

    /**
     * Content-Type에서 boundary 추출
     */
    private String extractBoundary(String contentType) {
        if (contentType == null) return null;
        String lower = contentType.toLowerCase();
        int idx = lower.indexOf("boundary=");
        if (idx == -1) return null;
        String boundary = contentType.substring(idx + 9).trim();
        if (boundary.startsWith("\"")) {
            int end = boundary.indexOf('"', 1);
            if (end != -1) boundary = boundary.substring(1, end);
        } else {
            int end = boundary.indexOf(';');
            if (end != -1) boundary = boundary.substring(0, end);
            end = boundary.indexOf(' ');
            if (end != -1) boundary = boundary.substring(0, end);
        }
        return boundary.trim();
    }

    /**
     * 본문 바이트를 CTE에 따라 디코딩하여 문자열로 변환
     */
    private String decodeBodyContent(byte[] bodyBytes, String cte, String charset) {
        try {
            if (cte == null) cte = "7bit";
            cte = cte.trim().toLowerCase();

            byte[] decoded;
            if (cte.equals("quoted-printable")) {
                // ISO-8859-1 문자열로 변환 후 QP 디코딩
                String bodyStr = new String(bodyBytes, StandardCharsets.ISO_8859_1);
                decoded = decodeQuotedPrintableBytes(bodyStr);
            } else if (cte.equals("base64")) {
                String bodyStr = new String(bodyBytes, StandardCharsets.US_ASCII).replaceAll("\\s", "");
                decoded = java.util.Base64.getDecoder().decode(bodyStr);
            } else {
                // 7bit, 8bit, binary
                decoded = bodyBytes;
            }

            return new String(decoded, Charset.forName(charset));
        } catch (Exception e) {
            // charset 실패 시 UTF-8 시도
            try {
                return new String(bodyBytes, StandardCharsets.UTF_8);
            } catch (Exception e2) {
                return new String(bodyBytes, StandardCharsets.ISO_8859_1);
            }
        }
    }

    /**
     * Quoted-Printable 디코딩 (바이트 배열 반환)
     */
    private byte[] decodeQuotedPrintableBytes(String input) {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        int i = 0;
        while (i < input.length()) {
            char c = input.charAt(i);
            if (c == '=') {
                // soft line break: =\r\n 또는 =\n
                if (i + 2 < input.length() && input.charAt(i + 1) == '\r' && input.charAt(i + 2) == '\n') {
                    i += 3;
                    continue;
                }
                if (i + 1 < input.length() && input.charAt(i + 1) == '\n') {
                    i += 2;
                    continue;
                }
                // hex 디코딩
                if (i + 2 < input.length()) {
                    String hex = input.substring(i + 1, i + 3);
                    try {
                        baos.write(Integer.parseInt(hex, 16));
                        i += 3;
                        continue;
                    } catch (NumberFormatException e) {
                        // 유효하지 않은 QP 시퀀스
                    }
                }
            }
            baos.write((byte) c);
            i++;
        }
        return baos.toByteArray();
    }

    /**
     * multipart 본문에서 텍스트 파트 추출
     * text/plain 우선, 없으면 text/html → 태그 제거
     */
    private String parseMultipartBody(String body, String boundary) {
        String textPlain = null;
        String textHtml = null;

        String delimiter = "--" + boundary;
        String[] parts = body.split(Pattern.quote(delimiter));

        for (String part : parts) {
            String trimmed = part.trim();
            if (trimmed.isEmpty() || trimmed.equals("--")) continue;
            // 종료 마커 ("--") 제거
            if (trimmed.startsWith("--")) continue;

            // 파트 헤더/본문 분리
            int partSplit = part.indexOf("\r\n\r\n");
            int partBodyOffset = 4;
            if (partSplit == -1) {
                partSplit = part.indexOf("\n\n");
                partBodyOffset = 2;
            }
            if (partSplit == -1) continue;

            String partHeaders = part.substring(0, partSplit);
            String partBodyStr = part.substring(partSplit + partBodyOffset);
            // 줄바꿈으로 시작하면 제거 (boundary 직후의 \r\n)
            if (partBodyStr.startsWith("\r\n")) partBodyStr = partBodyStr.substring(2);
            else if (partBodyStr.startsWith("\n")) partBodyStr = partBodyStr.substring(1);

            String partCT = getEmlHeaderValue(partHeaders, "Content-Type");
            String partCTE = getEmlHeaderValue(partHeaders, "Content-Transfer-Encoding");
            if (partCT == null) partCT = "text/plain";

            String partCTLower = partCT.toLowerCase();

            // 중첩 multipart (재귀)
            if (partCTLower.contains("multipart/")) {
                String nestedBoundary = extractBoundary(partCT);
                if (nestedBoundary != null) {
                    String nested = parseMultipartBody(partBodyStr, nestedBoundary);
                    if (nested != null && !nested.trim().isEmpty()) return nested;
                }
                continue;
            }

            // attachment는 건너뛰기
            String disposition = getEmlHeaderValue(partHeaders, "Content-Disposition");
            if (disposition != null && disposition.toLowerCase().contains("attachment")) continue;

            // text 파트 디코딩
            if (partCTLower.contains("text/plain")) {
                String cs = extractCharset(partCT);
                byte[] partBytes = partBodyStr.getBytes(StandardCharsets.ISO_8859_1);
                textPlain = decodeBodyContent(partBytes, partCTE, cs);
            } else if (partCTLower.contains("text/html")) {
                String cs = extractCharset(partCT);
                byte[] partBytes = partBodyStr.getBytes(StandardCharsets.ISO_8859_1);
                String decoded = decodeBodyContent(partBytes, partCTE, cs);
                textHtml = stripHtmlFull(decoded);
            }
        }

        // text/plain 우선, 없으면 text/html (태그 제거됨)
        if (textPlain != null && !textPlain.trim().isEmpty()) return textPlain;
        if (textHtml != null && !textHtml.trim().isEmpty()) return textHtml;
        return null;
    }

    /**
     * HTML 태그를 제거하고 순수 텍스트로 변환 (본문용 - 종합적)
     */
    private String stripHtmlFull(String html) {
        if (html == null) return "";
        // HTML 주석 제거
        html = html.replaceAll("(?s)<!--.*?-->", "");
        // style 블록 제거
        html = html.replaceAll("(?si)<style[^>]*>.*?</style>", "");
        // script 블록 제거
        html = html.replaceAll("(?si)<script[^>]*>.*?</script>", "");
        // <br> → 줄바꿈
        html = html.replaceAll("(?i)<br[^>]*>", "\n");
        // </p>, </div> → 줄바꿈
        html = html.replaceAll("(?i)</p>", "\n");
        html = html.replaceAll("(?i)</div>", "\n");
        // <li> → 목록 형태
        html = html.replaceAll("(?i)<li[^>]*>", "\n- ");
        // 테이블 구분
        html = html.replaceAll("(?i)</tr>", "\n");
        html = html.replaceAll("(?i)</td>", " | ");
        html = html.replaceAll("(?i)</th>", " | ");
        // 나머지 태그 제거
        html = html.replaceAll("<[^>]+>", "");
        // HTML 엔티티 디코딩
        html = html.replace("&amp;", "&")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                    .replace("&nbsp;", " ")
                    .replace("&quot;", "\"")
                    .replace("&#39;", "'")
                    .replace("&#58;", ":")
                    .replace("&#40;", "(")
                    .replace("&#41;", ")")
                    .replace("&middot;", "·")
                    .replace("&bull;", "•")
                    .replace("&ndash;", "–")
                    .replace("&mdash;", "—");
        // 숫자 엔티티 디코딩 (&#NNN;)
        Pattern numEntity = Pattern.compile("&#(\\d+);");
        Matcher matcher = numEntity.matcher(html);
        StringBuffer sb = new StringBuffer();
        while (matcher.find()) {
            try {
                int codePoint = Integer.parseInt(matcher.group(1));
                matcher.appendReplacement(sb, Matcher.quoteReplacement(String.valueOf((char) codePoint)));
            } catch (Exception e) {
                // 무시
            }
        }
        matcher.appendTail(sb);
        html = sb.toString();
        // 공백 정리
        html = html.replaceAll("[ \\t]+", " ");
        html = html.replaceAll("\\n[ \\t]+", "\n");
        html = html.replaceAll("\\n{3,}", "\n\n");
        return html.trim();
    }
%>
<%
    // ============================================================
    // 요청 파라미터 처리
    // ============================================================
    String apiKey = request.getParameter("api_key");
    String action = request.getParameter("action");
    String messageStore = request.getParameter("message_store");
    String keyword = request.getParameter("keyword");
    String limitStr = request.getParameter("limit");
    int limit = 10;

    // API 키 검증
    if (apiKey == null || !apiKey.equals(API_KEY)) {
        out.print("{\"error\": \"Unauthorized\", \"code\": 401}");
        return;
    }

    // 필수 파라미터 검증
    if (action == null || action.isEmpty()) {
        out.print("{\"error\": \"action parameter required (inbox|sent|search|folders|unread|detail)\", \"code\": 400}");
        return;
    }
    if (messageStore == null || messageStore.isEmpty()) {
        out.print("{\"error\": \"message_store parameter required\", \"code\": 400}");
        return;
    }

    try { if (limitStr != null) limit = Math.min(Integer.parseInt(limitStr), 100); }
    catch (NumberFormatException e) { limit = 10; }

    try {
        String query = "";
        String result = "";
        StringBuilder json = new StringBuilder();

        // ============================================================
        // action별 쿼리 실행
        // ============================================================
        switch (action) {

            // ----- 받은편지함 최근 N건 (v3: Inbox 하위폴더 포함) -----
            case "inbox":
                query = "SELECT m.uid_no, m.msg_receive, m.msg_date, m.msg_subject, m.msg_from, m.msg_to, m.msg_preview, m.msg_flag, m.msg_size, m.folder_no " +
                        "FROM mail_message m JOIN mail_folder f ON m.folder_no = f.folder_no " +
                        "WHERE (f.folder_name = 'Inbox' OR f.folder_name LIKE 'Inbox.%') " +
                        "ORDER BY m.msg_receive DESC LIMIT " + limit;
                result = executeSqlite(messageStore, query);
                json.append("{\"action\": \"inbox\", \"data\": [");
                if (!result.isEmpty()) {
                    String[] rows = result.split("\n");
                    for (int i = 0; i < rows.length; i++) {
                        String[] cols = rows[i].split("\\|", -1);
                        if (cols.length >= 9) {
                            if (i > 0) json.append(",");
                            json.append("{");
                            json.append("\"uid\":").append(cols[0]).append(",");
                            json.append("\"receive_ts\":").append(cols[1]).append(",");
                            json.append("\"date\":\"").append(jsonEscape(stripQuotes(cols[2]))).append("\",");
                            json.append("\"subject\":\"").append(jsonEscape(stripQuotes(decodeMime(stripQuotes(cols[3]))))).append("\",");
                            json.append("\"from\":\"").append(jsonEscape(parseEnvelopeAddress(cols[4]))).append("\",");
                            json.append("\"to\":\"").append(jsonEscape(parseEnvelopeAddress(cols[5]))).append("\",");
                            json.append("\"preview\":\"").append(jsonEscape(cleanHtml(cols[6]))).append("\",");
                            json.append("\"flag\":").append(cols[7]).append(",");
                            json.append("\"size\":").append(cols[8]);
                            if (cols.length >= 10) {
                                json.append(",\"folder_no\":").append(cols[9]);
                            }
                            json.append("}");
                        }
                    }
                }
                json.append("]}");
                break;

            // ----- 보낸편지함 최근 N건 (v2: folder_no 추가) -----
            case "sent":
                query = "SELECT m.uid_no, m.msg_receive, m.msg_date, m.msg_subject, m.msg_from, m.msg_to, m.msg_preview, m.msg_flag, m.msg_size, m.folder_no " +
                        "FROM mail_message m " +
                        "WHERE m.folder_no = (SELECT folder_no FROM mail_folder WHERE folder_name = 'Sent') " +
                        "ORDER BY m.msg_receive DESC LIMIT " + limit;
                result = executeSqlite(messageStore, query);
                json.append("{\"action\": \"sent\", \"data\": [");
                if (!result.isEmpty()) {
                    String[] rows = result.split("\n");
                    for (int i = 0; i < rows.length; i++) {
                        String[] cols = rows[i].split("\\|", -1);
                        if (cols.length >= 9) {
                            if (i > 0) json.append(",");
                            json.append("{");
                            json.append("\"uid\":").append(cols[0]).append(",");
                            json.append("\"receive_ts\":").append(cols[1]).append(",");
                            json.append("\"date\":\"").append(jsonEscape(stripQuotes(cols[2]))).append("\",");
                            json.append("\"subject\":\"").append(jsonEscape(stripQuotes(decodeMime(stripQuotes(cols[3]))))).append("\",");
                            json.append("\"from\":\"").append(jsonEscape(parseEnvelopeAddress(cols[4]))).append("\",");
                            json.append("\"to\":\"").append(jsonEscape(parseEnvelopeAddress(cols[5]))).append("\",");
                            json.append("\"preview\":\"").append(jsonEscape(cleanHtml(cols[6]))).append("\",");
                            json.append("\"flag\":").append(cols[7]).append(",");
                            json.append("\"size\":").append(cols[8]);
                            if (cols.length >= 10) {
                                json.append(",\"folder_no\":").append(cols[9]);
                            }
                            json.append("}");
                        }
                    }
                }
                json.append("]}");
                break;

            // ----- 키워드 검색 (v4: 하이브리드 — SQL LIKE + Java MIME 디코딩) -----
            // 1차: SQL LIKE로 msg_preview 전체 검색 (전 메일함, 건수 무제한)
            // 2차: 최근 1000건에서 Java MIME 디코딩 후 제목 매칭
            // 결과 병합 (uid_no 기준 중복 제거)
            case "search":
                if (keyword == null || keyword.isEmpty()) {
                    out.print("{\"error\": \"keyword parameter required for search\", \"code\": 400}");
                    return;
                }

                String lowerKeyword = keyword.toLowerCase();
                String escapedKw = keyword.replace("'", "''");

                // 1차: SQL LIKE — msg_preview에서 전체 메일 검색
                String sqlSearchQuery = "SELECT m.uid_no, m.msg_receive, m.msg_date, m.msg_subject, m.msg_from, m.msg_to, m.msg_preview, m.msg_flag, m.msg_size, f.folder_name, m.folder_no " +
                        "FROM mail_message m JOIN mail_folder f ON m.folder_no = f.folder_no " +
                        "WHERE m.msg_preview LIKE '%" + escapedKw + "%' " +
                        "ORDER BY m.msg_receive DESC LIMIT " + limit;
                String sqlSearchResult = executeSqlite(messageStore, sqlSearchQuery);

                // 2차: 최근 1000건에서 Java-side MIME 디코딩 후 제목/발신자 매칭
                String recentQuery = "SELECT m.uid_no, m.msg_receive, m.msg_date, m.msg_subject, m.msg_from, m.msg_to, m.msg_preview, m.msg_flag, m.msg_size, f.folder_name, m.folder_no " +
                        "FROM mail_message m JOIN mail_folder f ON m.folder_no = f.folder_no " +
                        "ORDER BY m.msg_receive DESC LIMIT 1000";
                String recentResult = executeSqlite(messageStore, recentQuery);

                // 결과 병합 (uid_no 기준 중복 제거, 순서 보존)
                LinkedHashMap<String, String[]> mergedResults = new LinkedHashMap<>();

                // SQL LIKE 결과 먼저 추가 (preview 본문 매칭 — 전 메일함 대상)
                if (!sqlSearchResult.isEmpty()) {
                    String[] rows = sqlSearchResult.split("\n");
                    for (String row : rows) {
                        String[] cols = row.split("\\|", -1);
                        if (cols.length >= 10) {
                            mergedResults.put(cols[0], cols);
                        }
                    }
                }

                // Java MIME 디코딩 결과 추가 (제목/발신자 매칭, 중복 제외)
                if (!recentResult.isEmpty()) {
                    String[] rows = recentResult.split("\n");
                    for (String row : rows) {
                        String[] cols = row.split("\\|", -1);
                        if (cols.length >= 10 && !mergedResults.containsKey(cols[0])) {
                            String decodedSubject = decodeMime(stripQuotes(cols[3]));
                            String fromAddr = parseEnvelopeAddress(cols[4]);
                            if (decodedSubject.toLowerCase().contains(lowerKeyword)
                                || fromAddr.toLowerCase().contains(lowerKeyword)) {
                                mergedResults.put(cols[0], cols);
                            }
                        }
                    }
                }

                // JSON 응답 생성
                json.append("{\"action\": \"search\", \"keyword\": \"").append(jsonEscape(keyword)).append("\", \"data\": [");
                int matchCount = 0;
                for (Map.Entry<String, String[]> entry : mergedResults.entrySet()) {
                    if (matchCount >= limit) break;
                    String[] cols = entry.getValue();
                    String decodedSubject = decodeMime(stripQuotes(cols[3]));
                    String fromAddr = parseEnvelopeAddress(cols[4]);
                    String previewText = cleanHtml(cols[6]);

                    if (matchCount > 0) json.append(",");
                    json.append("{");
                    json.append("\"uid\":").append(cols[0]).append(",");
                    json.append("\"receive_ts\":").append(cols[1]).append(",");
                    json.append("\"date\":\"").append(jsonEscape(stripQuotes(cols[2]))).append("\",");
                    json.append("\"subject\":\"").append(jsonEscape(decodedSubject)).append("\",");
                    json.append("\"from\":\"").append(jsonEscape(fromAddr)).append("\",");
                    json.append("\"to\":\"").append(jsonEscape(parseEnvelopeAddress(cols[5]))).append("\",");
                    json.append("\"preview\":\"").append(jsonEscape(previewText)).append("\",");
                    json.append("\"flag\":").append(cols[7]).append(",");
                    json.append("\"size\":").append(cols[8]).append(",");
                    json.append("\"folder\":\"").append(jsonEscape(cols[9])).append("\"");
                    if (cols.length >= 11) {
                        json.append(",\"folder_no\":").append(cols[10]);
                    }
                    json.append("}");
                    matchCount++;
                }
                json.append("]}");
                break;

            // ----- 메일함 목록 및 메일 수 (변경 없음) -----
            case "folders":
                query = "SELECT f.folder_no, f.folder_name, f.msg_count, f.unseen_count, f.disk_usage " +
                        "FROM mail_folder f ORDER BY f.msg_count DESC";
                result = executeSqlite(messageStore, query);
                json.append("{\"action\": \"folders\", \"data\": [");
                if (!result.isEmpty()) {
                    String[] rows = result.split("\n");
                    for (int i = 0; i < rows.length; i++) {
                        String[] cols = rows[i].split("\\|", -1);
                        if (cols.length >= 5) {
                            if (i > 0) json.append(",");
                            json.append("{");
                            json.append("\"folder_no\":").append(cols[0]).append(",");
                            json.append("\"folder_name\":\"").append(jsonEscape(decodeMime(cols[1]))).append("\",");
                            json.append("\"msg_count\":").append(cols[2].isEmpty() ? "0" : cols[2]).append(",");
                            json.append("\"unseen_count\":").append(cols[3].isEmpty() ? "0" : cols[3]).append(",");
                            json.append("\"disk_usage\":").append(cols[4].isEmpty() ? "0" : cols[4]);
                            json.append("}");
                        }
                    }
                }
                json.append("]}");
                break;

            // ----- 안읽은 메일 조회 (v2: folder_no 추가, v3: Inbox 하위폴더 포함) -----
            case "unread":
                // Inbox + Inbox.* 하위폴더 전체에서 안 읽은 메일 조회
                query = "SELECT m.uid_no, m.msg_receive, m.msg_date, m.msg_subject, m.msg_from, m.msg_to, m.msg_preview, m.msg_flag, m.msg_size, f.folder_name, m.folder_no " +
                        "FROM mail_message m JOIN mail_folder f ON m.folder_no = f.folder_no " +
                        "WHERE (f.folder_name = 'Inbox' OR f.folder_name LIKE 'Inbox.%') AND (m.msg_flag & 2) = 0 " +
                        "ORDER BY m.msg_receive DESC LIMIT " + limit;
                result = executeSqlite(messageStore, query);

                // 전체 안 읽은 메일 수 조회 (Inbox + 하위폴더)
                String countQuery = "SELECT COUNT(*) FROM mail_message m JOIN mail_folder f ON m.folder_no = f.folder_no " +
                        "WHERE (f.folder_name = 'Inbox' OR f.folder_name LIKE 'Inbox.%') AND (m.msg_flag & 2) = 0";
                String countResult = executeSqlite(messageStore, countQuery);
                int totalUnread = 0;
                try { totalUnread = Integer.parseInt(countResult.trim()); } catch (Exception e) { /* ignore */ }

                json.append("{\"action\": \"unread\", \"total_count\": ").append(totalUnread).append(", \"data\": [");
                if (!result.isEmpty()) {
                    String[] rows = result.split("\n");
                    for (int i = 0; i < rows.length; i++) {
                        String[] cols = rows[i].split("\\|", -1);
                        if (cols.length >= 10) {
                            if (i > 0) json.append(",");
                            json.append("{");
                            json.append("\"uid\":").append(cols[0]).append(",");
                            json.append("\"receive_ts\":").append(cols[1]).append(",");
                            json.append("\"date\":\"").append(jsonEscape(stripQuotes(cols[2]))).append("\",");
                            json.append("\"subject\":\"").append(jsonEscape(stripQuotes(decodeMime(stripQuotes(cols[3]))))).append("\",");
                            json.append("\"from\":\"").append(jsonEscape(parseEnvelopeAddress(cols[4]))).append("\",");
                            json.append("\"to\":\"").append(jsonEscape(parseEnvelopeAddress(cols[5]))).append("\",");
                            json.append("\"preview\":\"").append(jsonEscape(cleanHtml(cols[6]))).append("\",");
                            json.append("\"flag\":").append(cols[7]).append(",");
                            json.append("\"size\":").append(cols[8]).append(",");
                            json.append("\"folder\":\"").append(jsonEscape(cols[9])).append("\"");
                            if (cols.length >= 11) {
                                json.append(",\"folder_no\":").append(cols[10]);
                            }
                            json.append("}");
                        }
                    }
                }
                json.append("]}");
                break;

            // ----- v2 신규: 메일 전체 본문 조회 -----
            case "detail":
                String uidNoStr = request.getParameter("uid_no");
                String folderNoStr = request.getParameter("folder_no");

                if (uidNoStr == null || uidNoStr.isEmpty()) {
                    out.print("{\"error\": \"uid_no parameter required for detail\", \"code\": 400}");
                    return;
                }
                if (folderNoStr == null || folderNoStr.isEmpty()) {
                    out.print("{\"error\": \"folder_no parameter required for detail\", \"code\": 400}");
                    return;
                }

                // 정수 검증 (SQL injection 방지)
                int uidNo, folderNo;
                try {
                    uidNo = Integer.parseInt(uidNoStr);
                    folderNo = Integer.parseInt(folderNoStr);
                } catch (NumberFormatException e) {
                    out.print("{\"error\": \"uid_no and folder_no must be integers\", \"code\": 400}");
                    return;
                }

                // 1. 메일 메타데이터 + full_path 조회
                query = "SELECT m.full_path, m.msg_subject, m.msg_from, m.msg_to, m.msg_cc, m.msg_date, m.msg_flag, m.msg_size " +
                        "FROM mail_message m WHERE m.folder_no = " + folderNo + " AND m.uid_no = " + uidNo;
                result = executeSqlite(messageStore, query);

                if (result.isEmpty()) {
                    out.print("{\"error\": \"Mail not found\", \"code\": 404}");
                    return;
                }

                String[] detailCols = result.split("\\|", -1);
                if (detailCols.length < 8) {
                    out.print("{\"error\": \"Invalid data format\", \"code\": 500}");
                    return;
                }

                String fullPath = detailCols[0].trim();
                String dSubject = stripQuotes(detailCols[1]);
                String dFrom = detailCols[2];
                String dTo = detailCols[3];
                String dCc = detailCols[4];
                String dDate = stripQuotes(detailCols[5]);
                String dFlag = detailCols[6];
                String dSize = detailCols[7];

                // 2. .eml 파일에서 본문 추출
                String bodyText = "";
                boolean bodyTruncated = false;

                if (fullPath != null && !fullPath.isEmpty() && fullPath.startsWith("/mdata")) {
                    // 경로 보안 검증
                    if (fullPath.contains("..")) {
                        out.print("{\"error\": \"Invalid file path\", \"code\": 403}");
                        return;
                    }
                    try {
                        bodyText = extractBodyFromEml(fullPath);
                        if (bodyText == null) bodyText = "";
                        // 50,000자 제한
                        if (bodyText.length() > 50000) {
                            bodyText = bodyText.substring(0, 50000);
                            bodyTruncated = true;
                        }
                    } catch (Exception e) {
                        bodyText = "[본문 추출 실패: " + e.getMessage() + "]";
                    }
                } else {
                    // full_path가 없으면 preview 반환
                    String previewQuery = "SELECT msg_preview FROM mail_message WHERE folder_no = " + folderNo + " AND uid_no = " + uidNo;
                    String previewResult = executeSqlite(messageStore, previewQuery);
                    bodyText = "[미리보기] " + cleanHtml(previewResult);
                }

                // 3. JSON 응답
                json.append("{\"action\":\"detail\",\"data\":{");
                json.append("\"uid\":").append(uidNo).append(",");
                json.append("\"folder_no\":").append(folderNo).append(",");
                json.append("\"subject\":\"").append(jsonEscape(decodeMime(dSubject))).append("\",");
                json.append("\"from\":\"").append(jsonEscape(parseEnvelopeAddress(dFrom))).append("\",");
                json.append("\"to\":\"").append(jsonEscape(parseEnvelopeAddress(dTo))).append("\",");
                json.append("\"cc\":\"").append(jsonEscape(parseEnvelopeAddress(dCc))).append("\",");
                json.append("\"date\":\"").append(jsonEscape(dDate)).append("\",");
                json.append("\"flag\":").append(dFlag.isEmpty() ? "0" : dFlag).append(",");
                json.append("\"size\":").append(dSize.isEmpty() ? "0" : dSize).append(",");
                json.append("\"body\":\"").append(jsonEscape(bodyText)).append("\",");
                json.append("\"body_length\":").append(bodyText.length()).append(",");
                json.append("\"body_truncated\":").append(bodyTruncated);
                json.append("}}");
                break;

            default:
                json.append("{\"error\": \"Unknown action. Use: inbox, sent, search, folders, unread, detail\", \"code\": 400}");
        }

        out.print(json.toString());

    } catch (SecurityException se) {
        out.print("{\"error\": \"" + jsonEscape(se.getMessage()) + "\", \"code\": 403}");
    } catch (Exception e) {
        out.print("{\"error\": \"" + jsonEscape(e.getMessage()) + "\", \"code\": 500}");
    }
%>
