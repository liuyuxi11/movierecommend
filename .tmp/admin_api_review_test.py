"""One-off integration check for administrator APIs on movierecommend_test."""

from __future__ import annotations

import json
import os
import random
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from dotenv import dotenv_values


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = dotenv_values(os.path.join(ROOT, ".env"))
SCHEMA = urlsplit(CONFIG.get("DATABASE_URL", "")).path.lstrip("/")
if SCHEMA != "movierecommend_test":
    raise SystemExit(f"Refusing mutating API tests: configured schema is {SCHEMA!r}")

BASE_URL = os.getenv("ADMIN_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_USERNAME = os.getenv("ADMIN_TEST_USERNAME", "Yohana")
ADMIN_PASSWORD = os.getenv("ADMIN_TEST_PASSWORD")
if not ADMIN_PASSWORD:
    raise SystemExit("Set ADMIN_TEST_PASSWORD in the invoking PowerShell process")


def request(method: str, path: str, *, body=None, token: str | None = None):
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"detail": "non-json error response"}
        return exc.code, payload
    except URLError as exc:
        raise RuntimeError(f"API request failed for {method} {path}: {type(exc.reason).__name__}") from exc


passed = 0
failed: list[str] = []


def check(name: str, method: str, path: str, expected: int, *, body=None, token=None):
    global passed
    code, payload = request(method, path, body=body, token=token)
    if code == expected:
        passed += 1
        print(f"PASS {name} http={code}")
    else:
        failed.append(f"{name}: expected {expected}, got {code}")
        print(f"FAIL {name} expected={expected} actual={code} detail={payload.get('detail', '')}")
    return payload if code == expected else None


def login(username: str, password: str, expected: int = 200):
    code, payload = request("POST", "/api/admin/login", body={"username": username, "password": password})
    if code != expected:
        failed.append(f"login {username}: expected {expected}, got {code}")
        print(f"FAIL login_{username} expected={expected} actual={code}")
        return None
    print(f"PASS login_{username} http={code}")
    return payload.get("data")


suffix = uuid4().hex[:12]
test_user_name = f"api_review_{suffix}"
test_email = f"api-review-{suffix}@example.com"
test_phone = str(random.randrange(10**10, 10**11))
test_admin_name = f"api_review_admin_{suffix}"
test_admin_password = f"ReviewPass{suffix[:4]}7"
test_category_name = f"api-review-{suffix}"
test_category_id = None
test_movie_id = random.randrange(1_800_000_000, 2_000_000_000)
test_user_id = None
test_admin_id = None
test_movie_created = False
test_user_token = None

