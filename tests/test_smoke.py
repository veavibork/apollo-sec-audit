import socket

import pytest
from pytest_socket import SocketBlockedError


def test_package_imports() -> None:
    import crm_audit

    assert crm_audit.__name__ == "crm_audit"


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_network_is_blocked() -> None:
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
