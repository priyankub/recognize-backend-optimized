"""Patch recognize_backend ocs.py: niquests' `codes` is a lookup dict, not callable, so any HTTP error while
downloading a task file raised "'LookupDict' object is not callable" and hid the real status. Use http.HTTPStatus.
Fails the build if upstream changed."""
import sys
p = sys.argv[1]
s = open(p).read()
old = "    raise NextcloudException(status_code, reason=codes(status_code).phrase, info=info)\n"
new = '''    try:
        from http import HTTPStatus
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        phrase = "HTTP error"
    raise NextcloudException(status_code, reason=phrase, info=info)
'''
if s.count(old) != 1:
    sys.exit("fix_ocs_error patch: anchor not found exactly once")
open(p, "w").write(s.replace(old, new))
print("fix_ocs_error patch applied")