try:
    admin_data = login(ADMIN_USERNAME, ADMIN_PASSWORD)
    if not admin_data:
        raise SystemExit("Cannot run administrator tests without a successful Yohana login")
    admin_token = admin_data["access_token"]
    admin_id = int(admin_data["adminid"]) if "adminid" in admin_data else None

    check("admin_me", "GET", "/api/admin/me", 200, token=admin_token)
    check("admin_me_requires_auth", "GET", "/api/admin/me", 401)
    check("superadmin_user_list", "GET", "/api/admin/users?page=1&page_size=2&status=active", 200, token=admin_token)
    check("superadmin_account_list", "GET", "/api/admin/accounts", 200, token=admin_token)
    check("audit_log_list", "GET", "/api/admin/audit/logs?page=1&page_size=2", 200, token=admin_token)
    check("audit_like_event_list", "GET", "/api/admin/audit/like-events?page=1&page_size=2&action=like", 200, token=admin_token)
    check("analytics_overview", "GET", "/api/analytics/overview", 200, token=admin_token)
    for state in ("pending", "accepted", "rejected"):
        check(f"report_list_{state}", "GET", f"/api/comments/admin/reports?status={state}&page=1&page_size=2", 200, token=admin_token)

    # Exercise refresh rotation without invalidating Yohana's active access token.
    refresh_payload = request("POST", "/api/admin/login", body={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})[1]["data"]
    refresh = check("admin_refresh_first_use", "POST", "/api/admin/refresh", 200,
                    body={"refresh_token": refresh_payload["refresh_token"]})
    check("admin_refresh_replay_rejected", "POST", "/api/admin/refresh", 401,
          body={"refresh_token": refresh_payload["refresh_token"]})
    if refresh:
        check("refreshed_admin_access", "GET", "/api/admin/me", 200,
              token=refresh["data"]["access_token"])

    # Self-protection should reject these requests without changing Yohana.
    yohana_id = request("GET", "/api/admin/me", token=admin_token)[1]["data"]["adminid"]
    check("cannot_disable_self", "PUT", f"/api/admin/accounts/{yohana_id}", 400,
          body={"status": "disabled"}, token=admin_token)
    check("cannot_delete_self", "DELETE", f"/api/admin/accounts/{yohana_id}", 400, token=admin_token)

    user_body = {
        "username": test_user_name,
        "password": "ReviewUser123",
        "confirm_password": "ReviewUser123",
        "email": test_email,
        "phone": test_phone,
    }
    created_user = check("create_disposable_user", "POST", "/api/auth/register", 201, body=user_body)
    if created_user:
        test_user_id = int(created_user["userid"])
        user_login = request("POST", "/api/auth/login", body={"account": test_user_name, "password": "ReviewUser123"})
        if user_login[0] == 200:
            test_user_token = user_login[1]["access_token"]
            passed += 1
            print("PASS disposable_user_login http=200")
        else:
            failed.append(f"disposable user login expected 200, got {user_login[0]}")

        check("superadmin_disable_user", "PUT", f"/api/admin/users/{test_user_id}", 200,
              body={"status": "disabled"}, token=admin_token)
        disabled_login = request("POST", "/api/auth/login", body={"account": test_user_name, "password": "ReviewUser123"})
        if disabled_login[0] == 401:
            passed += 1
            print("PASS disabled_user_login_rejected http=401")
        else:
            failed.append(f"disabled user login expected 401, got {disabled_login[0]}")
            print(f"FAIL disabled_user_login_rejected actual={disabled_login[0]}")
        check("superadmin_reenable_user", "PUT", f"/api/admin/users/{test_user_id}", 200,
              body={"status": "active"}, token=admin_token)
        reenabled_login = request("POST", "/api/auth/login", body={"account": test_user_name, "password": "ReviewUser123"})
        if reenabled_login[0] == 200:
            test_user_token = reenabled_login[1]["access_token"]
            passed += 1
            print("PASS reenabled_user_login http=200")
        else:
            failed.append(f"reenabled user login expected 200, got {reenabled_login[0]}")
            test_user_token = None

    temp_admin = check("create_disposable_admin", "POST", "/api/admin/accounts", 201,
                       body={"username": test_admin_name, "password": test_admin_password, "role": "admin"},
                       token=admin_token)
    if temp_admin:
        test_admin_id = int(temp_admin["data"]["adminid"])
        temp_login = login(test_admin_name, test_admin_password)
        if temp_login:
            normal_token = temp_login["access_token"]
            check("normal_admin_cannot_list_users", "GET", "/api/admin/users?page=1&page_size=1", 403, token=normal_token)
            check("normal_admin_cannot_list_admins", "GET", "/api/admin/accounts", 403, token=normal_token)

        check("change_admin_role", "PUT", f"/api/admin/accounts/{test_admin_id}", 200,
              body={"role": "superadmin"}, token=admin_token)
        promoted = login(test_admin_name, test_admin_password)
        if promoted and promoted.get("role") == "superadmin":
            passed += 1
            print("PASS promoted_admin_role http=200")
        else:
            failed.append("promoted admin login did not return superadmin role")
        check("disable_admin_account", "PUT", f"/api/admin/accounts/{test_admin_id}", 200,
              body={"status": "disabled"}, token=admin_token)
        login(test_admin_name, test_admin_password, expected=401)
        check("reactivate_admin_account", "PUT", f"/api/admin/accounts/{test_admin_id}", 200,
              body={"role": "admin", "status": "active"}, token=admin_token)
        active_temp = login(test_admin_name, test_admin_password)
        if active_temp:
            check("admin_logout", "POST", "/api/admin/logout", 200, token=active_temp["access_token"])
            check("logout_invalidates_access", "GET", "/api/admin/me", 401, token=active_temp["access_token"])
            active_again = login(test_admin_name, test_admin_password)
            if active_again:
                normal_token = active_again["access_token"]

    category = check("create_test_category", "POST", "/api/movies/categories", 201,
                     body={"name": test_category_name}, token=admin_token)
    if category:
        test_category_id = int(category["data"]["categoryid"])
        check("update_test_category", "PUT", f"/api/movies/categories/{test_category_id}", 200,
              body={"name": f"{test_category_name}-updated"}, token=admin_token)

    movie_body = {
        "movieid": test_movie_id,
        "moviename": f"API Review Movie {suffix}",
        "typelist": "Drama",
        "category_ids": [test_category_id] if test_category_id else [],
    }
    movie = check("normal_admin_create_movie", "POST", "/api/movies", 201,
                  body=movie_body, token=(normal_token if 'normal_token' in locals() else admin_token))
    test_movie_created = bool(movie)
    if movie:
        check("update_test_movie", "PUT", f"/api/movies/{test_movie_id}", 200,
              body={"moviename": f"API Review Movie Updated {suffix}", "category_ids": [test_category_id] if test_category_id else []},
              token=admin_token)

        if test_user_token:
            for resolution in ("accepted", "rejected"):
                comment = check(f"create_comment_{resolution}", "POST", "/api/comments", 201,
                                body={"movieid": test_movie_id, "content": f"Temporary API review {resolution} {suffix}"},
                                token=test_user_token)
                if not comment:
                    continue
                comment_id = comment["data"]["commentid"]
                report = check(f"create_report_{resolution}", "POST", f"/api/comments/{comment_id}/reports", 201,
                               body={"reason_code": "advertisement"}, token=test_user_token)
                if report:
                    report_id = report["data"]["reportid"]
                    check(f"duplicate_report_{resolution}", "POST", f"/api/comments/{comment_id}/reports", 409,
                          body={"reason_code": "advertisement"}, token=test_user_token)
                    check(f"decide_report_{resolution}", "PUT", f"/api/comments/admin/reports/{report_id}", 200,
                          body={"status": resolution}, token=admin_token)
                    check(f"decide_report_twice_{resolution}", "PUT", f"/api/comments/admin/reports/{report_id}", 409,
                          body={"status": "rejected" if resolution == "accepted" else "accepted"}, token=admin_token)
                    visible = check(f"comments_after_{resolution}", "GET",
                                    f"/api/comments/movies/{test_movie_id}/comments?page=1&page_size=100", 200)
                    visible_ids = {row["commentid"] for row in visible["data"]["items"]} if visible else set()
                    should_show = resolution == "rejected"
                    if (comment_id in visible_ids) == should_show:
                        passed += 1
                        print(f"PASS report_{resolution}_visibility")
                    else:
                        failed.append(f"comment visibility after {resolution} decision was incorrect")
                        print(f"FAIL report_{resolution}_visibility")
                check(f"admin_soft_delete_comment_{resolution}", "DELETE", f"/api/comments/admin/{comment_id}", 200,
                      token=admin_token)

        if test_category_id:
            check("soft_delete_test_category", "DELETE", f"/api/movies/categories/{test_category_id}", 200, token=admin_token)
            detail = check("movie_detail_after_category_delete", "GET", f"/api/movies/{test_movie_id}", 200)
            if detail and not any(item.get("categoryid") == test_category_id for item in detail["data"].get("categories", [])):
                passed += 1
                print("PASS category_delete_clears_movie_relation")
            else:
                failed.append("soft-deleted category remained attached to movie")
                print("FAIL category_delete_clears_movie_relation")
            test_category_id = None

        check("soft_delete_test_movie", "DELETE", f"/api/movies/{test_movie_id}", 200, token=admin_token)
        test_movie_created = False
        check("deleted_movie_hidden", "GET", f"/api/movies/{test_movie_id}", 404)

    if test_user_id:
        check("soft_delete_disposable_user", "DELETE", f"/api/admin/users/{test_user_id}", 200, token=admin_token)
        test_user_id = None

    if test_admin_id:
        check("soft_delete_disposable_admin", "DELETE", f"/api/admin/accounts/{test_admin_id}", 200, token=admin_token)
        test_admin_id = None
    if test_user_id:
        # User may already be soft-deleted; a second delete should be a 404 and is harmless.
        status_code, _ = request("DELETE", f"/api/admin/users/{test_user_id}", token=admin_token)
        if status_code in (200, 404):
            passed += 1
            print(f"PASS disposable_user_cleanup http={status_code}")
        else:
            failed.append(f"disposable user cleanup returned {status_code}")
        test_user_id = None

    check("audit_log_filter_admin_create", "GET", "/api/admin/audit/logs?page=1&page_size=10&action=admin.create", 200, token=admin_token)
    check("audit_log_filter_report_decision", "GET", "/api/admin/audit/logs?page=1&page_size=10&action=comment.report_decide", 200, token=admin_token)

finally:
    # Best-effort soft-delete cleanup if an assertion or request interrupted the workflow.
    try:
        if "admin_token" in locals():
            if test_movie_created:
                request("DELETE", f"/api/movies/{test_movie_id}", token=admin_token)
            if test_category_id is not None:
                request("DELETE", f"/api/movies/categories/{test_category_id}", token=admin_token)
            if test_admin_id is not None:
                request("DELETE", f"/api/admin/accounts/{test_admin_id}", token=admin_token)
            if test_user_id is not None:
                request("DELETE", f"/api/admin/users/{test_user_id}", token=admin_token)
    except Exception as exc:
        print(f"CLEANUP_WARNING type={type(exc).__name__}")

print(f"RESULT passed={passed} failed={len(failed)} schema={SCHEMA}")
for message in failed:
    print(f"FAIL_DETAIL {message}")
raise SystemExit(1 if failed else 0)
