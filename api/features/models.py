from __future__ import unicode_literals

import datetime
import logging
import typing
import uuid
from copy import deepcopy

from core.models import (
    AbstractBaseExportableModel,
    BaseHistoricalModel,
    abstract_base_auditable_model_factory,
)
from django.core.exceptions import (
    NON_FIELD_ERRORS,
    ObjectDoesNotExist,
    ValidationError,
)
from django.db import models
from django.db.models import Max, Q, QuerySet
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django_lifecycle import (
    AFTER_CREATE,
    BEFORE_CREATE,
    LifecycleModelMixin,
    hook,
)
from ordered_model.models import OrderedModelBase
from softdelete.models import SoftDeleteObject

from audit.constants import (
    FEATURE_CREATED_MESSAGE,
    FEATURE_DELETED_MESSAGE,
    FEATURE_SEGMENT_UPDATED_MESSAGE,
    FEATURE_STATE_UPDATED_MESSAGE,
    FEATURE_STATE_VALUE_UPDATED_MESSAGE,
    FEATURE_UPDATED_MESSAGE,
    IDENTITY_FEATURE_STATE_DELETED_MESSAGE,
    IDENTITY_FEATURE_STATE_UPDATED_MESSAGE,
    IDENTITY_FEATURE_STATE_VALUE_UPDATED_MESSAGE,
    SEGMENT_FEATURE_STATE_DELETED_MESSAGE,
    SEGMENT_FEATURE_STATE_UPDATED_MESSAGE,
    SEGMENT_FEATURE_STATE_VALUE_UPDATED_MESSAGE,
)
from audit.related_object_type import RelatedObjectType
from environments.identities.helpers import (
    get_hashed_percentage_for_object_ids,
)
from features.constants import ENVIRONMENT, FEATURE_SEGMENT, IDENTITY
from features.custom_lifecycle import CustomLifecycleModelMixin
from features.feature_states.models import (
    AbstractBaseFeatureValueModel,
    FeatureValueMixin,
)
from features.feature_types import MULTIVARIATE, STANDARD
from features.helpers import get_correctly_typed_value
from features.managers import (
    FeatureManager,
    FeatureSegmentManager,
    FeatureStateManager,
    FeatureStateValueManager,
)
from features.multivariate.models import MultivariateFeatureStateValue
from features.utils import (
    get_boolean_from_string,
    get_integer_from_string,
    get_value_type,
)
from features.value_types import (
    BOOLEAN,
    FEATURE_STATE_VALUE_TYPES,
    INTEGER,
    STRING,
)
from projects.models import Project
from projects.tags.models import Tag

from . import audit_helpers

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from environments.identities.models import Identity
    from environments.models import Environment


