"""Tortoise ORM models for application data and recommendation analytics."""

from __future__ import annotations

from tortoise import fields, models


class User(models.Model):
    userid = fields.IntField(pk=True)
    username = fields.CharField(max_length=50)
    password = fields.CharField(max_length=255)
    phone = fields.CharField(max_length=32)
    email = fields.CharField(max_length=254)
    avatar = fields.CharField(max_length=1000, null=True)
    status = fields.CharField(max_length=20, default="active")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "user"
        indexes = (("status", "created_at"), ("deleted_at",))


class AdminUser(models.Model):
    adminid = fields.IntField(pk=True)
    username = fields.CharField(max_length=50, unique=True)
    password = fields.CharField(max_length=255)
    role = fields.CharField(max_length=30)
    status = fields.CharField(max_length=20, default="active")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "adminuser"
        indexes = (("role", "status"),)


class MovieInfo(models.Model):
    movieid = fields.IntField(pk=True)
    moviename = fields.CharField(max_length=1000, null=True)
    releasetime = fields.DateField(null=True)
    director = fields.CharField(max_length=1000, null=True)
    leadactors = fields.CharField(max_length=1000, null=True)
    picture = fields.CharField(max_length=1000, null=True)
    averating = fields.FloatField(null=True)
    numrating = fields.IntField(null=True)
    description = fields.CharField(max_length=1000, null=True)
    typelist = fields.CharField(max_length=255, null=True)
    updated_at = fields.DatetimeField(auto_now=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "movieinfo"
        indexes = (
            ("averating",),
            ("numrating",),
            ("releasetime",),
            ("deleted_at",),
        )


class Category(models.Model):
    categoryid = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "category"


class MovieCategory(models.Model):
    id = fields.BigIntField(pk=True)
    movie = fields.ForeignKeyField(
        "models.MovieInfo",
        related_name="movie_categories",
        source_field="movieid",
        on_delete=fields.RESTRICT,
    )
    category = fields.ForeignKeyField(
        "models.Category",
        related_name="movie_categories",
        source_field="categoryid",
        on_delete=fields.RESTRICT,
    )

    class Meta:
        table = "moviecategory"
        unique_together = (("movie", "category"),)
        indexes = (("category", "movie"),)


class PersonalRating(models.Model):
    ratingid = fields.BigIntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="ratings",
        source_field="userid",
        on_delete=fields.RESTRICT,
    )
    movie = fields.ForeignKeyField(
        "models.MovieInfo",
        related_name="ratings",
        source_field="movieid",
        on_delete=fields.RESTRICT,
    )
    rating = fields.IntField()
    rated_at = fields.DatetimeField()
    timestamp = fields.CharField(max_length=10, null=True)

    class Meta:
        table = "personalratings"
        unique_together = (("user", "movie"),)
        indexes = (("movie", "rating"), ("user", "rated_at"))


class TrainingDataset(models.Model):
    datasetid = fields.IntField(pk=True)
    dataset_key = fields.CharField(max_length=100, unique=True)
    source_name = fields.CharField(max_length=255)
    rating_min = fields.DecimalField(max_digits=5, decimal_places=2)
    rating_max = fields.DecimalField(max_digits=5, decimal_places=2)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "trainingdataset"


class TrainingRating(models.Model):
    trainingratingid = fields.BigIntField(pk=True)
    dataset = fields.ForeignKeyField(
        "models.TrainingDataset",
        related_name="ratings",
        source_field="datasetid",
        on_delete=fields.RESTRICT,
    )
    external_userid = fields.IntField()
    movie = fields.ForeignKeyField(
        "models.MovieInfo",
        related_name="training_ratings",
        source_field="movieid",
        on_delete=fields.RESTRICT,
    )
    rating = fields.DecimalField(max_digits=5, decimal_places=2)
    rated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "trainingrating"
        unique_together = (("dataset", "external_userid", "movie"),)
        indexes = (("movie",), ("dataset", "external_userid"))


