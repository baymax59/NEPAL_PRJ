"""Case Management: the organisation's name and case-number prefix (decision D13). Fictional names only."""

import pytest
from cm_support import create_case
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.casemgmt import organisations


def test_the_prefix_can_be_set_until_the_first_case(cm_client, db_session):
    assert organisations.set_up(db_session, code="tsp", name="Example State Police (fictional)") == ("KH", "TSP")
    db_session.commit()
    created = create_case(cm_client("inv.prefix"))
    assert created["display_id"].startswith("TSP-")
    assert organisations.overview(db_session)[0] == {"code": "TSP", "name": "Example State Police (fictional)",
                                                     "cases": 1, "users": 1}

    with pytest.raises(ValueError, match="already has cases"):
        organisations.set_up(db_session, code="XYZ", name="Example State Police (fictional)")
    organisations.rename(db_session, code="TSP", name="Example State Police, Cyber Wing (fictional)")  # names may change

    # The database refuses on its own, too.
    with pytest.raises(IntegrityError, match="prefix stays"):
        with db_session.begin_nested():
            db_session.execute(text("UPDATE organizations SET code = 'ABC' WHERE code = 'TSP'"))
    with pytest.raises(IntegrityError, match="permanent"):
        with db_session.begin_nested():
            db_session.execute(text("DELETE FROM organizations"))
    with pytest.raises(IntegrityError, match="only name and code"):
        with db_session.begin_nested():
            db_session.execute(text("UPDATE organizations SET created_at = now()"))


@pytest.mark.parametrize("code", ["", "K", "1KH", "KH-1", "TOOLONGPREFIX", "K H"])
def test_invalid_prefixes_are_refused(db_session, code):
    with pytest.raises(ValueError, match="prefix"):
        organisations.set_up(db_session, code=code, name="Example State Police (fictional)")


def test_a_name_is_required(db_session):
    with pytest.raises(ValueError, match="name"):
        organisations.set_up(db_session, code="AB", name="x")
