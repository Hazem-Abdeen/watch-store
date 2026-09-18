"""Fetch only legacy uploads, validating every redirect and raster image."""

import warnings
from io import BytesIO
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image

from .sql_dump import ImportDataError


PREFIX = '/wp-content/uploads/'
MAX_BYTES = 10 * 1024 * 1024


def uploads_url(value):
    if not isinstance(value, str) or not value:
        raise ImportDataError('Missing attachment path.')
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ImportDataError('Control character in attachment path.')
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        if (parsed.scheme not in {'http', 'https'}
                or parsed.netloc not in {'abdeenwatches.com', 'www.abdeenwatches.com'}):
            raise ImportDataError('Attachment URL is outside the legacy uploads host.')
        path = parsed.path
    elif value.startswith('/'):
        path = parsed.path
    else:
        path = PREFIX + parsed.path
    path = unquote(path, errors='strict')
    if (parsed.query or parsed.fragment or not path.startswith(PREFIX)
            or any(part in {'', '.', '..'} for part in path[len(PREFIX):].split('/'))
            or any(char in path for char in ('\\', '%', '?', '#'))
            or any(ord(char) < 32 or ord(char) == 127 for char in path)):
        raise ImportDataError('Attachment path is outside the legacy uploads directory.')
    return 'https://abdeenwatches.com' + quote(path, safe='/')


class UploadsRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Validation happens BEFORE urllib follows the redirect.
        if not urlsplit(newurl).netloc:
            raise ImportDataError('Invalid image redirect.')
        newurl = uploads_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_image(url):
    url = uploads_url(url)
    request = Request(url, headers={'User-Agent': 'AbdeenCatalogueImporter/1.0'})
    with build_opener(UploadsRedirectHandler()).open(request, timeout=15) as response:
        uploads_url(response.geturl())
        content = response.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ImportDataError('Image exceeds the 10 MiB limit.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > 20_000_000:
                raise ImportDataError('Image exceeds the 20 megapixel limit.')
            extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif'}.get(image.format)
            if extension is None:
                raise ImportDataError('Unsupported raster image format.')
            image.verify()
    return content, extension
