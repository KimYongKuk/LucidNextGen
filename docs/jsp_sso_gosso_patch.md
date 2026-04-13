# LFON JSP 수정안: GOSSOcookie 전달

## 목적
캘린더 일정 등록/수정/삭제 시 서비스 계정(wg0403) 대신 사용자 본인의 LFON 세션으로 API 호출하기 위해,
JSP 리다이렉트 시 GOSSOcookie 값을 AES 암호화하여 함께 전달합니다.

## 변경 전

```jsp
String action = "http://lucid.landf.co.kr/?empno=" + encStr;
```

## 변경 후

```jsp
<%@page import="com.daou.go.core.domain.User"%>
<%@page import="com.daou.go.core.session.SessionContext"%>
<%@page import="com.daou.go.core.service.UserService"%>
<%@page import="com.daou.go.integration.service.AESCipher"%>
<%@page import="java.net.URLEncoder"%>
<%@page import="org.springframework.web.context.support.WebApplicationContextUtils"%>
<%@page import="org.springframework.web.context.WebApplicationContext"%>
<%@ page language="java" contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<html>
<head>
<title>SLO</title>
<%
    WebApplicationContext wac = WebApplicationContextUtils.getWebApplicationContext(request.getServletContext());   
    UserService userService = (UserService)wac.getBean(UserService.class);
    SessionContext sessionContext = (SessionContext)wac.getBean(SessionContext.class);
    AESCipher aesipher = (AESCipher)wac.getBean(AESCipher.class);

    try {
        String key = "landf01234567890";

        User user = userService.get(sessionContext.getSessionUser().getId());
        String employeeNumber = user.getEmployeeNumber();

        // 사번 암호화 (기존)
        String encStr = URLEncoder.encode(aesipher.AES_Encode(employeeNumber, key));

        // GOSSOcookie 추출 및 암호화 (추가)
        String gossoParam = "";
        Cookie[] cookies = request.getCookies();
        if (cookies != null) {
            for (Cookie c : cookies) {
                if ("GOSSOcookie".equals(c.getName()) && c.getValue() != null && !c.getValue().isEmpty()) {
                    String encGosso = URLEncoder.encode(aesipher.AES_Encode(c.getValue(), key));
                    gossoParam = "&gosso=" + encGosso;
                    break;
                }
            }
        }

        String action = "http://lucid.landf.co.kr/?empno=" + encStr + gossoParam;
%>
<script type="text/javascript">
    location.href = '<%=action%>';
</script>
<%
    } catch(Exception e) {
        e.printStackTrace();
    }
%>
</head>
</body>
</html>
```

## 변경 요약

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| URL 파라미터 | `?empno=<enc>` | `?empno=<enc>&gosso=<enc>` |
| GOSSOcookie 처리 | 없음 | `request.getCookies()`에서 추출 → AES 암호화 → URL 파라미터 추가 |
| 하위 호환성 | - | gosso 쿠키가 없으면 gossoParam이 빈 문자열 → 기존과 동일하게 동작 |

## 배포 순서

1. **Lucid AI 서버 먼저 배포** (gosso 파라미터 없어도 기존대로 동작)
2. **LFON JSP 배포** (이후부터 gosso 파라미터 전달 시작)
3. 캘린더 등록/수정/삭제가 사용자 본인 세션으로 동작하는지 확인

## 보안 참고

- GOSSOcookie는 URL에 평문 노출하지 않음 (AES 암호화)
- 같은 AES 키(`landf01234567890`)로 암호화하므로 Lucid 서버에서 복호화 가능
- GOSSOcookie 세션 만료 시 → Lucid 서버가 서비스 계정으로 자동 폴백