class Feature(
    SoftDeleteObject,
    CustomLifecycleModelMixin,
    AbstractBaseExportableModel,
    abstract_base_auditable_model_factory(["uuid"]),
):
    name = models.CharField(max_length=2000)
    created_date = models.DateTimeField("DateCreated", auto_now_add=True)
    project = models.ForeignKey(
        Project,
        related_name="features",
        help_text=_(
            "Changing the project selected will remove previous Feature States for the previously"
            "associated projects Environments that are related to this Feature. New default "
            "Feature States will be created for the new selected projects Environments for this "
            "Feature. Also this will remove any Tags associated with a feature as Tags are Project defined"
        ),
        on_delete=models.CASCADE,
    )
    initial_value = models.CharField(
        max_length=20000, null=True, default=None, blank=True
    )
    description = models.TextField(null=True, blank=True)
    default_enabled = models.BooleanField(default=False)
    type = models.CharField(max_length=50, blank=True, default=STANDARD)
    tags = models.ManyToManyField(Tag, blank=True)
    is_archived = models.BooleanField(default=False)
    owners = models.ManyToManyField(
        "users.FFAdminUser", related_name="owned_features", blank=True
    )

    history_record_class_path = "features.models.HistoricalFeature"
    related_object_type = RelatedObjectType.FEATURE

    objects = FeatureManager()

    class Meta:
        # Note: uniqueness index is added in explicit SQL in the migrations (See 0005, 0050)
        # TODO: after upgrade to Django 4.0 use UniqueConstraint()
        ordering = ("id",)  # explicit ordering to prevent pagination warnings

    @hook(AFTER_CREATE)
    def create_feature_states(self):
        # create feature states for all environments
        environments = self.project.environments.all()
        for env in environments:
            # unable to bulk create as we need signals
            FeatureState.objects.create(
                feature=self,
                environment=env,
                identity=None,
                feature_segment=None,
                enabled=False
                if self.project.prevent_flag_defaults
                else self.default_enabled,
            )

    def validate_unique(self, *args, **kwargs):
        """
        Checks unique constraints on the model and raises ``ValidationError``
        if any failed.
        """
        super(Feature, self).validate_unique(*args, **kwargs)

        # handle case insensitive names per project, as above check allows it
        if (
            Feature.objects.filter(project=self.project, name__iexact=self.name)
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError(
                {
                    NON_FIELD_ERRORS: [
                        "Feature with that name already exists for this project. Note that feature "
                        "names are case insensitive.",
                    ],
                }
            )

    def __str__(self):
        return "Project %s - Feature %s" % (self.project.name, self.name)

    def get_create_log_message(self, history_instance) -> typing.Optional[str]:
        return FEATURE_CREATED_MESSAGE % self.name

    def get_delete_log_message(self, history_instance) -> typing.Optional[str]:
        return FEATURE_DELETED_MESSAGE % self.name

    def get_update_log_message(self, history_instance) -> typing.Optional[str]:
        return FEATURE_UPDATED_MESSAGE % self.name

    def _get_project(self) -> typing.Optional["Project"]:
        return self.project


def get_next_segment_priority(feature):
    feature_segments = FeatureSegment.objects.filter(feature=feature).order_by(
        "-priority"
    )
    if feature_segments.count() == 0:
        return 1
    else:
        return feature_segments.first().priority + 1


class FeatureSegment(
    AbstractBaseExportableModel,
    abstract_base_auditable_model_factory(["uuid"]),
    OrderedModelBase,
):
    history_record_class_path = "features.models.HistoricalFeatureSegment"
    related_object_type = RelatedObjectType.FEATURE

    feature = models.ForeignKey(
        Feature, on_delete=models.CASCADE, related_name="feature_segments"
    )
    segment = models.ForeignKey(
        "segments.Segment", related_name="feature_segments", on_delete=models.CASCADE
    )
    environment = models.ForeignKey(
        "environments.Environment",
        on_delete=models.CASCADE,
        related_name="feature_segments",
    )

    _enabled = models.BooleanField(
        default=False,
        db_column="enabled",
        help_text="Deprecated in favour of using FeatureStateValue.",
    )
    _value = models.CharField(
        max_length=2000,
        blank=True,
        null=True,
        db_column="value",
        help_text="Deprecated in favour of using FeatureStateValue.",
    )
    _value_type = models.CharField(
        choices=FEATURE_STATE_VALUE_TYPES,
        max_length=50,
        blank=True,
        null=True,
        db_column="value_type",
        help_text="Deprecated in favour of using FeatureStateValue.",
    )

    # specific attributes for managing the order of feature segments
    priority = models.PositiveIntegerField(editable=False, db_index=True)
    order_field_name = "priority"
    order_with_respect_to = ("feature", "environment")

    objects = FeatureSegmentManager()

    class Meta:
        unique_together = ("feature", "environment", "segment")
        ordering = ("priority",)

    def __str__(self):
        return (
            "FeatureSegment for "
            + self.feature.name
            + " with priority "
            + str(self.priority)
        )

    def __lt__(self, other):
        """
        Kind of counter intuitive but since priority 1 is highest, we want to check if priority is GREATER than the
        priority of the other feature segment.
        """
        return other and self.priority > other.priority

    def clone(self, environment: "Environment") -> "FeatureSegment":
        clone = deepcopy(self)
        clone.id = None
        clone.uuid = uuid.uuid4()
        clone.environment = environment
        clone.save()
        return clone

    # noinspection PyTypeChecker
    def get_value(self):
        return get_correctly_typed_value(self.value_type, self.value)

    def get_create_log_message(self, history_instance) -> typing.Optional[str]:
        return FEATURE_SEGMENT_UPDATED_MESSAGE % (
            self.feature.name,
            self.environment.name,
        )

    def get_update_log_message(self, history_instance) -> typing.Optional[str]:
        return self.get_create_log_message(history_instance)

    def get_delete_log_message(self, history_instance) -> typing.Optional[str]:
        return SEGMENT_FEATURE_STATE_DELETED_MESSAGE % (
            self.feature.name,
            self.segment.name,
        )

    def get_audit_log_related_object_id(self, history_instance) -> typing.Optional[int]:
        # TODO: this is here to maintain current behaviour but should probably be fixed
        if history_instance.history_type == "-":
            feature_state = (
                self.feature_states.first()
            )  # due to incorrect foreign key rather than 1-1
            return getattr(feature_state, "id", None)
        return self.feature_id

    def get_audit_log_related_object_type(self, history_instance) -> RelatedObjectType:
        # TODO: this is here to maintain current behaviour but should probably be fixed
        if history_instance.history_type == "-":
            return RelatedObjectType.FEATURE_STATE
        return RelatedObjectType.FEATURE

    def _get_environment(self) -> typing.Optional["Environment"]:
        return self.environment

    def _get_project(self) -> typing.Optional["Project"]:
        return self.feature.project


class FeatureState(
    SoftDeleteObject,
    LifecycleModelMixin,
    AbstractBaseExportableModel,
    abstract_base_auditable_model_factory(["uuid"]),
):
    history_record_class_path = "features.models.HistoricalFeatureState"
    related_object_type = RelatedObjectType.FEATURE_STATE

    feature = models.ForeignKey(
        Feature, related_name="feature_states", on_delete=models.CASCADE
    )

    environment = models.ForeignKey(
        "environments.Environment",
        related_name="feature_states",
        null=True,
        on_delete=models.CASCADE,
    )
    identity = models.ForeignKey(
        "identities.Identity",
        related_name="identity_features",
        null=True,
        default=None,
        blank=True,
        on_delete=models.CASCADE,
    )
    feature_segment = models.ForeignKey(
        FeatureSegment,
        related_name="feature_states",
        null=True,
        blank=True,
        default=None,
        on_delete=models.CASCADE,
    )

    enabled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.IntegerField(default=1, null=True)
    live_from = models.DateTimeField(null=True)

    change_request = models.ForeignKey(
        "workflows_core.ChangeRequest",
        on_delete=models.SET_NULL,
        null=True,
        related_name="feature_states",
    )

    objects = FeatureStateManager()

    class Meta:
        ordering = ["id"]

    def __gt__(self, other):
        """
        Checks if the current feature state is higher priority that the provided feature state.

        :param other: (FeatureState) the feature state to compare the priority of
        :return: True if self is higher priority than other
        """
        if self.environment_id != other.environment_id:
            raise ValueError(
                "Cannot compare feature states as they belong to different environments."
            )

        if self.feature_id != other.feature_id:
            raise ValueError(
                "Cannot compare feature states as they belong to different features."
            )

        if self.identity_id:
            # identity is the highest priority so we can always return true
            if other.identity_id and self.identity_id != other.identity_id:
                raise ValueError(
                    "Cannot compare feature states as they are for different identities."
                )
            return True

        if self.feature_segment_id:
            # Return true if other_feature_state has a lower priority feature segment and not an identity overridden
            # flag, else False.
            return not (
                other.identity_id or self.feature_segment < other.feature_segment
            )

        if self.type == other.type:
            return (
                self.version is not None
                and other.version is not None
                and self.version > other.version
            ) or (self.version is not None and other.version is None)

        # if we've reached here, then self is just the environment default. In this case, other is higher priority if
        # it has a feature_segment or an identity
        return not (other.feature_segment_id or other.identity_id)

    def __str__(self):
        s = f"Feature {self.feature.name} - Enabled: {self.enabled}"
        if self.environment is not None:
            s = f"{self.environment} - {s}"
        elif self.identity is not None:
            s = f"Identity {self.identity.identifier} - {s}"
        return s

    @property
    def previous_feature_state_value(self):
        try:
            history_instance = self.feature_state_value.history.first()
            return (
                history_instance
                and getattr(history_instance, "prev_record", None)
                and history_instance.prev_record.instance.value
            )
        except ObjectDoesNotExist:
            return None

    @property
    def type(self) -> str:
        if self.identity_id and self.feature_segment_id is None:
            return IDENTITY
        elif self.feature_segment_id and self.identity_id is None:
            return FEATURE_SEGMENT
        elif self.identity_id is None and self.feature_segment_id is None:
            return ENVIRONMENT

        logger.error(
            "FeatureState %d does not have a valid type. Defaulting to environment.",
            self.id,
        )
        return ENVIRONMENT

    @property
    def is_live(self) -> bool:
        return (
            self.version is not None
            and self.live_from is not None
            and self.live_from <= timezone.now()
        )

    @property
    def is_scheduled(self) -> bool:
        return self.live_from > timezone.now()

    def clone(
        self,
        env: "Environment",
        live_from: datetime.datetime = None,
        as_draft: bool = False,
        version: int = None,
    ) -> "FeatureState":
        # Cloning the Identity is not allowed because they are closely tied
        # to the environment
        assert self.identity is None
        clone = deepcopy(self)
        clone.id = None
        clone.uuid = uuid.uuid4()
        clone.feature_segment = (
            FeatureSegment.objects.get(
                environment=env,
                feature=clone.feature,
                segment=self.feature_segment.segment,
            )
            if self.feature_segment
            else None
        )
        clone.environment = env
        clone.version = None if as_draft else version or self.version
        clone.live_from = live_from
        clone.save()
        # clone the related objects
        self.feature_state_value.clone(clone)

        if self.feature.type == MULTIVARIATE:
            mv_values = [
                mv_value.clone(feature_state=clone, persist=False)
                for mv_value in self.multivariate_feature_state_values.all()
            ]
            MultivariateFeatureStateValue.objects.bulk_create(mv_values)

        return clone

    def generate_feature_state_value_data(self, value):
        """
        Takes the value of a feature state to generate a feature state value and returns dictionary
        to use for passing into feature state value serializer

        :param value: feature state value of variable type
        :return: dictionary to pass directly into feature state value serializer
        """
        fsv_type = self.get_feature_state_value_type(value)
        return {
            "type": fsv_type,
            "feature_state": self.id,
            self.get_feature_state_key_name(fsv_type): value,
        }

    def get_feature_state_value_by_id(self, identity_id: int = None) -> typing.Any:
        feature_state_value = (
            self.get_multivariate_feature_state_value(identity_id)
            if self.feature.type == MULTIVARIATE and identity_id
            else getattr(self, "feature_state_value", None)
        )

        # return the value of the feature state value only if the feature state
        # has a related feature state value. Note that we use getattr rather than
        # hasattr as we want to return None if no feature state value exists.
        return feature_state_value and feature_state_value.value

    def get_feature_state_value(self, identity: "Identity" = None) -> typing.Any:
        return self.get_feature_state_value_by_id(getattr(identity, "id", None))

    def get_feature_state_value_defaults(self) -> dict:
        if (
            self.feature.initial_value is None
            or self.feature.project.prevent_flag_defaults
        ):
            return {}

        value = self.feature.initial_value
        type = get_value_type(value)
        parse_func = {
            BOOLEAN: get_boolean_from_string,
            INTEGER: get_integer_from_string,
        }.get(type, lambda v: v)
        key_name = self.get_feature_state_key_name(type)

        return {"type": type, key_name: parse_func(value)}

    def get_multivariate_feature_state_value(
        self, identity_id: int
    ) -> AbstractBaseFeatureValueModel:
        # the multivariate_feature_state_values should be prefetched at this point
        # so we just convert them to a list and use python operations from here to
        # avoid further queries to the DB
        mv_options = list(self.multivariate_feature_state_values.all())

        percentage_value = (
            get_hashed_percentage_for_object_ids([self.id, identity_id]) * 100
        )

        # Iterate over the mv options in order of id (so we get the same value each
        # time) to determine the correct value to return to the identity based on
        # the percentage allocations of the multivariate options. This gives us a
        # way to ensure that the same value is returned every time we use the same
        # percentage value.
        start_percentage = 0
        for mv_option in sorted(mv_options, key=lambda o: o.id):
            limit = getattr(mv_option, "percentage_allocation", 0) + start_percentage
            if start_percentage <= percentage_value < limit:
                return mv_option.multivariate_feature_option

            start_percentage = limit

        # if none of the percentage allocations match the percentage value we got for
        # the identity, then we just return the default feature state value (or None
        # if there isn't one - although this should never happen)
        return getattr(self, "feature_state_value", None)

    @hook(BEFORE_CREATE)
    def check_for_existing_feature_state(self):
        # prevent duplicate feature states being created for an environment
        if self.version is None:
            return

        if FeatureState.objects.filter(
            environment=self.environment,
            feature=self.feature,
            version=self.version,
            feature_segment=self.feature_segment,
            identity=self.identity,
        ).exists():
            raise ValidationError(
                "Feature state already exists for this environment, feature, "
                "version, segment & identity combination"
            )

    @hook(BEFORE_CREATE)
    def set_live_from_for_version_1(self):
        """
        Set the live_from date on newly created, version 1 feature states to maintain
        the previous behaviour.
        """
        if self.version == 1 and not self.live_from:
            self.live_from = timezone.now()

    @hook(AFTER_CREATE)
    def create_feature_state_value(self):
        # note: this is only performed after create since feature state values are
        # updated separately, and hence if this is performed after each save,
        # it overwrites the FSV with the initial value again
        FeatureStateValue.objects.create(
            feature_state=self,
            **self.get_feature_state_value_defaults(),
        )

    @hook(AFTER_CREATE)
    def create_multivariate_feature_state_values(self):
        if not (self.feature_segment or self.identity):
            # we only want to create the multivariate feature state values for
            # feature states related to an environment only, i.e. when a new
            # environment is created or a new MV feature is created
            mv_feature_state_values = [
                MultivariateFeatureStateValue(
                    feature_state=self,
                    multivariate_feature_option=mv_option,
                    percentage_allocation=mv_option.default_percentage_allocation,
                )
                for mv_option in self.feature.multivariate_options.all()
            ]
            MultivariateFeatureStateValue.objects.bulk_create(mv_feature_state_values)

    @staticmethod
    def get_feature_state_key_name(fsv_type) -> str:
        return {
            INTEGER: "integer_value",
            BOOLEAN: "boolean_value",
            STRING: "string_value",
        }.get(fsv_type)

    @staticmethod
    def get_feature_state_value_type(value) -> str:
        fsv_type = type(value).__name__
        accepted_types = (STRING, INTEGER, BOOLEAN)

        # Default to string if not an anticipate type value to keep backwards compatibility.
        return fsv_type if fsv_type in accepted_types else STRING

    @classmethod
    def get_environment_flags_list(
        cls,
        environment_id: int,
        feature_name: str = None,
        additional_filters: Q = None,
    ) -> typing.List["FeatureState"]:
        """
        Get a list of the latest committed versions of FeatureState objects that are
        associated with the given environment only (i.e. not identity or segment).

        Note: uses a single query to get all valid versions of a given environment's
        feature states. The logic to grab the latest version is then handled in python
        by building a dictionary. Returns a list of FeatureState objects.
        """
        # Get all feature states for a given environment with a valid live_from in the
        # past. Note: includes all versions for a given environment / feature
        # combination. We filter for the latest version later on.
        feature_states = cls.objects.select_related(
            "feature", "feature_state_value"
        ).filter(
            environment_id=environment_id,
            live_from__isnull=False,
            live_from__lte=timezone.now(),
            version__isnull=False,
        )
        if feature_name:
            feature_states = feature_states.filter(feature__name__iexact=feature_name)

        if additional_filters:
            feature_states = feature_states.filter(additional_filters)

        # Build up a dictionary in the form
        # {(feature_id, feature_segment_id, identity_id): feature_state}
        # and only keep the latest version for each feature.
        feature_states_dict = {}
        for feature_state in feature_states:
            key = (
                feature_state.feature_id,
                feature_state.feature_segment_id,
                feature_state.identity_id,
            )
            current_feature_state = feature_states_dict.get(key)
            if (
                not current_feature_state
                or feature_state.version > current_feature_state.version
            ):
                feature_states_dict[key] = feature_state

        return list(feature_states_dict.values())

    @classmethod
    def get_environment_flags_queryset(
        cls, environment_id: int, feature_name: str = None
    ) -> QuerySet:
        """
        Get a queryset of the latest live versions of an environments' feature states
        """

        feature_states_list = cls.get_environment_flags_list(
            environment_id, feature_name
        )
        return FeatureState.objects.filter(id__in=[fs.id for fs in feature_states_list])

    @classmethod
    def get_next_version_number(
        cls,
        environment_id: int,
        feature_id: int,
        feature_segment_id: int,
        identity_id: int,
    ):
        return (
            cls.objects.filter(
                environment__id=environment_id,
                feature__id=feature_id,
                feature_segment__id=feature_segment_id,
                identity__id=identity_id,
            )
            .aggregate(max_version=Max("version"))
            .get("max_version", 0)
            + 1
        )

    def get_create_log_message(self, history_instance) -> typing.Optional[str]:
        if self.change_request_id and not self.change_request.committed_at:
            # change requests create feature states that may not ever go live,
            # since we already include the change requests in the audit log
            # we don't want to create separate audit logs for the associated
            # feature states
            return

        if self.identity_id:
            return audit_helpers.get_identity_override_created_audit_message(self)
        elif self.feature_segment_id:
            return audit_helpers.get_segment_override_created_audit_message(self)

        return audit_helpers.get_environment_feature_state_created_audit_message(self)

    def get_update_log_message(self, history_instance) -> typing.Optional[str]:
        if self.change_request and not self.change_request.committed_at:
            return

        if self.identity:
            return IDENTITY_FEATURE_STATE_UPDATED_MESSAGE % (
                self.feature.name,
                self.identity.identifier,
            )
        elif self.feature_segment:
            return SEGMENT_FEATURE_STATE_UPDATED_MESSAGE % (
                self.feature.name,
                self.feature_segment.segment.name,
            )
        return FEATURE_STATE_UPDATED_MESSAGE % (
            history_instance.enabled,
            self.enabled,
            self.feature.name,
        )

    def get_delete_log_message(self, history_instance) -> typing.Optional[str]:
        try:
            if self.identity:
                return IDENTITY_FEATURE_STATE_DELETED_MESSAGE % (
                    self.feature.name,
                    self.identity.identifier,
                )
            elif self.feature_segment:
                return SEGMENT_FEATURE_STATE_DELETED_MESSAGE % (
                    self.feature.name,
                    self.feature_segment.segment.name,
                )

            # TODO: this is here to maintain current functionality, however, I'm not
            #  sure that we want to create an audit log record in this case
            return FEATURE_DELETED_MESSAGE % self.feature.name
        except ObjectDoesNotExist:
            # Account for cascade deletes
            return None

    def get_extra_audit_log_kwargs(self, history_instance) -> dict:
        kwargs = super().get_extra_audit_log_kwargs(history_instance)

        if (
            history_instance.history_type == "+"
            and self.feature_segment_id is None
            and self.identity_id is None
        ):
            kwargs["skip_signals"] = "send_environments_to_dynamodb"

        return kwargs

    def _get_environment(self) -> typing.Optional["Environment"]:
        return self.environment

    def _get_project(self) -> typing.Optional["Project"]:
        return self.feature.project


class FeatureStateValueBaseHistoricalModel(BaseHistoricalModel, FeatureValueMixin):
    class Meta:
        abstract = True


class FeatureStateValue(
    AbstractBaseFeatureValueModel,
    AbstractBaseExportableModel,
    SoftDeleteObject,
    abstract_base_auditable_model_factory(
        historical_records_excluded_fields=["uuid"],
        historical_records_base_classes=[FeatureStateValueBaseHistoricalModel],
    ),
):
    history_record_class_path = "features.models.HistoricalFeatureStateValue"
    related_object_type = RelatedObjectType.FEATURE_STATE

    feature_state = models.OneToOneField(
        FeatureState, related_name="feature_state_value", on_delete=models.CASCADE
    )

    objects = FeatureStateValueManager()

    def clone(self, feature_state: FeatureState) -> "FeatureStateValue":
        clone = deepcopy(self)
        clone.id = None
        clone.uuid = uuid.uuid4()
        clone.feature_state = feature_state
        clone.save()
        return clone

    def get_update_log_message(self, history_instance):
        feature_state = self.feature_state
        if (
            feature_state.change_request
            and not feature_state.change_request.committed_at
        ):
            return

        if feature_state.identity:
            return IDENTITY_FEATURE_STATE_VALUE_UPDATED_MESSAGE % (
                history_instance.prev_record.value,
                self.value,
                feature_state.feature.name,
                feature_state.identity.identifier,
            )
        elif feature_state.feature_segment:
            return SEGMENT_FEATURE_STATE_VALUE_UPDATED_MESSAGE % (
                history_instance.prev_record.value,
                self.value,
                feature_state.feature.name,
                feature_state.feature_segment.segment.name,
            )
        return FEATURE_STATE_VALUE_UPDATED_MESSAGE % (
            history_instance.prev_record.value,
            self.value,
            feature_state.feature.name,
        )

    def _get_environment(self) -> typing.Optional["Environment"]:
        return self.feature_state.environment
