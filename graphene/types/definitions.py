from collections import OrderedDict
import inspect
import copy
from itertools import chain
from functools import partial

from graphql.utils.assert_valid_name import assert_valid_name
from graphql.type.definition import GraphQLObjectType

from .options import Options


class ClassTypeMeta(type):
    options_class = Options

    def __new__(mcs, name, bases, attrs):
        super_new = super(ClassTypeMeta, mcs).__new__

        module = attrs.pop('__module__', None)
        doc = attrs.pop('__doc__', None)
        new_class = super_new(mcs, name, bases, {
            '__module__': module,
            '__doc__': doc
        })
        attr_meta = attrs.pop('Meta', None)
        if not attr_meta:
            meta = getattr(new_class, 'Meta', None)
        else:
            meta = attr_meta

        new_class.add_to_class('_meta', new_class.get_options(meta))
        if new_class._meta.name:
            assert_valid_name(new_class._meta.name)
        new_class.construct_graphql_type(bases)

        return mcs.construct(new_class, bases, attrs)

    def get_options(cls, meta):
        raise NotImplementedError("get_options is not implemented")

    def construct_graphql_type(cls, bases):
        raise NotImplementedError("construct_graphql_type is not implemented")

    def add_to_class(cls, name, value):
        # We should call the contribute_to_class method only if it's bound
        if not inspect.isclass(value) and hasattr(
                value, 'contribute_to_class'):
            value.contribute_to_class(cls, name)
        else:
            setattr(cls, name, value)

    def construct(cls, bases, attrs):
        # Add all attributes to the class.
        for obj_name, obj in attrs.items():
            cls.add_to_class(obj_name, obj)

        # if not cls._meta.abstract:
        #     from ..types import List, NonNull

        return cls


class FieldsMeta(type):

    def _build_field_map(cls, bases, local_fields):
        from ..utils.extract_fields import get_base_fields
        extended_fields = get_base_fields(cls, bases)
        fields = chain(extended_fields, local_fields)
        return OrderedDict((f.name, f) for f in fields)

    def _fields(cls, bases, attrs):
        from ..utils.is_graphene_type import is_graphene_type
        from ..utils.extract_fields import extract_fields

        inherited_types = [
            base._meta.graphql_type for base in bases if is_graphene_type(base) and not base._meta.abstract
        ]

        local_fields = extract_fields(cls, attrs)
        return partial(cls._build_field_map, inherited_types, local_fields)


class GrapheneGraphQLType(object):
    def __init__(self, *args, **kwargs):
        self.graphene_type = kwargs.pop('graphene_type')
        super(GrapheneGraphQLType, self).__init__(*args, **kwargs)


class GrapheneFieldsType(GrapheneGraphQLType):
    def __init__(self, *args, **kwargs):
        self._fields = None
        self._field_map = None
        super(GrapheneFieldsType, self).__init__(*args, **kwargs)

    def add_field(self, field):
        # We clear the cached fields
        self._field_map = None
        self._fields.add(field)


class FieldMap(object):
    def __init__(self, parent, bases=None, fields=None):
        self.parent = parent
        self.fields = fields or []
        self.bases = bases or []

    def add(self, field):
        self.fields.append(field)

    def __call__(self):
        # It's in a call function for assuring that if a field is added
        # in runtime then it will be reflected in the Class type fields
        # If we add the field in the class type creation, then we
        # would not be able to change it later.
        from .field import Field
        prev_fields = []
        graphql_type = self.parent._meta.graphql_type

        # We collect the fields from the interfaces
        if isinstance(graphql_type, GraphQLObjectType):
            interfaces = graphql_type.get_interfaces()
            for interface in interfaces:
                prev_fields += interface.get_fields().items()

        # We collect the fields from the bases
        for base in self.bases:
            prev_fields += base.get_fields().items()

        fields = prev_fields + [
            (field.name, field) for field in sorted(self.fields)
        ]

        # Then we copy all the fields and assign the parent
        new_fields = []
        for field_name, field in fields:
            field = copy.copy(field)
            if isinstance(field, Field):
                field.parent = self.parent
            new_fields.append((field_name, field))

        return OrderedDict(new_fields)
