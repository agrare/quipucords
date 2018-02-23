#
# Copyright (c) 2018 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 3 (GPLv3). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv3
# along with this software; if not, see
# https://www.gnu.org/licenses/gpl-3.0.txt.
#
"""Module for serializing all model object for database storage."""

import json
from django.db import transaction
from django.utils.translation import ugettext as _
from rest_framework.serializers import (ValidationError,
                                        IntegerField,
                                        CharField)
from api.models import Source, ScanTask, Scan, ScanOptions
import api.messages as messages
from api.common.serializer import (NotEmptySerializer,
                                   ValidStringChoiceField,
                                   CustomJSONField)
from api.scantasks.serializer import SourceField
from api.common.util import check_for_existing_name


class ScanOptionsSerializer(NotEmptySerializer):
    """Serializer for the ScanOptions model."""

    max_concurrency = IntegerField(required=False, min_value=1, default=50)
    disable_optional_products = CustomJSONField(required=False)

    class Meta:
        """Metadata for serializer."""

        model = ScanOptions
        fields = ['max_concurrency',
                  'disable_optional_products']

    # pylint: disable=invalid-name
    @staticmethod
    def validate_disable_optional_products(disable_optional_products):
        """Make sure that extra vars are a dictionary with boolean values."""
        disable_optional_products = ScanOptions.get_optional_products(
            disable_optional_products)

        if not isinstance(disable_optional_products, dict):
            raise ValidationError(_(messages.SJ_EXTRA_VARS_DICT))
        for key in disable_optional_products:
            if not isinstance(disable_optional_products[key], bool):
                raise ValidationError(_(messages.SJ_EXTRA_VARS_BOOL))
            elif key not in [ScanOptions.JBOSS_EAP,
                             ScanOptions.JBOSS_BRMS,
                             ScanOptions.JBOSS_FUSE]:
                raise ValidationError(_(messages.SJ_EXTRA_VARS_KEY))
        return json.dumps(disable_optional_products)


class ScanSerializer(NotEmptySerializer):
    """Serializer for the Scan model."""

    name = CharField(required=True, read_only=False, max_length=64)
    sources = SourceField(many=True, queryset=Source.objects.all())
    scan_type = ValidStringChoiceField(required=False,
                                       choices=ScanTask.SCAN_TYPE_CHOICES)
    options = ScanOptionsSerializer(required=False, many=False)

    class Meta:
        """Metadata for serializer."""

        model = Scan
        fields = ['id', 'name', 'sources', 'scan_type', 'options']

    @transaction.atomic
    def create(self, validated_data):
        """Create a scan."""
        name = validated_data.get('name')
        check_for_existing_name(
            Scan.objects,
            name,
            _(messages.SCAN_NAME_ALREADY_EXISTS % name))

        options = validated_data.pop('options', None)
        scan = super().create(validated_data)
        if options:
            options = ScanOptions.objects.create(**options)
        else:
            options = ScanOptions()
        options.save()
        scan.options = options
        scan.save()

        return scan

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update a scan."""
        # If we ever add optional fields to Scan, we need to
        # add logic here to clear them on full update even if they are
        # not supplied.
        name = validated_data.get('name')
        check_for_existing_name(
            Scan.objects,
            name,
            _(messages.HC_NAME_ALREADY_EXISTS % name),
            search_id=instance.id)

        name = validated_data.pop('name', None)
        scan_type = validated_data.pop('scan_type', None)
        sources = validated_data.pop('sources', None)
        options = validated_data.pop('options', None)
        if not self.partial:
            instance.name = name
            instance.scan_type = scan_type
            instance.sources = sources
            if options:
                options = ScanOptions.objects.create(**options)
            else:
                options = ScanOptions()
            instance.options = options
        else:
            if name is not None:
                instance.name = name
            if scan_type is not None:
                instance.scan_type = scan_type
            if sources is not None:
                instance.sources = sources
            if options is not None:
                instance.options = ScanOptions.objects.create(**options)

        instance.save()
        return instance

    @staticmethod
    def validate_sources(sources):
        """Make sure the source is present."""
        if not sources:
            raise ValidationError(_(messages.SJ_REQ_SOURCES))

        return sources