"""Keep the regression suite away from live services and operational files."""

import socket

import pytest

from ChatBotAI.config import TestingConfig


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(TestingConfig, 'CHATBOT_INSTANCE_PATH', str(tmp_path), raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError('Live network access is disabled in tests; mock the integration.')

    monkeypatch.setattr(socket.socket, 'connect', no_network)
    monkeypatch.setattr(socket.socket, 'connect_ex', no_network)
