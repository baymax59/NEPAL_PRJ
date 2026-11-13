"""The profile photo (docs/case-management/13-plain-case-design.md, section 12): only a JPEG, PNG or WebP picture is accepted, it is drawn again as a small
square JPEG so nothing the sender put into the file survives, it can be changed only by its owner, and only logged-in people of the same organisation can
see it. All pictures are made by the tests."""

import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.auth.photos import MAX_UPLOAD_BYTES, SIDE
from app.casemgmt.models import Organization
from app.db.models import AuditEvent


def picture(fmt="PNG", size=(600, 300), color=(200, 30, 30, 255), mode="RGBA", exif=None) -> bytes:
    out = io.BytesIO()
    image = Image.new(mode, size, color if mode == "RGBA" else color[:3])
    kwargs = {"exif": exif} if exif else {}
    image.save(out, format=fmt, **kwargs)
    return out.getvalue()


def upload(client, data: bytes, name="me.png", kind="image/png", status=200):
    response = client.post("/api/auth/profile/photo", files={"file": (name, data, kind)})
    assert response.status_code == status, response.text
    return response


def stored(client, user_id) -> Image.Image:
    response = client.get(f"/api/auth/photo/{user_id}")
    assert response.status_code == 200
    return Image.open(io.BytesIO(response.content))


def test_a_picture_is_drawn_again_as_a_small_square_jpeg_and_served_safely(cm_client):
    me = cm_client("photo.owner", "investigator")
    assert me.get("/api/auth/me").json()["photo_updated_at"] is None
    saved = upload(me, picture()).json()  # 600 x 300 with transparent parts allowed
    assert saved["photo_updated_at"] is not None and saved["id"] == str(me.user.id)

    response = me.get(f"/api/auth/photo/{me.user.id}")
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff" and "public" not in response.headers["cache-control"]  # never kept by a shared cache
    image = Image.open(io.BytesIO(response.content))
    assert image.format == "JPEG" and image.size == (SIDE, SIDE)
    assert me.get("/api/auth/me").json()["photo_updated_at"] is not None


