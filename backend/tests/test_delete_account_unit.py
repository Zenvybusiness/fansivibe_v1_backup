"""Unit tests for `DeleteAccount` — run everywhere, no database."""

from __future__ import annotations

import uuid

import pytest

from app.api.errors import ApiError
from app.application.auth import DeleteAccount


class _StubAuth:
    def __init__(self, deleted: bool):
        self.deleted = deleted
        self.committed = False
        self.rolled_back = False

    def delete_account(self, *, user_id):
        return self.deleted

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_delete_account_missing_is_404_and_rolls_back():
    stub = _StubAuth(deleted=False)
    with pytest.raises(ApiError) as exc:
        DeleteAccount(auth=stub)(user_id=uuid.uuid4())
    assert exc.value.status_code == 404
    assert exc.value.code == "NOT_FOUND"
    assert stub.rolled_back and not stub.committed


def test_delete_account_present_commits():
    stub = _StubAuth(deleted=True)
    DeleteAccount(auth=stub)(user_id=uuid.uuid4())
    assert stub.committed and not stub.rolled_back
