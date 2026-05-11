import tempfile
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

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/webm": ".webm",
}

MAX_IMAGE_SIZE = 30 * 1024 * 1024
MAX_VIDEO_SIZE = 500 * 1024 * 1024
GLOBAL_MAX_CONTENT_LENGTH = MAX_VIDEO_SIZE
CHUNK_SIZE = 8 * 1024 * 1024
SPILL_THRESHOLD = 32 * 1024 * 1024


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
    from datetime import timedelta
    return client.presigned_get_object(MINIO_BUCKET, object_name, expires=timedelta(days=7))


@bp.before_request
def _check_global_upload_limit():
    content_length = request.content_length
    if content_length and content_length > GLOBAL_MAX_CONTENT_LENGTH:
        return jsonify({
            "success": False,
            "message": f"请求体过大，最大允许 {GLOBAL_MAX_CONTENT_LENGTH // (1024 * 1024)}MB",
        }), 413


@bp.route("/creative", methods=["POST"])
@api_login_required
def upload_creative():
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

    is_video = content_type.startswith("video/")
    max_size = MAX_VIDEO_SIZE if is_video else MAX_IMAGE_SIZE

    content_length = request.content_length
    if content_length and content_length > max_size:
        limit_mb = max_size // (1024 * 1024)
        return jsonify({
            "success": False,
            "message": f"文件过大，{'视频' if is_video else '图片'}最大 {limit_mb}MB",
        }), 400

    with tempfile.SpooledTemporaryFile(max_size=SPILL_THRESHOLD) as tmp:
        total_read = 0
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > max_size:
                limit_mb = max_size // (1024 * 1024)
                return jsonify({
                    "success": False,
                    "message": f"文件过大，{'视频' if is_video else '图片'}最大 {limit_mb}MB",
                }), 400
            tmp.write(chunk)

        total_size = total_read
        ext = ALLOWED_TYPES[content_type]
        now = datetime.now(timezone.utc)
        object_name = f"creatives/{now.strftime('%Y/%m/%d')}/{uuid.uuid4().hex[:12]}{ext}"

        try:
            client = _get_client()
            _ensure_bucket(client)
            tmp.seek(0)
            client.put_object(
                MINIO_BUCKET,
                object_name,
                tmp,
                length=total_size,
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
        "size": total_size,
        "content_type": content_type,
    })
