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
     * .eml 파일에서 본문 텍스트 추출
     */
    private String extractBodyFromEml(String filePath) {
        try {
            File file = new File(filePath);
            if (!file.exists()) return null;
            if (file.length() > 5 * 1024 * 1024) return "[파일 크기 초과 (5MB 제한)]";

            // 파일을 ISO-8859-1로 읽기 (바이트 보존, 헤더 파싱 안전)
            byte[] fileBytes = new byte[(int) file.length()];
            FileInputStream fis = new FileInputStream(file);
            int bytesRead = fis.read(fileBytes);
            fis.close();
            if (bytesRead <= 0) return null;

            String rawContent = new String(fileBytes, StandardCharsets.ISO_8859_1);

            // 헤더와 본문 분리
            int headerEnd = rawContent.indexOf("\r\n\r\n");
            int bodyStart = 4;
            if (headerEnd == -1) {
                headerEnd = rawContent.indexOf("\n\n");
                bodyStart = 2;
            }
            if (headerEnd == -1) return null;

            String headers = rawContent.substring(0, headerEnd);
            byte[] bodyBytes = Arrays.copyOfRange(fileBytes, headerEnd + bodyStart, bytesRead);

            // Content-Type, Content-Transfer-Encoding 파싱
            String contentType = getEmlHeaderValue(headers, "Content-Type");
            String cte = getEmlHeaderValue(headers, "Content-Transfer-Encoding");
            if (contentType == null) contentType = "text/plain; charset=utf-8";

            // multipart 처리
            if (contentType.toLowerCase().contains("multipart/")) {
                String boundary = extractBoundary(contentType);
                if (boundary != null) {
                    String bodyStr = new String(bodyBytes, StandardCharsets.ISO_8859_1);
                    String extracted = parseMultipartBody(bodyStr, boundary);
                    if (extracted != null && !extracted.trim().isEmpty()) return extracted;
                }
                return null;
            }

            // single-part 본문 디코딩
            String charset = extractCharset(contentType);
            String bodyText = decodeBodyContent(bodyBytes, cte, charset);

            // HTML → 텍스트
            if (contentType.toLowerCase().contains("text/html")) {
                bodyText = stripHtmlFull(bodyText);
            }

            return bodyText;

        } catch (Exception e) {
            return "[본문 파싱 오류: " + e.getMessage() + "]";
        }
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

            // ----- 받은편지함 최근 N건 (v2: folder_no 추가) -----
            case "inbox":
                query = "SELECT m.uid_no, m.msg_receive, m.msg_date, m.msg_subject, m.msg_from, m.msg_to, m.msg_preview, m.msg_flag, m.msg_size, m.folder_no " +
                        "FROM mail_message m " +
                        "WHERE m.folder_no = (SELECT folder_no FROM mail_folder WHERE folder_name = 'Inbox') " +
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

            // ----- 키워드 검색 (v2: folder_no 추가) -----
            case "search":
                if (keyword == null || keyword.isEmpty()) {
                    out.print("{\"error\": \"keyword parameter required for search\", \"code\": 400}");
                    return;
                }
                String safeKeyword = keyword.replace("'", "''");
                query = "SELECT m.uid_no, m.msg_receive, m.msg_date, m.msg_subject, m.msg_from, m.msg_to, m.msg_preview, m.msg_flag, m.msg_size, f.folder_name, m.folder_no " +
                        "FROM mail_message m JOIN mail_folder f ON m.folder_no = f.folder_no " +
                        "WHERE (m.msg_preview LIKE '%" + safeKeyword + "%' " +
                        "OR m.msg_subject LIKE '%" + safeKeyword + "%' " +
                        "OR m.msg_from LIKE '%" + safeKeyword + "%') " +
                        "ORDER BY m.msg_receive DESC LIMIT " + limit;
                result = executeSqlite(messageStore, query);
                json.append("{\"action\": \"search\", \"keyword\": \"").append(jsonEscape(keyword)).append("\", \"data\": [");
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

            // ----- 안읽은 메일 조회 (v2: folder_no 추가) -----
            case "unread":
                query = "SELECT m.uid_no, m.msg_receive, m.msg_date, m.msg_subject, m.msg_from, m.msg_to, m.msg_preview, m.msg_flag, m.msg_size, f.folder_name, m.folder_no " +
                        "FROM mail_message m JOIN mail_folder f ON m.folder_no = f.folder_no " +
                        "WHERE f.folder_name = 'Inbox' AND (m.msg_flag & 2) = 0 " +
                        "ORDER BY m.msg_receive DESC LIMIT " + limit;
                result = executeSqlite(messageStore, query);
                json.append("{\"action\": \"unread\", \"data\": [");
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
