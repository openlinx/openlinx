"""Real Set-Cookie and Last-Modified headers, each with the stack that sends it and where its form
comes from. The cookie values are made up and long enough to be found if a column held them; the
attribute names, their order, letter case and date forms are the stacks' own."""

from dataclasses import dataclass
from datetime import UTC, datetime

# The cookie row from name to same_site.
type CookieColumns = tuple[
    str, str | None, str | None, datetime | None, int | None, bool, bool, bool, str | None
]


@dataclass(frozen=True, slots=True, kw_only=True)
class SetCookie:
    stack: str
    source: str
    header: str
    # The cookie's value, which no column may hold.
    value: str
    row: CookieColumns


@dataclass(frozen=True, slots=True, kw_only=True)
class LastModified:
    stack: str
    source: str
    header: str
    time: datetime


SET_COOKIES = (
    SetCookie(
        stack="PHP 8.4 session",
        source="php-src ext/session/session.c with the default session.cookie_path",
        header="PHPSESSID=8f2c1e9b7a6d5c4b3a2f1e0d9c8b7a6f; path=/",
        value="8f2c1e9b7a6d5c4b3a2f1e0d9c8b7a6f",
        row=("PHPSESSID", None, "/", None, None, False, False, False, None),
    ),
    SetCookie(
        stack="PHP 8.4 setcookie()",
        source="php-src ext/standard/head.c and head.h",
        header="remember_me=c4ca4238a0b923820dcc509a6f75849b; expires=Fri, 27 Nov 2026 10:00:00"
        " GMT; Max-Age=2592000; path=/; secure; HttpOnly; SameSite=Lax",
        value="c4ca4238a0b923820dcc509a6f75849b",
        row=(
            "remember_me",
            None,
            "/",
            datetime(2026, 11, 27, 10, tzinfo=UTC),
            2592000,
            True,
            True,
            False,
            "lax",
        ),
    ),
    SetCookie(
        stack="PHP 8.4 setcookie() without options",
        source="php-src ext/standard/head.c: no expires, path or domain given",
        header="cart_id=7d1e5f2a9c3b4e6f8a0b",
        value="7d1e5f2a9c3b4e6f8a0b",
        row=("cart_id", None, None, None, None, False, False, False, None),
    ),
    SetCookie(
        stack="Django 5 session",
        source="django.http.HttpResponse.set_cookie through CPython's http.cookies.Morsel",
        header="sessionid=k2v9x0qzq8f1v3m7e5r2t6y4u8i0o9p1; expires=Wed, 11 Nov 2026 10:00:00 GMT;"
        " HttpOnly; Max-Age=1209600; Path=/; SameSite=Lax",
        value="k2v9x0qzq8f1v3m7e5r2t6y4u8i0o9p1",
        row=(
            "sessionid",
            None,
            "/",
            datetime(2026, 11, 11, 10, tzinfo=UTC),
            1209600,
            False,
            True,
            False,
            "lax",
        ),
    ),
    SetCookie(
        stack="Django 5 CSRF",
        source="django.middleware.csrf through CPython's http.cookies.Morsel",
        header="csrftoken=Qm9vT2xkQ3NyZlRva2VuVmFsdWU; expires=Wed, 27 Oct 2027 10:00:00 GMT;"
        " Max-Age=31449600; Path=/; SameSite=Lax",
        value="Qm9vT2xkQ3NyZlRva2VuVmFsdWU",
        row=(
            "csrftoken",
            None,
            "/",
            datetime(2027, 10, 27, 10, tzinfo=UTC),
            31449600,
            False,
            False,
            False,
            "lax",
        ),
    ),
    SetCookie(
        stack="Rails 7 on Rack 3 session",
        source="rack lib/rack/utils.rb set_cookie_header",
        header="_shop_session=Wm9vYmFyU2Vzc2lvbkRhdGFIZXJl--3f9a1c7e; path=/; secure; httponly;"
        " samesite=lax",
        value="Wm9vYmFyU2Vzc2lvbkRhdGFIZXJl--3f9a1c7e",
        row=("_shop_session", None, "/", None, None, True, True, False, "lax"),
    ),
    SetCookie(
        stack="Express 4 with express-session",
        source="jshttp/cookie serialize",
        header="connect.sid=s%3AeXJ0dW9pcGFzZGZnaGprbA.kL2mN3oP4qR5sT6uV7wX8yZ9aB0; Path=/;"
        " Expires=Thu, 29 Oct 2026 10:00:00 GMT; HttpOnly; SameSite=Strict",
        value="s%3AeXJ0dW9pcGFzZGZnaGprbA.kL2mN3oP4qR5sT6uV7wX8yZ9aB0",
        row=(
            "connect.sid",
            None,
            "/",
            datetime(2026, 10, 29, 10, tzinfo=UTC),
            None,
            False,
            True,
            False,
            "strict",
        ),
    ),
    SetCookie(
        stack="nginx userid module, userid_expires max",
        source="nginx src/http/modules/ngx_http_userid_filter_module.c",
        header="uid=fwAAAWkNpSQ+LgVcAwMDAg==; expires=Thu, 31-Dec-37 23:55:55 GMT;"
        " domain=.example.test; path=/",
        value="fwAAAWkNpSQ+LgVcAwMDAg==",
        row=(
            "uid",
            "example.test",
            "/",
            datetime(2037, 12, 31, 23, 55, 55, tzinfo=UTC),
            None,
            False,
            False,
            False,
            None,
        ),
    ),
    SetCookie(
        stack="Cloudflare bot management",
        source="a response of www.cloudflare.com, 2026-10-28, over HTTP/2",
        header="__cf_bm=x5PDLxq0Zr7Kj2mWv8NcYt3Bh6Ga1Ue9Rs4Lp; HttpOnly; SameSite=None; Secure;"
        " Path=/; Domain=www.example.test; Expires=Wed, 28 Oct 2026 04:33:58 GMT",
        value="x5PDLxq0Zr7Kj2mWv8NcYt3Bh6Ga1Ue9Rs4Lp",
        row=(
            "__cf_bm",
            "www.example.test",
            "/",
            datetime(2026, 10, 28, 4, 33, 58, tzinfo=UTC),
            None,
            True,
            True,
            False,
            "none",
        ),
    ),
    SetCookie(
        stack="AWS Application Load Balancer stickiness",
        source="AWSALB as published in captured responses (oss-review-toolkit/ort issue 8669)",
        header="AWSALB=rlhopvySkjsYFSk30vL2SO3xIcok/rnQ98TEfEjWBgT5F9X+8Rc; Expires=Wed, 04 Nov"
        " 2026 07:00:00 GMT; Path=/",
        value="rlhopvySkjsYFSk30vL2SO3xIcok/rnQ98TEfEjWBgT5F9X+8Rc",
        row=(
            "AWSALB",
            None,
            "/",
            datetime(2026, 11, 4, 7, tzinfo=UTC),
            None,
            False,
            False,
            False,
            None,
        ),
    ),
    SetCookie(
        stack="AWS Application Load Balancer stickiness for CORS",
        source="AWSALBCORS as published in captured responses (oss-review-toolkit/ort issue 8669)",
        header="AWSALBCORS=Qk3x9Lm2Np7Rt5Vw1Yz8Ac4Ef6Gh0Jk; Expires=Wed, 04 Nov 2026 07:00:00 GMT;"
        " Path=/; SameSite=None; Secure",
        value="Qk3x9Lm2Np7Rt5Vw1Yz8Ac4Ef6Gh0Jk",
        row=(
            "AWSALBCORS",
            None,
            "/",
            datetime(2026, 11, 4, 7, tzinfo=UTC),
            None,
            True,
            False,
            False,
            "none",
        ),
    ),
    SetCookie(
        stack="an application's SameSite=Lax after which a proxy appends its own, misspelt",
        source="RFC 6265bis 5.6.7: an unknown SameSite is not ignored",
        header="sid=Zx8Wv7Ut6Sr5Qp4On3Ml2Kj1; Path=/; SameSite=Lax; SameSite=Foo",
        value="Zx8Wv7Ut6Sr5Qp4On3Ml2Kj1",
        row=("sid", None, "/", None, None, False, False, False, None),
    ),
)

LAST_MODIFIEDS = (
    LastModified(
        stack="nginx 1.31",
        source="a response of nginx.org, 2026-10-28",
        header="Thu, 22 Oct 2026 11:23:21 GMT",
        time=datetime(2026, 10, 22, 11, 23, 21, tzinfo=UTC),
    ),
    LastModified(
        stack="Apache httpd",
        source="a response of httpd.apache.org, 2026-10-28",
        header="Thu, 01 Oct 2026 13:38:42 GMT",
        time=datetime(2026, 10, 1, 13, 38, 42, tzinfo=UTC),
    ),
    LastModified(
        stack="Amazon S3",
        source="a response of s3.amazonaws.com, 2026-10-28",
        header="Wed, 21 Oct 2026 19:33:13 GMT",
        time=datetime(2026, 10, 21, 19, 33, 13, tzinfo=UTC),
    ),
    LastModified(
        stack="Microsoft Learn's origin",
        source="a response of learn.microsoft.com, 2026-10-28",
        header="Mon, 26 Oct 2026 23:10:26 GMT",
        time=datetime(2026, 10, 26, 23, 10, 26, tzinfo=UTC),
    ),
)
