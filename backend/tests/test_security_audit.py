from app.security_audit import sanitize_security_details


def test_security_event_details_remove_credentials_hashes_and_request_bodies():
    details = sanitize_security_details(
        "institution.membership.role_changed",
        {
            "previous_role": "STUDENT",
            "new_role": "ADMIN",
            "password": "not-for-storage",
            "password_hash": "not-for-storage",
            "access_token": "not-for-storage",
            "authorization": "not-for-storage",
            "raw_request_body": {"message": "not-for-storage"},
            "change": {
                "refresh_token": "not-for-storage",
            },
        }
    )
    assert details == {"previous_role": "STUDENT", "new_role": "ADMIN"}


def test_security_event_detail_allowlist_drops_nested_and_invalid_values():
    details = sanitize_security_details(
        "platform.admin.revoke_denied",
        {
            "reason": "last_active_admin",
            "source": "cli",
            "operator": "audit-user",
            "request": {"authorization": "Bearer secret", "token": "raw"},
            "password": "raw-password",
        },
    )
    assert details == {
        "reason": "last_active_admin",
        "source": "cli",
        "operator": "audit-user",
    }
    assert sanitize_security_details("unknown.event", {"safe": "value"}) == {}