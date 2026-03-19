"""Tests for ErrorAction enum and AgencyError hierarchy."""

from agency.errors import (
    AgencyError,
    ConfigurationError,
    ErrorAction,
    MessageValidationError,
    TransientError,
)


def test_error_action_values():
    """ErrorAction enum has exactly four members."""
    assert ErrorAction.RETRY.value == "RETRY"
    assert ErrorAction.SKIP.value == "SKIP"
    assert ErrorAction.ESCALATE.value == "ESCALATE"
    assert ErrorAction.STOP.value == "STOP"
    assert len(ErrorAction) == 4


def test_agency_error_is_exception():
    """AgencyError is a proper Exception subclass."""
    err = AgencyError("test error")
    assert isinstance(err, Exception)
    assert str(err) == "test error"


def test_transient_error_hierarchy():
    """TransientError is a subclass of AgencyError."""
    err = TransientError("timeout")
    assert isinstance(err, AgencyError)
    assert isinstance(err, Exception)


def test_message_validation_error_hierarchy():
    """MessageValidationError is a subclass of AgencyError."""
    err = MessageValidationError("bad message")
    assert isinstance(err, AgencyError)


def test_configuration_error_hierarchy():
    """ConfigurationError is a subclass of AgencyError."""
    err = ConfigurationError("missing config")
    assert isinstance(err, AgencyError)


def test_errors_are_catchable_as_agency_error():
    """All subclass errors can be caught with 'except AgencyError'."""
    for err_cls in [TransientError, MessageValidationError, ConfigurationError]:
        try:
            raise err_cls("test")
        except AgencyError:
            pass  # expected