class MovieComment(models.Model):
    commentid = fields.BigIntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="comments",
        source_field="userid",
        on_delete=fields.RESTRICT,
    )
    movie = fields.ForeignKeyField(
        "models.MovieInfo",
        related_name="comments",
        source_field="movieid",
        on_delete=fields.RESTRICT,
    )
    content = fields.CharField(max_length=500)
    moderation_status = fields.CharField(max_length=20, default="published")
    created_at = fields.DatetimeField(auto_now_add=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "moviecomment"
        indexes = (
            ("movie", "created_at"),
            ("user", "created_at"),
            ("moderation_status", "created_at"),
        )


class CommentLike(models.Model):
    id = fields.BigIntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="comment_likes",
        source_field="userid",
        on_delete=fields.RESTRICT,
    )
    comment = fields.ForeignKeyField(
        "models.MovieComment",
        related_name="likes",
        source_field="commentid",
        on_delete=fields.RESTRICT,
    )
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "commentlike"
        unique_together = (("user", "comment"),)
        indexes = (("comment", "is_active"),)


class CommentLikeEvent(models.Model):
    eventid = fields.BigIntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="comment_like_events",
        source_field="userid",
        on_delete=fields.RESTRICT,
    )
    comment = fields.ForeignKeyField(
        "models.MovieComment",
        related_name="like_events",
        source_field="commentid",
        on_delete=fields.RESTRICT,
    )
    action = fields.CharField(max_length=10)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "commentlike_event"
        indexes = (("comment", "created_at"), ("user", "created_at"))


class CommentReport(models.Model):
    reportid = fields.BigIntField(pk=True)
    comment = fields.ForeignKeyField(
        "models.MovieComment",
        related_name="reports",
        source_field="commentid",
        on_delete=fields.RESTRICT,
    )
    reporter = fields.ForeignKeyField(
        "models.User",
        related_name="comment_reports",
        source_field="reporter_userid",
        on_delete=fields.RESTRICT,
    )
    reason_code = fields.CharField(max_length=40)
    reason_detail = fields.CharField(max_length=500, null=True)
    status = fields.CharField(max_length=20, default="pending")
    created_at = fields.DatetimeField(auto_now_add=True)
    handled_at = fields.DatetimeField(null=True)
    handled_by_admin = fields.ForeignKeyField(
        "models.AdminUser",
        related_name="handled_reports",
        source_field="handled_by_adminid",
        null=True,
        on_delete=fields.SET_NULL,
    )

    class Meta:
        table = "commentreport"
        unique_together = (("reporter", "comment"),)
        indexes = (("status", "created_at"),)


class UserFavorite(models.Model):
    id = fields.BigIntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="favorites",
        source_field="userid",
        on_delete=fields.RESTRICT,
    )
    movie = fields.ForeignKeyField(
        "models.MovieInfo",
        related_name="favorites",
        source_field="movieid",
        on_delete=fields.RESTRICT,
    )
    status = fields.CharField(max_length=30)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "userfavorite"
        unique_together = (("user", "movie"),)
        indexes = (
            ("user", "status", "deleted_at"),
            ("movie", "status", "deleted_at"),
        )


class AdminOperationLog(models.Model):
    logid = fields.BigIntField(pk=True)
    admin = fields.ForeignKeyField(
        "models.AdminUser",
        related_name="operation_logs",
        source_field="adminid",
        on_delete=fields.RESTRICT,
    )
    action = fields.CharField(max_length=100)
    target_type = fields.CharField(max_length=50)
    target_id = fields.CharField(max_length=100, null=True)
    detail = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "adminoperationlog"
        indexes = (("admin", "created_at"), ("target_type", "target_id"))


class RecommendationItem(models.Model):
    recommendationid = fields.BigIntField(pk=True)
    request_id = fields.CharField(max_length=64)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="recommendation_items",
        source_field="userid",
        on_delete=fields.RESTRICT,
    )
    movie = fields.ForeignKeyField(
        "models.MovieInfo",
        related_name="recommendation_items",
        source_field="movieid",
        on_delete=fields.RESTRICT,
    )
    position = fields.IntField()
    movie_rating_snapshot = fields.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
    )
    prediction_score = fields.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
    )
    algorithm_version = fields.CharField(max_length=100, null=True)
    generated_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "recommendationitem"
        unique_together = (("request_id", "movie"),)
        indexes = (("user", "generated_at"),)


class RecommendationEvent(models.Model):
    eventid = fields.BigIntField(pk=True)
    recommendation = fields.ForeignKeyField(
        "models.RecommendationItem",
        related_name="events",
        source_field="recommendationid",
        on_delete=fields.RESTRICT,
    )
    event_type = fields.CharField(max_length=20)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "recommendationevent"
        indexes = (
            ("event_type", "created_at"),
            ("recommendation", "event_type"),
        )
