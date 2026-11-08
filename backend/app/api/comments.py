from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from tortoise.exceptions import IntegrityError
from tortoise.functions import Count
from tortoise.transactions import in_transaction

from app import auth
from app.models import (
    AdminOperationLog, AdminUser, CommentLike, CommentLikeEvent,
    CommentReport, MovieComment, MovieInfo, User,
)
from app.schemas import CommentCreate, ReportCreate, ReportDecision

router = APIRouter()


async def _comment_or_404(commentid: int, *, include_deleted: bool = False):
    query = MovieComment.filter(commentid=commentid)
    if not include_deleted:
        query = query.filter(deleted_at=None)
    comment = await query.first()
    if comment is None:
        raise HTTPException(status_code=404, detail="评论不存在或已删除")
    return comment


async def _comment_rows(comments, current_user_id: Optional[int] = None):
    rows = await comments.values("commentid", "movie_id", "user_id", "content", "moderation_status", "created_at")
    if not rows:
        return []
    user_ids = {row["user_id"] for row in rows}
    movie_ids = {row["movie_id"] for row in rows}
    users = await User.filter(userid__in=user_ids).values("userid", "username", "avatar")
    movies = await MovieInfo.filter(movieid__in=movie_ids).values("movieid", "moviename")
    user_map = {row["userid"]: row for row in users}
    movie_map = {row["movieid"]: row for row in movies}
    comment_ids = [row["commentid"] for row in rows]
    like_counts = {}
    for row in await CommentLike.filter(comment_id__in=comment_ids, is_active=True).group_by("comment_id").annotate(total=Count("id")).values("comment_id", "total"):
        like_counts[row["comment_id"]] = row["total"]
    liked = set()
    if current_user_id is not None:
        liked = set(await CommentLike.filter(user_id=current_user_id, comment_id__in=comment_ids, is_active=True).values_list("comment_id", flat=True))
    return [
        {
            "commentid": row["commentid"], "movieid": row["movie_id"],
            "moviename": movie_map.get(row["movie_id"], {}).get("moviename"),
            "userid": row["user_id"], "username": user_map.get(row["user_id"], {}).get("username"),
            "avatar": user_map.get(row["user_id"], {}).get("avatar"), "content": row["content"],
            "moderation_status": row["moderation_status"], "created_at": row["created_at"],
            "like_count": like_counts.get(row["commentid"], 0), "liked": row["commentid"] in liked,
        }
        for row in rows
    ]


@router.get("/movies/{movieid}/comments")
async def list_movie_comments(
    movieid: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: Optional[User] = Depends(auth.get_optional_current_user),
):
    if not await MovieInfo.filter(movieid=movieid, deleted_at=None).exists():
        raise HTTPException(status_code=404, detail="电影不存在或已删除")
    comments = MovieComment.filter(movie_id=movieid, deleted_at=None, moderation_status__in=["published", "review_pending"])
    total = await comments.count()
    rows = await _comment_rows(
        comments.order_by("-created_at", "-commentid").offset((page - 1) * page_size).limit(page_size),
        user.userid if user else None,
    )
    return {"code": 200, "data": {"items": rows, "total": total, "page": page, "page_size": page_size}}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_comment(data: CommentCreate, user: User = Depends(auth.get_current_user)):
    if not await MovieInfo.filter(movieid=data.movieid, deleted_at=None).exists():
        raise HTTPException(status_code=404, detail="电影不存在或已删除")
    comment = await MovieComment.create(user_id=user.userid, movie_id=data.movieid, content=data.content, moderation_status="published")
    return {"code": 201, "data": {"commentid": comment.commentid, "movieid": data.movieid, "content": comment.content}}


@router.get("/me")
async def list_my_comments(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(auth.get_current_user)):
    comments = MovieComment.filter(user_id=user.userid, deleted_at=None)
    total = await comments.count()
    rows = await _comment_rows(comments.order_by("-created_at", "-commentid").offset((page - 1) * page_size).limit(page_size), user.userid)
    return {"code": 200, "data": {"items": rows, "total": total, "page": page, "page_size": page_size}}


