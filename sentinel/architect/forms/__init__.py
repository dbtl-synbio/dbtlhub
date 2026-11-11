"""The structured specification forms: the template, the instances, the loader.

    architect/forms.py              the seam - Form, Section, Field, Filled,
                                    and the INSTANCE_MAY / INSTANCE_MAY_NOT
                                    rules. Not redefined here.
    architect/forms/template.yaml   the generic form
    architect/forms/<case>.yaml     one use case's instance of it
    architect/forms/loader.py       read, check, convert

This package has the same dotted name as the seam module beside it, and a
package shadows a module - so `loader` loads `forms.py` from its path and
re-exports its dataclasses here. Anything that did `from architect.forms import
Field` before this package existed still gets the same class.
"""
from architect.forms.loader import (  # noqa: F401
    INSTANCE_MAY,
    INSTANCE_MAY_NOT,
    Field,
    Filled,
    Form,
    FormError,
    InstanceDoesNotFit,
    Kind,
    Section,
    answer,
    audit,
    fill,
    load_form,
    load_instance,
    load_template,
    to_specification,
    validate_instance,
)

__all__ = ["Field", "Filled", "Form", "Kind", "Section", "INSTANCE_MAY",
           "INSTANCE_MAY_NOT", "FormError", "InstanceDoesNotFit", "load_form",
           "load_template", "load_instance", "validate_instance", "audit",
           "fill", "answer", "to_specification"]
