"""Local Whoosh compatibility for Haystack 3.4's offset-based API."""

from haystack.backends.whoosh_backend import WhooshEngine, WhooshSearchBackend


class OffsetWhooshSearchBackend(WhooshSearchBackend):
    def search(self, query_string, start_offset=0, end_offset=None, **kwargs):
        start = start_offset or 0
        length = end_offset - start if end_offset is not None else None
        # Haystack converts offsets into a Whoosh page number using the slice
        # length. A short final page need not align: [720:731] becomes page 66
        # of length 11, incorrectly starting at 715. Fetch the prefix only for
        # unaligned slices, then return the exact requested offset range.
        if start and (length is None or (length > 0 and start % length)):
            result = super().search(
                query_string, start_offset=0, end_offset=end_offset, **kwargs,
            )
            result['results'] = result['results'][start:]
            return result
        return super().search(
            query_string, start_offset=start_offset, end_offset=end_offset, **kwargs,
        )


class LocalWhooshEngine(WhooshEngine):
    backend = OffsetWhooshSearchBackend