@router.delete("/{commentid}")
async def delete_comment(commentid: int, user: User = Depends(auth.get_current_user)):
    comment = await _comment_or_404(commentid)
    if comment.user_id != user.userid:
        raise HTTPException(status_code=403, detail="只能删除自己的评论")
    comment.deleted_at = datetime.now(timezone.utc)
    await comment.save(update_fields=["deleted_at"])
    return {"code": 200, "msg": "评论已删除"}


@router.post("/{commentid}/like")
async def toggle_comment_like(commentid: int, user: User = Depends(auth.get_current_user)):
    comment = await _comment_or_404(commentid)
    async with in_transaction() as connection:
        like = await CommentLike.filter(user_id=user.userid, comment_id=comment.commentid).using_db(connection).select_for_update().first()
        if like is None:
            await CommentLike.create(user_id=user.userid, comment_id=comment.commentid, is_active=True, using_db=connection)
            action, active = "like", True
        else:
            like.is_active = not like.is_active
            await like.save(using_db=connection)
            action, active = ("like", True) if like.is_active else ("unlike", False)
        await CommentLikeEvent.create(user_id=user.userid, comment_id=comment.commentid, action=action, using_db=connection)
    return {"code": 200, "msg": "点赞状态已更新", "data": {"liked": active}}


@router.post("/{commentid}/reports", status_code=201)
async def report_comment(commentid: int, data: ReportCreate, user: User = Depends(auth.get_current_user)):
    comment = await _comment_or_404(commentid)
    try:
        report = await CommentReport.create(
            comment_id=comment.commentid,
            reporter_id=user.userid,
            reason_code=data.reason_code,
            reason_detail=data.reason_detail,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="同一用户不能重复举报同一评论") from exc
    if comment.moderation_status == "published":
        comment.moderation_status = "review_pending"
        await comment.save(update_fields=["moderation_status"])
    return {"code": 201, "data": {"reportid": report.reportid, "status": report.status}}


@router.get("/admin/reports")
async def list_reports(report_status: Optional[Literal["pending", "accepted", "rejected"]] = Query(None, alias="status"), admin: AdminUser = Depends(auth.get_current_admin)):
    reports = CommentReport.all().order_by("created_at")
    if report_status:
        reports = reports.filter(status=report_status)
    rows = await reports.values(
        "reportid", "comment_id", "reporter_id", "reason_code", "reason_detail",
        "status", "created_at", "handled_at",
    )
    return {"code": 200, "data": rows}


@router.put("/admin/reports/{reportid}")
async def decide_report(reportid: int, data: ReportDecision, admin: AdminUser = Depends(auth.get_current_admin)):
    report = await CommentReport.get_or_none(reportid=reportid)
    if report is None:
        raise HTTPException(status_code=404, detail="举报不存在")
    if report.status != "pending":
        raise HTTPException(status_code=409, detail="该举报已经处理")
    now = datetime.now(timezone.utc)
    report.status, report.handled_at, report.handled_by_admin_id = data.status, now, admin.adminid
    await report.save(update_fields=["status", "handled_at", "handled_by_admin_id"])
    comment = await _comment_or_404(report.comment_id, include_deleted=True)
    comment.moderation_status = "hidden" if data.status == "accepted" else "published"
    await comment.save(update_fields=["moderation_status"])
    await AdminOperationLog.create(admin=admin, action="comment.report_decide", target_type="comment", target_id=str(comment.commentid), detail={"reportid": reportid, "status": data.status})
    return {"code": 200, "msg": "举报处理完成", "data": {"status": report.status, "comment_status": comment.moderation_status}}


@router.delete("/admin/{commentid}")
async def admin_delete_comment(commentid: int, admin: AdminUser = Depends(auth.get_current_admin)):
    comment = await _comment_or_404(commentid)
    comment.deleted_at = datetime.now(timezone.utc)
    await comment.save(update_fields=["deleted_at"])
    await AdminOperationLog.create(
        admin=admin, action="comment.delete", target_type="comment",
        target_id=str(commentid), detail=None,
    )
    return {"code": 200, "msg": "评论已软删除"}