@pytest.mark.parametrize(("fmt", "kind"), [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_jpeg_png_and_webp_are_accepted(cm_client, fmt, kind):
    me = cm_client(f"photo.{fmt.lower()}", "investigator")
    upload(me, picture(fmt, mode="RGB", color=(10, 80, 200)), f"me.{fmt.lower()}", kind)
    assert stored(me, me.user.id).format == "JPEG"


def test_what_the_sender_hid_in_the_file_does_not_survive(cm_client):
    me = cm_client("photo.clean", "investigator")
    exif = Image.Exif()
    exif[0x010F] = "Camera maker (fictional)"  # a camera tag
    exif[0x8825] = {1: "N", 2: (28.0, 36.0, 0.0)}  # a location
    upload(me, picture("JPEG", mode="RGB", exif=exif.tobytes()), "me.jpg", "image/jpeg")
    image = stored(me, me.user.id)
    assert len(image.getexif()) == 0  # no camera or location tags are carried over

    hidden = picture() + b"<script>alert('hidden')</script>" + b"MZ-not-a-picture-payload"  # something written after the picture
    upload(me, hidden)
    response = me.get(f"/api/auth/photo/{me.user.id}")
    assert b"<script" not in response.content and b"MZ-not" not in response.content


@pytest.mark.parametrize("data,name,kind", [
    (b"", "empty.png", "image/png"),
    (b"just some text, not a picture", "me.png", "image/png"),  # the name and type say picture, the content does not
    (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "me.svg", "image/svg+xml"),
    (picture("GIF", mode="RGB", color=(1, 2, 3)), "me.gif", "image/gif"),
    (picture("BMP", mode="RGB", color=(1, 2, 3)), "me.bmp", "image/bmp"),
])
def test_anything_that_is_not_a_readable_jpeg_png_or_webp_is_refused_and_the_old_photo_stays(cm_client, data, name, kind):
    me = cm_client("photo.refused", "investigator")
    upload(me, picture())
    before = me.get(f"/api/auth/photo/{me.user.id}").content
    response = upload(me, data, name, kind, status=422)
    assert "picture" in response.json()["detail"].lower() or "empty" in response.json()["detail"].lower()
    assert me.get(f"/api/auth/photo/{me.user.id}").content == before


def test_a_picture_that_is_too_big_in_bytes_or_in_pixels_is_refused(cm_client):
    me = cm_client("photo.big", "investigator")
    noise = Image.frombytes("RGB", (1000, 1000), os.urandom(3_000_000))  # noise does not compress: about 3 MB as a PNG
    out = io.BytesIO()
    noise.save(out, format="PNG")
    big = out.getvalue()
    assert len(big) > MAX_UPLOAD_BYTES
    assert "larger than" in upload(me, big, status=422).json()["detail"]
    bomb = picture(size=(5001, 5001), mode="RGB", color=(0, 0, 0))  # a small file that unpacks into 25 million pixels
    assert len(bomb) < MAX_UPLOAD_BYTES
    assert "too many pixels" in upload(me, bomb, status=422).json()["detail"]
    assert me.get(f"/api/auth/photo/{me.user.id}").status_code == 404


def test_only_logged_in_people_of_the_same_organisation_see_a_photo(cm_client, db_session, app_overrides):
    owner = cm_client("photo.seen", "investigator")
    upload(owner, picture())
    colleague = cm_client("photo.colleague", "viewer")
    assert colleague.get(f"/api/auth/photo/{owner.user.id}").status_code == 200

    other_org = Organization(code="PH", name="Another force (fictional)")
    db_session.add(other_org)
    db_session.commit()
    outsider = cm_client("photo.outsider", "investigator", organization=other_org)
    assert outsider.get(f"/api/auth/photo/{owner.user.id}").status_code == 404  # another organisation: as if there were none

    with TestClient(app_overrides) as anonymous:
        assert anonymous.get(f"/api/auth/photo/{owner.user.id}").status_code == 401
    assert colleague.get(f"/api/auth/photo/{colleague.user.id}").status_code == 404  # nobody without a photo


def test_a_photo_can_be_changed_and_taken_off_only_by_its_owner_and_it_shows_in_the_lists(cm_client):
    owner = cm_client("photo.mine", "investigator")
    super_admin = cm_client("photo.sa", "super_admin", "confidential")
    other = cm_client("photo.other", "investigator")
    upload(owner, picture())
    # somebody else's upload changes only their own photo: there is no way to name another person
    upload(other, picture(color=(0, 120, 0, 255)))
    assert owner.get(f"/api/auth/photo/{owner.user.id}").content != other.get(f"/api/auth/photo/{other.user.id}").content

    row = next(r for r in super_admin.get("/api/v1/people/accounts").json() if r["username"] == "photo.mine")
    assert isinstance(row["photo"], int)  # the People list knows who has a photo
    removed = owner.post("/api/auth/profile/photo/remove")
    assert removed.status_code == 200 and removed.json()["photo_updated_at"] is None
    assert owner.get(f"/api/auth/photo/{owner.user.id}").status_code == 404
    row = next(r for r in super_admin.get("/api/v1/people/accounts").json() if r["username"] == "photo.mine")
    assert row["photo"] is None


def test_the_audit_trail_records_that_a_photo_changed_never_the_picture(cm_client, db_session):
    me = cm_client("photo.audited", "investigator")
    upload(me, picture())
    upload(me, b"not a picture", status=422)
    me.post("/api/auth/profile/photo/remove")
    events = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "user.photo_changed").order_by(AuditEvent.id)).all()
    assert [(e.outcome, (e.details or {}).get("action") or (e.details or {}).get("reason")) for e in events] == [
        ("success", "set"), ("rejected", "refused"), ("success", "removed")]
