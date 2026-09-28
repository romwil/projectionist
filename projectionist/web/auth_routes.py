"""Auth, household users, invites, and access-request HTTP routes.

Registered via ``register_auth_routes`` so app.py stays the composition root.
"""


def register_auth_routes(app):
    """Attach auth / household routes to the FastAPI app."""
    from typing import Any, Dict, Literal, Optional

    from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
    from fastapi.responses import FileResponse, JSONResponse
    from pydantic import BaseModel, Field

    import projectionist.web.app as app_mod

    AccessRequestApprovePayload = app_mod.AccessRequestApprovePayload
    AuthMeUpdatePayload = app_mod.AuthMeUpdatePayload
    DATA_DIR = app_mod.DATA_DIR
    DEFAULT_TTL_SECONDS = app_mod.DEFAULT_TTL_SECONDS
    InviteConflict = app_mod.InviteConflict
    InviteCreatePayload = app_mod.InviteCreatePayload
    InviteRedeemLocalPayload = app_mod.InviteRedeemLocalPayload
    LocalLoginPayload = app_mod.LocalLoginPayload
    LocalRegisterPayload = app_mod.LocalRegisterPayload
    MemoryAccessError = app_mod.MemoryAccessError
    MyAppriseTestPayload = app_mod.MyAppriseTestPayload
    PlexLoginPayload = app_mod.PlexLoginPayload
    SESSION_COOKIE_NAME = app_mod.SESSION_COOKIE_NAME
    SeerrSyncPayload = app_mod.SeerrSyncPayload
    UserMemoryService = app_mod.UserMemoryService
    UserUpdatePayload = app_mod.UserUpdatePayload
    _db = app_mod._db
    _safe_error_detail = app_mod._safe_error_detail
    _settings = app_mod._settings
    authenticate_local_user = app_mod.authenticate_local_user
    authenticate_plex_user = app_mod.authenticate_plex_user
    clear_pin_nonce_cookie = app_mod.clear_pin_nonce_cookie
    clear_session_cookie = app_mod.clear_session_cookie
    enforce_rate_limit = app_mod.enforce_rate_limit
    get_current_user_dep = app_mod.get_current_user_dep
    handle_oidc_callback = app_mod.handle_oidc_callback
    link_plex_identity = app_mod.link_plex_identity
    peek_plex_pin_authorized = app_mod.peek_plex_pin_authorized
    poll_plex_pin_login = app_mod.poll_plex_pin_login
    register_local_user = app_mod.register_local_user
    require_role = app_mod.require_role
    set_session_cookie = app_mod.set_session_cookie
    start_oidc_authorize = app_mod.start_oidc_authorize
    start_plex_pin_login = app_mod.start_plex_pin_login
    sync_user_seerr_from_token = app_mod.sync_user_seerr_from_token
    time = app_mod.time
    uuid = app_mod.uuid

    router = APIRouter(tags=["auth"])

    @router.get("/api/auth/me")
    def auth_me(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
        return {"user": user.to_dict(), "authenticated": True}


    def _memory_service() -> UserMemoryService:
        return UserMemoryService(_db())


    @router.get("/api/me/memory")
    def export_my_memory(
        format: Literal["json", "markdown"] = "json",
        user=Depends(get_current_user_dep),
    ):
        payload = _db().export_user_memory(user.id)
        if format == "json":
            return JSONResponse(
                content=payload,
                headers={"Content-Disposition": 'attachment; filename="curatorx-memory.json"'},
            )
        lines = ["# CuratorX memory export", ""]

        lines.append("## Private notes")
        if payload["notes"]:
            for note in payload["notes"]:
                lines.extend([f"### {note['kind']}", note["text"], ""])
        else:
            lines.extend(["_No private notes._", ""])

        lines.append("## Saved library pages")
        saved_pages = payload.get("saved_library_pages") or []
        if saved_pages:
            for page in saved_pages:
                summary = (page.get("summary") or "").strip()
                lines.append(f"### {page.get('name', 'Untitled')}")
                if summary:
                    lines.append(summary)
                lines.append("")
        else:
            lines.extend(["_No saved library pages._", ""])

        lines.append("## Chat threads")
        chat_threads = payload.get("chat_threads") or []
        if chat_threads:
            for thread in chat_threads:
                messages = thread.get("messages") or []
                lines.append(f"### {thread.get('thread_title') or 'Conversation'}")
                lines.append(f"_{len(messages)} message(s)._")
                lines.append("")
        else:
            lines.extend(["_No chat threads._", ""])

        lines.append("## Preference facts")
        preference_facts = payload.get("preference_facts") or []
        if preference_facts:
            for fact in preference_facts:
                lines.append(f"- **{fact.get('signal_type', 'signal')}**: {fact.get('text', '')}")
            lines.append("")
        else:
            lines.extend(["_No preference facts._", ""])

        return Response(
            content="\n".join(lines),
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="curatorx-memory.md"'},
        )


    @router.delete("/api/me/memory")
    def purge_my_memory(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
        """Hard-delete private notes and every private chat transcript together."""
        return {"purged": _db().purge_user_memory_and_chats(user.id)}


    @router.get("/api/users/{user_id}/memory")
    def review_youth_memory(user_id: str, user=Depends(require_role("owner"))) -> Dict[str, Any]:
        try:
            notes = _memory_service().recall(
                caller_id=user.id, caller_role=user.role, target_id=user_id, limit=500
            )
        except MemoryAccessError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        return {"user_id": user_id, "notes": notes}


    @router.patch("/api/auth/me")
    def patch_auth_me(
        payload: AuthMeUpdatePayload,
        user=Depends(get_current_user_dep),
    ) -> Dict[str, Any]:
        """Self-service profile updates (preferred conversation name, UI prefs)."""
        from projectionist.web.avatars import resolve_avatar_url

        fields_set = getattr(payload, "model_fields_set", None) or getattr(payload, "__fields_set__", set())
        updates: Dict[str, Any] = {}
        if "preferred_name" in fields_set:
            updates["preferred_name"] = payload.preferred_name
        if "ui_font_size" in fields_set:
            updates["ui_font_size"] = payload.ui_font_size
        if "ui_theme" in fields_set:
            updates["ui_theme"] = payload.ui_theme
        if "notification_email" in fields_set:
            updates["notification_email"] = payload.notification_email
        if "notify_channel_inbox" in fields_set:
            updates["notify_channel_inbox"] = payload.notify_channel_inbox
        if "notify_channel_email" in fields_set:
            updates["notify_channel_email"] = payload.notify_channel_email
        if "newsletter_opt_in" in fields_set:
            updates["newsletter_opt_in"] = payload.newsletter_opt_in
        if "nudge_opt_in" in fields_set:
            updates["nudge_opt_in"] = payload.nudge_opt_in
        if "year_in_review_opt_in" in fields_set:
            updates["year_in_review_opt_in"] = payload.year_in_review_opt_in
        if "notify_channel_apprise" in fields_set:
            updates["notify_channel_apprise"] = payload.notify_channel_apprise
        if "apprise_urls" in fields_set:
            updates["apprise_urls"] = payload.apprise_urls
        if not updates:
            return {"user": user.to_dict(), "authenticated": True}
        try:
            updated = _db().update_user_profile(user.id, **updates)
        except ValueError as error:
            raise HTTPException(
                status_code=404,
                detail=_safe_error_detail(error, "User not found"),
            ) from error
        # Prefer resolved local avatar path when a cached/uploaded file exists.
        updated["avatar_url"] = resolve_avatar_url(user.id, updated.get("avatar_url"))
        return {"user": updated, "authenticated": True}


    @router.get("/api/auth/avatar/{user_id}")
    def get_user_avatar(user_id: str, user=Depends(get_current_user_dep)) -> FileResponse:
        """Serve a locally stored avatar for an authenticated household user."""
        from projectionist.web.avatars import find_local_avatar_file, media_type_for_avatar, safe_user_id

        del user  # auth gate only
        try:
            safe_user_id(user_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        path = find_local_avatar_file(user_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Avatar not found")
        return FileResponse(path, media_type=media_type_for_avatar(path))


    @router.post("/api/auth/me/avatar")
    async def upload_my_avatar(
        file: UploadFile = File(...),
        user=Depends(get_current_user_dep),
    ) -> Dict[str, Any]:
        """Upload a profile picture; stored under DATA_DIR/avatars/{user_id}.*."""
        from projectionist.web.avatars import local_avatar_api_path, save_avatar_bytes

        raw = await file.read()
        try:
            api_path = save_avatar_bytes(user.id, raw, file.content_type or "")
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        try:
            updated = _db().update_user_profile(user.id, avatar_url=api_path)
        except ValueError as error:
            raise HTTPException(
                status_code=404,
                detail=_safe_error_detail(error, "User not found"),
            ) from error
        updated["avatar_url"] = local_avatar_api_path(user.id)
        return {"user": updated, "authenticated": True}


    @router.post("/api/auth/me/apprise/test")
    def test_my_apprise_send(
        request: Request,
        payload: MyAppriseTestPayload,
        user=Depends(get_current_user_dep),
    ) -> Dict[str, Any]:
        """Send a short test notification to one self-serve Apprise URL."""
        del user
        from projectionist.notifications.apprise_transport import (
            AppriseSendError,
            apprise_available,
            send_apprise,
            split_apprise_urls,
        )

        enforce_rate_limit(request, bucket="apprise_me_test", limit=10, window_seconds=60)
        if not apprise_available():
            raise HTTPException(
                status_code=400,
                detail="Apprise is not installed. Ask the owner to reinstall with the web extras.",
            )
        urls = split_apprise_urls(payload.url)
        if len(urls) != 1:
            raise HTTPException(
                status_code=400,
                detail="Provide exactly one Apprise URL to test.",
            )
        try:
            result = send_apprise(
                None,
                title="Projectionist Apprise test",
                body=(
                    "This is a test notification from your Projectionist notification settings.\n\n"
                    "If you received it, this destination is working."
                ),
                urls=urls,
            )
        except AppriseSendError as exc:
            # Detail is safe (transport already avoids echoing raw URLs in common paths).
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "ok": True,
            "notified": result.notified,
            "detail": result.detail,
        }


    @router.post("/api/auth/plex/pin")
    def auth_plex_pin_start(
        request: Request,
        response: Response,
        invite_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start Overseerr-style Plex PIN login; client opens auth_url and polls."""
        return start_plex_pin_login(request, response, invite_token=invite_token)


    @router.get("/api/auth/plex/pin/{pin_id}")
    def auth_plex_pin_poll(
        pin_id: int,
        request: Request,
        response: Response,
        peek: bool = Query(False, description="Link Plex: status only, no session bind."),
    ) -> Dict[str, Any]:
        """Poll Plex PIN. Login/join complete the household session when claimed.

        Pass ``peek=1`` for Link Plex: plex.tv status only — no cookie, no user bind.
        An existing household session is not enough to force peek-only.
        """
        if peek:
            authorized = peek_plex_pin_authorized(pin_id, request)
            return {
                "authenticated": authorized,
                "pending": not authorized,
                "authorized": authorized,
                "bound": False,
            }
        user = poll_plex_pin_login(pin_id, request, _db())
        if user is None:
            return {"authenticated": False, "pending": True}
        clear_pin_nonce_cookie(response, request)
        set_session_cookie(response, user.id, request, db=_db())
        return {"user": user.to_dict(), "authenticated": True, "pending": False}


    class PlexLinkPayload(BaseModel):
        pin_id: int
        password: str = Field(min_length=1, max_length=256)


    @router.post("/api/auth/plex/link")
    def auth_plex_link(
        payload: PlexLinkPayload,
        request: Request,
        response: Response,
        user=Depends(get_current_user_dep),
    ) -> Dict[str, Any]:
        """Bind Plex to the current local-password user. Password + PIN in one request."""
        linked = link_plex_identity(
            pin_id=payload.pin_id,
            password=payload.password,
            request=request,
            db=_db(),
            user=user,
        )
        clear_pin_nonce_cookie(response, request)
        return {"user": linked.to_dict(), "authenticated": True, "linked": True}


    @router.post("/api/auth/plex")
    def auth_plex(payload: PlexLoginPayload, request: Request, response: Response) -> Dict[str, Any]:
        """Advanced fallback: sign in with a raw Plex auth token."""
        enforce_rate_limit(request, bucket="auth_plex_token", limit=10, window_seconds=60)
        user = authenticate_plex_user(
            payload.auth_token,
            _db(),
            invite_token=payload.invite_token,
        )
        set_session_cookie(response, user.id, request, db=_db())
        return {"user": user.to_dict(), "authenticated": True}


    @router.post("/api/auth/local/register")
    def auth_local_register(
        payload: LocalRegisterPayload,
        request: Request,
        response: Response,
    ) -> Dict[str, Any]:
        """Owner-authenticated local account create. Anonymous always 403."""
        enforce_rate_limit(request, bucket="auth_local_register", limit=5, window_seconds=60)
        db = _db()
        if not _settings().features.multi_user_enabled:
            raise HTTPException(
                status_code=403,
                detail="Local registration is disabled. Ask the household admin for a join link.",
            )
        requesting_user = get_current_user_dep(request)
        user = register_local_user(
            username=payload.username,
            password=payload.password,
            db=db,
            requesting_user=requesting_user,
        )
        set_session_cookie(response, user.id, request, db=_db())
        return {"user": user.to_dict(), "authenticated": True}


    @router.post("/api/auth/local/login")
    def auth_local_login(
        payload: LocalLoginPayload,
        request: Request,
        response: Response,
    ) -> Dict[str, Any]:
        """Authenticate with username/password and set session cookie."""
        user = authenticate_local_user(
            username=payload.username,
            password=payload.password,
            db=_db(),
            request=request,
        )
        set_session_cookie(response, user.id, request, db=_db())
        return {"user": user.to_dict(), "authenticated": True}


    @router.get("/api/auth/oidc/authorize")
    def auth_oidc_authorize(
        request: Request,
        invite_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start OIDC login — returns the provider authorization URL."""
        return start_oidc_authorize(request, invite_token=invite_token)


    @router.get("/api/auth/oidc/callback")
    def auth_oidc_callback(
        code: str,
        state: str,
        request: Request,
        response: Response,
    ) -> Dict[str, Any]:
        """Handle OIDC provider callback — exchange code, create/find user, set session."""
        user = handle_oidc_callback(code=code, state=state, db=_db(), request=request)
        set_session_cookie(response, user.id, request, db=_db())
        return {"user": user.to_dict(), "authenticated": True}


    @router.post("/api/auth/logout")
    def auth_logout(request: Request, response: Response) -> Dict[str, bool]:
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token:
            from projectionist.web.session_tokens import hash_session_jti, parse_session_claims

            claims = parse_session_claims(token)
            jti = str(claims.get("jti") or "") if claims else ""
            if jti:
                _db().revoke_session_jti(
                    hash_session_jti(jti),
                    expires_at=float(claims.get("exp") or (time.time() + DEFAULT_TTL_SECONDS)),
                )
        clear_session_cookie(response, request)
        return {"logged_out": True}


    class AccessRequestCreatePayload(BaseModel):
        display_name: str = Field(min_length=2, max_length=120)
        email: Optional[str] = Field(default=None, max_length=320)
        message: Optional[str] = Field(default=None, max_length=2000)
        organization_url: Optional[str] = Field(default=None, max_length=2000)


    @router.post("/api/access-requests")
    def create_access_request_endpoint(
        payload: AccessRequestCreatePayload,
        request: Request,
    ) -> Dict[str, Any]:
        """Public: ask the owner for household membership (queue only)."""
        settings = _settings()
        if not bool(getattr(settings.features, "access_requests_enabled", True)):
            raise HTTPException(status_code=404, detail="Not found")
        enforce_rate_limit(request, bucket="access_request", limit=3, window_seconds=3600)
        honeypot = str(payload.organization_url or "").strip()
        if honeypot:
            from projectionist.web.ingress import log_honeypot_ping

            log_honeypot_ping(request, honeypot="organization_url")
            return {
                "request": {
                    "id": uuid.uuid4().hex,
                    "status": "pending",
                    "created_at": time.time(),
                }
            }
        from projectionist.access_requests import notify_owners_of_access_request

        try:
            row = _db().create_access_request(
                display_name=payload.display_name,
                email=payload.email,
                message=payload.message,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=_safe_error_detail(error, "Invalid access request"),
            ) from error
        notify_owners_of_access_request(_db(), _settings(), row)
        return {"request": {"id": row["id"], "status": row["status"], "created_at": row["created_at"]}}


    @router.get("/api/invites/validate")
    def validate_invite_endpoint(token: str, request: Request) -> Dict[str, Any]:
        """Public: validate a join token before redeem UI offers sign-in methods."""
        enforce_rate_limit(request, bucket="invite_validate", limit=30, window_seconds=60)
        from projectionist.invites import lookup_pending_invite, public_invite_view

        try:
            invite = lookup_pending_invite(_db(), token)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"invite": public_invite_view(invite), "valid": True}


    @router.post("/api/invites/redeem/local")
    def redeem_invite_local_endpoint(
        payload: InviteRedeemLocalPayload,
        request: Request,
        response: Response,
    ) -> Dict[str, Any]:
        """Public: redeem invite by creating a local-password account."""
        enforce_rate_limit(request, bucket="invite_redeem_local", limit=10, window_seconds=60)
        from projectionist.invites import redeem_local_invite
        from projectionist.web.auth import _ensure_local_login_enabled

        _ensure_local_login_enabled()
        try:
            result = redeem_local_invite(
                _db(),
                _settings(),
                raw_token=payload.token,
                username=payload.username,
                password=payload.password,
            )
        except InviteConflict as error:
            raise HTTPException(
                status_code=409,
                detail=str(error) or "Invite has already been used",
            ) from error
        except ValueError as error:
            detail = str(error)
            if "already been used" in detail.lower():
                raise HTTPException(status_code=409, detail=detail) from error
            raise HTTPException(status_code=400, detail=detail) from error
        set_session_cookie(response, str(result["user"]["id"]), request, db=_db())
        return {"authenticated": True, **result}


    @router.get("/api/admin/access-requests")
    def list_access_requests_endpoint(
        status: Optional[str] = None,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        del user
        try:
            items = _db().list_access_requests(status=status, limit=100)
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=_safe_error_detail(error, "Invalid status filter"),
            ) from error
        return {"items": items, "count": len(items)}


    @router.post("/api/admin/access-requests/{request_id}/approve")
    def approve_access_request_endpoint(
        request_id: str,
        request: Request,
        payload: Optional[AccessRequestApprovePayload] = None,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        from projectionist.access_requests import approve_access_request

        body = payload or AccessRequestApprovePayload()
        base_url = str(request.base_url).rstrip("/")
        try:
            return approve_access_request(
                _db(),
                _settings(),
                request_id=request_id,
                owner_id=str(user.id),
                role=body.role,
                is_youth=body.is_youth,
                allowed_methods=body.allowed_methods,
                expires_in_seconds=body.expires_in_seconds,
                base_url=base_url,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=_safe_error_detail(error, "Could not approve request"),
            ) from error


    @router.post("/api/admin/access-requests/{request_id}/deny")
    def deny_access_request_endpoint(
        request_id: str,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        from projectionist.access_requests import deny_access_request

        try:
            return {"request": deny_access_request(_db(), request_id=request_id, owner_id=str(user.id))}
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=_safe_error_detail(error, "Could not deny request"),
            ) from error


    @router.get("/api/admin/invites")
    def list_invites_endpoint(
        status: Optional[str] = None,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        del user
        from projectionist.invites import public_invite_view

        try:
            items = _db().list_invites(status=status, limit=100)
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=_safe_error_detail(error, "Invalid status filter"),
            ) from error
        return {"items": [public_invite_view(i) for i in items], "count": len(items)}


    @router.post("/api/admin/invites")
    def create_invite_endpoint(
        payload: InviteCreatePayload,
        request: Request,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        from projectionist.invites import create_household_invite

        base_url = str(request.base_url).rstrip("/")
        try:
            return create_household_invite(
                _db(),
                _settings(),
                owner_id=str(user.id),
                role=payload.role,
                is_youth=payload.is_youth,
                allowed_methods=payload.allowed_methods,
                email=payload.email,
                expected_plex_user_id=payload.expected_plex_user_id,
                expected_oidc_sub=payload.expected_oidc_sub,
                expires_in_seconds=payload.expires_in_seconds or (7 * 24 * 3600),
                base_url=base_url,
                send_email=True,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=_safe_error_detail(error, "Could not create invite"),
            ) from error


    @router.post("/api/admin/invites/{invite_id}/revoke")
    def revoke_invite_endpoint(
        invite_id: str,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        from projectionist.invites import public_invite_view

        try:
            invite = _db().revoke_invite(invite_id, revoked_by=str(user.id))
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=_safe_error_detail(error, "Could not revoke invite"),
            ) from error
        return {"invite": public_invite_view(invite)}


    @router.get("/api/users")
    def list_users(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        items = _db().list_users()
        return {"items": items, "count": len(items)}


    @router.patch("/api/users/{user_id}")
    def patch_user(
        user_id: str,
        payload: UserUpdatePayload,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        if payload.role is None and payload.disabled is None and payload.is_youth is None:
            raise HTTPException(status_code=400, detail="Provide role, disabled, and/or is_youth")
        db = _db()
        target = db.get_user(user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        updated: Optional[Dict[str, Any]] = None
        if payload.role is not None:
            if user_id == user.id and payload.role != "owner":
                raise HTTPException(status_code=400, detail="Cannot demote your own owner account")
            if str(target["role"]) == "owner" and payload.role != "owner":
                if db.count_users_with_role("owner") <= 1:
                    raise HTTPException(status_code=400, detail="Cannot demote the last owner")
            try:
                updated = db.update_user_role(user_id, payload.role)
            except ValueError as error:
                raise HTTPException(
                    status_code=404,
                    detail=_safe_error_detail(error, "User not found"),
                ) from error
        if payload.disabled is not None:
            if user_id == user.id and payload.disabled:
                raise HTTPException(status_code=400, detail="Cannot disable your own account")
            if payload.disabled and str(target["role"]) == "owner":
                if db.count_users_with_role("owner") <= 1:
                    raise HTTPException(status_code=400, detail="Cannot disable the last owner")
            try:
                updated = db.set_user_disabled(user_id, payload.disabled)
            except ValueError as error:
                raise HTTPException(
                    status_code=404,
                    detail=_safe_error_detail(error, "User not found"),
                ) from error
        if payload.is_youth is not None:
            try:
                updated = db.set_user_youth(user_id, payload.is_youth)
            except ValueError as error:
                raise HTTPException(status_code=404, detail=_safe_error_detail(error, "User not found")) from error
        assert updated is not None
        return {"user": updated}


    @router.delete("/api/users/{user_id}")
    def delete_user(
        user_id: str,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        if user_id == user.id:
            raise HTTPException(status_code=400, detail="Cannot remove your own account")
        db = _db()
        target = db.get_user(user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        if str(target["role"]) == "owner" and db.count_users_with_role("owner") <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last owner")
        try:
            db.delete_user(user_id)
        except ValueError as error:
            raise HTTPException(
                status_code=404,
                detail=_safe_error_detail(error, "User not found"),
            ) from error
        return {"deleted": True, "id": user_id}


    @router.post("/api/users/{user_id}/sync-seerr")
    def sync_user_seerr(
        user_id: str,
        payload: SeerrSyncPayload,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        del user
        updated = sync_user_seerr_from_token(user_id, payload.auth_token, _db())
        return {"user": updated}


    app.include_router(router)
