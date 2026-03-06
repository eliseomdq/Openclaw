import pytest
from unittest.mock import patch, MagicMock
from workers.deployer import slugify, upload_to_github_pages


def test_slugify_basic():
    result = slugify("Plomería González & Hijos")
    assert result == "plomeria-gonzalez-hijos"


def test_slugify_max_length():
    long_name = "A" * 100
    assert len(slugify(long_name)) <= 50


def test_upload_creates_url():
    with patch("workers.deployer.requests.get") as mock_get, \
         patch("workers.deployer.requests.put") as mock_put, \
         patch("workers.deployer.GITHUB_USERNAME", "testuser"), \
         patch("workers.deployer.GITHUB_REPO", "test-repo"):

        mock_get.return_value = MagicMock(status_code=404)
        mock_put.return_value = MagicMock(status_code=201)
        mock_put.return_value.raise_for_status = lambda: None

        url = upload_to_github_pages(1, "Plomeria Test", "<html></html>")

        assert "testuser.github.io" in url
        assert "plomeria-test" in url
