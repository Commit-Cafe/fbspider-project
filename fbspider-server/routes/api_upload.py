"""File upload API — stores ad creatives in MinIO (S3-compatible)."""

import io
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from minio import Minio
from minio.error import S3Error

from auth import api_login_required
from config import (
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_PUBLIC_URL,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
)

bp = Blueprint("api_upload", __name__, url_prefix="/api/upload")

# Allowed MIME types → extensions
ALLOWED_TYPES = {
    # Images
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    # Videos
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/webm": ".webm",
}

MAX_IMAGE_SIZE = 30 * 1024 * 1024   # 30 MB
MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500 MB


def _get_client():
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def _ensure_bucket(client):
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)


def _presigned_url(client, object_name):
    """Generate a presigned URL valid for 7 days."""
    from datetime import timedelta
    return client.presigned_get_object(MINIO_BUCKET, object_name, expires=timedelta(days=7))


@bp.route("/creative", methods=["POST"])
@api_login_required
def upload_creative():
    """Upload an image or video file for ad creative.

    Expects multipart/form-data with a 'file' field.
    Returns the public URL that Facebook can download from.
    """
    if "file" not in request.files:
        return jsonify({"success": False, "message": "未选择文件"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"success": False, "message": "文件名为空"}), 400

    content_type = f.content_type or ""
    if content_type not in ALLOWED_TYPES:
        return jsonify({
            "success": False,
            "message": f"不支持的文件类型: {content_type}，支持: {', '.join(ALLOWED_TYPES.keys())}",
        }), 400

    # Read file into memory to check size
    data = f.read()
    is_video = content_type.startswith("video/")
    max_size = MAX_VIDEO_SIZE if is_video else MAX_IMAGE_SIZE

    if len(data) > max_size:
        limit_mb = max_size // (1024 * 1024)
        return jsonify({
            "success": False,
            "message": f"文件过大，{'视频' if is_video else '图片'}最大 {limit_mb}MB",
        }), 400

    # Generate unique object name: creatives/2026/04/14/<uuid>.<ext>
    ext = ALLOWED_TYPES[content_type]
    now = datetime.now(timezone.utc)
    object_name = f"creatives/{now.strftime('%Y/%m/%d')}/{uuid.uuid4().hex[:12]}{ext}"

    try:
        client = _get_client()
        _ensure_bucket(client)
        client.put_object(
            MINIO_BUCKET,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
    except S3Error as e:
        return jsonify({"success": False, "message": f"上传失败: {e}"}), 500

    url = _presigned_url(client, object_name)
    file_type = "video" if is_video else "image"

    return jsonify({
        "success": True,
        "url": url,
        "file_type": file_type,
        "object_name": object_name,
        "size": len(data),
        "content_type": content_type,
    })
